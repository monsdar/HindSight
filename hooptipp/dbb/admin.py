"""DBB admin customizations."""

import json
import logging

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponseNotAllowed, HttpResponseRedirect
from django.shortcuts import render
from django.urls import path, reverse
from django.utils.html import format_html

from hooptipp.predictions.models import OptionCategory

from .client import build_slapi_client
from .models import DbbMatch, TrackedLeague, TrackedTeam

logger = logging.getLogger(__name__)


class TrackedTeamInline(admin.TabularInline):
    """Inline admin for tracked teams."""
    model = TrackedTeam
    extra = 0
    fields = ('team_name', 'team_id', 'is_active')
    readonly_fields = ('team_name', 'team_id')


@admin.register(TrackedLeague)
class TrackedLeagueAdmin(admin.ModelAdmin):
    """Admin for tracked leagues."""

    list_display = (
        'league_name',
        'verband_name',
        'club_search_term',
        'team_count',
        'is_active',
        'created_at',
    )
    list_filter = ('is_active', 'verband_name')
    search_fields = ('league_name', 'verband_name', 'club_search_term')
    readonly_fields = ('verband_id', 'league_id', 'created_at', 'updated_at')
    inlines = [TrackedTeamInline]

    fieldsets = (
        ('League Information', {
            'fields': ('verband_name', 'verband_id', 'league_name', 'league_id')
        }),
        ('Tracking', {
            'fields': ('club_search_term', 'is_active')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def team_count(self, obj):
        """Display number of tracked teams."""
        count = obj.teams.count()
        active_count = obj.teams.filter(is_active=True).count()
        return format_html('{} <small>({} active)</small>', count, active_count)
    
    team_count.short_description = 'Teams'

    actions = ['sync_matches_action']

    def sync_matches_action(self, request, queryset):
        """Action to sync matches for selected leagues."""
        from .event_source import DbbEventSource
        
        event_source = DbbEventSource()
        
        # Sync options first
        options_result = event_source.sync_options()
        
        # Sync events
        events_result = event_source.sync_events()
        
        if events_result.has_errors:
            for error in events_result.errors:
                messages.error(request, f'Error: {error}')
        
        if events_result.changed or options_result.changed:
            messages.success(
                request,
                f'Synced: {events_result.events_created} events created, '
                f'{events_result.events_updated} events updated, '
                f'{options_result.options_created} teams created'
            )
        else:
            messages.info(request, 'No changes detected during sync')
    
    sync_matches_action.short_description = 'Sync matches for selected leagues'

    def changelist_view(self, request, extra_context=None):
        """Override changelist view to add custom button."""
        extra_context = extra_context or {}
        extra_context['show_add_leagues_button'] = True
        return super().changelist_view(request, extra_context=extra_context)


@admin.register(TrackedTeam)
class TrackedTeamAdmin(admin.ModelAdmin):
    """Admin for tracked teams."""

    list_display = ('team_name', 'tracked_league', 'is_active', 'created_at')
    list_filter = ('is_active', 'tracked_league__verband_name')
    search_fields = ('team_name', 'tracked_league__league_name')
    readonly_fields = ('team_id', 'created_at', 'updated_at')


@admin.register(DbbMatch)
class DbbMatchAdmin(admin.ModelAdmin):
    """Admin for DBB matches."""

    list_display = (
        'match_display',
        'match_date',
        'league_name',
        'venue',
        'created_at',
    )
    list_filter = ('match_date', 'league_name')
    search_fields = ('home_team', 'away_team', 'league_name')
    readonly_fields = ('external_match_id', 'created_at', 'updated_at', 'metadata')

    fieldsets = (
        ('Match Information', {
            'fields': ('external_match_id', 'match_date', 'home_team', 'away_team', 'venue')
        }),
        ('League', {
            'fields': ('league_name', 'tracked_league', 'tip_type')
        }),
        ('Metadata', {
            'fields': ('metadata', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def match_display(self, obj):
        """Display match in readable format."""
        return format_html(
            '<strong>{}</strong> @ <strong>{}</strong>',
            obj.away_team,
            obj.home_team
        )
    
    match_display.short_description = 'Match'


# Custom admin views

def select_verband_view(request: HttpRequest):
    """Display list of Verbände for admin to select."""
    if not request.user.has_perm('dbb.add_trackedleague'):
        raise PermissionDenied

    client = build_slapi_client()
    if not client:
        messages.error(request, 'SLAPI is not configured. Please set SLAPI_API_TOKEN.')
        return HttpResponseRedirect(reverse('admin:index'))

    try:
        verbaende = client.get_verbaende()
        logger.info(f'Fetched {len(verbaende)} Verbände from SLAPI')
        
        # Log the structure for debugging
        if verbaende:
            sample = verbaende[0]
            logger.debug(
                f'Sample Verband: id={sample.get("id")}, '
                f'label={sample.get("label")}, hits={sample.get("hits")}'
            )
        else:
            logger.warning('No Verbände returned from SLAPI API')
            messages.warning(request, 'No Verbände found. The SLAPI API may be empty or have connectivity issues.')
            
    except Exception as e:
        logger.exception('Failed to fetch Verbände from SLAPI')
        messages.error(request, f'Failed to fetch Verbände: {str(e)}')
        return HttpResponseRedirect(reverse('admin:index'))

    context = {
        'title': 'Select Verband',
        'verbaende': verbaende,
        'app_label': 'dbb',
        'has_permission': True,
    }

    return render(request, 'admin/dbb/select_verband.html', context)


def search_clubs_view(request: HttpRequest):
    """Search for clubs within a Verband and show their leagues."""
    if not request.user.has_perm('dbb.add_trackedleague'):
        raise PermissionDenied

    verband_id = request.GET.get('verband_id')
    verband_name = request.GET.get('verband_name')
    search_query = request.GET.get('query', '').strip()

    if not verband_id or not verband_name:
        messages.error(request, 'Verband not specified')
        return HttpResponseRedirect(reverse('admin:dbb_select_verband'))

    client = build_slapi_client()
    if not client:
        messages.error(request, 'SLAPI is not configured. Please set SLAPI_API_TOKEN.')
        return HttpResponseRedirect(reverse('admin:index'))

    leagues_with_teams = []
    if search_query:
        try:
            # Get leagues for the club search term
            leagues = client.get_club_leagues(verband_id, search_query)
            logger.info(f'Found {len(leagues)} leagues for club search "{search_query}" in {verband_name}')
            
            # For each league, fetch teams from standings
            for league in leagues:
                league_id = str(league.get('liga_id', ''))
                league_name = league.get('liganame', '')
                
                if not league_id:
                    continue

                try:
                    standings = client.get_league_standings(league_id)
                    
                    # Extract unique team names from standings
                    # Note: team is an object with structure {"id": "...", "name": "...", ...}
                    teams = []
                    seen_teams = set()
                    for standing in standings:
                        team_obj = standing.get('team', {})
                        if isinstance(team_obj, dict):
                            team_name = team_obj.get('name', '')
                            team_id = team_obj.get('id', '')
                        else:
                            # Fallback for legacy format
                            team_name = standing.get('team_name', '')
                            team_id = standing.get('team_id', '')
                        
                        if team_name and team_name not in seen_teams:
                            # Filter teams that match the club search term
                            if search_query.lower() in team_name.lower():
                                teams.append({
                                    'name': team_name,
                                    'id': team_id,
                                })
                                seen_teams.add(team_name)
                    
                    if teams:  # Only include leagues with matching teams
                        leagues_with_teams.append({
                            'id': league_id,
                            'name': league_name,
                            'teams': teams,
                            'metadata': league,
                        })
                except Exception as e:
                    logger.warning(f'Failed to fetch standings for league {league_id}: {e}')
                    continue
                    
        except Exception as e:
            logger.exception(f'Failed to fetch leagues for club search "{search_query}"')
            messages.error(request, f'Failed to fetch leagues: {str(e)}')

    context = {
        'title': f'Search Clubs in {verband_name}',
        'verband_id': verband_id,
        'verband_name': verband_name,
        'club_search_term': search_query,
        'search_query': search_query,
        'leagues': leagues_with_teams,
        'app_label': 'dbb',
        'has_permission': True,
    }

    return render(request, 'admin/dbb/search_clubs.html', context)




def import_leagues_view(request: HttpRequest):
    """Import selected leagues and teams."""
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    if not request.user.has_perm('dbb.add_trackedleague'):
        raise PermissionDenied

    verband_id = request.POST.get('verband_id')
    verband_name = request.POST.get('verband_name')
    club_search_term = request.POST.get('club_search_term', '')

    # Get selected leagues and teams
    # Format: league_{league_id} for league selection
    # Format: team_{league_id}_{team_index} for team selection
    
    selected_leagues = {}  # league_id -> {name, teams: []}
    
    for key, value in request.POST.items():
        if key.startswith('league_'):
            league_id = key.replace('league_', '')
            league_name = value
            selected_leagues[league_id] = {
                'name': league_name,
                'teams': []
            }
        elif key.startswith('team_'):
            parts = key.split('_', 2)
            if len(parts) == 3:
                _, league_id, team_idx = parts
                team_data = json.loads(value)
                if league_id in selected_leagues:
                    selected_leagues[league_id]['teams'].append(team_data)

    if not selected_leagues:
        messages.warning(request, 'No leagues selected')
        return HttpResponseRedirect(reverse('admin:dbb_select_verband'))

    # Import the leagues and teams
    imported_count = 0
    team_count = 0

    for league_id, league_data in selected_leagues.items():
        if not league_data['teams']:
            continue  # Skip leagues with no selected teams

        # Create or update TrackedLeague
        tracked_league, created = TrackedLeague.objects.update_or_create(
            verband_id=verband_id,
            league_id=league_id,
            defaults={
                'verband_name': verband_name,
                'league_name': league_data['name'],
                'club_search_term': club_search_term,
                'is_active': True,
            }
        )

        if created:
            imported_count += 1

        # Create TrackedTeam records
        for team_data in league_data['teams']:
            team_name = team_data.get('name', '')
            team_id = team_data.get('id', '')
            
            if team_name:
                TrackedTeam.objects.update_or_create(
                    tracked_league=tracked_league,
                    team_name=team_name,
                    defaults={
                        'team_id': team_id,
                        'is_active': True,
                    }
                )
                team_count += 1

    messages.success(
        request,
        f'Successfully imported {imported_count} league(s) with {team_count} team(s)'
    )

    # Ensure the dbb-teams category exists
    OptionCategory.objects.get_or_create(
        slug='dbb-teams',
        defaults={
            'name': 'German Basketball Teams',
            'description': 'Teams from German amateur basketball leagues',
            'icon': 'basketball',
            'is_active': True,
        }
    )

    return HttpResponseRedirect(reverse('admin:dbb_trackedleague_changelist'))


# Register custom admin URLs
class CustomDbbAdmin:
    """Container for custom DBB admin URLs."""

    @staticmethod
    def get_urls():
        """Get custom DBB admin URLs."""
        return [
            path(
                'select-verband/',
                admin.site.admin_view(select_verband_view),
                name='dbb_select_verband',
            ),
            path(
                'search-clubs/',
                admin.site.admin_view(search_clubs_view),
                name='dbb_search_clubs',
            ),
            path(
                'import-leagues/',
                admin.site.admin_view(import_leagues_view),
                name='dbb_import_leagues',
            ),
        ]


# Hook into admin site URLs
from django.contrib.admin import sites

# Save the original get_urls method
_original_get_urls = sites.AdminSite.get_urls

def _get_urls_with_dbb(self):
    """Get admin URLs including DBB custom views."""
    urls = _original_get_urls(self)
    dbb_urls = CustomDbbAdmin.get_urls()
    return dbb_urls + urls

# Only patch if not already patched
if not hasattr(_get_urls_with_dbb, '_dbb_patched'):
    _get_urls_with_dbb._dbb_patched = True
    sites.AdminSite.get_urls = _get_urls_with_dbb

