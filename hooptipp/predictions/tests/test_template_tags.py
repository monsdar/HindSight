"""Tests for prediction template tags."""

from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.template import Context, Template
from django.test import RequestFactory, TestCase
from django.utils import timezone

from hooptipp.predictions.card_renderers.base import CardRenderer
from hooptipp.predictions.card_renderers.registry import CardRendererRegistry
from hooptipp.predictions.models import (
    EventOutcome,
    Option,
    OptionCategory,
    PredictionEvent,
    PredictionOption,
    TipType,
    UserTip,
)
from hooptipp.predictions.theme_palettes import get_theme_palette


class RenderPredictionCardTemplateTagTests(TestCase):
    """Tests for {% render_prediction_card %} template tag."""

    def setUp(self):
        self.factory = RequestFactory()
        self.User = get_user_model()
        self.user = self.User.objects.create_user(username="testuser")

        self.tip_type = TipType.objects.create(
            name="Test",
            slug="test",
            deadline=timezone.now(),
        )
        self.category = OptionCategory.objects.create(slug="test", name="Test")
        self.option1 = Option.objects.create(
            category=self.category,
            slug="option1",
            name="Option 1",
        )
        self.option2 = Option.objects.create(
            category=self.category,
            slug="option2",
            name="Option 2",
        )
        self.event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name="Test Event",
            opens_at=timezone.now(),
            deadline=timezone.now() + timedelta(hours=1),
        )
        self.prediction_option1 = PredictionOption.objects.create(
            event=self.event,
            label="Option 1",
            option=self.option1,
        )
        self.prediction_option2 = PredictionOption.objects.create(
            event=self.event,
            label="Option 2",
            option=self.option2,
        )

    def test_render_prediction_card_uses_default_template(self):
        """Tag should use default template when no custom renderer matches."""
        template = Template(
            "{% load prediction_extras %}"
            "{% render_prediction_card event %}"
        )
        context = Context({
            "event": self.event,
            "active_user": self.user,
        })

        rendered = template.render(context)

        # Should contain event name
        self.assertIn("Test Event", rendered)
        # Should contain the article with prediction-card class
        self.assertIn("prediction-card", rendered)

    def test_render_prediction_card_with_user_tip(self):
        """Tag should render with user tip when provided."""
        user_tip = UserTip.objects.create(
            user=self.user,
            tip_type=self.tip_type,
            prediction_event=self.event,
            prediction_option=self.prediction_option1,
            selected_option=self.option1,
            prediction="Option 1",
        )

        template = Template(
            "{% load prediction_extras %}"
            "{% render_prediction_card event user_tip %}"
        )
        context = Context({
            "event": self.event,
            "user_tip": user_tip,
            "active_user": self.user,
        })

        rendered = template.render(context)

        # Should contain checked radio button (checked attribute)
        self.assertIn("checked", rendered)

    def test_render_prediction_card_with_custom_renderer(self):
        """Tag should use custom renderer when registered."""

        class TestCardRenderer(CardRenderer):
            def can_render(self, event) -> bool:
                return event.source_id == "test-source"

            def get_event_template(self, event) -> str:
                # Use a simple inline template for testing
                return "predictions/cards/default.html"

            def get_event_context(self, event, user=None) -> dict:
                return {"custom_test_data": "test_value"}

        # Register the custom renderer
        registry = CardRendererRegistry()
        registry.register(TestCardRenderer())

        # Create event with matching source_id
        event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name="Custom Event",
            source_id="test-source",
            opens_at=timezone.now(),
            deadline=timezone.now() + timedelta(hours=1),
        )

        # Mock the global registry
        with mock.patch("hooptipp.predictions.templatetags.prediction_extras.registry", registry):
            template = Template(
                "{% load prediction_extras %}"
                "{% render_prediction_card event %}"
            )
            context = Context({
                "event": event,
                "active_user": self.user,
            })

            rendered = template.render(context)

            # Should contain event name
            self.assertIn("Custom Event", rendered)

    def test_render_prediction_card_without_active_user(self):
        """Tag should render without active user."""
        template = Template(
            "{% load prediction_extras %}"
            "{% render_prediction_card event %}"
        )
        context = Context({
            "event": self.event,
            "active_user": None,
        })

        rendered = template.render(context)

        # Should contain event name
        self.assertIn("Test Event", rendered)
        # Should contain message about activating user
        self.assertIn("Activate a user", rendered)

    def test_render_prediction_card_includes_theme_palette(self):
        """Tag should include theme palette in context."""
        template = Template(
            "{% load prediction_extras %}"
            "{% render_prediction_card event %}"
        )
        palette = get_theme_palette("lakers")
        context = Context({
            "event": self.event,
            "active_user": self.user,
            "active_theme_palette": palette,
        })

        rendered = template.render(context)

        # The template should be rendered (contains the event name)
        self.assertIn("Test Event", rendered)
        # Theme classes should be present
        self.assertIn("theme-accent", rendered)

    def test_render_prediction_card_includes_lock_summary(self):
        """Tag should include lock summary in context."""
        lock_summary = {
            "total": 5,
            "available": 3,
            "active": 2,
        }

        template = Template(
            "{% load prediction_extras %}"
            "{% render_prediction_card event %}"
        )
        context = Context({
            "event": self.event,
            "active_user": self.user,
            "lock_summary": lock_summary,
        })

        rendered = template.render(context)

        # Should contain event name
        self.assertIn("Test Event", rendered)

    def test_render_prediction_card_includes_user_prediction_badges(self):
        """Tag should include users who have predicted in context."""
        # Create additional users
        user2 = self.User.objects.create_user(username="user2")
        user3 = self.User.objects.create_user(username="user3")
        
        # Create user tips for the event
        UserTip.objects.create(
            user=self.user,
            tip_type=self.tip_type,
            prediction_event=self.event,
            prediction_option=self.prediction_option1,
            selected_option=self.option1,
            prediction="Option 1",
        )
        UserTip.objects.create(
            user=user2,
            tip_type=self.tip_type,
            prediction_event=self.event,
            prediction_option=self.prediction_option2,
            selected_option=self.option2,
            prediction="Option 2",
        )

        # Create event_tip_users mapping
        event_tip_users = {
            self.event.id: [self.user, user2]
        }

        template = Template(
            "{% load prediction_extras %}"
            "{% render_prediction_card event %}"
        )
        context = Context({
            "event": self.event,
            "active_user": self.user,
            "event_tip_users": event_tip_users,
        })

        rendered = template.render(context)

        # Should contain event name
        self.assertIn("Test Event", rendered)
        # Should contain "Predicted by:" text
        self.assertIn("Predicted by:", rendered)
        # Should contain usernames of users who predicted
        self.assertIn("testuser", rendered)
        self.assertIn("user2", rendered)
        # Should not contain user3 who didn't predict
        self.assertNotIn("user3", rendered)

    def test_render_prediction_card_with_no_predictions(self):
        """Tag should not show prediction badges when no users have predicted."""
        template = Template(
            "{% load prediction_extras %}"
            "{% render_prediction_card event %}"
        )
        context = Context({
            "event": self.event,
            "active_user": self.user,
            "event_tip_users": {},  # Empty mapping
        })

        rendered = template.render(context)

        # Should contain event name
        self.assertIn("Test Event", rendered)
        # Should not contain "Predicted by:" text
        self.assertNotIn("Predicted by:", rendered)

    def test_render_prediction_card_with_user_display_names(self):
        """Tag should show user display names when available."""
        from hooptipp.predictions.models import UserPreferences
        
        # Create user with nickname
        user_with_nickname = self.User.objects.create_user(username="nickname_user")
        UserPreferences.objects.create(
            user=user_with_nickname,
            nickname="Cool User"
        )
        
        # Create user tip
        UserTip.objects.create(
            user=user_with_nickname,
            tip_type=self.tip_type,
            prediction_event=self.event,
            prediction_option=self.prediction_option1,
            selected_option=self.option1,
            prediction="Option 1",
        )

        # Manually set display name like the view does
        user_with_nickname.display_name = "Cool User"

        # Create event_tip_users mapping
        event_tip_users = {
            self.event.id: [user_with_nickname]
        }

        template = Template(
            "{% load prediction_extras %}"
            "{% render_prediction_card event %}"
        )
        context = Context({
            "event": self.event,
            "active_user": self.user,
            "event_tip_users": event_tip_users,
        })

        rendered = template.render(context)

        # Should contain the nickname
        self.assertIn("Cool User", rendered)
        # Should not contain the username
        self.assertNotIn("nickname_user", rendered)


class RenderResultCardTemplateTagTests(TestCase):
    """Tests for {% render_result_card %} template tag."""

    def setUp(self):
        self.factory = RequestFactory()
        self.User = get_user_model()
        self.user = self.User.objects.create_user(username="testuser")

        self.tip_type = TipType.objects.create(
            name="Test",
            slug="test",
            deadline=timezone.now(),
        )
        self.category = OptionCategory.objects.create(slug="test", name="Test")
        self.option1 = Option.objects.create(
            category=self.category,
            slug="option1",
            name="Option 1",
        )
        self.option2 = Option.objects.create(
            category=self.category,
            slug="option2",
            name="Option 2",
        )
        self.event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name="Test Event",
            opens_at=timezone.now() - timedelta(days=2),
            deadline=timezone.now() - timedelta(hours=1),
        )
        self.prediction_option1 = PredictionOption.objects.create(
            event=self.event,
            label="Option 1",
            option=self.option1,
        )
        self.prediction_option2 = PredictionOption.objects.create(
            event=self.event,
            label="Option 2",
            option=self.option2,
        )
        self.outcome = EventOutcome.objects.create(
            prediction_event=self.event,
            winning_option=self.prediction_option1,
            winning_generic_option=self.option1,
        )

    def test_render_result_card_basic(self):
        """Tag should render result card with outcome."""
        template = Template(
            "{% load prediction_extras %}"
            "{% render_result_card outcome %}"
        )
        context = Context({
            "outcome": self.outcome,
            "active_user": self.user,
        })

        rendered = template.render(context)

        # Should contain event name
        self.assertIn("Test Event", rendered)
        # Should contain winning option
        self.assertIn("Option 1", rendered)
        # Should contain "Winning outcome" label
        self.assertIn("Winning outcome", rendered)

    def test_render_result_card_with_correct_prediction(self):
        """Tag should show correct prediction indicator."""
        user_tip = UserTip.objects.create(
            user=self.user,
            tip_type=self.tip_type,
            prediction_event=self.event,
            prediction_option=self.prediction_option1,  # Correct option
            selected_option=self.option1,
            prediction="Option 1",
        )

        template = Template(
            "{% load prediction_extras %}"
            "{% render_result_card outcome user_tip True %}"
        )
        context = Context({
            "outcome": self.outcome,
            "user_tip": user_tip,
            "active_user": self.user,
        })

        rendered = template.render(context)

        # Should indicate correct prediction
        self.assertIn("Correct", rendered)
        # Should have green styling
        self.assertIn("green", rendered.lower())

    def test_render_result_card_with_incorrect_prediction(self):
        """Tag should show incorrect prediction indicator."""
        user_tip = UserTip.objects.create(
            user=self.user,
            tip_type=self.tip_type,
            prediction_event=self.event,
            prediction_option=self.prediction_option2,  # Incorrect option
            selected_option=self.option2,
            prediction="Option 2",
        )

        template = Template(
            "{% load prediction_extras %}"
            "{% render_result_card outcome user_tip False %}"
        )
        context = Context({
            "outcome": self.outcome,
            "user_tip": user_tip,
            "active_user": self.user,
        })

        rendered = template.render(context)

        # Should indicate incorrect prediction
        self.assertIn("Incorrect", rendered)
        # Should have red styling
        self.assertIn("red", rendered.lower())

    def test_render_result_card_without_user_tip(self):
        """Tag should render without user tip."""
        template = Template(
            "{% load prediction_extras %}"
            "{% render_result_card outcome %}"
        )
        context = Context({
            "outcome": self.outcome,
            "active_user": self.user,
        })

        rendered = template.render(context)

        # Should contain event name
        self.assertIn("Test Event", rendered)
        # Should not have user prediction section
        self.assertNotIn("Your prediction", rendered)

    def test_render_result_card_uses_custom_renderer(self):
        """Tag should use custom renderer for result template."""

        class TestResultRenderer(CardRenderer):
            def can_render(self, event) -> bool:
                return event.source_id == "test-result-source"

            def get_event_template(self, event) -> str:
                return "predictions/cards/default.html"

            def get_result_template(self, outcome) -> str:
                # Could be a different template for results
                return "predictions/cards/default.html"

            def get_result_context(self, outcome, user=None) -> dict:
                return {"custom_result_data": "result_value"}

        registry = CardRendererRegistry()
        registry.register(TestResultRenderer())

        # Create event with matching source_id
        event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name="Custom Result Event",
            source_id="test-result-source",
            opens_at=timezone.now() - timedelta(days=2),
            deadline=timezone.now() - timedelta(hours=1),
        )
        pred_option = PredictionOption.objects.create(
            event=event,
            label="Option",
            option=self.option1,
        )
        outcome = EventOutcome.objects.create(
            prediction_event=event,
            winning_option=pred_option,
        )

        with mock.patch("hooptipp.predictions.templatetags.prediction_extras.registry", registry):
            template = Template(
                "{% load prediction_extras %}"
                "{% render_result_card outcome %}"
            )
            context = Context({
                "outcome": outcome,
                "active_user": self.user,
            })

            rendered = template.render(context)

            # Should contain event name
            self.assertIn("Custom Result Event", rendered)

    def test_render_result_card_with_recent_outcome(self):
        """Tag should add thicker border for outcomes resolved in the last 24 hours."""
        now = timezone.now()
        
        # Update existing outcome to be resolved 12 hours ago (within 24 hours)
        self.outcome.resolved_at = now - timedelta(hours=12)
        self.outcome.save(update_fields=['resolved_at'])

        template = Template(
            "{% load prediction_extras %}"
            "{% render_result_card outcome %}"
        )
        context = Context({
            "outcome": self.outcome,
            "active_user": self.user,
        })

        rendered = template.render(context)

        # Should have border-2 class for recent outcome
        self.assertIn("border-2", rendered)

    def test_render_result_card_with_old_outcome(self):
        """Tag should use default border for outcomes resolved more than 24 hours ago."""
        now = timezone.now()
        
        # Update existing outcome to be resolved 2 days ago (outside 24 hours)
        self.outcome.resolved_at = now - timedelta(days=2)
        self.outcome.save(update_fields=['resolved_at'])

        template = Template(
            "{% load prediction_extras %}"
            "{% render_result_card outcome %}"
        )
        context = Context({
            "outcome": self.outcome,
            "active_user": self.user,
        })

        rendered = template.render(context)

        # Should have default border class (not border-2)
        # The template uses conditional: {% if is_recent %}border-2{% else %}border{% endif %}
        # So we check that border-2 is NOT present for old outcomes
        self.assertNotIn("border-2", rendered)


class GetItemFilterTests(TestCase):
    """Tests for the get_item filter."""

    def test_get_item_with_dict(self):
        """Filter should get item from dictionary."""
        template = Template(
            "{% load prediction_extras %}"
            "{{ mapping|get_item:key }}"
        )
        context = Context({
            "mapping": {"a": 1, "b": 2, "c": 3},
            "key": "b",
        })

        rendered = template.render(context).strip()
        self.assertEqual(rendered, "2")

    def test_get_item_with_none(self):
        """Filter should return None for None mapping."""
        template = Template(
            "{% load prediction_extras %}"
            "{{ mapping|get_item:key }}"
        )
        context = Context({
            "mapping": None,
            "key": "b",
        })

        rendered = template.render(context).strip()
        self.assertEqual(rendered, "None")

    def test_get_item_missing_key(self):
        """Filter should return None for missing key."""
        template = Template(
            "{% load prediction_extras %}"
            "{{ mapping|get_item:key }}"
        )
        context = Context({
            "mapping": {"a": 1, "b": 2},
            "key": "c",
        })

        rendered = template.render(context).strip()
        self.assertEqual(rendered, "None")
