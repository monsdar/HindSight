# DBB (German Basketball) Package

The DBB package provides German amateur basketball match predictions for the HindSight platform. It integrates with the SLAPI API to fetch leagues, teams, and matches from German basketball associations (Verbände).

## Features

- **League Tracking**: Track specific leagues from German basketball associations
- **Team Filtering**: Only track matches for selected teams within leagues
- **Automatic Match Import**: Fetch upcoming matches automatically from SLAPI
- **Result Processing**: Automatically resolve match outcomes and score predictions
- **Custom Admin Interface**: User-friendly workflow for selecting leagues and teams

## Configuration

### Environment Variables

Set the SLAPI API token in your environment:

```bash
SLAPI_API_TOKEN=your_token_here
```

The SLAPI API is available at: https://slapi.up.railway.app/docs

## Admin Workflow

### 1. Select a Verband

Navigate to **Admin > DBB > Select Verband** to view available basketball associations (Verbände).

### 2. Search for Clubs and Select Leagues

Enter a club search term (e.g., "Bierden-Bassen") to find all leagues that club participates in within the selected Verband. The system will:
- Fetch all leagues for the club
- Display teams from each league that match your search term
- Allow you to select which leagues and teams to track

### 3. Import Selected Leagues

- Check the leagues you want to track
- Select specific teams within each league (multiple teams per league supported)
- Click "Import Selected Leagues and Teams" to add them to your tracked leagues

### 4. Manage Tracked Leagues

View and manage your tracked leagues at **Admin > DBB > Tracked Leagues**:
- Enable/disable tracking for leagues
- View associated teams
- Manually trigger match sync with "Sync matches" action

## Management Commands

### Update Matches

Fetch and update matches for all tracked leagues:

```bash
python manage.py update_dbb_matches
```

Options:
- `--dry-run`: Show what would be updated without making changes
- `--league-id ID`: Only update matches for a specific league

This command should be run periodically (e.g., daily via cron) to:
- Import newly scheduled matches
- Update match times if rescheduled
- Handle cancelled matches

### Process Results

Check completed matches and create outcomes:

```bash
python manage.py process_dbb_results
```

Options:
- `--dry-run`: Show what would be processed without making changes
- `--hours-back N`: Look back N hours for completed matches (default: 72)

This command should be run regularly (e.g., every few hours) to automatically:
- Fetch match results from SLAPI
- Create EventOutcome records
- Score user predictions
- Update leaderboards

## Architecture

### Models

- **`TrackedLeague`**: Stores leagues selected by admin for tracking
- **`TrackedTeam`**: Stores specific teams to track within leagues
- **`DbbMatch`**: Stores individual match information

### Event Source

`DbbEventSource` implements the EventSource interface:
- Creates team Options from tracked teams
- Syncs matches as PredictionEvents
- Filters matches to only include tracked teams

### Card Renderer

`DbbCardRenderer` provides custom templates for DBB matches:
- Event card: `dbb/cards/match.html`
- Result card: `dbb/cards/match_result.html`

## Team Matching

When importing matches, the system:
1. Fetches all matches for tracked leagues
2. Filters matches where home_team or away_team matches any tracked team name
3. Creates PredictionEvents only for matching teams

This ensures the club only sees predictions for their own teams, even when multiple teams from different clubs play in the same league.

## Testing

Run the DBB tests:

```bash
python manage.py test hooptipp.dbb
```

Test coverage includes:
- Model validation and relationships
- SLAPI client API calls (mocked)
- Admin views and workflows
- Event source sync operations
- Card renderer template selection
- Management commands

## Example Use Case

A basketball club "BG Bierden-Bassen Achim" wants to let fans predict their team's matches:

1. Admin searches for "Bierden-Bassen" in their Verband
2. System finds all leagues the club participates in
3. Admin selects leagues and teams (e.g., "Herren 1", "Herren 2")
4. System imports upcoming matches for those teams
5. Fans make predictions on the home page
6. Results are automatically processed after matches conclude
7. Points are awarded and leaderboard updates

## Future Enhancements

- Live score updates during matches
- Team statistics and standings
- Player-based predictions
- Multi-club support for league-wide predictions
- Push notifications for match reminders

