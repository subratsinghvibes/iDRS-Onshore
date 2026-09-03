# Deterministic Scheduling — Root Cause Fix (Round 2)

## Why Schedules Were Still Non-Deterministic

The solver settings (single-threaded, fixed seed, FIXED_SEARCH) were correct, but the **CP-SAT model itself was different on every run** because of two upstream data ordering bugs:

### Root Cause 1: DataFrames Sorted Too Late

In `preprocess_data()`, the sort happened at **line 672** — AFTER the distance matrix (line 666) and ILM matrix (line 669) were already built. This meant:
- Matrices were constructed from **unsorted** DataFrame rows
- Variable IDs and constraint ordering depended on the original (random) row order
- Even though named lookups worked, the **model proto** was structurally different each time

### Root Cause 2: Unordered Database Queries

In `views.py`, all queries feeding the scheduler used `Rig.objects.filter(id__in=...)` **without** `.order_by('name')`. With UUID primary keys, SQLite/PostgreSQL returns rows in **arbitrary hash order** that changes between connections.

## Fixes Applied

### [optimization.py](file:///Users/neeleshpant/Desktop/script_python/iDRS%20v11.1%20(Deterministic%20try%201)/scheduler/optimization.py)

| Fix | What Changed |
|-----|-------------|
| **Sort FIRST** (line 674) | DataFrames now sorted by `name` BEFORE distance/ILM matrix construction |
| **Model fingerprint** (line 1724) | SHA-256 hash of model proto logged before solve — verify identical models between runs |
| Same fingerprint added to `solve_with_actuals()` (line 1554) | |

### [views.py](file:///Users/neeleshpant/Desktop/script_python/iDRS%20v11.1%20(Deterministic%20try%201)/scheduler/views.py)

| Location | Fix |
|----------|-----|
| `run_full_optimization()` (line 1712) | Added `.order_by('name')` to rig and well QuerySets |
| `create_schedule()` (line 1889) | Added `.order_by('name')` to `Rig.objects.filter()` and `Well.objects.filter()` |
| `_run_optimization_with_constraints()` (line 3141) | Added `.order_by('name')` with `hasattr` guard |

## How to Verify

1. Run the schedule **twice** with the same rigs/wells/time limit
2. Check the Django logs for `MODEL FINGERPRINT:` — the hash **must be identical** between runs
3. If the hashes match → the model is identical → the solver MUST produce the same result
4. If hashes differ → there's still an input ordering issue (report back)
