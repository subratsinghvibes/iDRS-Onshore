# Fix Non-Deterministic Scheduling in iDRS

The scheduling engine produces different schedules on each run because the deterministic solver mode is implemented but **never actually activated**. Three distinct problems conspire to break determinism.

## Root Cause Analysis

| # | Cause | Location | Impact |
|---|-------|----------|--------|
| 1 | `solve()` and `solve_with_actuals()` default to `deterministic=False` | `optimization.py:1549, 1388` | Multi-threaded PORTFOLIO_SEARCH runs by default — inherently non-deterministic |
| 2 | `FIXED_SEARCH` branching is set but **no `AddDecisionStrategy` is added** to the model | `optimization.py:889` | Without decision strategy hints, `FIXED_SEARCH` degrades to automatic (non-deterministic) branching |
| 3 | All **8 call sites** in `views.py` never pass `deterministic=True` | `views.py:1731,1948,2346,2350,2739,2741,3205,3209` | Even if defaults were correct, callers would override |

> [!IMPORTANT]
> **Root Cause #2 is the most subtle and critical.** Even with `num_search_workers=1` and `FIXED_SEARCH`, OR-Tools CP-SAT requires an explicit `AddDecisionStrategy` on the model to know *which variables to branch on and in what order*. Without it, the solver uses internal heuristics that can vary between runs.

## Proposed Changes

### Optimizer Core

#### [MODIFY] [optimization.py](file:///Users/neeleshpant/Desktop/script_python/iDRS%20v11.1%20(Deterministic%20try%201)/scheduler/optimization.py)

**Change 1: Default `deterministic=True`** (lines ~1549 and ~1388)

```diff
-    def solve(self, time_limit_seconds: int = 60, ..., deterministic: bool = False) -> Dict[str, Any]:
+    def solve(self, time_limit_seconds: int = 60, ..., deterministic: bool = True) -> Dict[str, Any]:
```

```diff
-    def solve_with_actuals(self, ..., deterministic: bool = False) -> Dict[str, Any]:
+    def solve_with_actuals(self, ..., deterministic: bool = True) -> Dict[str, Any]:
```

**Change 2: Add `AddDecisionStrategy` in `setup_variables()`** (after variable creation ~line 851)

Add a deterministic decision strategy that tells OR-Tools exactly how to branch:
- First branch on assignment BoolVars (sorted by well name, then rig name)
- Then branch on start time IntVars (same order)
- Use `CHOOSE_FIRST` + `SELECT_MAX_VALUE` for assignments (try assigning first)
- Use `CHOOSE_FIRST` + `SELECT_MIN_VALUE` for start times (prefer earlier starts)

This ensures FIXED_SEARCH follows a canonical, repeatable search path.

**Change 3: Disable `interleave_search`** in `_configure_solver_for_determinism()`

Add `self.solver.parameters.interleave_search = False` to prevent the solver from interleaving different search strategies.

---

### Views Layer

#### [MODIFY] [views.py](file:///Users/neeleshpant/Desktop/script_python/iDRS%20v11.1%20(Deterministic%20try%201)/scheduler/views.py)

Pass `deterministic=True` explicitly at all 8 call sites. Even though the default will change, explicit is better than implicit for production code:

| Line | Current Call | Fix |
|------|-------------|-----|
| 1731 | `scheduler.solve(time_limit_seconds=...)` | Add `deterministic=True` |
| 1948 | `scheduler.solve(validated_data['time_limit_seconds'])` | Add `deterministic=True` |
| 2346 | `scheduler.solve(time_limit_seconds=...)` | Add `deterministic=True` |
| 2350 | `scheduler.solve_with_actuals(..., time_limit_seconds=...)` | Add `deterministic=True` |
| 2739 | `scheduler.solve_with_actuals(..., time_limit_seconds=600)` | Add `deterministic=True` |
| 2741 | `scheduler.solve(time_limit_seconds=600)` | Add `deterministic=True` |
| 3205 | `scheduler.solve_with_actuals(..., time_limit_seconds=600)` | Add `deterministic=True` |
| 3209 | `scheduler.solve(time_limit_seconds=600)` | Add `deterministic=True` |

Also fix `run_full_optimization()` (line ~1731) which manually calls `preprocess_data → setup_variables → add_constraints → add_ilm_constraints → set_objective` and then calls `solve()` which **repeats all of those steps**. This should just call `solve()` directly.

## Verification Plan

### Automated Test

A standalone determinism verification script that:
1. Creates a `DrillingScheduler` with fixed synthetic test data
2. Runs `solve(deterministic=True)` **3 times** on identical input
3. Computes a schedule hash for each run (same `compute_schedule_hash` method used by `OptimalityValidator`)
4. Asserts all 3 hashes are identical
5. Prints pass/fail with hashes

**Run with:**
```bash
cd "/Users/neeleshpant/Desktop/script_python/iDRS v11.1 (Deterministic try 1)"
python -c "
from scheduler.optimization import DrillingScheduler
from datetime import date

# Create minimal test data
rigs_data = [
    {'name': 'RIG-A', 'start_date': '2024-04-01', 'end_date': '2025-03-31', 
     'rig_capacity_hp': 1500, 'drilling_capacity_m': 5000, 'bop_stack': 3,
     'tds_availability': 'Y', 'daily_cost_inr': 100000, 
     'ilm_cost_fixed': 50000, 'ilm_cost_per_km': 1000, 'ilm_cost_cluster': 0},
    {'name': 'RIG-B', 'start_date': '2024-04-01', 'end_date': '2025-03-31',
     'rig_capacity_hp': 1200, 'drilling_capacity_m': 4000, 'bop_stack': 2,
     'tds_availability': 'N', 'daily_cost_inr': 80000,
     'ilm_cost_fixed': 40000, 'ilm_cost_per_km': 800, 'ilm_cost_cluster': 0},
]
wells_data = [
    {'name': 'WELL-1', 'duration': 30, 'rtd': '2024-04-01', 'rig_capacity_required_hp': 1000, 
     'depth': 3000, 'bop_stack': 2, 'tds_requirement': 'N', 'priority': 'HIGH',
     'latitude': 22.3, 'longitude': 72.6},
    {'name': 'WELL-2', 'duration': 45, 'rtd': '2024-05-01', 'rig_capacity_required_hp': 1200,
     'depth': 3500, 'bop_stack': 2, 'tds_requirement': 'N', 'priority': 'MEDIUM',
     'latitude': 22.4, 'longitude': 72.7},
    {'name': 'WELL-3', 'duration': 20, 'rtd': '2024-04-15', 'rig_capacity_required_hp': 800,
     'depth': 2500, 'bop_stack': 1, 'tds_requirement': 'N', 'priority': 'HIGH',
     'latitude': 22.5, 'longitude': 72.8},
]

import hashlib, json
hashes = []
for i in range(3):
    scheduler = DrillingScheduler(rigs_data, wells_data, base_start_date=date(2024, 4, 1))
    result = scheduler.solve(time_limit_seconds=30, deterministic=True)
    
    assignments = sorted(result.get('assignments', []), 
                        key=lambda x: (x.get('rig',''), x.get('well',''), x.get('well_start_day',0)))
    canonical = json.dumps([{'rig': a['rig'], 'well': a['well'], 'start': a['well_start_day'], 'end': a['well_end_day']} 
                           for a in assignments], sort_keys=True)
    h = hashlib.sha256(canonical.encode()).hexdigest()
    hashes.append(h)
    print(f'Run {i+1}: {len(assignments)} wells assigned, hash={h[:16]}...')

if len(set(hashes)) == 1:
    print('✓ DETERMINISM VERIFIED: All 3 runs produced identical schedules')
else:
    print('✗ DETERMINISM FAILED: Schedules differ between runs')
    for i, h in enumerate(hashes): print(f'  Run {i+1}: {h}')
"
```

### Manual Verification

Since this is a Django application:
1. Open the UI and create a new schedule with the same rigs and wells
2. Run the schedule at least twice without changing any inputs
3. Compare the resulting assignments — they must be identical
