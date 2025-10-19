from django.contrib import admin, messages
from django.contrib.admin.options import IncorrectLookupParameters
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpRequest, HttpResponseRedirect, HttpResponseNotAllowed
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.shortcuts import render
from django.db import transaction

from hooptipp.nba.models import ScheduledGame

from . import scoring_service
from .event_sources import list_sources, get_source
from .models import (
    EventOutcome,
    Option,
    OptionCategory,
    PredictionEvent,
    PredictionOption,
    TipType,
    UserEventScore,
    UserFavorite,
    UserPreferences,
    UserTip,
)


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
    """
    Admin for ScheduledGame model.
    
    NOTE: This model is NBA-specific and should eventually be moved to the
    nba package. For now it remains here for backward compatibility.
    """
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
    
    def get_queryset(self, request):
        """
        Return an empty queryset that doesn't hit the database.
        
        This admin uses a pseudo-model with no backing table, so we return
        an empty queryset to prevent any database queries.
        """
        return self.model.objects.none()
    
    def changelist_view(self, request, extra_context=None):
        """
        Override changelist_view to render directly without querying the database.
        
        This admin uses a pseudo-model with no backing table, so we bypass
        the default changelist behavior and render our custom template directly.
        """
        if not self.has_view_or_change_permission(request):
            raise PermissionDenied
        
        sources = []
        for source in list_sources():
            sources.append({
                'id': source.source_id,
                'name': source.source_name,
                'categories': ', '.join(source.category_slugs),
                'configured': source.is_configured(),
                'config_help': source.get_configuration_help(),
            })
        
        context = {
            **self.admin_site.each_context(request),
            'module_name': str(self.model._meta.verbose_name_plural),
            'title': _('Event Sources'),
            'sources': sources,
            'opts': self.model._meta,
            'app_label': self.model._meta.app_label,
            'has_view_permission': self.has_view_permission(request),
            'has_add_permission': self.has_add_permission(request),
            'has_change_permission': self.has_change_permission(request),
            'has_delete_permission': self.has_delete_permission(request),
            'has_editable_inline_admin_formsets': False,
        }
        
        if extra_context:
            context.update(extra_context)
        
        return TemplateResponse(
            request,
            self.change_list_template,
            context
        )
    
    def has_view_or_change_permission(self, request, obj=None):
        """Check if user has view or change permission."""
        return self.has_view_permission(request, obj) or self.has_change_permission(request, obj)
    
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
            return HttpResponseRedirect(reverse('admin:predictions_eventsourcepseudomodel_changelist'))
        
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
        return HttpResponseRedirect(reverse('admin:predictions_eventsourcepseudomodel_changelist'))
    
    def sync_events_view(self, request: HttpRequest, source_id: str):
        if request.method != 'POST':
            return HttpResponseNotAllowed(['POST'])
        
        if not self.has_change_permission(request):
            raise PermissionDenied
        
        try:
            source = get_source(source_id)
        except ValueError as e:
            messages.error(request, str(e))
            return HttpResponseRedirect(reverse('admin:predictions_eventsourcepseudomodel_changelist'))
        
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
        return HttpResponseRedirect(reverse('admin:predictions_eventsourcepseudomodel_changelist'))


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


@admin.register(EventOutcome)
class EventOutcomeAdmin(admin.ModelAdmin):
    change_form_template = 'admin/predictions/eventoutcome/change_form.html'
    changelist_template = 'admin/predictions/eventoutcome/change_list.html'
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
            'description': 'Specify the PredictionOption that won (required), and optionally the underlying generic Option for easier querying.'
        }),
        ('Scoring', {
            'fields': ('scored_at', 'score_error'),
            'classes': ('collapse',),
        }),
    )

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                'batch-add/',
                self.admin_site.admin_view(self.batch_add_outcomes_view),
                name='predictions_eventoutcome_batch_add',
            ),
            path(
                '<path:object_id>/score/',
                self.admin_site.admin_view(self.score_event_view),
                name='predictions_eventoutcome_score',
            ),
        ]
        return custom_urls + urls

    def batch_add_outcomes_view(self, request: HttpRequest) -> HttpResponseRedirect | TemplateResponse:
        """Custom view for batch adding event outcomes."""
        if not self.has_add_permission(request):
            raise PermissionDenied

        # Get events that are past deadline and have no outcome
        now = timezone.now()
        events_without_outcomes = PredictionEvent.objects.filter(
            deadline__lt=now,
            outcome__isnull=True,
            is_active=True
        ).select_related('tip_type').prefetch_related('options__option').order_by('deadline', 'name')

        if request.method == 'POST':
            return self._process_batch_outcomes(request, events_without_outcomes)

        # Prepare context for GET request
        events_data = []
        for event in events_without_outcomes:
            events_data.append({
                'event': event,
                'options': event.options.filter(is_active=True).order_by('sort_order', 'label'),
            })

        context = {
            **self.admin_site.each_context(request),
            'title': _('Add Event Outcomes'),
            'events_data': events_data,
            'opts': self.model._meta,
            'app_label': self.model._meta.app_label,
            'has_view_permission': self.has_view_permission(request),
            'has_add_permission': self.has_add_permission(request),
        }

        return render(request, 'admin/predictions/eventoutcome/batch_add.html', context)

    def _process_batch_outcomes(self, request: HttpRequest, events_queryset) -> HttpResponseRedirect:
        """Process the batch outcomes form submission."""
        outcomes_created = 0
        
        with transaction.atomic():
            for event in events_queryset:
                winning_option_id = request.POST.get(f'winning_option_{event.id}')
                
                if winning_option_id:
                    try:
                        winning_option = PredictionOption.objects.get(
                            id=winning_option_id,
                            event=event
                        )
                        
                        # Create the outcome
                        outcome = EventOutcome.objects.create(
                            prediction_event=event,
                            winning_option=winning_option,
                            winning_generic_option=winning_option.option,
                            resolved_by=request.user,
                            resolved_at=timezone.now()
                        )
                        
                        outcomes_created += 1
                        
                    except PredictionOption.DoesNotExist:
                        messages.error(
                            request,
                            _('Invalid option selected for event "%(event)s".') % {'event': event.name}
                        )
                        continue

        if outcomes_created > 0:
            message = _('Successfully created %(count)d event outcomes.') % {'count': outcomes_created}
            messages.success(request, message)
        else:
            messages.info(request, _('No outcomes were created.'))

        return HttpResponseRedirect(reverse('admin:predictions_eventoutcome_changelist'))
    
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
    change_list_template = 'admin/predictions/usereventscore/change_list.html'
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

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                'process-all-scores/',
                self.admin_site.admin_view(self.process_all_scores_view),
                name='predictions_usereventscore_process_all_scores',
            ),
        ]
        return custom_urls + urls

    def process_all_scores_view(self, request: HttpRequest) -> HttpResponseRedirect:
        """Process scores for all user tips that have corresponding event outcomes."""
        if request.method != 'POST':
            return HttpResponseNotAllowed(['POST'])

        if not self.has_change_permission(request):
            raise PermissionDenied

        force = request.POST.get('force') == '1'

        try:
            result = scoring_service.process_all_user_scores(force=force)
        except Exception as exc:
            message = f"Error processing scores: {str(exc)}"
            self.message_user(request, message, level=messages.ERROR)
        else:
            if result.events_with_errors:
                for error in result.events_with_errors:
                    messages.warning(request, f"Warning: {error}")

            if result.total_scores_created or result.total_scores_updated:
                message = (
                    f"Successfully processed {result.total_events_processed} events. "
                    f"Created {result.total_scores_created} scores, "
                    f"updated {result.total_scores_updated} scores. "
                    f"Returned {result.total_locks_returned} locks to users, "
                    f"forfeited {result.total_locks_forfeited} locks. "
                    f"Skipped {result.total_tips_skipped} tips."
                )
                level = messages.SUCCESS
            else:
                message = (
                    f"No scores were created or updated. "
                    f"Processed {result.total_events_processed} events, "
                    f"returned {result.total_locks_returned} locks to users, "
                    f"forfeited {result.total_locks_forfeited} locks, "
                    f"skipped {result.total_tips_skipped} tips."
                )
                level = messages.INFO

            self.message_user(request, message, level=level)

        return HttpResponseRedirect(reverse('admin:predictions_usereventscore_changelist'))


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


# Register the EventSourceAdmin manually
# EventSource is not a real model, so we register it specially
from django.db import models

class EventSourcePseudoModel(models.Model):
    """Pseudo-model for EventSource admin registration."""
    
    class Meta:
        app_label = 'predictions'
        verbose_name = 'Event Source'
        verbose_name_plural = 'Event Sources'
        # This is not a real database model
        managed = False
        # Use a fake table name that won't conflict
        db_table = '_predictions_eventsource_pseudo'

# Register the EventSourceAdmin with the pseudo-model
admin.site.register(EventSourcePseudoModel, EventSourceAdmin)
