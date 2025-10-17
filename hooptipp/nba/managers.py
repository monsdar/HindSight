"""Managers and helpers for NBA-specific Option queries."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hooptipp.predictions.models import Option, OptionCategory
    from django.db.models import QuerySet


class NbaTeamManager:
    """Helper for querying NBA team Options."""

    CATEGORY_SLUG = 'nba-teams'

    @classmethod
    def get_category(cls) -> OptionCategory:
        """Get the NBA teams category."""
        from hooptipp.predictions.models import OptionCategory

        category, _ = OptionCategory.objects.get_or_create(
            slug=cls.CATEGORY_SLUG,
            defaults={
                'name': 'NBA Teams',
                'description': 'National Basketball Association teams',
                'icon': 'basketball',
                'sort_order': 10,
            },
        )
        return category

    @classmethod
    def all(cls) -> QuerySet[Option]:
        """Get all active NBA team options."""
        from hooptipp.predictions.models import Option

        return Option.objects.filter(
            category__slug=cls.CATEGORY_SLUG, is_active=True
        ).select_related('category')

    @classmethod
    def get_by_abbreviation(cls, abbr: str) -> Option | None:
        """Get a team by its abbreviation."""
        from hooptipp.predictions.models import Option

        return (
            Option.objects.filter(
                category__slug=cls.CATEGORY_SLUG,
                short_name__iexact=abbr,
                is_active=True,
            )
            .select_related('category')
            .first()
        )

    @classmethod
    def get_by_external_id(cls, external_id: str) -> Option | None:
        """Get a team by its BallDontLie ID."""
        from hooptipp.predictions.models import Option

        return (
            Option.objects.filter(
                category__slug=cls.CATEGORY_SLUG,
                external_id=str(external_id),
                is_active=True,
            )
            .select_related('category')
            .first()
        )

    @classmethod
    def get_by_name(cls, name: str) -> Option | None:
        """Get a team by its name."""
        from hooptipp.predictions.models import Option

        return (
            Option.objects.filter(
                category__slug=cls.CATEGORY_SLUG,
                name__iexact=name,
                is_active=True,
            )
            .select_related('category')
            .first()
        )


class NbaPlayerManager:
    """Helper for querying NBA player Options."""

    CATEGORY_SLUG = 'nba-players'

    @classmethod
    def get_category(cls) -> OptionCategory:
        """Get the NBA players category."""
        from hooptipp.predictions.models import OptionCategory

        category, _ = OptionCategory.objects.get_or_create(
            slug=cls.CATEGORY_SLUG,
            defaults={
                'name': 'NBA Players',
                'description': 'Active NBA players',
                'icon': 'person',
                'sort_order': 20,
            },
        )
        return category

    @classmethod
    def all(cls) -> QuerySet[Option]:
        """Get all active NBA player options."""
        from hooptipp.predictions.models import Option

        return Option.objects.filter(
            category__slug=cls.CATEGORY_SLUG, is_active=True
        ).select_related('category')

    @classmethod
    def get_by_external_id(cls, external_id: str) -> Option | None:
        """Get a player by their BallDontLie ID."""
        from hooptipp.predictions.models import Option

        return (
            Option.objects.filter(
                category__slug=cls.CATEGORY_SLUG,
                external_id=str(external_id),
                is_active=True,
            )
            .select_related('category')
            .first()
        )

    @classmethod
    def get_by_team(cls, team_option: Option) -> QuerySet[Option]:
        """Get all players for a specific team."""
        from hooptipp.predictions.models import Option

        # Assuming team info is stored in metadata
        return Option.objects.filter(
            category__slug=cls.CATEGORY_SLUG,
            metadata__team_abbreviation=team_option.short_name,
            is_active=True,
        ).select_related('category')
