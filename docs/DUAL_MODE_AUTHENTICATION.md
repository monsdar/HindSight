# Dual-Mode Authentication Implementation

This document explains the dual-mode authentication system implemented in HindSight.

## Overview

HindSight now supports two deployment modes:
- **User Selection Mode** (Private/Family): Simple dropdown-based user activation
- **Authentication Mode** (Public): Traditional signup/login system

Both modes use the same codebase and database schema.

## Architecture

### Core Module: `hooptipp/user_context.py`

This module provides a unified interface for user management across both modes:

- `get_active_user(request)`: Returns the active user regardless of mode
- `set_active_user(request, user)`: Sets the active user
- `clear_active_user(request)`: Clears the active user
- `is_user_active(request)`: Checks if a user is active
- `requires_active_user`: Decorator for views requiring an active user

### Mode Detection

The mode is determined by the `ENABLE_USER_SELECTION` environment variable:
- `True` (default): User Selection Mode
- `False`: Authentication Mode

## Implementation Details

### 1. User Context (`hooptipp/user_context.py`)

**User Selection Mode:**
- Stores user ID in session: `request.session['active_user_id']`
- No Django authentication required
- Works for trusted environments (family/private)

**Authentication Mode:**
- Uses Django's built-in authentication: `request.user`
- Ignores session-based activation
- Requires login for all actions

### 2. Views (`hooptipp/predictions/views.py`)

All views now use `get_active_user(request)` instead of direct session access:

```python
from hooptipp.user_context import get_active_user

def home(request):
    active_user = get_active_user(request)
    # ... rest of view logic
```

### 3. Middleware (`hooptipp/middleware.py`)

`PrivacyGateMiddleware` now respects both modes:
- Skips privacy gate if `ENABLE_USER_SELECTION=False`
- Skips privacy gate for authenticated users (allows admins to bypass)
- Only enforces privacy gate in User Selection Mode

### 4. Templates

#### Navigation (`templates/base.html`)

Shows different navigation based on mode:

**User Selection Mode:**
- Shows active user name
- No login/signup links

**Authentication Mode:**
- Shows login/signup links when not authenticated
- Shows username and logout link when authenticated

### 5. Authentication Views (`hooptipp/auth_views.py`)

New views for authentication mode:
- `signup`: User registration
- `profile`: User profile management (redirects to home currently)

These views automatically redirect when in User Selection Mode.

### 6. URL Configuration (`hooptipp/urls.py`)

All authentication URLs are always available:
- `/login/`: Login page
- `/logout/`: Logout action
- `/signup/`: Registration page
- `/password-reset/`: Password reset flow
- `/privacy-gate/`: Privacy gate (only used in User Selection Mode)

## Configuration

### Private/Family Deployment

```bash
ENABLE_USER_SELECTION=True
PRIVACY_GATE_ENABLED=True
PRIVACY_GATE_ANSWER=GSW,LAL,BOS,OKC
```

### Public Deployment

```bash
ENABLE_USER_SELECTION=False
PRIVACY_GATE_ENABLED=False

# Email configuration for password reset
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=noreply@yourdomain.com
EMAIL_HOST_PASSWORD=your_password
DEFAULT_FROM_EMAIL=noreply@yourdomain.com
```

## Testing

### Test Structure

- `hooptipp/tests/test_user_context.py`: Tests for unified user context
- `hooptipp/tests/test_auth_views.py`: Tests for authentication views
- Both modes tested with `@override_settings(ENABLE_USER_SELECTION=True/False)`

### Running Tests

```bash
# All tests
python manage.py test

# User context tests only
python manage.py test hooptipp.tests.test_user_context

# Authentication views tests only
python manage.py test hooptipp.tests.test_auth_views
```

## Migration Guide

### From Pure User Selection to Hybrid

No code changes needed! Just:
1. Keep `ENABLE_USER_SELECTION=True`
2. Authentication URLs are available but not advertised
3. Users can still use the dropdown

### From Pure User Selection to Pure Authentication

1. Set `ENABLE_USER_SELECTION=False`
2. Set `PRIVACY_GATE_ENABLED=False`
3. Configure email backend
4. Existing users can login with their existing credentials (set passwords via admin if needed)

### Adding Authentication to Existing Deployment

1. Keep `ENABLE_USER_SELECTION=True` (for existing users)
2. Add authentication URLs to navigation (optional)
3. Allow new users to sign up
4. Both systems work simultaneously

## Code Patterns

### Getting Active User

```python
from hooptipp.user_context import get_active_user

def my_view(request):
    active_user = get_active_user(request)
    if not active_user:
        # Handle no active user
        pass
```

### Requiring Active User

```python
from hooptipp.user_context import requires_active_user

@requires_active_user
def my_view(request):
    # Active user is guaranteed here
    active_user = get_active_user(request)
```

### Setting Active User (User Selection Mode)

```python
from hooptipp.user_context import set_active_user

def activate_user(request, user_id):
    user = get_object_or_404(User, id=user_id)
    set_active_user(request, user)
```

## Benefits

1. **Single Codebase**: One implementation supports both modes
2. **No Migrations**: Same database schema for both modes
3. **Environment-Driven**: Simple config change switches modes
4. **Backward Compatible**: Existing deployments keep working
5. **Future-Proof**: Easy to add more auth methods (OAuth, LDAP, etc.)
6. **Testable**: Both modes tested independently

## Future Enhancements

Potential additions:
- Social auth (Google, Facebook, etc.)
- Two-factor authentication
- LDAP/Active Directory integration
- API token authentication
- Email verification on signup
- User invitation system

