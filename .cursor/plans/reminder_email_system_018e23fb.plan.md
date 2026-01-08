---
name: Reminder Email System
overview: Add a management command that sends reminder emails to active users with unpredicted events due in 24 hours, with an option to disable reminders via email link. Emails are in German.
todos:
  - id: "1"
    content: Add reminder_emails_enabled field to UserPreferences model and create migration
    status: completed
  - id: "2"
    content: Create German email templates (HTML and plain text) for reminder emails
    status: completed
  - id: "3"
    content: Create send_reminder_email utility function
    status: completed
    dependencies:
      - "2"
  - id: "4"
    content: Implement management command send_reminder_emails with filtering logic
    status: completed
    dependencies:
      - "1"
      - "3"
  - id: "5"
    content: Create disable_reminder_emails view and confirmation template
    status: completed
    dependencies:
      - "1"
  - id: "6"
    content: Add URL pattern for disable reminders endpoint
    status: completed
    dependencies:
      - "5"
  - id: "7"
    content: Add reminder_emails_enabled to admin interface
    status: pending
    dependencies:
      - "1"
  - id: "8"
    content: Create comprehensive test suite for reminder email functionality
    status: pending
    dependencies:
      - "4"
      - "5"
---

# Reminder Email System Implementation

## Overview

Add a reminder email system that sends notifications to active users about unpredicted events with deadlines in the next 24 hours. The system includes a mechanism to disable reminders via a link in the email.

## Components

### 1. Database Model Changes

- **File**: [`hooptipp/predictions/models.py`](hooptipp/predictions/models.py)
- Add `reminder_emails_enabled` BooleanField to `UserPreferences` model (default=True)
- This field indicates whether the user wants to receive reminder emails
- Create migration using `makemigrations`

### 2. Management Command

- **File**: [`hooptipp/predictions/management/commands/send_reminder_emails.py`](hooptipp/predictions/management/commands/send_reminder_emails.py) (new file)
- Logic:
- Filter users: `is_active=True`, `reminder_emails_enabled=True` in preferences
- For each user:
    - Find the most recent event (by deadline) that has already passed
    - Only proceed if user has a UserTip for that event (prevents spamming inactive users)
    - Find events where:
    - `deadline` is within next 24 hours
    - `is_active=True`, `opens_at <= now`
    - User has no UserTip for the event
    - **Season enrollment filtering**: If a season is active:
        - For each unpredicted event, determine which season it belongs to (if any) by checking if the event's deadline falls within a season's timeframe (`season.start_datetime <= event.deadline <= season.end_datetime`)
        - Only include events where:
            - The event doesn't belong to any season, OR
            - The event belongs to the active season AND the user is enrolled in that season (via `SeasonParticipant`)
        - Skip events that belong to a season where the user is not enrolled
    - If unpredicted events exist (after season filtering), send reminder email with summary
- Include `--dry-run` option for testing
- Log results and errors appropriately

### 3. Email Templates (German)

- **Files**: 
- [`templates/emails/reminder_email.html`](templates/emails/reminder_email.html) (new file)
- [`templates/emails/reminder_email.txt`](templates/emails/reminder_email.txt) (new file)
- German content with:
- Subject: Reminder about upcoming predictions
- Summary of events with deadlines in next 24 hours (event name, deadline time)
- Button/link to view predictions page
- Button/link to disable future reminder emails
- Follow existing email template style (similar to `verification_email.html`)

### 4. Email Sending Function

- **File**: [`hooptipp/predictions/views.py`](hooptipp/predictions/views.py) or new utility file
- Create function `send_reminder_email(user, events)` that:
- Builds absolute URL for predictions page and disable reminders link
- Renders German email templates
- Sends email using Django's `send_mail`

### 5. Disable Reminders View

- **File**: [`hooptipp/predictions/views.py`](hooptipp/predictions/views.py)
- Create view `disable_reminder_emails(request, uidb64, token)`:
- Uses Django token generator (like email verification)
- Validates token and updates `UserPreferences.reminder_emails_enabled = False`
- Shows confirmation message (German)
- Create template for confirmation page

### 6. URL Configuration

- **File**: [`hooptipp/predictions/urls.py`](hooptipp/predictions/urls.py)
- Add URL pattern for disable reminders endpoint: `disable-reminders/<uidb64>/<token>/`

### 7. Tests

- **File**: [`hooptipp/predictions/tests/test_reminder_emails.py`](hooptipp/predictions/tests/test_reminder_emails.py) (new file)
- Test cases:
- Management command sends emails to eligible users
- Management command skips users without recent predictions
- Management command skips users with disabled reminders
- Management command skips inactive users
- Management command filters events by season enrollment (only includes events for seasons user is enrolled in)
- Management command includes events that don't belong to any season
- Management command excludes events from active season when user is not enrolled
- Disable reminders view updates preferences correctly
- Disable reminders view validates token
- Email content is correct (German, includes event summary)

### 8. Admin Integration (Optional)

- **File**: [`hooptipp/predictions/admin.py`](hooptipp/predictions/admin.py)
- Add `reminder_emails_enabled` field to UserPreferencesAdmin fieldsets

## Implementation Details

### Event Query Logic

```python
# Most recent passed event
latest_passed_event = PredictionEvent.objects.filter(
    is_active=True,
    deadline__lt=now
).order_by('-deadline').first()

# Check if user predicted it
has_predicted_latest = UserTip.objects.filter(
    user=user,
    prediction_event=latest_passed_event
).exists()

# Unpredicted events in next 24 hours
unpredicted_events = PredictionEvent.objects.filter(
    is_active=True,
    opens_at__lte=now,
    deadline__gte=now,
    deadline__lte=now + timedelta(hours=24)
).exclude(
    tips__user=user
).order_by('deadline')

# Season enrollment filtering
active_season = Season.get_active_season()
if active_season:
    # Get all seasons to check event membership
    all_seasons = Season.objects.exclude(start_date__isnull=True).exclude(end_date__isnull=True)
    
    # Filter events based on season enrollment
    eligible_events = []
    for event in unpredicted_events:
        # Find which season (if any) contains this event's deadline
        event_season = None
        for season in all_seasons:
            if season.start_datetime <= event.deadline <= season.end_datetime:
                event_season = season
                break
        
        if event_season is None:
            # Event doesn't belong to any season - include it
            eligible_events.append(event)
        elif event_season == active_season:
            # Event belongs to active season - check enrollment
            is_enrolled = SeasonParticipant.objects.filter(
                user=user,
                season=active_season
            ).exists()
            if is_enrolled:
                eligible_events.append(event)
            # If not enrolled, skip this event
        # If event belongs to a different season (shouldn't happen if only one active), skip it
    
    unpredicted_events = eligible_events
```



### Email Token Generation

Use Django's `default_token_generator` (same as email verification) for the disable reminders link, ensuring security and consistency.

### Cron Job Setup

Document that the command should be run at 2AM daily. Since this is a Django management command, it can be scheduled via:

- System cron (Linux/Mac)
- Task Scheduler (Windows)
- Railway cron jobs (if applicable)
- Or other scheduling mechanisms

## Files to Modify/Create

**Modified:**

- `hooptipp/predictions/models.py` - Add reminder_emails_enabled field
- `hooptipp/predictions/admin.py` - Add field to admin (optional)
- `hooptipp/predictions/views.py` - Add disable_reminders view
- `hooptipp/predictions/urls.py` - Add URL pattern

**Created:**

- `hooptipp/predictions/management/commands/send_reminder_emails.py` - Management command
- `templates/emails/reminder_email.html` - German HTML email template
- `templates/emails/reminder_email.txt` - German plain text email template
- `templates/predictions/disable_reminders_done.html` - Confirmation page template
- `hooptipp/predictions/tests/test_reminder_emails.py` - Test suite
- Migration file (auto-generated)
- Migration file (auto-generated)

## Season Enrollment Logic

When a season is active, the reminder system checks enrollment before including events:

1. **Determine event's season**: For each unpredicted event, check if the event's deadline falls within any season's timeframe (`season.start_datetime <= event.deadline <= season.end_datetime`)
2. **Filter by enrollment**:

- Events that don't belong to any season are always included (backward compatibility)
- Events belonging to the active season are only included if the user is enrolled via `SeasonParticipant`
- Events belonging to other seasons are excluded (shouldn't occur since only one season can be active)