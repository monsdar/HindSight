"""Custom adapters for django-allauth."""

from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.account.adapter import DefaultAccountAdapter

from hooptipp.predictions.models import UserPreferences


class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    Custom adapter to handle OAuth signups.
    
    Automatically creates UserPreferences and extracts nickname from OAuth provider data.
    """
    
    def save_user(self, request, sociallogin, form=None):
        """
        Save user from social login and create UserPreferences.
        
        Args:
            request: The HTTP request
            sociallogin: The social login instance
            form: Optional form (not used in auto-signup)
            
        Returns:
            The saved user instance
        """
        # Call parent to create the user
        user = super().save_user(request, sociallogin, form=form)
        
        # Ensure user is active (OAuth providers verify emails)
        user.is_active = True
        user.save()
        
        # Create UserPreferences if they don't exist
        if not hasattr(user, 'preferences'):
            # Extract nickname from social account data
            nickname = ''
            if sociallogin.account.extra_data:
                # Try to get name from Google OAuth data
                name = sociallogin.account.extra_data.get('name', '')
                if name:
                    nickname = name
                else:
                    # Fallback to given_name or family_name
                    given_name = sociallogin.account.extra_data.get('given_name', '')
                    family_name = sociallogin.account.extra_data.get('family_name', '')
                    if given_name or family_name:
                        nickname = f"{given_name} {family_name}".strip()
            
            # Create UserPreferences
            UserPreferences.objects.create(
                user=user,
                nickname=nickname
            )
        
        return user
    
    def populate_user(self, request, sociallogin, data):
        """
        Populate user fields from social account data.
        
        Args:
            request: The HTTP request
            sociallogin: The social login instance
            data: Dictionary of user data from provider
            
        Returns:
            User instance (not yet saved)
        """
        user = super().populate_user(request, sociallogin, data)
        
        # Generate username from email if not provided
        if not user.username and user.email:
            # Use email as username (before @ symbol)
            user.username = user.email.split('@')[0]
            # Ensure uniqueness
            from django.contrib.auth import get_user_model
            User = get_user_model()
            base_username = user.username
            counter = 1
            while User.objects.filter(username=user.username).exists():
                user.username = f"{base_username}{counter}"
                counter += 1
        
        return user

