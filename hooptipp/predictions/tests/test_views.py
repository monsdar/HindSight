from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from hooptipp.predictions.models import (
    NbaTeam,
    Option,
    OptionCategory,
    PredictionEvent,
    PredictionOption,
    ScheduledGame,
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
        self.home_team = NbaTeam.objects.create(
            name='Los Angeles Lakers',
            abbreviation='LAL',
        )
        self.away_team = NbaTeam.objects.create(
            name='Boston Celtics',
            abbreviation='BOS',
        )
        self.home_option_obj = Option.objects.create(
            category=self.teams_cat,
            slug='lal',
            name='Los Angeles Lakers',
            short_name='LAL',
            metadata={'nba_team_id': self.home_team.id}
        )
        self.away_option_obj = Option.objects.create(
            category=self.teams_cat,
            slug='bos',
            name='Boston Celtics',
            short_name='BOS',
            metadata={'nba_team_id': self.away_team.id}
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
        with mock.patch(
            'hooptipp.predictions.views.sync_weekly_games',
            return_value=(self.tip_type, [self.event], self.game.game_date.date()),
        ):
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

        self.assertContains(response, 'title="alice"')
        self.assertContains(response, 'title="bob"')

    def test_home_view_displays_nickname_everywhere(self) -> None:
        UserPreferences.objects.create(user=self.alice, nickname='Ace')
        UserPreferences.objects.create(user=self.bob, nickname='Buckets')

        session = self.client.session
        session['active_user_id'] = self.alice.id
        session.save()

        with mock.patch(
            'hooptipp.predictions.views.sync_weekly_games',
            return_value=(self.tip_type, [self.event], self.game.game_date.date()),
        ):
            response = self.client.get(reverse('predictions:home'))

        self.assertEqual(response.status_code, 200)

        self.assertContains(response, 'Ace (@alice)')
        self.assertContains(response, 'Buckets (@bob)')
        self.assertContains(response, 'No events have been scored for Ace (@alice) yet.')
        self.assertContains(
            response,
            'Picks are automatically stored for <span class="font-semibold text-slate-100">Ace</span><span class="ml-1 text-xs text-slate-400">@alice</span>.',
        )
        self.assertContains(response, 'title="Buckets (@bob)"')

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

        with mock.patch(
            'hooptipp.predictions.views.sync_weekly_games',
            return_value=(self.tip_type, [self.event], self.game.game_date.date()),
        ):
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
        away_team = NbaTeam.objects.create(name='Miami Heat', abbreviation='MIA')
        home_team = NbaTeam.objects.create(name='Chicago Bulls', abbreviation='CHI')
        
        # Create Options for these teams
        away_option = Option.objects.create(
            category=self.teams_cat,
            slug='mia',
            name='Miami Heat',
            short_name='MIA',
            metadata={'nba_team_id': away_team.id}
        )
        home_option = Option.objects.create(
            category=self.teams_cat,
            slug='chi',
            name='Chicago Bulls',
            short_name='CHI',
            metadata={'nba_team_id': home_team.id}
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

        with mock.patch(
            'hooptipp.predictions.views.sync_weekly_games',
            return_value=(self.tip_type, [self.event, additional_event], self.game.game_date.date()),
        ):
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

        with mock.patch(
            'hooptipp.predictions.views.sync_weekly_games',
            return_value=(self.tip_type, [self.event], self.game.game_date.date()),
        ):
            response = self.client.get(reverse('predictions:home'))

        self.assertEqual(response.status_code, 200)
        weekday_slots = response.context['weekday_slots']
        included_ids = [event.id for slot in weekday_slots for event in slot['events']]
        self.assertNotIn(distant_event.id, included_ids)

    def test_update_preferences_updates_record(self) -> None:
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

        with mock.patch(
            'hooptipp.predictions.views.sync_weekly_games',
            return_value=(self.tip_type, [self.event], self.game.game_date.date()),
        ):
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

    def test_finish_round_allows_switching_users(self) -> None:
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
                    'user_id': str(self.bob.id),
                    'active_user_action': 'finish',
                },
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.session.get('active_user_id'), self.bob.id)

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

    def test_finish_round_allows_switching_users(self) -> None:
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

        with mock.patch(
            'hooptipp.predictions.views.sync_weekly_games',
            return_value=(self.tip_type, [self.event], self.game.game_date.date()),
        ):
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

        with mock.patch(
            'hooptipp.predictions.views.sync_weekly_games',
            return_value=(self.tip_type, [self.event, extra_event], self.game.game_date.date()),
        ):
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

        with mock.patch(
            'hooptipp.predictions.views.sync_weekly_games',
            return_value=(self.tip_type, [self.event], self.game.game_date.date()),
        ):
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
        self.assertEqual(tip.lock_status, UserTip.LockStatus.RETURNED)
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

        with mock.patch(
            'hooptipp.predictions.views.sync_weekly_games',
            return_value=(self.tip_type, [self.event], self.game.game_date.date()),
        ):
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
        self.assertContains(response, 'Scoring overview')
        self.assertContains(response, '6 pts')
        self.assertContains(response, 'Bonus event')


class LeaderboardViewTests(TestCase):
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
        now = timezone.now()
        self.tip_type_regular = TipType.objects.create(
            name='Weekly games',
            slug='weekly',
            description='Regular season matchups',
            category=TipType.TipCategory.GAME,
            deadline=now,
        )
        self.tip_type_bonus = TipType.objects.create(
            name='Finals picks',
            slug='finals',
            description='High-stakes playoff predictions',
            category=TipType.TipCategory.SEASON,
            deadline=now,
        )
        self.event_regular = PredictionEvent.objects.create(
            tip_type=self.tip_type_regular,
            name='Game of the week',
            target_kind=PredictionEvent.TargetKind.TEAM,
            selection_mode=PredictionEvent.SelectionMode.CURATED,
            opens_at=now - timedelta(days=7),
            deadline=now - timedelta(days=1),
            reveal_at=now - timedelta(days=7),
            is_active=False,
            points=1,
        )
        self.event_bonus = PredictionEvent.objects.create(
            tip_type=self.tip_type_bonus,
            name='Season champion',
            target_kind=PredictionEvent.TargetKind.TEAM,
            selection_mode=PredictionEvent.SelectionMode.CURATED,
            opens_at=now - timedelta(days=30),
            deadline=now - timedelta(days=1),
            reveal_at=now - timedelta(days=30),
            is_active=False,
            points=5,
            is_bonus_event=True,
        )

        UserEventScore.objects.create(
            user=self.alice,
            prediction_event=self.event_regular,
            base_points=1,
            lock_multiplier=1,
            points_awarded=1,
        )
        UserEventScore.objects.create(
            user=self.alice,
            prediction_event=self.event_bonus,
            base_points=5,
            lock_multiplier=2,
            points_awarded=10,
            is_lock_bonus=True,
        )
        UserEventScore.objects.create(
            user=self.bob,
            prediction_event=self.event_regular,
            base_points=1,
            lock_multiplier=1,
            points_awarded=1,
        )

        super().setUp()

    def test_leaderboard_orders_by_total_points(self) -> None:
        response = self.client.get(reverse('predictions:leaderboard'))

        self.assertEqual(response.status_code, 200)
        rows = response.context['leaderboard_rows']
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].username, 'alice')
        self.assertEqual(rows[0].total_points, 11)
        self.assertEqual(rows[0].bonus_event_points, 5)
        self.assertEqual(rows[0].lock_bonus_points, 5)
        self.assertEqual(rows[0].standard_points, 1)
        self.assertContains(response, 'Showing 2 players')

    def test_leaderboard_filters_by_tip_type(self) -> None:
        response = self.client.get(
            reverse('predictions:leaderboard'),
            {'tip_type': self.tip_type_bonus.slug},
        )

        self.assertEqual(response.status_code, 200)
        rows = response.context['leaderboard_rows']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].username, 'alice')
        self.assertEqual(rows[0].total_points, 10)
        self.assertTrue(response.context['score_filters_applied'])
        self.assertEqual(response.context['selected_tip_type'], self.tip_type_bonus.slug)

    def test_leaderboard_filters_by_segment(self) -> None:
        response = self.client.get(
            reverse('predictions:leaderboard'),
            {'segment': TipType.TipCategory.SEASON},
        )

        self.assertEqual(response.status_code, 200)
        rows = response.context['leaderboard_rows']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].username, 'alice')
        self.assertEqual(rows[0].total_points, 10)
        self.assertEqual(response.context['selected_segment'], TipType.TipCategory.SEASON)

    def test_leaderboard_sort_by_lock_bonus(self) -> None:
        response = self.client.get(
            reverse('predictions:leaderboard'),
            {'sort': 'locks'},
        )

        self.assertEqual(response.status_code, 200)
        rows = response.context['leaderboard_rows']
        self.assertEqual(rows[0].username, 'alice')
        self.assertEqual(rows[1].username, 'bob')
        self.assertEqual(response.context['selected_sort'], 'locks')
