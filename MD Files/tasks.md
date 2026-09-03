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

- [ ] 1. Write bug condition exploration harness

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

- [ ] 2. Capture golden preservation fixtures from the CURRENT code (BEFORE implementing any fix)

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

- [ ] 3. Fix — stopping criterion: deterministic time becomes the binding limit (design decision 1 + 2)

  **⚠️ REVIEW REQUIRED — may change existing schedule output.** This changes how much search is
  performed inside the user's time limit, so any request that does not prove optimality today can
  return a different (reproducible) schedule. This is the load-bearing change and lands alone so it
  is independently attributable.

  - [ ] 3.1 Add the `IDRS_SOLVER_DETERMINISM` settings block
    - `drilling_scheduler/settings.py`, alongside the existing `VIDEO_PROCESSING` dict precedent
      (verified at `:227`)
    - `DETERMINISTIC_TIME_RATIO` (env `IDRS_DETERMINISTIC_TIME_RATIO`, default `0.60`),
      `WALL_BACKSTOP_FACTOR` (default `1.15`, must stay ≤ 1.2 per Property 4),
      `CANONICALIZE_BUDGET_SHARE` (default `0.15`), `FIXED_SEARCH` (default `False`)
    - Document in the comment that `DETERMINISTIC_TIME_RATIO` is a **schedule-affecting**
      configuration change, not a performance knob: tuning it changes how much search is done and
      therefore can change the answer. It belongs in the solver fingerprint (task 8)
    - _Requirements: 2.2, 2.4, 2.7_

  - [ ] 3.2 Replace the wall-clock stop with the deterministic budget
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
    - Note the scope of the guarantee in a docstring: identical results for a fixed
      `(OR-Tools build, platform)` — `ortools==9.15.6755` pinned at `requirements.txt:21` (verified)
      — not across CPU architectures, since CP-SAT's LP layer is double-precision
    - _Bug_Condition: `isBugCondition(X)` where `stopsOnWallClock` — `solveStatus(F, X) ≠ OPTIMAL`_
    - _Expected_Behavior: every run performs exactly the same amount of search, so the incumbent at
      the stop is reproducible_
    - _Preservation: a request that proves `OPTIMAL` inside `D` is unaffected — the proof needs no
      budget_
    - _Requirements: 2.2, 2.3, 2.4, 3.4, 3.9_

  - [ ] 3.3 Implement stop-reason classification
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

  - [ ] 3.4 Unit tests for calibration and classification
    - Budget calibration `T → (D, backstop)` for every dropdown value at
      `templates/scheduler/scheduling.html:447-459`, including `RATIO` and `WALL_BACKSTOP_FACTOR`
      overrides, asserting the backstop never exceeds `1.2 × T`
    - Table-driven stop-reason classification over `(status, deterministic_time, wall_time, D,
      backstop)` covering all five outcomes and the `0.995` / `0.98` boundaries
    - `test_stop_reason_is_deterministic_budget` — an open model reports
      `deterministic_stop is True` and `stop_reason == 'DETERMINISTIC_BUDGET'`
    - `test_wall_backstop_is_flagged` — `override_settings` with a tiny `WALL_BACKSTOP_FACTOR` so
      the backstop binds; assert `deterministic_stop is False` and
      `stop_reason == 'WALL_CLOCK_BACKSTOP'`. Proves the flag fires rather than being dead code
    - `test_wall_time_within_tolerance` — total wall time ≤ `time_limit_seconds × 1.2`
    - Independently runnable: `python manage.py test scheduler.tests.test_determinism`
    - _Requirements: 2.4, 3.9_

  - [ ] 3.5 Verify the repeat-run harness now passes
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

  - [ ] 3.6 Verify preservation goldens still pass
    - **Property 2: Preservation** - Unique proven optima are untouched
    - **IMPORTANT**: Re-run the SAME tests from task 2 — do NOT write new tests
    - **EXPECTED OUTCOME**: PASS. Proven-optimal models, performance mode and locked actuals all
      match the goldens captured from the pre-fix code
    - _Requirements: 3.1, 3.4, 3.8, 3.9, 3.12_

- [ ] 4. Fix — two-stage lexicographic solve for canonical tie-break selection (design decision 3)

  **⚠️ REVIEW REQUIRED — may change existing schedule output.** Stage 2 selects a canonical member
  of the tied optimal set, so requests with tied optima will return different assignments than
  today. The `objective_value` is preserved by construction (stage 1 is byte-identical to today's
  objective and stage 2 pins it as an equality), so clause 3.8 holds literally. Layered on top of
  task 3 and only after 3.5 and 3.6 pass.

  - [ ] 4.1 Split the objective into P-expr and T-expr
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

  - [ ] 4.2 Implement the stage-2 canonicalising solve
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

  - [ ] 4.3 Route `solve_with_actuals` through the same two stages
    - `scheduler/optimization.py:1514-1573`
    - SEM re-optimization (`scheduler/sem_views.py:1125-1131`) and the locked-actuals path inherit
      the guarantee
    - Stage 2 must not move a pinned well; `fixed_actuals` stays sorted by `(well, rig)` (`:1527-1528`)
    - _Requirements: 3.10, 3.11_

  - [ ] 4.4 Fix metric provenance in `_extract_solution`
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

  - [ ] 4.5 Unit tests for the two-stage structure
    - Tie-break weight derivation: `W₁ > max(rig_well_order)` across a range of well/rig counts, and
      the stage-2 objective maximum stays inside a safe coefficient bound
    - Stage-2 fallback: inject a contradictory extra constraint to force stage 2 `INFEASIBLE`;
      assert the stage-1 solution is returned intact and `canonicalization_status` reports the failure
    - Stage-1 metric provenance: `objective_value`, `best_bound`, `optimality_gap` and
      `solver_status` in the payload come from stage 1, not stage 2
    - Budget monotonicity: a larger `time_limit_seconds` never produces a worse objective — catches
      a stage-split or calibration mistake that starves the search
    - _Requirements: 2.5, 3.6, 3.8_

  - [ ] 4.6 Verify the tie-enumeration test now passes
    - **Property 1: Expected Behavior** - Repeated runs return one schedule
    - **IMPORTANT**: Re-run the SAME test from task 1 — do NOT write a new test
    - Solve stage 1 for `V*`, stage 2 for `T*`, then build a third model constrained to
      `P-expr == V*` **and** `T-expr == T*`, enumerate with `num_search_workers = 1`, and assert
      exactly 1 distinct `schedule_hash`
    - Also log the distinct count at `P-expr == V*` alone — expected > 1, that is the tied set — so
      the test documents what the canonicalisation is doing rather than just asserting a number
    - **EXPECTED OUTCOME**: PASS, count exactly 1 (was 10 on this model in task 1)
    - If the count is > 1, that is the trigger to add the third tie-break tier (arc-order index over
      `circuit_arcs`, design decision 3) — not a reason to weaken the assertion
    - _Requirements: Property 1 (validates 2.5), 2.12_

  - [ ] 4.7 Verify preservation goldens still pass
    - **Property 2: Preservation** - Unique proven optima are untouched
    - **IMPORTANT**: Re-run the SAME tests from task 2 — do NOT write new tests
    - **EXPECTED OUTCOME**: PASS. This is the test that catches stage 2 changing an answer it should
      not touch — assignments **and** `objective_value` identical to the goldens
    - _Requirements: 3.6, 3.7, 3.8, 3.10, 3.11, 3.12, 3.13_

- [ ] 5. Fix — ordering hardening (design decision 6)

  **⚠️ REVIEW REQUIRED — may change existing schedule output.** Replaces ties currently resolved by
  the database or by an unstable sort with total orderings. Output can change on inputs that have
  duplicate well names, tied `RigBuildingAdjustment` rows, or overlapping `WellPairDistance` rows.

  - [ ] 5.1 Total orderings on the querysets
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

  - [ ] 5.2 Stable, total pandas sorts
    - `scheduler/optimization.py:686-687` (verified) — sort on `["name", "id"]` when `id` is present,
      with `kind="stable"`, then `reset_index(drop=True)`
    - `kind="stable"` alone is **not** sufficient: a stable sort preserves the input order of tied
      rows, so it only helps when the input order is already total. The `id` column is what makes
      the key total; the stable kind covers frames arriving without it
    - Preserves the existing ordering fix at `:686-693` rather than replacing it (clause 3.1)
    - _Requirements: 2.8, 3.1_

  - [ ] 5.3 `RigBuildingAdjustment` rule ordering
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

  - [ ] 5.4 `WellPairDistance` fetch order and assignment-list sort keys
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

  - [ ] 5.5 Verify ordering invariance and preservation
    - **Property 2: Preservation** - Unchanged behaviour is preserved
    - Re-run the task 2 goldens and the task 1 repeat-run harness
    - Add `scheduler/tests/test_ordering.py` cases: two `RigBuildingAdjustment` rows with equal
      `priority` and `category` → `calculate_ilm_days` returns the same value regardless of
      insertion order and the applied rule is the lower `id`; two `WellPairDistance` rows covering
      the same name pair → the ILM matrix value is stable across repeated
      `_calculate_ilm_days_matrix()` calls
    - **EXPECTED OUTCOME**: goldens PASS, new ordering tests PASS
    - _Requirements: Property 5 (validates 2.8, 2.10), 3.1, 3.2_

- [ ] 6. Fix — reject duplicate well names (design decision 5)

  **⚠️ REVIEW REQUIRED — changes behaviour on an error path.** A run with duplicate well names is
  refused up front instead of silently collapsing wells. Note this state is already fatal today —
  `wells.get(name=...)` at `scheduler/views.py:1988` raises `MultipleObjectsReturned` inside
  `transaction.atomic()`, so the save already aborts, just opaquely and after the solve has been
  paid for.

  - [ ] 6.1 Add the invariant in `preprocess_data`
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

  - [ ] 6.2 Reject at the API boundary with an actionable message
    - `scheduler/views.py` — `ScheduleViewSet.create_schedule`, before creating the `Schedule` row
      (`:1911-1913`): check the selected wells for duplicate names, return HTTP 400 naming them, and
      leave no `FAILED` schedule row behind. The optimizer check is the invariant; this one is the
      user experience
    - Map `DuplicateWellNameError` through `_friendly_error_message` so the existing exception
      handler at `views.py:2100-2110` produces a clear message on the other call paths
    - _Requirements: 2.9_

  - [ ] 6.3 Delete the dead `well_name_to_obj` lookup
    - `scheduler/optimization.py:744-754` — built with `WellModel.objects.get(name=wname)` and never
      read. With duplicate names that `get` raises `MultipleObjectsReturned`, which the outer
      `except Exception` at `:753` swallows after aborting the loop. Harmless today only because the
      dict is unused. One fewer name-keyed lookup and one fewer swallowed exception
    - _Requirements: 2.9_

  - [ ] 6.4 Verify duplicate rejection
    - **Property 5: Total input ordering** - duplicates are rejected
    - `scheduler/tests/test_ordering.py`: two wells sharing a `name` → `preprocess_data()` raises
      `DuplicateWellNameError` naming **both**; `create_schedule` returns 400 with the names; no
      `Schedule` row is left behind
    - Re-run the task 2 goldens — no non-duplicate input may be affected
    - **EXPECTED OUTCOME**: new tests PASS, goldens PASS
    - _Requirements: Property 5 (validates 2.9)_

  - [ ] 6.5 Raise the out-of-scope follow-up, do not implement it
    - A `unique=True` (or `unique_together('location', 'name')`) constraint on `Well.name`
      (`scheduler/models.py:394`) plus a management command to report existing duplicates. The
      migration can fail on live data, so it needs its own change with a data-cleanup step
    - Record it as a follow-up; explicitly out of scope here
    - _Requirements: 2.9_

- [ ] 7. Fix — canonical decision strategy, `FIXED_SEARCH` off by default (design decision 4)

  **⚠️ REVIEW REQUIRED — may change existing schedule output.** Adds a first-branch preference, so
  a timed-out run can return a different incumbent. `AUTOMATIC_SEARCH` is retained, so the strategy
  is a hint rather than a mandate.

  - [ ] 7.1 Give `_add_decision_strategy` a real body
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

  - [ ] 7.2 Expose `FIXED_SEARCH` as an off-by-default setting
    - `IDRS_SOLVER_DETERMINISM['FIXED_SEARCH']` from task 3.1, for audit runs where path stability
      matters more than quality
    - Its cost is now **bounded**, a direct consequence of task 3: with a work-based budget a slower
      search cannot overrun the wall clock, it returns a worse incumbent within the same budget.
      That converts an unbounded risk into a measurable quality tradeoff, and is why this knob can
      exist at all
    - Because it changes the answer, it belongs in the solver fingerprint (task 8)
    - _Requirements: 2.7_

  - [ ] 7.3 Check the presolve interaction
    - Presolve remaps variables and decision strategies over variables presolve removes are handled
      by CP-SAT, but verify `cp_model_presolve = True` (`:981`) stays on and that no warning appears
      in the solver log
    - _Requirements: 2.6_

  - [ ] 7.4 Verify strategy, determinism and preservation
    - **Property 1: Expected Behavior** / **Property 2: Preservation**
    - Unit test: `_add_decision_strategy` adds exactly two strategies in canonical `(well, rig)`
      order, and `search_branching` remains `AUTOMATIC_SEARCH` unless `FIXED_SEARCH` is enabled
    - Re-run the task 1 repeat-run harness and the task 2 goldens
    - Measure solve time against the pre-task-7 baseline on a representative rig/well set — clause
      2.7 requires the fix be measured, not assumed, and clause 3.9 requires no material regression
      in wells assigned or total cost
    - **EXPECTED OUTCOME**: harness PASS, goldens PASS, no material runtime regression
    - _Requirements: 2.6, 2.7, 3.9_

- [ ] 8. Fix — observability and provenance persistence (design decision 7)

  **⚠️ REVIEW REQUIRED — DATABASE SCHEMA CHANGE.** Migration `0063_add_determinism_provenance.py`
  adds six nullable fields to `Schedule`. Additive and reversible, no data backfill, but it must be
  applied on the VM (`Install Windows/apply_migrations.bat`). Latest existing migration is
  `0062_add_schedule_input_metadata.py` (verified), so `0063` is the correct number.

  - [ ] 8.1 Add provenance to the result payload
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

  - [ ] 8.2 Persist the provenance fields — SCHEMA CHANGE
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

  - [ ] 8.3 Surface the fields through the API
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

  - [ ] 8.4 Render provenance on the schedule detail page
    - `templates/scheduler/schedule_detail.html` — the metadata block at `:393-421` already renders
      Optimality Gap and Schedule Hash in a two-column row. Add a third row: Model Fingerprint as a
      `<code>` element next to the existing hash, and a Reproducibility badge from `stop_reason` —
      green for `OPTIMAL_PROVEN` and `DETERMINISTIC_BUDGET`, amber for `WALL_CLOCK_BACKSTOP` with
      the text "stopped on the wall-clock backstop — this run is not guaranteed reproducible",
      muted for the rest
    - Show `deterministic_time_used` / `deterministic_budget` as small muted text beside it
    - Keep the badge accessible: convey the state in text as well as colour, and give the badge an
      appropriate ARIA label rather than relying on colour alone
    - _Requirements: 2.11_

  - [ ] 8.5 Surface provenance on the scheduling page
    - `templates/scheduler/scheduling.html` — `showResults()` (`:1275-1296`) currently reads only
      assignments, unassigned, cost and solve time from the response
    - Add the schedule hash (truncated, `title` with the full value), the model fingerprint, and a
      warning line rendered **only** when `result.deterministic_stop === false`
    - Follow the existing escaping pattern at `:1315-1317` for any interpolated text
    - _Requirements: 2.11_

  - [ ] 8.6 Verify fingerprints and provenance
    - **Property 6: Provenance is surfaced**
    - Unit tests: identical inputs give identical `model_fingerprint` and `solver_fingerprint`;
      changing `DETERMINISTIC_TIME_RATIO` or `FIXED_SEARCH` changes `solver_fingerprint` and leaves
      `model_fingerprint` alone
    - Integration test: the schedule detail page renders the model fingerprint, the schedule hash
      and the reproducibility badge for a completed schedule
    - `python manage.py makemigrations --check --dry-run` reports no pending changes after 8.2
    - **EXPECTED OUTCOME**: PASS
    - _Requirements: Property 6 (validates 2.11), 3.5_

- [ ] 9. Verification — full property, integration and regression suite

  - [ ] 9.1 Property-based test suite
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

  - [ ] 9.2 Confirm the residual tie count is measured, not assumed
    - Re-run `scheduler/tests/test_tie_enumeration.py` and record the two numbers it logs: the
      distinct count at `P-expr == V*` alone (the tied set, expected > 1) and at
      `(P-expr == V*) AND (T-expr == T*)` (expected exactly 1)
    - This is the measurable residual for clause 2.5, per the note at the top of this file. Record
      both numbers in the task notes so the interpretation of 2.5 stays auditable
    - _Requirements: 2.5, 2.12_

  - [ ] 9.3 Integration tests through the HTTP layer
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

  - [ ] 9.4 Performance and quality measurement on a representative set
    - **Property 4: Performance Bound**
    - Run a representative rig/well set at each Time Limit dropdown value
      (`templates/scheduler/scheduling.html:447-459`) and assert total wall time across both stages
      ≤ `time_limit_seconds × 1.2`
    - Compare wells assigned and total cost against the pre-fix baseline recorded in task 2 — no
      material regression (clauses 2.7, 3.9)
    - If the deterministic budget starves the search on this deployment, tune
      `DETERMINISTIC_TIME_RATIO` rather than reverting to a wall-clock stop, and record the value
      chosen — it is part of the solver fingerprint
    - _Requirements: 2.7, 3.9_

- [ ] 10. Verification — on-VM determinism check command

  - Create `scheduler/management/commands/check_determinism.py`, alongside the existing commands
    (`refresh_ilm_cache.py`, `load_all_data.py`, … — verified)
  - Usage: `python manage.py check_determinism --schedule-id <uuid> --runs 5 [--under-load]`
  - Re-solve an existing schedule's exact rig/well/FY/time-limit selection N times and print a table
    of `schedule_hash`, `model_fingerprint`, `solver_fingerprint`, `objective_value`, `stop_reason`,
    `deterministic_time_used` and `wall_time`
  - Exit non-zero if more than one distinct `schedule_hash` appears
  - **Writes nothing to the database** — read-only re-solve, so it is safe to run on the VM against
    production data
  - This is how the "same selection under heavy CPU load yields the same hash" and the cross-machine
    criteria get checked on the real host with real data, which the unit tests cannot do. It is also
    what makes the scoped guarantee (identical results for a fixed `(OR-Tools build, platform)`)
    confirmed rather than assumed
  - Run it on the VM after the task 8 migration is applied, both idle and with `--under-load`
  - _Requirements: 2.1, 2.3, 2.12_

- [ ] 11. Checkpoint - Ensure all tests pass

  - `python manage.py test scheduler.tests` green, including `IDRS_TEST_CPU_LOAD=1` for the
    under-load runs — the design records this as required before sign-off
  - Every verification criterion from `bugfix.md` confirmed: 10 runs → one `schedule_hash` including
    `FEASIBLE` runs; same hash under load; the repeat-run test exists and fails on a second hash;
    tie enumeration reports exactly one schedule; a representative run finishes inside the selected
    limit assigning no fewer wells at no greater cost; backstop-bound runs are flagged
  - Migration `0063` applied on the VM and `check_determinism` passing there
  - Clean up any temporary scripts used during exploration; the committed tests are the artefact
  - Ask the user if questions arise.