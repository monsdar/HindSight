from django.contrib import admin

from .models import (
    NbaPlayer,
    NbaTeam,
    PredictionEvent,
    PredictionOption,
    ScheduledGame,
    TipType,
    UserTip,
)


@admin.register(TipType)
class TipTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'deadline', 'is_active')
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


class PredictionOptionInline(admin.TabularInline):
    model = PredictionOption
    extra = 0


@admin.register(PredictionEvent)
class PredictionEventAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'tip_type',
        'target_kind',
        'selection_mode',
        'opens_at',
        'deadline',
        'is_active',
    )
    list_filter = (
        'tip_type',
        'target_kind',
        'selection_mode',
        'is_active',
    )
    search_fields = ('name', 'description')
    inlines = [PredictionOptionInline]


@admin.register(UserTip)
class UserTipAdmin(admin.ModelAdmin):
    list_display = (
        'user',
        'tip_type',
        'prediction_event',
        'scheduled_game',
        'prediction',
        'updated_at',
    )
    list_filter = (
        'tip_type',
        'scheduled_game__tip_type',
        'prediction_event__tip_type',
    )
    search_fields = ('user__username', 'prediction')
