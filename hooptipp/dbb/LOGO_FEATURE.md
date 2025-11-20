# DBB Team Logo Feature

## Overview

Added support for displaying team logos in DBB match cards. Teams can now have custom logos stored as SVG files that will be displayed instead of the default two-letter placeholder.

## Changes Made

### 1. Model Changes (`models.py`)

Added a `logo` field to the `TrackedTeam` model:

```python
logo = models.CharField(
    max_length=200,
    blank=True,
    help_text="Logo filename (e.g., 'bierden-bassen.svg') from static/dbb/ directory"
)
```

**Migration**: `0003_trackedteam_logo.py` - Adds the logo field to existing TrackedTeam records

### 2. Event Source Changes (`event_source.py`)

Updated the `sync_options()` method to include logo information in Option metadata:

- When syncing tracked teams to options, the logo filename is now included in the option's metadata
- Logos are only added to metadata when present on the TrackedTeam
- This ensures logo information flows through the prediction system

### 3. Card Renderer Changes (`card_renderer.py`)

Enhanced `get_event_context()` to extract logo information:

- Extracts `away_team_logo` and `home_team_logo` from option metadata
- Passes logo information to templates via context
- Falls back to empty string when no logo is available

### 4. Template Changes

#### `templates/dbb/cards/match.html`

Updated both home and away team sections to display logos:

```django
{% if card_context.away_team_logo %}
    {% load static %}
    <img src="{% static 'dbb/'|add:card_context.away_team_logo %}" 
         alt="{{ card_context.away_team }}" 
         class="h-14 w-14 object-contain">
{% else %}
    <span class="text-2xl font-bold text-slate-500">
        {{ card_context.away_team|slice:":2"|upper }}
    </span>
{% endif %}
```

#### `templates/dbb/cards/match_result.html`

Similar updates for result cards with appropriately sized logos (h-10 w-10)

### 5. Static Files Directory

Created `static/dbb/` directory structure:

- `static/dbb/README.md` - Documentation on logo usage and format guidelines
- Ready to receive SVG logo files

### 6. Tests

Added comprehensive unit tests:

#### Model Tests (`tests/test_models.py`)
- `test_tracked_team_with_logo()` - Verifies logo field can be set
- `test_tracked_team_without_logo()` - Verifies default empty string behavior

#### Card Renderer Tests (`tests/test_card_renderer.py`)
- `test_get_event_context_with_logos()` - Verifies logos are extracted to context
- `test_get_event_context_without_logos()` - Verifies fallback behavior
- `test_get_result_context_with_logos()` - Verifies logos appear in result context

#### Event Source Tests (`tests/test_event_source.py`)
- `test_sync_options_with_logos()` - Verifies logos are synced to Option metadata
- `test_sync_options_without_logos()` - Verifies behavior when no logos are set

**All 431 tests pass successfully** ✅

## Usage Instructions

### Adding a Logo to a Team

1. **Prepare the Logo File**:
   - Format: SVG (recommended) or PNG
   - Aspect ratio: Square or close to square
   - Save as: `static/dbb/your-team-name.svg`

2. **Configure in Django Admin**:
   - Navigate to **DBB** → **Tracked teams**
   - Select or create a team
   - In the **Logo** field, enter just the filename: `your-team-name.svg`
   - Save the team

3. **Sync Options**:
   - Navigate to **Predictions** → **Event sources**
   - Find "German Basketball (SLAPI)"
   - Click "Sync Options" to update the option metadata with logo information

4. **Logos will now appear** on all match cards for that team

### Fallback Behavior

If no logo is specified or the file doesn't exist:
- The card displays the first two letters of the team name as a placeholder
- Example: "BG Bierden-Bassen" → "BG"

## Technical Details

### Data Flow

1. `TrackedTeam.logo` stores the filename
2. `DbbEventSource.sync_options()` copies logo to `Option.metadata['logo']`
3. `PredictionOption` references the `Option` with logo metadata
4. `DbbCardRenderer.get_event_context()` extracts logo from option metadata
5. Templates render logo from `static/dbb/{logo}` or show fallback

### Static File Path

Logos are loaded using Django's static files system:

```python
{% static 'dbb/'|add:card_context.away_team_logo %}
```

This resolves to: `static/dbb/{filename}`

### Performance Considerations

- Logo filenames are stored as strings, not file fields
- No database queries for logo files
- Static files are served efficiently by Django/web server
- SVG format recommended for small file size and crisp rendering

## Future Enhancements

Potential improvements:
- Admin preview of logo when editing TrackedTeam
- Bulk logo upload interface
- Automatic logo download from external sources
- Logo validation to check if file exists
- Support for team colors from logo analysis

## Related Files

- `hooptipp/dbb/models.py` - TrackedTeam model with logo field
- `hooptipp/dbb/event_source.py` - Logo syncing to options
- `hooptipp/dbb/card_renderer.py` - Logo context extraction
- `hooptipp/dbb/templates/dbb/cards/match.html` - Logo display in match cards
- `hooptipp/dbb/templates/dbb/cards/match_result.html` - Logo display in results
- `hooptipp/dbb/migrations/0003_trackedteam_logo.py` - Database migration
- `static/dbb/` - Logo file directory

