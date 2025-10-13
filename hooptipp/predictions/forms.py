"""Forms for HoopTipp predictions views."""
from __future__ import annotations

from typing import Iterable, List, Sequence, Tuple

from django import forms

from .models import UserPreferences
from .services import get_player_choices, get_team_choices

ChoiceList = Sequence[Tuple[str, str]]


def _build_choices(options: Iterable[Tuple[str, str]]) -> List[Tuple[str, str]]:
    choice_list = [("", "No selection")]
    for value, label in options:
        if not value:
            continue
        choice_list.append((value, label))
    return choice_list


class UserPreferencesForm(forms.ModelForm):
    """Allow active users to customize their HoopTipp experience."""

    class Meta:
        model = UserPreferences
        fields = [
            "nickname",
            "favorite_team_id",
            "favorite_player_id",
            "theme_primary_color",
            "theme_secondary_color",
        ]
        widgets = {
            "nickname": forms.TextInput(
                attrs={
                    "class": "theme-accent-outline mt-1 block w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 focus:outline-none",
                    "placeholder": "Enter a nickname",
                }
            ),
            "theme_primary_color": forms.TextInput(
                attrs={
                    "type": "color",
                    "class": "theme-accent-outline h-10 w-16 rounded border border-slate-700 bg-slate-950",
                }
            ),
            "theme_secondary_color": forms.TextInput(
                attrs={
                    "type": "color",
                    "class": "theme-accent-outline h-10 w-16 rounded border border-slate-700 bg-slate-950",
                }
            ),
        }

    def __init__(
        self,
        *args: object,
        team_choices: ChoiceList | None = None,
        player_choices: ChoiceList | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(*args, **kwargs)

        if team_choices is None:
            team_choices = get_team_choices()
        if player_choices is None:
            player_choices = get_player_choices()

        self.fields["favorite_team_id"] = forms.TypedChoiceField(
            required=False,
            choices=_build_choices(team_choices),
            coerce=lambda value: int(value) if value else None,
            empty_value=None,
            label="Favorite team",
            widget=forms.Select(
                attrs={
                    "class": "theme-accent-outline mt-1 block w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 focus:outline-none",
                }
            ),
        )
        self.fields["favorite_player_id"] = forms.TypedChoiceField(
            required=False,
            choices=_build_choices(player_choices),
            coerce=lambda value: int(value) if value else None,
            empty_value=None,
            label="Favorite player",
            widget=forms.Select(
                attrs={
                    "class": "theme-accent-outline mt-1 block w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 focus:outline-none",
                }
            ),
        )

        self.fields["nickname"].label = "Display nickname"
        self.fields["theme_primary_color"].label = "Primary accent color"
        self.fields["theme_secondary_color"].label = "Accent text color"

    def clean_theme_primary_color(self) -> str:
        return self._clean_hex_color("theme_primary_color")

    def clean_theme_secondary_color(self) -> str:
        return self._clean_hex_color("theme_secondary_color")

    def _clean_hex_color(self, field_name: str) -> str:
        value = self.cleaned_data.get(field_name)
        if not value:
            return value
        return value.lower()
