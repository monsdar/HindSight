"""NBA admin customizations."""

import json
import logging
import threading
from datetime import datetime, timedelta

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponseNotAllowed, HttpResponseRedirect
from django.shortcuts import render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from hooptipp.predictions.models import (
    Option,
    OptionCategory,
    PredictionEvent,
    PredictionOption,
    TipType,
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


def add_upcoming_nba_games_view(request: HttpRequest):
    """Fetch upcoming NBA games from BallDontLie and display for selection."""
    if not request.user.has_perm('predictions.add_predictionevent'):
        raise PermissionDenied
    
    from balldontlie.exceptions import BallDontLieException
    
    client = _build_bdl_client()
    if client is None:
        messages.error(request, 'BallDontLie API is not configured. Please set BALLDONTLIE_API_TOKEN.')
        return HttpResponseRedirect(reverse('admin:index'))
    
    # Fetch next 100 upcoming games (1 API call)
    today = timezone.localdate()
    start_date = today
    # Look ahead 60 days to ensure we get 100 games even in off-season
    end_date = today + timedelta(days=60)
    
    try:
        response = client.nba.games.list(
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            per_page=100,
            postseason='false',
        )
    except BallDontLieException as e:
        messages.error(request, f'Unable to fetch games from BallDontLie API: {str(e)}')
        return HttpResponseRedirect(reverse('admin:index'))
    
    # Process games
    games = []
    for game in response.data:
        # Handle both dict and object responses
        if isinstance(game, dict):
            status = game.get('status', '')
            datetime_str = game.get('datetime', '')
            home_team = game.get('home_team', None)
            away_team = game.get('visitor_team', None)
            game_id = str(game.get('id', ''))
        else:
            # Handle NBAGame objects from BallDontLie API
            # The status field contains the datetime string in the new API format
            status = getattr(game, 'status', '')
            datetime_str = status  # Use status as datetime since it contains the datetime string
            home_team = getattr(game, 'home_team', None)
            away_team = getattr(game, 'visitor_team', None)
            game_id = str(getattr(game, 'id', ''))
        
        # Check if game is final - the status field now contains datetime strings
        # for scheduled games, so we need to check if it's a valid datetime
        # If it's not a datetime, it might be a status like "Final"
        status_lower = (status or '').lower()
        if 'final' in status_lower or 'end' in status_lower:
            continue
        
        # Additional check: if the status is a datetime string, it's likely a scheduled game
        # If it's not a datetime and contains game status keywords, it might be finished
        if status and not any(char.isdigit() for char in status) and any(
            keyword in status_lower for keyword in ['final', 'end', 'complete', 'finished']
        ):
            continue
        
        if not datetime_str:
            continue
        
        try:
            game_time = datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
            if timezone.is_naive(game_time):
                game_time = timezone.make_aware(game_time)
        except ValueError:
            continue
        
        # Skip games that have already started
        if game_time < timezone.now():
            continue
        
        # Check if this game already exists as a PredictionEvent
        existing_event = PredictionEvent.objects.filter(
            source_id='nba-balldontlie',
            source_event_id=game_id
        ).first()
        
        # Handle team data access for both dict and object responses
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
            # Handle NBAGame objects from BallDontLie API
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
        
        game_dict = {
            'game_id': game_id,
            'game_time': game_time.isoformat(),
            'home_team': home_team_dict,
            'away_team': away_team_dict,
            'arena': arena,
        }
        
        # Serialize to JSON for hidden form field
        json_data = json.dumps(game_dict)
        
        games.append({
            'game_id': game_id,
            'game_time': game_time,
            'home_team': home_team_dict,
            'away_team': away_team_dict,
            'arena': arena,
            'already_exists': existing_event is not None,
            'existing_event_id': existing_event.id if existing_event else None,
            'json_data': json_data,
        })
    
    if not games:
        messages.info(request, 'No upcoming games found.')
        return HttpResponseRedirect(reverse('admin:index'))
    
    # Sort by game time
    games.sort(key=lambda g: g['game_time'])
    
    # Add date grouping information for CSS styling
    current_date = None
    date_group_index = 0
    for game in games:
        game_date = game['game_time'].date()
        if current_date != game_date:
            current_date = game_date
            date_group_index = (date_group_index + 1) % 2  # Alternate between 0 and 1
        game['date_group'] = date_group_index
        game['game_date'] = game_date
    
    context = {
        'title': 'Add Upcoming NBA Games',
        'games': games,
        'games_count': len(games),
        'app_label': 'nba',
        'has_permission': True,
    }
    
    return render(request, 'admin/nba/add_upcoming_games.html', context)


def create_nba_events_view(request: HttpRequest):
    """Create PredictionEvents from selected NBA games."""
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    
    if not request.user.has_perm('predictions.add_predictionevent'):
        raise PermissionDenied
    
    # Get selected game IDs
    selected_game_ids = request.POST.getlist('selected_games')
    
    if not selected_game_ids:
        messages.warning(request, 'No games were selected.')
        return HttpResponseRedirect(reverse('admin:nba_add_upcoming_games'))
    
    # Get or create the tip type
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
    skipped_count = 0
    
    # Process each selected game
    for game_id in selected_game_ids:
        # Get game data from hidden input (stored as JSON)
        game_data_json = request.POST.get(f'game_data_{game_id}')
        if not game_data_json:
            continue
        
        try:
            game_data = json.loads(game_data_json)
        except json.JSONDecodeError:
            continue
        
        # Check if event already exists
        existing_event = PredictionEvent.objects.filter(
            source_id='nba-balldontlie',
            source_event_id=game_id
        ).first()
        
        if existing_event:
            skipped_count += 1
            continue
        
        # Parse game time
        game_time_str = game_data.get('game_time')
        try:
            game_time = datetime.fromisoformat(game_time_str)
            if timezone.is_naive(game_time):
                game_time = timezone.make_aware(game_time)
        except (ValueError, TypeError):
            continue
        
        home_team_data = game_data.get('home_team', {})
        away_team_data = game_data.get('away_team', {})
        
        # Create ScheduledGame
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
        
        # Calculate opens_at (1 week before game)
        opens_at = game_time - timedelta(days=7)
        # But not before now
        opens_at = max(opens_at, timezone.now())
        
        # Create PredictionEvent
        event = PredictionEvent.objects.create(
            scheduled_game=scheduled_game,
            tip_type=tip_type,
            name=f"{away_team_data.get('abbreviation', '')} @ {home_team_data.get('abbreviation', '')}",
            description=f"{away_team_data.get('full_name', '')} at {home_team_data.get('full_name', '')}",
            target_kind=PredictionEvent.TargetKind.TEAM,
            selection_mode=PredictionEvent.SelectionMode.CURATED,
            source_id='nba-balldontlie',
            source_event_id=game_id,
            metadata={
                'arena': game_data.get('arena', ''),
                'home_team_data': home_team_data,
                'away_team_data': away_team_data,
            },
            opens_at=opens_at,
            deadline=game_time,  # Exact game start time
            reveal_at=opens_at,
            is_active=True,
            points=tip_type.default_points,
        )
        
        # Create prediction options
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
        
        created_count += 1
    
    if created_count > 0:
        messages.success(
            request,
            f'Successfully created {created_count} prediction event(s) from NBA games.'
        )
    
    if skipped_count > 0:
        messages.info(
            request,
                f'Skipped {skipped_count} game(s) that already exist as prediction events.'
        )
    
    if created_count == 0 and skipped_count == 0:
        messages.warning(request, 'No events were created.')
    
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
