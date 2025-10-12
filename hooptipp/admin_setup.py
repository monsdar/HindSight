"""Utilities for provisioning administrative accounts."""

import os
from typing import Any, Optional

from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured


HOOPTIPP_ADMIN_USER_ENV = "HOOPTIPP_ADMIN_USER"
HOOPTIPP_ADMIN_PASSWORD_ENV = "HOOPTIPP_ADMIN_PASSWORD"


def _get_trimmed_env(name: str) -> Optional[str]:
    value = os.environ.get(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def ensure_default_superuser(sender: Any, **kwargs: Any) -> None:
    """Create the default superuser when the auth app finishes migrating.

    The username and password are read from ``HOOPTIPP_ADMIN_USER`` and
    ``HOOPTIPP_ADMIN_PASSWORD`` environment variables respectively. When either
    value is missing or empty the function simply returns. If the specified user
    already exists no changes are made.
    """

    if getattr(sender, "name", None) != "django.contrib.auth":
        return

    username = _get_trimmed_env(HOOPTIPP_ADMIN_USER_ENV)
    password = _get_trimmed_env(HOOPTIPP_ADMIN_PASSWORD_ENV)

    if not username or not password:
        return

    user_model = get_user_model()
    username_field = user_model.USERNAME_FIELD
    lookup = {username_field: username}

    try:
        if user_model.objects.filter(**lookup).exists():
            return
    except Exception as exc:  # pragma: no cover - defensive, should not occur
        raise ImproperlyConfigured("Unable to query the user model") from exc

    create_kwargs = {username_field: username, "password": password}

    for field_name in getattr(user_model, "REQUIRED_FIELDS", []):
        create_kwargs.setdefault(field_name, "")

    user_model.objects.create_superuser(**create_kwargs)
