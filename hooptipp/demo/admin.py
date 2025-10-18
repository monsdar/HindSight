"""Demo admin customizations."""

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db import models
from django.http import HttpRequest, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from datetime import timedelta

from hooptipp.predictions.models import (
    Option,
    OptionCategory,
    PredictionEvent,
    PredictionOption,
    TipType,
)


def create_demo_events_view(request: HttpRequest):
    """Create demo PredictableEvents for testing and demonstration."""
    if request.method != 'POST':
        from django.shortcuts import render
        context = {
            'title': 'Add Demo Events',
            'app_label': 'demo',
            'has_permission': True,
        }
        return render(request, 'admin/demo/add_demo_events.html', context)
    
    if not request.user.has_perm('predictions.add_predictionevent'):
        raise PermissionDenied
    
    now = timezone.now()
    deadline = now + timedelta(minutes=5)
    
    # Get or create demo tip type
    tip_type, _ = TipType.objects.get_or_create(
        slug='demo-tips',
        defaults={
            'name': 'Demo Tips',
            'description': 'Demo events for testing and demonstration purposes',
            'category': TipType.TipCategory.GAME,
            'deadline': deadline,
            'is_active': True,
        },
    )
    
    # Ensure we have demo option categories and options
    _setup_demo_options()
    
    created_events = []
    
    # Event 1: Simple yes/no question
    event1 = _create_yes_no_event(tip_type, now, deadline)
    if event1:
        created_events.append(event1)
    
    # Event 2: Multiple choice with colors
    event2 = _create_color_choice_event(tip_type, now, deadline)
    if event2:
        created_events.append(event2)
    
    # Event 3: Bonus event with custom styling
    event3 = _create_bonus_event(tip_type, now, deadline)
    if event3:
        created_events.append(event3)
    
    # Event 4: Player-type prediction
    event4 = _create_player_event(tip_type, now, deadline)
    if event4:
        created_events.append(event4)
    
    if created_events:
        messages.success(
            request,
            f'Successfully created {len(created_events)} demo prediction event(s). '
            f'They will expire in 5 minutes at {deadline.strftime("%H:%M:%S")}.'
        )
    else:
        messages.warning(request, 'No demo events were created.')
    
    return HttpResponseRedirect(reverse('admin:predictions_predictionevent_changelist'))


def _setup_demo_options():
    """Ensure demo option categories and options exist."""
    # Yes/No category
    yesno_cat, _ = OptionCategory.objects.get_or_create(
        slug='demo-yesno',
        defaults={
            'name': 'Yes/No',
            'description': 'Simple yes or no answers',
            'icon': 'check',
            'is_active': True,
        },
    )
    
    Option.objects.get_or_create(
        category=yesno_cat,
        slug='yes',
        defaults={
            'name': 'Yes',
            'short_name': 'Y',
            'is_active': True,
        },
    )
    
    Option.objects.get_or_create(
        category=yesno_cat,
        slug='no',
        defaults={
            'name': 'No',
            'short_name': 'N',
            'is_active': True,
        },
    )
    
    # Colors category
    colors_cat, _ = OptionCategory.objects.get_or_create(
        slug='demo-colors',
        defaults={
            'name': 'Colors',
            'description': 'Color choices',
            'icon': 'palette',
            'is_active': True,
        },
    )
    
    colors = [
        ('red', 'Red', '#ef4444'),
        ('blue', 'Blue', '#3b82f6'),
        ('green', 'Green', '#10b981'),
        ('yellow', 'Yellow', '#f59e0b'),
        ('purple', 'Purple', '#a855f7'),
    ]
    
    for slug, name, hex_color in colors:
        Option.objects.get_or_create(
            category=colors_cat,
            slug=slug,
            defaults={
                'name': name,
                'short_name': name[0],
                'metadata': {'color': hex_color},
                'is_active': True,
            },
        )
    
    # Demo characters category (for player-like predictions)
    chars_cat, _ = OptionCategory.objects.get_or_create(
        slug='demo-characters',
        defaults={
            'name': 'Demo Characters',
            'description': 'Fictional characters for demo predictions',
            'icon': 'user',
            'is_active': True,
        },
    )
    
    characters = [
        ('alice', 'Alice Wonder', 'AW'),
        ('bob', 'Bob Builder', 'BB'),
        ('charlie', 'Charlie Champion', 'CC'),
        ('diana', 'Diana Dreamer', 'DD'),
    ]
    
    for slug, name, short in characters:
        Option.objects.get_or_create(
            category=chars_cat,
            slug=slug,
            defaults={
                'name': name,
                'short_name': short,
                'is_active': True,
            },
        )


def _create_yes_no_event(tip_type, opens_at, deadline):
    """Create a simple yes/no demo event."""
    event_id = f'demo-yesno-{opens_at.timestamp()}'
    
    if PredictionEvent.objects.filter(
        source_id='demo',
        source_event_id=event_id
    ).exists():
        return None
    
    event = PredictionEvent.objects.create(
        tip_type=tip_type,
        name='Will it rain tomorrow?',
        description='A simple yes/no prediction to demonstrate basic functionality',
        target_kind=PredictionEvent.TargetKind.GENERIC,
        selection_mode=PredictionEvent.SelectionMode.CURATED,
        source_id='demo',
        source_event_id=event_id,
        metadata={
            'event_type': 'yesno',
            'demo': True,
        },
        opens_at=opens_at,
        deadline=deadline,
        reveal_at=opens_at,
        is_active=True,
        points=1,
    )
    
    # Add yes/no options
    yesno_cat = OptionCategory.objects.get(slug='demo-yesno')
    yes_option = Option.objects.get(category=yesno_cat, slug='yes')
    no_option = Option.objects.get(category=yesno_cat, slug='no')
    
    PredictionOption.objects.create(
        event=event,
        option=yes_option,
        label='Yes, it will rain',
        sort_order=1,
    )
    
    PredictionOption.objects.create(
        event=event,
        option=no_option,
        label='No, it will be sunny',
        sort_order=2,
    )
    
    return event


def _create_color_choice_event(tip_type, opens_at, deadline):
    """Create a multiple choice color event."""
    event_id = f'demo-colors-{opens_at.timestamp()}'
    
    if PredictionEvent.objects.filter(
        source_id='demo',
        source_event_id=event_id
    ).exists():
        return None
    
    event = PredictionEvent.objects.create(
        tip_type=tip_type,
        name='What will be the most popular color this season?',
        description='Predict which color will dominate fashion trends',
        target_kind=PredictionEvent.TargetKind.GENERIC,
        selection_mode=PredictionEvent.SelectionMode.CURATED,
        source_id='demo',
        source_event_id=event_id,
        metadata={
            'event_type': 'colors',
            'demo': True,
        },
        opens_at=opens_at,
        deadline=deadline,
        reveal_at=opens_at,
        is_active=True,
        points=2,
    )
    
    # Add color options
    colors_cat = OptionCategory.objects.get(slug='demo-colors')
    colors = ['red', 'blue', 'green', 'yellow', 'purple']
    
    for idx, color_slug in enumerate(colors, 1):
        color_option = Option.objects.get(category=colors_cat, slug=color_slug)
        PredictionOption.objects.create(
            event=event,
            option=color_option,
            label=color_option.name,
            sort_order=idx,
        )
    
    return event


def _create_bonus_event(tip_type, opens_at, deadline):
    """Create a bonus event with extra points."""
    event_id = f'demo-bonus-{opens_at.timestamp()}'
    
    if PredictionEvent.objects.filter(
        source_id='demo',
        source_event_id=event_id
    ).exists():
        return None
    
    event = PredictionEvent.objects.create(
        tip_type=tip_type,
        name='🎯 BONUS: Special Event Prediction',
        description='This is a bonus event worth extra points! Demonstrates custom styling and bonus mechanics.',
        target_kind=PredictionEvent.TargetKind.GENERIC,
        selection_mode=PredictionEvent.SelectionMode.CURATED,
        source_id='demo',
        source_event_id=event_id,
        metadata={
            'event_type': 'bonus',
            'demo': True,
            'special': True,
        },
        opens_at=opens_at,
        deadline=deadline,
        reveal_at=opens_at,
        is_active=True,
        is_bonus_event=True,
        points=5,
    )
    
    # Add yes/no options
    yesno_cat = OptionCategory.objects.get(slug='demo-yesno')
    yes_option = Option.objects.get(category=yesno_cat, slug='yes')
    no_option = Option.objects.get(category=yesno_cat, slug='no')
    
    PredictionOption.objects.create(
        event=event,
        option=yes_option,
        label='This will happen!',
        sort_order=1,
    )
    
    PredictionOption.objects.create(
        event=event,
        option=no_option,
        label='This will NOT happen!',
        sort_order=2,
    )
    
    return event


def _create_player_event(tip_type, opens_at, deadline):
    """Create a player-type event."""
    event_id = f'demo-player-{opens_at.timestamp()}'
    
    if PredictionEvent.objects.filter(
        source_id='demo',
        source_event_id=event_id
    ).exists():
        return None
    
    event = PredictionEvent.objects.create(
        tip_type=tip_type,
        name='Who will win the Demo Championship?',
        description='Choose the champion from our demo characters',
        target_kind=PredictionEvent.TargetKind.PLAYER,
        selection_mode=PredictionEvent.SelectionMode.CURATED,
        source_id='demo',
        source_event_id=event_id,
        metadata={
            'event_type': 'player',
            'demo': True,
        },
        opens_at=opens_at,
        deadline=deadline,
        reveal_at=opens_at,
        is_active=True,
        points=3,
    )
    
    # Add character options
    chars_cat = OptionCategory.objects.get(slug='demo-characters')
    characters = ['alice', 'bob', 'charlie', 'diana']
    
    for idx, char_slug in enumerate(characters, 1):
        char_option = Option.objects.get(category=chars_cat, slug=char_slug)
        PredictionOption.objects.create(
            event=event,
            option=char_option,
            label=char_option.name,
            sort_order=idx,
        )
    
    return event


# Register custom admin URLs
class CustomDemoAdmin:
    """Container for custom demo admin URLs."""
    
    @staticmethod
    def get_urls():
        """Get custom demo admin URLs."""
        return [
            path(
                'events/add-demo/',
                admin.site.admin_view(create_demo_events_view),
                name='demo_add_demo_events',
            ),
        ]


# Define pseudo-model for Demo admin registration
class DemoPseudoModel(models.Model):
    """Pseudo-model for Demo admin registration."""
    
    class Meta:
        app_label = 'demo'
        verbose_name = 'Demo Event'
        verbose_name_plural = 'Demo Events'
        # This is not a real database model
        managed = False
        # Use a fake table name that won't conflict
        db_table = '_demo_pseudo'


class DemoAdmin(admin.ModelAdmin):
    """
    Admin interface for managing demo events.
    
    This is a pseudo-model admin that provides a UI for creating
    demo events without a backing database model.
    """
    
    change_list_template = 'admin/demo/demo_index.html'
    
    def has_add_permission(self, request):
        return request.user.has_perm('predictions.add_predictionevent')
    
    def has_delete_permission(self, request, obj=None):
        return False
    
    def has_change_permission(self, request, obj=None):
        return request.user.has_perm('predictions.add_predictionevent')
    
    def get_queryset(self, request):
        """
        Return an empty queryset that doesn't hit the database.
        
        This admin uses a pseudo-model with no backing table, so we return
        an empty queryset to prevent any database queries.
        """
        return self.model.objects.none()
    
    def changelist_view(self, request, extra_context=None):
        """
        Override changelist_view to render directly without querying the database.
        
        This admin uses a pseudo-model with no backing table, so we bypass
        the default changelist behavior and render our custom template directly.
        """
        if not self.has_view_or_change_permission(request):
            raise PermissionDenied
        
        # Count existing demo events
        demo_event_count = PredictionEvent.objects.filter(source_id='demo').count()
        
        context = {
            **self.admin_site.each_context(request),
            'module_name': str(self.model._meta.verbose_name_plural),
            'title': _('Demo Events'),
            'demo_event_count': demo_event_count,
            'opts': self.model._meta,
            'app_label': self.model._meta.app_label,
            'has_view_permission': self.has_view_permission(request),
            'has_add_permission': self.has_add_permission(request),
            'has_change_permission': self.has_change_permission(request),
            'has_delete_permission': self.has_delete_permission(request),
            'has_editable_inline_admin_formsets': False,
        }
        
        if extra_context:
            context.update(extra_context)
        
        return TemplateResponse(
            request,
            self.change_list_template,
            context
        )
    
    def has_view_or_change_permission(self, request, obj=None):
        """Check if user has view or change permission."""
        return self.has_view_permission(request, obj) or self.has_change_permission(request, obj)


# Register the DemoAdmin with the pseudo-model
admin.site.register(DemoPseudoModel, DemoAdmin)


# Hook into admin site URLs
from django.contrib.admin import sites

# Save the current get_urls method (which may already be patched by NBA)
_current_get_urls = sites.AdminSite.get_urls

def _get_urls_with_demo(self):
    """Get admin URLs including demo custom views."""
    # Call whatever get_urls is currently set (NBA-patched or original)
    urls = _current_get_urls(self)
    demo_urls = CustomDemoAdmin.get_urls()
    return demo_urls + urls

# Only patch if not already patched by demo
if not hasattr(sites.AdminSite.get_urls, '_demo_patched'):
    _get_urls_with_demo._demo_patched = True
    sites.AdminSite.get_urls = _get_urls_with_demo
