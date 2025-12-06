# Forfeited Match Handling

## Overview

This document describes how the HoopTipp application handles forfeited matches (games that end with a score like 20-0 due to a forfeit rather than actual gameplay).

## Background

In German amateur basketball leagues, forfeited matches are recorded with a standard score of 20-0 and are marked with a special flag in the SLAPI API. These matches should not count toward prediction accuracy or scoring, as they don't represent actual game outcomes.

## Implementation

### API Changes

The SLAPI API now includes an `is_forfeit` boolean flag in match data:

```json
{
  "match_id": 123,
  "home_team": "Team A",
  "away_team": "Team B",
  "score_home": 20,
  "score_away": 0,
  "is_forfeit": true  // New flag indicating forfeit
}
```

### Application Behavior

When a match is forfeited (`is_forfeit: true`):

1. **No Outcome Created**: The system does not create an `EventOutcome` for forfeited matches
2. **Locks Returned**: Any locks placed on the forfeited match are returned to users immediately
3. **No Scoring**: No points are awarded to any predictions on the forfeited match
4. **Neutral Treatment**: Neither correct nor incorrect predictions are counted

### Code Changes

#### Event Source (`hooptipp/dbb/event_source.py`)

- Modified `_create_or_fix_outcome_for_past_match` to check for `is_forfeit` flag
- Added `_handle_forfeited_match` method to return locks without creating outcomes
- Logs forfeited matches for monitoring

#### Lock Service (`hooptipp/predictions/lock_service.py`)

- Added `return_lock_for_forfeited_event` method
- Returns locks immediately without penalty or delay
- Sets lock status to `NONE` since the match is neither correct nor incorrect

#### Scoring Service (`hooptipp/predictions/scoring_service.py`)

- Added `_is_forfeited_match` helper function to detect forfeited outcomes
- Added `_return_locks_for_forfeited_match` function to handle lock returns
- Modified `score_event_outcome` to skip scoring for forfeited matches
- Modified `process_all_user_scores` to handle forfeited matches in batch processing

#### Management Commands

**`update_dbb_matches.py`**:
- Automatically detects and handles forfeited matches when syncing
- Returns locks during sync process

**`process_scores.py`**:
- Skips scoring for forfeited matches
- Returns locks and marks outcomes as processed
- Reports forfeited matches in processing summary

### Testing

Comprehensive test coverage includes:

1. **Event Source Tests**:
   - `test_sync_events_handles_forfeited_matches`: Verifies no outcomes are created
   - `test_sync_events_returns_locks_for_forfeited_matches`: Verifies locks are returned

2. **Scoring Service Tests**:
   - `test_score_event_outcome_handles_forfeited_match`: Tests individual outcome scoring
   - `test_process_all_scores_handles_forfeited_matches`: Tests batch processing
   - `test_forfeited_match_does_not_award_points_to_correct_prediction`: Verifies no points awarded
   - `test_forfeited_match_does_not_count_as_incorrect`: Verifies locks not forfeited

## User Experience

From a user's perspective:

- **Before Match**: Users can make predictions and place locks normally
- **After Forfeit**: 
  - No points are awarded to anyone
  - Locks are returned immediately (no penalty)
  - The match appears as completed but not scored
  - No change to win/loss records

## Monitoring

The application logs forfeited matches at INFO level:

```
INFO - Match 123 was forfeited, returning locks but not creating outcome
INFO - Returned lock to user123 for forfeited match Team A vs Team B
```

## Database Implications

- Forfeited matches have `PredictionEvent` records but no `EventOutcome`
- If an outcome exists with `is_forfeit: true` in metadata, it will not be scored
- Locks are returned immediately (status set to `NONE`)

## Future Considerations

- Add UI indication for forfeited matches
- Include forfeited match stats in user dashboards
- Consider separate tracking for forfeit predictions

