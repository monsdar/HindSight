# Generic Prediction System Design

## Overview
This document outlines the design for generalizing the HoopTipp prediction system to support any type of predictable event, not just NBA-related predictions.

## Current State Analysis

### Current Architecture
The existing system has:
1. **TipType**: Already generic, represents categories of predictions
2. **PredictionEvent**: Mostly generic, but tied to ScheduledGame
3. **PredictionOption**: Has hard-coded references to NbaTeam and NbaPlayer
4. **NbaTeam/NbaPlayer**: NBA-specific models
5. **Services**: NBA-specific (BallDontLie API integration)
6. **UserTip**: Mixed generic and NBA-specific fields

### Key Requirements
1. Support any form of predictable event (not just NBA)
2. Binary predictions with selectable options (teams, players, countries, etc.)
3. Manual and automatic event creation
4. Extensible event sources via plugins/extensions
5. Active timeframe with due dates
6. Show upcoming unpredicted events on main page

## Proposed Architecture

### 1. Generic Option System

Replace hard-coded NBA team/player references with a generic option system:

```python
class OptionCategory(models.Model):
    """Represents a category of prediction options (e.g., 'nba-teams', 'countries', 'political-parties')"""
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, blank=True)  # Icon identifier
    is_active = models.BooleanField(default=True)

class Option(models.Model):
    """Generic option that can represent any selectable choice"""
    category = models.ForeignKey(OptionCategory, on_delete=models.CASCADE, related_name='options')
    slug = models.SlugField()
    name = models.CharField(max_length=200)
    short_name = models.CharField(max_length=50, blank=True)  # e.g., tricode for NBA teams
    description = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)  # Flexible storage for category-specific data
    external_id = models.CharField(max_length=100, blank=True)  # For external API references
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        unique_together = ('category', 'slug')
        ordering = ['category', 'sort_order', 'name']
```

### 2. Event Source System

Create an abstract base class for event sources that can automatically import events:

```python
# hooptipp/predictions/event_sources/base.py
from abc import ABC, abstractmethod
from typing import List, Dict, Any
from datetime import datetime

class EventSourceResult:
    """Result of an event source sync operation"""
    def __init__(self):
        self.events_created = 0
        self.events_updated = 0
        self.events_removed = 0
        self.options_created = 0
        self.options_updated = 0
        
    @property
    def changed(self) -> bool:
        return any([
            self.events_created,
            self.events_updated,
            self.events_removed,
            self.options_created,
            self.options_updated,
        ])

class EventSource(ABC):
    """
    Abstract base class for event sources.
    
    Event sources are responsible for:
    1. Importing options (e.g., teams, players, countries)
    2. Importing/generating prediction events
    3. Resolving outcomes (optional)
    """
    
    @property
    @abstractmethod
    def source_id(self) -> str:
        """Unique identifier for this event source"""
        pass
    
    @property
    @abstractmethod
    def source_name(self) -> str:
        """Human-readable name for this event source"""
        pass
    
    @property
    @abstractmethod
    def category_slugs(self) -> List[str]:
        """List of OptionCategory slugs this source provides"""
        pass
    
    @abstractmethod
    def sync_options(self) -> EventSourceResult:
        """Import/update options from this source"""
        pass
    
    @abstractmethod
    def sync_events(self) -> EventSourceResult:
        """Import/update prediction events from this source"""
        pass
    
    def resolve_outcomes(self) -> EventSourceResult:
        """
        Optionally resolve outcomes for events.
        Override if the source can automatically determine outcomes.
        """
        return EventSourceResult()
    
    def is_configured(self) -> bool:
        """
        Check if this event source is properly configured.
        Override to check for required API keys, credentials, etc.
        """
        return True
```

### 3. Refactored Models

#### PredictionEvent Updates
- Remove direct link to ScheduledGame
- Add generic `source_id` to track which EventSource created it
- Add `metadata` JSONField for source-specific data

```python
class PredictionEvent(models.Model):
    # ... existing fields ...
    source_id = models.CharField(max_length=100, blank=True)  # Which EventSource created this
    source_event_id = models.CharField(max_length=200, blank=True)  # External event ID
    metadata = models.JSONField(default=dict, blank=True)  # Source-specific data
    scheduled_game = models.OneToOneField(...)  # Keep for backward compatibility, make nullable
```

#### PredictionOption Updates
- Replace team/player ForeignKeys with generic Option FK
- Keep old fields for backward compatibility during migration

```python
class PredictionOption(models.Model):
    event = models.ForeignKey(PredictionEvent, ...)
    label = models.CharField(max_length=200)
    option = models.ForeignKey(Option, on_delete=CASCADE, null=True, blank=True)  # New generic reference
    
    # Deprecated fields - keep for migration compatibility
    team = models.ForeignKey(NbaTeam, ..., null=True, blank=True)
    player = models.ForeignKey(NbaPlayer, ..., null=True, blank=True)
```

#### UserTip Updates
- Replace team/player ForeignKeys with generic option
- Keep old fields temporarily for migration

```python
class UserTip(models.Model):
    # ... existing fields ...
    selected_option = models.ForeignKey(Option, ..., null=True, blank=True)  # New generic reference
    
    # Deprecated fields
    selected_team = models.ForeignKey(NbaTeam, ..., null=True, blank=True)
    selected_player = models.ForeignKey(NbaPlayer, ..., null=True, blank=True)
```

### 4. Event Source Registry

Create a registry to manage available event sources:

```python
# hooptipp/predictions/event_sources/registry.py
from typing import Dict, Type, List
from .base import EventSource

class EventSourceRegistry:
    """Registry for all available event sources"""
    
    def __init__(self):
        self._sources: Dict[str, Type[EventSource]] = {}
    
    def register(self, source_class: Type[EventSource]):
        """Register an event source"""
        instance = source_class()
        self._sources[instance.source_id] = source_class
    
    def get(self, source_id: str) -> EventSource:
        """Get an event source by ID"""
        source_class = self._sources.get(source_id)
        if not source_class:
            raise ValueError(f"Unknown event source: {source_id}")
        return source_class()
    
    def list_sources(self) -> List[EventSource]:
        """List all registered event sources"""
        return [cls() for cls in self._sources.values()]
    
    def list_configured_sources(self) -> List[EventSource]:
        """List only properly configured event sources"""
        return [source for source in self.list_sources() if source.is_configured()]

# Global registry instance
registry = EventSourceRegistry()
```

### 5. NBA Event Source Implementation

Convert existing NBA functionality into an EventSource:

```python
# hooptipp/predictions/event_sources/nba.py
from .base import EventSource, EventSourceResult
from ..models import OptionCategory, Option, PredictionEvent, PredictionOption, TipType
from ..balldontlie_client import build_cached_bdl_client

class NbaEventSource(EventSource):
    @property
    def source_id(self) -> str:
        return "nba-balldontlie"
    
    @property
    def source_name(self) -> str:
        return "NBA (BallDontLie API)"
    
    @property
    def category_slugs(self) -> List[str]:
        return ["nba-teams", "nba-players"]
    
    def is_configured(self) -> bool:
        return bool(self._get_api_key())
    
    def sync_options(self) -> EventSourceResult:
        """Sync NBA teams and players"""
        result = EventSourceResult()
        
        # Create categories
        teams_cat, _ = OptionCategory.objects.get_or_create(
            slug="nba-teams",
            defaults={"name": "NBA Teams", "icon": "basketball"}
        )
        players_cat, _ = OptionCategory.objects.get_or_create(
            slug="nba-players",
            defaults={"name": "NBA Players", "icon": "person"}
        )
        
        # Sync teams
        client = build_cached_bdl_client(api_key=self._get_api_key())
        # ... implement team sync ...
        
        # Sync players
        # ... implement player sync ...
        
        return result
    
    def sync_events(self) -> EventSourceResult:
        """Sync upcoming NBA games"""
        # ... implement game sync ...
        pass
```

### 6. Migration Strategy

#### Phase 1: Add New Models (Backward Compatible)
1. Create Option and OptionCategory models
2. Add new fields to existing models (option, metadata, source_id)
3. Keep all existing NBA-specific fields

#### Phase 2: Data Migration
1. Create OptionCategory for "nba-teams" and "nba-players"
2. Migrate NbaTeam → Option (nba-teams category)
3. Migrate NbaPlayer → Option (nba-players category)
4. Update PredictionOption to reference new Option model
5. Update UserTip to reference new Option model

#### Phase 3: Deprecation
1. Mark old fields as deprecated in code
2. Update admin to hide deprecated fields
3. Update views to use new fields

#### Phase 4: Cleanup (Future)
1. Remove deprecated fields
2. Optionally remove NbaTeam/NbaPlayer models (or keep for legacy data)

### 7. Admin Interface Updates

Create admin interfaces for:
- OptionCategory management
- Option management (with filtering by category)
- Event source configuration and sync triggers
- Generic prediction event creation

### 8. View and Template Updates

Update views to:
- Fetch options by category instead of hard-coded team/player queries
- Display options generically based on their category
- Handle generic metadata in templates

### 9. Future Event Source Examples

Easy to add new sources:

```python
# Future: Olympic medals prediction
class OlympicEventSource(EventSource):
    source_id = "olympics-2028"
    source_name = "2028 Olympics"
    category_slugs = ["countries"]
    
    def sync_options(self):
        # Import countries
        pass
    
    def sync_events(self):
        # Create "Which country wins 30+ medals first?" event
        pass

# Future: Papal election
class PapalElectionSource(EventSource):
    source_id = "papal-election"
    source_name = "Papal Election"
    category_slugs = ["countries"]
    
    def sync_events(self):
        # Create "Which country names the next Pope?" event
        pass
```

## Implementation Order

1. ✅ Create design document
2. Create new models (Option, OptionCategory)
3. Add new fields to existing models
4. Create EventSource base class and registry
5. Implement NBA EventSource
6. Create data migration
7. Update admin interface
8. Update views and templates
9. Update tests
10. Update documentation

## Benefits

1. **Flexibility**: Can add any type of prediction without code changes
2. **Extensibility**: New event sources are just Python classes
3. **Backward Compatible**: Existing NBA data and functionality preserved
4. **Clean Architecture**: Separation of concerns between prediction system and data sources
5. **Future-Proof**: Easy to add Olympics, elections, personal tracking, etc.

## Configuration

Event sources can be configured via environment variables:

```bash
# NBA
BALLDONTLIE_API_TOKEN=your_token

# Future: Olympics
OLYMPICS_API_KEY=your_key

# Future: Custom sources
CUSTOM_EVENT_SOURCE_ENABLED=true
```

## Example Use Cases

### Example 1: Next Pope
```python
# Manual event creation via admin
event = PredictionEvent.objects.create(
    tip_type=get_or_create_tip_type("special-events"),
    name="Which country names the next Pope?",
    description="Predict the nationality of the next Pope",
    opens_at=now,
    deadline=datetime(2025, 12, 31),
    points=5,
)

# Add options
countries_cat = OptionCategory.objects.get(slug="countries")
for country in ["Italy", "USA", "Brazil", "Poland", "France"]:
    option = Option.objects.get_or_create(
        category=countries_cat,
        name=country,
    )
    PredictionOption.objects.create(event=event, option=option, label=country)
```

### Example 2: Bike Commute Tracking
```python
class BikeCommuteSource(EventSource):
    source_id = "bike-commute"
    
    def sync_events(self):
        # Create monthly event
        event = PredictionEvent.objects.create(
            name="Will [Person] bike to work 10+ times this month?",
            tip_type=tip_type,
            opens_at=month_start,
            deadline=month_end,
        )
        
        # Binary yes/no options
        for choice in ["Yes (10+ times)", "No (< 10 times)"]:
            option = Option.objects.create(
                category=yes_no_category,
                name=choice,
            )
            PredictionOption.objects.create(event=event, option=option, label=choice)
```

## Summary

This design transforms HoopTipp from an NBA-specific prediction app into a general-purpose prediction platform while:
- Preserving all existing NBA functionality
- Maintaining data integrity
- Requiring minimal changes to existing code
- Enabling easy addition of new prediction types
- Following Django best practices
