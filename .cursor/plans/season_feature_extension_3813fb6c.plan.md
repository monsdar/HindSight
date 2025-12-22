---
name: Season Feature Extension
overview: Extend the Season feature to add enrollment, season information display, countdown timers, and season results. Users must enroll in seasons to participate, and the UI will show season details, participant counts, and countdown timers.
todos:
  - id: create_season_participant_model
    content: Create SeasonParticipant model with user and season ForeignKeys, enrolled_at timestamp, and unique constraint
    status: completed
  - id: add_enrollment_view
    content: Add enroll_in_season POST endpoint in views.py to handle user enrollment
    status: completed
    dependencies:
      - create_season_participant_model
  - id: update_home_view_season_logic
    content: Update home view to get next upcoming season, check enrollment status, calculate participant counts, and prepare season results data
    status: completed
    dependencies:
      - create_season_participant_model
  - id: add_markdown_rendering
    content: Add markdown2 rendering for season descriptions in view (reuse impressum pattern)
    status: completed
    dependencies:
      - update_home_view_season_logic
  - id: add_season_info_section
    content: Add Season Information section to home.html template with description, participant count, countdown, and sign-up button
    status: completed
    dependencies:
      - update_home_view_season_logic
      - add_markdown_rendering
  - id: add_season_results_section
    content: Add Season Results section to home.html template showing ended season stats (top 3, participant count, total picks)
    status: completed
    dependencies:
      - update_home_view_season_logic
  - id: conditional_leaderboard
    content: Update leaderboard section to show when active_season exists (regardless of enrollment) - allows users to see competition before enrolling
    status: completed
    dependencies:
      - update_home_view_season_logic
  - id: disable_predictions_when_not_enrolled
    content: Add disabled state to prediction cards when no active season or user not enrolled
    status: completed
    dependencies:
      - update_home_view_season_logic
  - id: add_countdown_javascript
    content: Add JavaScript for countdown timer calculation and display (days only)
    status: completed
    dependencies:
      - add_season_info_section
  - id: update_admin
    content: Add SeasonParticipant admin and update SeasonAdmin with inline participant management
    status: completed
    dependencies:
      - create_season_participant_model
  - id: add_url_route
    content: Add enroll_in_season URL route to urls.py
    status: completed
    dependencies:
      - add_enrollment_view
  - id: create_migration
    content: Run makemigrations to create SeasonParticipant migration
    status: completed
    dependencies:
      - create_season_participant_model
  - id: add_tests
    content: Add unit tests for SeasonParticipant model, enrollment endpoint, view logic, and template rendering
    status: completed
    dependencies:
      - create_season_participant_model
      - add_enrollment_view
      - update_home_view_season_logic
---

# Season Feature Extension Plan

## Overview

Extend the Season feature to require user enrollment, display season information with markdown support, show participant counts and countdown timers, and add a "Season Results" section for recently ended seasons.

## Architecture Changes

### 1. Database Models

**New Model: `SeasonParticipant`** (`hooptipp/predictions/models.py`)

- Many-to-many relationship between User and Season
- Fields: `user` (ForeignKey), `season` (ForeignKey), `enrolled_at` (DateTimeField, auto_now_add)
- Unique constraint on `(user, season)`
- Meta: ordering by `-enrolled_at`

### 2. View Logic Updates (`hooptipp/predictions/views.py`)

**Season Selection Logic:**

- Get active season using `Season.get_active_season()`
- If no active season, get next upcoming season: `Season.objects.filter(start_date__gt=timezone.now().date()).order_by('start_date').first()`
- Check if season ended within last 7 days for "Season Results" section

**Enrollment Check:**

- Add `is_enrolled` boolean to context (check if `active_user` is enrolled in displayed season)
- Add `participant_count` (count of users enrolled in season)
- Add enrollment endpoint: `enroll_in_season(request)` - POST handler to enroll active user

**Leaderboard Visibility:**

- Show leaderboard if `active_season` exists (regardless of enrollment status)
- This allows users to see who's playing and what they're competing against before enrolling
- Hide leaderboard section entirely when no active season

**Prediction Interaction:**

- Disable prediction cards when no active season OR user not enrolled
- Add visual indicator (disabled state) on prediction cards

**Season Results:**

- Calculate statistics for ended seasons (within 7 days of end_date)
- Get top 3 users from season leaderboard
- Count total picks made during season
- Render season description with markdown2 (reuse pattern from impressum views)

### 3. Template Updates (`hooptipp/predictions/templates/predictions/home.html`)

**New Section Order:**

1. **Season Information Section** (top of page)

- Show season name as heading
- Render description with markdown2 (reuse `prose prose-invert` classes)
- Show participant count
- Show countdown timer (days until start/end)
- Show "Sign Up" button if user not enrolled
- Only show if active season OR upcoming season exists

2. **Season Results Section** (after Season Information, if applicable)

- Show for seasons ended within last 7 days
- Display season description (markdown)
- Show statistics: participant count, total picks, top 3 places
- Hide after 7 days

3. **Leaderboard Section** (existing, conditional)

- Only show if `active_season` exists AND `active_user.is_enrolled`
- Hide completely otherwise (not just empty state)

4. **Open Predictions Section** (existing)

- Add disabled state styling when no active season or user not enrolled
- Prevent interaction (disable buttons/inputs)

### 4. Markdown Rendering

**Reuse Existing Pattern:**

- Use `markdown2.markdown()` with extras: `['fenced-code-blocks', 'tables', 'break-on-newline', 'cuddled-lists']`
- Render in template with: `<div class="text-slate-300 prose prose-invert max-w-none">{{ description_html|safe }}</div>`
- Convert season description to HTML in view before passing to template

### 5. Countdown Timer

**JavaScript Implementation:**

- Calculate days until season start (if upcoming) or days until season end (if active)
- Display format: "X days until start" or "X days remaining"
- Update daily (no need for real-time updates)

### 6. URL Routing (`hooptipp/predictions/urls.py`)

**New Endpoint:**

- `enroll_in_season/` - POST endpoint for season enrollment
- Returns JSON response with success/error status

### 7. Admin Updates (`hooptipp/predictions/admin.py`)

**SeasonAdmin:**

- Add inline admin for `SeasonParticipant` to view/manage enrollments
- Show participant count in list display

## Implementation Details

### Season Participant Count

```python
participant_count = SeasonParticipant.objects.filter(season=season).count()
```



### Enrollment Check

```python
is_enrolled = False
if active_user and season:
    is_enrolled = SeasonParticipant.objects.filter(
        user=active_user, 
        season=season
    ).exists()
```



### Countdown Calculation

```python
from datetime import date, timedelta
today = timezone.now().date()
if season.start_date > today:
    days_until = (season.start_date - today).days
    countdown_text = f"{days_until} days until start"
elif season.end_date >= today:
    days_remaining = (season.end_date - today).days
    countdown_text = f"{days_remaining} days remaining"
```



### Season Results Statistics

```python
# Get top 3 users for season
season_scores = UserEventScore.objects.filter(
    awarded_at__date__gte=season.start_date,
    awarded_at__date__lte=season.end_date
)
top_users = (season_scores.values('user')
    .annotate(total_points=Sum('points_awarded'))
    .order_by('-total_points')[:3])

# Count total picks
total_picks = UserTip.objects.filter(
    prediction_event__deadline__date__gte=season.start_date,
    prediction_event__deadline__date__lte=season.end_date
).count()
```



## Testing Requirements

1. **Model Tests** (`hooptipp/predictions/tests/test_seasons.py`)

- Test `SeasonParticipant` model creation
- Test unique constraint on (user, season)
- Test enrollment queries

2. **View Tests** (`hooptipp/predictions/tests/test_views.py`)

- Test season enrollment endpoint
- Test leaderboard visibility when active season exists (should show regardless of enrollment)
- Test prediction card disabled state
- Test season results section display logic
- Test countdown calculations

3. **Template Tests**

- Test markdown rendering in season description
- Test conditional display of sections

## Migration

Create migration for `SeasonParticipant` model:

- Run `python manage.py makemigrations`
- Migration will create the new model and unique constraint

## Files to Modify

1. `hooptipp/predictions/models.py` - Add `SeasonParticipant` model
2. `hooptipp/predictions/views.py` - Add enrollment logic, season selection, statistics calculation
3. `hooptipp/predictions/templates/predictions/home.html` - Add Season Information and Season Results sections, conditionally show leaderboard
4. `hooptipp/predictions/urls.py` - Add enrollment endpoint
5. `hooptipp/predictions/admin.py` - Add `SeasonParticipant` admin, update `SeasonAdmin`
6. `hooptipp/predictions/tests/test_seasons.py` - Add enrollment tests
7. `hooptipp/predictions/tests/test_views.py` - Add view tests for new functionality

## Notes

- Reuse existing markdown2 pattern from impressum/teilnahmebedingungen views