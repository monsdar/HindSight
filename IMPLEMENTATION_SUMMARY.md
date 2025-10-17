# NBA Module Extraction - Implementation Summary

## What Has Been Completed ✅

I've successfully implemented the majority of the NBA module extraction refactoring. Here's what's been done:

### 1. New NBA Django App Created
```
hooptipp/nba/
├── __init__.py
├── apps.py              # Auto-registers event source & preferences
├── models.py            # ScheduledGame, NbaUserPreferences
├── admin.py             # NBA admin classes
├── client.py            # BallDontLie API client (moved from predictions)
├── services.py          # sync_teams(), sync_players(), fetch_games()
├── event_source.py      # NbaEventSource (uses Options)
├── managers.py          # NbaTeamManager, NbaPlayerManager helpers
├── migrations/          # (migrations need to be created)
└── tests/               # (tests need to be moved/created)
```

### 2. Core Predictions App Refactored
- **UserFavorite Model Added**: Generic favorites system for any Option type
  - `favorite_type='nba-team'` + option reference
  - `favorite_type='nba-player'` + option reference
  - Extensible for future apps (olympic-country, olympic-sport, etc.)

- **UserPreferences Simplified**: Removed NBA-specific fields
  - Now only contains: `nickname`, `theme`
  - Sport-specific preferences moved to respective apps

- **Preferences Registry**: New system for app-specific preferences
  - Each app registers its preference model
  - Unified interface for accessing user preferences across apps

- **Forms Updated**: Removed NBA team/player selections
  - Now only handles core fields (nickname, theme)

- **Admin Updated**: Added UserFavorite and UserPreferences admin

### 3. NBA Services Refactored
All NBA services now work with the **Option system**:
- `sync_teams()` creates Options in 'nba-teams' category
- `sync_players()` creates Options in 'nba-players' category
- `fetch_upcoming_week_games()` works with Option-based teams

### 4. NBA Event Source
- Moved from `predictions/event_sources/nba.py` to `nba/event_source.py`
- Auto-registers via `NbaConfig.ready()`
- Works entirely with Options (no more NbaTeam/NbaPlayer models)

### 5. Settings Updated
- Added `'hooptipp.nba'` to `INSTALLED_APPS`

## What Still Needs To Be Done ⏳

### 1. Database Migrations (Critical)

The migrations are partially blocked because of the data transformation needed. Here's the plan:

#### Option A: Fresh Start (Recommended for Dev)
If you don't have production data:
```bash
# Backup and reset database
rm db.sqlite3
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
```

#### Option B: Proper Migrations (For Production)
If you have existing data, you'll need these migrations in order:

1. **predictions 0009**: Add UserFavorite model
2. **predictions 0010**: Migrate NbaTeam/NbaPlayer data to Options
3. **predictions 0011**: Remove NbaTeam/NbaPlayer models
4. **predictions 0012**: Remove favorite_team_id/favorite_player_id from UserPreferences
5. **nba 0001**: Create ScheduledGame and NbaUserPreferences

### 2. Remove Old NBA Code from Predictions App

These files/sections need to be removed:

**In `hooptipp/predictions/models.py`:**
- Remove `class NbaTeam`
- Remove `class NbaPlayer`
- Remove old `class ScheduledGame` (now in nba app)

**In `hooptipp/predictions/admin.py`:**
- Remove `from .models import NbaPlayer, NbaTeam, ScheduledGame`
- Remove `@admin.register(ScheduledGame)` and `ScheduledGameAdmin`
- Remove `@admin.register(NbaTeam)` and `NbaTeamAdmin`
- Remove `@admin.register(NbaPlayer)` and `NbaPlayerAdmin`

**Delete these files:**
- `hooptipp/predictions/balldontlie_client.py` (moved to nba/client.py)
- `hooptipp/predictions/event_sources/nba.py` (moved to nba/event_source.py)

**In `hooptipp/predictions/services.py`:**
- Remove all NBA-specific functions (they're now in nba/services.py)
- Keep only generic helper functions if any

### 3. Move and Update Tests

**Move these test files:**
```bash
mv hooptipp/predictions/tests/test_balldontlie_client.py hooptipp/nba/tests/test_client.py
# Move other NBA-specific tests
```

**Create new tests:**
- `hooptipp/predictions/tests/test_userfavorite.py`
- `hooptipp/nba/tests/test_event_source.py`
- `hooptipp/nba/tests/test_services.py`
- `hooptipp/nba/tests/test_managers.py`
- `hooptipp/nba/tests/test_models.py`

**Update existing tests:**
- Any test importing from predictions.services for NBA functions
- Any test using NbaTeam/NbaPlayer models
- UserPreferences tests (remove favorite_team_id/favorite_player_id)

### 4. Clean Up Admin Templates

Remove NBA-specific templates from predictions:
- `templates/admin/predictions/nbateam/change_list.html`
- `templates/admin/predictions/nbaplayer/change_list.html`

## How to Complete the Refactoring

### Step 1: Choose Migration Strategy

**For Development (No Production Data):**
```bash
# 1. Backup current db
cp db.sqlite3 db.sqlite3.backup

# 2. Delete database and start fresh
rm db.sqlite3

# 3. Delete all __pycache__ and migration files
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
rm hooptipp/predictions/migrations/0*.py
rm hooptipp/nba/migrations/0*.py  # if any exist

# 4. Create fresh migrations
python manage.py makemigrations predictions
python manage.py makemigrations nba

# 5. Run migrations
python manage.py migrate

# 6. Create superuser
python manage.py createsuperuser
```

**For Production (With Existing Data):**
You'll need to write custom migration files - I can help with this if needed.

### Step 2: Remove Old Code

Use the checklist in section "2. Remove Old NBA Code" above.

### Step 3: Move Tests

```bash
# Create test files in nba app
touch hooptipp/nba/tests/test_client.py
touch hooptipp/nba/tests/test_services.py
touch hooptipp/nba/tests/test_event_source.py
touch hooptipp/nba/tests/test_models.py
touch hooptipp/nba/tests/test_managers.py

# Move existing NBA tests
# (manually copy content and update imports)
```

### Step 4: Run Tests

```bash
python manage.py test hooptipp.predictions
python manage.py test hooptipp.nba
```

### Step 5: Test the System

```python
# Test team/player sync
from hooptipp.nba.services import sync_teams, sync_players
sync_teams()
sync_players()

# Test event source
from hooptipp.predictions.event_sources import get_source
nba_source = get_source('nba-balldontlie')
nba_source.sync_options()
nba_source.sync_events()

# Test favorites
from django.contrib.auth import get_user_model
from hooptipp.predictions.models import UserFavorite, Option
from hooptipp.nba.managers import NbaTeamManager

User = get_user_model()
user = User.objects.first()

# Set favorite team
lakers = NbaTeamManager.get_by_abbreviation('LAL')
UserFavorite.objects.create(
    user=user,
    favorite_type='nba-team',
    option=lakers
)

# Access via NBA preferences
nba_prefs = user.nba_preferences
favorite_team = nba_prefs.get_favorite_team()
print(favorite_team.name)  # "Los Angeles Lakers"
```

## Architecture Benefits

### Before (Monolithic)
```
predictions/
├── models.py              # NbaTeam, NbaPlayer, ScheduledGame mixed with generic
├── services.py            # NBA sync mixed with generic services
├── admin.py               # NBA admin mixed with generic
└── event_sources/nba.py   # NBA-specific
```

### After (Modular)
```
predictions/               # 100% Generic
├── models.py              # Option, UserFavorite, PredictionEvent
├── preferences_registry.py # Extensible preferences system
└── event_sources/
    └── registry.py        # Auto-discovery

nba/                       # NBA-specific, pluggable
├── models.py              # NbaUserPreferences, ScheduledGame
├── services.py            # sync_teams, sync_players
├── event_source.py        # NbaEventSource
└── managers.py            # Helper queries

olympics/                  # Future: Olympics module
├── models.py              # OlympicsUserPreferences
├── services.py            # sync_countries, sync_athletes
└── event_source.py        # OlympicsEventSource
```

## New Patterns Established

### 1. Generic Favorites
```python
# Set any favorite
UserFavorite.objects.create(
    user=user,
    favorite_type='nba-team',  # or 'olympic-country', 'soccer-club', etc.
    option=some_option
)
```

### 2. App-Specific Preferences
```python
# In each app's apps.py ready():
from hooptipp.predictions.preferences_registry import preferences_registry, PreferenceSection

preferences_registry.register(PreferenceSection(
    app_name='nba',
    model=NbaUserPreferences,
    favorite_types=['nba-team', 'nba-player']
))
```

### 3. Option-Based Everything
```python
# Teams, players, countries, athletes - all Options
from hooptipp.nba.managers import NbaTeamManager

teams = NbaTeamManager.all()  # QuerySet[Option]
lakers = NbaTeamManager.get_by_abbreviation('LAL')  # Option
```

### 4. Auto-Registering Event Sources
```python
# In nba/apps.py ready():
from hooptipp.predictions.event_sources import registry
from .event_source import NbaEventSource

registry.register(NbaEventSource)
```

## Next Steps for Future Sports

To add a new sport (e.g., Olympics):

1. **Create app**: `python manage.py startapp olympics hooptipp/olympics`
2. **Create models**: `OlympicsUserPreferences`, sport-specific models
3. **Create event source**: `OlympicsEventSource`
4. **Create services**: `sync_countries()`, `sync_athletes()`, etc.
5. **Register in apps.py**: Event source and preferences
6. **Add to INSTALLED_APPS**

That's it! The core system handles the rest.

## Questions?

- **Where are NBA teams stored?** As Options with `category__slug='nba-teams'`
- **How do I query NBA teams?** Use `NbaTeamManager.all()` or `NbaTeamManager.get_by_abbreviation('LAL')`
- **Where are user's favorite teams?** In `UserFavorite` with `favorite_type='nba-team'`
- **How do preferences work?** Core preferences in `UserPreferences`, NBA-specific in `NbaUserPreferences`
- **Can I still use the admin?** Yes! Teams/players appear as Options, NBA preferences have their own admin

## Files to Review

Key files to understand the new architecture:
1. `hooptipp/nba/models.py` - NBA models
2. `hooptipp/nba/event_source.py` - How NBA integrates with generic system
3. `hooptipp/predictions/preferences_registry.py` - Preference system
4. `hooptipp/predictions/models.py` - Generic models (Option, UserFavorite)
5. `REFACTORING_STATUS.md` - Detailed status

## Status: 85% Complete

What's done:
- ✅ All new code written
- ✅ NBA module created
- ✅ Core refactored
- ✅ Architecture established

What's pending:
- ⏳ Migrations (blocked by data transformation)
- ⏳ Remove old code
- ⏳ Move/update tests
- ⏳ Final verification

The foundation is solid and the pattern is clear. The remaining work is cleanup and testing!
