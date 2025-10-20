"""Main views for HindSight application."""

import os
import random
from django.conf import settings
from django.shortcuts import render, redirect
from django.contrib import messages
from logging import getLogger
from django.views.decorators.http import require_http_methods
from django.http import HttpResponse
from hooptipp.nba.managers import NbaTeamManager
from hooptipp.nba.services import get_team_logo_url

logger = getLogger(__name__)


def health(request):
    """Health check endpoint."""
    return HttpResponse("OK", content_type="text/plain")


@require_http_methods(["GET", "POST"])
def privacy_gate(request):
    """
    Privacy gate view that requires users to select correct NBA teams.
    
    This is a simple challenge to prevent random visitors from accessing
    the private prediction platform.
    """
    # Check if NBA teams are available
    all_teams = list(NbaTeamManager.all())
    
    # If no teams are available, redirect to admin to set up the system
    if not all_teams:
        logger.info("No NBA teams found, redirecting to admin for initial setup")
        messages.info(request, 'No NBA teams found. Please set up the system via admin panel.')
        return redirect('/admin/')
    
    if request.method == 'POST':
        # Get the correct answer from settings
        correct_teams = getattr(settings, 'PRIVACY_GATE_CORRECT_ANSWER', ['ORL', 'GSW', 'BOS', 'OKC'])
        
        selected_teams = request.POST.getlist('selected_teams')
        
        logger.info(f"Privacy gate check: correct_teams={correct_teams}, selected_teams={selected_teams}")
        
        if set(selected_teams) == set(correct_teams):
            request.session['privacy_gate_passed'] = True
            messages.success(request, 'Welcome! You can now access the prediction platform.')
            return redirect('predictions:home')
        else:
            logger.error(f"Incorrect privacy gate answer selection for user {request.user}, selected: {selected_teams}, expected: {correct_teams}")
            messages.error(request, 'Incorrect selection. Please try again.')
    
    # Shuffle teams to randomize the display
    random.shuffle(all_teams)
    
    # Prepare team data with logo URLs
    challenge_teams = []
    for team in all_teams:
        challenge_teams.append({
            'id': team.id,
            'name': team.name,
            'short_name': team.short_name,
            'logo_url': get_team_logo_url(team.short_name),
        })
    
    context = {
        'challenge_teams': challenge_teams,
        'challenge_question': 'Select the correct NBA teams to continue:'
    }
    return render(request, 'privacy_gate.html', context)