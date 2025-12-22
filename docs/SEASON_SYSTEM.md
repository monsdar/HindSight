# Season System

## Overview

The Season system provides time-bounded scoring periods for predictions. Users must enroll in a season to make predictions, and leaderboards are filtered to show only scores from the active season. This allows for organized competition periods (e.g., "2024-25 NBA Season", "Playoffs 2025") with clear start and end dates.

## Core Concepts

### Season Lifecycle

1. **Upcoming**: Season exists but hasn't started yet (`start_date > today`)
2. **Active**: Season is currently running (`start_date <= today <= end_date`)
3. **Ended**: Season has finished (`end_date < today`)

Only one season can be active at a time. The system enforces non-overlapping date ranges.

### Enrollment

Users must explicitly enroll in a season before they can:
- Make predictions
- Appear on the season leaderboard
- Earn points for that season

Enrollment is optional - users can see the leaderboard and season information without enrolling, but cannot participate until they sign up.

## Models

### Season

**Location**: `hooptipp/predictions/models.py`

Represents a time-bounded scoring period.

**Fields**:
- `name` (CharField): Display name (e.g., "2024-25 NBA Season")
- `start_date` (DateField): First day of the season
- `end_date` (DateField): Last day of the season
- `description` (TextField): Markdown-supported description for season information
- `created_at`, `updated_at` (DateTimeField): Timestamps

**Key Methods**:
- `is_active(check_date=None)`: Check if season is active on a given date
- `get_active_season(check_date=None)`: Class method to get the currently active season

**Validation**:
- `end_date` must be >= `start_date`
- Seasons cannot overlap (enforced in `clean()` method)

**Example**:
```python
from hooptipp.predictions.models import Season
from datetime import date

season = Season.objects.create(
    name="2024-25 NBA Season",
    start_date=date(2024, 10, 1),
    end_date=date(2025, 6, 30),
    description="## Regular Season\n\nPredict NBA games throughout the regular season!"
)

# Check if active
if season.is_active():
    print("Season is currently active")

# Get active season
active = Season.get_active_season()
```

### SeasonParticipant

**Location**: `hooptipp/predictions/models.py`

Tracks user enrollment in seasons.

**Fields**:
- `user` (ForeignKey): The enrolled user
- `season` (ForeignKey): The season they're enrolled in
- `enrolled_at` (DateTimeField): When they enrolled (auto-set)

**Constraints**:
- Unique together: `(user, season)` - users can only enroll once per season

**Example**:
```python
from hooptipp.predictions.models import SeasonParticipant

# Enroll a user
SeasonParticipant.objects.create(user=user, season=season)

# Check enrollment
is_enrolled = SeasonParticipant.objects.filter(
    user=user,
    season=season
).exists()
```

## View Logic

### Home View (`hooptipp/predictions/views.py`)

The home view calculates several season-related values:

#### Season Selection

```python
# Get active season
active_season = Season.get_active_season()

# Get next upcoming season if no active season
next_upcoming_season = None
if not active_season:
    today = timezone.now().date()
    next_upcoming_season = Season.objects.filter(
        start_date__gt=today
    ).order_by('start_date').first()

# Determine which season to display
displayed_season = active_season or next_upcoming_season
```

The `displayed_season` is shown in the UI:
- If there's an active season, show that
- If no active season, show the next upcoming season
- If neither exists, no season section is shown

#### Enrollment Status

```python
is_enrolled = False
if displayed_season and active_user:
    is_enrolled = SeasonParticipant.objects.filter(
        user=active_user,
        season=displayed_season
    ).exists()
```

#### Participant Count

```python
participant_count = SeasonParticipant.objects.filter(
    season=displayed_season
).count()
```

#### Countdown Calculation

```python
today = timezone.now().date()
if displayed_season.start_date > today:
    # Season hasn't started - countdown to start
    days_until = (displayed_season.start_date - today).days
    countdown_text = f"{days_until} day{'s' if days_until != 1 else ''} until season starts"
elif displayed_season.end_date >= today:
    # Season is active - countdown to end
    days_until = (displayed_season.end_date - today).days
    countdown_text = f"{days_until} day{'s' if days_until != 1 else ''} until season ends"
```

#### Season Results

For recently ended seasons (within 7 days), the view calculates:
- Top 3 users by points
- Total picks made
- Participant count
- Rendered markdown description

```python
seven_days_ago = today - timedelta(days=7)
recently_ended_seasons = Season.objects.filter(
    end_date__gte=seven_days_ago,
    end_date__lt=today
).order_by('-end_date')[:1]
```

### Leaderboard Filtering

When an active season exists, the leaderboard:
1. Only shows users enrolled in that season
2. Only counts scores from within the season's date range

```python
if active_season:
    # Filter to enrolled users only
    enrolled_user_ids = SeasonParticipant.objects.filter(
        season=active_season
    ).values_list('user_id', flat=True)
    
    # Filter scores by season date range
    season_filter = Q(
        usereventscore__awarded_at__date__gte=active_season.start_date,
        usereventscore__awarded_at__date__lte=active_season.end_date
    )
    
    leaderboard_users = User.objects.filter(id__in=enrolled_user_ids).annotate(
        total_points=Coalesce(
            Sum('usereventscore__points_awarded', filter=season_filter),
            0
        ),
        event_count=Coalesce(
            Count('usereventscore__prediction_event', distinct=True, filter=season_filter),
            0
        ),
    ).order_by('-total_points', '-event_count', 'username')
```

When no active season exists, the leaderboard shows all-time scores for all users.

### Prediction Restrictions

The `save_prediction` view enforces enrollment:

```python
@require_http_methods(["POST"])
@csrf_exempt
def save_prediction(request):
    active_user = get_active_user(request)
    if not active_user:
        return JsonResponse({'error': 'No active user'}, status=400)
    
    # Check if user is enrolled in active season
    active_season = Season.get_active_season()
    if active_season:
        is_enrolled = SeasonParticipant.objects.filter(
            user=active_user,
            season=active_season
        ).exists()
        if not is_enrolled:
            return JsonResponse({
                'error': 'You must be enrolled in the active season to make predictions'
            }, status=403)
    
    # ... rest of prediction saving logic
```

## API Endpoints

### Enroll in Season

**Endpoint**: `POST /api/enroll-in-season/`

**Request Body**:
```json
{
  "season_id": 1
}
```

**Response** (Success):
```json
{
  "success": true,
  "message": "Successfully enrolled in 2024-25 NBA Season"
}
```

**Response** (Already Enrolled):
```json
{
  "success": true,
  "message": "Already enrolled"
}
```

**Response** (Error):
```json
{
  "error": "Missing season_id"
}
```

**Implementation**: `hooptipp/predictions/views.py::enroll_in_season`

## UI Components

### Season Information Section

**Location**: `hooptipp/predictions/templates/predictions/home.html`

Displayed at the top of the home page when a `displayed_season` exists.

**Shows**:
- Season name (e.g., "Season 2024-25 NBA Season")
- Markdown-rendered description
- Participant count
- Countdown text (days until start/end)
- "Sign Up for Season" button (if user is not enrolled)

**Template Context**:
- `displayed_season`: The season to display
- `season_description_html`: Rendered markdown description
- `participant_count`: Number of enrolled users
- `countdown_text`: Countdown message
- `is_enrolled`: Whether the active user is enrolled

### Season Results Section

**Location**: `hooptipp/predictions/templates/predictions/home.html`

Displayed for recently ended seasons (within 7 days of end date).

**Shows**:
- Season name and description
- Statistics:
  - Participant count
  - Total picks made
  - Number of top finishers
- Top 3 users with their points

**Template Context**:
- `season_results`: Dictionary containing:
  - `season`: The ended season
  - `top_users`: List of top 3 users
  - `total_picks`: Total number of picks
  - `participant_count`: Number of participants
  - `description_html`: Rendered markdown description

### Leaderboard Section

**Location**: `hooptipp/predictions/templates/predictions/home.html`

Only displayed when `active_season` exists.

**Behavior**:
- Shows enrolled users only
- Shows scores from the active season's date range
- Hidden when no active season exists

### Prediction Cards

**Location**: `hooptipp/predictions/templates/predictions/home.html`

Prediction cards are disabled (via CSS `opacity-60 pointer-events-none`) when:
- No active season exists, OR
- User is not enrolled in the active season

**Visual Feedback**:
- Disabled cards show reduced opacity
- Message displayed: "You must be enrolled in the active season to make predictions"

## JavaScript

### Enrollment Button

**Location**: `hooptipp/predictions/templates/predictions/home.html`

Handles the "Sign Up for Season" button click:

```javascript
const enrollSeasonBtn = document.getElementById('enroll-season-btn');
if (enrollSeasonBtn) {
  enrollSeasonBtn.addEventListener('click', async function() {
    const seasonId = this.dataset.seasonId;
    
    // Disable button during request
    this.disabled = true;
    this.textContent = 'Enrolling...';
    
    try {
      const response = await fetch('{% url "predictions:enroll_in_season" %}', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCookie('csrftoken')
        },
        body: JSON.stringify({ season_id: seasonId })
      });
      
      const data = await response.json();
      
      if (data.success) {
        // Reload page to show updated enrollment status
        window.location.reload();
      } else {
        alert('Error: ' + (data.error || 'Failed to enroll in season'));
        this.disabled = false;
        this.textContent = 'Sign Up for Season';
      }
    } catch (error) {
      console.error('Enrollment error:', error);
      alert('Error: Failed to enroll in season. Please try again.');
      this.disabled = false;
      this.textContent = 'Sign Up for Season';
    }
  });
}
```

## Admin Interface

### Season Admin

**Location**: `hooptipp/predictions/admin.py`

**Features**:
- List display: name, start_date, end_date, status, participant count, created_at
- List filters: start_date, end_date
- Search: name, description
- Date hierarchy: start_date
- Inline: SeasonParticipant (read-only, cannot delete)

**Custom Display Methods**:
- `is_active_display()`: Shows "● Active" or "○ Inactive"
- `participant_count_display()`: Shows number of enrolled users

### SeasonParticipant Inline

**Location**: `hooptipp/predictions/admin.py`

**Features**:
- Read-only fields: user, enrolled_at
- Cannot delete enrollments (prevents accidental removal)
- Shows all participants for a season

## Markdown Support

Season descriptions support markdown rendering using `markdown2`:

```python
import markdown2

season_description_html = markdown2.markdown(
    season.description,
    extras=['fenced-code-blocks', 'tables', 'break-on-newline']
)
```

**Supported Features**:
- Headers
- Lists
- Code blocks
- Tables
- Line breaks

## Context Variables

The home view provides these season-related context variables:

- `active_season`: Currently active season (None if none active)
- `displayed_season`: Season to display in UI (active or next upcoming)
- `is_enrolled`: Whether active user is enrolled in displayed_season
- `participant_count`: Number of users enrolled in displayed_season
- `season_description_html`: Rendered markdown description
- `countdown_text`: Countdown message (days until start/end)
- `season_results`: Dictionary with results for recently ended season (None if none)

## Best Practices

### Creating Seasons

1. **Non-overlapping dates**: Ensure seasons don't overlap
2. **Clear names**: Use descriptive names (e.g., "2024-25 NBA Regular Season")
3. **Descriptive descriptions**: Use markdown to provide clear information
4. **Reasonable duration**: Consider the length of your competition period

### Enrollment Flow

1. Users can see season information without enrolling
2. Users can see the leaderboard (if active season exists) without enrolling
3. Users must enroll to make predictions
4. Enrollment is one-time per season (enforced by unique constraint)

### Leaderboard Behavior

- **With active season**: Shows only enrolled users, only season scores
- **Without active season**: Shows all users, all-time scores
- Leaderboard is hidden when no active season exists

## Future Enhancements

Potential areas for extension:

1. **Season-specific achievements**: Awards for top finishers, milestones, etc.
2. **Season statistics**: More detailed analytics (win rate, favorite teams, etc.)
3. **Season history**: Archive of past seasons with full results
4. **Season invitations**: Invite users to specific seasons
5. **Season groups**: Organize seasons into leagues or tournaments
6. **Season settings**: Per-season configuration (scoring rules, etc.)

