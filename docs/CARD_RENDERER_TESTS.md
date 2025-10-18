# Card Renderer System - Test Coverage

## Overview

Comprehensive test suite for the extensible card renderer system that allows extensions to provide custom card layouts for prediction events and results.

## Test Files Created

### 1. `hooptipp/predictions/tests/test_card_renderers.py`

Tests for the core card renderer system.

#### CardRendererBaseTests
- ✅ Default renderer accepts any event
- ✅ Default renderer uses default template path
- ✅ Default renderer has lowest priority (-1000)
- ✅ Default renderer returns empty context
- ✅ Result template defaults to event template (with override capability)
- ✅ Result context defaults to event context (with override capability)

#### CardRendererRegistryTests
- ✅ Registry returns default renderer for unmatched events
- ✅ Registry returns matching renderer when available
- ✅ Registry respects priority ordering (higher priority checked first)
- ✅ Registry lists all registered renderers
- ✅ Multiple matching renderers - first by priority wins

#### CustomRendererImplementationTests
- ✅ Custom renderer can check event metadata
- ✅ Custom renderer can use user parameter for personalization
- ✅ Demonstrates extension pattern

**Total: 11 test cases**

### 2. `hooptipp/predictions/tests/test_template_tags.py`

Tests for the Django template tags that render cards.

#### RenderPredictionCardTemplateTagTests
- ✅ Tag uses default template when no custom renderer
- ✅ Tag renders with user tip when provided
- ✅ Tag uses custom renderer when registered
- ✅ Tag renders without active user
- ✅ Tag includes theme palette in context
- ✅ Tag includes lock summary in context

#### RenderResultCardTemplateTagTests
- ✅ Tag renders result card with outcome
- ✅ Tag shows correct prediction indicator
- ✅ Tag shows incorrect prediction indicator
- ✅ Tag renders without user tip
- ✅ Tag uses custom renderer for result template

#### GetItemFilterTests
- ✅ Filter gets item from dictionary
- ✅ Filter returns None for None mapping
- ✅ Filter returns None for missing key

**Total: 14 test cases**

### 3. `hooptipp/nba/tests/test_card_renderer.py`

Tests for NBA-specific card renderer implementation.

#### NbaCardRendererTests
- ✅ Renderer accepts NBA events (source_id == "nba-balldontlie")
- ✅ Renderer rejects non-NBA events
- ✅ Returns game template for game events
- ✅ Returns MVP template for MVP events
- ✅ Returns playoff template for playoff events
- ✅ Defaults to game template when event_type not specified
- ✅ Returns game result template for resolved games
- ✅ Provides game context with team data (logos, names, venue, time)
- ✅ Includes playoff context when available
- ✅ Provides player data for MVP events
- ✅ Fetches live data for in-progress games
- ✅ Fetches final score for result cards
- ✅ Renderer has default priority (0)
- ✅ Handles events without scheduled games gracefully

**Total: 14 test cases**

### 4. `hooptipp/nba/tests/test_services.py`

Tests for NBA card rendering service functions.

#### GetTeamLogoUrlTests
- ✅ Returns CDN URL for team logo
- ✅ Returns different URLs for different teams

#### GetLiveGameDataTests
- ✅ Returns default data when client unavailable
- ✅ Fetches game data from BallDontLie API
- ✅ Detects live games (Q1-Q4, OT, Halftime)
- ✅ Caches live data for 30 seconds
- ✅ Handles API errors gracefully
- ✅ Detects multiple live statuses correctly

#### GetPlayerCardDataTests
- ✅ Returns player data from Option model
- ✅ Returns default data for missing player
- ✅ Caches player data for 1 hour
- ✅ Handles missing metadata gracefully

#### GetMvpStandingsTests
- ✅ Returns empty list (placeholder implementation)

**Total: 13 test cases**

## Summary Statistics

| Test File | Test Classes | Test Cases |
|-----------|--------------|------------|
| test_card_renderers.py | 3 | 11 |
| test_template_tags.py | 3 | 14 |
| test_card_renderer.py (NBA) | 1 | 14 |
| test_services.py (NBA) | 4 | 13 |
| **TOTAL** | **11** | **52** |

## Test Coverage Areas

### Core Functionality
- ✅ Base CardRenderer abstract class
- ✅ DefaultCardRenderer fallback
- ✅ CardRendererRegistry registration and lookup
- ✅ Priority-based renderer selection
- ✅ Template tag rendering (events and results)
- ✅ Context passing to templates

### Extension Pattern
- ✅ Custom renderer implementation
- ✅ Metadata-based routing
- ✅ User-aware personalization
- ✅ Multiple event types per source

### NBA Implementation
- ✅ Game cards with team logos
- ✅ MVP cards with player data
- ✅ Playoff series cards
- ✅ Live score fetching and caching
- ✅ Final score for results
- ✅ Error handling

### Edge Cases
- ✅ Missing data handling
- ✅ API errors
- ✅ Cache behavior
- ✅ No active user
- ✅ Events without scheduled games
- ✅ Empty metadata

## Running Tests

### Run All Card Renderer Tests
```bash
python manage.py test hooptipp.predictions.tests.test_card_renderers
python manage.py test hooptipp.predictions.tests.test_template_tags
python manage.py test hooptipp.nba.tests.test_card_renderer
python manage.py test hooptipp.nba.tests.test_services
```

### Run All Tests Together
```bash
python manage.py test hooptipp.predictions.tests.test_card_renderers \
                      hooptipp.predictions.tests.test_template_tags \
                      hooptipp.nba.tests.test_card_renderer \
                      hooptipp.nba.tests.test_services
```

### Run with Coverage
```bash
coverage run --source='hooptipp' manage.py test
coverage report
coverage html
```

## Continuous Integration

These tests should be included in CI pipelines to ensure:
- No regression when modifying card renderers
- New renderers follow the correct pattern
- Template tags continue working correctly
- NBA services handle API changes gracefully

## Future Test Additions

When adding new features, consider testing:
- [ ] Additional event types (e.g., season awards, All-Star)
- [ ] Live score WebSocket updates
- [ ] Player portrait integration
- [ ] MVP standings calculation
- [ ] Error recovery and retry logic
- [ ] Performance/load testing for cached data
- [ ] Template rendering performance
- [ ] Cross-browser template compatibility

## Notes

- All tests use mocking for external API calls (BallDontLie)
- Cache is cleared between tests to ensure isolation
- Templates are tested for content, not exact HTML structure
- Tests focus on behavior rather than implementation details
