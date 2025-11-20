# DBB Package Fixes - Admin View Issues

## Problem 1: Verbände Not Displaying

The admin view "Add leagues from Verband" was not displaying the list of Verbände to users, even though debugging showed that the SLAPI client was returning data in JSON form.

### Root Cause

Two issues were identified:

1. **Response Structure**: The SLAPI API client was not handling different response structures (direct lists vs wrapped dictionaries)
2. **Field Names**: The API returns `label` instead of `name` for Verband names

The real SLAPI API returns:
```json
[
  {"id": "100", "label": "Bundesligen", "hits": 34}
]
```

But the template was looking for `name` field, causing it to display nothing.

## Problem 2: Club Search Not Working

The admin workflow for searching clubs was broken because the code assumed a `/clubs/search` endpoint that doesn't exist in the SLAPI API.

### Root Cause

The SLAPI API doesn't have a separate club search endpoint. Instead, it provides:
- `/verbaende/{verband_id}/leagues?club={search_term}` - Returns leagues for a club within a Verband

The old workflow had three separate steps (select Verband → search clubs → select leagues), but this didn't match the API structure.

## Solutions Implemented

### 1. Fixed API Field Names

**File: `hooptipp/dbb/templates/admin/dbb/select_verband.html`**

Updated template to use `label` instead of `name` for Verband names:
- Changed `{{ verband.name }}` to `{{ verband.label }}`
- Updated all references throughout the template

### 2. Response Normalization in SLAPI Client

**File: `hooptipp/dbb/client.py`**

Added a `_normalize_list_response()` helper method that:
- Handles both direct list responses and wrapped dictionary responses
- Tries to extract data from keys like `verbaende`, `clubs`, `standings`, `matches`, etc.
- Falls back to a generic `data` key if the specific key is not found
- Logs warnings when unexpected response structures are encountered
- Returns an empty list for invalid responses instead of crashing

### 3. Corrected API Endpoints

**File: `hooptipp/dbb/client.py`**

- **Removed**: `search_clubs()` method (endpoint doesn't exist)
- **Updated**: `get_club_leagues(verband_id, club_search)` to use correct endpoint:
  - Endpoint: `/verbaende/{verband_id}/leagues?club={club_search}`
  - Takes verband_id and club search term instead of club_id
  
### 4. Simplified Admin Workflow

**Files: `hooptipp/dbb/admin.py`, `hooptipp/dbb/templates/admin/dbb/search_clubs.html`**

Consolidated the three-step workflow into two steps:
1. Select Verband
2. Search for club (now displays leagues and teams directly)

Changes:
- Updated `search_clubs_view()` to fetch leagues directly using `get_club_leagues()`
- Updated template to show leagues and teams selection form immediately
- **Removed**: `select_leagues_view()` (no longer needed)
- Workflow now goes: Select Verband → Search Club → Import (instead of four steps)

### 5. Improved Admin View Logging

**File: `hooptipp/dbb/admin.py`**

Enhanced `select_verband_view()` and `search_clubs_view()` with:
- Informational logging showing how many Verbände/leagues were fetched
- Debug logging showing sample data structure for troubleshooting
- Warning messages to users when no data is found
- Better exception handling with full stack trace logging

### 6. Improved Template Robustness

**File: `hooptipp/dbb/templates/admin/dbb/select_verband.html`**

Enhanced the template to:
- Display both label (name) and ID for each Verband
- Use `|default:"N/A"` filters to handle missing data gracefully
- Check that both `id` and `label` exist before showing the action button
- Show "Invalid data" message for malformed Verband entries
- Provide clearer empty state message directing users to check logs

### 7. Comprehensive Test Coverage

**File: `hooptipp/dbb/tests/test_client.py`**

- Updated existing tests to use correct API structure (`label` instead of `name`)
- Replaced `test_search_clubs()` with `test_get_club_leagues_with_search()`
- Added tests for wrapped response structures
- All tests use realistic data matching actual API responses

**File: `hooptipp/dbb/tests/test_admin.py`**

- Updated tests to use `label` field
- Updated `test_search_clubs_view()` to verify leagues are displayed
- Removed `test_select_leagues_view()` (view no longer exists)
- All 8 admin tests pass

## Test Results

All 56 tests in the DBB package pass successfully:

```
Ran 56 tests in 6.167s
OK
```

This includes:
- 12 client tests (updated for correct API structure)
- 8 admin tests (streamlined for new workflow)
- 8 model tests (including test for nullable venue field)
- 28 other tests for event sources, card renderers, and commands

## Additional Fixes

### Nullable Venue Field

The `venue` (location) field in the SLAPI API is optional according to the OpenAPI spec. Updated the `DbbMatch` model to allow NULL values:

- Added `null=True` to the `venue` field (already had `blank=True`)
- Created migration `0002_alter_dbbmatch_venue.py`
- Updated `event_source.py` to use `None` instead of empty string when venue is not provided
- Added test `test_create_dbb_match_without_venue()` to verify NULL handling

## Benefits

1. **Correctness**: Now uses actual API endpoints that exist
2. **Simplified Workflow**: Reduced from 4 steps to 3 steps
3. **Robustness**: Handles various API response structures without breaking
4. **Debuggability**: Enhanced logging makes it easier to diagnose API issues
5. **User Experience**: Users get clear feedback and see results faster
6. **Maintainability**: Centralized normalization logic reduces code duplication
7. **Test Coverage**: Comprehensive tests ensure the fixes work with real API data

## API Endpoints Used

The corrected implementation uses these SLAPI endpoints:
- `GET /verbaende` - List all Verbände
  - Returns: `[{"id": "100", "label": "Bundesligen", "hits": 34}, ...]`
- `GET /clubs/{club_search}/leagues?verband_id={verband_id}` - Get leagues for a club
  - Returns: `{"club_name": "...", "verband_id": ..., "leagues": [{"liga_id": 48693, "liganame": "...", ...}, ...]}`
- `GET /leagues/{league_id}/standings` - Get teams in a league
- `GET /leagues/{league_id}/matches` - Get matches in a league  
- `GET /matches/{match_id}` - Get match details

### Important Field Names

The SLAPI API uses specific field names and structures based on the [OpenAPI specification](https://slapi.up.railway.app/openapi.json):

- **Verbände**: Use `label` (not `name`) and `id`
  - Wrapped response: `{"verbaende": [{"id": "100", "label": "Bundesligen", "hits": 34}]}`
- **Leagues**: Use `liga_id` (not `id`) and `liganame` (not `name`)
  - Wrapped response: `{"club_name": "...", "verband_id": 7, "leagues": [...]}`
- **Standings**: Team is an **object**, not a string
  - Response: `{"league_id": "...", "standings": [{"position": 1, "team": {"id": "...", "name": "..."}, "wins": 10}]}`
- **Matches**: `home_team` and `away_team` are **Team objects**
  - Response: `{"league_id": "...", "matches": [{"match_id": 1, "home_team": {"name": "..."}, "away_team": {"name": "..."}]}`

## Future Improvements

1. Monitor logs to identify the actual response structure from production SLAPI API
2. Consider adding response validation/schema checking
3. Add response caching to reduce API calls
4. Add more detailed error messages based on specific API error codes

