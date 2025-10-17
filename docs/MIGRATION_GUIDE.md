# Migration Guide: Generic Prediction System

This guide helps you understand and use the new generic prediction system in HoopTipp.

## For Existing Users

### What Changed?

HoopTipp has been upgraded from an NBA-only prediction app to a **general-purpose prediction platform**. You can now predict anything: sports, politics, world events, or personal goals.

### Is My Data Safe?

**Yes!** All your existing NBA predictions and data are preserved:
- All NBA teams and players still work
- All user predictions are intact
- All scoring history is preserved
- The NBA game sync still works exactly as before

### What's New?

1. **Generic Options**: Teams, players, countries, or any custom choices
2. **Event Sources**: Automatic imports from external APIs
3. **Flexible Categories**: Organize predictions into any category
4. **Easy Extensions**: Add new prediction types without code changes

### Do I Need to Do Anything?

When you upgrade:
1. Pull the latest code
2. Run: `python manage.py migrate`
3. That's it! Your NBA predictions continue to work

The migration automatically converts your NBA data to the new generic system.

## For Administrators

### Managing Event Sources

Event Sources automatically import predictions from external systems.

#### View Available Sources

In the admin panel, navigate to the Event Sources section (you may need to add this custom admin view).

Sources show:
- **Name**: Human-readable name
- **Source ID**: Unique identifier
- **Categories**: What types of options it provides
- **Status**: Configured or not configured

#### NBA Event Source

The built-in NBA source requires a BallDontLie API token:

```bash
export BALLDONTLIE_API_TOKEN=your_token_here
```

Then in admin:
1. Click "Sync Options" to import teams and players
2. Click "Sync Events" to import upcoming games

#### Manual Syncing via Shell

You can also sync programmatically:

```python
from hooptipp.predictions.event_sources import get_source

# Get the NBA source
nba = get_source('nba-balldontlie')

# Check if configured
if nba.is_configured():
    # Sync options (teams, players)
    result = nba.sync_options()
    print(f"Options: {result.options_created} created, {result.options_updated} updated")
    
    # Sync events (games)
    result = nba.sync_events()
    print(f"Events: {result.events_created} created, {result.events_updated} updated")
```

### Creating Manual Predictions

#### Step 1: Create Option Category

If you need a new type of option:

1. Go to **Option Categories** in admin
2. Click **Add Option Category**
3. Fill in:
   - **Slug**: Unique identifier (e.g., `countries`, `yes-no`)
   - **Name**: Display name (e.g., "Countries", "Yes/No")
   - **Icon**: Optional icon identifier
   - **Sort Order**: Display order

#### Step 2: Add Options

1. Go to **Options** in admin
2. Click **Add Option**
3. Fill in:
   - **Category**: Select your category
   - **Name**: Full name (e.g., "United States", "Yes")
   - **Short Name**: Abbreviation (e.g., "USA")
   - **Slug**: URL-friendly identifier
   - **Description**: Optional details

#### Step 3: Create Tip Type

If you need a new prediction category:

1. Go to **Tip Types** in admin
2. Click **Add Tip Type**
3. Fill in:
   - **Name**: Display name (e.g., "Special Events")
   - **Slug**: Unique identifier
   - **Category**: Game/Player/Team/Season
   - **Default Points**: Points per prediction
   - **Deadline**: When predictions close

#### Step 4: Create Prediction Event

1. Go to **Prediction Events** in admin
2. Click **Add Prediction Event**
3. Fill in:
   - **Tip Type**: Select your tip type
   - **Name**: Short title
   - **Description**: Full description
   - **Target Kind**: Choose "Generic" for custom predictions
   - **Selection Mode**: "Curated" (recommended)
   - **Opens At**: When users can start predicting
   - **Deadline**: When predictions close
   - **Points**: Points awarded for correct prediction

#### Step 5: Add Prediction Options

After creating the event:

1. In the event edit page, scroll to **Prediction Options**
2. Click **Add Another Prediction Option**
3. Fill in:
   - **Label**: Display text
   - **Option**: Select from your options (recommended)
   - **Sort Order**: Display order
4. Add multiple options for users to choose from

### Example: Pope Prediction

Let's create a "Which country names the next Pope?" prediction:

#### 1. Create Countries Category
- Slug: `countries`
- Name: "Countries"

#### 2. Add Country Options
- Italy (slug: `italy`)
- United States (slug: `usa`)
- Brazil (slug: `brazil`)
- Poland (slug: `poland`)
- France (slug: `france`)

#### 3. Create Tip Type
- Name: "Special Events"
- Slug: `special-events`
- Category: Season
- Default Points: 5

#### 4. Create Prediction Event
- Tip Type: Special Events
- Name: "Which country names the next Pope?"
- Target Kind: Generic
- Opens At: Today
- Deadline: December 31, 2025
- Points: 5

#### 5. Add Options
Add all five countries as prediction options.

Done! Users can now predict which country will name the next Pope.

## For Developers

### Creating Custom Event Sources

Event sources automatically import predictions from external systems.

#### Basic Structure

```python
# hooptipp/predictions/event_sources/my_source.py
from .base import EventSource, EventSourceResult
from ..models import Option, OptionCategory, PredictionEvent, PredictionOption

class MyEventSource(EventSource):
    @property
    def source_id(self) -> str:
        return "my-source-id"
    
    @property
    def source_name(self) -> str:
        return "My Event Source"
    
    @property
    def category_slugs(self) -> list[str]:
        return ["my-category"]
    
    def is_configured(self) -> bool:
        # Check if API keys, etc. are configured
        return bool(os.environ.get('MY_API_KEY'))
    
    def sync_options(self) -> EventSourceResult:
        result = EventSourceResult()
        
        # 1. Create your category
        category, _ = OptionCategory.objects.get_or_create(
            slug='my-category',
            defaults={'name': 'My Category'}
        )
        
        # 2. Import options from external source
        for item in fetch_from_external_api():
            option, created = Option.objects.update_or_create(
                category=category,
                external_id=item['id'],
                defaults={
                    'name': item['name'],
                    'slug': item['slug'],
                    'metadata': item['extra_data'],
                }
            )
            if created:
                result.options_created += 1
            else:
                result.options_updated += 1
        
        return result
    
    def sync_events(self) -> EventSourceResult:
        result = EventSourceResult()
        
        # 1. Get or create tip type
        tip_type, _ = TipType.objects.get_or_create(
            slug='my-predictions',
            defaults={'name': 'My Predictions'}
        )
        
        # 2. Import events from external source
        for event_data in fetch_events_from_api():
            event, created = PredictionEvent.objects.update_or_create(
                source_id=self.source_id,
                source_event_id=event_data['id'],
                defaults={
                    'tip_type': tip_type,
                    'name': event_data['name'],
                    'description': event_data['description'],
                    'target_kind': PredictionEvent.TargetKind.GENERIC,
                    'opens_at': event_data['opens_at'],
                    'deadline': event_data['deadline'],
                    'metadata': event_data,
                }
            )
            
            if created:
                result.events_created += 1
            else:
                result.events_updated += 1
            
            # 3. Add prediction options
            for option_data in event_data['options']:
                option = Option.objects.get(
                    category__slug='my-category',
                    external_id=option_data['id']
                )
                PredictionOption.objects.update_or_create(
                    event=event,
                    option=option,
                    defaults={'label': option_data['name']}
                )
        
        return result
```

#### Register Your Source

```python
# hooptipp/predictions/event_sources/__init__.py
from .my_source import MyEventSource
registry.register(MyEventSource)
```

#### Optional: Auto-Resolve Outcomes

```python
def resolve_outcomes(self) -> EventSourceResult:
    result = EventSourceResult()
    
    # Find events from this source that need resolution
    events = PredictionEvent.objects.filter(
        source_id=self.source_id,
        outcome__isnull=True,
        deadline__lt=timezone.now()
    )
    
    for event in events:
        # Fetch result from external API
        winner_id = fetch_winner_from_api(event.source_event_id)
        
        # Find the winning option
        winning_option = event.options.get(option__external_id=winner_id)
        
        # Create outcome
        EventOutcome.objects.create(
            prediction_event=event,
            winning_option=winning_option,
            winning_generic_option=winning_option.option,
        )
        
        result.events_updated += 1
    
    return result
```

### Testing Event Sources

```python
# hooptipp/predictions/tests/test_my_source.py
from django.test import TestCase
from ..event_sources import get_source

class MyEventSourceTests(TestCase):
    def test_source_is_registered(self):
        source = get_source('my-source-id')
        self.assertEqual(source.source_name, 'My Event Source')
    
    def test_sync_options_creates_categories(self):
        source = get_source('my-source-id')
        result = source.sync_options()
        
        self.assertGreater(result.options_created, 0)
        self.assertTrue(OptionCategory.objects.filter(slug='my-category').exists())
    
    def test_sync_events_creates_predictions(self):
        source = get_source('my-source-id')
        source.sync_options()  # Import options first
        
        result = source.sync_events()
        self.assertGreater(result.events_created, 0)
```

## Troubleshooting

### Migration Issues

**Problem**: Migration fails with "option field doesn't exist"

**Solution**: Make sure you run migrations in order:
```bash
python manage.py migrate predictions 0008  # Schema changes
python manage.py migrate predictions 0009  # Data migration
```

### NBA Source Not Working

**Problem**: NBA games not importing

**Checklist**:
1. Is `BALLDONTLIE_API_TOKEN` set?
2. Run: `python manage.py shell`
   ```python
   from hooptipp.predictions.event_sources import get_source
   nba = get_source('nba-balldontlie')
   print(nba.is_configured())  # Should be True
   ```
3. Check logs for error messages
4. Verify API token is valid at balldontlie.io

### Custom Source Not Registered

**Problem**: `ValueError: Unknown event source: my-source`

**Solution**:
1. Check that you imported and registered the source in `event_sources/__init__.py`
2. Restart the Django server
3. Verify import doesn't fail:
   ```python
   python manage.py shell
   from hooptipp.predictions.event_sources import list_sources
   print([s.source_id for s in list_sources()])
   ```

## Best Practices

### Option Management
- Use meaningful slugs (they're permanent identifiers)
- Set external_id for options from APIs
- Use metadata for extra information
- Keep short_name concise (3-5 characters)

### Event Source Design
- Check `is_configured()` before syncing
- Use external_id to avoid duplicates
- Store source data in metadata JSON field
- Handle API errors gracefully
- Return detailed EventSourceResult

### Performance
- Sync options before events
- Use bulk_create/update when possible
- Add database indexes on frequently queried fields
- Cache API responses when appropriate

### Testing
- Test with and without API credentials
- Mock external API calls
- Test idempotent operations
- Verify cleanup of old data

## Support

For questions or issues:
- Check `docs/generic_prediction_system_design.md` for architecture details
- Review the NBA event source as a reference implementation
- Create an issue on GitHub (if open source)
- Contact the development team

## Summary

The generic prediction system provides:
- ✅ Flexibility to predict anything
- ✅ Backward compatibility with NBA predictions
- ✅ Easy extensibility via event sources
- ✅ Clean separation of concerns
- ✅ Comprehensive documentation

Happy predicting! 🎯
