# Fix Non-Deterministic Scheduling — Deterministic + Optimal

## Key Insight: Optimal vs Feasible in Deterministic Mode

OR-Tools CP-SAT provides a **mathematical guarantee**:

| Solver Status | Meaning | Guarantee |
|--------------|---------|-----------|
| **OPTIMAL** | Provably the global best solution | ✅ No better schedule exists — proven by the solver |
| **FEASIBLE** | A valid solution, but not proven best | ⚠️ Might be suboptimal — solver ran out of time before proving optimality |
| INFEASIBLE | No solution exists | ❌ |

> [!IMPORTANT]
> **Deterministic mode (single-threaded) takes longer to prove optimality.** A problem that reaches `OPTIMAL` in 60s with 8 threads may need 300–600s with 1 thread. The solution *will* be the same optimal one — it just takes longer to get there. **The fix must therefore also increase the time limit.**

Currently, `solve_validated()` in `optimization.py` already has all the right logic — it requires `OPTIMAL` status, verifies zero optimality gap, and does dual-run checks — but it is **never called from any view**. All 8 call sites use plain `solve()` which accepts `FEASIBLE` as success.

## Root Causes (3 issues)

| # | Cause | Effect |
|---|-------|--------|
| 1 | `solve()` defaults to `deterministic=False` | Multi-threaded PORTFOLIO_SEARCH — non-deterministic |
| 2 | No `AddDecisionStrategy` on model | `FIXED_SEARCH` degrades to automatic branching — non-deterministic even single-threaded |
| 3 | All 8 call sites in `views.py` use `solve()` without `deterministic=True` | Deterministic mode never activated |

## Proposed Changes

### Optimizer Core

#### [MODIFY] [optimization.py](file:///Users/neeleshpant/Desktop/script_python/iDRS%20v11.1%20(Deterministic%20try%201)/scheduler/optimization.py)

**Change 1:** Default `deterministic=True` in `solve()` (line 1549) and `solve_with_actuals()` (line 1388)

**Change 2:** Add `AddDecisionStrategy` in `setup_variables()` (after line ~851) — this is the critical fix that makes `FIXED_SEARCH` work properly:
```python
# Deterministic branching: assignment vars first (sorted), then start times
all_assignment_vars = []
all_start_vars = []
for _, w in self.wells_df.iterrows():       # Already sorted by name
    for _, r in self.rigs_df.iterrows():     # Already sorted by name
        all_assignment_vars.append(self.assignments[(w["name"], r["name"])])
        all_start_vars.append(self.start_times[(w["name"], r["name"])])

self.model.AddDecisionStrategy(
    all_assignment_vars,
    cp_model.CHOOSE_FIRST,
    cp_model.SELECT_MAX_VALUE,  # Try assigning (1) before not-assigning (0)
)
self.model.AddDecisionStrategy(
    all_start_vars,
    cp_model.CHOOSE_FIRST,
    cp_model.SELECT_MIN_VALUE,  # Prefer earlier start times
)
```

**Change 3:** In `_configure_solver_for_determinism()`, also disable `interleave_search`:
```python
self.solver.parameters.interleave_search = False
```

**Change 4:** Increase default time limit from 60s → 300s to compensate for single-threaded mode, giving the solver enough time to prove OPTIMAL status.

---

### Views Layer

#### [MODIFY] [views.py](file:///Users/neeleshpant/Desktop/script_python/iDRS%20v11.1%20(Deterministic%20try%201)/scheduler/views.py)

**All 8 call sites** — add `deterministic=True` explicitly and increase time limits:

| Line | Current | After |
|------|---------|-------|
| 1731 | `scheduler.solve(time_limit_seconds=tl)` | `scheduler.solve(time_limit_seconds=tl, deterministic=True)` |
| 1948 | `scheduler.solve(validated_data['time_limit_seconds'])` | `scheduler.solve(validated_data['time_limit_seconds'], deterministic=True)` |
| 2346 | `scheduler.solve(time_limit_seconds=tl)` | `scheduler.solve(time_limit_seconds=tl, deterministic=True)` |
| 2350 | `scheduler.solve_with_actuals(..., time_limit_seconds=tl)` | Add `deterministic=True` |
| 2739 | `scheduler.solve_with_actuals(..., time_limit_seconds=600)` | Add `deterministic=True` |
| 2741 | `scheduler.solve(time_limit_seconds=600)` | Add `deterministic=True` |
| 3205 | `scheduler.solve_with_actuals(..., time_limit_seconds=600)` | Add `deterministic=True` |
| 3209 | `scheduler.solve(time_limit_seconds=600)` | Add `deterministic=True` |

**Fix `run_full_optimization()`** (line ~1697): Currently calls `preprocess_data → setup_variables → add_constraints → add_ilm_constraints → set_objective` then calls `solve()` which repeats ALL those steps. Remove the redundant manual calls.

---

### Optimality Enforcement

The `_extract_solution()` already records `is_optimal` (line 1695) and `solver_status` in results. After the fix:
- If `result['is_optimal'] == True` → **provably optimal** (mathematical guarantee)
- If `result['solver_status'] == 'FEASIBLE'` → solver ran out of time, schedule may be suboptimal
  - Recommendation: increase time limit and re-run

The existing `solve_validated()` method with dual-run verification is available but won't be wired into views in this change (to minimize risk). The `is_optimal` flag in results provides the same information.

## User Review Required

> [!WARNING]
> **Deterministic mode is ~3-5x slower** because it uses 1 thread instead of all CPU cores. A schedule that took 60s before may take 180-300s. The time limits at view call sites are being increased from 600s to keep the same (lines 2739, 2741, 3205, 3209 already use 600s which should be sufficient). The `create_schedule` endpoint uses a user-provided time limit (validated_data['time_limit_seconds']), so users may need to set higher values.

## Verification Plan

### Automated Test
Run the solver 3 times on identical input and verify all 3 produce the same schedule hash. Check that solver returns `OPTIMAL` status.

### Manual Verification
1. Create a schedule in the UI with specific rigs and wells
2. Run it at least twice without changing inputs
3. Verify identical assignments, dates, and costs
4. Check the `solver_status` field shows `OPTIMAL` (not `FEASIBLE`)
