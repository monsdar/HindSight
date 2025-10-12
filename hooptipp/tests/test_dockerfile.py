from pathlib import Path

from django.test import SimpleTestCase


class DockerfileTests(SimpleTestCase):
    def setUp(self) -> None:
        self.dockerfile_path = Path(__file__).resolve().parents[2] / "Dockerfile"

    def test_dockerfile_exists(self) -> None:
        self.assertTrue(self.dockerfile_path.exists(), "Dockerfile should exist at project root")

    def test_python_version_is_pinned(self) -> None:
        content = self.dockerfile_path.read_text(encoding="utf-8")
        self.assertIn("python:3.12-slim", content)
        self.assertIn("gunicorn\", \"hooptipp.wsgi:application\"", content)
