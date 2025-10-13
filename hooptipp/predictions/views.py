from django.contrib import messages
from django.contrib.auth import get_user_model
from django.shortcuts import redirect, render
from datetime import timedelta

from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .forms import UserPreferencesForm
from .models import ScheduledGame, TipType, UserPreferences, UserTip
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
    tip_type, games, week_start = sync_weekly_games()
    active_user = _get_active_user(request)
    preferences = None
    preferences_form = None

    if active_user:
        preferences, _ = UserPreferences.objects.get_or_create(user=active_user)

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

            if tip_type is None:
                messages.error(request, 'No games are available right now.')
                return redirect('predictions:home')

            saved = 0
            for game in games:
                key = f'prediction_{game.id}'
                prediction = request.POST.get(key)
                if not prediction:
                    continue
                UserTip.objects.update_or_create(
                    user=active_user,
                    tip_type=tip_type,
                    scheduled_game=game,
                    defaults={'prediction': prediction},
                )
                saved += 1

            if saved:
                messages.success(request, 'Your picks have been saved!')
            else:
                messages.info(request, 'No picks were provided, nothing to save.')
            return redirect('predictions:home')

    all_users = get_user_model().objects.order_by('username')
    user_tips = {}
    if active_user and tip_type:
        user_tips = {
            tip.scheduled_game_id: tip
            for tip in UserTip.objects.filter(
                user=active_user,
                tip_type=tip_type,
                scheduled_game__in=games,
            )
        }

    game_tip_users = {}
    if tip_type:
        for tip in (
            UserTip.objects.filter(
                tip_type=tip_type,
                scheduled_game__in=games,
            )
            .select_related('user')
            .order_by('user__username')
        ):
            game_tip_users.setdefault(tip.scheduled_game_id, []).append(tip.user)

    if week_start is None and games:
        week_start = min(timezone.localdate(game.game_date) for game in games)

    weekday_slots = []
    if week_start:
        for offset in range(7):
            slot_date = week_start + timedelta(days=offset)
            day_games = [
                game
                for game in games
                if timezone.localdate(game.game_date) == slot_date
            ]
            weekday_slots.append({'date': slot_date, 'games': day_games})

    if preferences_form is None and preferences is not None:
        preferences_form = UserPreferencesForm(instance=preferences)

    context = {
        'tip_type': tip_type,
        'games': games,
        'active_user': active_user,
        'users': all_users,
        'user_tips': user_tips,
        'game_tip_users': game_tip_users,
        'now': timezone.now(),
        'weekday_slots': weekday_slots,
        'week_start': week_start,
        'user_preferences': preferences,
        'preferences_form': preferences_form,
    }
    return render(request, 'predictions/home.html', context)
