from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpRequest, HttpResponseRedirect, HttpResponseNotAllowed
from django.urls import path, reverse
from django.utils.translation import gettext_lazy as _

from . import scoring_service, services
from .models import (
    EventOutcome,
    NbaPlayer,
    NbaTeam,
    PredictionEvent,
    PredictionOption,
    ScheduledGame,
    TipType,
    UserEventScore,
    UserTip,
)


@admin.register(TipType)
class TipTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'default_points', 'deadline', 'is_active')
    list_filter = ('category', 'is_active')
    prepopulated_fields = {'slug': ('name',)}


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


class PredictionOptionInline(admin.TabularInline):
    model = PredictionOption
    extra = 0


@admin.register(PredictionOption)
class PredictionOptionAdmin(admin.ModelAdmin):
    list_display = (
        'event',
        'label',
        'team',
        'player',
        'is_active',
        'sort_order',
    )
    list_filter = ('event__tip_type', 'is_active')
    search_fields = ('label', 'team__name', 'player__display_name')
    autocomplete_fields = ('event', 'team', 'player')


@admin.register(PredictionEvent)
class PredictionEventAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'tip_type',
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
        'is_bonus_event',
        'target_kind',
        'selection_mode',
        'is_active',
    )
    search_fields = ('name', 'description')
    inlines = [PredictionOptionInline]


@admin.register(EventOutcome)
class EventOutcomeAdmin(admin.ModelAdmin):
    change_form_template = 'admin/predictions/eventoutcome/change_form.html'
    list_display = (
        'prediction_event',
        'winning_option',
        'winning_team',
        'winning_player',
        'resolved_at',
        'scored_at',
    )
    list_filter = ('prediction_event__tip_type',)
    search_fields = (
        'prediction_event__name',
        'winning_option__label',
        'winning_team__name',
        'winning_player__display_name',
    )
    autocomplete_fields = (
        'prediction_event',
        'winning_option',
        'winning_team',
        'winning_player',
        'resolved_by',
    )
    readonly_fields = ('scored_at', 'score_error')

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
        'scheduled_game',
        'prediction',
        'is_locked',
        'lock_status',
        'updated_at',
    )
    list_filter = (
        'tip_type',
        'scheduled_game__tip_type',
        'prediction_event__tip_type',
        'is_locked',
        'lock_status',
    )
    search_fields = ('user__username', 'prediction')
