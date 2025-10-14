# Scoring System Feature Plan

## Objective
Introduce a robust scoring framework that awards points to players for correctly predicted events. The system must support variable point values so routine game picks grant 1 point while premium predictions (e.g., MVP, Finals winner) can yield higher scores. Scoring should integrate cleanly with existing prediction data, stay idempotent, and provide aggregated leaderboards.

## Current State Assessment
- **Prediction capture**: `UserTip` records each user's submitted pick for either a scheduled game or a generic `PredictionEvent`. Lock mechanics already track `is_locked` and related metadata but no points are awarded yet.
- **Event metadata**: `TipType`, `PredictionEvent`, and `PredictionOption` describe pickable items but lack a notion of point values or actual outcomes.
- **Results tracking**: There is no storage for final outcomes of games or custom events, nor any utilities that reconcile submitted picks with results.
- **Leaderboards / stats**: No tables, services, or templates currently surface per-user point totals.

## Implementation Steps

### 1. Data Modeling & Migrations
1. Extend `PredictionEvent` with scoring attributes:
   - `points: PositiveSmallIntegerField` (default 1) to represent the reward for correctly predicting the event. This value must be editable by admins through Django admin forms so free-form predictions can have bespoke point totals without code deployments.
   - Optional: `is_bonus_event: BooleanField(default=False)` to simplify filtering for premium predictions in analytics.
2. For scheduled games tied to `ScheduledGame`, add a default scoring value at the `TipType` level (e.g., `default_points`). When syncing NBA games, use this default to pre-populate the associated event's `points` while still allowing admin overrides on a per-event basis.
3. Introduce an `EventOutcome` model that captures the resolved result:
   - `prediction_event` (one-to-one) referencing the event being scored.
   - Fields for the winning `PredictionOption`, or fallback `winning_team` / `winning_player` if the pick was free-form.
   - Status fields like `resolved_at`, `resolved_by`, and `notes` for auditing manual entries.
4. Create a `UserScore` (or `UserEventScore`) model that records points granted per user per event:
   - `user`, `prediction_event`, `points_awarded`, `awarded_at`, and flags for `is_locked_bonus` or similar multipliers.
   - Unique constraint on `(user, prediction_event)` to enforce idempotency.
5. Generate migrations for all additions, ensuring defaults migrate cleanly for existing data (normal games inherit `points=1`).

### 2. Domain Services & Business Logic
1. Build a `scoring_service` module responsible for:
   - Resolving events once outcomes are known.
   - Comparing the recorded outcome with each `UserTip` to determine correctness. Scoring remains binary (correct/incorrect) so there is no partial credit logic to model.
   - Writing `UserScore` rows and updating aggregate totals in a transactional, idempotent fashion.
2. Decide how lock bonuses interact with scoring:
   - If `UserTip.is_locked` or `lock_status` indicates an active or returned lock for a correct pick, multiply the base event points accordingly.
   - Store the multiplier or resulting bonus points in `UserScore` for transparency.
3. Provide helpers to compute aggregate totals quickly:
   - Either maintain a denormalized `total_points` on a `UserStats` model updated alongside each score, or compute via queries/Materialized views. Aggregate score presentation can ship in a follow-up feature so the initial scope only ensures the per-event `UserScore` rows exist.
   - Expose APIs/services to fetch leaderboard standings filtered by season, tip type, or event category.
4. Ensure scoring jobs are re-runnable without duplication by:
   - Checking for an existing `UserScore` row before awarding points.
   - Marking `EventOutcome` with `scored_at` timestamps to signal completion.

### 3. Results Ingestion Workflow
1. For NBA games, extend the sync job (if present) or create a new management command to pull final scores via BallDontLie, mapping them back to `ScheduledGame` and linked `PredictionEvent`.
2. For manual or special events (MVP, champion), build an admin workflow:
   - Django admin form for `EventOutcome` enabling staff to select the correct `PredictionOption` or enter free-form results.
   - Validation preventing scoring before the event deadline passes.
3. Support re-scoring when corrections occur by allowing `EventOutcome` edits that trigger a recalculation (revoking previous `UserScore` rows before writing new ones).

### 4. UI & Reporting Updates
1. Update user-facing dashboards to display:
   - Current total points, recent events scored, and breakdown of bonus vs. base points.
   - Event cards showing their point value so users understand potential rewards before making picks.
2. Provide a leaderboard page sortable by overall points, tip type, or season segment.
3. Expose point values in email or notification templates (if any) to highlight high-value opportunities.

### 5. Testing Strategy
1. Unit tests covering:
   - Event scoring logic for normal and bonus point values.
   - Lock bonus calculations to verify multipliers apply correctly.
   - Idempotent scoring (re-running the service does not double-award points).
2. Integration tests using the scoring service against sample outcomes and verifying `UserScore` rows, total aggregates, and lock state transitions.
3. Admin/view tests ensuring point values render and that manual scoring workflows enforce deadlines and validation rules.
4. Migration tests guaranteeing default point values for existing events and the integrity of new unique constraints.

### 6. Rollout & Monitoring
1. Provide a backfill management command to score historical events once outcomes are available.
2. Add metrics/logging around scoring operations (counts of events scored, durations, errors) to support observability.
3. Document scoring rules (point values, lock bonuses, leaderboards) in README or a dedicated user guide.
4. Coordinate deployment so the data migrations run before any scoring jobs, and feature-flag user-visible leaderboard pages until initial scoring completes.

## Dependencies & Open Questions
- Confirm the desired point scale for each event type (MVP, champion, series predictions). Admins will manage point values through the Django admin UI, so we only need stakeholder guidance on recommended defaults.
- Points accumulate indefinitely; capture requirements for a possible "reset after season" utility that could archive scores but is out of scope for the initial rollout.
- Scoring is strictly binary—no partial credit—so validation and UI copy should reinforce that expectation.
- Decide on long-term storage of detailed scoring history versus aggregated snapshots for performance once score aggregation/leaderboards are prioritized in a later feature.
