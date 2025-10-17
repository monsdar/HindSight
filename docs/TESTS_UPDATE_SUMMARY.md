# Test Updates Summary

## Overview

All tests have been successfully updated to work with the new generic option system. **All 63 tests now pass.**

## Changes Made

### 1. test_scoring_service.py ✅
**Updated:** All 4 test methods

**Changes:**
- Added imports for `Option` and `OptionCategory`
- Created `teams_cat` in `setUp()`
- Created generic `Option` objects for Lakers and Celtics
- Updated `PredictionOption` creation to use `option` field instead of `team`
- Updated `UserTip` creation to use `selected_option` instead of `selected_team`
- Updated `EventOutcome` creation to include `winning_generic_option`

**Example:**
```python
# Before:
self.lakers_option = PredictionOption.objects.create(
    event=self.event,
    label="Los Angeles Lakers",
    team=self.lakers,  # ❌
)

# After:
self.lakers_option_obj = Option.objects.create(
    category=self.teams_cat,
    slug='lal',
    name='Los Angeles Lakers',
    metadata={'nba_team_id': self.lakers.id}
)
self.lakers_option = PredictionOption.objects.create(
    event=self.event,
    label="Los Angeles Lakers",
    option=self.lakers_option_obj,  # ✅
)
```

### 2. test_admin.py ✅
**Updated:** 1 test class (`EventOutcomeAdminScoreTests`)

**Changes:**
- Added imports for `Option` and `OptionCategory`
- Created option category and option in `setUp()`
- Updated `PredictionOption` to use generic option
- Updated `EventOutcome` to include `winning_generic_option`
- Updated `UserTip` to use `selected_option`

### 3. test_services.py ✅
**Updated:** Service function (`_upsert_team`)

**Changes:**
- Modified `_upsert_team()` to automatically create/update corresponding `Option` objects
- Ensures NBA teams synced from API also get generic Options created
- This makes the `sync_weekly_games` tests pass without modification

### 4. test_views.py ✅
**Updated:** Multiple test methods

**Changes:**
- Changed `teams_cat` to `self.teams_cat` in `setUp()` for class-wide access
- Updated `test_weekday_slots_group_games_by_date` to create Options for additional teams
- Updated `test_weekday_slots_excludes_events_outside_range` to create generic option
- Updated `test_save_tips_respects_lock_limit` to use generic options

### 5. scoring_service.py ✅
**Updated:** Core scoring logic

**Changes:**
- Removed references to `winning_team_id` and `winning_player_id`
- Updated `_outcome_has_selection()` to check `winning_generic_option_id`
- Simplified `_tip_matches_outcome()` to use generic option matching
- Removed `_selected_team_id_for_tip()` and `_selected_player_id_for_tip()` helpers
- Updated `select_related()` to prefetch `selected_option` instead of `selected_team`/`selected_player`

### 6. views.py ✅
**Updated:** Prefetch optimization

**Changes:**
- Changed `prefetch_related('options__team', 'options__player')` to `prefetch_related('options__option__category')`

## Test Results

```bash
Ran 63 tests in 10.991s

OK
```

**Status:** ✅ All 63 tests passing
- 0 failures
- 0 errors
- 100% success rate

## Files Modified

1. `hooptipp/predictions/tests/test_scoring_service.py`
2. `hooptipp/predictions/tests/test_admin.py`
3. `hooptipp/predictions/tests/test_views.py`
4. `hooptipp/predictions/scoring_service.py`
5. `hooptipp/predictions/services.py` (updated `_upsert_team`)
6. `hooptipp/predictions/views.py`

## Pattern Used

The consistent pattern for updating tests:

1. **Import new models:**
   ```python
   from hooptipp.predictions.models import Option, OptionCategory
   ```

2. **Create option category:**
   ```python
   teams_cat = OptionCategory.objects.create(
       slug='nba-teams',
       name='NBA Teams'
   )
   ```

3. **Create generic options:**
   ```python
   option = Option.objects.create(
       category=teams_cat,
       slug='team-slug',
       name='Team Name',
       short_name='ABC',
       metadata={'nba_team_id': team.id}
   )
   ```

4. **Use options in PredictionOption:**
   ```python
   PredictionOption.objects.create(
       event=event,
       label='Team Name',
       option=option,  # Not team=
   )
   ```

5. **Use options in UserTip:**
   ```python
   UserTip.objects.create(
       user=user,
       prediction_event=event,
       selected_option=option,  # Not selected_team=
       prediction='Team Name',
   )
   ```

6. **Use options in EventOutcome:**
   ```python
   EventOutcome.objects.create(
       prediction_event=event,
       winning_option=prediction_option,
       winning_generic_option=option,  # Not winning_team=
   )
   ```

## Benefits

1. **Consistent:** All tests follow the same pattern
2. **Generic:** Tests work with any option type, not just NBA teams
3. **Future-proof:** Easy to add tests for new prediction categories
4. **Maintainable:** Clear relationship between options and predictions

## Next Steps

The codebase is now fully updated:
- ✅ Models streamlined (no legacy fields)
- ✅ Migrations clean and comprehensive
- ✅ Admin interfaces updated
- ✅ Views using generic options
- ✅ Services creating generic options
- ✅ Event sources using generic system
- ✅ All tests passing

The system is production-ready and fully generic!
