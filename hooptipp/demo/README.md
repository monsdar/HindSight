# Demo Package

The demo package provides a way to quickly create demo PredictableEvents for manual testing and demonstration purposes.

## Features

The demo package creates four types of demo events:

1. **Yes/No Question** - Simple binary choice with custom styling
2. **Color Choice** - Multiple choice with visual color swatches
3. **Bonus Event** - Special event with enhanced styling and bonus points
4. **Player Championship** - Player-type prediction with character selection

## Usage

### Admin Interface

1. Log in to the Django admin at `/admin/`
2. Navigate to the "Demo" section
3. Click on "Add Demo Events"
4. Click the "Create Demo Events" button
5. The events will be created with:
   - Opens at: Current time
   - Deadline: 5 minutes from creation time
   - Active status: True

### Programmatic Usage

You can also create demo events programmatically:

```python
from django.contrib.auth.models import User
from django.test import Client

client = Client()
admin_user = User.objects.get(username='admin')
client.force_login(admin_user)

# POST to create demo events
response = client.post('/admin/demo/events/add-demo/')
```

## Templates

The demo package includes custom card templates that showcase different features:

- `demo/cards/yesno.html` - Binary choice with large buttons
- `demo/cards/colors.html` - Color swatches with visual selection
- `demo/cards/bonus.html` - Animated bonus event with special styling
- `demo/cards/player.html` - Player cards with avatars
- Result templates for each event type

## Options

The demo package creates the following option categories:

- `demo-yesno` - Yes and No options
- `demo-colors` - Red, Blue, Green, Yellow, Purple options
- `demo-characters` - Alice Wonder, Bob Builder, Charlie Champion, Diana Dreamer

## Card Renderer

The demo package registers a custom card renderer (`DemoCardRenderer`) that:

- Matches events with `source_id='demo'`
- Provides custom templates based on event type
- Adds custom context data (e.g., color hex values)
- Works seamlessly with the prediction system

## Testing

Run the demo tests:

```bash
python manage.py test hooptipp.demo
```

All tests should pass, verifying:
- Admin view functionality
- Event creation
- Option creation
- Card renderer behavior
- Template selection

## Architecture

The demo package follows the same architecture as the NBA package:

- **No models** - Uses generic prediction system models
- **Custom card renderer** - Registered in `apps.py`
- **Admin actions** - Custom views for creating events
- **Separation of concerns** - Demo-specific logic stays in demo package
