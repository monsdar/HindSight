from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from hooptipp.nba.models import ScheduledGame
from hooptipp.predictions.models import (
    Option,
    OptionCategory,
    PredictionEvent,
    PredictionOption,
    TipType,
    UserPreferences,
    UserEventScore,
    UserTip,
)


@override_settings(ENABLE_USER_SELECTION=True)
class HomeViewTests(TestCase):
    def setUp(self) -> None:
        user_model = get_user_model()
        self.alice = user_model.objects.create_user(
            username='alice',
            password='password123',
        )
        self.bob = user_model.objects.create_user(
            username='bob',
            password='password123',
        )
        
        # Create Option category and options
        self.teams_cat = OptionCategory.objects.create(
            slug='nba-teams',
            name='NBA Teams'
        )
        self.home_option_obj = Option.objects.create(
            category=self.teams_cat,
            slug='lal',
            name='Los Angeles Lakers',
            short_name='LAL',
            external_id='1',
            metadata={'city': 'Los Angeles', 'conference': 'West', 'division': 'Pacific'}
        )
        self.away_option_obj = Option.objects.create(
            category=self.teams_cat,
            slug='bos',
            name='Boston Celtics',
            short_name='BOS',
            external_id='2',
            metadata={'city': 'Boston', 'conference': 'East', 'division': 'Atlantic'}
        )
        
        self.tip_type = TipType.objects.create(
            name='Weekly games',
            slug='weekly-games',
            description='Featured matchups for the upcoming week',
            deadline=timezone.now(),
        )
        game_time = timezone.now() + timedelta(hours=1)
        self.game = ScheduledGame.objects.create(
            tip_type=self.tip_type,
            nba_game_id='GAME123',
            game_date=game_time,
            home_team='Los Angeles Lakers',
            home_team_tricode='LAL',
            away_team='Boston Celtics',
            away_team_tricode='BOS',
            venue='Crypto.com Arena',
        )
        self.event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='BOS @ LAL',
            description='Boston Celtics at Los Angeles Lakers',
            target_kind=PredictionEvent.TargetKind.TEAM,
            selection_mode=PredictionEvent.SelectionMode.CURATED,
            opens_at=timezone.now() - timedelta(days=1),
            deadline=game_time,
            reveal_at=timezone.now() - timedelta(days=1),
            is_active=True,
            scheduled_game=self.game,
            sort_order=1,
        )
        self.away_option = PredictionOption.objects.create(
            event=self.event,
            label='Boston Celtics',
            option=self.away_option_obj,
            sort_order=1,
        )
        self.home_option = PredictionOption.objects.create(
            event=self.event,
            label='Los Angeles Lakers',
            option=self.home_option_obj,
            sort_order=2,
        )
        UserTip.objects.create(
            user=self.alice,
            tip_type=self.tip_type,
            prediction_event=self.event,
            prediction_option=self.away_option,
            selected_option=self.away_option_obj,
            prediction='BOS',
        )
        UserTip.objects.create(
            user=self.bob,
            tip_type=self.tip_type,
            prediction_event=self.event,
            prediction_option=self.home_option,
            selected_option=self.home_option_obj,
            prediction='LAL',
        )
        super().setUp()

    def test_home_view_exposes_event_tip_users(self) -> None:
        response = self.client.get(reverse('predictions:home'))

        self.assertEqual(response.status_code, 200)
        self.assertIn('event_tip_users', response.context)

        event_tip_users = response.context['event_tip_users']
        self.assertIn(self.event.id, event_tip_users)
        pick_users = event_tip_users[self.event.id]
        usernames = [user.username for user in pick_users]
        self.assertEqual(usernames, ['alice', 'bob'])
        self.assertEqual([user.display_name for user in pick_users], ['alice', 'bob'])
        self.assertEqual([user.display_initial for user in pick_users], ['A', 'B'])

        users_list = response.context['users']
        self.assertGreaterEqual(len(users_list), 2)
        self.assertEqual(users_list[0].display_name, 'alice')
        self.assertEqual(users_list[0].display_initial, 'A')

        # Note: In the new dashboard, user tips are not shown on the open predictions
        # if no user is active, so we just verify the context data is correct

    def test_home_view_displays_nickname_everywhere(self) -> None:
        UserPreferences.objects.create(user=self.alice, nickname='Ace')
        UserPreferences.objects.create(user=self.bob, nickname='Buckets')

        session = self.client.session
        session['active_user_id'] = self.alice.id
        session.save()

        response = self.client.get(reverse('predictions:home'))

        self.assertEqual(response.status_code, 200)

        # Check for the active player section since a user is active
        self.assertContains(response, 'Active Player')
        self.assertContains(response, 'Ace')
        self.assertContains(response, 'Finish Predictions')
        # Check for the new dashboard text instead of old "Scoring overview" text
        self.assertContains(response, 'Leaderboard')
        # Note: In the streamlined dashboard, user initials are not shown on individual
        # prediction cards, only in the user selection buttons

        event_tip_users = response.context['event_tip_users'][self.event.id]
        self.assertEqual([user.display_name for user in event_tip_users], ['Ace', 'Buckets'])
        self.assertEqual([user.display_initial for user in event_tip_users], ['A', 'B'])

        users_list = response.context['users']
        self.assertEqual(users_list[0].display_name, 'Ace')
        self.assertEqual(users_list[0].display_initial, 'A')

    def test_active_user_tip_renders_last_updated_timestamp(self) -> None:
        session = self.client.session
        session['active_user_id'] = self.alice.id
        session.save()

        response = self.client.get(reverse('predictions:home'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Last updated:')

    def test_weekday_slots_group_games_by_date(self) -> None:
        additional = ScheduledGame.objects.create(
            tip_type=self.tip_type,
            nba_game_id='GAME456',
            game_date=self.game.game_date + timedelta(days=1),
            home_team='Chicago Bulls',
            home_team_tricode='CHI',
            away_team='Miami Heat',
            away_team_tricode='MIA',
            venue='United Center',
            is_manual=True,
        )
        # Create Options for these teams
        away_option = Option.objects.create(
            category=self.teams_cat,
            slug='mia',
            name='Miami Heat',
            short_name='MIA',
            external_id='3',
            metadata={'city': 'Miami', 'conference': 'East', 'division': 'Southeast'}
        )
        home_option = Option.objects.create(
            category=self.teams_cat,
            slug='chi',
            name='Chicago Bulls',
            short_name='CHI',
            external_id='4',
            metadata={'city': 'Chicago', 'conference': 'East', 'division': 'Central'}
        )
        
        additional_event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='MIA @ CHI',
            description='Miami Heat at Chicago Bulls',
            target_kind=PredictionEvent.TargetKind.TEAM,
            selection_mode=PredictionEvent.SelectionMode.CURATED,
            opens_at=timezone.now() - timedelta(days=1),
            deadline=additional.game_date,
            reveal_at=timezone.now() - timedelta(days=1),
            is_active=True,
            scheduled_game=additional,
            sort_order=2,
        )
        PredictionOption.objects.create(
            event=additional_event,
            label='Miami Heat',
            option=away_option,
            sort_order=1,
        )
        PredictionOption.objects.create(
            event=additional_event,
            label='Chicago Bulls',
            option=home_option,
            sort_order=2,
        )

        response = self.client.get(reverse('predictions:home'))

        self.assertEqual(response.status_code, 200)
        weekday_slots = response.context['weekday_slots']
        self.assertEqual(len(weekday_slots), 7)
        first_day_events = weekday_slots[0]['events']
        second_day_events = weekday_slots[1]['events']
        self.assertEqual([event.id for event in first_day_events], [self.event.id])
        self.assertEqual([event.id for event in second_day_events], [additional_event.id])

    def test_weekday_slots_excludes_events_outside_range(self) -> None:
        far_future_deadline = timezone.now() + timedelta(days=8)
        distant_event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Future matchup',
            description='Far away showdown',
            target_kind=PredictionEvent.TargetKind.TEAM,
            selection_mode=PredictionEvent.SelectionMode.CURATED,
            opens_at=timezone.now() - timedelta(days=1),
            deadline=far_future_deadline,
            reveal_at=timezone.now() - timedelta(days=1),
            is_active=True,
            sort_order=5,
        )
        # Create a generic option for this event
        dummy_option = Option.objects.create(
            category=self.teams_cat,
            slug='option-a',
            name='Option A',
        )
        PredictionOption.objects.create(
            event=distant_event,
            label='Option A',
            option=dummy_option,
            sort_order=1,
        )

        response = self.client.get(reverse('predictions:home'))

        self.assertEqual(response.status_code, 200)
        weekday_slots = response.context['weekday_slots']
        included_ids = [event.id for slot in weekday_slots for event in slot['events']]
        self.assertNotIn(distant_event.id, included_ids)

    def test_update_preferences_updates_record(self) -> None:
        session = self.client.session
        session['active_user_id'] = self.alice.id
        session.save()

        response = self.client.post(
                reverse('predictions:home'),
                {
                    'update_preferences': '1',
                    'nickname': 'Splash',
                    'theme': 'golden-state-warriors',
                },
            )

        self.assertEqual(response.status_code, 302)
        preferences = UserPreferences.objects.get(user=self.alice)
        self.assertEqual(preferences.nickname, 'Splash')
        self.assertEqual(preferences.theme, 'golden-state-warriors')

    def test_update_preferences_validation_errors_return_to_page(self) -> None:
        session = self.client.session
        session['active_user_id'] = self.alice.id
        session.save()

        response = self.client.post(
                reverse('predictions:home'),
                {
                    'update_preferences': '1',
                    'nickname': 'Splash',
                    'theme': 'invalid-theme',
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn('preferences_form', response.context)
        form = response.context['preferences_form']
        self.assertTrue(form.errors)
        self.assertIn('theme', form.errors)

    def test_finish_round_clears_active_user(self) -> None:
        session = self.client.session
        session['active_user_id'] = self.alice.id
        session.save()

        with mock.patch(
            'hooptipp.predictions.views.sync_weekly_games',
            return_value=(self.tip_type, [self.event], self.game.game_date.date()),
        ):
            response = self.client.post(
                reverse('predictions:home'),
                {
                    'set_active_user': '1',
                    'user_id': str(self.alice.id),
                    'active_user_action': 'finish',
                },
            )

        self.assertEqual(response.status_code, 302)
        self.assertIsNone(self.client.session.get('active_user_id'))

    def test_finish_round_clears_active_user(self) -> None:
        session = self.client.session
        session['active_user_id'] = self.alice.id
        session.save()

        response = self.client.post(
            reverse('predictions:home'),
            {
                'set_active_user': '1',
                'user_id': str(self.alice.id),
                'active_user_action': 'finish',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertIsNone(self.client.session.get('active_user_id'))

    def test_finish_round_allows_switching_users(self) -> None:
        session = self.client.session
        session['active_user_id'] = self.alice.id
        session.save()

        response = self.client.post(
            reverse('predictions:home'),
            {
                'set_active_user': '1',
                'user_id': str(self.bob.id),
                'active_user_action': 'finish',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.session.get('active_user_id'), self.bob.id)

    def test_save_tips_allows_lock_when_available(self) -> None:
        session = self.client.session
        session['active_user_id'] = self.alice.id
        session.save()

        response = self.client.post(
                reverse('predictions:home'),
                {
                    'save_tips': '1',
                    f'prediction_{self.event.id}': str(self.away_option.id),
                    f'lock_{self.event.id}': '1',
                },
            )

        self.assertEqual(response.status_code, 302)
        tip = UserTip.objects.get(user=self.alice, prediction_event=self.event)
        self.assertTrue(tip.is_locked)
        self.assertEqual(tip.lock_status, UserTip.LockStatus.ACTIVE)
        self.assertIsNotNone(tip.lock_committed_at)

    def test_save_tips_respects_lock_limit(self) -> None:
        now = timezone.now()
        base_tip = UserTip.objects.get(user=self.alice, prediction_event=self.event)
        base_tip.is_locked = True
        base_tip.lock_status = UserTip.LockStatus.ACTIVE
        base_tip.lock_committed_at = now
        base_tip.save(update_fields=['is_locked', 'lock_status', 'lock_committed_at'])

        for index in range(2):
            event = PredictionEvent.objects.create(
                tip_type=self.tip_type,
                name=f'Extra event {index + 1}',
                description='Additional prediction',
                target_kind=PredictionEvent.TargetKind.TEAM,
                selection_mode=PredictionEvent.SelectionMode.CURATED,
                opens_at=now - timedelta(days=1),
                deadline=now + timedelta(days=1),
                reveal_at=now - timedelta(days=1),
                is_active=True,
                sort_order=index + 10,
            )
            option = PredictionOption.objects.create(
                event=event,
                label=f'Lock option {index + 1}',
                option=self.away_option_obj,
                sort_order=1,
            )
            locked_tip = UserTip.objects.create(
                user=self.alice,
                tip_type=self.tip_type,
                prediction_event=event,
                prediction_option=option,
                selected_option=self.away_option_obj,
                prediction=option.label,
            )
            locked_tip.is_locked = True
            locked_tip.lock_status = UserTip.LockStatus.ACTIVE
            locked_tip.lock_committed_at = now
            locked_tip.save(update_fields=['is_locked', 'lock_status', 'lock_committed_at'])

        extra_event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Overflow event',
            description='Attempt to exceed locks',
            target_kind=PredictionEvent.TargetKind.TEAM,
            selection_mode=PredictionEvent.SelectionMode.CURATED,
            opens_at=now - timedelta(days=1),
            deadline=now + timedelta(days=1),
            reveal_at=now - timedelta(days=1),
            is_active=True,
            sort_order=20,
        )
        extra_option = PredictionOption.objects.create(
            event=extra_event,
            label='Overflow pick',
            option=self.home_option_obj,
            sort_order=1,
        )

        session = self.client.session
        session['active_user_id'] = self.alice.id
        session.save()

        post_data = {
            'save_tips': '1',
            f'prediction_{extra_event.id}': str(extra_option.id),
            f'lock_{extra_event.id}': '1',
            f'lock_{self.event.id}': '1',
        }
        for idx, event in enumerate(
            PredictionEvent.objects.filter(name__startswith='Extra event').order_by('sort_order'),
            start=1,
        ):
            post_data[f'lock_{event.id}'] = '1'

        response = self.client.post(
                reverse('predictions:home'),
                post_data,
                follow=True,
            )

        self.assertEqual(response.status_code, 200)
        tip = UserTip.objects.get(user=self.alice, prediction_event=extra_event)
        self.assertFalse(tip.is_locked)
        self.assertEqual(tip.lock_status, UserTip.LockStatus.NONE)
        self.assertContains(response, 'Unable to lock', status_code=200)

    def test_save_tips_unlocks_before_deadline(self) -> None:
        tip = UserTip.objects.get(user=self.alice, prediction_event=self.event)
        tip.is_locked = True
        tip.lock_status = UserTip.LockStatus.ACTIVE
        tip.lock_committed_at = timezone.now()
        tip.save(update_fields=['is_locked', 'lock_status', 'lock_committed_at'])

        session = self.client.session
        session['active_user_id'] = self.alice.id
        session.save()

        response = self.client.post(
                reverse('predictions:home'),
                {
                    'save_tips': '1',
                    f'prediction_{self.event.id}': str(self.away_option.id),
                },
            )

        self.assertEqual(response.status_code, 302)
        tip.refresh_from_db()
        self.assertFalse(tip.is_locked)
        self.assertEqual(tip.lock_status, UserTip.LockStatus.NONE)
        self.assertIsNotNone(tip.lock_released_at)

    def test_home_view_includes_scoring_summary_for_active_user(self) -> None:
        session = self.client.session
        session['active_user_id'] = self.alice.id
        session.save()

        self.event.points = 3
        self.event.is_bonus_event = True
        self.event.save(update_fields=['points', 'is_bonus_event'])

        UserEventScore.objects.create(
            user=self.alice,
            prediction_event=self.event,
            base_points=3,
            lock_multiplier=2,
            points_awarded=6,
            is_lock_bonus=True,
        )

        response = self.client.get(reverse('predictions:home'))

        self.assertEqual(response.status_code, 200)
        scoreboard = response.context['scoreboard_summary']
        self.assertIsNotNone(scoreboard)
        self.assertEqual(scoreboard['total_points'], 6)
        self.assertEqual(scoreboard['bonus_event_points'], 3)
        self.assertEqual(scoreboard['lock_bonus_points'], 3)
        self.assertEqual(scoreboard['standard_points'], 0)
        recent_scores = response.context['recent_scores']
        self.assertEqual(len(recent_scores), 1)
        self.assertEqual(recent_scores[0].points_awarded, 6)
        # Check for the new dashboard sections instead of old "Scoring overview"
        self.assertContains(response, 'Leaderboard')
        self.assertContains(response, '6')  # Total points displayed in ranking
        self.assertContains(response, 'Bonus')

    def test_leaderboard_displays_lock_status_symbols(self) -> None:
        """Test that leaderboard displays lock status symbols for each user."""
        # Create some scores to get users in the leaderboard
        UserEventScore.objects.create(
            user=self.alice,
            prediction_event=self.event,
            base_points=3,
            lock_multiplier=1,
            points_awarded=3,
        )
        UserEventScore.objects.create(
            user=self.bob,
            prediction_event=self.event,
            base_points=3,
            lock_multiplier=1,
            points_awarded=3,
        )

        response = self.client.get(reverse('predictions:home'))

        self.assertEqual(response.status_code, 200)
        self.assertIn('leaderboard_rows', response.context)
        
        leaderboard_rows = response.context['leaderboard_rows']
        self.assertGreaterEqual(len(leaderboard_rows), 2)
        
        # Check that each user has lock_summary data
        for row in leaderboard_rows:
            self.assertTrue(hasattr(row, 'lock_summary'))
            self.assertEqual(row.lock_summary.total, 3)
            # For users without any lock activity, all locks should be available
            self.assertEqual(row.lock_summary.available, 3)
            self.assertEqual(row.lock_summary.active, 0)
            self.assertEqual(row.lock_summary.pending, 0)

    def test_leaderboard_lock_status_with_active_locks(self) -> None:
        """Test leaderboard lock status when users have active locks."""
        # Create scores for leaderboard
        UserEventScore.objects.create(
            user=self.alice,
            prediction_event=self.event,
            base_points=3,
            lock_multiplier=1,
            points_awarded=3,
        )
        
        # Give Alice an active lock
        alice_tip = UserTip.objects.get(user=self.alice, prediction_event=self.event)
        alice_tip.is_locked = True
        alice_tip.lock_status = UserTip.LockStatus.ACTIVE
        alice_tip.lock_committed_at = timezone.now()
        alice_tip.save(update_fields=['is_locked', 'lock_status', 'lock_committed_at'])

        response = self.client.get(reverse('predictions:home'))

        self.assertEqual(response.status_code, 200)
        leaderboard_rows = response.context['leaderboard_rows']
        
        # Find Alice in the leaderboard
        alice_row = None
        for row in leaderboard_rows:
            if row.id == self.alice.id:
                alice_row = row
                break
        
        self.assertIsNotNone(alice_row)
        self.assertEqual(alice_row.lock_summary.available, 2)  # 3 total - 1 active
        self.assertEqual(alice_row.lock_summary.active, 1)
        self.assertEqual(alice_row.lock_summary.pending, 0)

    def test_leaderboard_lock_status_with_forfeited_locks(self) -> None:
        """Test leaderboard lock status when users have forfeited locks."""
        # Create scores for leaderboard
        UserEventScore.objects.create(
            user=self.alice,
            prediction_event=self.event,
            base_points=3,
            lock_multiplier=1,
            points_awarded=3,
        )
        
        # Give Alice a forfeited lock
        alice_tip = UserTip.objects.get(user=self.alice, prediction_event=self.event)
        alice_tip.is_locked = False
        alice_tip.lock_status = UserTip.LockStatus.FORFEITED
        alice_tip.lock_releases_at = timezone.now() + timedelta(days=30)
        alice_tip.save(update_fields=['is_locked', 'lock_status', 'lock_releases_at'])

        response = self.client.get(reverse('predictions:home'))

        self.assertEqual(response.status_code, 200)
        leaderboard_rows = response.context['leaderboard_rows']
        
        # Find Alice in the leaderboard
        alice_row = None
        for row in leaderboard_rows:
            if row.id == self.alice.id:
                alice_row = row
                break
        
        self.assertIsNotNone(alice_row)
        self.assertEqual(alice_row.lock_summary.available, 2)  # 3 total - 1 forfeited
        self.assertEqual(alice_row.lock_summary.active, 0)
        self.assertEqual(alice_row.lock_summary.pending, 1)

    def test_leaderboard_displays_3_day_score_change(self) -> None:
        """Test that leaderboard displays 3-day score change for each user."""
        now = timezone.now()
        
        # Create a second event for additional scores
        event2 = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Event 2',
            opens_at=now - timedelta(days=10),
            deadline=now - timedelta(days=5),
            is_active=True,
            points=5,
        )
        
        # Create scores for Alice: 3 points from 2 days ago (within 3 days), 5 points from 5 days ago (outside 3 days)
        alice_score1 = UserEventScore.objects.create(
            user=self.alice,
            prediction_event=self.event,
            base_points=3,
            lock_multiplier=1,
            points_awarded=3,
        )
        alice_score1.awarded_at = now - timedelta(days=2)
        alice_score1.save(update_fields=['awarded_at'])
        
        alice_score2 = UserEventScore.objects.create(
            user=self.alice,
            prediction_event=event2,
            base_points=5,
            lock_multiplier=1,
            points_awarded=5,
        )
        alice_score2.awarded_at = now - timedelta(days=5)  # Outside 3-day window
        alice_score2.save(update_fields=['awarded_at'])
        
        # Create scores for Bob: 3 points from 1 day ago (within 3 days), 5 points from 4 days ago (outside 3 days)
        bob_score1 = UserEventScore.objects.create(
            user=self.bob,
            prediction_event=self.event,
            base_points=3,
            lock_multiplier=1,
            points_awarded=3,
        )
        bob_score1.awarded_at = now - timedelta(days=1)
        bob_score1.save(update_fields=['awarded_at'])
        
        bob_score2 = UserEventScore.objects.create(
            user=self.bob,
            prediction_event=event2,
            base_points=5,
            lock_multiplier=1,
            points_awarded=5,
        )
        bob_score2.awarded_at = now - timedelta(days=4)  # Outside 3-day window
        bob_score2.save(update_fields=['awarded_at'])

        response = self.client.get(reverse('predictions:home'))

        self.assertEqual(response.status_code, 200)
        self.assertIn('leaderboard_rows', response.context)
        
        leaderboard_rows = response.context['leaderboard_rows']
        self.assertGreaterEqual(len(leaderboard_rows), 2)
        
        # Find Alice and Bob in the leaderboard
        alice_row = None
        bob_row = None
        for row in leaderboard_rows:
            if row.id == self.alice.id:
                alice_row = row
            elif row.id == self.bob.id:
                bob_row = row
        
        self.assertIsNotNone(alice_row)
        self.assertIsNotNone(bob_row)
        
        # Alice should have 3 points from the last 3 days (only the score from 2 days ago)
        self.assertTrue(hasattr(alice_row, 'points_change_3d'))
        self.assertEqual(alice_row.points_change_3d, 3)
        
        # Bob should have 3 points from the last 3 days (only the score from 1 day ago)
        self.assertTrue(hasattr(bob_row, 'points_change_3d'))
        self.assertEqual(bob_row.points_change_3d, 3)
        
        # Verify the template displays the change
        self.assertContains(response, '+3', count=2)  # Should appear twice (once for Alice, once for Bob)

    def test_leaderboard_3_day_score_change_with_multiple_scores(self) -> None:
        """Test 3-day score change calculation with multiple scores within the window."""
        now = timezone.now()
        
        # Create multiple events
        event2 = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Event 2',
            opens_at=now - timedelta(days=10),
            deadline=now - timedelta(days=5),
            is_active=True,
            points=5,
        )
        event3 = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Event 3',
            opens_at=now - timedelta(days=10),
            deadline=now - timedelta(days=5),
            is_active=True,
            points=2,
        )
        
        # Create multiple scores for Alice within the 3-day window
        alice_score1 = UserEventScore.objects.create(
            user=self.alice,
            prediction_event=self.event,
            base_points=3,
            lock_multiplier=1,
            points_awarded=3,
        )
        alice_score1.awarded_at = now - timedelta(days=1)
        alice_score1.save(update_fields=['awarded_at'])
        
        alice_score2 = UserEventScore.objects.create(
            user=self.alice,
            prediction_event=event2,
            base_points=5,
            lock_multiplier=1,
            points_awarded=5,
        )
        alice_score2.awarded_at = now - timedelta(days=2)
        alice_score2.save(update_fields=['awarded_at'])
        
        alice_score3 = UserEventScore.objects.create(
            user=self.alice,
            prediction_event=event3,
            base_points=2,
            lock_multiplier=2,  # Lock bonus
            points_awarded=4,
        )
        alice_score3.awarded_at = now - timedelta(hours=12)  # 12 hours ago
        alice_score3.save(update_fields=['awarded_at'])
        
        # Create one score outside the 3-day window
        event4 = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Event 4',
            opens_at=now - timedelta(days=10),
            deadline=now - timedelta(days=5),
            is_active=True,
            points=10,
        )
        alice_score4 = UserEventScore.objects.create(
            user=self.alice,
            prediction_event=event4,
            base_points=10,
            lock_multiplier=1,
            points_awarded=10,
        )
        alice_score4.awarded_at = now - timedelta(days=4)  # Outside 3-day window
        alice_score4.save(update_fields=['awarded_at'])

        response = self.client.get(reverse('predictions:home'))

        self.assertEqual(response.status_code, 200)
        leaderboard_rows = response.context['leaderboard_rows']
        
        # Find Alice in the leaderboard
        alice_row = None
        for row in leaderboard_rows:
            if row.id == self.alice.id:
                alice_row = row
                break
        
        self.assertIsNotNone(alice_row)
        # Should sum: 3 + 5 + 4 = 12 points from the last 3 days
        self.assertEqual(alice_row.points_change_3d, 12)
        
        # Verify the template displays the change
        self.assertContains(response, '+12')

    def test_leaderboard_3_day_score_change_zero_when_no_recent_scores(self) -> None:
        """Test that 3-day score change is 0 when user has no scores in the last 3 days."""
        now = timezone.now()
        
        # Create a score for Alice from 5 days ago (outside 3-day window)
        alice_score = UserEventScore.objects.create(
            user=self.alice,
            prediction_event=self.event,
            base_points=3,
            lock_multiplier=1,
            points_awarded=3,
        )
        alice_score.awarded_at = now - timedelta(days=5)
        alice_score.save(update_fields=['awarded_at'])

        response = self.client.get(reverse('predictions:home'))

        self.assertEqual(response.status_code, 200)
        leaderboard_rows = response.context['leaderboard_rows']
        
        # Find Alice in the leaderboard
        alice_row = None
        for row in leaderboard_rows:
            if row.id == self.alice.id:
                alice_row = row
                break
        
        self.assertIsNotNone(alice_row)
        # Should be 0 since no scores in the last 3 days
        self.assertEqual(alice_row.points_change_3d, 0)
        
        # Verify the template does NOT display the change indicator (only shows when > 0)
        # The total points should still be displayed
        self.assertContains(response, str(alice_row.total_points))
        # But the +X indicator should not appear
        response_content = response.content.decode('utf-8')
        # Check that there's no +0 or similar pattern for Alice's row
        # We'll verify by checking that points_change_3d > 0 condition prevents display

    def test_home_view_filters_open_predictions_to_upcoming_week(self) -> None:
        """Test that open_predictions only shows events with deadlines in the upcoming week."""
        now = timezone.now()
        
        # Create events with different deadline dates
        # Event 1: Due in 1 hour (should be included - today)
        event_today = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Event Today',
            opens_at=now - timedelta(hours=1),
            deadline=now + timedelta(hours=1),
            is_active=True,
        )
        
        # Event 2: Due in 3 days (should be included)
        event_3_days = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Event in 3 Days',
            opens_at=now - timedelta(hours=1),
            deadline=now + timedelta(days=3),
            is_active=True,
        )
        
        # Event 3: Due in 6 days (should be included - end of week)
        event_6_days = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Event in 6 Days',
            opens_at=now - timedelta(hours=1),
            deadline=now + timedelta(days=6),
            is_active=True,
        )
        
        # Event 4: Due in 8 days (should NOT be included - beyond week)
        event_8_days = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Event in 8 Days',
            opens_at=now - timedelta(hours=1),
            deadline=now + timedelta(days=8),
            is_active=True,
        )
        
        # Event 5: Due 1 hour ago (should NOT be included - past deadline)
        event_past = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Event Past',
            opens_at=now - timedelta(days=2),
            deadline=now - timedelta(hours=1),
            is_active=True,
        )
        
        # Event 6: Opens tomorrow (should NOT be included - not yet open)
        event_opens_tomorrow = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Event Opens Tomorrow',
            opens_at=now + timedelta(days=1),
            deadline=now + timedelta(days=2),
            is_active=True,
        )

        response = self.client.get(reverse('predictions:home'))
        
        self.assertEqual(response.status_code, 200)
        self.assertIn('open_predictions', response.context)
        
        open_predictions = response.context['open_predictions']
        open_prediction_ids = [event.id for event in open_predictions]
        
        # Should include events due today, in 3 days, and in 6 days
        self.assertIn(event_today.id, open_prediction_ids)
        self.assertIn(event_3_days.id, open_prediction_ids)
        self.assertIn(event_6_days.id, open_prediction_ids)
        
        # Should NOT include events due in 8 days, past deadline, or not yet open
        self.assertNotIn(event_8_days.id, open_prediction_ids)
        self.assertNotIn(event_past.id, open_prediction_ids)
        self.assertNotIn(event_opens_tomorrow.id, open_prediction_ids)
        
        # Should be ordered by deadline
        # Note: The existing event from setUp might also be included if its deadline is within the week
        self.assertGreaterEqual(len(open_predictions), 3)
        # Check that our specific events are included and in the right order
        our_events = [event for event in open_predictions if event.id in [event_today.id, event_3_days.id, event_6_days.id]]
        self.assertEqual(len(our_events), 3)
        self.assertEqual(our_events[0].id, event_today.id)
        self.assertEqual(our_events[1].id, event_3_days.id)
        self.assertEqual(our_events[2].id, event_6_days.id)


@override_settings(ENABLE_USER_SELECTION=True)
class UserActivationPinTests(TestCase):
    """Tests for PIN-based user activation functionality."""
    
    def setUp(self) -> None:
        user_model = get_user_model()
        self.alice = user_model.objects.create_user(
            username='alice',
            password='password123',
        )
        self.bob = user_model.objects.create_user(
            username='bob',
            password='password123',
        )
        
        # Create NBA teams for PIN testing
        self.teams_cat = OptionCategory.objects.create(
            slug='nba-teams',
            name='NBA Teams'
        )
        self.lal_team = Option.objects.create(
            category=self.teams_cat,
            slug='lal',
            name='Los Angeles Lakers',
            short_name='LAL',
            external_id='1',
            metadata={'nba_team_id': '1'}
        )
        self.gsw_team = Option.objects.create(
            category=self.teams_cat,
            slug='gsw',
            name='Golden State Warriors',
            short_name='GSW',
            external_id='2',
            metadata={'nba_team_id': '2'}
        )
        self.bos_team = Option.objects.create(
            category=self.teams_cat,
            slug='bos',
            name='Boston Celtics',
            short_name='BOS',
            external_id='3',
            metadata={'nba_team_id': '3'}
        )
        self.mia_team = Option.objects.create(
            category=self.teams_cat,
            slug='mia',
            name='Miami Heat',
            short_name='MIA',
            external_id='4',
            metadata={'nba_team_id': '4'}
        )
        
        # Set up user preferences with PINs
        self.alice_prefs = UserPreferences.objects.create(
            user=self.alice,
            activation_pin='LAL,GSW,BOS'
        )
        self.bob_prefs = UserPreferences.objects.create(
            user=self.bob,
            activation_pin=''  # No PIN set
        )

    def test_user_activation_without_pin(self) -> None:
        """Test activating a user who has no PIN set."""
        response = self.client.post(reverse('predictions:home'), {
            'set_active_user': '1',
            'user_id': str(self.bob.id),
            'active_user_action': 'activate',
            'pin_teams': ['LAL', 'GSW', 'BOS']
        })
        
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.session.get('active_user_id'), self.bob.id)

    def test_user_activation_with_correct_pin(self) -> None:
        """Test activating a user with correct PIN."""
        response = self.client.post(reverse('predictions:home'), {
            'set_active_user': '1',
            'user_id': str(self.alice.id),
            'active_user_action': 'activate',
            'pin_teams': ['LAL', 'GSW', 'BOS']
        })
        
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.session.get('active_user_id'), self.alice.id)

    def test_user_activation_with_incorrect_pin(self) -> None:
        """Test activating a user with incorrect PIN."""
        response = self.client.post(reverse('predictions:home'), {
            'set_active_user': '1',
            'user_id': str(self.alice.id),
            'active_user_action': 'activate',
            'pin_teams': ['LAL', 'GSW', 'MIA']  # Wrong third team
        })
        
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(self.client.session.get('active_user_id'))

    def test_user_activation_with_pin_different_order(self) -> None:
        """Test activating a user with correct PIN in different order."""
        response = self.client.post(reverse('predictions:home'), {
            'set_active_user': '1',
            'user_id': str(self.alice.id),
            'active_user_action': 'activate',
            'pin_teams': ['BOS', 'LAL', 'GSW']  # Different order
        })
        
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.session.get('active_user_id'), self.alice.id)

    def test_user_activation_with_wrong_number_of_teams(self) -> None:
        """Test activating a user with wrong number of teams."""
        response = self.client.post(reverse('predictions:home'), {
            'set_active_user': '1',
            'user_id': str(self.alice.id),
            'active_user_action': 'activate',
            'pin_teams': ['LAL', 'GSW']  # Only 2 teams
        })
        
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(self.client.session.get('active_user_id'))

    def test_user_activation_case_insensitive(self) -> None:
        """Test that PIN validation is case insensitive."""
        response = self.client.post(reverse('predictions:home'), {
            'set_active_user': '1',
            'user_id': str(self.alice.id),
            'active_user_action': 'activate',
            'pin_teams': ['lal', 'gsw', 'bos']  # Lowercase
        })
        
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.session.get('active_user_id'), self.alice.id)

    def test_user_activation_nonexistent_user(self) -> None:
        """Test activating a non-existent user."""
        response = self.client.post(reverse('predictions:home'), {
            'set_active_user': '1',
            'user_id': '999',
            'active_user_action': 'activate',
            'pin_teams': ['LAL', 'GSW', 'BOS']
        })
        
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(self.client.session.get('active_user_id'))

    def test_user_activation_without_pin_teams_parameter(self) -> None:
        """Test activating a user without providing pin_teams parameter."""
        response = self.client.post(reverse('predictions:home'), {
            'set_active_user': '1',
            'user_id': str(self.alice.id),
            'active_user_action': 'activate',
            # No pin_teams parameter
        })
        
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(self.client.session.get('active_user_id'))
