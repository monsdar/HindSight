# Card Renderer System

## Overview

The card renderer system provides an extensible way for different apps to define custom card layouts for prediction events and results. This keeps the base `predictions` package generic while allowing extensions like the `nba` app to provide their own specialized UI.

## Architecture

### Core Components

1. **CardRenderer (Base Class)** - `hooptipp/predictions/card_renderers/base.py`
   - Abstract base class defining the card rendering interface
   - Methods for determining templates and providing context data
   - Separate handling for event cards (open predictions) and result cards (resolved predictions)

2. **CardRendererRegistry** - `hooptipp/predictions/card_renderers/registry.py`
   - Central registry for all card renderers
   - Finds the appropriate renderer for each event based on priority and capability
   - Provides a default fallback renderer

3. **Template Tags** - `hooptipp/predictions/templatetags/prediction_extras.py`
   - `{% render_prediction_card event user_tip %}` - Renders open prediction events
   - `{% render_result_card outcome user_tip is_correct %}` - Renders resolved predictions

### How It Works

1. **Registration**: Each extension app registers its card renderer in `apps.py`:
   ```python
   from hooptipp.predictions.card_renderers.registry import register
   from .card_renderer import NbaCardRenderer
   
   register(NbaCardRenderer())
   ```

2. **Template Selection**: When rendering a card, the system:
   - Looks up the appropriate renderer from the registry
   - Asks the renderer for the template path
   - Asks the renderer for additional context data
   - Renders the template with the combined context

3. **Fallback**: If no specific renderer matches an event, the system uses the default generic card template.

## Creating a Custom Card Renderer

### Step 1: Create the Renderer Class

```python
# myapp/card_renderer.py

from hooptipp.predictions.card_renderers.base import CardRenderer

class MyCardRenderer(CardRenderer):
    def can_render(self, event) -> bool:
        """Check if this renderer handles this event."""
        return event.source_id == "my-source-id"
    
    def get_event_template(self, event) -> str:
        """Return template path for event cards."""
        return "myapp/cards/event.html"
    
    def get_result_template(self, outcome) -> str:
        """Return template path for result cards."""
        return "myapp/cards/result.html"
    
    def get_event_context(self, event, user=None) -> dict:
        """Provide custom context data for event cards."""
        return {
            'custom_data': self._fetch_custom_data(event),
            'user_specific': self._get_user_data(user),
        }
    
    def get_result_context(self, outcome, user=None) -> dict:
        """Provide custom context data for result cards."""
        context = self.get_event_context(outcome.prediction_event, user)
        context['final_data'] = self._get_final_data(outcome)
        return context
    
    @property
    def priority(self) -> int:
        """Higher priority = checked first. Default is 0."""
        return 0
```

### Step 2: Create Templates

```django
{# myapp/templates/myapp/cards/event.html #}

<article class="prediction-card">
  {# Header #}
  <header>
    <h3>{{ event.name }}</h3>
    <p>Deadline: {{ event.deadline|date:"M d, H:i" }}</p>
  </header>
  
  {# Custom content from card_context #}
  {% if card_context.custom_data %}
    <div class="custom-section">
      {{ card_context.custom_data }}
    </div>
  {% endif %}
  
  {# Prediction options - standard pattern #}
  {% if active_user %}
    <div class="options">
      {% for option in event.options.all %}
        <label>
          <input type="radio" 
                 name="prediction_{{ event.id }}" 
                 value="{{ option.id }}" 
                 form="tips-form"
                 {% if user_tip and user_tip.prediction_option_id == option.id %}checked{% endif %} />
          {{ option.label }}
        </label>
      {% endfor %}
    </div>
    
    {# Lock option #}
    <label>
      <input type="checkbox" 
             name="lock_{{ event.id }}" 
             value="1" 
             form="tips-form"
             {% if user_tip and user_tip.is_locked %}checked{% endif %} />
      Lock this pick
    </label>
  {% endif %}
</article>
```

### Step 3: Register the Renderer

```python
# myapp/apps.py

from django.apps import AppConfig

class MyAppConfig(AppConfig):
    name = 'myapp'
    
    def ready(self):
        from hooptipp.predictions.card_renderers.registry import register
        from .card_renderer import MyCardRenderer
        
        register(MyCardRenderer())
```

## NBA Implementation Example

The NBA app demonstrates the complete implementation:

### Files Created

- `hooptipp/nba/card_renderer.py` - NBA card renderer
- `hooptipp/nba/templates/nba/cards/game.html` - NBA game prediction card
- `hooptipp/nba/templates/nba/cards/game_result.html` - NBA game result card
- `hooptipp/nba/templates/nba/cards/mvp.html` - NBA MVP prediction card
- `hooptipp/nba/templates/nba/cards/playoff_series.html` - NBA playoff series card
- `hooptipp/nba/services.py` - Helper functions (get_team_logo_url, get_live_game_data, etc.)

### Features Demonstrated

1. **Multiple card types** - Different templates for games, MVP, playoffs
2. **Dynamic context** - Team logos, live scores, playoff series info
3. **Caching** - Live data cached for 30 seconds to avoid API rate limits
4. **Graceful fallback** - Missing logos handled with error callbacks

## Usage in Templates

Replace manual card rendering with the template tag:

**Before:**
```django
{% for event in open_predictions %}
  <article class="...">
    {# Lots of manual HTML #}
  </article>
{% endfor %}
```

**After:**
```django
{% load prediction_extras %}

{% for event in open_predictions %}
  {% with user_tip=user_tips|get_item:event.id %}
    {% render_prediction_card event user_tip %}
  {% endwith %}
{% endfor %}
```

For resolved predictions:
```django
{% for item in resolved_predictions %}
  {% render_result_card item.outcome item.user_tip item.is_correct %}
{% endfor %}
```

## Available Context Variables

Templates have access to:

### Event Cards
- `event` - The PredictionEvent instance
- `user_tip` - User's current tip (if any)
- `active_user` - Currently active user
- `lock_summary` - Lock availability info
- `card_context` - Custom context from the renderer
- `palette` - Active theme palette

### Result Cards
- `outcome` - The EventOutcome instance
- `event` - The PredictionEvent (same as outcome.prediction_event)
- `user_tip` - User's tip for this event
- `is_correct` - Boolean indicating if prediction was correct
- `active_user` - Currently active user
- `card_context` - Custom context from the renderer
- `palette` - Active theme palette

## Benefits

✅ **Clean separation** - UI logic separate from data management  
✅ **Extensible** - New apps just register their renderer  
✅ **Type-based routing** - Renderers claim events they can handle  
✅ **Priority system** - Handle overlapping renderers gracefully  
✅ **Event/result separation** - Different layouts for open vs resolved  
✅ **No pollution** - Base package stays generic  
✅ **Auto-registration** - Extensions register in apps.py  
✅ **Fallback** - Default renderer handles anything unclaimed  

## Future Extensions

Adding new card types is straightforward:

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
            'country_flags': self._get_country_flags(event),
            'athlete_photos': self._get_athlete_photos(event),
            'current_standings': self._get_standings(event),
        }

# olympics/apps.py
def ready(self):
    from hooptipp.predictions.card_renderers.registry import register
    from .card_renderer import OlympicsCardRenderer
    register(OlympicsCardRenderer())
```

## Testing

The card renderer system can be tested independently:

```python
from hooptipp.predictions.card_renderers.registry import registry

# Get renderer for an event
event = PredictionEvent.objects.get(pk=1)
renderer = registry.get_renderer(event)

# Check template
template = renderer.get_event_template(event)
assert template == "nba/cards/game.html"

# Check context
context = renderer.get_event_context(event)
assert 'away_team_logo' in context
```
