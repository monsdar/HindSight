"""
Event sources package.

This package contains the EventSource system for automatically importing
prediction events from external sources.
"""

from .base import EventSource, EventSourceResult
from .registry import registry, get_source, list_sources, list_configured_sources

__all__ = [
    'EventSource',
    'EventSourceResult',
    'registry',
    'get_source',
    'list_sources',
    'list_configured_sources',
]
