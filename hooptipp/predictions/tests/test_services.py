import os
from datetime import datetime, timedelta, timezone as dt_timezone
from unittest import TestCase, mock

from balldontlie import exceptions
from django.test import TestCase as DjangoTestCase
from django.utils import timezone

from hooptipp.predictions import services
from hooptipp.predictions.models import ScheduledGame, TipType


class GetBdlApiKeyTests(TestCase):
    def setUp(self) -> None:
        os.environ.pop('BALLDONTLIE_API_TOKEN', None)
        os.environ.pop('BALLDONTLIE_API_KEY', None)
        return super().setUp()

    def test_returns_bearer_prefix_for_token(self) -> None:
        os.environ['BALLDONTLIE_API_TOKEN'] = 'secret-token'
        self.assertEqual(services._get_bdl_api_key(), 'Bearer secret-token')

    def test_supports_api_key_environment_variable(self) -> None:
        os.environ['BALLDONTLIE_API_KEY'] = 'another-token'
        self.assertEqual(services._get_bdl_api_key(), 'Bearer another-token')


class FetchUpcomingWeekGamesTests(TestCase):
    def setUp(self) -> None:
        os.environ.pop('BALLDONTLIE_API_TOKEN', None)
        os.environ.pop('BALLDONTLIE_API_KEY', None)
        services._BDL_CLIENT_CACHE.clear()
        return super().setUp()

    def test_fetch_upcoming_week_games_parses_payload(self) -> None:
        os.environ['BALLDONTLIE_API_TOKEN'] = 'secret-token'
        fake_now = datetime(2024, 1, 10, 12, 0, tzinfo=dt_timezone.utc)

        scheduled_game = mock.Mock()
        scheduled_game.id = 42
        scheduled_game.status = 'Scheduled'
        scheduled_game.date = '2024-01-12T00:00:00.000Z'
        scheduled_game.home_team = mock.Mock(full_name='Los Angeles Lakers', abbreviation='LAL')
        scheduled_game.visitor_team = mock.Mock(full_name='Boston Celtics', abbreviation='BOS')
        scheduled_game.arena = 'Crypto.com Arena'

        completed_game = mock.Mock()
        completed_game.status = 'Final'
        completed_game.date = '2024-01-12T00:00:00.000Z'

        response = mock.Mock()
        response.data = [scheduled_game, completed_game]

        with mock.patch.object(services.timezone, 'now', return_value=fake_now):
            with mock.patch.object(services, 'build_cached_bdl_client') as mock_builder:
                mock_client = mock.Mock()
                mock_games_api = mock.Mock()
                mock_client.nba = mock.Mock()
                mock_client.nba.games = mock_games_api
                mock_games_api.list.return_value = response
                mock_builder.return_value = mock_client

                week_start, games = services.fetch_upcoming_week_games(limit=3)

        self.assertEqual(week_start, datetime(2024, 1, 11, tzinfo=dt_timezone.utc).date())
        self.assertEqual(len(games), 1)
        game = games[0]
        self.assertEqual(game['game_id'], '42')
        self.assertEqual(game['home_team_name'], 'Los Angeles Lakers')
        self.assertEqual(game['home_team_tricode'], 'LAL')
        self.assertEqual(game['away_team_name'], 'Boston Celtics')
        self.assertEqual(game['away_team_tricode'], 'BOS')
        self.assertEqual(game['arena'], 'Crypto.com Arena')
        self.assertIsNotNone(game['game_time'].tzinfo)

        mock_builder.assert_called_once_with(api_key='Bearer secret-token')
        mock_games_api.list.assert_called_once_with(
            start_date='2024-01-11',
            end_date='2024-02-09',
            per_page=100,
            postseason='false',
        )

    def test_fetch_upcoming_week_games_picks_one_game_per_day(self) -> None:
        os.environ['BALLDONTLIE_API_TOKEN'] = 'secret-token'
        fake_now = datetime(2024, 1, 1, 9, 0, tzinfo=dt_timezone.utc)

        day_one_late = mock.Mock(
            id=200,
            status='Scheduled',
            date='2024-01-02T05:00:00.000Z',
            home_team=mock.Mock(full_name='Denver Nuggets', abbreviation='DEN'),
            visitor_team=mock.Mock(full_name='Milwaukee Bucks', abbreviation='MIL'),
            arena='Ball Arena',
        )
        day_one_early = mock.Mock(
            id=201,
            status='Scheduled',
            date='2024-01-02T01:00:00.000Z',
            home_team=mock.Mock(full_name='Los Angeles Lakers', abbreviation='LAL'),
            visitor_team=mock.Mock(full_name='Boston Celtics', abbreviation='BOS'),
            arena='Crypto.com Arena',
        )
        day_two_first = mock.Mock(
            id=202,
            status='Scheduled',
            date='2024-01-03T03:30:00.000Z',
            home_team=mock.Mock(full_name='Miami Heat', abbreviation='MIA'),
            visitor_team=mock.Mock(full_name='New York Knicks', abbreviation='NYK'),
            arena='Kaseya Center',
        )
        day_two_second = mock.Mock(
            id=203,
            status='Scheduled',
            date='2024-01-03T04:30:00.000Z',
            home_team=mock.Mock(full_name='Phoenix Suns', abbreviation='PHX'),
            visitor_team=mock.Mock(full_name='Golden State Warriors', abbreviation='GSW'),
            arena='Footprint Center',
        )

        response = mock.Mock(data=[day_one_late, day_one_early, day_two_first, day_two_second])

        with mock.patch.object(services.timezone, 'now', return_value=fake_now):
            with mock.patch.object(services, 'build_cached_bdl_client') as mock_builder:
                mock_client = mock.Mock()
                mock_games_api = mock.Mock()
                mock_client.nba = mock.Mock()
                mock_client.nba.games = mock_games_api
                mock_games_api.list.return_value = response
                mock_builder.return_value = mock_client

                week_start, games = services.fetch_upcoming_week_games(limit=7)

        self.assertEqual(week_start, datetime(2024, 1, 2, tzinfo=dt_timezone.utc).date())
        self.assertEqual(len(games), 2)
        returned_ids = [game['game_id'] for game in games]
        self.assertEqual(returned_ids, ['201', '202'])

    def test_fetch_upcoming_week_games_uses_first_available_week(self) -> None:
        os.environ['BALLDONTLIE_API_TOKEN'] = 'secret-token'
        fake_now = datetime(2024, 7, 1, 12, 0, tzinfo=dt_timezone.utc)

        opener = mock.Mock(
            id=100,
            status='Scheduled',
            date='2024-10-20T23:00:00.000Z',
            home_team=mock.Mock(full_name='Boston Celtics', abbreviation='BOS'),
            visitor_team=mock.Mock(full_name='Los Angeles Lakers', abbreviation='LAL'),
            arena='TD Garden',
        )

        same_week = mock.Mock(
            id=101,
            status='Scheduled',
            date='2024-10-22T23:30:00.000Z',
            home_team=mock.Mock(full_name='Denver Nuggets', abbreviation='DEN'),
            visitor_team=mock.Mock(full_name='Phoenix Suns', abbreviation='PHX'),
            arena='Ball Arena',
        )

        later_game = mock.Mock(
            id=102,
            status='Scheduled',
            date='2024-10-30T00:30:00.000Z',
            home_team=mock.Mock(full_name='Miami Heat', abbreviation='MIA'),
            visitor_team=mock.Mock(full_name='New York Knicks', abbreviation='NYK'),
            arena='Kaseya Center',
        )

        response = mock.Mock(data=[opener, same_week, later_game])

        with mock.patch.object(services.timezone, 'now', return_value=fake_now):
            with mock.patch.object(services, 'build_cached_bdl_client') as mock_builder:
                mock_client = mock.Mock()
                mock_games_api = mock.Mock()
                mock_client.nba = mock.Mock()
                mock_client.nba.games = mock_games_api
                mock_games_api.list.return_value = response
                mock_builder.return_value = mock_client

                week_start, games = services.fetch_upcoming_week_games(limit=5)

        self.assertEqual(week_start, datetime(2024, 10, 20, 23, 0, tzinfo=dt_timezone.utc).date())
        self.assertEqual(len(games), 2)
        returned_ids = {game['game_id'] for game in games}
        self.assertEqual(returned_ids, {'100', '101'})

    def test_fetch_upcoming_week_games_handles_request_errors(self) -> None:
        os.environ['BALLDONTLIE_API_TOKEN'] = 'secret-token'

        with mock.patch.object(services, 'build_cached_bdl_client') as mock_builder:
            mock_client = mock.Mock()
            mock_games_api = mock.Mock()
            mock_games_api.list.side_effect = exceptions.BallDontLieException('boom')
            mock_client.nba = mock.Mock()
            mock_client.nba.games = mock_games_api
            mock_builder.return_value = mock_client

            with self.assertLogs('hooptipp.predictions.services', level='ERROR') as captured:
                week_start, games = services.fetch_upcoming_week_games(limit=2)

        self.assertIsNone(week_start)
        self.assertEqual(games, [])
        self.assertTrue(any('Unable to fetch games from BallDontLie API.' in entry for entry in captured.output))

    def test_logs_when_token_missing(self) -> None:
        with self.assertLogs('hooptipp.predictions.services', level='WARNING') as captured:
            week_start, games = services.fetch_upcoming_week_games(limit=2)

        self.assertIsNone(week_start)
        self.assertEqual(games, [])
        self.assertTrue(any('BALLDONTLIE_API_TOKEN environment variable is not configured' in entry for entry in captured.output))


class BuildBdlClientCachingTests(TestCase):
    def setUp(self) -> None:
        os.environ.pop('BALLDONTLIE_API_TOKEN', None)
        os.environ.pop('BALLDONTLIE_API_KEY', None)
        services._BDL_CLIENT_CACHE.clear()
        return super().setUp()

    def tearDown(self) -> None:
        services._BDL_CLIENT_CACHE.clear()
        return super().tearDown()

    def test_reuses_cached_client_for_same_api_key(self) -> None:
        os.environ['BALLDONTLIE_API_TOKEN'] = 'secret-token'

        with mock.patch.object(services, 'build_cached_bdl_client') as mock_builder:
            first_client = mock.Mock()
            second_client = mock.Mock()
            mock_builder.side_effect = [first_client, second_client]

            client_a = services._build_bdl_client()
            client_b = services._build_bdl_client()

        self.assertIs(client_a, first_client)
        self.assertIs(client_b, first_client)
        self.assertEqual(mock_builder.call_count, 1)

    def test_caches_per_distinct_api_key(self) -> None:
        os.environ['BALLDONTLIE_API_TOKEN'] = 'first-token'

        with mock.patch.object(services, 'build_cached_bdl_client') as mock_builder:
            first_client = mock.Mock()
            second_client = mock.Mock()
            mock_builder.side_effect = [first_client, second_client]

            client_first = services._build_bdl_client()
            os.environ['BALLDONTLIE_API_TOKEN'] = 'second-token'

            client_second = services._build_bdl_client()

        self.assertIs(client_first, first_client)
        self.assertIs(client_second, second_client)
        self.assertEqual(mock_builder.call_count, 2)
        self.assertEqual(len(services._BDL_CLIENT_CACHE), 2)
        self.assertIn('Bearer first-token', services._BDL_CLIENT_CACHE)
        self.assertIn('Bearer second-token', services._BDL_CLIENT_CACHE)


class SyncWeeklyGamesTests(DjangoTestCase):
    def test_sync_weekly_games_preserves_manual_entries(self) -> None:
        base_time = timezone.now()

        tip_type = TipType.objects.create(
            name='Weekly games',
            slug='weekly-games',
            description='Featured matchups for the upcoming week',
            deadline=base_time,
        )
        manual_game = ScheduledGame.objects.create(
            tip_type=tip_type,
            nba_game_id='MANUAL-1',
            game_date=base_time + timedelta(days=2),
            home_team='Dallas Mavericks',
            home_team_tricode='DAL',
            away_team='Los Angeles Clippers',
            away_team_tricode='LAC',
            venue='American Airlines Center',
            is_manual=True,
        )

        auto_game_payload = {
            'game_id': 'AUTO-1',
            'game_time': base_time + timedelta(days=1),
            'home_team_name': 'Denver Nuggets',
            'home_team_tricode': 'DEN',
            'away_team_name': 'Phoenix Suns',
            'away_team_tricode': 'PHX',
            'arena': 'Ball Arena',
        }

        with mock.patch(
            'hooptipp.predictions.services.fetch_upcoming_week_games',
            return_value=(timezone.localdate(auto_game_payload['game_time']), [auto_game_payload]),
        ):
            tip_type, games, week_start = services.sync_weekly_games()

        self.assertIsNotNone(tip_type)
        self.assertEqual(week_start, timezone.localdate(auto_game_payload['game_time']))
        returned_ids = {game.nba_game_id for game in games}
        self.assertSetEqual(returned_ids, {'AUTO-1', 'MANUAL-1'})
        manual_game.refresh_from_db()
        self.assertTrue(manual_game.is_manual)
        tip_type.refresh_from_db()
        self.assertEqual(tip_type.deadline, min(game.game_date for game in games))

    def test_sync_weekly_games_returns_manual_when_no_automatic_games(self) -> None:
        base_time = timezone.now()
        tip_type = TipType.objects.create(
            name='Weekly games',
            slug='weekly-games',
            description='Featured matchups for the upcoming week',
            deadline=base_time,
        )
        manual_game = ScheduledGame.objects.create(
            tip_type=tip_type,
            nba_game_id='MANUAL-ONLY',
            game_date=base_time + timedelta(days=3),
            home_team='Memphis Grizzlies',
            home_team_tricode='MEM',
            away_team='San Antonio Spurs',
            away_team_tricode='SAS',
            venue='FedExForum',
            is_manual=True,
        )

        with mock.patch(
            'hooptipp.predictions.services.fetch_upcoming_week_games',
            return_value=(timezone.localdate(base_time), []),
        ):
            tip_type, games, week_start = services.sync_weekly_games()

        self.assertIsNotNone(tip_type)
        self.assertEqual(week_start, timezone.localdate(base_time))
        self.assertEqual([game.nba_game_id for game in games], ['MANUAL-ONLY'])
        manual_game.refresh_from_db()
        self.assertTrue(manual_game.is_manual)
