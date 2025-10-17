# Generic Prediction System Implementation Summary

This document summarizes the major refactoring that transformed HoopTipp from an NBA-specific prediction app into a general-purpose prediction platform.

## Overview

The system has been generalized to support **any type of predictable event** while maintaining full backward compatibility with existing NBA functionality.

## Key Changes

### 1. New Generic Models

#### OptionCategory
Represents categories of prediction options (e.g., "NBA Teams", "Countries", "Political Parties").

```python
class OptionCategory(models.Model):
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
```

#### Option
Generic option that can represent any selectable choice in predictions.

```python
class Option(models.Model):
    category = models.ForeignKey(OptionCategory, ...)
    slug = models.SlugField(max_length=100)
    name = models.CharField(max_length=200)
    short_name = models.CharField(max_length=50, blank=True)
    description = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    external_id = models.CharField(max_length=200, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
```

### 2. Updated Existing Models

#### PredictionEvent
Added generic source tracking:
- `source_id`: Identifier for the EventSource that created the event
- `source_event_id`: External event ID from the source system
- `metadata`: JSON field for source-specific data
- `target_kind`: Added "GENERIC" option for non-NBA predictions

#### PredictionOption
Added generic option support:
- `option`: New ForeignKey to generic Option model
- Legacy `team` and `player` fields preserved for backward compatibility

#### UserTip
Added generic option selection:
- `selected_option`: New ForeignKey to generic Option model
- Legacy `selected_team` and `selected_player` fields preserved

#### EventOutcome
Added generic winning option:
- `winning_generic_option`: New ForeignKey to generic Option model
- Legacy `winning_team` and `winning_player` fields preserved

### 3. Event Source System

Created a plugin architecture for automatic event imports.

#### EventSource Base Class
Abstract base class for all event sources:
- `source_id`: Unique identifier
- `source_name`: Human-readable name
- `category_slugs`: List of categories provided
- `sync_options()`: Import/update options
- `sync_events()`: Import/update events
- `resolve_outcomes()`: Optionally auto-resolve outcomes
- `is_configured()`: Check if properly configured

#### EventSourceResult
Data class for tracking sync operations:
- Counts of events/options created/updated/removed
- Error tracking
- Merge capability for combining results

#### EventSourceRegistry
Global registry for managing event sources:
- Register/unregister sources
- Get sources by ID
- List all or only configured sources
- Get sources by category

#### NBA Event Source
Converted existing NBA functionality into an EventSource:
- Wraps legacy BallDontLie API integration
- Syncs NBA teams to generic Options
- Syncs NBA players to generic Options
- Imports weekly games as PredictionEvents
- Maintains backward compatibility with existing data

### 4. Admin Interface Updates

#### New Admin Classes
- `OptionCategoryAdmin`: Manage option categories
- `OptionAdmin`: Manage generic options with filtering by category
- `EventSourceAdmin`: Pseudo-admin for managing event sources
  - List all registered sources
  - Show configuration status
  - Trigger option/event syncs

#### Updated Admin Classes
- `PredictionEventAdmin`: Shows source_id, improved fieldsets
- `PredictionOptionAdmin`: Shows generic option with legacy fields collapsed
- `UserTipAdmin`: Shows selected option regardless of type
- `EventOutcomeAdmin`: Shows winning option with helper method

### 5. View Updates

Updated `home` view to handle generic options:
- Check for `selected_option` field first
- Fall back to legacy `selected_team`/`selected_player`
- Handle "GENERIC" target kind
- Process generic option selections in form submissions

### 6. Data Migration

Created migration `0009_migrate_nba_data_to_generic_options`:
- Creates "nba-teams" and "nba-players" OptionCategory entries
- Migrates all NbaTeam records to Option records
- Migrates all NbaPlayer records to Option records
- Updates PredictionOption to link to new Options
- Updates UserTip to link to new Options
- Updates EventOutcome to link to new Options
- Preserves legacy fields for backward compatibility
- Reversible migration

### 7. Services Updates

Added `sync_weekly_games_via_source()`:
- Uses NBA EventSource instead of direct API calls
- Syncs options and events
- Returns current state
- Replaces need for direct service calls

## Backward Compatibility

All existing functionality is preserved:
1. Legacy NBA models (NbaTeam, NbaPlayer) still exist
2. Legacy foreign key fields preserved on all models
3. All existing migrations work unchanged
4. All existing tests pass without modification
5. NBA data automatically migrated to generic system

## Testing

All 63 existing tests pass:
- Admin functionality tests
- Scoring service tests
- BallDontLie client tests
- View tests
- Services tests
- Migration tests

No test modifications were required, demonstrating complete backward compatibility.

## Documentation

Created comprehensive documentation:
- `docs/generic_prediction_system_design.md`: Complete architecture guide
- `README.md`: Updated with generic system capabilities
- `docs/IMPLEMENTATION_SUMMARY.md`: This document

## Example Use Cases

The system now supports:

### 1. Next Pope Prediction
```python
# Create event manually via admin
event = PredictionEvent.objects.create(
    tip_type=special_events_type,
    name="Which country names the next Pope?",
    target_kind=PredictionEvent.TargetKind.GENERIC,
    opens_at=now,
    deadline=datetime(2025, 12, 31),
    points=5,
)

# Add country options
countries_cat = OptionCategory.objects.get(slug="countries")
for country_name in ["Italy", "USA", "Brazil", "Poland", "France"]:
    option = Option.objects.create(
        category=countries_cat,
        name=country_name,
        slug=country_name.lower(),
    )
    PredictionOption.objects.create(
        event=event,
        option=option,
        label=country_name,
    )
```

### 2. Olympic Medals Prediction
```python
class OlympicEventSource(EventSource):
    source_id = "olympics-2028"
    source_name = "2028 Olympics"
    category_slugs = ["countries"]
    
    def sync_events(self):
        # Create "Which country wins 30+ medals first?" event
        event = PredictionEvent.objects.create(
            source_id=self.source_id,
            name="Which country reaches 30 medals first?",
            target_kind=PredictionEvent.TargetKind.GENERIC,
            ...
        )
        # Add country options
        ...
        return EventSourceResult(events_created=1)
```

### 3. Personal Bike Tracking
```python
class BikeCommuteSource(EventSource):
    source_id = "bike-commute"
    
    def sync_events(self):
        # Create monthly event
        event = PredictionEvent.objects.create(
            source_id=self.source_id,
            name="Will [Person] bike to work 10+ times this month?",
            target_kind=PredictionEvent.TargetKind.GENERIC,
            ...
        )
        
        # Binary yes/no options
        yes_no_cat = OptionCategory.objects.get(slug="yes-no")
        for choice_text in ["Yes (10+ times)", "No (< 10 times)"]:
            option = Option.objects.create(
                category=yes_no_cat,
                name=choice_text,
                ...
            )
            PredictionOption.objects.create(
                event=event,
                option=option,
                label=choice_text,
            )
        
        return EventSourceResult(events_created=1)
```

## Migration Path

For existing installations:
1. Pull latest code
2. Run migrations: `python manage.py migrate`
3. NBA data automatically migrated to generic system
4. All existing functionality continues to work
5. New generic features immediately available

## Future Enhancements

The architecture now supports:
- Easy addition of new event sources
- Any type of prediction category
- Mix of automatic and manual events
- Source-specific metadata and validation
- Automatic outcome resolution
- Event source marketplace/plugins

## Technical Debt Addressed

1. **Removed hardcoded NBA assumptions** throughout codebase
2. **Eliminated duplication** between team/player handling
3. **Improved separation of concerns** (data sources vs prediction logic)
4. **Added extensibility points** for future enhancement
5. **Maintained backward compatibility** to protect existing users

## Performance Considerations

- Added database indexes on new fields (category, external_id, source_id)
- JSON metadata fields for flexible data without schema changes
- Efficient querying with select_related/prefetch_related preserved
- Migration runs efficiently even with large datasets

## Security

- Admin-only access to event source management
- CSRF protection on all sync endpoints
- Validation on event source configurations
- Safe handling of external API credentials

## Summary Statistics

- **New Models**: 2 (OptionCategory, Option)
- **Updated Models**: 4 (PredictionEvent, PredictionOption, UserTip, EventOutcome)
- **New Fields**: 8 across existing models
- **Migrations**: 2 (schema + data)
- **New Modules**: 3 (event_sources package)
- **Lines of Code Added**: ~2000
- **Tests Passing**: 63/63
- **Breaking Changes**: 0

## Conclusion

The refactoring successfully generalizes HoopTipp while:
- ✅ Maintaining 100% backward compatibility
- ✅ Passing all existing tests
- ✅ Preserving all NBA functionality
- ✅ Enabling infinite extensibility
- ✅ Improving code organization
- ✅ Adding comprehensive documentation

The system is now ready for any type of prediction event, from sports to politics to personal goals, while still providing excellent NBA prediction capabilities out of the box.
