"""Tests for the new API endpoints for immediate prediction saving."""
import json
from django.contrib.auth import get_user_model
from django.test import TestCase, Client, override_settings
from django.utils import timezone
from datetime import timedelta

from hooptipp.predictions.models import (
    PredictionEvent,
    PredictionOption,
    TipType,
    UserTip,
    Option,
    OptionCategory,
)
from hooptipp.predictions.lock_service import LockService


@override_settings(ENABLE_USER_SELECTION=True)
class SavePredictionAPITests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user_model = get_user_model()
        self.user = self.user_model.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.force_login(self.user)
        
        # Create test data
        self.tip_type = TipType.objects.create(
            name='Game Winner',
            slug='game-winner',
            deadline=timezone.now() + timedelta(days=1)
        )
        self.category = OptionCategory.objects.create(name='Teams')
        self.option = Option.objects.create(
            name='Lakers',
            category=self.category
        )
        
        self.event = PredictionEvent.objects.create(
            name='Test Game',
            tip_type=self.tip_type,
            opens_at=timezone.now() - timedelta(hours=1),
            deadline=timezone.now() + timedelta(hours=1),
            points=10
        )
        
        self.prediction_option = PredictionOption.objects.create(
            event=self.event,
            option=self.option,
            label='Lakers Win'
        )
        
        # Set active user in session
        session = self.client.session
        session['active_user_id'] = self.user.id
        session.save()

    def test_save_prediction_success(self):
        """Test successful prediction saving."""
        response = self.client.post(
            '/api/save-prediction/',
            data=json.dumps({
                'event_id': self.event.id,
                'option_id': self.prediction_option.id
            }),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['message'], 'Prediction saved successfully')
        
        # Check that tip was created
        tip = UserTip.objects.get(user=self.user, prediction_event=self.event)
        self.assertEqual(tip.prediction_option, self.prediction_option)
        self.assertEqual(tip.selected_option, self.option)
        self.assertEqual(tip.prediction, 'Lakers Win')

    def test_save_prediction_update_existing(self):
        """Test updating an existing prediction."""
        # Create existing tip
        existing_tip = UserTip.objects.create(
            user=self.user,
            prediction_event=self.event,
            tip_type=self.tip_type,
            prediction='Old Prediction',
            prediction_option=self.prediction_option,
            selected_option=self.option
        )
        
        response = self.client.post(
            '/api/save-prediction/',
            data=json.dumps({
                'event_id': self.event.id,
                'option_id': self.prediction_option.id
            }),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertFalse(data['created'])  # Should be update, not create
        
        # Check that tip was updated
        tip = UserTip.objects.get(id=existing_tip.id)
        self.assertEqual(tip.prediction, 'Lakers Win')

    def test_save_prediction_no_active_user(self):
        """Test saving prediction without active user."""
        # Clear active user
        session = self.client.session
        session.pop('active_user_id', None)
        session.save()
        
        response = self.client.post(
            '/api/save-prediction/',
            data=json.dumps({
                'event_id': self.event.id,
                'option_id': self.prediction_option.id
            }),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data['error'], 'No active user')

    def test_save_prediction_deadline_passed(self):
        """Test saving prediction after deadline."""
        # Set deadline in the past
        self.event.deadline = timezone.now() - timedelta(hours=1)
        self.event.save()
        
        response = self.client.post(
            '/api/save-prediction/',
            data=json.dumps({
                'event_id': self.event.id,
                'option_id': self.prediction_option.id
            }),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data['error'], 'Event deadline has passed')

    def test_save_prediction_missing_data(self):
        """Test saving prediction with missing data."""
        response = self.client.post(
            '/api/save-prediction/',
            data=json.dumps({
                'event_id': self.event.id
                # Missing option_id
            }),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data['error'], 'Missing event_id or option_id')

    def test_save_prediction_with_session_activation(self):
        """Test saving prediction with session-based activation (no traditional login)."""
        # Logout the user to simulate no traditional authentication
        self.client.logout()
        
        # Set active user in session (simulating PIN activation)
        session = self.client.session
        session['active_user_id'] = self.user.id
        session.save()
        
        response = self.client.post(
            '/api/save-prediction/',
            data=json.dumps({
                'event_id': self.event.id,
                'option_id': self.prediction_option.id
            }),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertTrue(data['created'])
        
        # Check that tip was created
        tip = UserTip.objects.get(user=self.user, prediction_event=self.event)
        self.assertEqual(tip.prediction, 'Lakers Win')

    def test_save_prediction_no_authentication_no_session(self):
        """Test saving prediction with no authentication and no session."""
        # Logout the user and clear session
        # In user selection mode, this should behave the same as no active user
        self.client.logout()
        session = self.client.session
        session.pop('active_user_id', None)
        session.save()
        
        response = self.client.post(
            '/api/save-prediction/',
            data=json.dumps({
                'event_id': self.event.id,
                'option_id': self.prediction_option.id
            }),
            content_type='application/json'
        )
        
        # In user selection mode, authentication status doesn't matter
        # Only session-based active user matters, so expect 400 not 401
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data['error'], 'No active user')


class ToggleLockAPITests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user_model = get_user_model()
        self.user = self.user_model.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.force_login(self.user)
        
        # Create test data
        self.tip_type = TipType.objects.create(
            name='Game Winner',
            slug='game-winner',
            deadline=timezone.now() + timedelta(days=1)
        )
        self.category = OptionCategory.objects.create(name='Teams')
        self.option = Option.objects.create(
            name='Lakers',
            category=self.category
        )
        
        self.event = PredictionEvent.objects.create(
            name='Test Game',
            tip_type=self.tip_type,
            opens_at=timezone.now() - timedelta(hours=1),
            deadline=timezone.now() + timedelta(hours=1),
            points=10
        )
        
        self.prediction_option = PredictionOption.objects.create(
            event=self.event,
            option=self.option,
            label='Lakers Win'
        )
        
        # Create a tip
        self.tip = UserTip.objects.create(
            user=self.user,
            prediction_event=self.event,
            tip_type=self.tip_type,
            prediction='Lakers Win',
            prediction_option=self.prediction_option,
            selected_option=self.option
        )
        
        # Set active user in session
        session = self.client.session
        session['active_user_id'] = self.user.id
        session.save()

    def test_toggle_lock_success(self):
        """Test successful lock toggle."""
        response = self.client.post(
            '/api/toggle-lock/',
            data=json.dumps({
                'event_id': self.event.id,
                'should_lock': True
            }),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['message'], 'Prediction locked successfully')
        self.assertTrue(data['is_locked'])
        self.assertIn('lock_summary', data)
        
        # Check that tip is locked
        self.tip.refresh_from_db()
        self.assertTrue(self.tip.is_locked)

    def test_toggle_lock_limit_exceeded(self):
        """Test lock toggle when limit is exceeded."""
        # Use up all locks
        lock_service = LockService(self.user)
        for i in range(3):  # LOCK_LIMIT is 3
            event = PredictionEvent.objects.create(
                name=f'Test Game {i}',
                tip_type=self.tip_type,
                opens_at=timezone.now() - timedelta(hours=1),
                deadline=timezone.now() + timedelta(hours=1),
                points=10
            )
            option = PredictionOption.objects.create(
                event=event,
                option=self.option,
                label=f'Lakers Win {i}'
            )
            tip = UserTip.objects.create(
                user=self.user,
                prediction_event=event,
                tip_type=self.tip_type,
                prediction=f'Lakers Win {i}',
                prediction_option=option,
                selected_option=self.option
            )
            lock_service.ensure_locked(tip)
        
        # Try to lock one more
        response = self.client.post(
            '/api/toggle-lock/',
            data=json.dumps({
                'event_id': self.event.id,
                'should_lock': True
            }),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data['error'], 'No locks available')
        self.assertIn('lock_summary', data)

    def test_toggle_unlock_success(self):
        """Test successful unlock."""
        # First lock the tip
        lock_service = LockService(self.user)
        lock_service.ensure_locked(self.tip)
        
        # Then unlock it
        response = self.client.post(
            '/api/toggle-lock/',
            data=json.dumps({
                'event_id': self.event.id,
                'should_lock': False
            }),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['message'], 'Prediction unlocked successfully')
        self.assertFalse(data['is_locked'])
        
        # Check that tip is unlocked
        self.tip.refresh_from_db()
        self.assertFalse(self.tip.is_locked)

    def test_toggle_lock_deadline_passed(self):
        """Test lock toggle after deadline."""
        # Set deadline in the past
        self.event.deadline = timezone.now() - timedelta(hours=1)
        self.event.save()
        
        response = self.client.post(
            '/api/toggle-lock/',
            data=json.dumps({
                'event_id': self.event.id,
                'should_lock': True
            }),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data['error'], 'Event deadline has passed')

    def test_toggle_lock_no_prediction(self):
        """Test lock toggle when no prediction exists."""
        # Delete the existing tip
        self.tip.delete()
        
        response = self.client.post(
            '/api/toggle-lock/',
            data=json.dumps({
                'event_id': self.event.id,
                'should_lock': True
            }),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data['error'], 'No prediction found. Please make a prediction first before locking.')
        self.assertIn('lock_summary', data)


@override_settings(ENABLE_USER_SELECTION=True)
class GetLockSummaryAPITests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user_model = get_user_model()
        self.user = self.user_model.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.force_login(self.user)
        
        # Set active user in session
        session = self.client.session
        session['active_user_id'] = self.user.id
        session.save()

    def test_get_lock_summary_success(self):
        """Test successful lock summary retrieval."""
        response = self.client.get('/api/lock-summary/')
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('available', data)
        self.assertIn('active', data)
        self.assertIn('total', data)
        self.assertIn('pending', data)
        self.assertEqual(data['total'], 3)  # LOCK_LIMIT
        self.assertEqual(data['available'], 3)  # All locks available initially

    def test_get_lock_summary_no_active_user(self):
        """Test lock summary without active user."""
        # Clear active user
        session = self.client.session
        session.pop('active_user_id', None)
        session.save()
        
        response = self.client.get('/api/lock-summary/')
        
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data['error'], 'No active user')
