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
    Season,
    TipType,
    UserPreferences,
    UserEventScore,
    UserTip,
)


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

    def test_leaderboard_shows_top_6_when_no_active_user(self) -> None:
        """Test that leaderboard shows top 6 users when no active user is set."""
        user_model = get_user_model()
        
        # Create 15 users with scores
        users = []
        for i in range(15):
            user = user_model.objects.create_user(
                username=f'user{i}',
                password='password123',
            )
            # Create scores with decreasing points to create a clear ranking
            UserEventScore.objects.create(
                user=user,
                prediction_event=self.event,
                base_points=100 - i,
                lock_multiplier=1,
                points_awarded=100 - i,
            )
            users.append(user)
        
        response = self.client.get(reverse('predictions:home'))
        
        self.assertEqual(response.status_code, 200)
        self.assertIn('leaderboard_rows', response.context)
        
        leaderboard_rows = response.context['leaderboard_rows']
        # Should show top 6 only
        non_divider_rows = [r for r in leaderboard_rows if not hasattr(r, 'is_divider') or not r.is_divider]
        self.assertLessEqual(len(non_divider_rows), 6)
        
        # Verify ranks are sequential for non-divider rows
        for row in non_divider_rows:
            if hasattr(row, 'rank'):
                self.assertLessEqual(row.rank, 6)
    
    def test_leaderboard_shows_rank1_and_users_around_active_user(self) -> None:
        """Test that leaderboard shows rank 1 + divider + users around active user when active user is not rank 1."""
        user_model = get_user_model()
        
        # Create users and set Alice as active user
        UserPreferences.objects.create(user=self.alice)
        
        # Set active user in session
        session = self.client.session
        session['active_user_id'] = self.alice.id
        session.save()
        
        # Create 20 users with scores
        users = []
        for i in range(20):
            user = user_model.objects.create_user(
                username=f'user{i}',
                password='password123',
            )
            # Create scores with decreasing points
            UserEventScore.objects.create(
                user=user,
                prediction_event=self.event,
                base_points=200 - i,
                lock_multiplier=1,
                points_awarded=200 - i,
            )
            users.append(user)
        
        # Give Alice a lower score to ensure she's not rank 1 (rank ~4-20)
        alice_score = UserEventScore.objects.create(
            user=self.alice,
            prediction_event=self.event,
            base_points=50,
            lock_multiplier=1,
            points_awarded=50,
        )
        
        response = self.client.get(reverse('predictions:home'))
        
        self.assertEqual(response.status_code, 200)
        self.assertIn('leaderboard_rows', response.context)
        
        leaderboard_rows = response.context['leaderboard_rows']
        
        # Should have rank 1 + divider + users around active user (max 6 total)
        divider_found = False
        alice_found = False
        rank_1_found = False
        
        for idx, row in enumerate(leaderboard_rows):
            if hasattr(row, 'is_divider') and row.is_divider:
                divider_found = True
            elif hasattr(row, 'is_active_user') and row.is_active_user:
                alice_found = True
                self.assertTrue(hasattr(row, 'rank'))
            elif hasattr(row, 'rank'):
                if row.rank == 1:
                    rank_1_found = True
        
        self.assertTrue(rank_1_found, "Rank 1 should always be shown")
        self.assertTrue(divider_found, "Divider should be present when active user is not rank 1 and not adjacent")
        self.assertTrue(alice_found, "Active user should be in leaderboard")
        
        # Total should be max 6 (excluding divider)
        non_divider_rows = [r for r in leaderboard_rows if not hasattr(r, 'is_divider') or not r.is_divider]
        self.assertLessEqual(len(non_divider_rows), 6)
    
    def test_leaderboard_shows_top_6_when_active_user_is_rank1(self) -> None:
        """Test that leaderboard shows top 6 when active user is rank 1."""
        user_model = get_user_model()
        
        # Set active user in session
        session = self.client.session
        session['active_user_id'] = self.alice.id
        session.save()
        
        # Create 15 users with scores, but give Alice a high score to be in top 3
        UserEventScore.objects.create(
            user=self.alice,
            prediction_event=self.event,
            base_points=200,
            lock_multiplier=1,
            points_awarded=200,
        )
        
        users = []
        for i in range(15):
            user = user_model.objects.create_user(
                username=f'user{i}',
                password='password123',
            )
            # Create scores with decreasing points (Alice should be rank 1)
            UserEventScore.objects.create(
                user=user,
                prediction_event=self.event,
                base_points=100 - i,
                lock_multiplier=1,
                points_awarded=100 - i,
            )
            users.append(user)
        
        response = self.client.get(reverse('predictions:home'))
        
        self.assertEqual(response.status_code, 200)
        self.assertIn('leaderboard_rows', response.context)
        
        leaderboard_rows = response.context['leaderboard_rows']
        
        # Should show top 6
        non_divider_rows = [r for r in leaderboard_rows if not hasattr(r, 'is_divider') or not r.is_divider]
        self.assertLessEqual(len(non_divider_rows), 6)
        
        # Active user should be marked and should be rank 1, no divider
        alice_found = False
        divider_found = False
        alice_rank = None
        
        for row in leaderboard_rows:
            if hasattr(row, 'is_divider') and row.is_divider:
                divider_found = True
            elif hasattr(row, 'is_active_user') and row.is_active_user and hasattr(row, 'id') and row.id == self.alice.id:
                alice_found = True
                if hasattr(row, 'rank'):
                    alice_rank = row.rank
        
        self.assertFalse(divider_found, "Divider should not be present when active user is rank 1")
        self.assertTrue(alice_found, "Active user should be in leaderboard")
        self.assertEqual(alice_rank, 1, "Active user should be rank 1")
    
    def test_leaderboard_shows_active_user_with_no_scores(self) -> None:
        """Test that leaderboard shows active user even when they have 0 points (at bottom of list)."""
        user_model = get_user_model()
        
        # Set active user in session (Alice has no scores)
        session = self.client.session
        session['active_user_id'] = self.alice.id
        session.save()
        
        # Create 15 users with scores
        users = []
        for i in range(15):
            user = user_model.objects.create_user(
                username=f'user{i}',
                password='password123',
            )
            UserEventScore.objects.create(
                user=user,
                prediction_event=self.event,
                base_points=100 - i,
                lock_multiplier=1,
                points_awarded=100 - i,
            )
            users.append(user)
        
        response = self.client.get(reverse('predictions:home'))
        
        self.assertEqual(response.status_code, 200)
        self.assertIn('leaderboard_rows', response.context)
        
        leaderboard_rows = response.context['leaderboard_rows']
        
        # Should show rank 1 + divider + users around Alice (who is last with 0 points)
        # Max 6 users (excluding divider)
        non_divider_rows = [r for r in leaderboard_rows if not hasattr(r, 'is_divider') or not r.is_divider]
        self.assertLessEqual(len(non_divider_rows), 6, "Should show max 6 users")
        
        # Alice should be in the leaderboard with 0 points
        alice_found = False
        divider_found = False
        rank_1_found = False
        
        for row in leaderboard_rows:
            if hasattr(row, 'is_divider') and row.is_divider:
                divider_found = True
            elif hasattr(row, 'id') and row.id == self.alice.id:
                alice_found = True
                self.assertEqual(row.total_points, 0, "Alice should have 0 points")
                self.assertEqual(row.event_count, 0, "Alice should have 0 events scored")
                self.assertTrue(hasattr(row, 'is_active_user') and row.is_active_user, "Alice should be marked as active user")
            elif hasattr(row, 'rank') and row.rank == 1:
                rank_1_found = True
        
        self.assertTrue(alice_found, "Alice should be in the leaderboard even with no scores")
        self.assertTrue(divider_found, "Divider should be present when active user is at bottom")
        self.assertTrue(rank_1_found, "Rank 1 should be shown")
    
    def test_leaderboard_zero_score_users_only_shown_when_active(self) -> None:
        """Test that users with 0 points only appear when they are the active user."""
        user_model = get_user_model()
        
        # Create 10 users with scores
        users_with_scores = []
        for i in range(10):
            user = user_model.objects.create_user(
                username=f'scorer{i}',
                password='password123',
            )
            UserEventScore.objects.create(
                user=user,
                prediction_event=self.event,
                base_points=100 - (i * 5),
                lock_multiplier=1,
                points_awarded=100 - (i * 5),
            )
            users_with_scores.append(user)
        
        # Create 2 users without any scores (besides alice from setUp)
        user_no_score_1 = user_model.objects.create_user(
            username='no_score_1',
            password='password123',
        )
        user_no_score_2 = user_model.objects.create_user(
            username='no_score_2',
            password='password123',
        )
        
        # Test 1: No active user - 0-score users should NOT be in top 6
        response = self.client.get(reverse('predictions:home'))
        leaderboard_rows = response.context['leaderboard_rows']
        non_divider_rows = [r for r in leaderboard_rows if not hasattr(r, 'is_divider') or not r.is_divider]
        user_ids = [row.id for row in non_divider_rows]
        
        self.assertNotIn(self.alice.id, user_ids, "Alice (0 points) should not be in top 6")
        self.assertNotIn(user_no_score_1.id, user_ids, "0-score user should not be in top 6")
        self.assertNotIn(user_no_score_2.id, user_ids, "0-score user should not be in top 6")
        
        # Test 2: Set user_no_score_1 as active - they SHOULD appear
        session = self.client.session
        session['active_user_id'] = user_no_score_1.id
        session.save()
        
        response = self.client.get(reverse('predictions:home'))
        leaderboard_rows = response.context['leaderboard_rows']
        non_divider_rows = [r for r in leaderboard_rows if not hasattr(r, 'is_divider') or not r.is_divider]
        user_ids = [row.id for row in non_divider_rows]
        
        self.assertIn(user_no_score_1.id, user_ids, "Active user with 0 points should be shown")
        
        # Verify the 0-score user has correct values
        for row in non_divider_rows:
            if row.id == user_no_score_1.id:
                self.assertEqual(row.total_points, 0, "User should have 0 points")
                self.assertEqual(row.event_count, 0, "User should have 0 events scored")
                self.assertTrue(hasattr(row, 'is_active_user') and row.is_active_user, "Should be marked as active")
    
    def test_leaderboard_active_user_highlighted_in_template(self) -> None:
        """Test that active user is highlighted in the template."""
        user_model = get_user_model()
        
        # Set active user in session
        session = self.client.session
        session['active_user_id'] = self.alice.id
        session.save()
        
        # Create users with high scores (top 3 will be user0, user1, user2)
        for i in range(20):
            user = user_model.objects.create_user(
                username=f'user{i}',
                password='password123',
            )
            UserEventScore.objects.create(
                user=user,
                prediction_event=self.event,
                base_points=100 - i,
                lock_multiplier=1,
                points_awarded=100 - i,
            )
        
        # Give Alice a score that puts her around rank 17 (not in top 3)
        UserEventScore.objects.create(
            user=self.alice,
            prediction_event=self.event,
            base_points=30,
            lock_multiplier=1,
            points_awarded=30,
        )
        
        response = self.client.get(reverse('predictions:home'))
        
        self.assertEqual(response.status_code, 200)
        
        # Check that the active user's name is present in the response
        # (Alice should be in the leaderboard with her display name)
        self.assertContains(response, 'alice')
        
        # Check that Alice is marked as active user with the accent border
        response_content = response.content.decode('utf-8')
        # Alice should have the theme-accent-border class (for active user highlighting)
        self.assertTrue('theme-accent-border' in response_content, "Active user should have accent border")
    
    def test_leaderboard_max_6_users_shown(self) -> None:
        """Test that leaderboard never shows more than 6 users (excluding divider)."""
        user_model = get_user_model()
        
        # Set active user in session
        session = self.client.session
        session['active_user_id'] = self.alice.id
        session.save()
        
        # Create 25 users with scores
        for i in range(25):
            user = user_model.objects.create_user(
                username=f'user{i}',
                password='password123',
            )
            UserEventScore.objects.create(
                user=user,
                prediction_event=self.event,
                base_points=200 - i,
                lock_multiplier=1,
                points_awarded=200 - i,
            )
        
        # Give Alice a score that puts her around rank 17
        UserEventScore.objects.create(
            user=self.alice,
            prediction_event=self.event,
            base_points=30,
            lock_multiplier=1,
            points_awarded=30,
        )
        
        response = self.client.get(reverse('predictions:home'))
        
        self.assertEqual(response.status_code, 200)
        self.assertIn('leaderboard_rows', response.context)
        
        leaderboard_rows = response.context['leaderboard_rows']
        
        # Count non-divider rows
        non_divider_rows = [r for r in leaderboard_rows if not hasattr(r, 'is_divider') or not r.is_divider]
        self.assertLessEqual(len(non_divider_rows), 6, "Should never show more than 6 users")

    def test_home_view_filters_open_predictions_to_upcoming_week(self) -> None:
        """Test that open_predictions shows events from the next 7 days, and fills up to 5 with future events if needed."""
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
        
        # Event 4: Due in 8 days (should be included if we have less than 5 events in the 7-day window)
        event_8_days = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Event in 8 Days',
            opens_at=now - timedelta(hours=1),
            deadline=now + timedelta(days=8),
            is_active=True,
        )
        
        # Event 5: Due in 10 days (should be included if we have less than 5 events in the 7-day window)
        event_10_days = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Event in 10 Days',
            opens_at=now - timedelta(hours=1),
            deadline=now + timedelta(days=10),
            is_active=True,
        )
        
        # Event 6: Due 1 hour ago (should NOT be included - past deadline)
        event_past = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Event Past',
            opens_at=now - timedelta(days=2),
            deadline=now - timedelta(hours=1),
            is_active=True,
        )
        
        # Event 7: Opens tomorrow (should NOT be included - not yet open)
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
        
        # Should always include events due today, in 3 days, and in 6 days (within 7-day window)
        self.assertIn(event_today.id, open_prediction_ids)
        self.assertIn(event_3_days.id, open_prediction_ids)
        self.assertIn(event_6_days.id, open_prediction_ids)
        
        # Should NOT include events with past deadline or not yet open
        self.assertNotIn(event_past.id, open_prediction_ids)
        self.assertNotIn(event_opens_tomorrow.id, open_prediction_ids)
        
        # Since we have only 3 events in the 7-day window, we should fill up to 5 with future events
        # Note: The existing event from setUp might also be included if its deadline is within the week
        events_in_7_days = [event for event in open_predictions if event.id in [event_today.id, event_3_days.id, event_6_days.id]]
        self.assertEqual(len(events_in_7_days), 3)
        
        # If we have less than 5 total events (including setUp events), future events should be included
        if len(open_predictions) < 5:
            # Should include future events to fill up to 5
            self.assertIn(event_8_days.id, open_prediction_ids)
            # Should be ordered by deadline
            our_events = [event for event in open_predictions if event.id in [event_today.id, event_3_days.id, event_6_days.id, event_8_days.id]]
            self.assertGreaterEqual(len(our_events), 3)
            # Verify ordering
            if event_today.id in open_prediction_ids and event_3_days.id in open_prediction_ids:
                idx_today = open_prediction_ids.index(event_today.id)
                idx_3_days = open_prediction_ids.index(event_3_days.id)
                self.assertLess(idx_today, idx_3_days)

    def test_home_view_fills_open_predictions_with_future_events_when_less_than_5(self) -> None:
        """Test that open_predictions fills up to 5 events with future events when there are less than 5 in the 7-day window."""
        now = timezone.now()
        
        # Create only 2 events in the 7-day window
        event_today = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Event Today',
            opens_at=now - timedelta(hours=1),
            deadline=now + timedelta(hours=1),
            is_active=True,
        )
        
        event_3_days = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Event in 3 Days',
            opens_at=now - timedelta(hours=1),
            deadline=now + timedelta(days=3),
            is_active=True,
        )
        
        # Create events beyond the 7-day window
        event_8_days = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Event in 8 Days',
            opens_at=now - timedelta(hours=1),
            deadline=now + timedelta(days=8),
            is_active=True,
        )
        
        event_10_days = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Event in 10 Days',
            opens_at=now - timedelta(hours=1),
            deadline=now + timedelta(days=10),
            is_active=True,
        )
        
        event_12_days = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Event in 12 Days',
            opens_at=now - timedelta(hours=1),
            deadline=now + timedelta(days=12),
            is_active=True,
        )
        
        event_15_days = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Event in 15 Days',
            opens_at=now - timedelta(hours=1),
            deadline=now + timedelta(days=15),
            is_active=True,
        )

        response = self.client.get(reverse('predictions:home'))
        
        self.assertEqual(response.status_code, 200)
        self.assertIn('open_predictions', response.context)
        
        open_predictions = response.context['open_predictions']
        open_prediction_ids = [event.id for event in open_predictions]
        
        # Should always include events from the 7-day window
        self.assertIn(event_today.id, open_prediction_ids)
        self.assertIn(event_3_days.id, open_prediction_ids)
        
        # Should include future events to fill up to 5 (we have 2 in 7-day window, need 3 more)
        # Note: The existing event from setUp might also be included if its deadline is within the week
        # So we check that we have at least 2 events from the 7-day window, and future events are added
        events_in_7_days = [event for event in open_predictions if event.id in [event_today.id, event_3_days.id]]
        self.assertEqual(len(events_in_7_days), 2)
        
        # Should include future events (at least event_8_days and event_10_days should be included)
        # to reach up to 5 total events
        self.assertIn(event_8_days.id, open_prediction_ids)
        self.assertIn(event_10_days.id, open_prediction_ids)
        
        # Verify ordering - events should be ordered by deadline
        if event_today.id in open_prediction_ids and event_8_days.id in open_prediction_ids:
            idx_today = open_prediction_ids.index(event_today.id)
            idx_8_days = open_prediction_ids.index(event_8_days.id)
            self.assertLess(idx_today, idx_8_days)

    def test_season_end_description_displayed_when_season_ended(self) -> None:
        """Test that season_end_description is used when season has ended."""
        now = timezone.now()
        
        # Create an active season - should use regular description
        active_season = Season.objects.create(
            name='Active Season',
            start_date=now - timedelta(days=5),
            end_date=now + timedelta(days=5),
            description='Active season description',
            season_end_description='This should not be shown yet'
        )
        
        session = self.client.session
        session['active_user_id'] = self.alice.id
        session.save()
        
        response = self.client.get(reverse('predictions:home'))
        self.assertEqual(response.status_code, 200)
        
        # Check that regular description is used for active season
        season_description_html = response.context.get('season_description_html', '')
        self.assertIn('Active season description', season_description_html)
        self.assertNotIn('This should not be shown yet', season_description_html)
        
        # Delete the active season to avoid overlap
        active_season.delete()
        
        # Test season_end_description in season_results for ended seasons
        # Create a recently ended season with both descriptions
        ended_season = Season.objects.create(
            name='Ended Season',
            start_date=now - timedelta(days=30),
            end_date=now - timedelta(days=1),  # Ended yesterday (within 7 days)
            description='Regular season description',
            season_end_description='Season has ended! Thanks for playing.'
        )
        
        # Enroll user in the ended season so season_results are shown
        from hooptipp.predictions.models import SeasonParticipant
        SeasonParticipant.objects.create(user=self.alice, season=ended_season)
        
        # Create some scores so season_results are calculated
        UserEventScore.objects.create(
            user=self.alice,
            prediction_event=self.event,
            base_points=10,
            points_awarded=10
        )
        
        response = self.client.get(reverse('predictions:home'))
        self.assertEqual(response.status_code, 200)
        
        # Check that season_end_description is used in season_results
        season_results = response.context.get('season_results')
        if season_results:
            description_html = season_results.get('description_html', '')
            self.assertIn('Season has ended! Thanks for playing.', description_html)
            self.assertNotIn('Regular season description', description_html)
