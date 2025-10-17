from collections import defaultdict
from datetime import timedelta
from typing import Iterable

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db.models import Case, Count, F, IntegerField, Q, Sum, When
from django.db.models.functions import Coalesce
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .forms import UserPreferencesForm
from .lock_service import LockLimitError, LockService
from .models import (
    NbaPlayer,
    NbaTeam,
    Option,
    OptionCategory,
    PredictionEvent,
    TipType,
    UserPreferences,
    UserEventScore,
    UserTip,
)
from .services import sync_weekly_games
from .theme_palettes import DEFAULT_THEME_KEY, get_theme_palette


def _get_active_user(request):
    user_id = request.session.get('active_user_id')
    if not user_id:
        return None
    User = get_user_model()
    try:
        return User.objects.get(pk=user_id)
    except User.DoesNotExist:
        request.session.pop('active_user_id', None)
        return None


def _build_display_name_map(user_ids: Iterable[int]) -> dict[int, str]:
    unique_ids = {user_id for user_id in user_ids if user_id}
    if not unique_ids:
        return {}

    nickname_map: dict[int, str] = {}
    for preferences in UserPreferences.objects.filter(user_id__in=unique_ids):
        nickname = (preferences.nickname or '').strip()
        if nickname:
            nickname_map[preferences.user_id] = nickname
    return nickname_map


def _apply_display_metadata(user, display_name_map: dict[int, str]) -> None:
    if user is None:
        return
    display_name = display_name_map.get(user.id, user.username)
    user.display_name = display_name
    user.display_initial = display_name[:1].upper() if display_name else ''


@require_http_methods(["GET", "POST"])
def home(request):
    sync_weekly_games()
    active_user = _get_active_user(request)
    preferences = None
    preferences_form = None

    if active_user:
        preferences, _ = UserPreferences.objects.get_or_create(user=active_user)

    now = timezone.now()

    tip_types = list(TipType.objects.filter(is_active=True).order_by('deadline'))
    sections: list[dict] = []

    for tip_type in tip_types:
        events = list(
            PredictionEvent.objects.filter(
                tip_type=tip_type,
                is_active=True,
                opens_at__lte=now,
            )
            .exclude(deadline__lt=now)
            .select_related('scheduled_game')
            .prefetch_related('options__team', 'options__player')
            .order_by('deadline', 'sort_order', 'name')
        )
        if not events:
            continue

        sections.append({'tip_type': tip_type, 'events': events})

    visible_events: list[PredictionEvent] = []
    seen_event_ids: set[int] = set()
    for section in sections:
        for event in section['events']:
            if event.id in seen_event_ids:
                continue
            seen_event_ids.add(event.id)
            visible_events.append(event)

    requires_team_choices = any(
        event.selection_mode == PredictionEvent.SelectionMode.ANY
        and event.target_kind == PredictionEvent.TargetKind.TEAM
        for event in visible_events
    )
    requires_player_choices = any(
        event.selection_mode == PredictionEvent.SelectionMode.ANY
        and event.target_kind == PredictionEvent.TargetKind.PLAYER
        for event in visible_events
    )

    team_choices = list(NbaTeam.objects.order_by('name')) if requires_team_choices else []
    player_choices = list(NbaPlayer.objects.order_by('display_name')) if requires_player_choices else []

    user_tips: dict[int, UserTip] = {}
    if active_user and visible_events:
        user_tips = {
            tip.prediction_event_id: tip
            for tip in UserTip.objects.filter(
                user=active_user,
                prediction_event__in=visible_events,
            )
        }

    if request.method == 'POST':
        if 'set_active_user' in request.POST:
            user_id = request.POST.get('user_id')
            action = request.POST.get('active_user_action')

            if (
                action == 'finish'
                and active_user is not None
                and user_id == str(active_user.id)
            ):
                request.session.pop('active_user_id', None)
                messages.success(request, 'Active user cleared successfully.')
                return redirect('predictions:home')

            if user_id:
                request.session['active_user_id'] = int(user_id)
                messages.success(request, 'Active user selected successfully.')
            else:
                request.session.pop('active_user_id', None)
                messages.info(request, 'No active user selected.')
            return redirect('predictions:home')

        if 'update_preferences' in request.POST:
            if not active_user or preferences is None:
                messages.error(request, 'Please activate a user before updating preferences.')
                return redirect('predictions:home')

            preferences_form = UserPreferencesForm(
                data=request.POST,
                instance=preferences,
            )
            if preferences_form.is_valid():
                preferences_form.save()
                messages.success(request, 'Your preferences have been updated!')
                return redirect('predictions:home')

            messages.error(request, 'Please correct the errors below to update preferences.')

        if 'save_tips' in request.POST:
            if not active_user:
                messages.error(request, 'Please activate a user before saving picks.')
                return redirect('predictions:home')

            if not visible_events:
                messages.error(request, 'No prediction events are available right now.')
                return redirect('predictions:home')

            lock_service = LockService(active_user)
            lock_service.refresh()
            insufficient_lock_events: list[PredictionEvent] = []
            deadline_locked_events: list[PredictionEvent] = []
            saved = 0
            for event in visible_events:
                key = f'prediction_{event.id}'
                submitted_value = request.POST.get(key)
                lock_key = f'lock_{event.id}'
                should_lock = request.POST.get(lock_key) == '1'

                if not submitted_value:
                    existing_tip = user_tips.get(event.id)
                    if existing_tip is None:
                        continue
                    option = existing_tip.prediction_option
                    selected_option = existing_tip.selected_option
                    prediction_label = existing_tip.prediction
                else:
                    option = None
                    selected_option = None
                    prediction_label = ''

                    if event.selection_mode == PredictionEvent.SelectionMode.CURATED:
                        try:
                            option_id = int(submitted_value)
                        except (TypeError, ValueError):
                            continue
                        option = next(
                            (
                                item
                                for item in event.options.all()
                                if item.id == option_id
                            ),
                            None,
                        )
                        if not option:
                            continue
                        # Get the underlying generic option
                        selected_option = option.option
                        prediction_label = option.label
                    else:
                        # ANY selection mode - select from available options
                        if event.target_kind == PredictionEvent.TargetKind.TEAM:
                            try:
                                team_id = int(submitted_value)
                            except (TypeError, ValueError):
                                continue
                            selected_team = next(
                                (team for team in team_choices if team.id == team_id),
                                None,
                            )
                            if not selected_team:
                                continue
                            prediction_label = selected_team.name
                            # Find or create the Option for this team
                            selected_option = Option.objects.filter(
                                category__slug='nba-teams',
                                metadata__nba_team_id=selected_team.id
                            ).first()
                        elif event.target_kind == PredictionEvent.TargetKind.PLAYER:
                            try:
                                player_id = int(submitted_value)
                            except (TypeError, ValueError):
                                continue
                            selected_player = next(
                                (player for player in player_choices if player.id == player_id),
                                None,
                            )
                            if not selected_player:
                                continue
                            prediction_label = selected_player.display_name
                            # Find or create the Option for this player
                            selected_option = Option.objects.filter(
                                category__slug='nba-players',
                                metadata__nba_player_id=selected_player.id
                            ).first()
                        else:
                            # Generic option selection
                            try:
                                generic_option_id = int(submitted_value)
                            except (TypeError, ValueError):
                                continue
                            selected_option = Option.objects.filter(
                                id=generic_option_id
                            ).first()
                            if not selected_option:
                                continue
                            prediction_label = selected_option.name

                tip = user_tips.get(event.id)
                if tip is None:
                    tip = UserTip(
                        user=active_user,
                        prediction_event=event,
                    )
                tip.tip_type = event.tip_type
                tip.prediction = prediction_label
                tip.prediction_option = option
                tip.selected_option = selected_option
                tip.save()
                user_tips[event.id] = tip
                saved += 1

                if should_lock:
                    try:
                        lock_service.ensure_locked(tip)
                    except LockLimitError:
                        insufficient_lock_events.append(event)
                elif tip.is_locked:
                    if event.deadline <= now:
                        deadline_locked_events.append(event)
                    else:
                        lock_service.release_lock(tip)

            if saved:
                messages.success(request, 'Your picks have been saved!')
            else:
                messages.info(request, 'No picks were provided, nothing to save.')

            if insufficient_lock_events:
                event_titles = ', '.join(event.name for event in insufficient_lock_events)
                messages.error(
                    request,
                    f"Unable to lock {event_titles}. You have no locks remaining.",
                )

            if deadline_locked_events:
                event_titles = ', '.join(event.name for event in deadline_locked_events)
                messages.warning(
                    request,
                    f"Locks for {event_titles} could not be removed because the deadline has passed.",
                )
            return redirect('predictions:home')

    all_users = list(get_user_model().objects.order_by('username'))
    lock_summary = None
    scoreboard_summary = None
    recent_scores: list[UserEventScore] = []
    if active_user:
        lock_summary = LockService(active_user).refresh()

        score_queryset = (
            UserEventScore.objects.filter(user=active_user)
            .select_related('prediction_event__tip_type')
            .order_by('-awarded_at', '-id')
        )
        recent_scores = list(score_queryset[:5])
        for score in recent_scores:
            score.lock_bonus_value = max(score.points_awarded - score.base_points, 0)

        bonus_event_points_expr = Case(
            When(prediction_event__is_bonus_event=True, then=F('base_points')),
            default=0,
            output_field=IntegerField(),
        )
        bonus_event_count_expr = Case(
            When(prediction_event__is_bonus_event=True, then=1),
            default=0,
            output_field=IntegerField(),
        )
        lock_bonus_points_expr = Case(
            When(is_lock_bonus=True, then=F('points_awarded') - F('base_points')),
            default=0,
            output_field=IntegerField(),
        )
        lock_bonus_count_expr = Case(
            When(is_lock_bonus=True, then=1),
            default=0,
            output_field=IntegerField(),
        )

        aggregated = score_queryset.aggregate(
            total_points=Coalesce(Sum('points_awarded'), 0),
            base_points_total=Coalesce(Sum('base_points'), 0),
            bonus_event_points=Coalesce(Sum(bonus_event_points_expr), 0),
            bonus_event_count=Coalesce(Sum(bonus_event_count_expr), 0),
            lock_bonus_points=Coalesce(Sum(lock_bonus_points_expr), 0),
            lock_bonus_count=Coalesce(Sum(lock_bonus_count_expr), 0),
            events_scored=Coalesce(Count('prediction_event', distinct=True), 0),
        )

        scoreboard_summary = {key: int(value) for key, value in aggregated.items()}
        base_points_total = scoreboard_summary.pop('base_points_total', 0)
        scoreboard_summary['base_points'] = base_points_total
        bonus_event_points_total = scoreboard_summary.get('bonus_event_points', 0)
        scoreboard_summary['standard_points'] = max(base_points_total - bonus_event_points_total, 0)

    event_tip_users: dict[int, list] = defaultdict(list)
    tip_user_objects: list = []
    if visible_events:
        for tip in (
            UserTip.objects.filter(
                prediction_event__in=visible_events,
            )
            .select_related('user')
            .order_by('user__username')
        ):
            event_tip_users[tip.prediction_event_id].append(tip.user)
            tip_user_objects.append(tip.user)

    upcoming_range_start = timezone.localdate(now)
    upcoming_range_end = upcoming_range_start + timedelta(days=6)

    def event_sort_key(event: PredictionEvent) -> tuple:
        return (
            event.deadline,
            event.sort_order,
            event.name.lower(),
        )

    upcoming_events = [
        event
        for event in visible_events
        if event.deadline is not None
        and upcoming_range_start
        <= timezone.localdate(event.deadline)
        <= upcoming_range_end
    ]

    upcoming_events.sort(key=event_sort_key)

    events_by_day: dict = defaultdict(list)
    for event in upcoming_events:
        deadline_date = timezone.localdate(event.deadline)
        events_by_day[deadline_date].append(event)

    for event_list in events_by_day.values():
        event_list.sort(key=event_sort_key)

    weekday_slots = []
    for offset in range(7):
        slot_date = upcoming_range_start + timedelta(days=offset)
        day_events = events_by_day.get(slot_date, [])
        weekday_slots.append({'date': slot_date, 'events': day_events})

    week_start = upcoming_range_start
    week_end = upcoming_range_end

    if preferences_form is None and preferences is not None:
        preferences_form = UserPreferencesForm(instance=preferences)

    selected_theme_key = DEFAULT_THEME_KEY
    if preferences_form and preferences_form.is_bound:
        selected_theme_key = preferences_form.data.get('theme', '') or selected_theme_key
    elif preferences:
        selected_theme_key = preferences.theme

    active_theme_palette = get_theme_palette(selected_theme_key)

    display_name_ids: list[int] = [user.id for user in all_users]
    if active_user:
        display_name_ids.append(active_user.id)
    display_name_ids.extend(user.id for user in tip_user_objects)
    display_name_map = _build_display_name_map(display_name_ids)

    for user in all_users:
        _apply_display_metadata(user, display_name_map)
    for user in tip_user_objects:
        _apply_display_metadata(user, display_name_map)
    _apply_display_metadata(active_user, display_name_map)

    context = {
        'active_user': active_user,
        'users': all_users,
        'user_tips': user_tips,
        'event_tip_users': event_tip_users,
        'now': now,
        'weekday_slots': weekday_slots,
        'week_start': week_start,
        'week_end': week_end,
        'user_preferences': preferences,
        'preferences_form': preferences_form,
        'event_sections': sections,
        'team_choices': team_choices,
        'player_choices': player_choices,
        'lock_summary': lock_summary,
        'scoreboard_summary': scoreboard_summary,
        'recent_scores': recent_scores,
        'active_theme_palette': active_theme_palette,
    }
    return render(request, 'predictions/home.html', context)


@require_http_methods(["GET"])
def leaderboard(request):
    User = get_user_model()

    tip_types = list(TipType.objects.filter(is_active=True).order_by('name'))
    tip_type_slug = request.GET.get('tip_type', '').strip()
    selected_segment = request.GET.get('segment', '').strip()
    selected_sort = request.GET.get('sort', 'total').strip().lower()

    order_map = {
        'total': ('-total_points', '-event_count', 'username'),
        'bonus': ('-bonus_event_points', '-total_points', 'username'),
        'locks': ('-lock_bonus_points', '-total_points', 'username'),
        'events': ('-event_count', '-total_points', 'username'),
    }
    if selected_sort not in order_map:
        selected_sort = 'total'

    filter_condition = Q()
    if tip_type_slug:
        filter_condition &= Q(usereventscore__prediction_event__tip_type__slug=tip_type_slug)
    if selected_segment:
        filter_condition &= Q(usereventscore__prediction_event__tip_type__category=selected_segment)

    user_queryset = User.objects.filter(usereventscore__isnull=False)

    bonus_event_points_expr = Case(
        When(
            usereventscore__prediction_event__is_bonus_event=True,
            then=F('usereventscore__base_points'),
        ),
        default=0,
        output_field=IntegerField(),
    )
    bonus_event_count_expr = Case(
        When(usereventscore__prediction_event__is_bonus_event=True, then=1),
        default=0,
        output_field=IntegerField(),
    )
    lock_bonus_points_expr = Case(
        When(
            usereventscore__is_lock_bonus=True,
            then=F('usereventscore__points_awarded') - F('usereventscore__base_points'),
        ),
        default=0,
        output_field=IntegerField(),
    )
    lock_bonus_count_expr = Case(
        When(usereventscore__is_lock_bonus=True, then=1),
        default=0,
        output_field=IntegerField(),
    )

    annotated_users = user_queryset.annotate(
        total_points=Coalesce(Sum('usereventscore__points_awarded', filter=filter_condition), 0),
        base_points=Coalesce(Sum('usereventscore__base_points', filter=filter_condition), 0),
        bonus_event_points=Coalesce(Sum(bonus_event_points_expr, filter=filter_condition), 0),
        bonus_event_count=Coalesce(Sum(bonus_event_count_expr, filter=filter_condition), 0),
        lock_bonus_points=Coalesce(Sum(lock_bonus_points_expr, filter=filter_condition), 0),
        lock_bonus_count=Coalesce(Sum(lock_bonus_count_expr, filter=filter_condition), 0),
        event_count=Coalesce(
            Count('usereventscore__prediction_event', distinct=True, filter=filter_condition),
            0,
        ),
    )

    score_filters_applied = bool(tip_type_slug or selected_segment)
    if score_filters_applied:
        annotated_users = annotated_users.filter(event_count__gt=0)

    order_fields = order_map[selected_sort]
    leaderboard_qs = annotated_users.order_by(*order_fields)

    leaderboard_rows = list(leaderboard_qs)
    user_ids = [row.id for row in leaderboard_rows]
    display_name_map = _build_display_name_map(user_ids)

    for index, row in enumerate(leaderboard_rows, start=1):
        row.display_name = display_name_map.get(row.id, row.username)
        row.total_points = int(row.total_points)
        row.base_points = int(row.base_points)
        row.bonus_event_points = int(row.bonus_event_points)
        row.lock_bonus_points = int(row.lock_bonus_points)
        row.event_count = int(row.event_count)
        row.bonus_event_count = int(row.bonus_event_count)
        row.lock_bonus_count = int(row.lock_bonus_count)
        row.standard_points = max(row.base_points - row.bonus_event_points, 0)
        row.rank = index

    sort_options = [
        ('total', 'Total points'),
        ('bonus', 'Bonus events'),
        ('locks', 'Lock bonuses'),
        ('events', 'Events scored'),
    ]

    selected_tip_type_obj = next(
        (tip_type for tip_type in tip_types if tip_type.slug == tip_type_slug),
        None,
    )

    context = {
        'leaderboard_rows': leaderboard_rows,
        'tip_types': tip_types,
        'segments': TipType.TipCategory.choices,
        'selected_tip_type': tip_type_slug,
        'selected_tip_type_obj': selected_tip_type_obj,
        'selected_segment': selected_segment,
        'sort_options': sort_options,
        'selected_sort': selected_sort,
        'score_filters_applied': score_filters_applied,
        'result_count': len(leaderboard_rows),
    }
    return render(request, 'predictions/leaderboard.html', context)
