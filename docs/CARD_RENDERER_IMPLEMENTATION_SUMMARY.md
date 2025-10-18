# Card Renderer System - Implementation Summary

## Overview

Successfully implemented an extensible card rendering system that allows extensions to provide custom UI layouts for prediction events and results, keeping the base `predictions` package generic while enabling NBA-specific (and future extension-specific) card designs.

## What Was Implemented

### 1. Core Card Renderer System

**Location**: `hooptipp/predictions/card_renderers/`

#### Base Classes
- **`CardRenderer`** (abstract base class)
  - `can_render(event)` - Check if renderer handles an event
  - `get_event_template(event)` - Return template path for open predictions
  - `get_result_template(outcome)` - Return template path for resolved predictions
  - `get_event_context(event, user)` - Provide custom context data
  - `get_result_context(outcome, user)` - Provide result-specific context
  - `priority` property - For ordering when multiple renderers match

- **`DefaultCardRenderer`**
  - Accepts any event (fallback)
  - Uses `predictions/cards/default.html`
  - Priority: -1000 (lowest)

#### Registry System
- **`CardRendererRegistry`**
  - Central registry for all renderers
  - Priority-based renderer selection
  - Automatic fallback to default renderer
  - `register(renderer)` - Add new renderer
  - `get_renderer(event)` - Find appropriate renderer

### 2. Template Tags

**Location**: `hooptipp/predictions/templatetags/prediction_extras.py`

- **`{% render_prediction_card event user_tip %}`**
  - Renders open prediction event cards
  - Automatically uses correct renderer
  - Passes active_user, lock_summary, palette

- **`{% render_result_card outcome user_tip is_correct %}`**
  - Renders resolved prediction result cards
  - Shows correctness indicators
  - Uses result-specific templates when available

### 3. Default Card Template

**Location**: `hooptipp/predictions/templates/predictions/cards/default.html`

Generic card template that works for any prediction type:
- Event name, description, deadline
- Points badge
- Prediction options (radio buttons)
- Lock checkbox
- User-friendly when no active user

### 4. NBA Card Renderer

**Location**: `hooptipp/nba/card_renderer.py`

Specialized renderer for NBA events:
- Handles events with `source_id == "nba-balldontlie"`
- Routes to different templates based on `event_type` metadata:
  - `game` → `nba/cards/game.html`
  - `mvp` → `nba/cards/mvp.html`
  - `playoff_series` → `nba/cards/playoff_series.html`
- Provides rich context:
  - Team logos (CDN URLs)
  - Live scores (with 30s caching)
  - Playoff series information
  - Player data for MVP cards

### 5. NBA Card Templates

**Location**: `hooptipp/nba/templates/nba/cards/`

- **`game.html`** - NBA game predictions
  - Team logos (16x16 images)
  - Team tricodes and full names
  - Venue and game time
  - Live scores when game is in progress
  - Playoff context badge

- **`game_result.html`** - Resolved NBA games
  - Final scores
  - Winning team highlighted
  - User prediction with correct/incorrect indicator
  - Green/red styling for results

- **`mvp.html`** - MVP predictions
  - 2-column player grid
  - Player portraits (or initials fallback)
  - Team information
  - Optional MVP standings sidebar

- **`playoff_series.html`** - Playoff game predictions
  - Playoff badge (🏆)
  - Series context (e.g., "NBA Finals - Game 1")
  - Series score (e.g., "LAL 2-1 BOS")
  - Enhanced styling for playoff atmosphere

### 6. NBA Services

**Location**: `hooptipp/nba/services.py`

Helper functions for card data:

- **`get_team_logo_url(tricode)`**
  - Returns NBA CDN URL for team logo
  - Example: `https://cdn.nba.com/logos/nba/LAL/primary/L/logo.svg`

- **`get_live_game_data(game_id)`**
  - Fetches live scores from BallDontLie API
  - Cached for 30 seconds
  - Returns: scores, status, is_live flag
  - Graceful error handling

- **`get_player_card_data(player_id)`**
  - Fetches player data from Option model
  - Cached for 1 hour
  - Returns: team, position, portrait_url, stats
  - Ready for future portrait integration

- **`get_mvp_standings()`**
  - Placeholder for MVP race data
  - Returns empty list currently
  - Ready for integration with stats service

### 7. Registration

**Location**: `hooptipp/nba/apps.py`

NBA renderer auto-registers on app startup:
```python
def ready(self):
    from hooptipp.predictions.card_renderers.registry import register
    from .card_renderer import NbaCardRenderer
    register(NbaCardRenderer())
```

### 8. Updated Home Page

**Location**: `hooptipp/predictions/templates/predictions/home.html`

Simplified to use new template tags:

**Before** (120+ lines of card HTML):
```django
<article class="...">
  {# Manual card HTML #}
</article>
```

**After** (3 lines):
```django
{% for event in open_predictions %}
  {% render_prediction_card event user_tip %}
{% endfor %}
```

## Test Coverage

Created **52 test cases** across **4 test files**:

### Test Files

1. **`test_card_renderers.py`** (11 tests)
   - CardRenderer base class behavior
   - DefaultCardRenderer functionality
   - CardRendererRegistry operations
   - Priority-based selection
   - Custom renderer patterns

2. **`test_template_tags.py`** (14 tests)
   - `render_prediction_card` tag
   - `render_result_card` tag
   - Context passing
   - Custom renderer integration
   - `get_item` filter

3. **`test_card_renderer.py`** (14 tests)
   - NBA renderer event matching
   - Template selection by event type
   - Context data generation
   - Live game data integration
   - Playoff context handling

4. **`test_services.py`** (13 tests)
   - Team logo URLs
   - Live game data fetching
   - Player card data
   - Caching behavior
   - Error handling

### Coverage Summary

- ✅ Core renderer system (base classes, registry)
- ✅ Template tag rendering
- ✅ NBA-specific implementation
- ✅ Service functions with mocking
- ✅ Edge cases and error handling
- ✅ Cache behavior
- ✅ Extension patterns

## Architecture Benefits

### Clean Separation
- UI rendering separate from EventSource
- NBA code stays in `hooptipp/nba/`
- Base predictions package stays generic

### Extensibility
- New apps just create a CardRenderer
- Register in `apps.py` ready()
- No changes to base package needed

### Type-Based Routing
- Renderers check `source_id` or `metadata`
- Multiple templates per extension
- Priority system handles conflicts

### Maintainability
- Each extension owns its templates
- Changes isolated to specific packages
- Clear extension pattern to follow

## Future Extensions Example

Adding Olympics predictions:

```python
# hooptipp/olympics/card_renderer.py
class OlympicsCardRenderer(CardRenderer):
    def can_render(self, event):
        return event.source_id == 'olympics-2028'
    
    def get_event_template(self, event):
        sport = event.metadata.get('sport')
        return f'olympics/cards/{sport}.html'
    
    def get_event_context(self, event, user=None):
        return {
            'country_flags': get_country_flags(event),
            'athlete_photos': get_athlete_photos(event),
        }

# hooptipp/olympics/apps.py
def ready(self):
    from hooptipp.predictions.card_renderers.registry import register
    from .card_renderer import OlympicsCardRenderer
    register(OlympicsCardRenderer())
```

## Documentation

Created comprehensive documentation:

1. **`CARD_RENDERER_SYSTEM.md`** - Complete system guide
   - Architecture overview
   - Creating custom renderers
   - Template patterns
   - Usage examples

2. **`CARD_RENDERER_TESTS.md`** - Test coverage guide
   - All test cases documented
   - Running instructions
   - Coverage statistics
   - Future test ideas

3. **`CARD_RENDERER_IMPLEMENTATION_SUMMARY.md`** (this file)
   - What was built
   - How it works
   - Benefits and patterns

## Migration Path

Existing events automatically work:
- Events without `source_id` use default card
- NBA events (with `source_id="nba-balldontlie"`) use NBA cards
- No database changes required
- Backwards compatible

## Usage

### For Users
Cards automatically render with appropriate template - no changes needed.

### For Developers Adding Extensions

1. Create a `CardRenderer` subclass
2. Implement required methods
3. Create templates in your app
4. Register in `apps.py`
5. Done!

### For Testing

```bash
# Run all card renderer tests
python manage.py test \
  hooptipp.predictions.tests.test_card_renderers \
  hooptipp.predictions.tests.test_template_tags \
  hooptipp.nba.tests.test_card_renderer \
  hooptipp.nba.tests.test_services
```

## Files Created/Modified

### New Files (17)
- `hooptipp/predictions/card_renderers/__init__.py`
- `hooptipp/predictions/card_renderers/base.py`
- `hooptipp/predictions/card_renderers/registry.py`
- `hooptipp/predictions/templates/predictions/cards/default.html`
- `hooptipp/predictions/tests/test_card_renderers.py`
- `hooptipp/predictions/tests/test_template_tags.py`
- `hooptipp/nba/card_renderer.py`
- `hooptipp/nba/templates/nba/cards/game.html`
- `hooptipp/nba/templates/nba/cards/game_result.html`
- `hooptipp/nba/templates/nba/cards/mvp.html`
- `hooptipp/nba/templates/nba/cards/playoff_series.html`
- `hooptipp/nba/tests/__init__.py`
- `hooptipp/nba/tests/test_card_renderer.py`
- `hooptipp/nba/tests/test_services.py`
- `docs/CARD_RENDERER_SYSTEM.md`
- `docs/CARD_RENDERER_TESTS.md`
- `docs/CARD_RENDERER_IMPLEMENTATION_SUMMARY.md`

### Modified Files (4)
- `hooptipp/predictions/templatetags/prediction_extras.py` (added template tags)
- `hooptipp/predictions/templates/predictions/home.html` (simplified with tags)
- `hooptipp/nba/services.py` (added card helper functions)
- `hooptipp/nba/apps.py` (registered card renderer)

## Total Lines of Code

- Core system: ~200 lines
- NBA implementation: ~500 lines
- Templates: ~600 lines
- Tests: ~900 lines
- Documentation: ~600 lines
- **Total: ~2,800 lines**

## Summary

Successfully implemented a production-ready, extensible card rendering system that:
- ✅ Keeps base package generic
- ✅ Allows NBA-specific rich UI
- ✅ Provides clear extension pattern
- ✅ Has comprehensive test coverage
- ✅ Is fully documented
- ✅ Works with existing data
- ✅ Ready for future extensions
