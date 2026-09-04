# Implementation Plan

## Notes before starting

**Clause 2.5 is delivered by interpretation, not literally.** The design (root cause 4, and the
"Requirement conflict to resolve before implementation" section) established that clause 2.5's
literal wording — "a strictly dominating weight hierarchy … so that no two distinct schedules share
an objective value" — is **not achievable** with polynomially-bounded integer weights: the solution
space is exponential and an injective linear objective over it would need exponential coefficients.
The requirements' own measurement confirms this: 2 distinct schedules still tied at the optimum
under the previously-dominating `START_TIME_WEIGHT`. This plan therefore delivers clause 2.5's
stated goal — its opening words, "select a single canonical one" — via the dominating tie-break
hierarchy in the stage-2 solve (task 4) plus the deterministic stop (task 3). The residual is not
hand-waved: task 9.2's tie-enumeration test **measures** it by counting distinct schedules at
`(P-expr == V*) AND (T-expr == T*)` and failing if the count exceeds 1. If that test ever reports
> 1, the trigger is to add the third tie-break tier (arc-order index over `circuit_arcs`) described
in design decision 3. If you want clause 2.5 reworded in `bugfix.md` to match this reading, say so
and we return to the requirements phase before task 3 runs.

**Line numbers** cited below are the design's, checked against the current working tree. A few are
off by a line or two (e.g. `_add_decision_strategy`'s `pass` is at `:992`, design says `:986-994`).
Earlier tasks also shift later line numbers. Re-locate by symbol name before editing.

**Tasks flagged for review before running:**

| Task | Why it needs review |
|---|---|
| 3 | Changes how much search is performed. Can change the returned schedule on any request that does not prove optimality today. |
| 4 | Changes which schedule is returned when several tie at the optimal objective. Objective value is preserved by construction; assignments may differ. |
| 5 | Total orderings replace ties currently resolved by the database. Can change output on inputs with duplicate well names, tied `RigBuildingAdjustment` rows or overlapping `WellPairDistance` rows. |
| 6 | Turns a currently-silent duplicate-well-name collision into an explicit rejection. Requests that "work" today (and then fail opaquely at save) will now be refused up front. |
| 7 | Adds a branching preference. `AUTOMATIC_SEARCH` is retained, but the search path changes, so a timed-out run can return a different incumbent. |
| 8 | **DATABASE SCHEMA CHANGE.** Migration `0063_add_determinism_provenance.py` adds six nullable fields to `Schedule`. Additive and reversible, but it must be applied on the VM. |

**Dependency addition:** the property-based tests (task 9.1) need `hypothesis`, which is not in
`requirements.txt` and not present in `.venv` (verified). Pin the exact resolved version.

---

- [x] 1. Write bug condition exploration harness

  - **Property 1: Bug Condition** - Repeated runs return one schedule
  - **CRITICAL**: This harness MUST FAIL on the current unfixed code. Failure is what confirms the
    diagnosis. **DO NOT fix the test or the code when it fails.**
  - **IF THE HARNESS PASSES ON UNFIXED CODE THE DIAGNOSIS IS WRONG — STOP.** Do not write any fix
    code. Return to the requirements phase. Specifically: if `schedule_hash` is stable while
    `deterministic_time` varies, the wall-clock-stop mechanism (design root cause 1) is not the
    cause and the analysis moves to the ordering hazards (root cause 6).
  - **NOTE**: This harness encodes the expected behaviour. The same tests validate the fix in 3.5,
    4.7 and 9.3 — they are re-run, never rewritten.
  - **GOAL**: Surface counterexamples that demonstrate the bug exists.
  - **Scoped PBT Approach**: The bug is load- and size-dependent, not universal, so scope the
    property to the concrete failing regime rather than generating freely: a model with enough wells
    to stay open, a short `time_limit_seconds` so the solver cannot prove optimality, and cores
    saturated on at least 2 of the N runs. Free generation would mostly produce models that close to
    optimality, where the bug does not fire.
  - Replace the `scheduler/tests.py` placeholder (2 lines, `from django.test import TestCase`) with
    a `scheduler/tests/` package — Django discovers tests in a package identically
    (design decision 8)
  - Create `scheduler/tests/__init__.py` and `scheduler/tests/factories.py` — in-memory rig/well
    dicts **plus** the matching `Rig`, `Well` and `WellPairDistance` DB rows, so the real ILM path
    at `scheduler/optimization.py:733-734`, `:781-783`, `:813` is exercised instead of the fallback
  - Use `django.test.TestCase`, not `SimpleTestCase` — `_calculate_ilm_days_matrix` queries the DB
  - Create `scheduler/tests/test_determinism.py::test_repeat_runs_yield_one_schedule_hash` — N = 5
    solves, a fresh `DrillingScheduler` per run from identical input dicts, asserting exactly one
    distinct value each of `schedule_hash`, `model_fingerprint`, `objective_value`, and that every
    run's `(well, rig, start_day, end_day)` tuple list equals run 1's
  - Create `test_repeat_runs_under_cpu_load` — 2 of the runs execute while background
    `multiprocessing` busy-loops saturate the cores; gate behind `IDRS_TEST_CPU_LOAD=1` so a shared
    box is not wrecked. This is the test that would have caught the original bug
  - Record `solver.deterministic_time` on every run and assert it **varies** (design's exploratory
    test case 2 — the requirements measured 7.1256 → 7.3596). This is the direct evidence that the
    wall-clock stop is the mechanism, and it is what discriminates between root cause 1 and the
    ordering hazards
  - Create `scheduler/tests/test_tie_enumeration.py` — the 5-well / 2-identical-rig symmetric model
    from the requirements. Enumerate solutions at the optimal objective with today's
    `START_TIME_WEIGHT = 1` / `RIG_WELL_ORDER_WEIGHT = 1`
    (`scheduler/optimization.py:1358-1359`, verified at `:1358-1359` in the current file) using
    `enumerate_all_solutions = True` and `num_search_workers = 1`; expect ≫ 1 distinct
    `schedule_hash` (10 on the requirements' model). Cap the callback at 50 solutions and fail on
    the cap so a regression fails fast instead of hanging
  - Add an exploratory check for the silent duplicate-well-name collision: two wells sharing a
    `name` (no `unique=True` at `scheduler/models.py:394`), solve, and observe `len(assignments)`
    short by one with no error raised — `self.assignments[(wid, rid)]`
    (`scheduler/optimization.py:891`) creates one variable pair for two wells
  - Add an exploratory check for the `RigBuildingAdjustment` tie: two rules with equal `priority`
    and `category`, re-created in the opposite insertion order, and observe whether
    `calculate_ilm_days` (`scheduler/views.py:10791`, `:11087`) returns a different ILM value
  - Run the whole harness on UNFIXED code
  - **EXPECTED OUTCOME**: Tests FAIL. Two or three distinct `schedule_hash` values across five runs
    at an identical `model_fingerprint`, with `deterministic_time` differing between them; ≫ 1 tied
    schedule at the optimal objective
  - Document every counterexample found — objective values, hashes, deterministic times, tied count
    — in the task notes, so the fix has a measured baseline to be judged against
  - Mark complete when the harness is written, run, and the failures are documented
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 2.12_

### Task 1 measured baseline (counterexamples on the UNFIXED code)

Environment: macOS, 12 cores (8P + 4E), Python 3.13, Django 5.1.5, `ortools==9.15.6755`,
PostgreSQL test database `test_idrs_db`. Runner: `python manage.py test scheduler.tests`.

Files delivered (tests only — no production file was touched; `git status` shows exactly
`D scheduler/tests.py` and `?? scheduler/tests/`):

```
scheduler/tests/__init__.py
scheduler/tests/cpu_burn.py                 # Django-free burner target (spawn-safe)
scheduler/tests/factories.py                # DB rows + optimizer input dicts
scheduler/tests/support.py                  # measurement + CPU load harness
scheduler/tests/test_determinism.py         # Property 1, repeat runs
scheduler/tests/test_tie_enumeration.py     # Property 1, tied-optimum count
scheduler/tests/test_ordering.py            # Property 5, duplicates + tied ILM rules
```

**Result: 3 of 4 assertions fail on unfixed code (4 of 5 with `IDRS_TEST_CPU_LOAD=1`).**
Ungated suite: 6 tests, 61 s. Under-load test: 211 s.

#### 1a. Repeat runs, idle machine — PASSES on unfixed code (expected)

`test_repeat_runs_yield_one_schedule_hash`, 5 solves, 6 s limit, 6 rigs / 40 wells, all
`FEASIBLE`:

| run | schedule_hash | objective | det_time | wall_s | assigned | total_cost |
|---|---|---|---|---|---|---|
| 1-5 | `1a6136917eac05eb` | 97,768,602,348 | 3.4378 | 5.85-5.99 | 23 | 1,279,834,676 |

One distinct hash, one fingerprint, one objective, `deterministic_time` spread 0.0000.
**This is not a contradiction of the diagnosis** — `bugfix.md` records the same thing
("1 distinct schedule on an idle machine"). On an idle machine the same amount of work fits
in the same wall-clock window every time, so the stop lands on the same node. The idle test
is the clause-2.12 regression guard; the load test is the reproduction.

#### 1b. Repeat runs, idle vs CPU-saturated — FAILS (the bug)

`test_repeat_runs_under_cpu_load`, 3 idle + 2 loaded (36 burner processes = 3x cores),
same scenario, same 6 s limit:

| run | load | schedule_hash | objective | det_time | wall_s | assigned | total_cost |
|---|---|---|---|---|---|---|---|
| 1 | N | `1a6136917eac05eb` | 97,768,602,348 | 3.4378 | 5.92 | 23 | 1,279,834,676 |
| 2 | N | `1a6136917eac05eb` | 97,768,602,348 | 3.4378 | 5.88 | 23 | 1,279,834,676 |
| 3 | N | `1a6136917eac05eb` | 97,768,602,348 | 3.4378 | 5.85 | 23 | 1,279,834,676 |
| 4 | **Y** | `92f12d9691802821` | **223,981,623,957** | **0.7595** | 6.02 | **1** | **42,900,000** |
| 5 | **Y** | `92f12d9691802821` | **223,981,623,957** | **0.8579** | 6.00 | **1** | **42,900,000** |

- distinct `schedule_hash` = **2**; distinct `objective_value` = **2**
- distinct `model_fingerprint` = **1** — the input model is byte-identical, so this is *not* an
  input-ordering failure
- `deterministic_time` spread **2.6783** (0.7595 → 3.4378); the two loaded runs also differ
  from *each other* (0.7595 vs 0.8579), while the three idle runs agree to 4 dp
- business impact: the same request assigns **23 wells** idle and **1 well** under load

**Mechanism confirmed.** `schedule_hash` varies *and* `deterministic_time` varies → the stop is
being taken at different amounts of completed search work, i.e. the wall-clock criterion at
`scheduler/optimization.py:927`, `:954` — design root cause 1. Had the hash varied while
`deterministic_time` stayed identical, the diagnosis would have moved to the ordering hazards
(root cause 6); the harness prints that discrimination explicitly.

#### 1c. Deterministic-time drift is the mechanism, measured directly

Objective-versus-work curve for the same scenario, idle, at increasing limits — the answer keeps
moving across the whole budget, which is why a work-level change changes the schedule:

| limit | det_time | objective | assigned | schedule_hash |
|---|---|---|---|---|
| 2 s | 1.436 | 201,514,687,130 | 5 | `c3c419ee932837aa` |
| 4 s | 2.642 | 97,768,602,348 | 23 | `1a6136917eac05eb` |
| 6 s | 3.438 | 97,768,602,348 | 23 | `1a6136917eac05eb` |
| 8 s | 3.438 | 97,768,602,348 | 23 | `1a6136917eac05eb` |
| 12 s | 7.438 | 97,767,133,788 | 23 | `69b8cb1284a85ccc` |
| 20 s | 12.413 | 97,213,755,424 | 23 | `3eba90abc73564bb` |

Note limits 6 s and 8 s both stop at 3.438 units with wall times of 5.8 s and 5.9 s — inside those
limits CP-SAT's own work budget binds, not the clock. Under contention the clock binds instead and
the run is cut short. That is the whole defect in one table.

Calibration note for later tasks: **model sizing is load-bearing**. A 5-rig / 26-well model settled
its incumbent by ~1.5 work units and then plateaued, so it was reproducible *by accident* — hash
identical at both 2.55 and 4.62 units. Divergence only appears when the incumbent is still
improving at the stop. `factories.HARD_OPEN_CONFIG` records the configuration that achieves that
(large distance-scaled ILM gaps couple the routing to the well-count tier). Likewise CPU-load
intensity: at 1 burner per core the solver still completed ~60 % of its idle work and nothing
diverged; 3 per core (~20 %) is what exposes the defect.

#### 1d. Tied optima — FAILS

`test_exactly_one_schedule_attains_the_optimal_objective`, 5 wells / 2 identical rigs,
`OPTIMAL`, V\* = **218,583,260**:

- **4 distinct schedules attain V\*** — `0b236ee41210272d`, `21eab6f2022716e3`,
  `2659d0ba8a8fc116`, `8fa867e67fbbd0bd`
- the enumeration **exhausted** the tied set (terminated `INFEASIBLE`, cap of 50 not reached), so 4
  is an exact count, not a lower bound
- baseline for task 4.6 / 9.2: 4 → *at the time this was written*, "must become 1". **Superseded by
  the Option B decision recorded in "Task 4 results" below**: the four are interchangeable
  permutations that no sum-based tie-break tier can separate, clause 2.5 was reworded, and the target
  is now the measured count (4) with the tied count still > 1 and both enumerations exhausted. The
  test method is now `test_the_canonical_set_matches_its_measured_size`

Method deviation, deliberate and documented in the test's module docstring: the design suggested
`enumerate_all_solutions = True` with a solution callback. That was tried first and does **not**
measure the tied-schedule count. `start_time_sum` in the objective
(`scheduler/optimization.py:1394`) sums the start-time variables of *every* `(well, rig)` pair
including unselected ones, and those variables are otherwise unconstrained, so one schedule maps to
combinatorially many full solutions. Measured: the callback hit the 50-solution cap having seen only
**3** distinct schedules. The committed test instead solves repeatedly and adds a no-good clause per
schedule (assignment pattern + start day of each selected pair, unselected pairs excluded), which
counts schedules exactly and still fails fast on a 50 cap.

#### 1e. Duplicate well names — FAILS

`test_duplicate_well_names_are_rejected_naming_the_duplicates`, 3 wells of which 2 share
`name = "WELL-001"`, 1 rig:

- `preprocess_data()` does **not** reject the input
- 3 well rows collapse to **2 assignment variables** (one per well x rig would be 3) —
  `self.assignments[(wid, rid)]` at `scheduler/optimization.py:891` overwrites
- the run then dies downstream in `add_ilm_constraints` with
  `TypeError: float() argument must be a string or a real number, not 'DataFrame'`
  (`optimization.py:1173`, `ilm_matrix.loc[wi, wj]` returns a DataFrame because the matrix index has
  duplicate labels; the surrounding `except (KeyError, ValueError)` does not catch `TypeError`).
  The message names no well, so the operator has nothing to act on
- side observation confirming design decision 5: the dead `well_name_to_obj` loop logs
  `Error building well lookup: get() returned more than one Well -- it returned 2!` — the
  `MultipleObjectsReturned` swallowed by the broad `except` at `optimization.py:753`

So clause 1.6's "silently collides them" is confirmed, with the refinement that the collision is
silent only until ILM construction, where it becomes an opaque `TypeError` rather than a named
rejection.

#### 1f. Tied `RigBuildingAdjustment` rows — FAILS

`test_ilm_days_do_not_depend_on_rule_insertion_order`. Two `replace` rules, identical `priority`
(100) and `category` (`cluster_movement`), both matching all distances, values 2.0 and 7.0 days.
Same rule *set* both times; only the insertion order differs:

| insertion order | fetch order under `order_by('-priority','category')` | ILM days |
|---|---|---|
| X then Y | X (2.0), Y (7.0) | **2.0** |
| Y then X | Y (7.0), X (2.0) | **7.0** |

A 5-day swing in the ILM gap for identical data. `calculate_ilm_days` applies the first matching
`replace` rule and latches `base_replaced` (`scheduler/views.py:10831-10839`), and the ILM matrix
feeds the circuit gap constraints, so this changes the model the solver sees. Clause 1.8 confirmed.

#### How to re-run

```bash
python manage.py test scheduler.tests                      # 61 s, 3 failures + 1 skip
IDRS_TEST_CPU_LOAD=1 python manage.py test scheduler.tests  # + the reproduction, 4 failures
```

The CPU-load test is gated behind `IDRS_TEST_CPU_LOAD=1` because it spawns 3 busy-loop processes per
core. `cpu_load()` verifies every burner is alive and raises if not, so the test cannot silently
measure an idle machine and pass for the wrong reason.

- [x] 2. Capture golden preservation fixtures from the CURRENT code (BEFORE implementing any fix)

  - **Property 2: Preservation** - Unique proven optima are untouched
  - **IMPORTANT**: Follow observation-first methodology. Property 2 compares against **today's**
    behaviour, so these fixtures MUST be captured before any solver change lands. Once task 3 runs,
    the baseline is gone.
  - **CRITICAL ORDERING**: this task must complete before task 3 begins.
  - Create `scheduler/tests/test_preservation.py` and
    `scheduler/tests/fixtures/preservation_golden.json`
  - Observe: a model small enough to prove `OPTIMAL` with a unique optimum — record every
    assignment `(well, rig, start_day, end_day, sequence_order)`, the `objective_value` and the
    `schedule_hash` from the current code (`¬isBugCondition` regime)
  - Observe: `deterministic=False` performance mode (`scheduler/optimization.py:962-978`) — record
    the parameter block and the results, so clause 3.12 can be asserted unchanged
  - Observe: `solve_with_actuals` (`scheduler/optimization.py:1514`) with pinned actual start/end
    dates (`:1458-1513`) — record that the actuals are pinned exactly and that `fixed_actuals` is
    sorted by `(well, rig)` first (`:1527-1528`)
  - Observe: the save path — per-rig `sequence_order` derived from start date
    (`scheduler/views.py:1996-2002`, verified near `:1997`) and unassigned wells carrying rejection
    analysis (`:2069-2084`)
  - Record the git commit SHA the goldens were captured from **inside** the fixture file, so the
    provenance is auditable (design decision 8)
  - Write the assertions as property tests over the fixture: assignments and `objective_value` equal
    the golden for every recorded case
  - Run on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS. This is the baseline that tasks 3-8 must not move
  - Mark complete when the fixtures are committed and the tests pass on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.10, 3.11, 3.12, 3.13_

### Task 2 captured baseline (goldens from the UNFIXED code)

Fixture: `scheduler/tests/fixtures/preservation_golden.json` (433 lines, strict JSON — no
`Infinity`/`NaN` tokens, so non-Python parsers can read it).

Provenance recorded **inside** the fixture: `git_commit`
`3561731c40b4fe6f1fae336f9307911ee0267294` (branch `main`), captured `2026-09-03`,
`ortools 9.15.6755`, Python `3.13.9`, Django `5.1.5`, macOS arm64, 12 cores,
`working_tree_clean_of_production_files: true` with
`working_tree_production_files_modified: []`, plus a SHA-256 for each of the six production files
the goldens depend on (`scheduler/optimization.py` `14e26153…`, `views.py` `202767a9…`,
`models.py` `537c0d94…`, `serializers.py` `f1cde900…`, `well_rejection_analyzer.py` `9bcdb1b6…`,
`drilling_scheduler/settings.py` `09f422ed…`).

**Acceptance: all 8 tests in `scheduler.tests.test_preservation` pass WITHOUT
`IDRS_REGENERATE_GOLDEN`.** No production file was modified — `git status` shows only
`M .kiro/…/tasks.md`, `D scheduler/tests.py` and the untracked `scheduler/tests/` package, and
`git diff HEAD` over the six production files is empty.

#### Case 1 — `unique_optimum` (clauses 3.1, 3.3, 3.4, 3.6, 3.8)

5 wells / 2 rigs, 10 s limit, deterministic mode, `OPTIMAL` with `optimality_gap = 0.0`:

| field | value |
|---|---|
| `objective_value` / `best_bound` | **698,525,729** |
| `schedule_hash` | **`0dcdf8e6ecc66b25`** |
| `model_fingerprint` | `aba6f48409da8d3b40f8d04cb33985763c4e0415db5eb265f48a2c0a094d224d` |
| wells assigned / unassigned | 4 / 1 (`WELL-005`) |
| rigs used | 2 of 2 |
| `total_drilling_cost` | 187,800,000.0 |
| `total_ilm_cost` | 10,098,668.668948516 |
| `total_cost` | 197,898,668.66894853 |
| `project_end_day` / date | 85 / 2024-06-25 |
| FY window | 2024-04-01 → 2025-03-31, `fy_constrained = True` |

| well | rig | start_day | end_day | start_date | end_date | days | seq | drilling_cost | ilm_cost | ilm_days |
|---|---|---|---|---|---|---|---|---|---|---|
| WELL-001 | RIG-01 | 44 | 85 | 2024-05-15 | 2024-06-24 | 41 | 2 | 49,200,000 | 4,593,893.935130352 | 11.1 |
| WELL-002 | RIG-01 | 0 | 33 | 2024-04-01 | 2024-05-03 | 33 | 1 | 39,600,000 | null | null |
| WELL-003 | RIG-02 | 42 | 79 | 2024-05-13 | 2024-06-18 | 37 | 2 | 55,500,000 | 5,504,774.733818165 | 13.4 |
| WELL-004 | RIG-02 | 0 | 29 | 2024-04-01 | 2024-04-29 | 29 | 1 | 43,500,000 | null | null |

Parameter block in force (clause 3.4): `num_search_workers = 1`, `random_seed = 42`,
`search_branching = AUTOMATIC_SEARCH`, `symmetry_level = 2`, `use_lns = true`,
`interleave_search = true`, `cp_model_presolve = true`, `enumerate_all_solutions = false`,
`max_time_in_seconds = 10`, `max_deterministic_time = inf` (unset — the wall clock is the only
limit today, which is precisely what task 3 changes), `interleave_batch_size = 0` (unset, the
silent default design decision 2 rung 1 pins).

#### Case 2 — `optimum_uniqueness` (the precondition that makes case 1 meaningful)

`V*` = **698,525,729**, **exactly 1** schedule attains it, `schedule_hash 0dcdf8e6ecc66b25`,
`enumeration_exhausted = True` (terminated `INFEASIBLE`, not on the 50 cap). So this is the
`¬isBugCondition` regime: there is only one answer available, and Property 2 can demand
byte-identical output without asking the solver to break a tie.

#### Case 3 — `performance_mode` (clause 3.12)

`deterministic=False`, `OPTIMAL`. Parameter block: `num_search_workers = 0` (auto-detect),
`search_branching = PORTFOLIO_SEARCH`, `random_seed = 42`, `symmetry_level = 2`,
`use_lns = true`, `interleave_search = false`, **`max_deterministic_time = inf`** (no budget).

Same answer as case 1 — `objective_value` 698,525,729 and `schedule_hash 0dcdf8e6ecc66b25` — which
is sound rather than lucky: the scenario has a unique optimum (case 2), so every solver that proves
optimality has exactly one schedule available to return whatever path it took. A future difference
here means the model or the economics moved, not that a race resolved differently.

#### Case 4 — `solve_with_actuals` (clauses 3.10, 3.11)

Pinned actual start/end dates, `OPTIMAL`, `optimality_gap = 0.0`:

- `objective_value` / `best_bound` = **710,225,835**
- `schedule_hash` = **`ade2afa77882d02e`**
- `model_fingerprint` = `9ebfd59f5ccdc6fc402687d86ad48d13c7234eec69baef5a4ccd785c427d587a`
- `project_end_day` 124 (2024-08-03); 4 assigned, `WELL-005` unassigned
- assignments: WELL-001/RIG-01 0→41 seq 1, WELL-002/RIG-01 60→93 seq 2, WELL-004/RIG-02 45→74
  seq 1, WELL-003/RIG-02 87→124 seq 2 — the pinned actuals are held exactly
- deterministic parameter block, identical to case 1
- separately asserted (not a golden value): reversing the `fixed_actuals` input order leaves
  `model_fingerprint`, `schedule_hash` and `objective_value` unchanged, so the `(well, rig)` sort at
  `optimization.py:1527-1528` is already doing its job on this path

#### Case 5 — `save_path` (clause 3.13)

Driven through the real `POST /api/schedules/create_schedule/`, so these are the rows Django
actually wrote: HTTP **200**, `Schedule.status = COMPLETED`, `solver_status = OPTIMAL`,
`schedule_hash 0dcdf8e6ecc66b25`, `optimality_gap_percent 0.0`,
`total_drilling_cost 187800000.00`, `total_ilm_cost 10098668.67`,
`project_end_date 2024-06-25`, `input_rigs_count 2`, `input_wells_count 5`.

Per-rig `sequence_order` derived from start date, cross-checked against
`support.derive_sequence_orders`: RIG-01 → WELL-002 seq 1, WELL-001 seq 2; RIG-02 → WELL-004 seq 1,
WELL-003 seq 2.

`UnassignedWell`: `WELL-005`, reason `"Analysis error: 'capacity_hp'"`.

**Two pre-existing production defects are captured as-is, deliberately.** This is an observation
task and Property 2 preserves today's *behaviour*, not today's intentions. Both are out of scope
here and neither was touched:

- `UnassignedWell.reason` is an analyser error string, not a rejection reason.
  `WellRejectionAnalyzer` reads `rigs_df['capacity_hp']` (`well_rejection_analyzer.py:49`) while
  `views.py:2044` builds that frame with a `rig_capacity_hp` column, so the lookup raises `KeyError`
  and the broad `except` stores the text.
- `Schedule.unassigned_wells_count` persists as **0** despite one unassigned well. `views.py:1968`
  reads `results['unassigned_wells_count']` but `_extract_solution` publishes
  `wells_unassigned_count` (`optimization.py:1868`), so the `.get(..., 0)` default always wins.

If a later task changes either value, the goldens will flag it — which is the point. Fixing them is
a separate change.

#### Test-harness repairs needed to make the capture run

No production file was touched. Five defects in the task 1 / task 2 harness blocked the capture:

1. `support.explicit_solver_parameters` called `solver.parameters.ListFields()`. Under
   `ortools 9.15.6755` `solver.parameters` is a pybind11 wrapper
   (`cp_model_helper.SatParameters`), not a protobuf message: no `ListFields`, no
   `SerializeToString`, no `DESCRIPTOR`. Rewritten to parse `str(solver.parameters)`, which emits
   the text-format proto with one `key: value` line per field that was set. An unrecognised line is
   parked under `__unparsed_line_N` so an OR-Tools upgrade degrades loudly instead of breaking the
   capture. This single call accounted for all 6 original test errors.
2. The comment above `PARAMETERS_OF_INTEREST` claimed that, the message being proto3, a field
   assigned its default value drops out of the record and `num_search_workers = 0` would therefore
   be invisible. **That is false for this API** — verified: `num_search_workers: 0` and
   `enumerate_all_solutions: false` both appear in `str()`. Comment corrected; the read-by-name
   mechanism is kept, with its real rationale (a fixed set of keys present in every observation
   whether or not the code set them).
3. `effective_solver_parameters` returned values that will not serialise. `search_branching` is a
   `SearchBranching` enum object → coerced to its ordinal, chosen over its name because the pybind
   enum compares equal to its own integer (`0 == cp_model.AUTOMATIC_SEARCH`), so the existing
   assertions needed no change. `max_time_in_seconds` / `max_deterministic_time` default to
   **infinity**, and `json` writes a bare `Infinity` that is invalid for non-Python parsers →
   non-finite floats become the proto text spelling `"inf"` / `"-inf"` / `"nan"`.
4. `test_preservation.py` asserted performance mode has `max_deterministic_time == 0.0`. The proto
   default is **inf**, not zero — and zero would be the opposite claim, a budget of no work at all.
   Corrected to `"inf"`, which is what "no deterministic budget" actually looks like.
5. `golden._git()` stripped the whole `git status --porcelain` output, eating the leading
   status-column space of the first line, so `line[3:]` shifted left and
   `.kiro/…/tasks.md` was recorded as `kiro/…/tasks.md`. That failed the `.kiro/` allow-prefix and
   was misreported as a modified production file, which made
   `working_tree_clean_of_production_files` false and failed `test_provenance_is_complete`. `_git`
   now takes `strip=False` for porcelain.

`SavePathPreservationTests` additionally logs in with `scheduler.signals.log_user_login`
disconnected, reconnected via `addCleanup`. `force_login` does not go through a view: Django sends
`user_logged_in` with a bare `HttpRequest()` whose `method` is `None`, the receiver passes it to
`UserActivity.log` which writes `request_method` into a NOT NULL column, and PostgreSQL raises
`NotNullViolation`. The receiver's own `except Exception` swallows it, but the `TestCase` atomic
block is already poisoned and every later query fails — including `force_login`'s own
`session.save()`. An artifact of the synthetic request, not a production defect: a real login
arrives through a view where `method` is always set. Nothing this case observes concerns login
auditing.

#### How to re-run

```bash
# verify against the committed baseline (this is the acceptance test)
python manage.py test scheduler.tests.test_preservation --keepdb        # 8 tests, all pass

# regenerate — refused once any production file listed in the fixture has changed
IDRS_REGENERATE_GOLDEN=1 python manage.py test scheduler.tests.test_preservation --keepdb
```

Regeneration is gated on `IDRS_REGENERATE_GOLDEN=1`, refuses to write a partial fixture if any of
the 5 cases failed to capture, and refuses outright once `production_file_sha256` drift is detected
— overriding that needs `IDRS_GOLDEN_OVERWRITE_EVEN_THOUGH_THE_SOLVER_CHANGED=1`. **After task 3
lands, a preservation failure means the fix moved an answer that was already correct. Fix the
change, not the fixture.**

#### Task 1 baseline re-confirmed unchanged

`python manage.py test scheduler.tests --keepdb` → 14 tests, **3 failures + 1 skip**, 59 s. The
three failures are exactly the documented task 1 counterexamples and must stay failing until their
fix tasks land:

| test | documented in | status |
|---|---|---|
| `test_repeat_runs_yield_one_schedule_hash` | 1a | passes — 1 hash, det_time spread 0.0042 |
| `test_repeat_runs_under_cpu_load` | 1b | skipped (needs `IDRS_TEST_CPU_LOAD=1`) |
| `test_exactly_one_schedule_attains_the_optimal_objective` — since renamed `test_the_canonical_set_matches_its_measured_size` | 1d | **FAILS — still 4 tied schedules** at `V*` 218,583,260, enumeration exhausted → task 4.6 target (closed by Option B: 4 is the pinned measured count) |
| `test_duplicate_well_names_are_rejected_naming_the_duplicates` | 1e | **FAILS** → task 6 target |
| `test_ilm_days_do_not_depend_on_rule_insertion_order` | 1f | **FAILS** — still 2.0 vs 7.0 days → task 5.3 target |

- [x] 3. Fix — stopping criterion: deterministic time becomes the binding limit (design decision 1 + 2)

  **⚠️ REVIEW REQUIRED — may change existing schedule output.** This changes how much search is
  performed inside the user's time limit, so any request that does not prove optimality today can
  return a different (reproducible) schedule. This is the load-bearing change and lands alone so it
  is independently attributable.

  - [x] 3.1 Add the `IDRS_SOLVER_DETERMINISM` settings block
    - `drilling_scheduler/settings.py`, alongside the existing `VIDEO_PROCESSING` dict precedent
      (verified at `:227`)
    - `DETERMINISTIC_TIME_RATIO` (env `IDRS_DETERMINISTIC_TIME_RATIO`, default `0.60`),
      `WALL_BACKSTOP_FACTOR` (default `1.5`, sized from measured contention on the deployment
      machine; it must **exceed** (worst observed wall-seconds per deterministic unit ×
      `DETERMINISTIC_TIME_RATIO`) with headroom) *(revised by the user's Option A decision —
      Property 4's `1.2 × T` bound was deliberately superseded; see "Deriving
      `WALL_BACKSTOP_FACTOR = 1.5`" below)*,
      `CANONICALIZE_BUDGET_SHARE` (default `0.15`), `FIXED_SEARCH` (default `False`)
    - Document in the comment what `DETERMINISTIC_TIME_RATIO` is for: it is a **search quality
      knob**. `0.60` is the measured full-quality value (23 wells assigned); `0.15` was reproducible
      but collapsed the schedule to 1 well and is rejected. Contention is absorbed by
      `WALL_BACKSTOP_FACTOR`, **not** by shrinking the ratio. It is not a headroom knob and not a
      slow-machine-vs-fast-machine knob *(revised by the user's Option A decision — this bullet
      previously described the ratio as a headroom knob)*
    - Document in the same comment that it is a **schedule-affecting** configuration change, not a
      performance knob: tuning it changes how much search is done and therefore can change the
      answer. It belongs in the solver fingerprint (task 8)
    - _Requirements: 2.2, 2.4, 2.7_

  - [x] 3.2 Replace the wall-clock stop with the deterministic budget
    - `scheduler/optimization.py` — `_configure_solver_for_determinism` (`:905-984`)
    - Set `max_deterministic_time = D` where `D = DETERMINISTIC_TIME_RATIO × T` as the binding limit
    - Set `max_time_in_seconds = WALL_BACKSTOP_FACTOR × T` as a backstop only (replaces `:927` and
      the overwrite at `:954`)
    - Keep unchanged: `num_search_workers = 1` (`:932`), `random_seed = 42` (`:935`),
      `search_branching = AUTOMATIC_SEARCH` (`:938`), `symmetry_level = 2`, `use_lns = True`
      (`:942`), `interleave_search = True` (`:945`), `cp_model_presolve = True` (`:981`) —
      per clause 3.4 and design decision 2
    - Pin `interleave_batch_size` explicitly (design decision 2, rung 1 — currently unset, so
      OR-Tools derives it from the worker count and an upgrade can change it silently). This
      converts an invisible default into a recorded parameter
    - Delete the comment block at `:947-953` (verified present, "CRITICAL ENTERPRISE FIX … CP-SAT
      guarantees perfect determinism … out-of-the-box"); it asserts the opposite of what task 1
      measured. Replace it with a short note recording the measurement and the mechanism: LNS is
      metered in deterministic time already, as the sibling parameters
      (`probing_deterministic_time_limit`, `shaving_search_deterministic_time`, …) demonstrate
    - **Hard rule**: no solver parameter may be derived from a measured wall time. Every parameter
      is a pure function of `T`. A remaining-time computation reintroduces the bug through the back
      door
    - Note the scope of the guarantee in a docstring: the same request run repeatedly on this
      machine performs the same amount of search and returns the same schedule regardless of how
      busy the machine is, because the stop is metered in work rather than in elapsed time.
      `ortools` is pinned at `requirements.txt:21` (`ortools==9.15.6755`, verified) so the solver
      build is a fixed, recorded input — state that as a version-pinning fact, not as a
      cross-platform claim
    - _Bug_Condition: `isBugCondition(X)` where `stopsOnWallClock` — `solveStatus(F, X) ≠ OPTIMAL`_
    - _Expected_Behavior: every run performs exactly the same amount of search, so the incumbent at
      the stop is reproducible_
    - _Preservation: a request that proves `OPTIMAL` inside `D` is unaffected — the proof needs no
      budget_
    - _Requirements: 2.2, 2.3, 2.4, 3.4, 3.9_

  - [x] 3.3 Implement stop-reason classification
    - After each `Solve()`, read `solver.deterministic_time` and `solver.wall_time` and classify in
      this order: `OPTIMAL` → `OPTIMAL_PROVEN`; `INFEASIBLE` → `INFEASIBLE`;
      `deterministic_time ≥ 0.995 × D` → `DETERMINISTIC_BUDGET`;
      `wall_time ≥ 0.98 × backstop` → `WALL_CLOCK_BACKSTOP`; otherwise `OTHER`
    - Order matters — check `OPTIMAL` first. The `0.995` threshold reflects the measured overshoot
      (`7.0001` against a 7.0 budget)
    - `deterministic_stop` is `True` for the first three, `False` for the last two
    - Return `stop_reason`, `deterministic_stop`, `deterministic_time_used`,
      `deterministic_budget`, `wall_backstop_seconds` for the payload work in task 8
    - _Requirements: 2.4_

  - [x] 3.4 Unit tests for calibration and classification
    - Budget calibration `T → (D, backstop)` for every dropdown value at
      `templates/scheduler/scheduling.html:447-459`, including `RATIO` and `WALL_BACKSTOP_FACTOR`
      overrides, asserting `backstop == WALL_BACKSTOP_FACTOR × T` *(revised by the user's Option A
      decision — was "the backstop never exceeds `1.2 × T`"; see the superseded-bound table below)*
    - Table-driven stop-reason classification over `(status, deterministic_time, wall_time, D,
      backstop)` covering all five outcomes and the `0.995` / `0.98` boundaries
    - `test_stop_reason_is_deterministic_budget` — an open model reports
      `deterministic_stop is True` and `stop_reason == 'DETERMINISTIC_BUDGET'`
    - `test_wall_backstop_is_flagged` — `override_settings` with a tiny `WALL_BACKSTOP_FACTOR` so
      the backstop binds; assert `deterministic_stop is False` and
      `stop_reason == 'WALL_CLOCK_BACKSTOP'`. Proves the flag fires rather than being dead code
    - `test_wall_time_stays_inside_the_configured_backstop` — total wall time ≤ `backstop`, and
      `backstop == WALL_BACKSTOP_FACTOR × T` *(revised by the user's Option A decision — renamed
      from `test_wall_time_within_tolerance`, which asserted `≤ time_limit_seconds × 1.2`)*
    - Independently runnable: `python manage.py test scheduler.tests.test_determinism`
    - _Requirements: 2.4, 3.9_

  - [x] 3.5 Verify the repeat-run harness now passes
    - **Property 1: Expected Behavior** - Repeated runs return one schedule
    - **IMPORTANT**: Re-run the SAME tests from task 1 — do NOT write new tests
    - Run `test_repeat_runs_yield_one_schedule_hash` and, with `IDRS_TEST_CPU_LOAD=1`,
      `test_repeat_runs_under_cpu_load`
    - **EXPECTED OUTCOME**: PASS — one distinct `schedule_hash`, and `deterministic_time` now
      constant to within the 0.995 overshoot, matching the design's target measurement
      (`7.0001` every run while wall time varied 8.85-8.97 s)
    - If drift remains, apply design decision 2's ladder in order, re-testing at each rung and
      recording which rung was needed: (1) `interleave_batch_size` already pinned in 3.2,
      (2) `use_lns = False`, (3) `interleave_search = False`. Do not skip rungs — each costs
      solution quality
    - The tie-enumeration test from task 1 is still expected to FAIL here; task 4 closes it
    - _Requirements: Property 1 (validates 2.1, 2.2, 2.3), 2.12_

  - [x] 3.6 Verify preservation goldens still pass
    - **Property 2: Preservation** - Unique proven optima are untouched
    - **IMPORTANT**: Re-run the SAME tests from task 2 — do NOT write new tests
    - **EXPECTED OUTCOME**: PASS. Proven-optimal models, performance mode and locked actuals all
      match the goldens captured from the pre-fix code
    - _Requirements: 3.1, 3.4, 3.8, 3.9, 3.12_

### Task 3 results

Production files touched: **`drilling_scheduler/settings.py`** and **`scheduler/optimization.py`**,
nothing else (`git status`). The `optimization.py` diff is four hunks: the settings/calibration/
classification block at module level, two instance attributes (`solver_budget`,
`stop_classification`), `_configure_solver_for_determinism`, and one
`_record_stop_classification(...)` call in each of `solve` and `solve_with_actuals`. **No
tie-break, ordering, objective, decision-strategy or two-stage change** — those are tasks 4-7.

**No parameter is derived from a measured wall time.** `calibrate_solver_budget(T, deterministic)`
takes the selected limit and nothing else; there is no clock, no solver and no elapsed time
reachable from it. Asserted, not just intended, by
`test_calibration_is_a_pure_function_of_the_selected_limit` and
`test_calibration_needs_no_solver_and_no_measurement` (the latter reads the signature and fails if
`solver` / `elapsed` / `remaining` / `wall_time` / `started_at` is ever added).

#### Settings in force

| key | value | why |
|---|---|---|
| `DETERMINISTIC_TIME_RATIO` | **0.60** | search quality — see the rejected 0.15 experiment below |
| `WALL_BACKSTOP_FACTOR` | **1.5** | sized from the contention measurement below |
| `CANONICALIZE_BUDGET_SHARE` | 0.15 | untouched, task 4 consumes it |
| `FIXED_SEARCH` | False | design decision 2 rung 4, not needed |

`interleave_batch_size` is **pinned to 1** (`DETERMINISTIC_INTERLEAVE_BATCH_SIZE`), design decision
2 rung 1. Verified against the pinned `ortools==9.15.6755`: with `num_search_workers = 1` the solver
log already reads "Setting number of tasks in each batch of interleaved search to 1", so 1 is
exactly what the derivation produces today and pinning it changes no behaviour. What the pin buys is
that an OR-Tools upgrade can no longer change the batch size — and with it the search path, and with
it the schedule — silently: it is now a recorded parameter instead of an invisible default. **No
further rung of the ladder was needed**: `use_lns` stays `True` and `interleave_search` stays
`True`, so no solution quality was given up to get determinism.

#### The contention measurement that sized the backstop

Method: the task 1 model (`factories.build_hard_open_scenario()`, 6 rigs / 40 wells) at
`HARD_OPEN_TIME_LIMIT_SECONDS = 6` with `RATIO = 0.60`, so the work is a **fixed 3.6 units** at
every level. The backstop was opened wide (factor 20) for the measurement only, so the work budget
always fired and the wall time recorded is the honest cost of finishing that fixed work. Burner
counts are **absolute** (12-core host), 2 solves each, via the new `IDRS_TEST_CPU_LOAD_WORKERS`
override in `scheduler/tests/support.py`. Measured with a throwaway probe that has been deleted —
this is a calibration of the host, not a test that could pass anywhere else.

| burners | wall_s | deterministic_time | wall per unit | schedule_hash | wells | stop_reason |
|---|---|---|---|---|---|---|
| 0 | 5.77 | 3.6000 | 1.602 | `1a6136917eac05eb` | 23 | DETERMINISTIC_BUDGET |
| 0 | 5.81 | 3.6000 | 1.613 | `1a6136917eac05eb` | 23 | DETERMINISTIC_BUDGET |
| 2 | 5.77 | 3.6000 | 1.604 | `1a6136917eac05eb` | 23 | DETERMINISTIC_BUDGET |
| 2 | 5.80 | 3.6000 | 1.611 | `1a6136917eac05eb` | 23 | DETERMINISTIC_BUDGET |
| 4 | 6.03 | 3.6000 | 1.674 | `1a6136917eac05eb` | 23 | DETERMINISTIC_BUDGET |
| 4 | 5.93 | 3.6000 | 1.647 | `1a6136917eac05eb` | 23 | DETERMINISTIC_BUDGET |
| 8 | 6.60 | 3.6000 | 1.832 | `1a6136917eac05eb` | 23 | DETERMINISTIC_BUDGET |
| 8 | 6.49 | 3.6000 | 1.804 | `1a6136917eac05eb` | 23 | DETERMINISTIC_BUDGET |

Same hash, same 23 wells, `deterministic_time` **3.6000 to 4 dp at every level** — the work budget
is the limit that fires from idle up to 8 background burners, and the only thing load moves is the
elapsed time (+14 % at 8 burners).

#### Deriving `WALL_BACKSTOP_FACTOR = 1.5`

```
worst representative cost         = 1.832 s per deterministic unit   (8 burners)
wall needed for the fixed work    = 1.832 x D
                                  = 1.832 x RATIO x T
                                  = 1.832 x 0.60 x T   = 1.0992 x T
chosen factor                     = 1.5 x T            (~36 % headroom, clean round number)
covered cost per unit             = 1.5 / 0.60         = 2.50 s per unit
                                  = 1.56x this host's idle cost of 1.60 s
```

Sanity check at the page's default selection: **T = 300 s → backstop 450 s (7.5 min) worst case**,
with the expected finish around 300 x 1.10 = 330 s idle-to-moderately-busy. At T = 6 s the measured
run uses 5.89 s of a 9.00 s backstop (65 %), and the classifier's binding threshold is 0.98 x 9.00 =
8.82 s, so there is real margin before the amber path can trigger.

**Property 4's `1.2 x T` bound is superseded, deliberately.** A tight wall bound and same-machine
determinism under load are mutually exclusive: holding the *work* fixed means the *elapsed time* has
to absorb the contention. Determinism wins, per the user's requirement. Three assertions were
updated to match, and none of them was weakened into a tautology — each now pins the backstop to
`the configured WALL_BACKSTOP_FACTOR x T`, which is a stronger statement than "under 1.2 x T":

| test | was | now |
|---|---|---|
| `test_solver_budget.test_every_dropdown_value_calibrates_from_the_configured_factors` (renamed from `…_within_property_4`) | `backstop <= 1.2 x T` | `backstop == F x T` and `budget.wall_backstop_factor == F` |
| `test_solver_budget.test_overrides_are_honoured` (renamed from `…_and_still_bounded`) | override + `<= 1.2 x T` | override arithmetic only |
| `test_solver_budget.test_wall_time_stays_inside_the_configured_backstop` (renamed from `test_wall_time_within_tolerance`) | `wall_time <= 1.2 x T` | `wall_time <= backstop` **and** `backstop == F x T` |
| `test_preservation.assert_stop_criterion_parameters` | `max_time_in_seconds <= 1.2 x T` | `max_time_in_seconds == F x T` |

Added: `test_defaults_match_the_shipped_settings_block`, which asserts `settings.py` and
`optimization.py`'s `DETERMINISM_SETTING_DEFAULTS` agree on both keys. The defaults are duplicated
on purpose (so a settings module predating the block still works), and that duplication is exactly
how the two could silently disagree. The stop-reason tests were **not** touched.

#### 3.5 — the task 1 harness, before and after

`scheduler.tests.test_determinism`, re-run unchanged. `T = 6 s`, `D = 3.6` units.

| run set | schedule_hash | objective | wells | deterministic_time | wall_s |
|---|---|---|---|---|---|
| **BEFORE** idle x5 | `1a6136917eac05eb` | 97,768,602,348 | 23 | 3.4378 (spread 0.0000) | 5.85-5.99 |
| **AFTER** idle x5 | `1a6136917eac05eb` | 97,768,602,348 | 23 | **3.6000** (spread 0.0000) | 5.87-6.03 |
| **BEFORE** loaded (36 burners) | `92f12d9691802821` | 223,981,623,957 | **1** | 0.7595 / 0.8579 | ~6.0 |
| **AFTER** loaded (4 burners) | `1a6136917eac05eb` | 97,768,602,348 | 23 | **3.6000** (spread 0.0000) | 5.93 / 6.18 |
| **AFTER** loaded (8 burners) | `1a6136917eac05eb` | 97,768,602,348 | 23 | 3.4378 (spread 0.1622) | 7.19 / 7.42 |
| **AFTER** loaded (36 burners) | `c3c419ee932837aa` | 201,514,687,130 | **5** | 1.4364 (spread 2.1637) | 8.17 / 8.20 |

- **Idle: PASSES.** Same schedule as before the fix, now reached by a *work* budget rather than a
  clock. The answer did not move (still 23 wells, objective 97,768,602,348) while the work performed
  went from 3.4378 to 3.6000 units — the run now spends the whole budget instead of whatever the
  6-second clock happened to allow.
- **`IDRS_TEST_CPU_LOAD_WORKERS=4` (the level the factor was sized for): PASSES**, 3 idle + 2 loaded
  runs agreeing on one hash, one objective and `deterministic_time` identical to 4 dp. This is the
  case that failed on the unfixed code and it is the case the backstop is sized for.
- **8 burners: the business answer holds, the work-stability assertion does not.** Same hash, same
  objective, same 23 assignments; but the loaded runs stop at 3.4378 of the 3.6000 budget (95.5 %)
  and are classified `OTHER`, so the harness's `deterministic_time` spread check (1 % of the minimum)
  fails on a 0.1622 spread. Neither limit bound: wall 7.42 s is 82 % of the 9.00 s backstop, below
  the 0.98 threshold. CP-SAT stopped a little short of its own work budget under contention. The
  assertion was left as it is — this is a real, if narrow, gap between "same answer" and "same amount
  of search", and it belongs on the record rather than being tuned away.
- **36 burners (`IDRS_TEST_CPU_LOAD=1` default, 3 per core): FAILS, and this is the documented
  boundary of the guarantee.** At ~7.3 s per unit the fixed 3.6 units need ~26 s, far past the 9 s
  backstop, so the loaded runs stop at 1.4364 units and return `c3c419ee932837aa` with 5 wells. Two
  things worth stating precisely: the divergence is *smaller* than before the fix (5 wells rather
  than 1, and the two loaded runs agree with each other to 4 dp instead of differing), and the run is
  flagged — `deterministic_stop = False` — so it is visibly not-reproducible rather than silently
  wrong. The reason string is `OTHER` rather than `WALL_CLOCK_BACKSTOP` because the solve ended at
  8.20 s, 91 % of the backstop and under the 0.98 threshold. **`WALL_BACKSTOP_FACTOR` was
  deliberately not inflated to cover this level**: it is scoped to representative contention, and
  covering 3x-per-core oversubscription would mean a 4.4 x T backstop (22 minutes on the page's
  default 5-minute selection).

**The rejected alternative, recorded so it is not re-tried by accident.** `RATIO = 0.15` (D = 0.9
units) does make all five runs agree at the 36-burner torture level with `deterministic_time`
identical to 4 dp — and it collapses the answer to **1 well** assigned, objective 223,981,623,957,
against 23 wells at 0.60. Reproducibly returning a near-useless schedule is not the requirement.
0.60 is the deliberate choice and the backstop absorbs the load instead.

#### 3.6 — preservation

`scheduler.tests.test_preservation` — **8 of 8 pass**, without `IDRS_REGENERATE_GOLDEN` and without
the overwrite flag. Unique proven optimum still `698,525,729` / `0dcdf8e6ecc66b25`, performance mode
unchanged (clause 3.12: no work budget, `max_time_in_seconds = max(1, int(T))`), locked actuals
still pinned exactly. The fixture's drift report lists `drilling_scheduler/settings.py` and
`scheduler/optimization.py` as changed since capture, which is expected information — the goldens
still holding across that change *is* Property 2.

#### Suite status

`.venv/bin/python manage.py test scheduler.tests --keepdb` → **31 tests, 3 failures + 1 skip**, 86 s.
The three failures are exactly the counterexamples owned by later tasks, unchanged by task 3:

| test | documented in | owner |
|---|---|---|
| `test_exactly_one_schedule_attains_the_optimal_objective` — since renamed `test_the_canonical_set_matches_its_measured_size` | 1d — 4 tied schedules at `V*` | task 4.6 — closed by Option B |
| `test_duplicate_well_names_are_rejected_naming_the_duplicates` | 1e | task 6 |
| `test_ilm_days_do_not_depend_on_rule_insertion_order` | 1f — 2.0 vs 7.0 days | task 5.3 |

The skip is `test_repeat_runs_under_cpu_load`, gated on `IDRS_TEST_CPU_LOAD=1`.

#### How to re-run

```bash
.venv/bin/python manage.py test scheduler.tests.test_solver_budget --keepdb    # 17 tests, ~27 s
.venv/bin/python manage.py test scheduler.tests.test_determinism   --keepdb    # idle, passes
.venv/bin/python manage.py test scheduler.tests.test_preservation  --keepdb    # 8/8

# representative contention — the level WALL_BACKSTOP_FACTOR is sized for
IDRS_TEST_CPU_LOAD=1 IDRS_TEST_CPU_LOAD_WORKERS=4 .venv/bin/python manage.py test \
  scheduler.tests.test_determinism.RepeatRunDeterminismTests.test_repeat_runs_under_cpu_load --keepdb

# torture level (3 burners per core) — expected to fail, see the boundary note above
IDRS_TEST_CPU_LOAD=1 .venv/bin/python manage.py test scheduler.tests.test_determinism --keepdb
```

### Task 3 follow-on — `DETERMINISTIC_BUDGET_BINDING_FRACTION` 0.995 → 0.93

One constant, its comment, and the tests that pin it. `WALL_BACKSTOP_BINDING_FRACTION` (0.98) and the
classification precedence order are **untouched**. No tie-break, ordering, objective,
decision-strategy or two-stage change; no parameter derived from a measured wall time. Files touched:
`scheduler/optimization.py` and `scheduler/tests/test_solver_budget.py`.

**The false amber being fixed.** At 8 background burners (8 of 12 cores busy) all five runs returned
the *identical* schedule — hash `1a6136917eac05eb`, objective 97,768,602,348, 23 wells — but one
loaded run stopped at **3.4378 of its 3.6000 budget = 95.49 %**. That is under 0.995, and its wall
time (7.42 s) was under the 0.98 x 9.00 s backstop threshold, so it classified `OTHER` with
`deterministic_stop = False`: amber on a run that was in fact reproducible. See the 8-burner row in
the 3.5 table above, which recorded exactly this.

**Why 0.93 and not 0.95.** The observed short stop is at 95.49 %, so 0.95 leaves no margin and would
false-amber again on a slightly busier host. 0.93 has room underneath the observation.

**Why relaxing it is safe** (this reasoning is also in the comment on the constant):

- The single-solve `deterministic_stop` badge is **advisory**. It is a proxy for reproducibility, and
  one solve cannot prove reproducibility — that needs more than one run to compare.
- The **authoritative** check is the cross-run `schedule_hash` comparison in the `check_determinism`
  management command (task 10). Tasks 8.4 and 8.5 now carry a requirement that the badge and the
  warning say so in text.
- The two genuinely non-reproducible modes are caught by **separate** classifiers, neither of which
  depends on this threshold: a clock-cut run is caught by `WALL_BACKSTOP_BINDING_FRACTION` as
  `WALL_CLOCK_BACKSTOP`, and a genuinely divergent schedule is caught as a different `schedule_hash`.
- The `OTHER`/short-stop case this absorbs is a benign contention artefact: same hash, same 23 wells,
  CP-SAT simply stopping a hair short of its own work budget.

**Tests updated** (`test_solver_budget.StopReasonClassificationTests`) — the table now exercises the
0.93 boundary instead of 0.995 on a `BUDGET` of 10.0: at threshold (9.3) and just above (9.3001) →
`DETERMINISTIC_BUDGET`; just below (9.2999) → `OTHER`; just below **with the backstop bound** (9.2999
at wall 99.0) → `WALL_CLOCK_BACKSTOP`, which is the row that pins the fall-through the amber path
depends on; precedence row moved to 9.3 at wall 99.0 → `DETERMINISTIC_BUDGET`.
`test_the_two_thresholds_are_the_documented_ones` now asserts 0.93. Added
`test_the_measured_contention_short_stop_is_not_flagged`, pinned to the artefact rather than to a
round number: `det_time 3.4378`, `budget 3.6`, `wall 7.42`, `backstop 9.0` → `DETERMINISTIC_BUDGET`
with `deterministic_stop = True`.

#### Verification outcomes

| # | check | result |
|---|---|---|
| a | `test_solver_budget --keepdb` | **OK — 18 tests**, 25.5 s (17 + the new regression case) |
| b | `test_preservation --keepdb` | **OK — 8/8**, no `IDRS_REGENERATE_GOLDEN`, no overwrite flag |
| c | `test_wall_backstop_is_flagged` in isolation | **OK — amber path alive**, numbers below |
| d | 8-burner `test_repeat_runs_under_cpu_load` | **OK — all assertions pass**, twice; numbers below |
| e | `scheduler.tests --keepdb` | **32 tests, 3 failures + 1 skip** — the 3 owned by tasks 4-7 |

(b) drift report still lists `drilling_scheduler/settings.py` and `scheduler/optimization.py` as
changed since capture, which is expected information: the goldens holding across the change *is*
Property 2. Unique proven optimum still `698,525,729` / `0dcdf8e6ecc66b25`, 1 schedule attains `V*`,
enumeration exhausted.

**(c) The amber path is NOT dead — verified empirically, not by argument.** Run alone with
`WALL_BACKSTOP_FACTOR = 0.15`:

| field | value |
|---|---|
| `stop_reason` | **`WALL_CLOCK_BACKSTOP`** |
| `deterministic_stop` | **`False`** |
| `deterministic_time_used` | **0.7319** of budget 3.6000 = **20.3 %** |
| binding threshold now | 0.93 x 3.6000 = 3.348 — the run is far below it, so it falls through |
| `wall_time` | **0.90 s** of backstop 0.90 s = 100 %, past the 0.98 threshold (0.882 s) |

A second observation of the same test inside the full `test_solver_budget` run gave 0.7345 of 3.6000
(20.4 %) at wall 0.90 s, same classification. The genuine backstop hit spends ~20 % of its work
budget, nowhere near 0.93, so the relaxation cannot swallow it.

**(d) 8 burners — all five runs identical, and the short stop did not recur.** Two consecutive runs
of `IDRS_TEST_CPU_LOAD=1 IDRS_TEST_CPU_LOAD_WORKERS=8`, 3 idle + 2 loaded, `T = 6 s`, `D = 3.6`:

| run | load | status | schedule_hash | objective | det_time | wall_s | wells | stop_reason |
|---|---|---|---|---|---|---|---|---|
| 1 | N | FEASIBLE | `1a6136917eac05eb` | 97,768,602,348 | 3.6000 | 5.71 | 23 | DETERMINISTIC_BUDGET |
| 2 | N | FEASIBLE | `1a6136917eac05eb` | 97,768,602,348 | 3.6000 | 5.76 | 23 | DETERMINISTIC_BUDGET |
| 3 | N | FEASIBLE | `1a6136917eac05eb` | 97,768,602,348 | 3.6000 | 5.54 | 23 | DETERMINISTIC_BUDGET |
| 4 | **Y** | FEASIBLE | `1a6136917eac05eb` | 97,768,602,348 | 3.6000 | 6.03 | 23 | DETERMINISTIC_BUDGET |
| 5 | **Y** | FEASIBLE | `1a6136917eac05eb` | 97,768,602,348 | 3.6000 | 6.14 | 23 | DETERMINISTIC_BUDGET |

Second run: identical hash / objective / 23 wells / `det_time 3.6000` on all five, wall 5.64-6.56 s.
Both runs: distinct `schedule_hash` **1**, distinct `model_fingerprint` **1**, distinct
`objective_value` **1**, `deterministic_time` spread **0.0000**. **Every assertion passes**, including
the 1 %-of-minimum `deterministic_time` stability check that failed during task 3 — so the feared
4.5 % spread did not need to be tolerated and **no assertion was weakened**.

Stated precisely: on this occasion the 95.49 % short stop **did not reproduce**, so the relaxed
classification could not be observed live at 8 burners. The 3.4378-of-3.6000 observation from task
3.5 stands on the record, and it is what
`test_the_measured_contention_short_stop_is_not_flagged` pins deterministically — which is the
durable form of the check, since the live artefact is contention-dependent and does not appear on
demand.

- [x] 4. Fix — two-stage lexicographic solve for canonical tie-break selection (design decision 3)

  **⚠️ REVIEW REQUIRED — may change existing schedule output.** Stage 2 selects a canonical member
  of the tied optimal set, so requests with tied optima will return different assignments than
  today. The `objective_value` is preserved by construction (stage 1 is byte-identical to today's
  objective and stage 2 pins it as an equality), so clause 3.8 holds literally. Layered on top of
  task 3 and only after 3.5 and 3.6 pass.

  - [x] 4.1 Split the objective into P-expr and T-expr
    - `scheduler/optimization.py` — `set_objective` (`:1206-1430`)
    - Stage 1 minimises exactly the expression built today at `:1412-1428` with weights unchanged
      (`START_TIME_WEIGHT = RIG_WELL_ORDER_WEIGHT = 1`, `:1358-1359` — verified). No `num_pairs+1`
      weight anywhere in stage 1, so Big-M, the LP relaxation and the proof difficulty are untouched
      and the ~1.7 % gap of the previous attempt cannot recur
    - Expose T-expr = `W₁·start_time_sum + W₂·rig_well_order` with `W₂ = 1` and
      `W₁ = max(rig_well_order) + 1`
    - Correct `max_order_tiebreak` at `:1362` (verified: `RIG_WELL_ORDER_WEIGHT * num_pairs *
      num_pairs`) to the tight bound `num_wells × num_pairs` — each well contributes at most one
      active assignment — so Big-M is not padded unnecessarily and `W₁` is derived from the tight
      bound
    - Sanity-check the coefficient range: at ~30 wells / ~13 rigs (`num_pairs ≈ 390`),
      `W₁ ≈ 11 701` and the stage-2 objective maximum ≈ `1.8 × 10⁹` — inside int64 and far below the
      magnitudes that degrade CP-SAT's LP scaling
    - _Requirements: 2.5, 3.6_

  - [x] 4.2 Implement the stage-2 canonicalising solve
    - `scheduler/optimization.py` — `solve` (`:1688-1763`)
    - Stage 1 yields `V*`. On the same `CpModel`, `Add(P-expr == V*)` and replace the objective with
      `Minimize(T-expr)`. Locking the **full** objective (not tiers 1-3) means stage 2's feasible
      set is exactly the set today's solver may return arbitrarily — it can only replace an
      arbitrary choice with a canonical one, never change the economics
    - `AddHint` the stage-1 solution onto the assignment BoolVars and start-time IntVars so stage 2
      starts from a known feasible incumbent and its only work is improving the tie-break
    - Budget split: `D₁ = (1 − CANONICALIZE_BUDGET_SHARE) × D`, `D₂ = share × D`. Backstops
      `0.90 × WALL_BACKSTOP_FACTOR × T` and `0.25 × WALL_BACKSTOP_FACTOR × T` — both computed from
      `T`, **never** from remaining wall time (task 3.2's hard rule). The shares sum to `1.15 × T`,
      satisfying Property 4
    - Stage 2 need not prove optimality: its stop is deterministic, so its incumbent is reproducible
      either way. Report `canonicalization_status`
    - Skip stage 2 entirely when stage 1 returned neither `OPTIMAL` nor `FEASIBLE`, and when
      `deterministic=False` (clause 3.12)
    - Stage 2 must never worsen or lose a result — on stage-2 failure, return stage 1 intact
    - _Bug_Condition: `isBugCondition(X)` where `hasObjectiveTies` — more than one distinct schedule
      attains `minObj(X)`_
    - _Expected_Behavior: a single canonical schedule is selected from the tied set; `objective_value`
      equals stage 1's `V*`, i.e. today's value_
    - _Preservation: when the optimal set has one member, stage 2 cannot change anything — Property 2
      holds by construction_
    - _Requirements: 2.1, 2.5, 3.6, 3.8_

  - [x] 4.3 Route `solve_with_actuals` through the same two stages
    - `scheduler/optimization.py:1514-1573`
    - SEM re-optimization (`scheduler/sem_views.py:1125-1131`) and the locked-actuals path inherit
      the guarantee
    - Stage 2 must not move a pinned well; `fixed_actuals` stays sorted by `(well, rig)` (`:1527-1528`)
    - _Requirements: 3.10, 3.11_

  - [x] 4.4 Fix metric provenance in `_extract_solution`
    - `scheduler/optimization.py:1764-1922`
    - Reported metrics come from **stage 1**: `objective_value`, `best_bound`, `optimality_gap`,
      `solver_status`, `is_optimal`. These currently read `self.solver` at `:1793-1803`; they must
      read stage 1's captured values. Stage 2's objective is a tie-break index and is meaningless
      to the business — leaking it onto the detail page would show nonsense
    - Variable **values** come from stage 2 when stage 2 succeeded, otherwise stage 1. Capture
      stage 1's values into a plain dict before mutating the model, and give `_extract_solution` an
      optional value-lookup so it can extract from either source
    - Do **not** change `for (wid, rid), a in self.assignments.items()` at `:1807`. Dict insertion
      order is the canonical `(well, rig)` order and is load-bearing; add a comment saying so, since
      a future refactor to a set would silently reintroduce non-determinism
    - _Requirements: 3.8, 3.13_

  - [x] 4.5 Unit tests for the two-stage structure
    - Tie-break weight derivation: `W₁ > max(rig_well_order)` across a range of well/rig counts, and
      the stage-2 objective maximum stays inside a safe coefficient bound
    - Stage-2 fallback: inject a contradictory extra constraint to force stage 2 `INFEASIBLE`;
      assert the stage-1 solution is returned intact and `canonicalization_status` reports the failure
    - Stage-1 metric provenance: `objective_value`, `best_bound`, `optimality_gap` and
      `solver_status` in the payload come from stage 1, not stage 2
    - Budget monotonicity: a larger `time_limit_seconds` never produces a worse objective — catches
      a stage-split or calibration mistake that starves the search
    - _Requirements: 2.5, 3.6, 3.8_

  - [x] 4.6 Verify the tie-enumeration test now passes
    - **RESOLVED by user decision (Option B) — see "Task 4 results" below.** Measured after 4.1-4.5:
      the tied set at `P-expr == V*` is 4 (expected, stage 1 is unchanged) and the canonical set at
      `(P-expr == V*) AND (T-expr == T*)` is **also 4**, not 1. All four survivors share
      `start_time_sum = 160` and `rig_well_order = 22`, because both tie-break tiers are *sums* and
      the four schedules differ only by permuting equal-duration wells between identical rigs. The
      user accepted the four interchangeable survivors and **de-scoped canonical
      path-independence**: `bugfix.md` clause 2.5 was reworded (2.5, 2.5.1-2.5.3) to the delivered
      goal — reproducible, not canonical; residual **measured, not eliminated** — and the test now
      pins the measured count instead of asserting 1. The third tie-break tier was **not** added; it
      remains the designated escalation and is out of scope (clause 2.5.3).
    - **Property 1: Expected Behavior** - Repeated runs return one schedule
    - **IMPORTANT**: Re-run the SAME test from task 1 — do NOT write a new test
    - Solve stage 1 for `V*`, stage 2 for `T*`, then build a third model constrained to
      `P-expr == V*` **and** `T-expr == T*`, enumerate with `num_search_workers = 1`, and assert the
      distinct `schedule_hash` count equals `MEASURED_CANONICAL_SCHEDULE_COUNT` (amended clause
      2.5.2). The test method was renamed from
      `test_exactly_one_schedule_attains_the_optimal_objective` to
      `test_the_canonical_set_matches_its_measured_size` — same test, same scenario, same
      enumeration; only the name and the pinned target changed, because the old name asserted a
      claim the spec no longer makes
    - Also log the distinct count at `P-expr == V*` alone — expected > 1, that is the tied set — so
      the test documents what the canonicalisation is doing rather than just asserting a number
    - **EXPECTED OUTCOME**: PASS — canonical count **4** (the measured interchangeable-permutation
      residual), tied count 4, both enumerations exhausted, hierarchy real (`W1 = 51 > 50`)
    - Rigour preserved, canonicality de-scoped: the hierarchy assertion `W1 > max(rig_well_order)` is
      now asserted explicitly, a cap hit is still a failure (a capped count is only a lower bound),
      the tied count is still asserted > 1, and the canonical count is asserted for **equality** so
      a count above the constant is a regression and a count below it forces a deliberate revisit
      rather than a silent pass
    - _Requirements: Property 1 (validates 2.5, 2.5.1, 2.5.2), 2.12_

  - [x] 4.7 Verify preservation goldens still pass
    - **Property 2: Preservation** - Unique proven optima are untouched
    - **IMPORTANT**: Re-run the SAME tests from task 2 — do NOT write new tests
    - **EXPECTED OUTCOME**: PASS. This is the test that catches stage 2 changing an answer it should
      not touch — assignments **and** `objective_value` identical to the goldens
    - _Requirements: 3.6, 3.7, 3.8, 3.10, 3.11, 3.12, 3.13_

### Task 4 results — **COMPLETE**, 4.1-4.7 done, 4.6 closed by user decision (Option B)

**What stage 2 does, in one line:** it locks the full stage-1 objective as an equality
(`Add(P-expr == V*)`) and minimises only the tie-break expression, so it cannot change economics and
cannot touch a unique optimum. That sentence is also the opening of
`_prepare_canonical_stage`'s docstring in `scheduler/optimization.py`.

Production files touched: **`scheduler/optimization.py`** only (`drilling_scheduler/settings.py` was
not modified — `CANONICALIZE_BUDGET_SHARE` was already there from task 3 and is now consumed). Tests
touched: `scheduler/tests/test_two_stage.py` (new, 13 tests), `test_tie_enumeration.py` (the T\*
stage added per 4.6's own instructions), and two task-3 assertions that read stage 1's parameter
block and had to learn about the split (below — no golden value moved).

#### 4.6 — the canonical set is 4, and 4 is the accepted, measured answer

**Decision: Option B — accept the four interchangeable survivors and de-scope canonical
path-independence.** The user's requirement is *same rigs, wells, financial year and time limit, same
machine, same schedule every run*. That is met and measured: task 3's reproducible stop plus the
repeat-run harness, which passes idle **and** under representative load with one `schedule_hash`, one
`model_fingerprint`, one `objective_value` and a `deterministic_time` spread of **0.0000**. Separating
four interchangeable permutations would buy path-independence of the *choice*, not reproducibility,
and the user is not paying model complexity for it.

What was amended, and what deliberately was not:

| | |
|---|---|
| `bugfix.md` clause 2.5 | Reworded to the delivered goal — select a **reproducible** member via the dominating hierarchy in stage 2 plus the reproducible stop. New 2.5.1 (reproducible but not canonical, and why: both tiers are sums), 2.5.2 (residual **measured, not eliminated**, with the numbers), 2.5.3 (arc-order third tier is the **designated escalation**, out of scope now) |
| `bugfix.md` Introduction | New subsection *Reproducible versus canonical — measured, then decided*, parallel to the existing wall-time decision record. Nothing deleted; the pre-fix reproduction evidence (10 tied at 3244) stands as the measurement it always was |
| `bugfix.md` Verification Criteria | The "confirms exactly one schedule attains the optimal objective value" bullet **restated**, not dropped: the canonical count is measured and asserted against its known value with both enumerations exhausted, the count at `V*` alone stays > 1, and the hierarchy is asserted real |
| `design.md` | The clause-2.5 paragraph in *Requirement conflict to resolve before implementation* converted from "say so and I will return to the requirements phase" into the decision record, with the measured numbers. Decision 3's stage-2 description and decision 8's tie-enumeration description no longer promise 1. Root cause 4 and the *Examples* line updated to match. Property 1 gained an explicit note that it is a repeatability claim and is unchanged in strength |
| `design.md` Property 1 | Accurate as written and left at full strength — byte-identical output on repeated runs on the same machine is still guaranteed; canonical selection was never part of it |
| **Not** amended | The tie-break hierarchy must still be real, the enumeration must still be exhaustive, and stage 2 must still never worsen a result. This de-scopes canonicality, **not** rigour |

The enumeration measures both points 4.6 specifies:

| measured at | count | value | schedule_hash values |
|---|---|---|---|
| `P-expr == V*` (the tied set) | **4** | `V* = 218,583,260` | `0b236ee41210272d`, `21eab6f2022716e3`, `2659d0ba8a8fc116`, `8fa867e67fbbd0bd` |
| `P-expr == V*` **AND** `T-expr == T*` (the canonical selection) | **4** — pinned as the measured value | `T* = 8,182` | the same four |

Both enumerations **exhausted** (terminated `INFEASIBLE`, 50-cap not reached), so 4 is exact, not a
lower bound. The tied set staying at 4 is expected and correct — stage 1's objective is unchanged.
The canonical set staying at 4 is the **residual**, and it is inseparable by any sum-based tier.

**Why, measured rather than argued.** All four survivors have *identical* tie-break components:
`start_time_sum = 160` and `rig_well_order = 22` on every one of them. `W1 = 51`, `W2 = 1`, and
`W1 > max(rig_well_order) = 50` holds, so the hierarchy is real — it just has nothing to bite on.
The four schedules differ only by **permuting interchangeable wells**, and both tie-break tiers are
**sums**, which are invariant under exactly that:

```
#0  RIG-01: W3@0, W4@40, W5@80   RIG-02: W2@0,  W1@40
#1  RIG-01: W5@0, W4@40, W3@80   RIG-02: W1@0,  W2@40
#2  RIG-01: W3@0, W4@40, W5@80   RIG-02: W1@0,  W2@40
#3  RIG-01: W5@0, W4@40, W3@80   RIG-02: W2@0,  W1@40
```

Every well has duration 30 and every rig is identical, so swapping two wells between the two start
slots on one rig leaves `start_time_sum` unchanged, and swapping two wells between the two rigs
leaves the *sum* `Σ (well_index × num_rigs + rig_index)` unchanged as well. No linear objective built
from these two sums can separate them — this is design root cause 4 ("two schedules that swap
equal-duration wells between two identical rigs can agree on … `start_time_sum` *and*
`rig_well_order`") reproduced exactly, now with the numbers.

**No sum-based tier can separate these four.** That is the load-bearing point behind the decision:
the residual is not a weight that needs raising, it is the wrong *shape* of tie-break. Any tier of the
form "sum some per-pair index over the selected pairs" is invariant under exactly the permutation that
distinguishes these schedules, so raising `W1`, adding a third *sum*, or tightening Big-M would all
change nothing here.

**The third tier remains the designated escalation, and stays out of scope.** An arc-order index over
`circuit_arcs` (design decision 3) is order-sensitive rather than a sum over selected pairs, so it
*is* the mechanism that could separate these four. It was **not** added: it changes which schedule the
business gets, and the user chose not to pay for path-independence they do not need. Clause 2.5.3
records it as the escalation for a future non-symmetric model whose canonical count exceeds its pinned
value for reasons interchangeable permutations do not explain.

**The test now pins the measured count.** `scheduler/tests/test_tie_enumeration.py` —
`MEASURED_CANONICAL_SCHEDULE_COUNT = 4`, a named module constant with the mechanism recorded in its
comment, asserted for **equality**. Above 4 is a regression; below 4 means canonicalisation improved
and the constant must be revisited deliberately with the new number recorded in the spec, not
satisfied silently by a looser comparison. Everything strict about the old test survived, and one
assertion was **added**:

| assertion | state |
|---|---|
| canonical count | `== MEASURED_CANONICAL_SCHEDULE_COUNT` (4), was `== 1` |
| tied count at `V*` alone | **now asserted** `> 1`, was only reported — so the test still documents what stage 2 chooses within |
| both enumerations exhausted | unchanged — a 50-cap hit is still a **failure**, because a capped count is only a lower bound and cannot be compared for equality |
| tie-break hierarchy real | **new** — `W1 > max(rig_well_order)` via the production `tiebreak_weights` / `max_rig_well_order` helpers, so a passing count can never be an artefact of a collapsed hierarchy |
| printed report | unchanged, plus the weights line |

Measured on the re-run: `W1 = 51`, `W2 = 1`, `max(rig_well_order) = 50`, hierarchy real.

What production does on this model, for the record: stage 1's incumbent is already at `T* = 8,182`, so
stage 2 returns `ALREADY_CANONICAL` and keeps stage 1's answer (`21eab6f2022716e3`). Which of the four
that is remains decided by the search path, not by the objective — reproducible on this machine
(task 3's deterministic stop), but not canonical. That is exactly what amended clause 2.5.1 now says.

**Big-M padding precedence call: user confirmed correct.** The authorised `max_order_tiebreak`
correction stays **unapplied** to `BIG_M_WELLS`, with its measurement comment in place
(`scheduler/optimization.py`, `max_rig_well_order`'s docstring and the `max_order_tiebreak` comment).
Tightening it moves the preservation golden's `objective_value` from 698,525,729 to 698,525,679 and
changes the model fingerprint — a 4.7 failure and a gate-5 violation — to buy only solve speed. The
tight bound *is* used where it matters, deriving `W1`. Tightening Big-M stays available as the
separate work design decision 3 flags it as.

#### 4.7 — preservation: 8/8, no golden moved

`scheduler.tests.test_preservation --keepdb` → **8 of 8 pass**, without `IDRS_REGENERATE_GOLDEN` and
without the overwrite flag. Unique proven optimum still `698,525,729` / `0dcdf8e6ecc66b25`, still
exactly 1 schedule attaining `V*` (enumeration exhausted); locked actuals still `710,225,835` /
`ade2afa77882d02e` with every pin held exactly; performance mode unchanged. Preservation holds *by
construction* here, and the mechanism is visible in the numbers: with one member in the optimal set,
stage 2 has nothing to choose between, reports `ALREADY_CANONICAL` and adopts nothing.

Two assertions in the existing tests had to be told about the stage split. **Both are observation
helpers reading stage 1's parameter block; no golden value was touched and none moved:**

| assertion | was | now |
|---|---|---|
| `test_preservation.assert_stop_criterion_parameters` | `max_deterministic_time == RATIO x T` (6.0), `max_time_in_seconds == FACTOR x T` (15.0 at T=10) | stage 1's shares — `0.85 x 0.60 x T = 5.1` and `0.85 x 1.5 x T = 12.75` — **plus** new assertions that `D1 + D2 == D` and the two backstops sum to exactly `FACTOR x T` |
| `test_solver_budget.test_wall_time_stays_inside_the_configured_backstop` | in-force backstop `== 1.5 x T` (9.0) | stage 1's `7.65`, **plus** the shares summing to `9.00`, **plus** stage-1 wall + stage-2 wall `<= 9.00` |

Neither is a relaxation: each gained the sum-to-the-whole check it previously did not need, so the
total ceiling Property 4 bounds is now pinned as well as each share. The reason the change was
needed at all is metric provenance: `self.solver` deliberately keeps holding **stage 1's**
parameters and counters, so the recorded block is stage 1's, and stage 1 carries `D1`, not `D`.

#### Wall-split arithmetic (from `T` and settings only — never from elapsed time)

```
D   = DETERMINISTIC_TIME_RATIO x T        = 0.60 x T
D2  = CANONICALIZE_BUDGET_SHARE x D       = 0.15 x D
D1  = D - D2                              = 0.85 x D      (subtraction, so D1 + D2 == D exactly)

backstop      = WALL_BACKSTOP_FACTOR x T  = 1.5 x T
stage 2 wall  = 0.15 x 1.5 x T            = 0.225 x T
stage 1 wall  = 1.5 x T - 0.225 x T       = 1.275 x T
                                          -> shares sum to EXACTLY 1.0 x 1.5 x T
```

The design's own decision-1 numbers, not task 4.2's stale "0.90 / 0.25 summing to 1.15" line: 0.85 /
0.15 summing to **exactly** `1.0 x FACTOR x T` is what Property 4 bounds, and a split summing above
the factor would let the two stages together overrun the stated ceiling. At `T = 6 s`: `D1 = 3.06`,
`D2 = 0.54`, backstops `7.65 s` + `1.35 s` = `9.00 s`. Measured on the 6-rig / 40-well model: stage 1
`4.87 s` of `7.65 s` (64 %), stage 2 `0.76 s` of `1.35 s`, total `5.63 s` of `9.00 s` (63 %).

`calibrate_two_stage_budgets(T, deterministic)` takes the selected limit and nothing else — no
solver, no clock, no elapsed or remaining time is reachable from it. Asserted, not intended, by
`test_two_stage.test_the_split_cannot_see_a_clock` (signature inspection plus equality of two calls),
and the exact-sum property by `test_the_two_wall_shares_sum_to_exactly_the_configured_factor` and
`test_the_two_work_shares_sum_to_exactly_the_whole_budget` across all 12 dropdown values.

#### `canonicalization_status` semantics

Published in the result payload as `canonicalization_status`. Stage 2's objective **value** is
deliberately absent from the payload: it is a tie-break index and means nothing to the business.

| status | stage 2 | schedule returned |
|---|---|---|
| `CANONICAL_OPTIMAL` | closed — tie-break minimum proven | **stage 2's** (canonical) |
| `CANONICAL_INCUMBENT` | improved the tie-break, did not prove the minimum | **stage 2's** (reproducible, not provably canonical) |
| `ALREADY_CANONICAL` | ran, found nothing better | stage 1's |
| `SKIPPED_PERFORMANCE_MODE` | not attempted — `deterministic=False`, clause 3.12 | stage 1's |
| `SKIPPED_NO_STAGE_1_SOLUTION` | not attempted — stage 1 was neither `OPTIMAL` nor `FEASIBLE` | stage 1's (i.e. none) |
| `SKIPPED_NO_EXPRESSIONS` | not attempted — `set_objective` published no P-expr / T-expr | stage 1's |
| `FAILED_INFEASIBLE` | returned `INFEASIBLE` | stage 1's, intact |
| `FAILED_NO_SOLUTION` | returned no solution | stage 1's, intact |
| `FAILED_EXCEPTION` | raised | stage 1's, intact |

The last six are grouped as `CANONICALIZATION_STAGE_ONE_PRESERVED`: in every one of them the caller
receives stage 1's schedule unchanged. Stage 2 can never worsen or lose a result — it holds its own
`CpSolver`, only ever *adds* the `P-expr == V*` equality and swaps the objective, and its values are
adopted only when `tiebreak_after < tiebreak_before`. `test_two_stage` forces the `INFEASIBLE` path
(by injecting an unsatisfiable `project_end == horizon + 1` at the `_prepare_canonical_stage` seam,
after the real preparation has run) and compares the returned payload against stage 1's **captured
variable snapshot**, not against a second solve.

#### What 4.1-4.5 actually changed

- **4.1** — `set_objective` now publishes `primary_objective_expr` (P-expr, byte-identical to
  today's: `START_TIME_WEIGHT = RIG_WELL_ORDER_WEIGHT = 1`, same terms, same order, same weights) and
  `tiebreak_objective_expr` (T-expr = `W1 x start_time_sum + W2 x rig_well_order`), plus
  `rig_well_order_index` so the tie-break value can be evaluated for a captured solution without a
  solver. `W1 = max_rig_well_order(num_wells, num_rigs) + 1` uses the **tight** bound
  `num_wells x num_pairs`, not `num_pairs x num_pairs`.
  **The authorised `max_order_tiebreak` correction was deliberately NOT applied to Big-M**, and this
  is the one place task 4 diverges from the letter of its instructions. `max_order_tiebreak` at that
  line is a coefficient of `BIG_M_WELLS` and therefore of **stage 1's objective**, which the same
  instruction requires to stay byte-identical. Measured: tightening it moves the preservation
  golden's `objective_value` from `698,525,729` to `698,525,679` and changes the model fingerprint —
  a 4.7 failure and a gate-5 violation, for a Big-M padding change that buys only solve speed. The
  tight bound *is* used where it matters (deriving `W1`); the padding is left alone with a comment
  recording the measurement, and tightening Big-M stays available as the separate work design
  decision 3 already flags it as.
- **4.2** — `_run_two_stage_solve` / `_resolve_canonicalization` / `_canonicalize_stage_one_solution`
  / `_prepare_canonical_stage`. Stage 1's solution is `AddHint`-ed onto the assignment BoolVars and
  the start-time IntVars (hints emitted in dict insertion order, which is the canonical `(well, rig)`
  order and part of the proto). Both stage protos are fingerprinted: `model_fingerprint` (stage 1,
  taken before the mutation, so it stays the fingerprint of the model whose objective value is
  reported) and `model_fingerprint_stage_two`.
- **4.3** — `solve_with_actuals` routes through the same `_run_two_stage_solve`, so SEM
  re-optimization and the locked-actuals endpoint inherit it; `fixed_actuals` still sorted by
  `(well, rig)` first. A pin is a hard constraint on the model *both* stages solve, so stage 2 cannot
  move it — asserted directly by
  `test_two_stage.test_stage_two_does_not_move_a_pinned_actual`, and by the 4.7 goldens.
- **4.4** — `_extract_solution` takes an optional `value_lookup` (`{var index: value}`). Metrics
  (`objective_value`, `best_bound`, `optimality_gap`, `solver_status`, `is_optimal`) come from
  `stage_one_metrics`, captured **before** the model is mutated; variable *values* come from stage 2
  only when it was adopted. `for (wid, rid), a in self.assignments.items()` is unchanged and now
  carries a comment saying the dict insertion order **is** the canonical `(well, rig)` order and is
  load-bearing.
- **4.5** — `scheduler/tests/test_two_stage.py`, **13 tests, all pass** (1.7 s): `W1` dominating the
  independently-derived attainable `rig_well_order` maximum across 8 well/rig shapes; the bound being
  the tight one; the stage-2 objective maximum inside `2**62` (and the design's `W1 = 11,701` /
  `~1.8 x 10**9` worked example reproduced); the exact wall-share and work-share sums across all 12
  dropdown values; the split's signature carrying no clock; performance mode having no second stage;
  a forced-`INFEASIBLE` stage 2 returning stage 1 intact with `FAILED_INFEASIBLE`; performance mode
  reporting `SKIPPED_PERFORMANCE_MODE`; stage-1 metric provenance (payload objective equals an
  independently recomputed `V*`, and no tie-break quantity appears in the payload); both stage protos
  fingerprinted and distinct; budget monotonicity across 10 / 20 / 30 s.

#### Determinism re-check (task 3's harness, re-run unchanged)

`T = 6 s`. Stage 1's work budget is now `D1 = 3.0600` where the single-stage code had `D = 3.6000` —
the split is visible here and **the answer did not move**: same hash, same objective, same 23 wells.

| run | load | status | schedule_hash | objective | wells | det_time | wall_s | stop_reason |
|---|---|---|---|---|---|---|---|---|
| 1-5 | N (idle) | FEASIBLE | `1a6136917eac05eb` | 97,768,602,348 | 23 | 3.0600 | 4.90-4.93 | DETERMINISTIC_BUDGET |
| 1-3 | N | FEASIBLE | `1a6136917eac05eb` | 97,768,602,348 | 23 | 3.0600 | 4.55-4.81 | DETERMINISTIC_BUDGET |
| 4-5 | **Y** (4 burners) | FEASIBLE | `1a6136917eac05eb` | 97,768,602,348 | 23 | 3.0600 | 4.86 / 4.93 | DETERMINISTIC_BUDGET |

Both runs: distinct `schedule_hash` **1**, distinct `model_fingerprint` **1**, distinct
`objective_value` **1**, `deterministic_time` spread **0.0000**. Total wall (both stages) ~5.7 s of
the 9.00 s ceiling.

#### Suite status

`.venv/bin/python manage.py test scheduler.tests --keepdb` → **45 tests, 2 failures + 1 skip**, 84 s
(was 45 tests / 3 failures before the 2.5 amendment; 32 tests / 3 failures before task 4).

| test | documented in | owner |
|---|---|---|
| `test_duplicate_well_names_are_rejected_naming_the_duplicates` | 1e | task 6 — leave failing |
| `test_ilm_days_do_not_depend_on_rule_insertion_order` | 1f — 2.0 vs 7.0 days | task 5.3 — leave failing |

`test_the_canonical_set_matches_its_measured_size` (renamed from
`test_exactly_one_schedule_attains_the_optimal_objective`) now **PASSES**. Both remaining failures are
owned by later tasks and were not touched. The skip is `test_repeat_runs_under_cpu_load`, gated on
`IDRS_TEST_CPU_LOAD=1`.

#### Closing verification for task 4 (all re-run after the 2.5 amendment)

| # | command | result |
|---|---|---|
| 1 | `test_tie_enumeration --keepdb` | **PASS** (1 test, 0.65 s). `V* = 218,583,260`, `T* = 8,182`, `W1 = 51 > 50`. Tied set **4**, exhausted **True**. Canonical set **4**, exhausted **True**. Both hash lists identical: `0b236ee41210272d`, `21eab6f2022716e3`, `2659d0ba8a8fc116`, `8fa867e67fbbd0bd` |
| 2 | `test_preservation --keepdb` | **8/8 PASS** (0.75 s), no `IDRS_REGENERATE_GOLDEN`, no overwrite flag. Unique proven optimum `698,525,729` / `0dcdf8e6ecc66b25`, exactly 1 schedule attaining `V*`, enumeration exhausted. Locked actuals `710,225,835` / `ade2afa77882d02e` |
| 3 | `test_determinism --keepdb` (idle) | **PASS** (2 tests, 1 skipped, 55.6 s). 5 idle runs @ `T = 6 s`: hash `1a6136917eac05eb`, objective `97,768,602,348`, **23** wells, `det_time` `3.0600` on every run (spread `0.0000`), wall `4.80-4.85 s`, `stop_reason = DETERMINISTIC_BUDGET`. Distinct hash / fingerprint / objective all **1** |
| 4 | `IDRS_TEST_CPU_LOAD=1 IDRS_TEST_CPU_LOAD_WORKERS=4 … test_repeat_runs_under_cpu_load --keepdb` | **PASS** (59.6 s, 4 burners established). 3 idle + 2 loaded, all five: hash `1a6136917eac05eb`, objective `97,768,602,348`, 23 wells, `det_time 3.0600`, `DETERMINISTIC_BUDGET`; wall `4.83 / 4.80 / 4.84` idle and `4.74 / 4.93` loaded. Spread `0.0000` |
| 5 | `scheduler.tests --keepdb` (full) | **45 tests, 2 failures, 1 skip**, 84 s — only the two later-task failures above |

The under-load table, in full:

| run | load | status | schedule_hash | objective | wells | det_time | wall_s | stop_reason |
|---|---|---|---|---|---|---|---|---|
| 1 | N | FEASIBLE | `1a6136917eac05eb` | 97,768,602,348 | 23 | 3.0600 | 4.83 | DETERMINISTIC_BUDGET |
| 2 | N | FEASIBLE | `1a6136917eac05eb` | 97,768,602,348 | 23 | 3.0600 | 4.80 | DETERMINISTIC_BUDGET |
| 3 | N | FEASIBLE | `1a6136917eac05eb` | 97,768,602,348 | 23 | 3.0600 | 4.84 | DETERMINISTIC_BUDGET |
| 4 | **Y** | FEASIBLE | `1a6136917eac05eb` | 97,768,602,348 | 23 | 3.0600 | 4.74 | DETERMINISTIC_BUDGET |
| 5 | **Y** | FEASIBLE | `1a6136917eac05eb` | 97,768,602,348 | 23 | 3.0600 | 4.93 | DETERMINISTIC_BUDGET |

That table is the evidence Option B rests on: the user's requirement — same inputs, same machine, same
schedule every run — holds with load varying, which is what makes the four-way canonical residual an
acceptable, measured artefact rather than an open defect.

#### How to re-run

```bash
.venv/bin/python manage.py test scheduler.tests.test_two_stage       --keepdb   # 13 tests, ~2 s
.venv/bin/python manage.py test scheduler.tests.test_tie_enumeration --keepdb   # 1 test, canonical == 4
.venv/bin/python manage.py test scheduler.tests.test_preservation    --keepdb   # 8/8
.venv/bin/python manage.py test scheduler.tests.test_solver_budget   --keepdb   # 18 tests
.venv/bin/python manage.py test scheduler.tests.test_determinism     --keepdb   # idle

IDRS_TEST_CPU_LOAD=1 IDRS_TEST_CPU_LOAD_WORKERS=4 .venv/bin/python manage.py test \
  scheduler.tests.test_determinism.RepeatRunDeterminismTests.test_repeat_runs_under_cpu_load --keepdb
```

- [x] 5. Fix — ordering hardening (design decision 6)

  **⚠️ REVIEW REQUIRED — may change existing schedule output.** Replaces ties currently resolved by
  the database or by an unstable sort with total orderings. Output can change on inputs that have
  duplicate well names, tied `RigBuildingAdjustment` rows, or overlapping `WellPairDistance` rows.

  - [x] 5.1 Total orderings on the querysets
    - `.order_by('name', 'id')` at `scheduler/views.py:1911-1912` (verified at `:1910-1911`) — the
      `/scheduling/` path
    - `scheduler/views.py:1717-1718` — `run_full_optimization`. Note this function is **dead**: it
      calls `rig.to_dict()` / `well.to_dict()` (`:1719-1720`) which do not exist on the models, and
      nothing in the app calls it. Harden for consistency with clause 3.2 but do not treat it as a
      live path
    - `scheduler/views.py:2422-2423`, `:2506`, `:2520`, `:2976-2977`, `:3112-3113`, `:3175-3176` —
      the re-optimize, reschedule and add/delete-well paths
    - `('name', 'id')` is specified because clause 2.8 names it and `id` is present in every
      `.values()` payload the optimizer receives (`Well.sn` at `models.py:383` would be equally
      total and more legible — noted, not chosen)
    - _Requirements: 2.8, 3.2_

  - [x] 5.2 Stable, total pandas sorts
    - `scheduler/optimization.py:686-687` (verified) — sort on `["name", "id"]` when `id` is present,
      with `kind="stable"`, then `reset_index(drop=True)`
    - `kind="stable"` alone is **not** sufficient: a stable sort preserves the input order of tied
      rows, so it only helps when the input order is already total. The `id` column is what makes
      the key total; the stable kind covers frames arriving without it
    - Preserves the existing ordering fix at `:686-693` rather than replacing it (clause 3.1)
    - _Requirements: 2.8, 3.1_

  - [x] 5.3 `RigBuildingAdjustment` rule ordering
    - `.order_by('-priority', 'category', 'id')` — `calculate_ilm_days` applies the first matching
      `replace` rule and then sets `base_replaced = True` (`scheduler/views.py:10831-10839`), so row
      order decides the ILM value
    - `scheduler/views.py:10791` — the non-prefetched branch inside `calculate_ilm_days`
    - `scheduler/views.py:11087` — the bulk ILM refresh that prefetches the rules
    - `scheduler/models.py:737`, `:816`, `:881`, `:952` — the same pattern in the model-side helpers
      that populate `WellPairDistance`'s cached ILM values. These feed the numbers the optimizer
      reads at `optimization.py:781-790`, so leaving them unordered keeps the hazard alive one layer
      down
    - _Requirements: 2.10_

  - [x] 5.4 `WellPairDistance` fetch order and assignment-list sort keys
    - `scheduler/optimization.py:781-783` — add `.order_by('well_1__name', 'well_2__name', 'id')`.
      The queryset is unordered and each row writes both directions into `distance_cache`
      (`:789-790`), so overlapping rows overwrite each other in database order. The filter is
      `rig=rig_obj` with no location predicate, which is why overlaps are possible at all
    - `scheduler/optimization.py:2243` —
      `arr.sort(key=lambda x: (x["well_start_date"], x["well"]))`
    - `scheduler/views.py:1997` and `:3268` — same total key for the `sequence_order` derivation.
      Cheap, and removes a latent hazard even though per-rig `AddNoOverlap` makes same-rig
      start-date ties impossible today
    - _Requirements: 2.10, 3.13_

  - [x] 5.5 Verify ordering invariance and preservation
    - **Property 2: Preservation** - Unchanged behaviour is preserved
    - Re-run the task 2 goldens and the task 1 repeat-run harness
    - Add `scheduler/tests/test_ordering.py` cases: two `RigBuildingAdjustment` rows with equal
      `priority` and `category` → `calculate_ilm_days` returns the same value regardless of
      insertion order and the applied rule is the lower `id`; two `WellPairDistance` rows covering
      the same name pair → the ILM matrix value is stable across repeated
      `_calculate_ilm_days_matrix()` calls
    - **EXPECTED OUTCOME**: goldens PASS, new ordering tests PASS
    - _Requirements: Property 5 (validates 2.8, 2.10), 3.1, 3.2_

### Task 5 results — **COMPLETE**, 5.1-5.5 done

Production files touched: **`scheduler/views.py`** (first production change to this file in the
spec), **`scheduler/models.py`** (first change), **`scheduler/optimization.py`**. Tests touched:
`scheduler/tests/test_ordering.py` (3 new tests + 1 new assertion pair), `factories.py` (pinned
primary keys and a new overlap builder), `support.py` (the `sequence_order` replica tracks the new
production key). No migration, no settings change, no scratch file.

Line numbers in the task text were checked and were still accurate for `views.py` and `models.py`
(neither had been touched by tasks 3-4); `optimization.py`'s had all shifted by ~450-1050 lines, so
every site there was located by symbol name.

#### Sites changed, by file and symbol

| # | File | Symbol / location | Before | After |
|---|---|---|---|---|
| 1 | `views.py` | `run_full_optimization` (**dead** — calls `rig.to_dict()` / `well.to_dict()`, which do not exist; nothing invokes it) | `.order_by('name')` x4 | `.order_by('name', 'id')` x4 |
| 2 | `views.py` | `ScheduleViewSet.create_schedule` — the `/scheduling/` rig+well querysets feeding the optimizer | `.order_by('name')` x2 | `.order_by('name', 'id')` x2 |
| 3 | `views.py` | `create_schedule` save path — per-rig `sequence_order` derivation | `sort(key=lambda x: x['well_start_date'])` | `sort(key=lambda x: (x['well_start_date'], x['well']))` |
| 4 | `views.py` | locked-actuals persist path — `rigs_by_name` / `wells_by_name` lookups | `.order_by('name')` x2 | `.order_by('name', 'id')` x2 |
| 5 | `views.py` | locked-actuals path — `wells_df` / `rigs_df` for `WellRejectionAnalyzer` | `.order_by('name')` x2 | `.order_by('name', 'id')` x2 |
| 6 | `views.py` | re-optimize-after-delete — `all_wells_except_deleted` / `all_rigs` | `.order_by('name')` x2 | `.order_by('name', 'id')` x2 |
| 7 | `views.py` | add-well-and-reoptimize — `wells_in_schedule` / `rigs_in_schedule` | `.order_by('name')` x2 | `.order_by('name', 'id')` x2 |
| 8 | `views.py` | reschedule — `rigs_data` / `wells_data` `.values()` conversion | `.order_by('name')` x2 | `.order_by('name', 'id')` x2 |
| 9 | `views.py` | reschedule save path — per-rig `sequence_order` derivation | `sort(key=lambda x: x['well_start_date'])` | `sort(key=lambda x: (x['well_start_date'], x['well']))` |
| 10 | `views.py` | `calculate_ilm_days` — non-prefetched rule branch | `.order_by('-priority', 'category')` | `.order_by('-priority', 'category', 'id')` |
| 11 | `views.py` | `refresh_ilm_cache_for_location` — bulk ILM refresh, prefetched rules | `.order_by('-priority', 'category')` | `.order_by('-priority', 'category', 'id')` |
| 12 | `models.py` | `WellPairDistance.calculate_distances_for_location` (the `try: from scheduler.views import calculate_ilm_days` prefetch) | `.order_by('-priority', 'category')` | `.order_by('-priority', 'category', 'id')` |
| 13 | `models.py` | `WellPairDistance` bulk ILM back-fill (`records_to_update` / `to_update`) | `.order_by('-priority', 'category')` | `.order_by('-priority', 'category', 'id')` |
| 14 | `models.py` | `WellPairDistance` per-well recalculation (deletes both directions, then rebuilds) | `.order_by('-priority', 'category')` | `.order_by('-priority', 'category', 'id')` |
| 15 | `models.py` | `WellPairDistance` per-rig recalculation | `.order_by('-priority', 'category')` | `.order_by('-priority', 'category', 'id')` |
| 16 | `optimization.py` | new `DrillingScheduler._sort_frame_totally` staticmethod | — | `sort_values(["name", "id"] if "id" in df.columns else ["name"], kind="stable").reset_index(drop=True)` |
| 17 | `optimization.py` | `preprocess_data` — the rig/well sort **in place**, still before matrix construction (clause 3.1) | `sort_values(by="name").reset_index(drop=True)` x2 | `self._sort_frame_totally(...)` x2 |
| 18 | `optimization.py` | `_calculate_ilm_days_matrix` — `WellPairDistance` fetch | `.filter(rig=rig_obj).select_related(...)` | `+ .order_by('well_1__name', 'well_2__name', 'id')` |
| 19 | `optimization.py` | `_calculate_ilm_costs` — per-rig assignment sort | `arr.sort(key=lambda x: x["well_start_date"])` | `arr.sort(key=lambda x: (x["well_start_date"], x["well"]))` |

**Grepped, not assumed.** `order_by('-priority'` now returns 6 hits (2 in `views.py`, 4 in
`models.py`) and every one carries `'id'`. The task text guessed "there may be more or fewer than
four" in `models.py` — it is exactly four.

**Not changed, deliberately:** the `for (wid, rid), a in self.assignments.items()` loop in
`_extract_solution`. Task 4's comment is present and intact ("dict insertion order **is** the
canonical `(well, rig)` order … a refactor to an unordered container would silently reintroduce the
non-determinism this whole spec removes"). Left alone.

**Observed and reported, not changed:** two further `sort(key=lambda x: x['well_start_date'])` sites
exist in `views.py` (the locked-actuals `assignments_by_rig` loop and one inside the SEM-facing
reschedule branch) that the design does not enumerate. They are the same latent hazard as items 3
and 9. Left as-is rather than widening a review-flagged task's blast radius without authorisation;
flagged here as candidate follow-up work.

#### 5.3 — the failing test now passes, and *why* it needed a harness fix

`RigBuildingAdjustment.id` is a **`UUIDField` defaulting to `uuid.uuid4`**, not an auto-increment
integer. That single fact decides the shape of this subtask, and it was not in the design:

- Before the fix, PostgreSQL returned the two tied rows in heap (= insertion) order, so the measured
  baseline was **X-then-Y → 2.0 days, Y-then-X → 7.0 days**.
- Adding `'id'` makes the fetch order **total and stable for a given database**, which is what
  clause 2.10 requires. But because the keys are *random*, the existing test — which built the two
  halves as **two separate locations, i.e. four distinct rows with four random keys** — became a coin
  toss rather than a fix. Measured on the first run after the production change: **X-then-Y → 7.0,
  Y-then-X → 2.0**, the exact reverse of the baseline. Deterministic per database, random per run.
- So `factories.create_tied_adjustment_pair` now **pins** the primary keys via a new
  `factories.tied_rule_pk(label, pk_group)`. Within a `pk_group` the key is derived from the label's
  position in `sorted(TIED_RULE_SPECS)`, so `X` precedes `Y` whichever order the rows were inserted
  in; `pk_group` keeps the two halves' keys distinct (a pk is unique table-wide, so two locations
  cannot reuse one pair). `UUID(int=…)` ordering matches PostgreSQL's, which compares `uuid`
  byte-wise over the big-endian 16-byte value.

That is not weakening the test — it is what makes it measure the stated property. With unpinned keys
the assertion's outcome came from `os.urandom`; with pinned keys the rule *set* is genuinely
identical across the two halves and **insertion order is the only variable left**, which is exactly
what clause 2.10 is about.

| | insertion X,Y | insertion Y,X |
|---|---|---|
| before task 5 | **2.0 days** | **7.0 days** |
| after the production change, unpinned keys | 7.0 days | 2.0 days (random per run) |
| **after task 5 (pinned keys)** | **2.0 days** | **2.0 days** |

Applied rule in both halves: `Tied rule X - replace base norm`, which is the tied rule with the
**lower `id`** — asserted, not merely observed. Two assertions were **added** to
`test_ilm_days_do_not_depend_on_rule_insertion_order`: the applied-rule list equals
`[lowest-id rule condition]` in each half, and `ilm_days` equals that rule's `adjustment_value`. A
third guard asserts `tied_rule_pk("X", g) < tied_rule_pk("Y", g)` for both groups, so the expectation
cannot silently invert. The test's diagnostic printout also now reports the fetch order under the
**production** key (`('-priority', 'category', 'id')`) instead of the old two-key one, which
previously printed a misleading order.

**Standing note for the VM.** `id` is total and stable but *not* portable: it is a random UUID, so
two databases holding the same logical rule set can order tied rules differently. Determinism is
per-database, which is what the requirement asks for ("same machine, same schedule"). If
cross-environment reproducibility is ever wanted, the key would need a content component
(`condition` before `id`); that is not clause 2.10's key and was not added.

#### 5.4 — `WellPairDistance` overlap: added, and it is a real hazard

`WellPairDistance.Meta.ordering` already sorted on
`('location__company_code', 'rig__name', 'well_1__name', 'well_2__name')`, so the design's "the
queryset is unordered" is **imprecise** — Django was applying that. The hazard is real anyway,
because for the colliding case **every one of those four keys ties**, which is the gap `id` closes.

The overlap is only constructible the way it really occurs: `unique_together = ['rig', 'well_1',
'well_2']` forbids two rows over the same `Well` objects, and `Well.name` has no `unique=True`, so
`build_overlapping_well_pair_distance_scenario` creates a **third well row sharing `WELL-001`'s
name** that takes no part in the schedule. Its distance row is loaded regardless, because the fetch
filters on `rig=` alone — no location predicate, no restriction to the scheduled wells — and both
rows land on the same name-keyed `distance_cache` entry.

**Added** (it did not already exist) — `OverlappingWellPairDistanceTests`, 3 tests:

| test | result |
|---|---|
| `test_the_scenario_really_contains_an_overlap` | PASS — 2 colliding rows, distances 10 m vs 60,000 m |
| `test_ilm_matrix_value_is_stable_across_repeated_builds` | PASS — 6 observations (`preprocess_data` + 4 further `_calculate_ilm_days_matrix()` calls + a fresh `DrillingScheduler`), all **11.7**, 1 distinct value |
| `test_the_surviving_row_is_the_one_the_total_ordering_names` | PASS — survivor is the greater-`id` row (11.7), not the other candidate (2.0) |

The third test is the substantive one: stability alone could be an accident of one database's heap
order, so the winner is asserted to be the row the documented order names. The loader iterates
ascending and each row overwrites the previous, so the **last** row in
`('well_1__name', 'well_2__name', 'id')` order wins; the fixture pins the keys so that expectation is
a stated consequence rather than an observation.

#### 5.5 — verification, all re-run after every edit

| # | command | result |
|---|---|---|
| 1 | `test_ordering --keepdb` | **6 tests, 1 failure.** `test_ilm_days_do_not_depend_on_rule_insertion_order` **PASSES** (2.0 both insertion orders, lower-`id` rule applied). All 3 `WellPairDistance` tests PASS. `test_tied_rules_are_actually_tied` PASSES. `test_duplicate_well_names_are_rejected_naming_the_duplicates` **still FAILS** — task 6, untouched |
| 2 | `test_preservation --keepdb` | **8/8 PASS** (0.81 s), no `IDRS_REGENERATE_GOLDEN`, no overwrite flag. **No golden moved.** Unique proven optimum `698,525,729` / `0dcdf8e6ecc66b25`, exactly 1 schedule attaining `V*`, enumeration exhausted. Locked actuals `710,225,835` / `ade2afa77882d02e`, every pin held. Performance mode unchanged |
| 3 | `test_tie_enumeration --keepdb` | **PASS.** Canonical count still **4** (pinned value), tied set still 4, both exhausted, identical hash list `0b236ee41210272d`, `21eab6f2022716e3`, `2659d0ba8a8fc116`, `8fa867e67fbbd0bd`; `V* = 218,583,260`, `T* = 8,182`, `W1 = 51 > 50`. Ordering did not move it |
| 4 | `test_determinism --keepdb` (idle) | **PASS** (2 tests, 1 skipped, 57.1 s). 5 idle runs @ `T = 6 s`: hash `1a6136917eac05eb`, objective `97,768,602,348`, **23** wells, `det_time 3.0600` every run (spread `0.0000`), wall `4.72-4.86 s`, `DETERMINISTIC_BUDGET`, `total_cost 1,279,834,676` |
| 5 | `IDRS_TEST_CPU_LOAD=1 IDRS_TEST_CPU_LOAD_WORKERS=4 … test_repeat_runs_under_cpu_load --keepdb` | **PASS** (59.6 s, 4 burners established). 3 idle + 2 loaded, all five: hash `1a6136917eac05eb`, objective `97,768,602,348`, 23 wells, `det_time 3.0600`, spread `0.0000`; wall `4.92 / 4.83 / 4.85` idle, `4.90 / 4.87` loaded |
| 6 | `scheduler.tests --keepdb` (full) | **48 tests, 1 failure, 1 skip**, 85.9 s. The single failure is `test_duplicate_well_names_are_rejected_naming_the_duplicates` (task 6). Test count rose 45 → 48 from the three new overlap tests |

**Why preservation could not move here, and it is not luck.** The preservation scenario's
`create_ilm_adjustment_rules` gives every rule a **distinct `priority`** (100 / 50 / 40), so
`('-priority', 'category')` was already total on it and adding `'id'` cannot reorder anything. Its
well names are distinct, so `('name', 'id')` and `('name',)` agree. `create_well_pair_distances`
writes one row per unordered pair per rig with no name collisions, so the `WellPairDistance` order was
already total. And per-rig `AddNoOverlap` makes same-rig start-date ties impossible, so the total sort
keys on the assignment lists cannot change a `sequence_order`. Every one of the three ordering
changes is a no-op on inputs that contain no tie — which is the design's claim, now measured.

#### How to re-run

```bash
.venv/bin/python manage.py test scheduler.tests.test_ordering      --keepdb   # 6 tests, 1 expected failure (task 6)
.venv/bin/python manage.py test scheduler.tests.test_preservation  --keepdb   # 8/8
.venv/bin/python manage.py test scheduler.tests.test_tie_enumeration --keepdb # canonical == 4
.venv/bin/python manage.py test scheduler.tests.test_determinism   --keepdb   # idle
.venv/bin/python manage.py test scheduler.tests                    --keepdb   # 48 tests, 1 failure

IDRS_TEST_CPU_LOAD=1 IDRS_TEST_CPU_LOAD_WORKERS=4 .venv/bin/python manage.py test \
  scheduler.tests.test_determinism.RepeatRunDeterminismTests.test_repeat_runs_under_cpu_load --keepdb
```

- [x] 6. Fix — reject duplicate well names (design decision 5)

  **⚠️ REVIEW REQUIRED — changes behaviour on an error path.** A run with duplicate well names is
  refused up front instead of silently collapsing wells. Note this state is already fatal today —
  `wells.get(name=...)` at `scheduler/views.py:1988` raises `MultipleObjectsReturned` inside
  `transaction.atomic()`, so the save already aborts, just opaquely and after the solve has been
  paid for.

  - [x] 6.1 Add the invariant in `preprocess_data`
    - `scheduler/optimization.py` — `preprocess_data` (`:653-696`), immediately before the sort at
      `:686-687`
    - If `wells_df["name"]` has duplicates, raise a typed `DuplicateWellNameError` listing every
      duplicate. Placing it here covers all eight `solve` / `solve_with_actuals` call sites plus SEM
      at once, and it fires before any expensive work
    - Assert the same for `rigs_df["name"]` — `Rig.name` is unique at `scheduler/models.py:228` so
      it cannot trigger, but the invariant is free and documents the assumption
    - Chosen over re-keying the model on `Well.id`: re-keying is a cross-module contract change
      touching `assignments`/`start_times`/`end_times`/`intervals` (`:891-901`), the distance matrix
      (`:697-716`), the per-rig ILM matrices (`:759-764`, `:795-822`), `circuit_arcs` (`:1168`),
      every objective term (`:1239-1270`, `:1399-1410`), extraction (`:1809`), the payload keys
      (`:1818-1829`), `_calculate_ilm_costs` (`:2226-2277`), `analyze_infeasible_solution`
      (`:1598-1610`), `merge_wells_for_scenario` (`:2341`), the actuals paths (`:1454`, `:1480-1513`),
      plus `views.py:1988-1989`, `:2422-2423`, `:2506`, `:2520`,
      `well_rejection_analyzer.py:38` and `sem_views.py:1107`, `:1137-1145`
    - _Bug_Condition: `isBugCondition(X)` via clauses 1.6 / 1.7 — two selected wells share a `name`_
    - _Expected_Behavior: the run is rejected naming the duplicates, rather than one variable pair
      being created for two wells_
    - _Preservation: the assignment payload keys stay well/rig **names**, so the save logic
      (`views.py:1988-1989`), the SEM mapping (`sem_views.py:1137-1145`) and
      `WellRejectionAnalyzer` (`well_rejection_analyzer.py:38`) need no change_
    - _Requirements: 2.9_

  - [x] 6.2 Reject at the API boundary with an actionable message
    - `scheduler/views.py` — `ScheduleViewSet.create_schedule`, before creating the `Schedule` row
      (`:1911-1913`): check the selected wells for duplicate names, return HTTP 400 naming them, and
      leave no `FAILED` schedule row behind. The optimizer check is the invariant; this one is the
      user experience
    - Map `DuplicateWellNameError` through `_friendly_error_message` so the existing exception
      handler at `views.py:2100-2110` produces a clear message on the other call paths
    - _Requirements: 2.9_

  - [x] 6.3 Delete the dead `well_name_to_obj` lookup
    - `scheduler/optimization.py:744-754` — built with `WellModel.objects.get(name=wname)` and never
      read. With duplicate names that `get` raises `MultipleObjectsReturned`, which the outer
      `except Exception` at `:753` swallows after aborting the loop. Harmless today only because the
      dict is unused. One fewer name-keyed lookup and one fewer swallowed exception
    - _Requirements: 2.9_

  - [x] 6.4 Verify duplicate rejection
    - **Property 5: Total input ordering** - duplicates are rejected
    - `scheduler/tests/test_ordering.py`: two wells sharing a `name` → `preprocess_data()` raises
      `DuplicateWellNameError` naming **both**; `create_schedule` returns 400 with the names; no
      `Schedule` row is left behind
    - Re-run the task 2 goldens — no non-duplicate input may be affected
    - **EXPECTED OUTCOME**: new tests PASS, goldens PASS
    - _Requirements: Property 5 (validates 2.9)_

  - [ ] 6.5 Raise the out-of-scope follow-up, do not implement it
    - **DELIBERATELY NOT IMPLEMENTED — left unchecked on purpose.** Recorded as item 1 of
      "Deferred follow-ups (out of scope for this spec)" at the end of this file. Nothing in
      `scheduler/models.py` was changed by task 6 and no migration was added
    - A `unique=True` (or `unique_together('location', 'name')`) constraint on `Well.name`
      (`scheduler/models.py:394`) plus a management command to report existing duplicates. The
      migration can fail on live data, so it needs its own change with a data-cleanup step
    - Record it as a follow-up; explicitly out of scope here
    - _Requirements: 2.9_

### Task 6 results — **COMPLETE**, 6.1-6.4 done, 6.5 deliberately not implemented

Production files touched: **`scheduler/optimization.py`** and **`scheduler/views.py`**. Tests
touched: `scheduler/tests/test_ordering.py` (2 new tests). No migration, no settings change, no
model change, no scratch file.

Line numbers in the task text were **stale for `optimization.py`** (shifted ~450-1050 lines across
tasks 3-5, as warned) and still accurate for `views.py`. Every site was located by symbol name.

#### Sites changed, by file and symbol

| # | File | Symbol / location | Change |
|---|---|---|---|
| 1 | `optimization.py` | new module-level `DuplicateNameError(ValueError)` + `DuplicateWellNameError` / `DuplicateRigNameError` subclasses, and a `find_duplicate_names()` helper, next to the other module constants | added |
| 2 | `optimization.py` | new `DrillingScheduler._reject_duplicate_names()` | added — raises the typed error naming **every** duplicate; wells first, then rigs |
| 3 | `optimization.py` | `preprocess_data` — call inserted **immediately before** `self._sort_frame_totally(...)` (task 5's sort), i.e. before the distance and ILM matrices | added |
| 4 | `optimization.py` | `_calculate_ilm_days_matrix` — the dead `well_name_to_obj` loop | **deleted** (11 lines), replaced by a note; `Well as WellModel` dropped from the local import, which that loop was its only user |
| 5 | `views.py` | `ScheduleViewSet.create_schedule` — new "Phase 0" check **before** `Schedule.objects.create(...)` | added — HTTP 400, `error` names the duplicates, `duplicate_well_names` carries them as data |
| 6 | `views.py` | `_friendly_error_message` — signature is now `(raw, exc=None)` | `DuplicateNameError` passes its own message through untouched instead of being flattened into the generic fallback; a string-prefix branch covers callers that only have the text |
| 7 | `views.py` | the two `_friendly_error_message(str(e))` call sites in `create_schedule` | now pass the exception too: `(str(e), e)` |

**Why `DuplicateNameError` subclasses `ValueError`.** Checked before choosing it: all 16
`except ValueError` sites in `views.py` / `sem_views.py` wrap `parse_financial_year` or task-id
parsing — none wraps a `solve` / `preprocess_data` call — so subclassing cannot silently downgrade
the rejection to a warning anywhere, and callers that already funnel bad input through
`except ValueError` keep working.

**`well_name_to_obj` verified dead before deleting**, not assumed: `grep -n well_name_to_obj`
returned exactly the 4 lines of its own construction and nothing else. Its `except Exception` was
swallowing the `MultipleObjectsReturned` that duplicate names raise — the very error that used to
log `get() returned more than one Well -- it returned 2!` and then abort the loop silently.

**Not changed, deliberately** (per the task's preservation note): the assignment payload keys stay
well/rig **names**, so the save path, `sem_views.py`'s mapping and `WellRejectionAnalyzer` needed
no change and were not touched. The `for (wid, rid), a in self.assignments.items()` loop and its
load-bearing comment are untouched. `scheduler/models.py` is untouched — task 6.5 is not
implemented.

#### 6.4 — verification

| # | command | result |
|---|---|---|
| 1 | `test_ordering --keepdb` | **8 tests, 0 failures** (0.36 s). `test_duplicate_well_names_are_rejected_naming_the_duplicates` now **PASSES** — the last failing test in the suite is closed. All 5 task-5 ordering tests still PASS (tied rules 2.0 both insertion orders, all 3 `WellPairDistance` overlap tests). Count 6 → 8 from the two new tests |
| 2 | `test_preservation --keepdb` | **8/8 PASS** (0.75 s), no `IDRS_REGENERATE_GOLDEN`, no overwrite flag. **No golden moved.** Unique proven optimum `698,525,729` / `0dcdf8e6ecc66b25`, exactly 1 schedule attaining `V*`, enumeration exhausted. Locked actuals `710,225,835` / `ade2afa77882d02e` |
| 3 | `test_determinism --keepdb` (idle) | **PASS** (2 tests, 1 skipped, 54.3 s). 5 idle runs @ `T = 6 s`: hash `1a6136917eac05eb`, objective `97,768,602,348`, **23** wells, `det_time 3.0600` every run (spread `0.0000`), wall `4.67-4.71 s`, `DETERMINISTIC_BUDGET`, `total_cost 1,279,834,676` |
| 4 | `IDRS_TEST_CPU_LOAD=1 IDRS_TEST_CPU_LOAD_WORKERS=4 … test_repeat_runs_under_cpu_load --keepdb` | **PASS** (58.4 s, 4 burners established). 3 idle + 2 loaded, all five: hash `1a6136917eac05eb`, objective `97,768,602,348`, 23 wells, `det_time 3.0600`, spread `0.0000`; wall `4.73 / 4.72 / 4.67` idle, `4.83 / 4.78` loaded |
| 5 | `scheduler.tests --keepdb` (full) | **50 tests, 0 failures, 1 skip**, 83.1 s — **GREEN**. Test count 48 → 50 from the two new tests |

#### The two new tests, and what each one pins

The pre-existing `test_duplicate_well_names_are_rejected_naming_the_duplicates` accepts *any* typed
rejection whose message names the duplicates, because it was written before the fix existed. It
passes unchanged. Two tests were **added** so the contract the fix actually delivers is pinned
rather than merely satisfied:

| test | asserts |
|---|---|
| `test_the_rejection_is_the_typed_error_and_fires_before_any_work` | the error is specifically `DuplicateWellNameError`; `exc.duplicate_names == ["WELL-001"]` (the names are data, not only prose); and `distance_matrix` is still empty and `ilm_days_matrix` still `{}` — i.e. the check fires before the expensive matrix construction and before the collision can reach `self.assignments` |
| `test_create_schedule_returns_400_and_leaves_no_schedule_row` | `POST /api/schedules/create_schedule/` returns **400**, the body's `error` names `WELL-001` and `duplicate_well_names == ["WELL-001"]`, and `Schedule.objects.count()` is **unchanged** — no `FAILED` row left behind. Uses the same `user_logged_in` / `log_user_login` disconnect workaround as `test_preservation.SavePathPreservationTests`, for the same reason (`force_login` sends a bare `HttpRequest` whose `method` is `None` into a NOT NULL column) |

**Before / after, on the same 3-well 1-rig duplicate scenario:**

| | before task 6 | after task 6 |
|---|---|---|
| `preprocess_data()` | accepted the input | raises `DuplicateWellNameError: Duplicate well name: WELL-001. …` |
| assignment variables | **2** for 3 wells (silent collapse) | never built |
| downstream outcome | `TypeError: float() argument must be a string or a real number, not 'DataFrame'` in `add_ilm_constraints`, naming no well | n/a — rejected up front |
| `POST create_schedule` | ran the solve, then aborted in the save path with `MultipleObjectsReturned` inside `transaction.atomic()`, leaving a row behind | 400 naming `WELL-001`, no `Schedule` row created, no solve paid for |

**Why preservation could not move.** The check is a pure guard: on any input whose well and rig
names are already distinct — which every preservation, determinism and tie-enumeration scenario is
— `find_duplicate_names` returns `[]` and `preprocess_data` proceeds byte-identically. Deleting
`well_name_to_obj` cannot move a number either: the dict was never read. Measured, not assumed:
goldens 8/8 with no drift.

#### How to re-run

```bash
.venv/bin/python manage.py test scheduler.tests.test_ordering      --keepdb   # 8/8
.venv/bin/python manage.py test scheduler.tests.test_preservation  --keepdb   # 8/8
.venv/bin/python manage.py test scheduler.tests.test_determinism   --keepdb   # idle
.venv/bin/python manage.py test scheduler.tests                    --keepdb   # 50 tests, GREEN

IDRS_TEST_CPU_LOAD=1 IDRS_TEST_CPU_LOAD_WORKERS=4 .venv/bin/python manage.py test \
  scheduler.tests.test_determinism.RepeatRunDeterminismTests.test_repeat_runs_under_cpu_load --keepdb
```

- [x] 7. Fix — canonical decision strategy, `FIXED_SEARCH` off by default (design decision 4)

  **⚠️ REVIEW REQUIRED — may change existing schedule output.** Adds a first-branch preference, so
  a timed-out run can return a different incumbent. `AUTOMATIC_SEARCH` is retained, so the strategy
  is a hint rather than a mandate.

  - [x] 7.1 Give `_add_decision_strategy` a real body
    - `scheduler/optimization.py:986-994` — the body is currently `pass` (verified at `:992`, with
      the stale docstring claiming the strategy "cripples OR-Tools performance")
    - Two strategies in canonical order, which is already the dict insertion order of
      `self.assignments` and `self.start_times` since `preprocess_data` sorts both frames
      (`:686-687`) and `setup_variables` iterates wells then rigs (`:886-908`):
      (1) assignment BoolVars, `CHOOSE_FIRST`, `SELECT_MAX_VALUE` — try assigning before dropping;
      (2) start-time IntVars, `CHOOSE_FIRST`, `SELECT_MIN_VALUE` — try earlier before later
    - Both are the same preference direction the tie-break objective encodes, so the first solutions
      found are closer to the canonical one and stage 2 has less to do
    - Apply the same strategies to stage 2
    - _Bug_Condition: `isBugCondition(X)` where `noCanonicalOrder` — `decisionStrategyCount(model(X)) = 0`_
    - _Expected_Behavior: an explicit canonical branching order over the assignment BoolVars and
      start-time IntVars in sorted well-then-rig order_
    - _Preservation: `search_branching` stays `AUTOMATIC_SEARCH` (`:938`), so the strategy is a hint
      on first-branch preference, not a mandate — near-zero cost, and it cannot cripple the search
      the way the removed version did (clause 2.7, 3.9)_
    - _Requirements: 2.6, 2.7_

  - [x] 7.2 Expose `FIXED_SEARCH` as an off-by-default setting
    - `IDRS_SOLVER_DETERMINISM['FIXED_SEARCH']` from task 3.1, for audit runs where path stability
      matters more than quality
    - Its cost is now **bounded**, a direct consequence of task 3: with a work-based budget a slower
      search cannot overrun the wall clock, it returns a worse incumbent within the same budget.
      That converts an unbounded risk into a measurable quality tradeoff, and is why this knob can
      exist at all
    - Because it changes the answer, it belongs in the solver fingerprint (task 8)
    - _Requirements: 2.7_

  - [x] 7.3 Check the presolve interaction
    - Presolve remaps variables and decision strategies over variables presolve removes are handled
      by CP-SAT, but verify `cp_model_presolve = True` (`:981`) stays on and that no warning appears
      in the solver log
    - _Requirements: 2.6_

  - [x] 7.4 Verify strategy, determinism and preservation
    - **Property 1: Expected Behavior** / **Property 2: Preservation**
    - Unit test: `_add_decision_strategy` adds exactly two strategies in canonical `(well, rig)`
      order, and `search_branching` remains `AUTOMATIC_SEARCH` unless `FIXED_SEARCH` is enabled
    - Re-run the task 1 repeat-run harness and the task 2 goldens
    - Measure solve time against the pre-task-7 baseline on a representative rig/well set — clause
      2.7 requires the fix be measured, not assumed, and clause 3.9 requires no material regression
      in wells assigned or total cost
    - **EXPECTED OUTCOME**: harness PASS, goldens PASS, no material runtime regression
    - _Requirements: 2.6, 2.7, 3.9_

    **MEASURED — task 7 outcome (clause 2.7: measured, not assumed).**

    Unit tests: 11 new in `scheduler/tests/test_decision_strategy.py`, all passing. Exactly two
    strategies, both in canonical `(well, rig)` order read back out of the *model proto* (resolved
    through `proto.variables[i].name`, so it is what CP-SAT sees rather than what the Python dict
    held); `search_branching` stays `AUTOMATIC_SEARCH` by default and becomes `FIXED_SEARCH` only
    when the setting is on; performance mode gets **zero** strategies.

    Presolve (7.3): `cp_model_presolve: true` in both stages' logged parameter lines, and **0
    warning lines** in 385 captured log lines. Presolve removed 8,776 unused variables and *carried
    the strategies through* the remap rather than dropping them — the log reports
    `Search strategy: on 240 variables` before presolve and `on 77 variables` after, same
    `CHOOSE_FIRST, SELECT_MAX_VALUE`.

    Determinism: still one hash. `HARD_OPEN` scenario, 5 idle + 5 mixed (4 CPU burners), 1 distinct
    `schedule_hash`, 1 distinct `objective_value`, `deterministic_time` spread 0.0000.

    Quality and runtime, `HARD_OPEN` scenario at `T = 6 s`, identical invocation before and after:

    | | schedule_hash | objective | wells assigned | total_cost | det_time | wall idle | wall loaded |
    |---|---|---|---|---|---|---|---|
    | **BEFORE** (pre-7) | `1a6136917eac05eb` | 97,768,602,348 | 23 | 1,279,834,676 | 3.0600 | 4.51 / 4.53 / 4.51 | 4.67 / 4.66 |
    | **AFTER** (task 7) | `d465c4ea56cfe37c` | 92,781,674,351 | **24** | 1,296,627,456 | 3.0600 | 5.23 / 5.23 / 5.28 | 5.39 / 5.38 |

    Reading it against clause 3.9, which forbids a material regression in wells assigned or total
    cost:

    - **Objective improved 5.10 %** (97.77 bn → 92.78 bn; this is a minimisation). The objective is
      the expression that encodes the whole trade-off, so this is the number that says the answer
      got better.
    - **Wells assigned 23 → 24.** The first-branch preference is "assign before drop, early before
      late", and it bought a well. This is the improvement the task was for, showing up exactly
      where predicted: a run truncated by the deterministic budget now holds a better incumbent.
    - **`total_cost` rose 1.31 %** (1,279,834,676 → 1,296,627,456, +16,792,780). Not a regression:
      drilling a 24th well costs more than drilling 23. Cost per well assigned *fell*, 55,645,003 →
      54,026,144 (-2.91 %). Clause 3.9 is about quality, and the extra spend buys the extra well
      that the objective prices as a net 5.10 % gain.
    - **`deterministic_time` unchanged at 3.0600**, exactly the budget, in every run. The work
      performed is identical; the strategy changed *where* that work went, not how much.
    - **Wall time +16.2 % idle** (4.517 → 5.247 mean), **+15.4 % loaded** (4.665 → 5.385). Not from
      extra search — `det_time` is identical — but from the larger model proto and presolve handling
      480 extra strategy expressions. It does not threaten the budget: stage 1's backstop at
      `T = 6` is `0.85 x 1.5 x 6 = 7.65 s`, and the worst observed wall is 5.44 s, i.e. 71 % of it,
      with every run still classifying `DETERMINISTIC_BUDGET` rather than `WALL_CLOCK_BACKSTOP`.

    **RESOLVED — two `model_fingerprint` values re-anchored, nothing exempted.**

    Adding two `search_strategy` entries to the model proto necessarily moves its SHA-256, so
    `unique_optimum` and `solve_with_actuals` failed on `model_fingerprint` while
    `performance_mode` and `save_path` passed untouched. A decision strategy cannot change the
    feasible set or the optimal value, only the order of descent, so the answer was expected to
    hold — and was proved to hold before the fixture was touched.

    Resolution chosen: **re-anchor the two values, do not exempt the field.** An exemption would
    blind the test to `model_fingerprint` permanently; re-anchoring keeps it under byte-for-byte
    comparison. Executed under four guards:

    1. **Precondition gate.** The full preservation comparison was re-run with `model_fingerprint`
       stripped from both sides and nothing else, using the production comparison code. All 8 cases
       passed, so on both affected cases 24 fields held byte-identical — `objective_value`
       698,525,729 / 710,225,835, `schedule_hash` `0dcdf8e6ecc66b25` / `ade2afa77882d02e`, all 4
       assignment records including `well_start_date`, `well_end_date` and `sequence_order`, every
       cost field, the project and FY dates, and both solver-parameter blocks. Exhaustive
       enumeration still reported exactly 1 schedule at `V* = 698,525,729`.
    2. **Diff audit.** Old fixture backed up, re-baseline applied, then old vs new diffed over every
       leaf field of `cases`: 306 before, 306 after, **0 added, 0 removed, exactly 2 changed** — the
       two `model_fingerprint` values and nothing else.

       A first attempt using the full `write_golden` re-capture **failed this audit** and was rolled
       back byte-identically. It changed 10 fields, not 2: besides the fingerprints it rewrote the
       task-3 stop-criterion parameters (`max_deterministic_time` inf → 5.1,
       `max_time_in_seconds` 10 → 12.75, `interleave_batch_size` 0 → 1). Those are the values
       `STOP_CRITERION_PARAMETER_KEYS` exempts from equality and asserts positively instead, and
       that exemption is only meaningful while the golden still holds the *pre-fix* numbers. A full
       re-capture would have quietly deleted the record of what the parameters were before task 3.
       Hence the new `golden.rebaseline_fields()`: a surgical re-anchor whose allow-list
       (`REBASELINEABLE_FIELDS`) contains `model_fingerprint` and nothing else, so it cannot reach
       an answer field, cannot add a field, and refuses a no-op edit.
    3. **Provenance preserved, not overwritten.** `write_golden` used to replace `provenance`
       wholesale, which for a provenance fixture is the one unacceptable loss. Re-baselining is now
       additive: `provenance_history` is ordered oldest-first with entry 0 holding the original
       pre-fix capture (commit `3561731c40b4fe6f1fae336f9307911ee0267294`, captured 2026-09-03,
       ortools 9.15.6755) together with its production-file SHA-256 set, the files that had changed
       by the time it was superseded, and the one-line reason. Current `provenance` carries
       `supersedes_git_commit`, `rebaseline_reason`, `rebaseline_kind: surgical` and
       `rebaselined_fields` recording each old → new fingerprint in full. The `_README` gains a
       section explaining what a re-baseline did and did not move.

       **Caveat, recorded deliberately:** `provenance.git_commit` is still
       `3561731c40b4fe6f1fae336f9307911ee0267294` — the same SHA as the superseded entry — because
       tasks 3-7 are uncommitted in the working tree, so HEAD has not moved. The two baselines are
       distinguished by `production_file_sha256`, which differs on
       `drilling_scheduler/settings.py`, `scheduler/models.py`, `scheduler/optimization.py` and
       `scheduler/views.py`, and is identical on the two files tasks 3-7 never touched. Committing
       tasks 3-7 and re-running the surgical re-baseline would make `git_commit` distinct as well.
    4. **The field stays checked.** `test_model_fingerprint_is_still_compared_byte_for_byte` asserts
       both that `model_fingerprint` is absent from the exemption list *and* that a mutated value
       actually fails the comparison — the second because a field can be off an exemption list and
       still never be reached.

    One test assertion changed: `test_provenance_is_complete` required
    `working_tree_clean_of_production_files`, which a surgical re-baseline cannot satisfy by
    construction, since the change responsible for the move is necessarily still uncommitted. It is
    now mode-aware — unchanged and full-strength for a first capture; for a re-baseline it instead
    requires that history[0] names a full 40-character commit, that `supersedes_git_commit` matches
    the chain, that the reason and re-anchored field list are present, that every re-anchored field
    is on the allow-list, and that every history entry keeps its reason and file hashes. The pre-fix
    baseline's correspondence to its own commit is still asserted, from the history entry that now
    holds it.

    **Final state: 62 tests, 0 failures, 0 skips. 8/8 goldens pass with the two updated
    fingerprints. Repeat-run harness one hash idle and under 4-burner load, `deterministic_time`
    spread 0.0000.**

- [x] 8. Fix — observability and provenance persistence (design decision 7)

  **⚠️ REVIEW REQUIRED — DATABASE SCHEMA CHANGE.** Migration `0063_add_determinism_provenance.py`
  adds six nullable fields to `Schedule`. Additive and reversible, no data backfill, but it must be
  applied on the VM (`Install Windows/apply_migrations.bat`). Latest existing migration is
  `0062_add_schedule_input_metadata.py` (verified), so `0063` is the correct number.

  - [x] 8.1 Add provenance to the result payload
    - `scheduler/optimization.py` — both `self.results` branches of `_extract_solution`
      (`:1858-1887` and `:1889-1920`)
    - `model_fingerprint` (stage-1 proto SHA-256, already computed at `:1735-1738`, `:1560-1563`),
      `model_fingerprint_canonical` (stage-2 proto SHA-256, null when stage 2 was skipped),
      `solver_fingerprint` (SHA-256 over the explicitly-set parameter proto text +
      `ortools.__version__` + the `IDRS_SOLVER_DETERMINISM` values), `deterministic_stop`,
      `stop_reason`, `deterministic_time_used`, `deterministic_budget`, `wall_backstop_seconds`,
      `canonicalization_status`
    - The chain `fp₁ → V* → fp₂` is itself reproducible, since stage 2's proto is a deterministic
      function of stage 1's result
    - Keep **every** existing log line (clause 3.5) and add one reporting the stop reason and the
      deterministic time against its budget
    - _Requirements: 2.11, 3.5_

  - [x] 8.2 Persist the provenance fields — SCHEMA CHANGE
    - New nullable fields on `Schedule` (`scheduler/models.py:1498-1540` block, verified —
      `schedule_hash` at `:1498`, `optimality_gap_percent` at `:1493`): `model_fingerprint`
      (CharField 64), `solver_fingerprint` (CharField 64), `deterministic_stop` (BooleanField,
      null), `stop_reason` (CharField 32), `deterministic_time_used` (FloatField, null),
      `deterministic_budget` (FloatField, null)
    - Migration `scheduler/migrations/0063_add_determinism_provenance.py`
    - Populate next to the existing assignments at `scheduler/views.py:1966-1974` (verified — the
      `schedule.schedule_hash = results.get('schedule_hash')` block near `:1972`), and on the other
      save paths at `:2394`, `:2775`, `:3405`
    - _Requirements: 2.11_

  - [x] 8.3 Surface the fields through the API
    - `ScheduleSerializer` uses `fields = '__all__'` (`scheduler/serializers.py:202-204`), so the new
      model fields appear in the `create_schedule` response and the detail endpoint with no
      serializer change
    - Add them to `ScheduleListSerializer`'s explicit field list (`serializers.py:246-257`) so the
      schedules list can show a determinism badge
    - Leave the determinism fields visible to **everyone** — do not route them through the
      `to_representation` admin gate that hides `optimality_gap_percent`
      (`serializers.py:222-230`, `:272-279`). The detail page already shows the full `schedule_hash`
      (`schedule_detail.html:413-421`), and the stop reason is a trust signal operators need more
      than admins do
    - _Requirements: 2.11_

  - [x] 8.4 Render provenance on the schedule detail page
    - `templates/scheduler/schedule_detail.html` — the metadata block at `:393-421` already renders
      Optimality Gap and Schedule Hash in a two-column row. Add a third row: Model Fingerprint as a
      `<code>` element next to the existing hash, and a Reproducibility badge from `stop_reason` —
      green for `OPTIMAL_PROVEN` and `DETERMINISTIC_BUDGET`, amber for `WALL_CLOCK_BACKSTOP` with
      the text "stopped on the wall-clock backstop — this run is not guaranteed reproducible",
      muted for the rest
    - Show `deterministic_time_used` / `deterministic_budget` as small muted text beside it
    - Keep the badge accessible: convey the state in text as well as colour, and give the badge an
      appropriate ARIA label rather than relying on colour alone
    - **The badge label and its tooltip MUST say the badge is ADVISORY**, and MUST name
      `python manage.py check_determinism` (task 10) as the authoritative reproducibility check. A
      single solve cannot prove reproducibility — only the cross-run `schedule_hash` comparison can.
      Wording along the lines of "Advisory — reproducibility is confirmed by running
      `check_determinism`". Carry this in the text and the ARIA label, not by colour alone
      *(added by the task 3 follow-on: `DETERMINISTIC_BUDGET_BINDING_FRACTION` was relaxed to 0.93
      precisely because the single-solve proxy is advisory; see "Task 3 follow-on" above)*
    - _Requirements: 2.11_

  - [x] 8.5 Surface provenance on the scheduling page
    - `templates/scheduler/scheduling.html` — `showResults()` (`:1275-1296`) currently reads only
      assignments, unassigned, cost and solve time from the response
    - Add the schedule hash (truncated, `title` with the full value), the model fingerprint, and a
      warning line rendered **only** when `result.deterministic_stop === false`
    - Follow the existing escaping pattern at `:1315-1317` for any interpolated text
    - **The warning text MUST state that the flag is ADVISORY** and MUST point at
      `python manage.py check_determinism` (task 10) as the authoritative reproducibility check —
      one solve cannot prove reproducibility, only comparing `schedule_hash` across runs can. Say it
      in the text (and the `title`), not by colour alone, so it survives for a screen reader
      *(added by the task 3 follow-on — see "Task 3 follow-on" above)*
    - _Requirements: 2.11_

  - [x] 8.6 Verify fingerprints and provenance
    - **Property 6: Provenance is surfaced**
    - Unit tests: identical inputs give identical `model_fingerprint` and `solver_fingerprint`;
      changing `DETERMINISTIC_TIME_RATIO` or `FIXED_SEARCH` changes `solver_fingerprint` and leaves
      `model_fingerprint` alone
    - Integration test: the schedule detail page renders the model fingerprint, the schedule hash
      and the reproducibility badge for a completed schedule
    - `python manage.py makemigrations --check --dry-run` reports no pending changes after 8.2
    - **EXPECTED OUTCOME**: PASS
    - _Requirements: Property 6 (validates 2.11), 3.5_

- [x] 9. Verification — full property, integration and regression suite

  - [x] 9.1 Property-based test suite
    - Add `hypothesis` to `requirements.txt`, pinned to the exact version resolved at install time
      (not currently installed — verified against `.venv`). Note this is a test-only dependency
    - Generate over: well count, rig count, durations, daily costs, ILM cost parameters, RTD offsets
      and FY windows. Keep generated models small enough to prove `OPTIMAL` quickly, since that is
      the `¬isBugCondition` regime
    - Repeat-run determinism over generated inputs: N solves yield one distinct `schedule_hash`
      (Property 1)
    - Preservation over generated inputs that prove `OPTIMAL`: fixed output equals unfixed output
      (Property 2). The task 2 golden fixture is the concrete anchor; this is the general claim
    - Feasibility and economics over all generated inputs: every hard constraint in clause 3.7
      holds — one rig per well, per-rig `AddNoOverlap`, rig availability windows, well RTD,
      HP/depth/BOP/TDS compatibility, FY start bounds, circuit-based ILM gaps
      (`scheduler/optimization.py:999-1204`); wells assigned does not decrease; cost does not
      increase at equal wells assigned (Property 3)
    - Ordering invariance: shuffling the input row order and the DB insertion order of wells, rigs,
      `RigBuildingAdjustment` and `WellPairDistance` rows leaves `model_fingerprint` unchanged
      (Property 5). This is the strongest single test of task 5, because it tests the invariant
      rather than each individual `order_by`
    - Independently runnable: `python manage.py test scheduler.tests`
    - _Requirements: Properties 1, 2, 3, 5 (validates 2.1, 2.8, 2.10, 3.1, 3.2, 3.6, 3.7, 3.8)_

  - [x] 9.2 Confirm the residual tie count is measured, not assumed
    - Re-run `scheduler/tests/test_tie_enumeration.py` and record the two numbers it logs: the
      distinct count at `P-expr == V*` alone (the tied set, expected > 1) and at
      `(P-expr == V*) AND (T-expr == T*)` (expected exactly 1)
    - This is the measurable residual for clause 2.5, per the note at the top of this file. Record
      both numbers in the task notes so the interpretation of 2.5 stays auditable
    - _Requirements: 2.5, 2.12_

  - [x] 9.3 Integration tests through the HTTP layer
    - `POST /api/schedules/create_schedule/` twice with an identical payload via the Django test
      client (`scheduler/views.py:1882`): both responses carry the same `schedule_hash` and
      `model_fingerprint`, and both persisted `Schedule` rows agree on every determinism field
    - A backstop-bound run through the same endpoint surfaces `deterministic_stop = false` and
      `stop_reason = WALL_CLOCK_BACKSTOP` in the response body, and the detail page renders the
      amber badge (assert on the rendered context and the presence of the warning text)
    - Re-optimize with locked actuals (`views.py:2361-2365`) and the SEM re-optimization endpoint
      (`sem_views.py:1125-1131`) each run twice and produce identical assignments (clauses 3.10, 3.11)
    - A duplicate-well-name payload returns 400 naming the duplicates and creates no `Schedule` row
    - `deterministic=False` still takes the performance path with no deterministic budget and no
      stage 2 (clause 3.12)
    - Save path unchanged: `sequence_order` still derived per rig from start date
      (`views.py:1996-2002`), unassigned wells still carry rejection analysis (`:2069-2084`)
    - _Requirements: 2.1, 2.4, 2.9, 2.11, 3.10, 3.11, 3.12, 3.13_

  - [x] 9.4 Performance and quality measurement on a representative set
    - **Property 4: Performance Bound**
    - Run a representative rig/well set at each Time Limit dropdown value
      (`templates/scheduler/scheduling.html:447-459`) and assert total wall time across both stages
      ≤ `time_limit_seconds × 1.2`
    - Compare wells assigned and total cost against the pre-fix baseline recorded in task 2 — no
      material regression (clauses 2.7, 3.9)
    - If the deterministic budget starves the search, or the wall-clock backstop binds when this
      machine is busy, tune `DETERMINISTIC_TIME_RATIO` for local contention headroom on this
      machine rather than reverting to a wall-clock stop, and record the value chosen — it is part
      of the solver fingerprint
    - _Requirements: 2.7, 3.9_

  **MEASURED — task 9 outcome.**

  *9.1* — `scheduler/tests/test_properties.py`, 5 property tests on `hypothesis==6.167.1`, green in
  ~5 s. Generates over rig count (2-3), well count (3-6), seed, duration and norm-day choices, ILM
  per-unit days, staggered availability windows and geographic spread. Properties: repeat-run
  determinism, proven-optimum stability, clause 3.7 feasibility/economics (one rig per well, per-rig
  non-overlap, rig windows, RTD, FY start, HP/depth/BOP/TDS compatibility, duration honoured), and
  ordering invariance both at the `model_fingerprint` level and end-to-end.

  **Non-vacuity is enforced, not assumed.** `build_open_scenario` draws rig capability independently
  of well requirements, so some seeds produce a model where nothing is compatible and the optimum is
  an empty schedule — hypothesis found exactly that (`num_rigs=2, num_wells=3, seed=2718`). Those
  examples are filtered with `assume()`, but every example is counted by `NonVacuityMixin` and
  `tearDownClass` **fails** if none turned out useful, so the suite cannot go green while asserting
  nothing. Reported per class on every run; latest: 8/8, 8/8, 8/8 and 16/16 useful.

  **Honest limitation on Property 2.** "Fixed output equals unfixed output" is not testable here —
  the unfixed code is gone, and running the current code twice compares the fix to itself. The
  concrete anchor stays the task 2 golden at commit `3561731c`. What is generalised is the checkable
  half: a proven optimum equals its own bound, reports a zero gap, and reproduces on re-solve.

  *9.2* — Tie enumeration re-run, both numbers recorded:

  | quantity | value |
  |---|---|
  | optimal objective `V*` | 218,583,260 |
  | tie-break minimum `T*` | 8,182 |
  | tie-break weights | `W1 = 51`, `W2 = 1`; `max(rig_well_order) = 50`, so `W1 >` it and the hierarchy is real |
  | schedules at `P-expr == V*` (the tied set) | **4**, enumeration exhausted |
  | schedules at `V*` **and** `T*` (canonical selection) | **4**, enumeration exhausted |

  The second number is 4 rather than 1 by the user's explicit Option B decision: the four survivors
  are interchangeable permutations of a symmetric model, same-machine reproducibility is met and
  measured, and canonicality was de-scoped (clause 2.5.2). The arc-order third tier over
  `circuit_arcs` remains the designated escalation if a non-symmetric model ever shows >1.

  *9.4* — `scheduler/tests/measure_performance.py` (committed, deliberately **not** named `test_*`,
  so a multi-minute measurement cannot silently join the suite). `HARD_OPEN` scenario:

  | `T` | e2e wall | solver wall | model build | whole backstop | solver/backstop | stage1/stage1 share | det used / budget | assigned | total cost | stop reason |
  |---|---|---|---|---|---|---|---|---|---|---|
  | 6 s | 11.47 s | 6.11 s | 5.36 s | 9.00 s | 67.9 % | 69.2 % | 3.0600 / 3.0600 | 24 | 1,296,627,456 | `DETERMINISTIC_BUDGET` |
  | 60 s | 57.57 s | 52.28 s | 5.29 s | 90.00 s | 58.1 % | 59.5 % | 30.6001 / 30.6000 | 27 | 1,524,113,161 | `DETERMINISTIC_BUDGET` |

  Three findings, and the first corrects an earlier assumption:

  1. **Backstop pressure falls as `T` grows** (69.2 % → 59.5 % of stage 1's share), so the risk is at
     *small* `T`, not large. Deferred follow-up 6 was written the other way round and is corrected
     there.
  2. **Model-build time is ~5.3 s and independent of `T`**, and it is *not* covered by the backstop —
     the backstop bounds CP-SAT's `Solve()` calls only. So end-to-end wall exceeds the whole-request
     ceiling at `T = 6` (11.47 s against 9.00 s) while both stages still stop on their work budgets
     and correctly classify `DETERMINISTIC_BUDGET`. Comparing end-to-end wall against the backstop is
     the wrong comparison, which is why the script now reports both separately.
  3. **Quality improves with `T`, no regression**: 24 wells at 6 s → 27 at 60 s. Cost rises with the
     extra wells drilled, as it must. Property 4's `1.2 x T` bound is not asserted — it is superseded
     — and `T = 60` lands at 57.57 s end-to-end anyway, inside `T`.

  Not measured: `T` = 300 s and above. That is deferred follow-up 6, which names the ladder and the
  exact ratio to watch.

- [x] 10. Verification — on-VM determinism check command

  - Create `scheduler/management/commands/check_determinism.py`, alongside the existing commands
    (`refresh_ilm_cache.py`, `load_all_data.py`, … — verified)
  - Usage: `python manage.py check_determinism --schedule-id <uuid> --runs 5 [--under-load]`
  - Re-solve an existing schedule's exact rig/well/FY/time-limit selection N times and print a table
    of `schedule_hash`, `model_fingerprint`, `solver_fingerprint`, `objective_value`, `stop_reason`,
    `deterministic_time_used` and `wall_time`
  - Exit non-zero if more than one distinct `schedule_hash` appears
  - **Writes nothing to the database** — read-only re-solve, so it is safe to run on the VM against
    production data
  - `--under-load` saturates the cores for some of the runs, so the command verifies the
    requirement's own criterion — "the same selection under heavy CPU load yields the same
    `schedule_hash`" — on the real host with real data, which the unit tests cannot do. Same host,
    varying load, is the scope that matters
  - Run it on the VM after the task 8 migration is applied, both idle and with `--under-load`
  - _Requirements: 2.1, 2.3, 2.12_

  **DELIVERED — `scheduler/management/commands/check_determinism.py`.**

  Interface: `--schedule-id <uuid>` (or `--latest`, or `--list` to see what is re-solvable),
  `--runs N` (default 3, **refuses N < 2** — one run cannot demonstrate reproducibility, which is
  exactly why the badge is only advisory), `--under-load` with `--load-workers` (default
  `cpu_count - 1`, leaving a core for the solve), and `--time-limit` to override the limit recorded
  on the row.

  Exit codes: `0` one hash, `1` more than one distinct `schedule_hash` **or** more than one distinct
  `model_fingerprint`, `2` could not run. The two failure causes are reported differently on
  purpose: differing fingerprints mean the solver was asked a *different question* each time (an
  input-ordering defect), while one fingerprint and several hashes mean the *search* diverged.
  Conflating them would send an operator looking in the wrong place.

  **Read-only, enforced rather than intended.** Nothing calls `save()`, and the whole run is
  additionally wrapped in a transaction closed with `transaction.set_rollback(True)`, so even a
  future code path that tried to write could not leave anything behind. `test_it_writes_nothing`
  asserts row counts and eleven fields of the target row are unchanged afterwards.

  The re-solve mirrors `create_schedule` exactly — `ScheduleRig`/`ScheduleWell` →
  `order_by('name', 'id')` → `.values()` → `parse_financial_year` → `DrillingScheduler` →
  `solve(deterministic=True)` — because a re-solve that fed a differently-ordered or
  differently-shaped frame would not be re-solving the same request, and a hash mismatch would then
  say nothing about the solver. `test_the_resolve_agrees_with_the_stored_hash` guards that: on an
  unchanged database the re-solve must reproduce the stored hash.

  Verified output (`--runs 4 --under-load --load-workers 4`, unique-optimum target, test database):

  ```
  runs            : 4  (last 2 under CPU load, 4 burners)
  stored hash     : 0dcdf8e6ecc66b25      stored stop : OPTIMAL_PROVEN
   run  load schedule_hash               objective  det used  wall (s)  asgn stop reason     det?
     1     N 0dcdf8e6ecc66b25          698,525,729    0.0007      0.06     4 OPTIMAL_PROVEN     Y
     2     N 0dcdf8e6ecc66b25          698,525,729    0.0007      0.05     4 OPTIMAL_PROVEN     Y
     3     Y 0dcdf8e6ecc66b25          698,525,729    0.0007      0.06     4 OPTIMAL_PROVEN     Y
     4     Y 0dcdf8e6ecc66b25          698,525,729    0.0007      0.06     4 OPTIMAL_PROVEN     Y
    distinct schedule_hash : 1 ['0dcdf8e6ecc66b25']   model_fingerprint : 1   solver_fingerprint : 1
    deterministic_time spread : 0.0000
  PASS: 4 runs, one schedule (0dcdf8e6ecc66b25), including 2 under CPU load.
  ```

  Tests: `scheduler/tests/test_check_determinism.py`, 10 tests, green. Includes the **failure
  path** — patched at the solve boundary to force two different hashes, because no input reliably
  produces a non-deterministic result any more, and a verification tool whose failure branch is
  never executed is a tool that reports success. Also pins a real defect found and fixed during this
  task: `--runs 4 --under-load` reported "last 2 under CPU load" while actually loading three.

  **Not run against `idrs_db`.** The development database does not have migration 0063 applied, per
  the user's instruction, so `manage.py check_determinism` against it fails on the missing
  `stop_reason` column until the migration is deployed. That is the expected state, and it is also
  incidental proof that the command reads the new columns. It is exercised against the test
  database, where the runner applies 0063.

- [x] 11. Checkpoint - Ensure all tests pass

  - `python manage.py test scheduler.tests` green, including `IDRS_TEST_CPU_LOAD=1` for the
    under-load runs — the design records this as required before sign-off
  - Every verification criterion from `bugfix.md` confirmed: 10 runs → one `schedule_hash` including
    `FEASIBLE` runs; same hash under load; the repeat-run test exists and fails on a second hash;
    tie enumeration reports exactly one schedule; a representative run finishes inside the selected
    limit assigning no fewer wells at no greater cost; backstop-bound runs are flagged
  - Migration `0063` applied on the VM and `check_determinism` passing there
  - Clean up any temporary scripts used during exploration; the committed tests are the artefact
  - Ask the user if questions arise.

  **CHECKPOINT PASSED.**

  | criterion | result |
  |---|---|
  | `manage.py test scheduler.tests` with `IDRS_TEST_CPU_LOAD=1` | **111 tests, OK, 0 failures, 0 skips** |
  | Repeat-run harness, 5 idle + 5 mixed (4 burners) | 1 `schedule_hash`, 1 `objective_value`, `deterministic_time` spread **0.0000** (3.0600 flat) |
  | Preservation goldens | **9/9 green**; diff audit against the pre-rebaseline backup: 306 leaf fields before and after, **0 added, 0 removed, 2 changed** — the two task-7 `model_fingerprint` values and nothing else |
  | Migration 0063 reverses cleanly | **Confirmed live**, `0062 → 0063 → 0062 → 0063` on a throwaway database: 6 columns added (all `nullable=YES`, `default=None`), all 6 dropped on reverse with the row intact, all 6 restored on re-apply |
  | Pre-0063 rows read back with nulls | **Confirmed live**: a row inserted at 0062 reads back after 0063 with all six fields `None`, no error, and `deterministic_stop is None` rather than `False` |
  | Temporary scripts cleaned up | `/tmp` clear of every harness, probe, audit and log artefact; `scheduler/tests/` holds only committed modules |
  | Deferred follow-ups | **7**, intact |

  Two deviations from this task's own wording, both deliberate and both decided earlier by the user:

  * "tie enumeration reports **exactly one** schedule" — it reports **4**, by the Option B decision
    recorded against task 4. The four are interchangeable permutations of a symmetric model,
    same-machine reproducibility is met and measured, and canonicality was de-scoped (clause 2.5.2).
  * "Migration `0063` applied on the VM and `check_determinism` passing there" — **not done, by
    instruction.** 0063 is generated, its round-trip verified, and the command is tested against the
    test database. Applying it on the VM is the user's own deployment step.

---

## Deferred follow-ups (out of scope for this spec)

Seven distinct items surfaced while implementing tasks 3-8. None of them is required by
`bugfix.md`'s clauses, each one needs its own change with its own verification, and each is recorded
here rather than folded into a task so nothing is silently dropped. For each: **what** it is,
**where** it lives, **why** it was deferred, and **what fixing it involves**.

### 1. `Well.name` has no uniqueness constraint

- **What.** The optimizer identifies every well by `name` — the assignment / start / end / interval
  variable dicts, the distance matrix index and columns, the per-rig ILM matrices, the circuit arcs,
  every objective term, the extraction lookup and the assignment payload the save path consumes are
  all keyed on it — while the database permits two wells to share a name.
- **Where.** `scheduler/models.py`, `Well.name` (no `unique=True`, and no
  `unique_together('location', 'name')` on `Well.Meta`). Contrast `Rig.name`, which **is** unique.
- **Why deferred.** This is task **6.5**, deliberately not implemented. The migration can fail on
  live data: any existing duplicate pair makes `AddConstraint` error out mid-migrate, and the VM's
  data is not known to be clean. It needs a data-cleanup step ahead of the constraint, plus a
  management command to report existing duplicates so an operator can resolve them before the
  migration runs. That is a different change with a different risk profile from a runtime guard.
- **What fixing it involves.** (a) A management command, e.g.
  `scheduler/management/commands/report_duplicate_wells.py`, grouping `Well` by
  `('location', 'name')` and printing every group with `count > 1` together with each row's `sn` and
  `id`; (b) an operator-run cleanup using its output; (c) a migration adding
  `unique_together = ['location', 'name']` (location-scoped is the safer choice — a global
  `unique=True` may be false for legitimately reused names across locations); (d) mapping
  `IntegrityError` on that constraint to a friendly message in the well create/update paths.
- **Status.** Task 6 (implemented) rejects duplicates at **runtime** in
  `DrillingScheduler._reject_duplicate_names` and at the API boundary in
  `ScheduleViewSet.create_schedule`, so the fatal path is closed. The DB constraint is the real
  fix and remains outstanding.

### 2. Two unhardened `well_start_date` sort sites in `views.py`

- **What.** Two remaining `sort(key=lambda x: x['well_start_date'])` calls on assignment lists. The
  key is not total: two assignments sharing a start date keep whatever relative order the list
  happened to have, which is the same latent hazard task 5.4 closed elsewhere.
- **Where.** `scheduler/views.py` — the locked-actuals `assignments_by_rig` loop, and one inside the
  SEM-facing reschedule branch. (The two *live* `sequence_order` derivations — in
  `create_schedule`'s save path and the reschedule save path — **were** hardened by task 5.4 to
  `(x['well_start_date'], x['well'])`.)
- **Why deferred.** Design decision 6 enumerates the sites to change and these two are not among
  them. Task 5 was flagged **⚠️ REVIEW REQUIRED**, and widening a review-flagged task's blast radius
  beyond its authorised list without asking is the wrong trade. Note the hazard is latent rather
  than live today: per-rig `AddNoOverlap` makes same-rig start-date ties impossible in a solved
  schedule, so nothing currently reaches these sites with a tie.
- **What fixing it involves.** The same one-line change at each site — make the key
  `(x['well_start_date'], x['well'])` — plus a test that constructs a same-start-date pair on one
  rig and asserts the resulting order is stable across repeated runs. No migration, no contract
  change.

### 3. `RigBuildingAdjustment.id` is a random UUID, so tied-rule ordering is per-database

- **What.** Task 5.3 appended `id` to the rule fetch order, making `('-priority', 'category', 'id')`
  a **total** key. Total and stable is enough for the requirement's own criterion — same machine,
  same schedule — but `id` is a `UUIDField` defaulting to `uuid.uuid4`, i.e. a *random* key with no
  relationship to the rule's content. So the same logical rule set held in two databases (dev vs
  the VM), or the same rules re-imported into one, can order tied rules differently. Because
  `calculate_ilm_days` applies the first matching `replace` rule and then latches `base_replaced`,
  a different tied order means a different ILM day count, a different gap constraint and therefore
  a different schedule.
- **Where.** `scheduler/models.py`, `RigBuildingAdjustment.id`; the six ordered fetches carrying
  `'id'` (2 in `scheduler/views.py` — `calculate_ilm_days` and `refresh_ilm_cache_for_location`; 4
  in `scheduler/models.py`'s `WellPairDistance` helpers).
- **Why deferred.** Clause 2.10 specifies `('-priority', 'category', 'id')` and that is exactly what
  was implemented. Cross-environment reproducibility is a **stronger** property than the requirement
  asks for, and adding a content component changes which rule wins on tied input — i.e. it can
  change existing ILM values on real data. Not this spec's key; not added.
- **What fixing it involves.** Put a content component ahead of `id` in the key — `condition` is the
  natural choice, giving `('-priority', 'category', 'condition', 'id')` — at all six sites, and
  re-run the ILM cache refresh so the cached `WellPairDistance` values are rebuilt under the new
  order. Needs measurement on real data first: any location with tied rules whose `condition`
  ordering disagrees with its `id` ordering will see its ILM days change.

### 4. Two pre-existing key-mismatch defects captured as-is in the preservation goldens

- **What.** Two independent producer/consumer key mismatches, both currently visible to users:
  - **(a) Every rejection reason is an error string.** `UnassignedWell.reason` persists as
    `"Analysis error: 'capacity_hp'"`. `WellRejectionAnalyzer` reads a `capacity_hp` column from the
    rigs frame while `views.py` builds that frame with `rig_capacity_hp`, so the lookup raises
    `KeyError` and a broad `except` turns it into the stored text. The user is shown an internal
    error where an explanation of *why the well could not be scheduled* belongs.
  - **(b) `Schedule.unassigned_wells_count` is always 0.** `views.py` reads
    `results['unassigned_wells_count']` with a `.get(..., 0)` default, while `_extract_solution`
    publishes the value under `wells_unassigned_count`. The default always wins, so the persisted
    count is 0 even when `UnassignedWell` rows exist.
- **Where.** (a) `scheduler/well_rejection_analyzer.py` (`WellRejectionAnalyzer.analyze_well_rejection`,
  the `capacity_hp` read) against `scheduler/views.py`'s analyzer-frame construction
  (`rig_capacity_hp`). (b) `scheduler/views.py`'s `create_schedule` save path against
  `DrillingScheduler._extract_solution` in `scheduler/optimization.py`.
- **Why deferred.** Task 2 was a capture task, and **Property 2 preserves today's *behaviour*, not
  today's intentions**. Both defects were therefore recorded into
  `scheduler/tests/fixtures/preservation_golden.json` exactly as the unfixed code produces them —
  deliberately, and documented in `SavePathPreservationTests.test_save_path_matches_golden`'s
  docstring. Fixing either one *inside* this spec would have made the golden disagree with the code
  it was supposed to pin, destroying the baseline every later task is verified against.
- **What fixing it involves.** (a) Align the column name — either rename the frame column to
  `capacity_hp` at the build site or read `rig_capacity_hp` in the analyzer — and narrow the broad
  `except` so a future mismatch fails loudly rather than being stored as prose. (b) Read
  `wells_unassigned_count` (or publish both keys during a transition). Both then require
  **re-capturing the affected golden values**, which must be a deliberate, reviewed step with the
  regeneration guard's drift report attached — see `scheduler/tests/golden.py` before reaching for
  `IDRS_REGENERATE_GOLDEN`.

### 5. Big-M padding in the tie-break objective is loose

- **What.** `max_order_tiebreak` is padded with `num_pairs × num_pairs` where the tight bound is
  `num_wells × num_pairs`. A looser Big-M means weaker LP relaxations and a slower solve; it does
  **not** make the answer wrong.
- **Where.** `scheduler/optimization.py`, the `max_order_tiebreak` derivation in the objective
  construction (located by name — the line numbers in the design text are stale).
- **Why deferred.** Task 4 deliberately did not tighten it. That expression is a **coefficient of
  stage 1's objective**, so changing it changes the objective's numeric value and the model proto:
  tightening it moved the preservation golden's `objective_value` from **698,525,729** to
  **698,525,679** and changed the model fingerprint. That is a Property 2 violation for a
  performance-only gain. The tight bound **is** used where it actually matters — deriving `W1`, the
  weight that has to dominate the tier below it — so correctness of the tier separation does not
  depend on the padding.
- **What fixing it involves.** Replace the padding with `num_wells × num_pairs`, then re-capture the
  preservation golden's `objective_value` and `model_fingerprint` (same deliberate, reviewed
  re-capture as item 4), and measure the solve-time gain on a representative set to confirm the
  change buys something. Design decision 3 already flags this as separate work.

### 6. Task 7's wall-time overhead is unmeasured at larger `T`

- **What.** The decision strategy costs about +16 % wall time (idle 4.517 s → 5.247 s mean at
  `T = 6 s`, loaded 4.665 s → 5.385 s). It is **not** extra search — `deterministic_time` is
  identical at 3.0600 in every run — but per-solve overhead from the larger model proto and from
  presolve remapping 480 extra strategy expressions. Accepted on the measurement: quality improved
  (wells assigned 23 → 24, objective -5.10 %, cost per well -2.91 %), and the worst observed wall
  time is 5.44 s against stage 1's 7.65 s backstop, i.e. 71 %, with every run still classifying
  `DETERMINISTIC_BUDGET` rather than `WALL_CLOCK_BACKSTOP`. Clause 3.9 is satisfied.
- **Where.** `DrillingScheduler._add_decision_strategy`, and the backstop arithmetic in
  `calibrate_two_stage_budgets` it has to fit inside.
- **Why deferred.** There is nothing to fix: the overhead is real, bounded and paid for. What is
  missing is a measurement at the time limits production actually uses.
- **CORRECTED by the task 9.4 measurement.** This item was originally written expecting wall time to
  creep towards the backstop *as `T` grows*. The measurement says the opposite: stage-1 solver wall
  against stage 1's own backstop share falls from 69.2 % at `T = 6 s` to 59.5 % at `T = 60 s`. The
  reason is that the expensive part is **fixed**: model build is ~5.3 s regardless of `T` (frames,
  distance matrix, per-rig ILM matrices, constraints, objective, and the 480 decision-strategy
  expressions), so it amortises as `T` grows. **The pressure is at small `T`, not large.**
  A second finding from the same measurement: the backstop bounds CP-SAT's `Solve()` calls only, so
  model-build time is unbudgeted and end-to-end wall can exceed the whole-request ceiling
  (11.47 s against 9.00 s at `T = 6`) while both stages still stop on their work budgets and
  correctly classify `DETERMINISTIC_BUDGET`. End-to-end wall against the backstop is the wrong
  comparison.
- **What fixing it involves.** Run `scheduler/tests/measure_performance.py` at the realistic ladder
  (`T` = 300 / 900 / 1800 s) on a production-sized rig and well set, and read the `s1/s1bs` column —
  stage-1 solver wall against `0.85 × WALL_BACKSTOP_FACTOR × T` — against the 0.98 threshold that
  classifies `WALL_CLOCK_BACKSTOP`. Use *solver* wall, not end-to-end, per the correction above. On
  the evidence so far this ratio falls with `T`, so the expected outcome is more headroom, not less;
  the measurement is to confirm that on a bigger model, where build time and per-solve overhead both
  grow with `wells × rigs`. If the ratio ever does approach 1, the lever is `WALL_BACKSTOP_FACTOR`
  (already documented as sized from measured contention, so re-sizing it is expected maintenance) —
  not removing the decision strategy, which is what bought the extra well.
- **Status.** Raised by the user when accepting task 7: "if wall time ever creeps toward the backstop
  at larger T we revisit." Partially discharged by task 9.4 at `T` = 6 s and 60 s, which corrected
  the direction of the concern; `T` = 300 s and above remain unmeasured.

### 7. `.venv` was copied rather than recreated, so `.venv/bin/pip` is broken

- **What.** `.venv/bin/pip` fails on every invocation. Its shebang points at
  `/Users/subratsingh/Desktop/1. WebApp Developments/11. Interactive Drilling Rig Scheduler/IDRS v9/.venv/bin/python3.13`,
  which does not exist — the virtualenv was copied from an **IDRS v9** directory instead of being
  created in place, and console-script shebangs carry absolute interpreter paths. The error is
  `cannot execute: No such file or directory`, which reads like a missing pip rather than a stale
  path, so it is easy to misdiagnose.
- **Where.** `.venv/bin/pip`, and by the same mechanism every other console script in `.venv/bin/`
  (`pip3`, `django-admin`, and anything else installed with an entry point). `.venv/bin/python`
  itself is fine, so the environment is fully usable.
- **Why deferred.** Nothing in this spec needs it: `.venv/bin/python -m pip` bypasses the broken
  shim entirely and is what was used to install and pin `hypothesis==6.167.1`. Recreating the
  virtualenv is also not a free action — it would re-resolve every pin in `requirements.txt` on a
  machine where the current set is known to work, which is a change with its own verification
  burden and no bearing on determinism. Explicitly left alone at the user's instruction.
- **What fixing it involves.** Either recreate the environment
  (`python3.13 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt`) and re-run the
  suite to confirm the pins still resolve, or repair the shebangs in place with
  `.venv/bin/python -m pip install --force-reinstall pip`. The first is cleaner; the second is
  narrower. Until then, prefer `.venv/bin/python -m pip` over `.venv/bin/pip` in any documentation
  or script that touches this environment.
- **Status.** Recorded at the user's instruction while approving task 8 setup: "Record the broken
  `.venv/bin/pip` / copied-venv issue as follow-up #7 — don't fix it."
