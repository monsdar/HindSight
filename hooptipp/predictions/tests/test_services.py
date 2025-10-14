import os
from datetime import datetime, timedelta, timezone as dt_timezone
from types import SimpleNamespace
from unittest import TestCase, mock

from balldontlie import exceptions
from django.test import TestCase as DjangoTestCase
from django.utils import timezone

from hooptipp.predictions import services
from hooptipp.predictions.models import (
    NbaPlayer,
    NbaTeam,
    PredictionEvent,
    ScheduledGame,
    TipType,
)


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


class GetTeamChoicesTests(TestCase):
    def setUp(self) -> None:
        services.get_team_choices.cache_clear()
        return super().setUp()

    def tearDown(self) -> None:
        services.get_team_choices.cache_clear()
        return super().tearDown()

    def test_fetches_and_sorts_teams(self) -> None:
        lakers = mock.Mock(id=14, full_name='Los Angeles Lakers')
        celtics = mock.Mock(id=2, full_name='Boston Celtics')

        response = mock.Mock(data=[lakers, celtics])
        mock_client = mock.Mock()
        mock_client.nba.teams.list.return_value = response

        with mock.patch.object(services, '_build_bdl_client', return_value=mock_client):
            choices = services.get_team_choices()

        self.assertEqual(choices, [('2', 'Boston Celtics'), ('14', 'Los Angeles Lakers')])
        mock_client.nba.teams.list.assert_called_once_with(per_page=100)

    def test_retries_without_per_page_when_unsupported(self) -> None:
        lakers = mock.Mock(id=14, full_name='Los Angeles Lakers')
        fallback_response = mock.Mock(data=[lakers])

        mock_client = mock.Mock()
        mock_client.nba.teams.list.side_effect = [
            TypeError("NBATeamsAPI.list() got an unexpected keyword argument 'per_page'"),
            fallback_response,
        ]

        with mock.patch.object(services, '_build_bdl_client', return_value=mock_client):
            choices = services.get_team_choices()

        self.assertEqual(choices, [('14', 'Los Angeles Lakers')])
        self.assertEqual(mock_client.nba.teams.list.call_count, 2)
        first_call, second_call = mock_client.nba.teams.list.call_args_list
        self.assertEqual(first_call.kwargs, {'per_page': 100})
        self.assertEqual(second_call.kwargs, {})

    def test_ignores_teams_without_conference_or_division(self) -> None:
        active = mock.Mock(
            id=14,
            full_name='Los Angeles Lakers',
            conference='West',
            division='Pacific',
        )
        inactive = mock.Mock(
            id=55,
            full_name='Baltimore Bullets',
            conference='',
            division=None,
        )

        response = mock.Mock(data=[active, inactive])
        mock_client = mock.Mock()
        mock_client.nba.teams.list.return_value = response

        with mock.patch.object(services, '_build_bdl_client', return_value=mock_client):
            choices = services.get_team_choices()

        self.assertEqual(choices, [('14', 'Los Angeles Lakers')])


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

        response = mock.Mock(data=[scheduled_game, completed_game])

        with mock.patch.object(services.timezone, 'now', return_value=fake_now):
            with mock.patch.object(services, '_build_bdl_client') as mock_builder:
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
        self.assertEqual(game['home_team']['full_name'], 'Los Angeles Lakers')
        self.assertEqual(game['home_team']['abbreviation'], 'LAL')
        self.assertEqual(game['away_team']['full_name'], 'Boston Celtics')
        self.assertEqual(game['away_team']['abbreviation'], 'BOS')
        self.assertEqual(game['arena'], 'Crypto.com Arena')
        self.assertIsNotNone(game['game_time'].tzinfo)

        mock_builder.assert_called_once()
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
            with mock.patch.object(services, '_build_bdl_client') as mock_builder:
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
            with mock.patch.object(services, '_build_bdl_client') as mock_builder:
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

        with mock.patch.object(services, '_build_bdl_client') as mock_builder:
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


class GetPlayerChoicesTests(TestCase):
    def setUp(self) -> None:
        services.get_player_choices.cache_clear()
        return super().setUp()

    def tearDown(self) -> None:
        services.get_player_choices.cache_clear()
        return super().tearDown()

    def test_fetches_active_players_across_pages(self) -> None:
        first_player = mock.Mock(
            id=23,
            first_name='LeBron',
            last_name='James',
            team=mock.Mock(abbreviation='LAL'),
        )
        second_player = mock.Mock(
            id=30,
            first_name='Stephen',
            last_name='Curry',
            team=mock.Mock(abbreviation='GSW'),
        )

        first_response = mock.Mock(
            data=[first_player],
            meta=mock.Mock(next_cursor=101),
        )
        second_response = mock.Mock(
            data=[second_player],
            meta=mock.Mock(next_cursor=None),
        )

        mock_client = mock.Mock()
        mock_client.nba.players.list_active.side_effect = [first_response, second_response]

        with mock.patch.object(services, '_build_bdl_client', return_value=mock_client):
            choices = services.get_player_choices()

        self.assertEqual(
            choices,
            [
                ('23', 'LeBron James (LAL)'),
                ('30', 'Stephen Curry (GSW)'),
            ],
        )

        self.assertEqual(mock_client.nba.players.list_active.call_count, 2)
        first_call, second_call = mock_client.nba.players.list_active.call_args_list
        self.assertEqual(first_call.kwargs, {'per_page': 100})
        self.assertEqual(second_call.kwargs, {'per_page': 100, 'cursor': 101})

    def test_supports_dict_meta_with_next_link(self) -> None:
        first_player = mock.Mock(
            id=11,
            first_name='Jalen',
            last_name='Brunson',
            team=mock.Mock(abbreviation='NYK'),
        )
        second_player = mock.Mock(
            id=12,
            first_name='Julius',
            last_name='Randle',
            team=mock.Mock(abbreviation='NYK'),
        )

        first_response = mock.Mock(
            data=[first_player],
            meta={'next': '/nba/v1/players/active?cursor=200'},
        )
        second_response = mock.Mock(
            data=[second_player],
            meta={'next': None},
        )

        mock_client = mock.Mock()
        mock_client.nba.players.list_active.side_effect = [first_response, second_response]

        with mock.patch.object(services, '_build_bdl_client', return_value=mock_client):
            choices = services.get_player_choices()

        self.assertEqual(
            choices,
            [
                ('11', 'Jalen Brunson (NYK)'),
                ('12', 'Julius Randle (NYK)'),
            ],
        )

        self.assertEqual(mock_client.nba.players.list_active.call_count, 2)
        first_call, second_call = mock_client.nba.players.list_active.call_args_list
        self.assertEqual(first_call.kwargs, {'per_page': 100})
        self.assertEqual(second_call.kwargs, {'per_page': 100, 'cursor': 200})

    def test_handles_api_errors(self) -> None:
        mock_client = mock.Mock()
        mock_client.nba.players.list_active.side_effect = exceptions.BallDontLieException('boom')

        with mock.patch.object(services, '_build_bdl_client', return_value=mock_client):
            with self.assertLogs('hooptipp.predictions.services', level='ERROR') as captured:
                choices = services.get_player_choices()

        self.assertEqual(choices, [])
        self.assertTrue(any('Unable to fetch player list from BallDontLie API.' in entry for entry in captured.output))


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
            'home_team': {
                'id': 1,
                'full_name': 'Denver Nuggets',
                'name': 'Denver Nuggets',
                'abbreviation': 'DEN',
                'city': 'Denver',
                'conference': 'West',
                'division': 'Northwest',
            },
            'away_team': {
                'id': 2,
                'full_name': 'Phoenix Suns',
                'name': 'Phoenix Suns',
                'abbreviation': 'PHX',
                'city': 'Phoenix',
                'conference': 'West',
                'division': 'Pacific',
            },
            'arena': 'Ball Arena',
        }

        with mock.patch(
            'hooptipp.predictions.services.fetch_upcoming_week_games',
            return_value=(timezone.localdate(auto_game_payload['game_time']), [auto_game_payload]),
        ):
            tip_type, events, week_start = services.sync_weekly_games()

        self.assertIsNotNone(tip_type)
        self.assertEqual(week_start, timezone.localdate(auto_game_payload['game_time']))
        returned_ids = {event.scheduled_game.nba_game_id for event in events}
        self.assertSetEqual(returned_ids, {'AUTO-1', 'MANUAL-1'})
        manual_game.refresh_from_db()
        self.assertTrue(manual_game.is_manual)
        tip_type.refresh_from_db()
        self.assertEqual(
            tip_type.deadline,
            min(event.deadline for event in events),
        )

        auto_event = next(event for event in events if event.scheduled_game.nba_game_id == 'AUTO-1')
        self.assertEqual(auto_event.selection_mode, PredictionEvent.SelectionMode.CURATED)
        self.assertEqual(auto_event.options.count(), 2)

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
            tip_type, events, week_start = services.sync_weekly_games()

        self.assertIsNotNone(tip_type)
        self.assertEqual(week_start, timezone.localdate(base_time))
        self.assertEqual([event.scheduled_game.nba_game_id for event in events], ['MANUAL-ONLY'])
        manual_game.refresh_from_db()
        self.assertTrue(manual_game.is_manual)


class SyncTeamsTests(DjangoTestCase):
    def setUp(self) -> None:
        services._BDL_CLIENT_CACHE.clear()
        services.get_team_choices.cache_clear()
        return super().setUp()

    def test_sync_teams_creates_updates_and_removes(self) -> None:
        existing = NbaTeam.objects.create(
            balldontlie_id=1,
            name='Old Lakers',
            abbreviation='OLD',
            city='Old City',
            conference='Old',
            division='Old',
        )
        manual = NbaTeam.objects.create(
            name='Minnesota',
            abbreviation='MIN',
            city='Minneapolis',
        )
        stale = NbaTeam.objects.create(
            balldontlie_id=99,
            name='Stale Team',
        )

        lakers = SimpleNamespace(
            id=1,
            full_name='Los Angeles Lakers',
            name='Lakers',
            abbreviation='LAL',
            city='Los Angeles',
            conference='West',
            division='Pacific',
        )
        wolves = SimpleNamespace(
            id=30,
            full_name='Minnesota Timberwolves',
            name='Timberwolves',
            abbreviation='MIN',
            city='Minneapolis',
            conference='West',
            division='Northwest',
        )

        heat = SimpleNamespace(
            id=17,
            full_name='Miami Heat',
            name='Heat',
            abbreviation='MIA',
            city='Miami',
            conference='East',
            division='Southeast',
        )

        response = SimpleNamespace(data=[lakers, wolves, heat])
        mock_client = mock.Mock()
        mock_client.nba.teams.list.return_value = response

        with mock.patch.object(services, '_build_bdl_client', return_value=mock_client):
            result = services.sync_teams()

        self.assertEqual(result.created, 1)
        self.assertEqual(result.updated, 2)
        self.assertEqual(result.removed, 1)

        mock_client.nba.teams.list.assert_called_once_with(per_page=100)

        existing.refresh_from_db()
        self.assertEqual(existing.name, 'Los Angeles Lakers')
        self.assertEqual(existing.abbreviation, 'LAL')
        self.assertEqual(existing.conference, 'West')
        self.assertEqual(existing.division, 'Pacific')

        manual.refresh_from_db()
        self.assertEqual(manual.balldontlie_id, 30)
        self.assertEqual(manual.name, 'Minnesota Timberwolves')

        self.assertTrue(NbaTeam.objects.filter(balldontlie_id=17, name='Miami Heat').exists())

        self.assertFalse(NbaTeam.objects.filter(pk=stale.pk).exists())

    def test_sync_teams_retries_without_per_page(self) -> None:
        lakers = SimpleNamespace(
            id=1,
            full_name='Los Angeles Lakers',
            abbreviation='LAL',
            conference='West',
            division='Pacific',
        )
        response = SimpleNamespace(data=[lakers])

        mock_client = mock.Mock()
        mock_client.nba.teams.list.side_effect = [
            TypeError("NBATeamsAPI.list() got an unexpected keyword argument 'per_page'"),
            response,
        ]

        with mock.patch.object(services, '_build_bdl_client', return_value=mock_client):
            result = services.sync_teams()

        self.assertTrue(result.changed)
        self.assertEqual(result.created, 1)
        self.assertEqual(result.updated, 0)
        self.assertEqual(result.removed, 0)

        self.assertEqual(mock_client.nba.teams.list.call_count, 2)
        first_call, second_call = mock_client.nba.teams.list.call_args_list
        self.assertEqual(first_call.kwargs, {'per_page': 100})
        self.assertEqual(second_call.kwargs, {})

    def test_sync_teams_handles_api_errors(self) -> None:
        mock_client = mock.Mock()
        mock_client.nba.teams.list.side_effect = exceptions.BallDontLieException('boom')

        with mock.patch.object(services, '_build_bdl_client', return_value=mock_client):
            result = services.sync_teams()

        self.assertFalse(result.changed)
        self.assertEqual(result.created, 0)
        self.assertEqual(result.updated, 0)
        self.assertEqual(result.removed, 0)

        mock_client.nba.teams.list.assert_called_once_with(per_page=100)

    def test_sync_teams_skips_inactive_teams(self) -> None:
        inactive = NbaTeam.objects.create(
            balldontlie_id=55,
            name='Baltimore Bullets',
            abbreviation='BAL',
            city='Baltimore',
        )

        lakers = SimpleNamespace(
            id=1,
            full_name='Los Angeles Lakers',
            name='Lakers',
            abbreviation='LAL',
            city='Los Angeles',
            conference='West',
            division='Pacific',
        )
        bullets = SimpleNamespace(
            id=55,
            full_name='Baltimore Bullets',
            name='Bullets',
            abbreviation='BAL',
            city='Baltimore',
            conference='',
            division=None,
        )

        response = SimpleNamespace(data=[lakers, bullets])
        mock_client = mock.Mock()
        mock_client.nba.teams.list.return_value = response

        with mock.patch.object(services, '_build_bdl_client', return_value=mock_client):
            result = services.sync_teams()

        self.assertEqual(result.created, 1)
        self.assertEqual(result.updated, 0)
        self.assertEqual(result.removed, 1)

        self.assertTrue(NbaTeam.objects.filter(balldontlie_id=1).exists())
        self.assertFalse(NbaTeam.objects.filter(pk=inactive.pk).exists())
        self.assertFalse(NbaTeam.objects.filter(balldontlie_id=55).exists())


class SyncActivePlayersTests(DjangoTestCase):
    def setUp(self) -> None:
        services._BDL_CLIENT_CACHE.clear()
        return super().setUp()

    def test_sync_active_players_creates_updates_and_removes(self) -> None:
        existing_team = NbaTeam.objects.create(
            balldontlie_id=14,
            name='Old Lakers',
            abbreviation='OLD',
            city='Old City',
        )
        existing_player = NbaPlayer.objects.create(
            balldontlie_id=23,
            first_name='Old',
            last_name='Name',
            display_name='Old Name',
            position='G',
            team=existing_team,
        )
        stale_player = NbaPlayer.objects.create(
            balldontlie_id=77,
            first_name='Stale',
            last_name='Player',
            display_name='Stale Player',
            position='C',
        )

        lakers_team = SimpleNamespace(
            id=14,
            full_name='Los Angeles Lakers',
            name='Lakers',
            abbreviation='LAL',
            city='Los Angeles',
            conference='West',
            division='Pacific',
        )
        bulls_team = SimpleNamespace(
            id=4,
            full_name='Chicago Bulls',
            name='Bulls',
            abbreviation='CHI',
            city='Chicago',
            conference='East',
            division='Central',
        )

        lebron = SimpleNamespace(
            id=23,
            first_name='LeBron',
            last_name='James',
            position='F',
            team=lakers_team,
        )
        davis = SimpleNamespace(
            id=3,
            first_name='Anthony',
            last_name='Davis',
            position='C',
            team=lakers_team,
        )
        caruso = SimpleNamespace(
            id=6,
            first_name='Alex',
            last_name='Caruso',
            position='G',
            team=bulls_team,
        )

        first_page = SimpleNamespace(
            data=[lebron, davis],
            meta=SimpleNamespace(next_cursor=50),
        )
        second_page = SimpleNamespace(
            data=[caruso],
            meta=SimpleNamespace(next_cursor=None),
        )

        mock_client = mock.Mock()
        mock_client.nba.players.list_active.side_effect = [first_page, second_page]

        with mock.patch.object(services, '_build_bdl_client', return_value=mock_client):
            result = services.sync_active_players(throttle_seconds=0)

        self.assertEqual(result.created, 2)
        self.assertEqual(result.updated, 1)
        self.assertEqual(result.removed, 1)

        mock_client.nba.players.list_active.assert_has_calls(
            [
                mock.call(per_page=100),
                mock.call(per_page=100, cursor=50),
            ]
        )

        existing_player.refresh_from_db()
        self.assertEqual(existing_player.display_name, 'LeBron James')
        self.assertEqual(existing_player.position, 'F')
        self.assertIsNotNone(existing_player.team)
        self.assertEqual(existing_player.team.abbreviation, 'LAL')

        self.assertFalse(NbaPlayer.objects.filter(pk=stale_player.pk).exists())
        self.assertEqual(NbaPlayer.objects.count(), 3)

        lakers_team_obj = NbaTeam.objects.get(balldontlie_id=14)
        self.assertEqual(lakers_team_obj.name, 'Los Angeles Lakers')
        self.assertEqual(lakers_team_obj.abbreviation, 'LAL')

        bulls_team_obj = NbaTeam.objects.get(balldontlie_id=4)
        self.assertEqual(bulls_team_obj.name, 'Chicago Bulls')
        self.assertEqual(bulls_team_obj.abbreviation, 'CHI')

    def test_sync_active_players_supports_dict_meta(self) -> None:
        lebron = SimpleNamespace(
            id=23,
            first_name='LeBron',
            last_name='James',
            position='F',
        )
        davis = SimpleNamespace(
            id=3,
            first_name='Anthony',
            last_name='Davis',
            position='C',
        )

        first_page = SimpleNamespace(
            data=[lebron],
            meta={'next': '/nba/v1/players/active?cursor=50'},
        )
        second_page = SimpleNamespace(
            data=[davis],
            meta={'next': None},
        )

        mock_client = mock.Mock()
        mock_client.nba.players.list_active.side_effect = [first_page, second_page]

        with mock.patch.object(services, '_build_bdl_client', return_value=mock_client):
            result = services.sync_active_players(throttle_seconds=0)

        self.assertEqual(result.created, 2)
        self.assertEqual(result.updated, 0)
        self.assertEqual(result.removed, 0)

        mock_client.nba.players.list_active.assert_has_calls(
            [
                mock.call(per_page=100),
                mock.call(per_page=100, cursor=50),
            ]
        )

        self.assertEqual(NbaPlayer.objects.count(), 2)
        self.assertTrue(NbaPlayer.objects.filter(display_name='LeBron James').exists())
        self.assertTrue(NbaPlayer.objects.filter(display_name='Anthony Davis').exists())

    def test_sync_active_players_handles_api_errors(self) -> None:
        mock_client = mock.Mock()
        mock_client.nba.players.list_active.side_effect = exceptions.BallDontLieException('boom')

        with mock.patch.object(services, '_build_bdl_client', return_value=mock_client):
            result = services.sync_active_players(throttle_seconds=0)

        self.assertFalse(result.changed)
        self.assertEqual(result.created, 0)
        self.assertEqual(result.updated, 0)
        self.assertEqual(result.removed, 0)
