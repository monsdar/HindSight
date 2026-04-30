"""NBA admin customizations."""

import json
import logging
import threading
from datetime import datetime, timedelta, date
from typing import Any, Literal, Optional, Tuple

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponseNotAllowed, HttpResponseRedirect
from django.shortcuts import render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from hooptipp.predictions.lock_service import LockService
from hooptipp.predictions.models import (
    Option,
    OptionCategory,
    PredictionEvent,
    PredictionOption,
    TipType,
    UserEventScore,
    UserTip,
)

from .models import NbaUserPreferences, ScheduledGame
from .services import sync_players, sync_players_from_hoopshype, sync_teams, _build_bdl_client

logger = logging.getLogger(__name__)

# Note: ScheduledGame admin is in predictions.admin for now
# It will be moved here when we fully migrate ScheduledGame to the nba app


@admin.register(NbaUserPreferences)
class NbaUserPreferencesAdmin(admin.ModelAdmin):
    """Admin for NBA user preferences."""

    list_display = (
        "user",
        "favorite_team_display",
        "favorite_player_display",
        "notifications_enabled",
        "favorite_conference",
    )
    search_fields = ("user__username",)
    autocomplete_fields = ("user",)

    fieldsets = (
        (
            "User",
            {
                "fields": ("user",)
            },
        ),
        (
            "Favorites",
            {
                "description": (
                    "Favorites are managed via User Favorites in the Predictions app. "
                    "Go to Predictions > User Favorites to edit team and player favorites."
                ),
                "fields": ("favorite_team_display", "favorite_player_display"),
            },
        ),
        (
            "Preferences",
            {
                "fields": (
                    "notifications_enabled",
                    "favorite_conference",
                    "show_player_stats",
                )
            },
        ),
    )

    readonly_fields = ("favorite_team_display", "favorite_player_display")

    def favorite_team_display(self, obj):
        team = obj.get_favorite_team()
        if team:
            return format_html(
                '<strong>{}</strong> <a href="{}">Edit favorites</a>',
                team.name,
                reverse("admin:predictions_userfavorite_changelist")
                + f"?user__id__exact={obj.user.id}",
            )
        return format_html(
            '<em>None set</em> <a href="{}">Set favorite</a>',
            reverse("admin:predictions_userfavorite_add")
            + f"?user={obj.user.id}&favorite_type=nba-team",
        )

    favorite_team_display.short_description = "Favorite Team"

    def favorite_player_display(self, obj):
        player = obj.get_favorite_player()
        if player:
            return format_html(
                '<strong>{}</strong> <a href="{}">Edit favorites</a>',
                player.name,
                reverse("admin:predictions_userfavorite_changelist")
                + f"?user__id__exact={obj.user.id}",
            )
        return format_html(
            '<em>None set</em> <a href="{}">Set favorite</a>',
            reverse("admin:predictions_userfavorite_add")
            + f"?user={obj.user.id}&favorite_type=nba-player",
        )

    favorite_player_display.short_description = "Favorite Player"


# Note: NBA teams and players sync is available through the Event Sources
# admin in the predictions app. Teams and players can be viewed directly
# as Options in the predictions admin.

NBA_BALLDONTLIE_SOURCE_ID = 'nba-balldontlie'


def _is_postponed_or_cancelled_status(status_raw: Optional[str]) -> bool:
    if not status_raw or not isinstance(status_raw, str):
        return False
    s = status_raw.strip().lower()
    # ISO datetimes describe schedule time, not postpone/cancel
    if len(s) > 14 and ('t' in s or 'z' in s) and any(c.isdigit() for c in s[:4]):
        return False
    return 'postpon' in s or 'cancel' in s


def _parse_balldontlie_row(game: Any) -> Optional[dict]:
    """Build a canonical game payload or None if the row should be skipped."""
    if isinstance(game, dict):
        raw_status_field = game.get('status')
        datetime_str = game.get('datetime', '') or ''
        if datetime_str == '' and raw_status_field and isinstance(raw_status_field, str):
            datetime_str = raw_status_field
        if isinstance(raw_status_field, str) and _is_postponed_or_cancelled_status(raw_status_field):
            return None
        home_team = game.get('home_team', None)
        away_team = game.get('visitor_team', None)
        game_id = str(game.get('id', ''))
    else:
        raw_status_field = getattr(game, 'status', '')
        # New API sometimes stores game time under status when it is ISO-shaped
        datetime_str = getattr(game, 'datetime', '') or raw_status_field
        legacy_status_attr = getattr(game, 'time', '') or getattr(
            game,
            'status_text',
            '',
        )
        if isinstance(raw_status_field, str) and _is_postponed_or_cancelled_status(raw_status_field):
            return None
        if legacy_status_attr and _is_postponed_or_cancelled_status(str(legacy_status_attr)):
            return None
        home_team = getattr(game, 'home_team', None)
        away_team = getattr(game, 'visitor_team', None)
        game_id = str(getattr(game, 'id', ''))

    status_for_final = ''
    if isinstance(raw_status_field, str):
        status_for_final = raw_status_field
    status_lower = (status_for_final or '').lower()
    if 'final' in status_lower or 'end' in status_lower:
        return None
    if status_for_final and not any(char.isdigit() for char in status_for_final) and any(
        keyword in status_lower for keyword in ['final', 'end', 'complete', 'finished']
    ):
        return None

    if not datetime_str:
        return None

    try:
        game_time = datetime.fromisoformat(str(datetime_str).replace('Z', '+00:00'))
        if timezone.is_naive(game_time):
            game_time = timezone.make_aware(game_time)
    except ValueError:
        return None

    if game_time < timezone.now():
        return None

    if isinstance(game, dict):
        home_team_dict = {
            'id': home_team.get('id', None) if home_team else None,
            'full_name': home_team.get('full_name', '') if home_team else '',
            'name': home_team.get('name', '') if home_team else '',
            'abbreviation': home_team.get('abbreviation', '') if home_team else '',
            'city': home_team.get('city', '') if home_team else '',
            'conference': home_team.get('conference', '') if home_team else '',
            'division': home_team.get('division', '') if home_team else '',
        }
        away_team_dict = {
            'id': away_team.get('id', None) if away_team else None,
            'full_name': away_team.get('full_name', '') if away_team else '',
            'name': away_team.get('name', '') if away_team else '',
            'abbreviation': away_team.get('abbreviation', '') if away_team else '',
            'city': away_team.get('city', '') if away_team else '',
            'conference': away_team.get('conference', '') if away_team else '',
            'division': away_team.get('division', '') if away_team else '',
        }
        arena = game.get('arena', '') or ''
    else:
        home_team_dict = {
            'id': getattr(home_team, 'id', None) if home_team else None,
            'full_name': getattr(home_team, 'full_name', '') if home_team else '',
            'name': getattr(home_team, 'name', '') if home_team else '',
            'abbreviation': getattr(home_team, 'abbreviation', '') if home_team else '',
            'city': getattr(home_team, 'city', '') if home_team else '',
            'conference': getattr(home_team, 'conference', '') if home_team else '',
            'division': getattr(home_team, 'division', '') if home_team else '',
        }
        away_team_dict = {
            'id': getattr(away_team, 'id', None) if away_team else None,
            'full_name': getattr(away_team, 'full_name', '') if away_team else '',
            'name': getattr(away_team, 'name', '') if away_team else '',
            'abbreviation': getattr(away_team, 'abbreviation', '') if away_team else '',
            'city': getattr(away_team, 'city', '') if away_team else '',
            'conference': getattr(away_team, 'conference', '') if away_team else '',
            'division': getattr(away_team, 'division', '') if away_team else '',
        }
        arena = getattr(game, 'arena', '') or ''

    return {
        'game_id': game_id,
        'game_time': game_time,
        'home_team': home_team_dict,
        'away_team': away_team_dict,
        'arena': arena,
    }


def _balldontlie_upcoming_rows_from_response(response: Any) -> Tuple[list[dict], set[str]]:
    rows = []
    ids: set[str] = set()
    for game in response.data:
        parsed = _parse_balldontlie_row(game)
        if parsed is None:
            continue
        rows.append(parsed)
        ids.add(parsed['game_id'])
    return rows, ids


def _fetch_balldontlie_upcoming(
    client: Any,
    start_date: date,
    end_date: date,
) -> Tuple[list[dict], set[str]]:
    response = client.nba.games.list(
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        per_page=100,
    )
    return _balldontlie_upcoming_rows_from_response(response)


def _serialize_game_payload_for_form(row: dict) -> str:
    game_dict = {
        'game_id': row['game_id'],
        'game_time': row['game_time'].isoformat(),
        'home_team': row['home_team'],
        'away_team': row['away_team'],
        'arena': row['arena'],
    }
    return json.dumps(game_dict)


def _opens_at_from_game_time(game_time: datetime) -> datetime:
    opens_at = game_time - timedelta(days=7)
    return max(opens_at, timezone.now())


def _ensure_nba_prediction_options(event: PredictionEvent, home_team_data: dict, away_team_data: dict) -> None:
    teams_cat = OptionCategory.objects.get(slug='nba-teams')
    away_abbr = away_team_data.get('abbreviation', '')
    home_abbr = home_team_data.get('abbreviation', '')

    home_option = Option.objects.filter(category=teams_cat, short_name=home_abbr).first()
    away_option = Option.objects.filter(category=teams_cat, short_name=away_abbr).first()

    prediction_options = list(
        PredictionOption.objects.filter(event=event).select_related('option').order_by('sort_order')
    )

    def _current_matches() -> bool:
        if len(prediction_options) != 2 or not away_option or not home_option:
            return False
        first, second = prediction_options[0], prediction_options[1]
        return (
            first.sort_order == 1
            and second.sort_order == 2
            and first.option_id == away_option.id
            and second.option_id == home_option.id
        )

    if _current_matches():
        return

    PredictionOption.objects.filter(event=event).delete()

    if away_option:
        PredictionOption.objects.create(
            event=event,
            option=away_option,
            label=away_option.name,
            sort_order=1,
            is_active=True,
        )

    if home_option:
        PredictionOption.objects.create(
            event=event,
            option=home_option,
            label=home_option.name,
            sort_order=2,
            is_active=True,
        )


def _sync_nba_balldontlie_event(
    game_id: str,
    game_data: dict,
    tip_type: TipType,
) -> Literal['created', 'updated']:
    game_time_str = game_data.get('game_time')
    if not isinstance(game_time_str, str):
        raise ValueError('game_time missing')
    raw = game_time_str.replace('Z', '+00:00')
    try:
        game_time = datetime.fromisoformat(raw)
    except ValueError as e:
        raise ValueError('invalid game_time') from e
    if timezone.is_naive(game_time):
        game_time = timezone.make_aware(game_time)

    home_team_data = game_data.get('home_team', {})
    away_team_data = game_data.get('away_team', {})

    scheduled_game, _ = ScheduledGame.objects.update_or_create(
        nba_game_id=game_id,
        defaults={
            'tip_type': tip_type,
            'game_date': game_time,
            'home_team': home_team_data.get('full_name') or home_team_data.get('name', ''),
            'home_team_tricode': home_team_data.get('abbreviation', ''),
            'away_team': away_team_data.get('full_name') or away_team_data.get('name', ''),
            'away_team_tricode': away_team_data.get('abbreviation', ''),
            'venue': game_data.get('arena', ''),
            'is_manual': False,
        },
    )

    opens_at = _opens_at_from_game_time(game_time)
    metadata = {
        'arena': game_data.get('arena', ''),
        'home_team_data': home_team_data,
        'away_team_data': away_team_data,
    }

    existing = PredictionEvent.objects.filter(
        source_id=NBA_BALLDONTLIE_SOURCE_ID,
        source_event_id=game_id,
    ).first()

    if existing:
        PredictionEvent.objects.filter(pk=existing.pk).update(
            scheduled_game_id=scheduled_game.id,
            tip_type_id=tip_type.id,
            name=f"{away_team_data.get('abbreviation', '')} @ {home_team_data.get('abbreviation', '')}",
            description=f"{away_team_data.get('full_name', '')} at {home_team_data.get('full_name', '')}",
            opens_at=opens_at,
            deadline=game_time,
            reveal_at=opens_at,
            metadata=metadata,
            points=tip_type.default_points,
        )
        existing.refresh_from_db()
        _ensure_nba_prediction_options(existing, home_team_data, away_team_data)
        return 'updated'

    event = PredictionEvent.objects.create(
        scheduled_game=scheduled_game,
        tip_type=tip_type,
        name=f"{away_team_data.get('abbreviation', '')} @ {home_team_data.get('abbreviation', '')}",
        description=f"{away_team_data.get('full_name', '')} at {home_team_data.get('full_name', '')}",
        target_kind=PredictionEvent.TargetKind.TEAM,
        selection_mode=PredictionEvent.SelectionMode.CURATED,
        source_id=NBA_BALLDONTLIE_SOURCE_ID,
        source_event_id=game_id,
        metadata=metadata,
        opens_at=opens_at,
        deadline=game_time,
        reveal_at=opens_at,
        is_active=True,
        points=tip_type.default_points,
    )

    teams_cat = OptionCategory.objects.get(slug='nba-teams')
    home_option = Option.objects.filter(
        category=teams_cat,
        short_name=home_team_data.get('abbreviation', ''),
    ).first()
    away_option = Option.objects.filter(
        category=teams_cat,
        short_name=away_team_data.get('abbreviation', ''),
    ).first()
    if away_option:
        PredictionOption.objects.create(
            event=event,
            option=away_option,
            label=away_option.name,
            sort_order=1,
            is_active=True,
        )
    if home_option:
        PredictionOption.objects.create(
            event=event,
            option=home_option,
            label=home_option.name,
            sort_order=2,
            is_active=True,
        )
    return 'created'


def _return_active_locks_for_event(event: PredictionEvent) -> None:
    tips_with_locks = UserTip.objects.filter(
        prediction_event=event,
        lock_status=UserTip.LockStatus.ACTIVE,
    ).select_related('user')
    for tip in tips_with_locks:
        try:
            lock_service = LockService(tip.user)
            lock_service.return_lock_for_forfeited_event(tip)
        except Exception as e:
            logger.warning(f'Failed to return lock before removing NBA event {event.name}: {e}')


def add_upcoming_nba_games_view(request: HttpRequest):
    """Fetch upcoming NBA games from BallDontLie and display for selection."""
    gate_perms = (
        'predictions.add_predictionevent',
        'predictions.change_predictionevent',
        'predictions.delete_predictionevent',
    )
    if not any(request.user.has_perm(p) for p in gate_perms):
        raise PermissionDenied

    from balldontlie.exceptions import BallDontLieException

    client = _build_bdl_client()
    if client is None:
        messages.error(request, 'BallDontLie API is not configured. Please set BALLDONTLIE_API_TOKEN.')
        return HttpResponseRedirect(reverse('admin:index'))

    today = timezone.localdate()
    start_date = today
    end_date = today + timedelta(days=60)

    try:
        rows, fetched_ids = _fetch_balldontlie_upcoming(client, start_date, end_date)
    except BallDontLieException as e:
        messages.error(request, f'Unable to fetch games from BallDontLie API: {str(e)}')
        return HttpResponseRedirect(reverse('admin:index'))

    games = []
    for row in rows:
        game_id = row['game_id']
        existing_event = PredictionEvent.objects.filter(
            source_id=NBA_BALLDONTLIE_SOURCE_ID,
            source_event_id=game_id,
        ).first()
        json_data = _serialize_game_payload_for_form(row)
        games.append({
            'game_id': game_id,
            'game_time': row['game_time'],
            'home_team': row['home_team'],
            'away_team': row['away_team'],
            'arena': row['arena'],
            'already_exists': existing_event is not None,
            'existing_event_id': existing_event.id if existing_event else None,
            'json_data': json_data,
        })

    games.sort(key=lambda g: g['game_time'])

    current_date = None
    date_group_index = 0
    for game in games:
        game_date = game['game_time'].date()
        if current_date != game_date:
            current_date = game_date
            date_group_index = (date_group_index + 1) % 2
        game['date_group'] = date_group_index
        game['game_date'] = game_date

    now = timezone.now()

    orphans = (
        PredictionEvent.objects.select_related('scheduled_game')
        .filter(
            source_id=NBA_BALLDONTLIE_SOURCE_ID,
            scheduled_game__isnull=False,
            scheduled_game__is_manual=False,
            deadline__gte=now,
            deadline__date__gte=start_date,
            deadline__date__lte=end_date,
        )
        .exclude(source_event_id__in=fetched_ids)
        .order_by('deadline')
    )

    orphan_events = [
        {
            'event_id': oe.id,
            'name': oe.name,
            'deadline': oe.deadline,
            'source_event_id': oe.source_event_id,
        }
        for oe in orphans
    ]

    if not games and not orphan_events:
        messages.info(request, 'No upcoming games found.')
        return HttpResponseRedirect(reverse('admin:index'))

    context = {
        'title': 'Add Upcoming NBA Games',
        'games': games,
        'games_count': len(games),
        'orphan_events': orphan_events,
        'orphans_count': len(orphan_events),
        'can_remove_orphans': request.user.has_perm('predictions.delete_predictionevent'),
        'app_label': 'nba',
        'has_permission': True,
    }

    return render(request, 'admin/nba/add_upcoming_games.html', context)


def create_nba_events_view(request: HttpRequest):
    """Create or update PredictionEvents from selected NBA games; optionally remove orphans."""
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    gate_perms = (
        'predictions.add_predictionevent',
        'predictions.change_predictionevent',
        'predictions.delete_predictionevent',
    )
    if not any(request.user.has_perm(p) for p in gate_perms):
        raise PermissionDenied

    from balldontlie.exceptions import BallDontLieException

    selected_game_ids = request.POST.getlist('selected_games')
    remove_raw = request.POST.getlist('remove_event_ids')

    if not selected_game_ids and not remove_raw:
        messages.warning(request, 'No games or removals were selected.')
        return HttpResponseRedirect(reverse('admin:nba_add_upcoming_games'))

    client = _build_bdl_client()
    if client is None:
        messages.error(request, 'BallDontLie API is not configured. Please set BALLDONTLIE_API_TOKEN.')
        return HttpResponseRedirect(reverse('admin:nba_add_upcoming_games'))

    today = timezone.localdate()
    start_date = today
    end_date = today + timedelta(days=60)

    try:
        _, fetched_ids = _fetch_balldontlie_upcoming(client, start_date, end_date)
    except BallDontLieException as e:
        messages.error(request, f'Unable to verify games with BallDontLie API: {str(e)}')
        return HttpResponseRedirect(reverse('admin:nba_add_upcoming_games'))

    tip_type, _ = TipType.objects.get_or_create(
        slug='weekly-games',
        defaults={
            'name': 'Weekly games',
            'description': 'Featured NBA matchups',
            'category': TipType.TipCategory.GAME,
            'deadline': timezone.now() + timedelta(days=7),
            'is_active': True,
        },
    )

    created_count = 0
    updated_count = 0
    skipped_existing_perm = 0
    malformed_rows = 0

    for game_id in selected_game_ids:
        game_data_json = request.POST.get(f'game_data_{game_id}')
        if not game_data_json:
            malformed_rows += 1
            continue
        try:
            game_data = json.loads(game_data_json)
        except json.JSONDecodeError:
            malformed_rows += 1
            continue

        existing_event = PredictionEvent.objects.filter(
            source_id=NBA_BALLDONTLIE_SOURCE_ID,
            source_event_id=game_id,
        ).first()

        needs_add = existing_event is None
        needs_change = existing_event is not None

        if needs_add and not request.user.has_perm('predictions.add_predictionevent'):
            skipped_existing_perm += 1
            continue
        if needs_change and not request.user.has_perm('predictions.change_predictionevent'):
            skipped_existing_perm += 1
            continue

        try:
            result = _sync_nba_balldontlie_event(game_id, game_data, tip_type)
        except ValueError:
            malformed_rows += 1
            continue

        if result == 'created':
            created_count += 1
        else:
            updated_count += 1

    deleted_count = 0
    skipped_scored_removal = 0
    skipped_invalid_removal = 0

    if remove_raw and request.user.has_perm('predictions.delete_predictionevent'):
        now = timezone.now()
        raw_ids_parsed = []
        for sid in remove_raw:
            try:
                raw_ids_parsed.append(int(sid))
            except (TypeError, ValueError):
                skipped_invalid_removal += 1
        pk_list = sorted(set(raw_ids_parsed))

        for event_id in pk_list:
            try:
                event = PredictionEvent.objects.select_related('scheduled_game').get(pk=event_id)
            except PredictionEvent.DoesNotExist:
                skipped_invalid_removal += 1
                continue

            if event.source_id != NBA_BALLDONTLIE_SOURCE_ID:
                skipped_invalid_removal += 1
                continue

            sg = event.scheduled_game
            if sg is None or sg.is_manual:
                skipped_invalid_removal += 1
                continue

            ext_id = event.source_event_id or sg.nba_game_id
            if ext_id and ext_id in fetched_ids:
                skipped_invalid_removal += 1
                continue

            if event.deadline < now:
                skipped_invalid_removal += 1
                continue

            gd = timezone.localtime(event.deadline).date()
            if gd < start_date or gd > end_date:
                skipped_invalid_removal += 1
                continue

            outcome = getattr(event, 'outcome', None)
            if outcome is not None and outcome.scored_at is not None:
                skipped_scored_removal += 1
                continue

            if UserEventScore.objects.filter(prediction_event=event).exists():
                skipped_scored_removal += 1
                continue

            _return_active_locks_for_event(event)
            sg.delete()
            deleted_count += 1

    parts = []
    if created_count:
        parts.append(f'created {created_count}')
    if updated_count:
        parts.append(f'updated {updated_count}')
    if deleted_count:
        parts.append(f'removed {deleted_count}')
    if parts:
        messages.success(request, 'NBA prediction events from BallDontLie: ' + ', '.join(parts) + '.')

    if skipped_existing_perm:
        messages.warning(
            request,
            f'Skipped {skipped_existing_perm} game(s): missing add or change permission for that action.',
        )
    if malformed_rows:
        messages.warning(request, f'Skipped {malformed_rows} row(s): missing or invalid game payload.')
    if skipped_scored_removal:
        messages.warning(
            request,
            f'Skipped removing {skipped_scored_removal} event(s): already scored or scored users exist.',
        )
    if skipped_invalid_removal:
        messages.warning(
            request,
            f'Skipped {skipped_invalid_removal} removal(s): invalid target, deadline outside '
            'the sync window, or game still returned as upcoming on BallDontLie.',
        )

    if remove_raw and not request.user.has_perm('predictions.delete_predictionevent'):
        messages.warning(
            request,
            'Removing orphan events requires the delete_predictionevent permission.',
        )

    skipped_any = bool(
        skipped_existing_perm or malformed_rows or skipped_scored_removal or skipped_invalid_removal
    )
    removal_denied_bad_perm = bool(remove_raw) and (
        not request.user.has_perm('predictions.delete_predictionevent')
    )
    if (
        created_count == 0
        and updated_count == 0
        and deleted_count == 0
        and not skipped_any
        and not removal_denied_bad_perm
        and bool(selected_game_ids or remove_raw)
    ):
        messages.info(request, 'No prediction events were created, updated, or removed.')

    return HttpResponseRedirect(reverse('admin:predictions_predictionevent_changelist'))


def nba_sync_view(request: HttpRequest):
    """Display the NBA sync page with buttons to sync teams and players."""
    if not request.user.has_perm('predictions.add_option'):
        raise PermissionDenied
    
    context = {
        'title': 'NBA Data Synchronization',
        'app_label': 'nba',
        'has_permission': True,
    }
    
    return render(request, 'admin/nba/sync.html', context)


def sync_teams_view(request: HttpRequest):
    """Sync NBA teams from BallDontLie API."""
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    
    if not request.user.has_perm('predictions.add_option'):
        raise PermissionDenied
    
    try:
        result = sync_teams()
        
        if not result.changed:
            messages.info(request, 'Teams sync completed with no changes.')
        else:
            message_parts = []
            if result.created:
                message_parts.append(f'{result.created} team(s) created')
            if result.updated:
                message_parts.append(f'{result.updated} team(s) updated')
            if result.removed:
                message_parts.append(f'{result.removed} team(s) removed')
            
            messages.success(
                request,
                f'Teams synced successfully: {", ".join(message_parts)}.'
            )
    except Exception as e:
        messages.error(request, f'Failed to sync teams: {str(e)}')
    
    return HttpResponseRedirect(reverse('admin:nba_sync'))


def _run_player_sync_background():
    """
    Background worker function for player sync.
    
    Runs the HoopsHype sync and logs results. This function is executed in a separate thread
    to avoid blocking the admin request.
    """
    try:
        logger.info('Starting background HoopsHype player sync...')
        result = sync_players_from_hoopshype()
        
        if not result.changed:
            logger.info('HoopsHype player sync completed with no changes.')
        else:
            message_parts = []
            if result.created:
                message_parts.append(f'{result.created} player(s) created')
            if result.updated:
                message_parts.append(f'{result.updated} player(s) updated')
            if result.removed:
                message_parts.append(f'{result.removed} player(s) removed')
            
            logger.info(f'HoopsHype player sync completed successfully: {", ".join(message_parts)}.')
    except Exception as e:
        logger.exception(f'Background HoopsHype player sync failed: {str(e)}')


def sync_players_view(request: HttpRequest):
    """Sync NBA players from HoopsHype in the background."""
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    
    if not request.user.has_perm('predictions.add_option'):
        raise PermissionDenied
    
    # Start the sync in a background thread
    sync_thread = threading.Thread(
        target=_run_player_sync_background,
        daemon=True,
        name='nba-player-sync'
    )
    sync_thread.start()
    
    messages.info(
        request,
        'HoopsHype player sync started in the background. This will take about 30 seconds to complete. '
        'Check the server logs for completion status. You can continue working normally.'
    )
    
    return HttpResponseRedirect(reverse('admin:nba_sync'))


# Register custom admin URLs for NBA games management
# These are registered as part of the NbaUserPreferencesAdmin get_urls
class CustomNbaAdmin:
    """Container for custom NBA admin URLs."""
    
    @staticmethod
    def get_urls():
        """Get custom NBA admin URLs."""
        return [
            path(
                'sync/',
                admin.site.admin_view(nba_sync_view),
                name='nba_sync',
            ),
            path(
                'sync/teams/',
                admin.site.admin_view(sync_teams_view),
                name='nba_sync_teams',
            ),
            path(
                'sync/players/',
                admin.site.admin_view(sync_players_view),
                name='nba_sync_players',
            ),
            path(
                'games/add-upcoming/',
                admin.site.admin_view(add_upcoming_nba_games_view),
                name='nba_add_upcoming_games',
            ),
            path(
                'games/create-events/',
                admin.site.admin_view(create_nba_events_view),
                name='nba_create_events',
            ),
        ]


# Hook into admin site URLs
from django.contrib.admin import sites

# Save the original get_urls method
_original_get_urls = sites.AdminSite.get_urls

def _get_urls_with_nba(self):
    """Get admin URLs including NBA custom views."""
    urls = _original_get_urls(self)
    nba_urls = CustomNbaAdmin.get_urls()
    return nba_urls + urls

# Monkey patch the admin site's get_urls method
# Mark it so other apps (like demo) know it's been patched
_get_urls_with_nba._nba_patched = True
sites.AdminSite.get_urls = _get_urls_with_nba
