# Bugfix Requirements Document

## Introduction

Running a schedule from `http://127.0.0.1:8011/scheduling/` twice with the same rigs, the same
wells, the same financial year and the same time limit can produce two different schedules. The
prior determinism work is only partially present in the current code: the input-ordering fixes
survived, but the three fixes that actually pin the solver's answer were reverted or weakened.

Verified request path for the Run/Start button on the scheduling page:

| Step | Location |
|------|----------|
| Page | `scheduler/urls.py:31` → `views.scheduling` (`scheduler/views.py:457`) |
| Button POST | `templates/scheduler/scheduling.html:1079` → `/api/schedules/create_schedule/` |
| Time limit sent | `templates/scheduler/scheduling.html:1036, 1064` (dropdown at `:447`, default 300s) |
| Endpoint | `ScheduleViewSet.create_schedule` — `scheduler/views.py:1882` |
| Solver entry | `scheduler/views.py:1959` → `DrillingScheduler.solve(time_limit_seconds=…, deterministic=True)` |
| Solver | `scheduler/optimization.py:1688` (`solve`), config at `:905`, objective at `:1206` |

Audit of the previously-applied fixes against the code as it stands today:

| Prior fix | Current state | File / line |
|-----------|---------------|-------------|
| Sort DataFrames before distance + ILM matrix construction | **Present** — sort at `:686-687`, matrices built at `:690` and `:693` | `scheduler/optimization.py` |
| `.order_by('name')` on rig/well querysets feeding the scheduler | **Present** on the `/scheduling/` path | `scheduler/views.py:1912-1913`, also `:1718-1719` |
| `deterministic=True` at every call site | **Present**; also now the parameter default | `scheduler/views.py:1734, 1959, 2361, 2365, 2761, 2763, 3212, 3216`; defaults at `optimization.py:1514, 1688` |
| SHA-256 model fingerprint logging | **Present** | `scheduler/optimization.py:1735-1738`, `:1560-1563` |
| `num_search_workers = 1`, `random_seed = 42` | **Present** | `scheduler/optimization.py:932, 935` |
| `model.AddDecisionStrategy(...)` | **REVERTED — method body is `pass`** | `scheduler/optimization.py:986-996` |
| `search_branching = FIXED_SEARCH` | **REVERTED — now `AUTOMATIC_SEARCH`** | `scheduler/optimization.py:938` |
| `interleave_search = False` | **REVERTED — now `True`** | `scheduler/optimization.py:945` |
| Reproducible stopping criterion | **Absent — wall-clock `max_time_in_seconds` only**; `max_deterministic_time` explicitly rejected in a comment at `:948-954` | `scheduler/optimization.py:927, 954` |
| Strict lexicographic tie-break hierarchy | **WEAKENED — both tie-break tiers now weight 1** | `scheduler/optimization.py:1358-1359` |

Reproduction evidence gathered on this workspace (ortools 9.15.6755, `requirements.txt:21`), using a
synthetic model that mirrors the real formulation (optional intervals + `AddNoOverlap` +
per-rig `AddCircuit` + the same objective shape) and the exact parameter block from
`_configure_solver_for_determinism`:

- Same model proto fingerprint on every run (`de7ec4d44a8297a2`), 11 s wall-clock limit, machine
  under CPU load: **two different schedules** — objective `73927958` (twice) and `73867926` (once);
  reported deterministic time drifted `7.1256` → `7.3596`.
- Same model, `max_deterministic_time = 7.0` instead: deterministic time `7.0001` on every run,
  **one** schedule fingerprint, even though wall time varied 8.85–8.97 s.
- Tie enumeration on a 5-well / 2-identical-rig model: with the current weights
  (`START_TIME_WEIGHT = 1`, `RIG_WELL_ORDER_WEIGHT = 1`) **10 distinct schedules share the optimal
  objective 3244**. With the previous strictly-dominating start-time weight, 2.
- Same tied model solved along 5 different search paths: without a decision strategy, **3
  different schedules** were returned at the identical optimal objective; with
  `AddDecisionStrategy` + `FIXED_SEARCH`, **1**.

Three independent causes therefore have to be closed. Closing only the timeout cause still leaves
proven-optimal runs free to return any of the tied schedules; closing only the tie-break causes
still leaves timed-out runs varying.

### Wall time versus determinism — measured, then decided

A tight wall-time bound and same-machine determinism under load are **mutually exclusive**: holding
the *work* fixed means the *elapsed time* has to absorb the contention. Measured during
implementation on one host (12 cores, ortools 9.15.6755, the 6-rig / 40-well model, work held at a
fixed 3.6 deterministic units, 2 solves per level):

| background burners | wall_s | deterministic_time | wall per unit | wells assigned |
|---|---|---|---|---|
| 0 (idle) | 5.77 / 5.81 | 3.6000 | 1.602 / 1.613 | 23 |
| 2 | 5.77 / 5.80 | 3.6000 | 1.604 / 1.611 | 23 |
| 4 | 6.03 / 5.93 | 3.6000 | 1.674 / 1.647 | 23 |
| 8 | 6.60 / 6.49 | 3.6000 | 1.832 / 1.804 | 23 |

The work performed is identical to four decimal places at every level and so is the schedule; the
only thing load moves is elapsed time (+14 % at 8 burners). Forcing wall time under a tight
`1.2 × T` ceiling therefore requires cutting the work budget, and cutting it far enough to hold
under load (`DETERMINISTIC_TIME_RATIO = 0.15`) was reproducible but collapsed the schedule from **23
wells assigned to 1** (objective 97,768,602,348 → 223,981,623,957) — violating clause 3.9's own "no
material regression in wells assigned or total cost".

**Determinism plus full schedule quality are the binding guarantees; wall time is what gives.** The
work-budget ratio stays at 0.60, and the wall-clock ceiling is a backstop sized from measured
representative contention (`WALL_BACKSTOP_FACTOR`, currently 1.5 — at the page's default T = 300 s
that is a 450 s / 7.5 min worst case). The backstop is not the limit that decides the answer; the
work budget is. The backstop only bounds damage when the work cannot be completed, and when it fires
the run is flagged (`stop_reason = WALL_CLOCK_BACKSTOP`, `deterministic_stop = False`) rather than
silently returned — see clause 2.4. Contention beyond the representative level — around 3 background
burners per core, ≈ 7.3 s per deterministic unit, which would need a `4.4 × T` backstop — is
explicitly out of scope: there the backstop fires and the run is reported non-deterministic. That is
the documented boundary of the guarantee, not a silent failure.

### Reproducible versus canonical — measured, then decided

The tie-break work was originally written to reach "no two distinct schedules share an objective
value". Measured after the two-stage lexicographic solve was implemented, on the 5-well /
2-identical-rig model this document reproduces:

| enumerated at | count | value |
|---|---|---|
| `P-expr == V*` (the tied set) | **4** | `V* = 218,583,260` |
| `P-expr == V*` **AND** `T-expr == T*` (the canonical set) | **4** | `T* = 8,182` |

Both enumerations **exhausted** — they terminated `INFEASIBLE` with the 50-schedule cap not reached —
so 4 is exact, not a lower bound. The hierarchy is real (`W₁ = 51 > max(rig_well_order) = 50`); it
simply has nothing to bite on. All four survivors carry *identical* tie-break components
(`start_time_sum = 160`, `rig_well_order = 22`) because both tiers are **sums** and the four
schedules differ only by permuting interchangeable wells — every well duration 30, both rigs
identical — which leaves a sum invariant. Swapping W3@0 with W5@80 on one rig leaves `0 + 80`
unchanged. No linear objective built from those two sums can separate them.

**Decision taken: accept the residual and de-scope canonical path-independence.** The requirement is
same rigs, wells, financial year and time limit, same machine, same schedule every run — and that is
met and measured (the reproducible stop of 2.2, plus the repeat-run harness of 2.12 passing idle and
under representative load with one hash and zero `deterministic_time` spread). Separating four
interchangeable permutations would buy path-independence of the *choice*, not reproducibility, and it
is not worth the model complexity. Clause 2.5 states the delivered goal; 2.5.1-2.5.3 record what is
promised, what is measured, and what the escalation would be. This de-scopes canonicality, not
rigour: the hierarchy must still dominate, the enumeration must still be exhaustive, and stage 2 must
still never worsen a result.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN a schedule is run twice from `/scheduling/` with an identical rig set, well set, financial year and time limit, and the solver stops on the wall-clock limit at `scheduler/optimization.py:927` and `:954` before proving optimality, THEN the system returns whichever incumbent solution the search happened to reach in that wall-clock window, so the two runs produce different assignments and a different `schedule_hash`

1.2 WHEN the machine is under varying CPU load (other requests, other processes, a shared VM), THEN the system completes a different amount of search work inside the same wall-clock budget and the divergence in 1.1 becomes materially more likely

1.3 WHEN the search terminates with status `FEASIBLE` rather than `OPTIMAL`, THEN the system stores and displays that non-optimal incumbent as the schedule (`scheduler/views.py:1962` accepts both statuses identically) with no signal to the user that the result is not reproducible

1.4 WHEN several schedules tie at the same optimal objective value, THEN the system returns an arbitrary one of them, because `START_TIME_WEIGHT` and `RIG_WELL_ORDER_WEIGHT` are both `1` at `scheduler/optimization.py:1358-1359` and the two tie-break tiers can trade off against each other instead of forming a strict lexicographic order

1.5 WHEN the solver has to choose between tied solutions, THEN the system leaves the choice to CP-SAT's internal heuristics, because `_add_decision_strategy()` at `scheduler/optimization.py:986-996` has an empty body (`pass`) and `search_branching` is `AUTOMATIC_SEARCH` at `:938`, so no canonical variable or value order is imposed

1.6 WHEN two or more selected wells share the same `name`, THEN the system silently collides them, because `Well.name` has no `unique=True` (`scheduler/models.py:394`) while the whole optimizer keys on well name — `self.assignments[(wid, rid)]` (`optimization.py:864`), the distance and ILM matrices indexed by name (`:699-713`, `:757-761`), and `wells_df.loc[wells_df["name"] == wid].iloc[0]` (`optimization.py:1810`)

1.7 WHEN wells share a `name`, THEN the system orders them arbitrarily, because `.order_by('name')` at `scheduler/views.py:1913` leaves ties to the database and `sort_values(by="name")` at `scheduler/optimization.py:687` uses pandas' default non-stable quicksort, so the row order that feeds matrix construction can differ between runs

1.8 WHEN two `RigBuildingAdjustment` rows for a location share the same `priority` and `category`, THEN the system may compute different ILM days for the same well pair, because `order_by('-priority', 'category')` at `scheduler/views.py:10791` (and `:11087`) leaves ties unordered while `calculate_ilm_days()` applies the first `replace` rule it encounters and then sets `base_replaced`, making the outcome order-dependent and feeding a different ILM matrix into the model

1.9 WHEN a run diverges, THEN the system gives the operator no way to see it, because the model fingerprint at `scheduler/optimization.py:1738` and the schedule hash at `:1877` are only written to the log; `Schedule.schedule_hash` is persisted (`views.py:1975`) but neither hash is surfaced on the scheduling or schedule-detail pages, and nothing compares them across runs

### Expected Behavior (Correct)

2.1 WHEN a schedule is run twice from `/scheduling/` with an identical rig set, well set, financial year and time limit, THEN the system SHALL return byte-identical assignments — same well-to-rig mapping, same start and end dates, same sequence order — and therefore an identical `schedule_hash`, regardless of whether the solver proved optimality or stopped on the limit

2.2 WHEN the solver must stop before proving optimality, THEN the system SHALL stop on a reproducible work-based criterion (CP-SAT's `max_deterministic_time`, calibrated from the user's wall-clock selection) rather than on wall-clock elapsed time, so that every run performs exactly the same amount of search

2.3 WHEN the machine is under different CPU load between two runs, THEN the system SHALL still produce identical output, because the stopping point no longer depends on how fast the machine ran

2.4 WHEN a wall-clock ceiling is still needed to protect the request from hanging, THEN the system SHALL treat it as a safety backstop set generously above the deterministic budget, and SHALL record in the result whether that backstop was the binding stop reason, so a non-reproducible run is identifiable rather than silent

2.5 WHEN several schedules tie at the same objective value, THEN the system SHALL select a **reproducible** one — on this machine, the same rigs, wells, financial year and time limit SHALL yield the same schedule on every run — by minimising a strictly dominating tie-break hierarchy (`W₁ > max(rig_well_order)`) in a second, canonicalising solve constrained to the stage-1 optimal objective value, together with the reproducible stopping criterion of 2.2

2.5.1 WHEN a tied optimum contains interchangeable permutations — equal-duration wells on identical rigs — THEN the selection SHALL be **reproducible but not canonical**: both tie-break tiers are *sums*, and permuting interchangeable wells leaves a sum invariant, so which member of that set is returned is decided by the search path — stable on this machine, but not pinned by the objective

2.5.2 WHEN such a residual exists, THEN it SHALL be **measured, not eliminated** — the tie-enumeration test enumerates the tied set at `P-expr == V*` and the canonical set at `(P-expr == V*) AND (T-expr == T*)`, records both counts, and asserts the canonical count against its measured value (**4** on the 5-well / 2-identical-rig model, at `V* = 218,583,260` and `T* = 8,182`, both enumerations exhausted), so a regression that grows the residual fails loudly

2.5.3 WHEN a future non-symmetric model shows a canonical count > 1 that interchangeable permutations do NOT explain, THEN the third tie-break tier — an arc-order index over `circuit_arcs`, design decision 3 — SHALL be the **designated escalation**; it is explicitly **out of scope** now by user decision, because path-independence of the canonical selection is not worth the model complexity when same-machine reproducibility is already met and measured (clauses 2.1-2.3, 2.12)

2.6 WHEN the solver explores the search tree, THEN the system SHALL impose an explicit canonical branching order via `model.AddDecisionStrategy()` over the assignment BoolVars and the start-time IntVars in sorted well-then-rig order, restoring a real body to `_add_decision_strategy()` at `scheduler/optimization.py:986`, so that the returned solution does not depend on CP-SAT's internal heuristic choices

2.7 WHEN a canonical branching order is imposed, THEN the system SHALL keep the solve fast enough to be usable — the fix SHALL be measured against the current runtime on a representative rig/well set, and if forcing `FIXED_SEARCH` costs unacceptable time, determinism SHALL instead be secured by the strict objective hierarchy of 2.5 plus a deterministic post-solve canonicalization, not by abandoning tie-break determinism

2.8 WHEN wells are loaded for a schedule, THEN the system SHALL order them by a total, tie-free key — `.order_by('name', 'id')` at `scheduler/views.py:1913` and a stable sort (`kind="stable"`) at `scheduler/optimization.py:686-687` — so that row order into matrix construction is fully determined by the input set

2.9 WHEN two selected wells share the same `name`, THEN the system SHALL either key the model on the well's unique `id` instead of `name`, or reject the run with an explicit message naming the duplicates, rather than silently collapsing them into one model variable

2.10 WHEN ILM days are computed for a well pair, THEN the system SHALL apply adjustment rules in a fully ordered sequence — `order_by('-priority', 'category', 'id')` at `scheduler/views.py:10791` and `:11087` — so the same inputs always yield the same ILM matrix

2.11 WHEN a schedule completes, THEN the system SHALL surface the model fingerprint and schedule hash to the operator (response payload and schedule detail page) alongside the solver status, so that two runs can be compared without reading server logs

2.12 WHEN determinism is claimed, THEN the system SHALL be backed by an automated repeat-run test that solves the same rig/well set N times and asserts a single distinct `schedule_hash`, so this regression cannot recur unnoticed

### Unchanged Behavior (Regression Prevention)

3.1 WHEN a schedule is run from `/scheduling/`, THEN the system SHALL CONTINUE TO sort rigs and wells by name before building the distance and ILM matrices, preserving the existing ordering fix at `scheduler/optimization.py:686-693`

3.2 WHEN rigs and wells are fetched for a schedule, THEN the system SHALL CONTINUE TO apply `.order_by('name')` at `scheduler/views.py:1912-1913` and `:1718-1719`

3.3 WHEN any solver entry point is called, THEN the system SHALL CONTINUE TO default `deterministic=True` (`scheduler/optimization.py:1514, 1688`) and SHALL CONTINUE TO pass it explicitly at all eight call sites in `scheduler/views.py`

3.4 WHEN the solver is configured in deterministic mode, THEN the system SHALL CONTINUE TO set `num_search_workers = 1` and `random_seed = 42` (`scheduler/optimization.py:932, 935`)

3.5 WHEN a model is built, THEN the system SHALL CONTINUE TO log the SHA-256 model proto fingerprint before solving (`scheduler/optimization.py:1735-1738`, `:1560-1563`)

3.6 WHEN the objective is set, THEN the system SHALL CONTINUE TO honour the lexicographic priority order — maximise assigned wells, then minimise total cost, then minimise project duration — with `BIG_M_WELLS` still dominating every lower tier (`scheduler/optimization.py:1368-1379`); the tie-break reweighting SHALL NOT let the solver trade a well for cost or duration

3.7 WHEN a schedule is solved, THEN the system SHALL CONTINUE TO respect all hard constraints — one rig per well, per-rig `AddNoOverlap`, rig availability windows, well RTD, HP / depth / BOP / TDS compatibility, financial-year start bounds, and circuit-based ILM gaps (`scheduler/optimization.py:999-1204`)

3.8 WHEN a schedule already solves to proven `OPTIMAL` well inside its time limit today, THEN the system SHALL CONTINUE TO return that same optimal schedule and the same objective value after the fix

3.9 WHEN the deterministic budget is applied, THEN the system SHALL CONTINUE TO return a representative `/scheduling/` run with **no material regression in wells assigned or total cost** — this quality clause is the **binding constraint**, it may not be traded against wall time, and it is precisely what a work budget shrunk to hold wall time down violates (`DETERMINISTIC_TIME_RATIO = 0.15` reproducibly collapsed 23 assigned wells to 1) — AND the wall time of that run SHALL be bounded by `WALL_BACKSTOP_FACTOR × T` (configured, currently 1.5 × the limit selected at `templates/scheduler/scheduling.html:447-450`) rather than by the selected limit itself

3.10 WHEN re-optimization runs with locked actual dates, THEN `solve_with_actuals()` SHALL CONTINUE TO pin those actuals exactly (`scheduler/optimization.py:1458-1513`) and SHALL CONTINUE TO sort `fixed_actuals` by `(well, rig)` before applying them (`:1527-1528`)

3.11 WHEN the SEM re-optimization endpoint runs (`scheduler/sem_views.py:1125-1131`), THEN the system SHALL CONTINUE TO work unchanged and SHALL inherit the same determinism guarantees, since it shares `DrillingScheduler`

3.12 WHEN `deterministic=False` is requested explicitly, THEN the system SHALL CONTINUE TO offer the faster multi-threaded performance mode (`scheduler/optimization.py:962-978`) without any determinism promise

3.13 WHEN a schedule is saved, THEN the system SHALL CONTINUE TO persist assignments with per-rig `sequence_order` derived from start date (`scheduler/views.py:1996-2002`) and SHALL CONTINUE TO record unassigned wells with their rejection analysis (`:2062-2075`)

## Deriving the Bug Condition

**F** — `DrillingScheduler.solve()` as it exists today (`scheduler/optimization.py:1688`).
**F'** — the same method after the fix.
**X** — one scheduling request: the rig set, well set, financial year and time limit.

The bug has three independent triggers, so the condition is a disjunction. Any one of them being
true makes the output non-reproducible.

```pascal
FUNCTION isBugCondition(X)
  INPUT:  X of type ScheduleRequest   // {rig_ids, well_ids, financial_year, time_limit_seconds}
  OUTPUT: boolean

  // (a) the run stops on the wall-clock limit instead of proving optimality,
  //     so the amount of search performed varies between runs
  stopsOnWallClock  ← solveStatus(F, X) ≠ OPTIMAL

  // (b) more than one distinct schedule attains the optimal objective value,
  //     because the two tie-break tiers share weight 1
  hasObjectiveTies  ← COUNT{ s : s is feasible for X AND obj(s) = minObj(X) } > 1

  // (c) the optimal solution is not pinned by an explicit branching order
  noCanonicalOrder  ← decisionStrategyCount(model(X)) = 0

  RETURN stopsOnWallClock OR hasObjectiveTies OR noCanonicalOrder
END FUNCTION
```

Measured on this workspace: (c) is true for every request today (`_add_decision_strategy` is
`pass`); (b) was true for a 5-well / 2-rig case with 10 tied optima; (a) is true for any request
whose model is too large to close inside the selected limit.

```pascal
// Property: Fix Checking — identical output on repeated runs
FOR ALL X WHERE isBugCondition(X) DO
  results ← [ F'(X) for k in 1..N ]        // N ≥ 5, N ≥ 2 of them under CPU load
  ASSERT  COUNT(DISTINCT scheduleHash(r) FOR r IN results) = 1
    AND   COUNT(DISTINCT modelFingerprint(r) FOR r IN results) = 1
    AND   COUNT(DISTINCT objectiveValue(r) FOR r IN results) = 1
    AND   ∀ r IN results : assignments(r) = assignments(results[1])
                            // same well→rig, same start/end day, same sequence_order
END FOR
```

```pascal
// Property: Preservation Checking — nothing else moves
FOR ALL X WHERE NOT isBugCondition(X) DO
  ASSERT F(X) = F'(X)
END FOR
```

`¬isBugCondition(X)` is the case where the model already closes to proven `OPTIMAL` with a unique
optimum: those requests must return exactly the schedule they return today.

Two constraints that the fix must also satisfy, and that the properties above do not capture:

```pascal
// Property: Feasibility Preservation — hard constraints still hold
FOR ALL X DO
  s ← F'(X)
  ASSERT allHardConstraintsSatisfied(s)      // per 3.7
    AND  wellsAssigned(s)  ≥ wellsAssigned(F(X))
    AND  totalCost(s)      ≤ totalCost(F(X)) WHEN wellsAssigned equal
END FOR

// Property: Bounded Wall Time and Preserved Quality
// The work budget is what determines the answer. The wall-clock backstop only bounds damage
// when that work cannot be completed, and a run it stops is flagged, not silently returned.
FOR ALL X DO
  s ← F'(X)

  // wall time is bounded by the configured backstop, NOT by the selected limit
  ASSERT wallTime(s) ≤ X.time_limit_seconds × WALL_BACKSTOP_FACTOR   // configured; currently 1.5

  // the binding half: the work budget must not be shrunk to buy wall time
  AND    wellsAssigned(s) ≥ wellsAssigned(F(X))
  AND    totalCost(s)     ≤ totalCost(F(X)) WHEN wellsAssigned equal

  // a backstop-bound run is identifiable rather than silent
  AND    (stopReason(s) = WALL_CLOCK_BACKSTOP) → (deterministicStop(s) = FALSE)
END FOR
```

## Reproduction Steps

1. Open `http://127.0.0.1:8011/scheduling/`.
2. Pick a rig/well combination large enough that the solver does not prove optimality inside the
   limit — the server log line `Schedule NOT proven optimal (FEASIBLE only)`
   (`scheduler/optimization.py:1746`) confirms you are in that regime.
3. Select a financial year and set Time Limit to 5 minutes.
4. Run the schedule. Note the `MODEL FINGERPRINT (solve)` and `Solution:` lines in the log, and the
   saved `Schedule.schedule_hash`.
5. Run again with an identical selection, a different schedule name, and the same time limit.
6. Compare. The model fingerprints match (identical input model) while the schedule hashes and the
   Gantt assignments differ — that mismatch is the bug.
7. To widen the failure rate, put the host under CPU load during step 5. The reproduction above
   went from 1 distinct schedule on an idle machine to 2 out of 3 runs under load at an 11 s limit.

## Verification Criteria

- The same rig/well/FY/time-limit selection run 10 times yields exactly one distinct
  `schedule_hash`, including runs that report `FEASIBLE` rather than `OPTIMAL`.
- The same selection run under heavy CPU load yields the same `schedule_hash` as the idle runs.
- An automated repeat-run test exists (per 2.12) and fails if a second distinct hash appears.
- A tie-enumeration check on a small symmetric rig/well set **measures** the canonical count at
  `(P-expr == V*) AND (T-expr == T*)` and asserts it against its known value (4 on that model), with
  **both** enumerations exhausted — a cap hit is a failure, because a capped count is only a lower
  bound. Per clause 2.5.2 the residual is measured, not eliminated: a count **above** the pinned
  value is a regression, a count **below** it means canonicalisation improved and the pinned value
  must be revisited deliberately.
- The same check confirms the count at `P-expr == V*` alone stays **> 1**, so the test still
  documents the tied set that stage 2 is choosing within rather than only asserting a number.
- The tie-break hierarchy is real on the model under test — `W₁ > max(rig_well_order)` — so a
  passing canonical count is never an artefact of a collapsed hierarchy.
- **Hard criterion** — a representative `/scheduling/` run assigns no fewer wells at no greater cost
  than the current code. Nothing may be traded against this, wall time included.
- A representative `/scheduling/` run's wall time stays inside `WALL_BACKSTOP_FACTOR × T` (currently
  1.5 × the selected limit), not inside the selected limit itself.
- Any run whose stop reason was the wall-clock backstop rather than the deterministic budget is
  flagged non-reproducible in the result — `deterministic_stop = False`,
  `stop_reason = WALL_CLOCK_BACKSTOP` — rather than reported as a normal completion, and a test
  forces the backstop to bind so that path is proven live rather than assumed.
