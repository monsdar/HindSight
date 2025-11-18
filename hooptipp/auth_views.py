"""Authentication views for HindSight."""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from hooptipp.predictions.models import UserPreferences


@require_http_methods(["GET", "POST"])
def signup(request):
    """
    User registration view.
    
    Only available when ENABLE_USER_SELECTION is False (authentication mode).
    """
    # Redirect to home if in user selection mode
    if settings.ENABLE_USER_SELECTION:
        messages.info(request, 'User registration is not available in this mode. Please contact an administrator.')
        return redirect('predictions:home')
    
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        password1 = request.POST.get('password1', '')
        password2 = request.POST.get('password2', '')
        nickname = request.POST.get('nickname', '').strip()
        
        # Validation
        errors = []
        
        if not username:
            errors.append('Username is required.')
        elif len(username) < 3:
            errors.append('Username must be at least 3 characters long.')
        
        if not email:
            errors.append('Email is required.')
        
        if not password1:
            errors.append('Password is required.')
        elif len(password1) < 8:
            errors.append('Password must be at least 8 characters long.')
        
        if password1 != password2:
            errors.append('Passwords do not match.')
        
        User = get_user_model()
        
        # Check if username exists
        if username and User.objects.filter(username=username).exists():
            errors.append('Username already exists.')
        
        # Check if email exists
        if email and User.objects.filter(email=email).exists():
            errors.append('Email already exists.')
        
        if errors:
            for error in errors:
                messages.error(request, error)
            return render(request, 'auth/signup.html', {
                'username': username,
                'email': email,
                'nickname': nickname,
            })
        
        # Create user
        try:
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password1
            )
            
            # Create user preferences
            UserPreferences.objects.create(
                user=user,
                nickname=nickname if nickname else ''
            )
            
            # Log the user in
            login(request, user)
            
            messages.success(request, f'Welcome, {username}! Your account has been created.')
            return redirect('predictions:home')
            
        except Exception as e:
            messages.error(request, f'An error occurred while creating your account: {str(e)}')
            return render(request, 'auth/signup.html', {
                'username': username,
                'email': email,
                'nickname': nickname,
            })
    
    return render(request, 'auth/signup.html')


@login_required
def profile(request):
    """
    User profile view.
    
    Allows users to update their preferences.
    Only available in authentication mode.
    """
    if settings.ENABLE_USER_SELECTION:
        messages.info(request, 'Profile editing is not available in this mode.')
        return redirect('predictions:home')
    
    # Redirect to home page - preferences editing is handled there
    return redirect('predictions:home')

