# Prediction Lock Feature Plan

## Objective
Introduce a lock mechanism that lets each user mark up to three active predictions as "locked." A locked prediction indicates high confidence and provides modified scoring: a correct locked prediction yields double points, returns the lock immediately, and remains eligible for normal scoring flows; an incorrect locked prediction forfeits the lock for one month before the lock replenishes automatically.

## Current State Assessment
- **Data model**: `UserTip` persists per-event predictions but has no notion of locks or confidence levels. User-specific metadata lives in `UserPreferences`.
- **Prediction submission**: The `home` view handles pick creation via POST, with templates rendering curated lists or free-form selections. There is no UI for lock selection.
- **Scoring**: Points tracking logic is not yet implemented in the visible codebase, so a future scoring service or management command must account for the lock behavior when introduced.

## Implementation Steps

### 1. Data Modeling & Migrations
1. Extend `UserTip` with lock-specific fields:
   - `is_locked: models.BooleanField(default=False)` to flag locked picks.
   - `lock_committed_at: models.DateTimeField(null=True, blank=True)` to track when a lock was last allocated, useful for auditing and preventing race conditions.
   - Optional: `lock_resolved_state: models.CharField` (choices: `pending`, `returned`, `forfeited`) to support scoring workflows.
   - Optional: `lock_releases_at: models.DateTimeField(null=True, blank=True)` set when a lock is forfeited, enabling automatic replenishment after one month.
2. Create a `UserLockLedger` (or similar) model that keeps a running total of available locks per user. Suggested fields: `user`, `locks_available` (default 3), `locks_spent`, `locks_returned`, `locks_pending_return`, timestamps.
3. Generate and check in migrations for all schema changes, including data migrations to initialise `locks_available=3` for existing users, set default lock metadata for historical `UserTip` rows, and populate `lock_releases_at` for forfeited historical tips if applicable.

### 2. Domain Services & Business Logic
1. Introduce a service layer (e.g., `hooptipp.predictions.lock_service`) encapsulating lock allocation, release, and validation to keep view logic slim and reusable for future APIs.
2. When saving tips:
   - Validate that the submitted lock selections do not exceed the user's available locks (considering existing locked tips that are still pending resolution or scheduled for automatic return).
   - Update `UserTip` records atomically using transactions to avoid partially-applied lock state when multiple picks are saved at once.
   - Adjust the lock ledger counters accordingly (decrement on allocation, increment when a previously locked pick is unlocked before the prediction deadline, track pending returns for forfeited locks, and increment again when the scheduled one-month release triggers).
3. Provide helper utilities to compute `locks_remaining` for templates and forms, including a countdown for the next scheduled lock return when users are out of locks.
4. Introduce a periodic task (Celery beat or Django `crontab` style management command) that scans for forfeited locks whose `lock_releases_at` has passed, replenishing ledger counts and clearing pending state.

### 3. UI & Interaction Updates
1. Modify the predictions submission form to include a lock toggle per event:
   - For curated events, add a checkbox or button next to each option to mark it as locked once selected.
   - For "any selection" events, expose a lock toggle adjacent to the radio/select control.
2. Display the user's remaining locks prominently (e.g., badge near "Save picks"). Disable additional lock toggles when none remain and surface messaging about when the next lock returns if all three are committed.
3. Indicate locked picks in summaries (`event_tip_users` list and active user saved picks) with iconography and allow users to clear the lock up until the prediction deadline.
4. Ensure accessibility: keyboard operable toggles, ARIA labels, and clear messaging when locks are unavailable or scheduled to return.

### 4. Scoring Workflow Integration
1. Define or extend the scoring process (management command or scheduled task) to interpret `UserTip.is_locked`:
   - On resolution, evaluate the prediction outcome.
   - Provide a flag or metadata to the scoring engine indicating whether the prediction was locked so downstream configurable point calculations can use it.
   - When a locked prediction is correct, mark `lock_resolved_state='returned'`, restore the lock immediately, and apply the temporary double-points rule.
   - If the prediction fails, set `lock_resolved_state='forfeited'`, schedule the lock return by setting `lock_releases_at = resolved_at + 30 days`, and keep the ledger count reduced until the scheduled task restores it.
2. Keep scoring idempotent by recording the resolution timestamp on `UserTip` so repeated runs do not double-apply adjustments and by guarding against repeated scheduling of lock returns.
3. Update leaderboard or stats aggregation logic (when available) to incorporate the adjusted points and lock counts, using the lock flag to inform the future configurable scoring component.

### 5. Administrative & API Considerations
1. Update Django admin for `UserTip` and new lock ledger model to show lock status, resolution state, and allow manual corrections.
2. If APIs or serializers exist, extend them to expose lock metadata with proper validation.

### 6. Testing Strategy
1. Unit tests for lock allocation logic covering:
   - Enforcing the three-lock limit across multiple events.
   - Unlocking before the prediction deadline restores the available lock.
   - Post-resolution state transitions (`returned` vs. `forfeited`) and scheduling of one-month lock returns.
2. View tests ensuring the `home` view respects remaining locks, rejects over-allocation, allows unlocks only before deadlines, and persists lock state.
3. Template regression tests (e.g., using Django's `assertContains`) to verify lock indicators render for locked picks and that countdown messaging appears when appropriate.
4. Migration tests verifying default lock counts for existing users and correct initialization of scheduled return timestamps.

### 7. Rollout & Monitoring
1. Provide a management command to audit lock state consistency (e.g., verifying ledger balances match locked tips).
2. Document the feature in `README.md` or user-facing guides, including an explanation of lock usage and scoring.
3. After deployment, monitor logs for lock allocation errors and add Sentry breadcrumbs (if integrated) around lock service operations.

## Dependencies & Open Questions
- Confirm upcoming scoring implementation details to ensure the lock design aligns with planned point calculations.
- Ensure operational support for the one-month lock replenishment job (scheduling, monitoring, retries).
