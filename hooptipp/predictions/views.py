from django.contrib import messages
from django.contrib.auth import get_user_model
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .models import ScheduledGame, TipType, UserTip
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
    tip_type, games = sync_weekly_games()
    active_user = _get_active_user(request)

    if request.method == 'POST':
        if 'set_active_user' in request.POST:
            user_id = request.POST.get('user_id')
            if user_id:
                request.session['active_user_id'] = int(user_id)
                messages.success(request, 'Aktiver Benutzer wurde gesetzt.')
            else:
                request.session.pop('active_user_id', None)
                messages.info(request, 'Kein aktiver Benutzer ausgewählt.')
            return redirect('predictions:home')

        if 'save_tips' in request.POST:
            if not active_user:
                messages.error(request, 'Bitte zuerst einen Benutzer aktivieren.')
                return redirect('predictions:home')

            if tip_type is None:
                messages.error(request, 'Es konnten keine Spiele geladen werden.')
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
                messages.success(request, 'Deine Tipps wurden gespeichert!')
            else:
                messages.info(request, 'Keine Tipps zum Speichern gefunden.')
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

    context = {
        'tip_type': tip_type,
        'games': games,
        'active_user': active_user,
        'users': all_users,
        'user_tips': user_tips,
        'now': timezone.now(),
    }
    return render(request, 'predictions/home.html', context)
