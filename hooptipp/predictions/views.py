from collections import defaultdict
from datetime import timedelta
from typing import Iterable

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db.models import Case, Count, F, IntegerField, Q, Sum, When
from django.db.models.functions import Coalesce
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
import json

from hooptipp.nba.managers import NbaPlayerManager, NbaTeamManager
from hooptipp.user_context import get_active_user, set_active_user, clear_active_user

from .forms import UserPreferencesForm
from .lock_service import LockLimitError, LockService
from .models import (
    EventOutcome,
    Option,
    OptionCategory,
    PredictionEvent,
    PredictionOption,
    Season,
    TipType,
    UserPreferences,
    UserEventScore,
    UserTip,
)
from .theme_palettes import DEFAULT_THEME_KEY, get_theme_palette


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
    # Sync events via event sources if needed
    # Event sources can be triggered manually via admin or scheduled tasks
    active_user = get_active_user(request)
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
            .prefetch_related('options__option__category')
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

    # Always load team choices for PIN modal functionality
    team_choices = list(NbaTeamManager.all())
    player_choices = list(NbaPlayerManager.all()) if requires_player_choices else []

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
                clear_active_user(request)
                messages.success(request, 'Active user cleared successfully.')
                return redirect('predictions:home')

            if user_id:
                # Check if PIN validation is required
                if action == 'activate':
                    selected_teams = request.POST.getlist('pin_teams')
                    User = get_user_model()
                    try:
                        target_user = User.objects.get(pk=user_id)
                        user_prefs, _ = UserPreferences.objects.get_or_create(user=target_user)
                        
                        # Validate PIN if user has one set
                        if user_prefs.activation_pin:
                            if not user_prefs.validate_pin(selected_teams):
                                messages.error(request, 'Invalid PIN. Please select the correct NBA teams.')
                                return redirect('predictions:home')
                        
                        set_active_user(request, target_user)
                        messages.success(request, 'Active user selected successfully.')
                    except User.DoesNotExist:
                        messages.error(request, 'User not found.')
                else:
                    # For other actions, just set the user (this handles the case where PIN was already validated)
                    User = get_user_model()
                    try:
                        target_user = User.objects.get(pk=user_id)
                        set_active_user(request, target_user)
                        messages.success(request, 'Active user selected successfully.')
                    except User.DoesNotExist:
                        messages.error(request, 'User not found.')
            else:
                clear_active_user(request)
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
                            # Team choice is already an Option
                            selected_option = selected_team
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
                            prediction_label = selected_player.name
                            # Player choice is already an Option
                            selected_option = selected_player
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

    all_users = list(get_user_model().objects.select_related('preferences').order_by('username'))
    
    # Get active season (if any) - needed for scoreboard filtering
    active_season = Season.get_active_season()
    
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
        
        # Filter by active season if one exists
        if active_season:
            score_queryset = score_queryset.filter(
                awarded_at__date__gte=active_season.start_date,
                awarded_at__date__lte=active_season.end_date
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

    # Fetch leaderboard data for dashboard
    # (active_season already retrieved above for scoreboard_summary)
    User = get_user_model()
    bonus_event_points_expr = Case(
        When(
            usereventscore__prediction_event__is_bonus_event=True,
            then=F('usereventscore__base_points'),
        ),
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

    # Build base queryset for leaderboard
    leaderboard_score_filter = Q(usereventscore__isnull=False)
    
    # If active season exists, filter scores by season timeframe
    if active_season:
        leaderboard_score_filter &= Q(
            usereventscore__awarded_at__date__gte=active_season.start_date,
            usereventscore__awarded_at__date__lte=active_season.end_date
        )

    leaderboard_users = User.objects.filter(leaderboard_score_filter).annotate(
        total_points=Coalesce(Sum('usereventscore__points_awarded'), 0),
        event_count=Coalesce(Count('usereventscore__prediction_event', distinct=True), 0),
    ).order_by('-total_points', '-event_count', 'username')

    leaderboard_rows = list(leaderboard_users)
    leaderboard_user_ids = [row.id for row in leaderboard_rows]
    leaderboard_display_name_map = _build_display_name_map(leaderboard_user_ids)

    # Calculate 3-day score change for each user
    three_days_ago = now - timedelta(days=3)
    for index, row in enumerate(leaderboard_rows, start=1):
        row.display_name = leaderboard_display_name_map.get(row.id, row.username)
        row.total_points = int(row.total_points)
        row.event_count = int(row.event_count)
        row.rank = index
        
        # Calculate points awarded in the last 3 days
        points_filter = Q(user=row, awarded_at__gte=three_days_ago)
        if active_season:
            points_filter &= Q(
                awarded_at__date__gte=active_season.start_date,
                awarded_at__date__lte=active_season.end_date
            )
        points_last_3_days = UserEventScore.objects.filter(points_filter).aggregate(
            total=Coalesce(Sum('points_awarded'), 0)
        )['total']
        row.points_change_3d = int(points_last_3_days) if points_last_3_days else 0
        
        # Add lock summary for each user
        try:
            lock_service = LockService(row)
            row.lock_summary = lock_service.get_summary()
        except Exception:
            # If there's any issue getting lock data, default to all locks available
            from .lock_service import LockSummary
            row.lock_summary = LockSummary(total=3, available=3, active=0, pending=0, next_return_at=None)
    
    # Filter leaderboard rows based on requirements (max 6 users):
    # - If less than 6 users total: show all users
    # - If 6 or more users:
    #   - Always show 1st place
    #   - Show nearest 4 users around the active user
    #   - Examples:
    #     - User in 1st: Show 1st + 5 users after = 6 total
    #     - User in last: Show 1st + 4 before + active = 6 total
    #     - User in 3rd: Show places 1-6 = 6 total
    #     - User in 6th: Show 1st + 2 before + active + 2 after = 6 total
    #     - User in 21st: Show 1st + 2 before + active + 2 after = 6 total
    if len(leaderboard_rows) <= 6:
        # Less than or equal to 6 users, show all
        filtered_leaderboard = leaderboard_rows
        if active_user:
            # Mark active user if present
            for row in filtered_leaderboard:
                if row.id == active_user.id:
                    row.is_active_user = True
                    break
    elif active_user and leaderboard_rows:
        # More than 6 users, find active user's rank
        active_user_rank = None
        for idx, row in enumerate(leaderboard_rows, start=1):
            if row.id == active_user.id:
                active_user_rank = idx
                break
        
        if active_user_rank:
            total_users = len(leaderboard_rows)
            
            if active_user_rank == 1:
                # User is 1st: Show 1st + 5 users after = 6 total
                filtered_leaderboard = leaderboard_rows[:6]
                filtered_leaderboard[0].is_active_user = True
            elif active_user_rank == total_users:
                # User is last: Show 1st + 4 before + active = 6 total
                rank_1 = [leaderboard_rows[0]]
                # Show 4 users before active (positions active-4 to active-1)
                start_idx = active_user_rank - 4 - 1  # -1 because index is 0-based
                users_before = leaderboard_rows[start_idx:active_user_rank - 1]  # 4 users before active
                active_user_row = [leaderboard_rows[active_user_rank - 1]]
                active_user_row[0].is_active_user = True
                
                # Add divider if rank 1 is not adjacent to the users before section
                class DividerMarker:
                    def __init__(self):
                        self.is_divider = True
                filtered_leaderboard = rank_1 + [DividerMarker()] + users_before + active_user_row
            else:
                # User is in the middle: Show 1st + nearest 4 users around active (2 before + 2 after when possible)
                rank_1 = [leaderboard_rows[0]]
                
                # Try to show 2 before and 2 after (4 users around active)
                # Examples:
                # - User in 3rd: Show 1-6 (rank 1 + positions 2,3,4,5,6)
                # - User in 6th: Show 1st + 4,5,6,7,8 (2 before + active + 2 after)
                # - User in 21st: Show 1st + 19,20,21,22,23 (2 before + active + 2 after)
                
                # Start with ideal: 2 before + active + 2 after = 5 users (plus 1st = 6 total)
                users_before_count = 2
                users_after_count = 2
                
                # Check if active is in positions 2-5 (can show continuous 1-6)
                # Position 6+ should show with divider to match example: "User in 6th? Show 2 users before + 2 users after + 1st"
                if active_user_rank <= 5:
                    # Can show continuous range 1-6 for positions 2-5 (cleaner UX, no divider needed)
                    filtered_leaderboard = leaderboard_rows[:6]
                    for row in filtered_leaderboard:
                        if row.id == active_user.id:
                            row.is_active_user = True
                            break
                else:
                    # Active is position 7 or later - need divider
                    # Adjust if we're too close to the end
                    max_after = total_users - active_user_rank
                    if max_after < 2:
                        # Can't show 2 after, show more before
                        users_after_count = max_after
                        users_before_count = 4 - users_after_count
                    
                    # Adjust if we're too close to rank 1 (shouldn't happen since rank > 6)
                    if active_user_rank - users_before_count <= 1:
                        # Edge case: active is at position 2-5 but somehow got here
                        users_before_count = max(0, active_user_rank - 2)
                        users_after_count = 4 - users_before_count
                    
                    start_idx = active_user_rank - 1 - users_before_count
                    users_before = leaderboard_rows[start_idx:active_user_rank - 1]
                    
                    active_user_row = [leaderboard_rows[active_user_rank - 1]]
                    active_user_row[0].is_active_user = True
                    
                    end_idx = active_user_rank + users_after_count
                    users_after = leaderboard_rows[active_user_rank:end_idx]
                    
                    # Add divider since rank 1 is not adjacent
                    class DividerMarker:
                        def __init__(self):
                            self.is_divider = True
                    filtered_leaderboard = rank_1 + [DividerMarker()] + users_before + active_user_row + users_after
        else:
            # Active user not in leaderboard, show top 6
            filtered_leaderboard = leaderboard_rows[:6]
    else:
        # No active user, show top 6
        filtered_leaderboard = leaderboard_rows[:6]
    
    leaderboard_rows = filtered_leaderboard

    # Fetch recently resolved predictions (last 5)
    resolved_predictions = list(
        EventOutcome.objects.select_related(
            'prediction_event__tip_type',
            'winning_option__option',
            'winning_generic_option',
        )
        .prefetch_related('prediction_event__options__option')
        .order_by('-resolved_at')[:5]
    )

    # For each resolved prediction, get user tips if active user exists
    resolved_predictions_data = []
    if resolved_predictions:
        for outcome in resolved_predictions:
            outcome_data = {
                'outcome': outcome,
                'user_tip': None,
                'is_correct': False,
            }
            if active_user:
                try:
                    user_tip = UserTip.objects.get(
                        user=active_user,
                        prediction_event=outcome.prediction_event
                    )
                    outcome_data['user_tip'] = user_tip
                    # Check if the user's prediction was correct
                    if outcome.winning_option and user_tip.prediction_option:
                        outcome_data['is_correct'] = (user_tip.prediction_option.id == outcome.winning_option.id)
                    elif outcome.winning_generic_option and user_tip.selected_option:
                        outcome_data['is_correct'] = (user_tip.selected_option.id == outcome.winning_generic_option.id)
                except UserTip.DoesNotExist:
                    pass
            resolved_predictions_data.append(outcome_data)

    # Get open predictions with due dates in the upcoming week
    upcoming_range_start = timezone.localdate(now)
    upcoming_range_end = upcoming_range_start + timedelta(days=6)
    
    open_predictions = list(
        PredictionEvent.objects.filter(
            is_active=True,
            opens_at__lte=now,
            deadline__gte=now,
            deadline__date__gte=upcoming_range_start,
            deadline__date__lte=upcoming_range_end,
        )
        .exclude(outcome__isnull=False)  # Exclude events that have outcomes
        .select_related('scheduled_game', 'tip_type')
        .prefetch_related('options__option__category')
        .order_by('deadline', 'sort_order', 'name')
    )

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
        'leaderboard_rows': leaderboard_rows,
        'resolved_predictions': resolved_predictions_data,
        'open_predictions': open_predictions,
        'enable_user_selection': settings.ENABLE_USER_SELECTION,
        'active_season': active_season,
    }
    return render(request, 'predictions/home.html', context)


@require_http_methods(["POST"])
@csrf_exempt
def save_prediction(request):
    """Save a single prediction immediately via AJAX."""
    # Get the active user (works in both authentication modes)
    active_user = get_active_user(request)
    if not active_user:
        return JsonResponse({'error': 'No active user'}, status=400)
    
    try:
        data = json.loads(request.body)
        event_id = data.get('event_id')
        option_id = data.get('option_id')
        
        if not event_id or not option_id:
            return JsonResponse({'error': 'Missing event_id or option_id'}, status=400)
        
        # Get the event
        event = get_object_or_404(PredictionEvent, id=event_id)
        
        # Check if event is still open
        now = timezone.now()
        if event.deadline <= now:
            return JsonResponse({'error': 'Event deadline has passed'}, status=400)
        
        # Get the option
        option = get_object_or_404(PredictionOption, id=option_id, event=event)
        selected_option = option.option
        prediction_label = option.label
        
        # Create or update the tip
        tip, created = UserTip.objects.get_or_create(
            user=active_user,
            prediction_event=event,
            defaults={
                'tip_type': event.tip_type,
                'prediction': prediction_label,
                'prediction_option': option,
                'selected_option': selected_option,
            }
        )
        
        if not created:
            # Update existing tip
            tip.tip_type = event.tip_type
            tip.prediction = prediction_label
            tip.prediction_option = option
            tip.selected_option = selected_option
            tip.save()
        
        return JsonResponse({
            'success': True,
            'message': 'Prediction saved successfully',
            'created': created
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_http_methods(["POST"])
@csrf_exempt
def toggle_lock(request):
    """Toggle lock status for a prediction immediately via AJAX."""
    # Get the active user (works in both authentication modes)
    active_user = get_active_user(request)
    if not active_user:
        return JsonResponse({'error': 'Authentication required'}, status=401)
    
    try:
        data = json.loads(request.body)
        event_id = data.get('event_id')
        should_lock = data.get('should_lock', False)
        
        if not event_id:
            return JsonResponse({'error': 'Missing event_id'}, status=400)
        
        # Get the event
        event = get_object_or_404(PredictionEvent, id=event_id)
        
        # Check if event is still open
        now = timezone.now()
        if event.deadline <= now:
            return JsonResponse({'error': 'Event deadline has passed'}, status=400)
        
        # Get the tip - must exist first (user must have made a prediction)
        try:
            tip = UserTip.objects.get(user=active_user, prediction_event=event)
        except UserTip.DoesNotExist:
            return JsonResponse({
                'error': 'No prediction found. Please make a prediction first before locking.',
                'lock_summary': {
                    'available': 0,
                    'active': 0,
                    'total': 0
                }
            }, status=400)
        
        lock_service = LockService(active_user)
        lock_service.refresh()
        
        if should_lock:
            try:
                lock_service.ensure_locked(tip)
                return JsonResponse({
                    'success': True,
                    'message': 'Prediction locked successfully',
                    'is_locked': True,
                    'lock_summary': {
                        'available': lock_service.available,
                        'active': len(lock_service._active_ids),
                        'total': lock_service.total
                    }
                })
            except LockLimitError:
                return JsonResponse({
                    'error': 'No locks available',
                    'lock_summary': {
                        'available': lock_service.available,
                        'active': len(lock_service._active_ids),
                        'total': lock_service.total
                    }
                }, status=400)
        else:
            # Release lock
            if tip.is_locked:
                lock_service.release_lock(tip)
                return JsonResponse({
                    'success': True,
                    'message': 'Prediction unlocked successfully',
                    'is_locked': False,
                    'lock_summary': {
                        'available': lock_service.available,
                        'active': len(lock_service._active_ids),
                        'total': lock_service.total
                    }
                })
            else:
                return JsonResponse({
                    'success': True,
                    'message': 'Prediction was not locked',
                    'is_locked': False,
                    'lock_summary': {
                        'available': lock_service.available,
                        'active': len(lock_service._active_ids),
                        'total': lock_service.total
                    }
                })
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_http_methods(["GET"])
def get_lock_summary(request):
    """Get current lock summary for the active user."""
    # Get the active user (works in both authentication modes)
    active_user = get_active_user(request)
    if not active_user:
        return JsonResponse({'error': 'No active user'}, status=400)
    
    lock_service = LockService(active_user)
    summary = lock_service.refresh()
    
    return JsonResponse({
        'available': summary.available,
        'active': summary.active,
        'total': summary.total,
        'pending': summary.pending,
        'next_return_at': summary.next_return_at.isoformat() if summary.next_return_at else None
    })


