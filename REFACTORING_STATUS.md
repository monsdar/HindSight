# NBA Module Extraction - Refactoring Status

## Overview
This document tracks the progress of extracting NBA-specific code into its own Django app module, making the core predictions system fully generic and extensible.

## Completed ✅

### 1. NBA App Structure
- ✅ Created `hooptipp/nba/` directory structure
- ✅ Created `hooptipp/nba/apps.py` with NbaConfig
- ✅ Created `hooptipp/nba/__init__.py`
- ✅ Created `hooptipp/nba/migrations/` directory
- ✅ Created `hooptipp/nba/tests/` directory

### 2. Core Models Refactored
- ✅ Added `UserFavorite` model to predictions app (generic favorites system)
- ✅ Refactored `UserPreferences` to remove NBA-specific fields (`favorite_team_id`, `favorite_player_id`)
- ✅ Created `PreferencesRegistry` system for app-specific preferences

### 3. NBA Models Created
- ✅ Created `NbaUserPreferences` model with NBA-specific settings
- ✅ Created `ScheduledGame` model in NBA app with Option foreign keys
- ✅ Added helper methods to NbaUserPreferences for accessing favorites via UserFavorite

### 4. NBA Managers and Helpers
- ✅ Created `hooptipp/nba/managers.py` with NbaTeamManager and NbaPlayerManager
- ✅ Helper methods for querying NBA teams/players as Options

### 5. NBA Client
- ✅ Moved `balldontlie_client.py` to `hooptipp/nba/client.py`

### 6. NBA Services
- ✅ Created `hooptipp/nba/services.py` with Option-based sync functions
- ✅ `sync_teams()` - creates/updates Options for NBA teams
- ✅ `sync_players()` - creates/updates Options for NBA players
- ✅ `fetch_upcoming_week_games()` - fetches upcoming games

### 7. NBA Event Source
- ✅ Created `hooptipp/nba/event_source.py` with NbaEventSource
- ✅ Updated to work with Option system
- ✅ Removed from predictions/event_sources/nba.py (old location)

### 8. NBA Admin
- ✅ Created `hooptipp/nba/admin.py`
- ✅ ScheduledGameAdmin
- ✅ NbaUserPreferencesAdmin with favorites display
- ✅ Created admin template `templates/admin/nba/options_changelist.html`

### 9. Core Predictions Updates
- ✅ Added UserFavorite and UserPreferences admin classes
- ✅ Updated forms.py to remove NBA-specific fields
- ✅ Updated settings.py to include `hooptipp.nba` in INSTALLED_APPS
- ✅ Removed NBA event source registration from predictions/event_sources/__init__.py

## In Progress 🚧

### 10. Database Migrations
**Status**: Need to complete

**Required Migrations:**

#### predictions app:
1. Add `UserFavorite` model
2. Remove `favorite_team_id` and `favorite_player_id` from `UserPreferences`
3. Data migration: Move NbaTeam records to Option (category='nba-teams')
4. Data migration: Move NbaPlayer records to Option (category='nba-players')
5. Remove `NbaTeam` and `NbaPlayer` models
6. Remove `ScheduledGame` model (moved to NBA app)

#### nba app:
1. Initial migration with `ScheduledGame` and `NbaUserPreferences` models

**Current Issue**: 
- `PredictionOption.option` field needs data migration before making it non-nullable
- Need manual migration files to handle data transformation properly

## Pending ⏳

### 11. Remove Old NBA Code from Predictions App
- ❌ Remove `NbaTeam` model from predictions/models.py
- ❌ Remove `NbaPlayer` model from predictions/models.py  
- ❌ Remove old `ScheduledGame` model from predictions/models.py
- ❌ Remove `NbaTeamAdmin` from predictions/admin.py
- ❌ Remove `NbaPlayerAdmin` from predictions/admin.py
- ❌ Remove old `ScheduledGameAdmin` from predictions/admin.py
- ❌ Remove `balldontlie_client.py` from predictions/
- ❌ Remove NBA functions from predictions/services.py
- ❌ Remove event_sources/nba.py

### 12. Update Tests
- ❌ Move NBA-specific tests to nba/tests/
- ❌ Update test imports
- ❌ Create new tests for:
  - UserFavorite model
  - NbaUserPreferences model
  - NBA managers
  - NBA event source
  - Preference registry
- ❌ Update existing tests to work with new structure

### 13. Update Admin Templates
- ❌ Remove NBA-specific admin templates from predictions/
- ❌ Update any remaining references

### 14. Final Verification
- ❌ Run full test suite
- ❌ Verify admin works
- ❌ Test event source syncing
- ❌ Test predictions flow end-to-end

## Migration Strategy

### Step 1: Create Nullable Option Reference
```python
# predictions 0009: Add UserFavorite, make PredictionOption.option nullable temporarily
operations = [
    migrations.CreateModel(
        name='UserFavorite',
        fields=[...],
    ),
    migrations.AlterField(
        model_name='predictionoption',
        name='option',
        field=models.ForeignKey(
            null=True,  # Temporarily nullable
            blank=True,
            ...
        ),
    ),
]
```

### Step 2: Migrate NBA Data to Options
```python
# predictions 0010: Migrate NbaTeam and NbaPlayer to Options
def migrate_nba_to_options(apps, schema_editor):
    # Create OptionCategories
    # Migrate NbaTeam -> Option
    # Migrate NbaPlayer -> Option
    # Update PredictionOption references
```

### Step 3: Remove NBA Models
```python
# predictions 0011: Remove NbaTeam, NbaPlayer, old ScheduledGame
# predictions 0012: Remove favorite_team_id, favorite_player_id from UserPreferences
```

### Step 4: NBA App Initial Migration
```python
# nba 0001: Create ScheduledGame and NbaUserPreferences
```

### Step 5: Make Option Non-Nullable
```python
# predictions 0013: Make PredictionOption.option non-nullable
```

## Architecture Summary

### Core Predictions (Generic)
```
hooptipp/predictions/
├── models.py              # Option, OptionCategory, PredictionEvent, UserFavorite, UserPreferences
├── admin.py               # Generic admin classes
├── views.py               # Generic views
├── forms.py               # Generic forms (theme, nickname)
├── scoring_service.py     # Generic scoring
├── lock_service.py        # Generic locking
├── preferences_registry.py # App preference registration
└── event_sources/
    ├── base.py            # EventSource base
    └── registry.py        # Source registry
```

### NBA Module (Sport-Specific)
```
hooptipp/nba/
├── models.py              # ScheduledGame, NbaUserPreferences
├── admin.py               # NBA admin
├── client.py              # BallDontLie API client
├── services.py            # NBA sync services
├── event_source.py        # NbaEventSource
├── managers.py            # NBA Option managers
└── tests/                 # NBA tests
```

### Future Modules
```
hooptipp/olympics/         # Olympics predictions
hooptipp/soccer/           # Soccer predictions
etc.
```

## Next Steps

1. **Create manual migration files** for data transformation
2. **Run migrations** in correct order
3. **Remove old NBA code** from predictions app
4. **Move and update tests**
5. **Run full test suite**
6. **Document the pattern** for future sport modules

## Testing the Refactoring

```bash
# After migrations are complete:
python manage.py migrate
python manage.py test

# Test NBA sync:
python manage.py shell
>>> from hooptipp.nba.services import sync_teams, sync_players
>>> sync_teams()
>>> sync_players()

# Test event source:
>>> from hooptipp.predictions.event_sources import get_source
>>> nba = get_source('nba-balldontlie')
>>> nba.sync_options()
>>> nba.sync_events()
```

## Benefits Achieved

1. ✅ **Clean Separation**: NBA is now a pluggable module
2. ✅ **Generic Core**: Predictions app works for any sport/domain
3. ✅ **Extensible Preferences**: Each app can add its own user settings
4. ✅ **Option System**: Universal favorites and selections
5. ✅ **Event Source Pattern**: Easy to add new data sources
6. ✅ **Better Organization**: Clear boundaries between generic and specific code

## Files Modified

### Created:
- `hooptipp/nba/*` (entire NBA app)
- `hooptipp/predictions/preferences_registry.py`
- `templates/admin/nba/options_changelist.html`
- `REFACTORING_STATUS.md`

### Modified:
- `hooptipp/predictions/models.py` (added UserFavorite, updated UserPreferences)
- `hooptipp/predictions/forms.py` (removed NBA fields)
- `hooptipp/predictions/admin.py` (added UserFavorite/UserPreferences admin)
- `hooptipp/predictions/event_sources/__init__.py` (removed NBA import)
- `hooptipp/settings.py` (added nba app)

### To be Removed:
- `hooptipp/predictions/balldontlie_client.py`
- `hooptipp/predictions/event_sources/nba.py`
- NBA models/admin from predictions app
- NBA functions from predictions/services.py
