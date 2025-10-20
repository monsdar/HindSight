"""Forms for HindSight predictions views."""
from __future__ import annotations

from django import forms

from .models import UserPreferences
from .theme_palettes import DEFAULT_THEME_KEY, THEME_CHOICES


class UserPreferencesForm(forms.ModelForm):
    """Allow active users to customize their HindSight experience."""

    class Meta:
        model = UserPreferences
        fields = [
            "nickname",
            "theme",
            "activation_pin",
        ]
        widgets = {
            "nickname": forms.TextInput(
                attrs={
                    "class": "theme-accent-outline mt-1 block w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 focus:outline-none",
                    "placeholder": "Enter a nickname",
                }
            ),
            "activation_pin": forms.HiddenInput(),  # We'll handle this with custom JavaScript
        }

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)

        self.fields["nickname"].label = "Display nickname"
        self.fields["theme"] = forms.ChoiceField(
            required=True,
            choices=THEME_CHOICES,
            initial=DEFAULT_THEME_KEY,
            label="Theme",
            widget=forms.Select(
                attrs={
                    "class": "theme-accent-outline mt-1 block w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 focus:outline-none",
                }
            ),
            help_text="Choose an NBA-inspired colorway.",
        )
        self.fields["activation_pin"].label = "Activation PIN"
        self.fields["activation_pin"].help_text = "Select 3 NBA teams as your activation PIN. This prevents others from activating your account."
