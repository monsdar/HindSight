from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse

from hooptipp.predictions import services


class NbaPlayerAdminSyncTests(TestCase):
    def setUp(self) -> None:
        self.user = get_user_model().objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='password123',
        )
        self.client.force_login(self.user)
        return super().setUp()

    def test_sync_players_requires_post(self) -> None:
        url = reverse('admin:predictions_nbaplayer_sync')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 405)

    def test_sync_players_triggers_service_and_shows_message(self) -> None:
        url = reverse('admin:predictions_nbaplayer_sync')
        sync_result = services.PlayerSyncResult(created=1, updated=2, removed=3)

        with mock.patch('hooptipp.predictions.admin.services.sync_active_players', return_value=sync_result) as mock_sync:
            response = self.client.post(url, follow=True)

        mock_sync.assert_called_once_with()
        self.assertEqual(response.status_code, 200)

        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any('Player data updated' in message.message for message in messages))
