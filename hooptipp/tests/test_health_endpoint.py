from django.test import Client, TestCase
from django.urls import reverse


class HealthEndpointTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()

    def test_health_endpoint_returns_ok(self) -> None:
        response = self.client.get(reverse('health'))
        self.assertEqual(response.status_code, 200)
