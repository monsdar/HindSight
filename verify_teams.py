#!/usr/bin/env python
"""
Verify that team metadata has been properly updated with NBA team IDs.
"""

import os
import sys
import django

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hooptipp.settings')
django.setup()

from hooptipp.predictions.models import Option, OptionCategory
from hooptipp.nba.managers import NbaTeamManager

def main():
    """Verify team metadata."""
    print("Verifying Team Metadata")
    print("=" * 40)
    
    teams_cat = NbaTeamManager.get_category()
    teams = Option.objects.filter(category=teams_cat)[:5]
    
    for team in teams:
        nba_id = team.metadata.get("nba_team_id")
        bdl_id = team.metadata.get("balldontlie_team_id")
        print(f"Team: {team.short_name}")
        print(f"  External ID: {team.external_id}")
        print(f"  NBA Team ID: {nba_id}")
        print(f"  BallDontLie ID: {bdl_id}")
        print()

if __name__ == "__main__":
    main()
