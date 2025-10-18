"""Tests for the card renderer system."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from hooptipp.predictions.card_renderers.base import CardRenderer, DefaultCardRenderer
from hooptipp.predictions.card_renderers.registry import CardRendererRegistry
from hooptipp.predictions.models import (
    EventOutcome,
    OptionCategory,
    PredictionEvent,
    PredictionOption,
    TipType,
    Option,
)


class MockCardRenderer(CardRenderer):
    """Mock card renderer for testing."""

    def __init__(self, source_id: str = "mock-source", priority: int = 0):
        self._source_id = source_id
        self._priority = priority

    def can_render(self, event) -> bool:
        return event.source_id == self._source_id

    def get_event_template(self, event) -> str:
        return "mock/cards/event.html"

    def get_result_template(self, outcome) -> str:
        return "mock/cards/result.html"

    def get_event_context(self, event, user=None) -> dict:
        return {"mock_data": "event_data"}

    def get_result_context(self, outcome, user=None) -> dict:
        return {"mock_data": "result_data"}

    @property
    def priority(self) -> int:
        return self._priority


class CardRendererBaseTests(TestCase):
    """Tests for CardRenderer base class."""

    def test_default_renderer_accepts_any_event(self):
        """DefaultCardRenderer should accept any event."""
        tip_type = TipType.objects.create(
            name="Test",
            slug="test",
            deadline=timezone.now(),
        )
        event = PredictionEvent.objects.create(
            tip_type=tip_type,
            name="Test Event",
            opens_at=timezone.now(),
            deadline=timezone.now(),
        )

        renderer = DefaultCardRenderer()
        self.assertTrue(renderer.can_render(event))

    def test_default_renderer_uses_default_template(self):
        """DefaultCardRenderer should use default template."""
        tip_type = TipType.objects.create(
            name="Test",
            slug="test",
            deadline=timezone.now(),
        )
        event = PredictionEvent.objects.create(
            tip_type=tip_type,
            name="Test Event",
            opens_at=timezone.now(),
            deadline=timezone.now(),
        )

        renderer = DefaultCardRenderer()
        template = renderer.get_event_template(event)
        self.assertEqual(template, "predictions/cards/default.html")

    def test_default_renderer_has_lowest_priority(self):
        """DefaultCardRenderer should have lowest priority."""
        renderer = DefaultCardRenderer()
        self.assertEqual(renderer.priority, -1000)

    def test_default_renderer_empty_context(self):
        """DefaultCardRenderer should return empty context."""
        tip_type = TipType.objects.create(
            name="Test",
            slug="test",
            deadline=timezone.now(),
        )
        event = PredictionEvent.objects.create(
            tip_type=tip_type,
            name="Test Event",
            opens_at=timezone.now(),
            deadline=timezone.now(),
        )

        renderer = DefaultCardRenderer()
        context = renderer.get_event_context(event)
        self.assertEqual(context, {})

    def test_result_template_defaults_to_event_template(self):
        """Result template should default to event template."""
        tip_type = TipType.objects.create(
            name="Test",
            slug="test",
            deadline=timezone.now(),
        )
        event = PredictionEvent.objects.create(
            tip_type=tip_type,
            name="Test Event",
            opens_at=timezone.now(),
            deadline=timezone.now(),
        )
        category = OptionCategory.objects.create(slug="test", name="Test")
        option_obj = Option.objects.create(
            category=category,
            slug="test",
            name="Test Option",
        )
        prediction_option = PredictionOption.objects.create(
            event=event,
            label="Test",
            option=option_obj,
        )
        outcome = EventOutcome.objects.create(
            prediction_event=event,
            winning_option=prediction_option,
        )

        renderer = MockCardRenderer()
        event_template = renderer.get_event_template(event)
        result_template = renderer.get_result_template(outcome)

        # Should be different in our mock implementation
        self.assertNotEqual(event_template, result_template)
        self.assertEqual(result_template, "mock/cards/result.html")

    def test_result_context_defaults_to_event_context(self):
        """Result context should default to event context by default."""
        tip_type = TipType.objects.create(
            name="Test",
            slug="test",
            deadline=timezone.now(),
        )
        event = PredictionEvent.objects.create(
            tip_type=tip_type,
            name="Test Event",
            opens_at=timezone.now(),
            deadline=timezone.now(),
        )
        category = OptionCategory.objects.create(slug="test", name="Test")
        option_obj = Option.objects.create(
            category=category,
            slug="test",
            name="Test Option",
        )
        prediction_option = PredictionOption.objects.create(
            event=event,
            label="Test",
            option=option_obj,
        )
        outcome = EventOutcome.objects.create(
            prediction_event=event,
            winning_option=prediction_option,
        )

        renderer = DefaultCardRenderer()
        event_context = renderer.get_event_context(event)
        result_context = renderer.get_result_context(outcome)

        self.assertEqual(event_context, result_context)


class CardRendererRegistryTests(TestCase):
    """Tests for CardRendererRegistry."""

    def test_registry_returns_default_for_unmatched_event(self):
        """Registry should return default renderer if no match."""
        registry = CardRendererRegistry()

        tip_type = TipType.objects.create(
            name="Test",
            slug="test",
            deadline=timezone.now(),
        )
        event = PredictionEvent.objects.create(
            tip_type=tip_type,
            name="Test Event",
            source_id="unknown-source",
            opens_at=timezone.now(),
            deadline=timezone.now(),
        )

        renderer = registry.get_renderer(event)
        self.assertIsInstance(renderer, DefaultCardRenderer)

    def test_registry_returns_matching_renderer(self):
        """Registry should return matching renderer."""
        registry = CardRendererRegistry()
        mock_renderer = MockCardRenderer(source_id="test-source")
        registry.register(mock_renderer)

        tip_type = TipType.objects.create(
            name="Test",
            slug="test",
            deadline=timezone.now(),
        )
        event = PredictionEvent.objects.create(
            tip_type=tip_type,
            name="Test Event",
            source_id="test-source",
            opens_at=timezone.now(),
            deadline=timezone.now(),
        )

        renderer = registry.get_renderer(event)
        self.assertIsInstance(renderer, MockCardRenderer)
        self.assertEqual(renderer.get_event_template(event), "mock/cards/event.html")

    def test_registry_respects_priority(self):
        """Registry should check renderers in priority order."""
        registry = CardRendererRegistry()

        # Register low priority renderer first
        low_priority = MockCardRenderer(source_id="test-source", priority=0)
        registry.register(low_priority)

        # Register high priority renderer second
        high_priority = MockCardRenderer(source_id="test-source", priority=10)
        registry.register(high_priority)

        tip_type = TipType.objects.create(
            name="Test",
            slug="test",
            deadline=timezone.now(),
        )
        event = PredictionEvent.objects.create(
            tip_type=tip_type,
            name="Test Event",
            source_id="test-source",
            opens_at=timezone.now(),
            deadline=timezone.now(),
        )

        # Should return high priority renderer
        renderer = registry.get_renderer(event)
        self.assertEqual(renderer.priority, 10)

    def test_registry_lists_renderers(self):
        """Registry should list all registered renderers."""
        registry = CardRendererRegistry()
        renderer1 = MockCardRenderer(source_id="source1")
        renderer2 = MockCardRenderer(source_id="source2")

        registry.register(renderer1)
        registry.register(renderer2)

        renderers = registry.list_renderers()
        self.assertEqual(len(renderers), 2)
        self.assertIn(renderer1, renderers)
        self.assertIn(renderer2, renderers)

    def test_multiple_renderers_first_match_wins(self):
        """When multiple renderers match, first by priority should win."""
        registry = CardRendererRegistry()

        class AlwaysMatchRenderer(CardRenderer):
            def __init__(self, name: str, priority: int):
                self.name = name
                self._priority = priority

            def can_render(self, event) -> bool:
                return True  # Always matches

            def get_event_template(self, event) -> str:
                return f"{self.name}/template.html"

            @property
            def priority(self) -> int:
                return self._priority

        renderer_a = AlwaysMatchRenderer("a", priority=5)
        renderer_b = AlwaysMatchRenderer("b", priority=10)
        renderer_c = AlwaysMatchRenderer("c", priority=3)

        # Register in random order
        registry.register(renderer_a)
        registry.register(renderer_b)
        registry.register(renderer_c)

        tip_type = TipType.objects.create(
            name="Test",
            slug="test",
            deadline=timezone.now(),
        )
        event = PredictionEvent.objects.create(
            tip_type=tip_type,
            name="Test Event",
            opens_at=timezone.now(),
            deadline=timezone.now(),
        )

        renderer = registry.get_renderer(event)
        # Should be renderer_b with highest priority
        self.assertEqual(renderer.get_event_template(event), "b/template.html")


class CustomRendererImplementationTests(TestCase):
    """Tests for custom renderer implementations."""

    def test_custom_renderer_with_metadata_check(self):
        """Custom renderer can check event metadata."""

        class MetadataRenderer(CardRenderer):
            def can_render(self, event) -> bool:
                return event.metadata.get("custom_type") == "special"

            def get_event_template(self, event) -> str:
                return "custom/special.html"

        registry = CardRendererRegistry()
        registry.register(MetadataRenderer())

        tip_type = TipType.objects.create(
            name="Test",
            slug="test",
            deadline=timezone.now(),
        )

        # Event without matching metadata
        event1 = PredictionEvent.objects.create(
            tip_type=tip_type,
            name="Regular Event",
            opens_at=timezone.now(),
            deadline=timezone.now(),
            metadata={},
        )

        # Event with matching metadata
        event2 = PredictionEvent.objects.create(
            tip_type=tip_type,
            name="Special Event",
            opens_at=timezone.now(),
            deadline=timezone.now(),
            metadata={"custom_type": "special"},
        )

        # Regular event should use default
        renderer1 = registry.get_renderer(event1)
        self.assertIsInstance(renderer1, DefaultCardRenderer)

        # Special event should use custom renderer
        renderer2 = registry.get_renderer(event2)
        self.assertIsInstance(renderer2, MetadataRenderer)
        self.assertEqual(renderer2.get_event_template(event2), "custom/special.html")

    def test_custom_renderer_with_user_context(self):
        """Custom renderer can use user parameter for personalization."""

        class UserAwareRenderer(CardRenderer):
            def can_render(self, event) -> bool:
                return event.source_id == "user-aware"

            def get_event_template(self, event) -> str:
                return "custom/user_aware.html"

            def get_event_context(self, event, user=None) -> dict:
                context = {"is_personalized": False}
                if user:
                    context["is_personalized"] = True
                    context["username"] = user.username
                return context

        registry = CardRendererRegistry()
        registry.register(UserAwareRenderer())

        tip_type = TipType.objects.create(
            name="Test",
            slug="test",
            deadline=timezone.now(),
        )
        event = PredictionEvent.objects.create(
            tip_type=tip_type,
            name="User Aware Event",
            source_id="user-aware",
            opens_at=timezone.now(),
            deadline=timezone.now(),
        )

        renderer = registry.get_renderer(event)

        # Without user
        context_no_user = renderer.get_event_context(event)
        self.assertFalse(context_no_user["is_personalized"])

        # With user
        User = get_user_model()
        user = User.objects.create_user(username="testuser")
        context_with_user = renderer.get_event_context(event, user=user)
        self.assertTrue(context_with_user["is_personalized"])
        self.assertEqual(context_with_user["username"], "testuser")
