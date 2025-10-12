from unittest import mock

from django.apps import apps
from django.contrib.auth import get_user_model
from django.test import TestCase

from hooptipp import admin_setup


class EnsureDefaultSuperuserTests(TestCase):
    def _call_handler(self) -> None:
        sender = apps.get_app_config('auth')
        admin_setup.ensure_default_superuser(sender)

    def test_no_action_when_environment_missing(self) -> None:
        with mock.patch.dict('os.environ', {}, clear=True):
            self._call_handler()

        user_model = get_user_model()
        self.assertEqual(user_model.objects.count(), 0)

    def test_creates_superuser_when_not_present(self) -> None:
        username = 'auto-admin'
        password = 'secure-password'
        with mock.patch.dict(
            'os.environ',
            {
                admin_setup.HOOPTIPP_ADMIN_USER_ENV: username,
                admin_setup.HOOPTIPP_ADMIN_PASSWORD_ENV: password,
            },
            clear=True,
        ):
            self._call_handler()

        user_model = get_user_model()
        user = user_model.objects.get(**{user_model.USERNAME_FIELD: username})
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.check_password(password))

    def test_existing_user_is_not_modified(self) -> None:
        username = 'existing-admin'
        original_password = 'original-password'
        user_model = get_user_model()
        user = user_model.objects.create_superuser(username=username, password=original_password)
        original_hash = user.password

        with mock.patch.dict(
            'os.environ',
            {
                admin_setup.HOOPTIPP_ADMIN_USER_ENV: username,
                admin_setup.HOOPTIPP_ADMIN_PASSWORD_ENV: 'new-password',
            },
            clear=True,
        ):
            self._call_handler()

        user.refresh_from_db()
        self.assertEqual(user.password, original_hash)
        self.assertTrue(user.check_password(original_password))
