"""NBA admin customizations."""

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponseNotAllowed, HttpResponseRedirect
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models import NbaUserPreferences, ScheduledGame
from .services import sync_players, sync_teams


@admin.register(ScheduledGame)
class ScheduledGameAdmin(admin.ModelAdmin):
    """Admin for NBA scheduled games."""

    list_display = (
        "nba_game_id",
        "game_date",
        "away_team_tricode",
        "home_team_tricode",
        "tip_type",
        "is_manual",
    )
    list_filter = ("tip_type", "is_manual")
    search_fields = ("nba_game_id", "home_team", "away_team")
    autocomplete_fields = ("tip_type", "home_team_option", "away_team_option")
    readonly_fields = ("nba_game_id",)

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "tip_type",
                    "nba_game_id",
                    "game_date",
                    "venue",
                    "is_manual",
                )
            },
        ),
        (
            "Teams",
            {
                "fields": (
                    "home_team",
                    "home_team_tricode",
                    "home_team_option",
                    "away_team",
                    "away_team_tricode",
                    "away_team_option",
                )
            },
        ),
    )


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
