"""Theme definitions for HindSight user customization."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Tuple


@dataclass(frozen=True)
class ThemePalette:
    """Represents a selectable color theme."""

    key: str
    label: str
    primary: str
    secondary: str


_THEMES: Tuple[ThemePalette, ...] = (
    ThemePalette("classic", "HindSight Classic (Gold & Midnight)", "#f59e0b", "#0f172a"),
    ThemePalette("atlanta-hawks", "Atlanta Hawks (Red & Black)", "#c8102e", "#000000"),
    ThemePalette("boston-celtics", "Boston Celtics (Green & Black)", "#007a33", "#000000"),
    ThemePalette("brooklyn-nets", "Brooklyn Nets (Black & White)", "#000000", "#ffffff"),
    ThemePalette("charlotte-hornets", "Charlotte Hornets (Teal & Purple)", "#00788c", "#1d1160"),
    ThemePalette("chicago-bulls", "Chicago Bulls (Red & Black)", "#ce1141", "#000000"),
    ThemePalette("cleveland-cavaliers", "Cleveland Cavaliers (Wine & Navy)", "#6f263d", "#041e42"),
    ThemePalette("dallas-mavericks", "Dallas Mavericks (Royal & Navy)", "#00538c", "#002b5e"),
    ThemePalette("denver-nuggets", "Denver Nuggets (Navy & Gold)", "#0e2240", "#fec524"),
    ThemePalette("detroit-pistons", "Detroit Pistons (Blue & Red)", "#1d428a", "#c8102e"),
    ThemePalette("golden-state-warriors", "Golden State Warriors (Blue & Gold)", "#1d428a", "#ffc72c"),
    ThemePalette("houston-rockets", "Houston Rockets (Red & Black)", "#ce1141", "#000000"),
    ThemePalette("indiana-pacers", "Indiana Pacers (Navy & Gold)", "#002d62", "#fdbb30"),
    ThemePalette("los-angeles-clippers", "LA Clippers (Blue & Red)", "#1d428a", "#c8102e"),
    ThemePalette("los-angeles-lakers", "Los Angeles Lakers (Purple & Gold)", "#552583", "#fdb927"),
    ThemePalette("memphis-grizzlies", "Memphis Grizzlies (Blue & Navy)", "#5d76a9", "#12173f"),
    ThemePalette("miami-heat", "Miami Heat (Red & Gold)", "#98002e", "#f9a01b"),
    ThemePalette("milwaukee-bucks", "Milwaukee Bucks (Green & Cream)", "#00471b", "#eee1c6"),
    ThemePalette("minnesota-timberwolves", "Minnesota Timberwolves (Navy & Green)", "#0c2340", "#78be20"),
    ThemePalette("new-orleans-pelicans", "New Orleans Pelicans (Navy & Red)", "#0c2340", "#c8102e"),
    ThemePalette("new-york-knicks", "New York Knicks (Blue & Orange)", "#006bb6", "#f58426"),
    ThemePalette("oklahoma-city-thunder", "Oklahoma City Thunder (Blue & Orange)", "#007ac1", "#ef3b24"),
    ThemePalette("orlando-magic", "Orlando Magic (Blue & Black)", "#0077c0", "#000000"),
    ThemePalette("philadelphia-76ers", "Philadelphia 76ers (Blue & Red)", "#006bb6", "#ed174c"),
    ThemePalette("phoenix-suns", "Phoenix Suns (Purple & Orange)", "#1d1160", "#e56020"),
    ThemePalette("portland-trail-blazers", "Portland Trail Blazers (Red & Black)", "#e03a3e", "#000000"),
    ThemePalette("sacramento-kings", "Sacramento Kings (Purple & Black)", "#5a2d81", "#000000"),
    ThemePalette("san-antonio-spurs", "San Antonio Spurs (Black & Silver)", "#000000", "#c4ced4"),
    ThemePalette("toronto-raptors", "Toronto Raptors (Red & Black)", "#ba0c2f", "#000000"),
    ThemePalette("utah-jazz", "Utah Jazz (Navy & Gold)", "#002b5c", "#f9a01b"),
    ThemePalette("washington-wizards", "Washington Wizards (Navy & Red)", "#002b5c", "#e31837"),
)

DEFAULT_THEME_KEY = "classic"

THEME_CHOICES: Tuple[Tuple[str, str], ...] = tuple((theme.key, theme.label) for theme in _THEMES)

_THEME_LOOKUP: Dict[str, ThemePalette] = {theme.key: theme for theme in _THEMES}


def get_theme_choices() -> Tuple[Tuple[str, str], ...]:
    """Return the available theme options for forms and model fields."""

    return THEME_CHOICES


def get_theme_palette(theme_key: str) -> Dict[str, str]:
    """Return the primary and secondary colors for the given theme key."""

    theme = _THEME_LOOKUP.get(theme_key, _THEME_LOOKUP[DEFAULT_THEME_KEY])
    return {"primary": theme.primary, "secondary": theme.secondary}


def iter_themes() -> Iterable[ThemePalette]:
    """Yield each configured theme palette."""

    return iter(_THEMES)

