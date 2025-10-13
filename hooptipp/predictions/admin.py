from django.contrib import admin

from .models import TipType, ScheduledGame, UserTip


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


@admin.register(UserTip)
class UserTipAdmin(admin.ModelAdmin):
    list_display = ('user', 'tip_type', 'scheduled_game', 'prediction', 'updated_at')
    list_filter = ('tip_type', 'scheduled_game__tip_type')
    search_fields = ('user__username', 'prediction')
