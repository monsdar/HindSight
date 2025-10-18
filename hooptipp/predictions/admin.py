from datetime import timedelta

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpRequest, HttpResponseRedirect, HttpResponseNotAllowed
from django.shortcuts import render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from . import scoring_service
from .event_sources import list_sources, get_source
from .models import (
    EventOutcome,
    NbaPlayer,
    NbaTeam,
    Option,
    OptionCategory,
    PredictionEvent,
    PredictionOption,
    ScheduledGame,
    TipType,
    UserEventScore,
    UserFavorite,
    UserPreferences,
    UserTip,
)
from .services import _build_bdl_client, _upsert_team


@admin.register(OptionCategory)
class OptionCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'icon', 'option_count', 'is_active', 'sort_order')
    list_filter = ('is_active',)
    search_fields = ('name', 'slug', 'description')
    prepopulated_fields = {'slug': ('name',)}
    ordering = ('sort_order', 'name')

    def option_count(self, obj):
        return obj.options.filter(is_active=True).count()

    option_count.short_description = 'Active Options'


@admin.register(Option)
class OptionAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'short_name',
        'category',
        'external_id',
        'is_active',
        'sort_order',
    )
    list_filter = ('category', 'is_active')
    search_fields = ('name', 'short_name', 'slug', 'external_id')
    autocomplete_fields = ('category',)
    ordering = ('category', 'sort_order', 'name')
    fieldsets = (
        (None, {
            'fields': ('category', 'name', 'short_name', 'slug', 'description')
        }),
        ('Configuration', {
            'fields': ('is_active', 'sort_order')
        }),
        ('External Integration', {
            'fields': ('external_id', 'metadata'),
            'classes': ('collapse',),
        }),
    )


@admin.register(TipType)
class TipTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'default_points', 'deadline', 'is_active')
    list_filter = ('category', 'is_active')
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ('name', 'slug')


@admin.register(ScheduledGame)
class ScheduledGameAdmin(admin.ModelAdmin):
    list_display = (
        'nba_game_id',
        'game_date',
        'away_team_tricode',
        'home_team_tricode',
        'tip_type',
        'is_manual',
    )
    list_filter = ('tip_type', 'is_manual')
    search_fields = ('nba_game_id', 'home_team', 'away_team')
    autocomplete_fields = ('tip_type',)


@admin.register(NbaTeam)
class NbaTeamAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'abbreviation',
        'conference',
        'division',
    )
    search_fields = ('name', 'abbreviation', 'city')
    change_list_template = 'admin/predictions/nbateam/change_list.html'

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                'sync/',
                self.admin_site.admin_view(self.sync_teams_view),
                name='predictions_nbateam_sync',
            ),
        ]
        return custom_urls + urls

    def sync_teams_view(self, request: HttpRequest):
        if request.method != 'POST':
            return HttpResponseNotAllowed(['POST'])

        if not self.has_change_permission(request):
            raise PermissionDenied

        result = services.sync_teams()

        if result.changed:
            message = _(
                'Team data updated. %(created)d created, %(updated)d updated, %(removed)d removed.'
            ) % {
                'created': result.created,
                'updated': result.updated,
                'removed': result.removed,
            }
            level = messages.SUCCESS
        else:
            message = _('Team sync completed with no changes.')
            level = messages.INFO

        self.message_user(request, message, level=level)
        changelist_url = reverse('admin:predictions_nbateam_changelist')
        return HttpResponseRedirect(changelist_url)


@admin.register(NbaPlayer)
class NbaPlayerAdmin(admin.ModelAdmin):
    list_display = (
        'display_name',
        'position',
        'team',
    )
    list_filter = ('team',)
    search_fields = (
        'display_name',
        'first_name',
        'last_name',
    )
    change_list_template = 'admin/predictions/nbaplayer/change_list.html'

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                'sync/',
                self.admin_site.admin_view(self.sync_players_view),
                name='predictions_nbaplayer_sync',
            ),
        ]
        return custom_urls + urls

    def sync_players_view(self, request: HttpRequest):
        if request.method != 'POST':
            return HttpResponseNotAllowed(['POST'])

        if not self.has_change_permission(request):
            raise PermissionDenied

        result = services.sync_active_players()

        if result.changed:
            message = _(
                'Player data updated. %(created)d created, %(updated)d updated, %(removed)d removed.'
            ) % {
                'created': result.created,
                'updated': result.updated,
                'removed': result.removed,
            }
            level = messages.SUCCESS
        else:
            message = _('Player sync completed with no changes.')
            level = messages.INFO

        self.message_user(request, message, level=level)
        changelist_url = reverse('admin:predictions_nbaplayer_changelist')
        return HttpResponseRedirect(changelist_url)


class EventSourceAdmin(admin.ModelAdmin):
    """
    Admin interface for managing event sources.
    
    This is a pseudo-model admin that provides a UI for managing
    event sources without a backing database model.
    """
    
    change_list_template = 'admin/predictions/eventsource/change_list.html'
    
    def has_add_permission(self, request):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return False
    
    def changelist_view(self, request, extra_context=None):
        sources = []
        for source in list_sources():
            sources.append({
                'id': source.source_id,
                'name': source.source_name,
                'categories': ', '.join(source.category_slugs),
                'configured': source.is_configured(),
                'config_help': source.get_configuration_help(),
            })
        
        extra_context = extra_context or {}
        extra_context['sources'] = sources
        extra_context['title'] = 'Event Sources'
        
        return super().changelist_view(request, extra_context=extra_context)
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                '<str:source_id>/sync-options/',
                self.admin_site.admin_view(self.sync_options_view),
                name='predictions_eventsource_sync_options',
            ),
            path(
                '<str:source_id>/sync-events/',
                self.admin_site.admin_view(self.sync_events_view),
                name='predictions_eventsource_sync_events',
            ),
        ]
        return custom_urls + urls
    
    def sync_options_view(self, request: HttpRequest, source_id: str):
        if request.method != 'POST':
            return HttpResponseNotAllowed(['POST'])
        
        if not self.has_change_permission(request):
            raise PermissionDenied
        
        try:
            source = get_source(source_id)
        except ValueError as e:
            messages.error(request, str(e))
            return HttpResponseRedirect(reverse('admin:predictions_eventsource_changelist'))
        
        result = source.sync_options()
        
        if result.has_errors:
            for error in result.errors:
                messages.error(request, error)
        
        if result.changed:
            message = _(
                'Options synced for %(source)s. %(created)d created, %(updated)d updated, %(removed)d removed.'
            ) % {
                'source': source.source_name,
                'created': result.options_created,
                'updated': result.options_updated,
                'removed': result.options_removed,
            }
            level = messages.SUCCESS
        else:
            message = _('Options sync completed with no changes for %(source)s.') % {
                'source': source.source_name
            }
            level = messages.INFO
        
        self.message_user(request, message, level=level)
        return HttpResponseRedirect(reverse('admin:predictions_eventsource_changelist'))
    
    def sync_events_view(self, request: HttpRequest, source_id: str):
        if request.method != 'POST':
            return HttpResponseNotAllowed(['POST'])
        
        if not self.has_change_permission(request):
            raise PermissionDenied
        
        try:
            source = get_source(source_id)
        except ValueError as e:
            messages.error(request, str(e))
            return HttpResponseRedirect(reverse('admin:predictions_eventsource_changelist'))
        
        result = source.sync_events()
        
        if result.has_errors:
            for error in result.errors:
                messages.error(request, error)
        
        if result.changed:
            message = _(
                'Events synced for %(source)s. %(created)d created, %(updated)d updated, %(removed)d removed.'
            ) % {
                'source': source.source_name,
                'created': result.events_created,
                'updated': result.events_updated,
                'removed': result.events_removed,
            }
            level = messages.SUCCESS
        else:
            message = _('Events sync completed with no changes for %(source)s.') % {
                'source': source.source_name
            }
            level = messages.INFO
        
        self.message_user(request, message, level=level)
        return HttpResponseRedirect(reverse('admin:predictions_eventsource_changelist'))


class PredictionOptionInline(admin.TabularInline):
    model = PredictionOption
    extra = 0


@admin.register(PredictionOption)
class PredictionOptionAdmin(admin.ModelAdmin):
    list_display = (
        'event',
        'label',
        'option_display',
        'is_active',
        'sort_order',
    )
    list_filter = ('event__tip_type', 'is_active', 'option__category')
    search_fields = (
        'label',
        'option__name',
    )
    autocomplete_fields = ('event', 'option')
    
    def option_display(self, obj):
        if obj.option:
            return format_html(
                '<strong>{}</strong> <em>({})</em>',
                obj.option.name,
                obj.option.category.name
            )
        return '-'
    
    option_display.short_description = 'Option'


@admin.register(PredictionEvent)
class PredictionEventAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'tip_type',
        'source_display',
        'points',
        'is_bonus_event',
        'target_kind',
        'selection_mode',
        'opens_at',
        'deadline',
        'is_active',
    )
    list_filter = (
        'tip_type',
        'source_id',
        'is_bonus_event',
        'target_kind',
        'selection_mode',
        'is_active',
    )
    search_fields = ('name', 'description', 'source_id', 'source_event_id')
    inlines = [PredictionOptionInline]
    change_list_template = 'admin/predictions/predictionevent/change_list.html'
    fieldsets = (
        (None, {
            'fields': ('tip_type', 'name', 'description')
        }),
        ('Configuration', {
            'fields': (
                'target_kind',
                'selection_mode',
                'points',
                'is_bonus_event',
                'sort_order',
            )
        }),
        ('Schedule', {
            'fields': ('opens_at', 'deadline', 'reveal_at', 'is_active')
        }),
        ('Source Information', {
            'fields': ('source_id', 'source_event_id', 'metadata', 'scheduled_game'),
            'classes': ('collapse',),
            'description': 'Metadata for events imported from external sources'
        }),
    )
    
    def source_display(self, obj):
        if obj.source_id:
            return format_html('<code>{}</code>', obj.source_id)
        return format_html('<em>manual</em>')
    
    source_display.short_description = 'Source'
    source_display.admin_order_field = 'source_id'
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                'add-nba-games/',
                self.admin_site.admin_view(self.add_nba_games_view),
                name='predictions_predictionevent_add_nba_games',
            ),
            path(
                'create-nba-events/',
                self.admin_site.admin_view(self.create_nba_events_view),
                name='predictions_predictionevent_create_nba_events',
            ),
        ]
        return custom_urls + urls
    
    def add_nba_games_view(self, request: HttpRequest):
        """Fetch upcoming NBA games from BallDontLie and display for selection."""
        if not self.has_add_permission(request):
            raise PermissionDenied
        
        from balldontlie.exceptions import BallDontLieException
        from datetime import date
        
        client = _build_bdl_client()
        if client is None:
            messages.error(request, 'BallDontLie API is not configured. Please set BALLDONTLIE_API_TOKEN.')
            return HttpResponseRedirect(reverse('admin:predictions_predictionevent_changelist'))
        
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
            return HttpResponseRedirect(reverse('admin:predictions_predictionevent_changelist'))
        
        # Process games
        games = []
        for game in response.data:
            status = (getattr(game, 'status', '') or '').lower()
            if 'final' in status:
                continue
            
            date_str = getattr(game, 'date', '')
            if not date_str:
                continue
            
            try:
                from datetime import datetime
                game_time = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                if timezone.is_naive(game_time):
                    game_time = timezone.make_aware(game_time)
            except ValueError:
                continue
            
            # Skip games that have already started
            if game_time < timezone.now():
                continue
            
            home_team = getattr(game, 'home_team', None)
            away_team = getattr(game, 'visitor_team', None)
            
            game_id = str(getattr(game, 'id', ''))
            
            # Check if this game already exists as a PredictionEvent
            existing_event = PredictionEvent.objects.filter(
                source_id='nba-balldontlie',
                source_event_id=game_id
            ).first()
            
            home_team_dict = {
                'id': getattr(home_team, 'id', None),
                'full_name': getattr(home_team, 'full_name', ''),
                'name': getattr(home_team, 'name', ''),
                'abbreviation': getattr(home_team, 'abbreviation', ''),
                'city': getattr(home_team, 'city', ''),
                'conference': getattr(home_team, 'conference', ''),
                'division': getattr(home_team, 'division', ''),
            }
            
            away_team_dict = {
                'id': getattr(away_team, 'id', None),
                'full_name': getattr(away_team, 'full_name', ''),
                'name': getattr(away_team, 'name', ''),
                'abbreviation': getattr(away_team, 'abbreviation', ''),
                'city': getattr(away_team, 'city', ''),
                'conference': getattr(away_team, 'conference', ''),
                'division': getattr(away_team, 'division', ''),
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
            import json
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
            return HttpResponseRedirect(reverse('admin:predictions_predictionevent_changelist'))
        
        # Sort by game time
        games.sort(key=lambda g: g['game_time'])
        
        context = {
            **self.admin_site.each_context(request),
            'title': 'Add Upcoming NBA Games',
            'games': games,
            'games_count': len(games),
            'opts': self.model._meta,
        }
        
        return render(request, 'admin/predictions/predictionevent/add_nba_games.html', context)
    
    def create_nba_events_view(self, request: HttpRequest):
        """Create PredictionEvents from selected NBA games."""
        if request.method != 'POST':
            return HttpResponseNotAllowed(['POST'])
        
        if not self.has_add_permission(request):
            raise PermissionDenied
        
        from datetime import datetime
        import json
        
        # Get selected game IDs
        selected_game_ids = request.POST.getlist('selected_games')
        
        if not selected_game_ids:
            messages.warning(request, 'No games were selected.')
            return HttpResponseRedirect(reverse('admin:predictions_predictionevent_add_nba_games'))
        
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
            
            # Create/update teams
            home_team = _upsert_team(home_team_data)
            away_team = _upsert_team(away_team_data)
            
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


@admin.register(EventOutcome)
class EventOutcomeAdmin(admin.ModelAdmin):
    change_form_template = 'admin/predictions/eventoutcome/change_form.html'
    list_display = (
        'prediction_event',
        'winner_display',
        'resolved_at',
        'scored_at',
    )
    list_filter = ('prediction_event__tip_type',)
    search_fields = (
        'prediction_event__name',
        'winning_option__label',
        'winning_generic_option__name',
    )
    autocomplete_fields = (
        'prediction_event',
        'winning_option',
        'winning_generic_option',
        'resolved_by',
    )
    readonly_fields = ('scored_at', 'score_error')
    fieldsets = (
        (None, {
            'fields': ('prediction_event', 'resolved_at', 'resolved_by', 'notes')
        }),
        ('Winning Option', {
            'fields': (
                'winning_option',
                'winning_generic_option',
            ),
            'description': 'Specify the PredictionOption that won, and optionally the generic Option for easier querying.'
        }),
        ('Scoring', {
            'fields': ('scored_at', 'score_error'),
            'classes': ('collapse',),
        }),
    )
    
    def winner_display(self, obj):
        if obj.winning_option:
            return format_html(
                '<strong>{}</strong>',
                obj.winning_option.label
            )
        elif obj.winning_generic_option:
            return format_html(
                '<strong>{}</strong> <em>({})</em>',
                obj.winning_generic_option.name,
                obj.winning_generic_option.category.name if obj.winning_generic_option.category else 'N/A'
            )
        return '-'
    
    winner_display.short_description = 'Winner'

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                '<path:object_id>/score/',
                self.admin_site.admin_view(self.score_event_view),
                name='predictions_eventoutcome_score',
            ),
        ]
        return custom_urls + urls

    def score_event_view(self, request: HttpRequest, object_id: str) -> HttpResponseRedirect:
        if request.method != 'POST':
            return HttpResponseNotAllowed(['POST'])

        outcome = self.get_object(request, object_id)
        if outcome is None:
            raise Http404("Event outcome does not exist.")

        if not self.has_change_permission(request, outcome):
            raise PermissionDenied

        force = request.POST.get('force') == '1'

        try:
            result = scoring_service.score_event_outcome(outcome, force=force)
        except ValueError as exc:
            message = str(exc)
            outcome.score_error = message
            outcome.save(update_fields=['score_error'])
            self.message_user(request, message, level=messages.ERROR)
        else:
            awarded_count = len(result.awarded_scores)
            context = {
                'event': result.event,
                'total': result.total_awarded_points,
                'awarded': awarded_count,
                'created': result.created_count,
                'updated': result.updated_count,
                'skipped': result.skipped_tips,
            }

            if result.created_count or result.updated_count:
                message = _(
                    'Scored %(event)s. Awarded %(total)d total points across %(awarded)d tips '
                    '(%(created)d created, %(updated)d updated). %(skipped)d tips skipped.'
                ) % context
                level = messages.SUCCESS
            elif awarded_count:
                message = _('%(event)s was already scored. No changes were made.') % context
                level = messages.INFO
            else:
                message = _(
                    'No user tips were awarded points for %(event)s. %(skipped)d tips evaluated.'
                ) % context
                level = messages.INFO

            log_message = _(
                'Processed scoring via admin (force=%(force)s). '
                'total=%(total)d created=%(created)d updated=%(updated)d skipped=%(skipped)d'
            ) % {**context, 'force': force}
            self.log_change(request, outcome, log_message)
            self.message_user(request, message, level=level)

        change_url = reverse('admin:predictions_eventoutcome_change', args=[outcome.pk])
        return HttpResponseRedirect(change_url)


@admin.register(UserEventScore)
class UserEventScoreAdmin(admin.ModelAdmin):
    list_display = (
        'user',
        'prediction_event',
        'points_awarded',
        'base_points',
        'lock_multiplier',
        'is_lock_bonus',
        'awarded_at',
    )
    list_filter = (
        'prediction_event__tip_type',
        'is_lock_bonus',
    )
    search_fields = (
        'user__username',
        'prediction_event__name',
    )
    autocomplete_fields = (
        'user',
        'prediction_event',
    )


@admin.register(UserTip)
class UserTipAdmin(admin.ModelAdmin):
    list_display = (
        'user',
        'tip_type',
        'prediction_event',
        'prediction',
        'option_display',
        'is_locked',
        'lock_status',
        'updated_at',
    )
    list_filter = (
        'tip_type',
        'prediction_event__tip_type',
        'is_locked',
        'lock_status',
    )
    search_fields = ('user__username', 'prediction')
    autocomplete_fields = ('user', 'prediction_event', 'prediction_option', 'selected_option')
    fieldsets = (
        (None, {
            'fields': (
                'user',
                'tip_type',
                'prediction_event',
                'prediction_option',
                'selected_option',
                'prediction',
            )
        }),
        ('Lock Information', {
            'fields': (
                'is_locked',
                'lock_status',
                'lock_committed_at',
                'lock_released_at',
                'lock_releases_at',
            ),
            'classes': ('collapse',),
        }),
    )
    
    def option_display(self, obj):
        if obj.selected_option:
            return format_html(
                '<strong>{}</strong> <em>({})</em>',
                obj.selected_option.name,
                obj.selected_option.category.name if obj.selected_option.category else 'N/A'
            )
        return '-'
    
    option_display.short_description = 'Selected'


@admin.register(UserFavorite)
class UserFavoriteAdmin(admin.ModelAdmin):
    list_display = ('user', 'favorite_type', 'option', 'created_at')
    list_filter = ('favorite_type', 'option__category')
    search_fields = ('user__username', 'option__name')
    autocomplete_fields = ('user', 'option')
    
    fieldsets = (
        (None, {
            'fields': ('user', 'favorite_type', 'option')
        }),
        ('Info', {
            'fields': ('created_at',),
            'classes': ('collapse',),
        }),
    )
    readonly_fields = ('created_at',)


@admin.register(UserPreferences)
class UserPreferencesAdmin(admin.ModelAdmin):
    list_display = ('user', 'nickname', 'theme', 'updated_at')
    search_fields = ('user__username', 'nickname')
    autocomplete_fields = ('user',)
    
    fieldsets = (
        (None, {
            'fields': ('user', 'nickname', 'theme')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )
    readonly_fields = ('created_at', 'updated_at')
