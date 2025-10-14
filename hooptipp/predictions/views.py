from collections import defaultdict
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .forms import UserPreferencesForm
from .lock_service import LockLimitError, LockService
from .models import (
    NbaPlayer,
    NbaTeam,
    PredictionEvent,
    TipType,
    UserPreferences,
    UserTip,
)
from .services import sync_weekly_games


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


@require_http_methods(["GET", "POST"])
def home(request):
    weekly_tip_type, weekly_events, week_start = sync_weekly_games()
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

    weekly_visible_events: list[PredictionEvent] = []
    if weekly_tip_type:
        for section in sections:
            if section['tip_type'].pk == weekly_tip_type.pk:
                weekly_visible_events = section['events']
                break
        if not weekly_visible_events:
            weekly_visible_events = [
                event
                for event in weekly_events
                if event.is_active
                and event.opens_at <= now
                and event.deadline >= now
            ]
            if weekly_visible_events:
                sections.insert(0, {
                    'tip_type': weekly_tip_type,
                    'events': weekly_visible_events,
                })
                for event in weekly_visible_events:
                    if event.id not in seen_event_ids:
                        visible_events.append(event)
                        seen_event_ids.add(event.id)

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
                    selected_team = existing_tip.selected_team
                    selected_player = existing_tip.selected_player
                    prediction_label = existing_tip.prediction
                else:
                    option = None
                    selected_team = None
                    selected_player = None
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
                        selected_team = option.team
                        selected_player = option.player
                        prediction_label = option.label
                    else:
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
                        else:
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

                tip = user_tips.get(event.id)
                if tip is None:
                    tip = UserTip(
                        user=active_user,
                        prediction_event=event,
                    )
                tip.tip_type = event.tip_type
                tip.scheduled_game = event.scheduled_game
                tip.prediction = prediction_label
                tip.prediction_option = option
                tip.selected_team = selected_team
                tip.selected_player = selected_player
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

    all_users = get_user_model().objects.order_by('username')
    lock_summary = None
    if active_user:
        lock_summary = LockService(active_user).refresh()

    event_tip_users: dict[int, list] = defaultdict(list)
    if visible_events:
        for tip in (
            UserTip.objects.filter(
                prediction_event__in=visible_events,
            )
            .select_related('user')
            .order_by('user__username')
        ):
            event_tip_users[tip.prediction_event_id].append(tip.user)

    if week_start is None and weekly_visible_events:
        week_start = min(
            timezone.localdate(event.scheduled_game.game_date)
            for event in weekly_visible_events
            if event.scheduled_game
        )

    weekday_slots = []
    if week_start:
        for offset in range(7):
            slot_date = week_start + timedelta(days=offset)
            day_games = [
                event
                for event in weekly_visible_events
                if event.scheduled_game
                and timezone.localdate(event.scheduled_game.game_date) == slot_date
            ]
            weekday_slots.append({'date': slot_date, 'games': day_games})

    if preferences_form is None and preferences is not None:
        preferences_form = UserPreferencesForm(instance=preferences)

    context = {
        'weekly_tip_type': weekly_tip_type,
        'weekly_events': weekly_visible_events,
        'active_user': active_user,
        'users': all_users,
        'user_tips': user_tips,
        'event_tip_users': event_tip_users,
        'now': now,
        'weekday_slots': weekday_slots,
        'week_start': week_start,
        'user_preferences': preferences,
        'preferences_form': preferences_form,
        'event_sections': sections,
        'team_choices': team_choices,
        'player_choices': player_choices,
        'lock_summary': lock_summary,
    }
    return render(request, 'predictions/home.html', context)
