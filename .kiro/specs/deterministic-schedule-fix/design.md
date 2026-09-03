# Deterministic Schedule Fix — Bugfix Design

## Overview

**The goal: the same rigs, wells, financial year and time limit, run repeatedly on the same
machine, must always produce the same schedule — no matter how busy that machine happens to be at
the time.** That is the whole requirement. Two runs of `/scheduling/` with an identical selection
today can return different schedules. The requirements document establishes three independent
causes and a set of secondary ordering hazards. This design closes all of them.

Scope is set by `bugfix.md`, which is authoritative: clause 2.3 (same machine, different CPU load,
identical output) and the verification criterion "the same selection run under heavy CPU load yields
the same `schedule_hash` as the idle runs" are the correct and authoritative expression of the
requirement. Comparing schedules across different machines or CPU architectures is not in scope, and
nothing in this design should be read as offering or needing that.

The load-bearing change is the stopping criterion. CP-SAT's search is a pure function of
`(model proto, parameter proto, solver build)` — *provided the termination condition is itself a
pure function of that triple*. Today it is not: `max_time_in_seconds`
(`scheduler/optimization.py:927`, `:954`) makes the amount of search performed depend on how much
CPU the machine had to spare during that particular run, which is exactly what the reproduction in
the requirements measured on one machine (same proto fingerprint `de7ec4d44a8297a2`, three runs, two
objective values, deterministic time drifting 7.1256 → 7.3596). Replacing it with
`max_deterministic_time` pins the work performed (`7.0001` on every run in the same experiment) and
makes the answer reproducible whether or not optimality was proved.

The tie-break work is a second, separate concern. Once the stop is deterministic, run-to-run
reproducibility no longer *depends* on breaking ties — but the choice among tied optima is still
arbitrary, business-visible (a needlessly late start, an odd rig), and fragile to anything that
perturbs the search path (an OR-Tools upgrade, a parameter change, a decision-strategy
experiment). The requirements demand a canonical selection, and the previous attempt to get it by
inflating `START_TIME_WEIGHT` to `num_pairs+1` cost a ~1.7 % optimality gap because the tie-break
then represented ~2.5 % of Big-M. This design gets the canonical selection from a **two-stage
lexicographic solve**: stage 1 minimises exactly today's objective and yields `V*`; stage 2 pins
that objective to `V*` as a constraint and minimises a strictly-dominating tie-break hierarchy.
The dominating weights then live in a solve that contains no Big-M at all, so they cannot widen any
relaxation gap, and because stage 2 only ever chooses *within* today's optimal set, a request that
already has a unique optimum returns byte-identical output to today.

The remaining changes are containment: total orderings everywhere a tie is currently left to the
database or to an unstable sort, an explicit rejection of duplicate well names instead of a silent
collision, and provenance (model fingerprint, solver fingerprint, stop reason) surfaced in the API
response and on the schedule detail page so a non-reproducible run is identifiable without reading
server logs.

Nothing in this document changes code. It specifies what the implementation phase will change.

## Glossary

- **Bug_Condition (C)**: A scheduling request whose output is not reproducible — the solver stops
  on wall-clock time, or several schedules tie at the optimal objective, or no canonical branching
  order is imposed. Formalised as `isBugCondition` below.
- **Property (P)**: The desired behaviour for such a request — repeated runs return byte-identical
  assignments and therefore an identical `schedule_hash`.
- **Preservation**: A request that already closes to a proven, *unique* optimum must return exactly
  the schedule and objective value it returns today.
- **Deterministic time**: CP-SAT's work counter
  (`CpSolverResponse.deterministic_time`, exposed as `solver.deterministic_time`). It counts work
  performed, not time elapsed, so it does not move when the machine is busy. Units are "as close as
  possible to a second" per the OR-Tools parameter documentation but are a count of work, not
  elapsed time. `max_deterministic_time` bounds it.
- **Wall-clock backstop**: `max_time_in_seconds`, retained only to stop a request hanging. If it
  binds, the run is not reproducible and must be flagged.
- **Deterministic budget (D)**: The `max_deterministic_time` value derived from the user's
  wall-clock selection on the Time Limit dropdown (`templates/scheduler/scheduling.html:447-459`).
- **Stage 1 / Stage 2**: The primary economic solve and the canonicalising tie-break solve.
- **V\***: The stage-1 objective value, pinned as an equality constraint in stage 2.
- **Primary objective (P-expr)**: The full composite expression currently passed to
  `model.Minimize()` at `scheduler/optimization.py:1412-1428`.
- **Tie-break objective (T-expr)**: `W₁·start_time_sum + W₂·rig_well_order`, minimised in stage 2
  with `W₁ > max(rig_well_order)`.
- **`_configure_solver_for_determinism`**: `scheduler/optimization.py:905-984`. Sets the parameter
  block for both deterministic and performance modes.
- **`_add_decision_strategy`**: `scheduler/optimization.py:986-994`. Body is currently `pass`.
- **`set_objective`**: `scheduler/optimization.py:1206-1430`. Builds Big-M, duration weight and
  tie-break weights, then calls `Minimize` once.
- **`solve` / `solve_with_actuals`**: `scheduler/optimization.py:1688`, `:1514`. Both run the full
  pipeline then `self.solver.Solve(self.model)`.
- **`schedule_hash`**: SHA-256 (16 hex chars) over `(rig, well, start_day, end_day)` tuples sorted
  by `(rig, well)`, computed at `scheduler/optimization.py:1852-1856`, persisted at
  `scheduler/views.py:1973`, already displayed at `templates/scheduler/schedule_detail.html:413-421`.
- **Model fingerprint**: SHA-256 of `str(self.model.Proto())`, computed at
  `scheduler/optimization.py:1735-1738` and `:1560-1563`, currently logged only.
- **Solver fingerprint** (new): SHA-256 over the explicitly-set parameter proto text plus the
  OR-Tools version string, so a parameter or library change is detectable as the cause of a
  differing result.

## Bug Details

### Bug Condition

The bug manifests when a scheduling request's output is not a pure function of its inputs. Three
mechanisms make it so, and any one is sufficient:

1. **Wall-clock stop.** `_configure_solver_for_determinism` sets only `max_time_in_seconds`
   (`scheduler/optimization.py:927`, overwritten at `:954`). `max_deterministic_time` is explicitly
   rejected in the comment at `:947-953` on the grounds that CP-SAT is "perfectly deterministic
   out-of-the-box" and that a work-based limit "cripples the LNS heuristics which rely on real CPU
   cycles". The measurement in the requirements refutes the first claim directly and the second is
   a mechanism error (addressed in *Hypothesized Root Cause* below).
2. **Objective ties.** `START_TIME_WEIGHT = 1` and `RIG_WELL_ORDER_WEIGHT = 1`
   (`scheduler/optimization.py:1358-1359`) let the two tie-break tiers trade against each other, so
   they form no order at all. Ten distinct schedules shared objective 3244 on the 5-well /
   2-identical-rig case.
3. **No canonical branching order.** `_add_decision_strategy` is `pass`
   (`scheduler/optimization.py:986-994`) and `search_branching = AUTOMATIC_SEARCH` (`:938`), so
   which tied optimum is returned is whatever the heuristic reaches first.

**Formal Specification:**

```
FUNCTION isBugCondition(X)
  INPUT:  X of type ScheduleRequest   // {rig_ids, well_ids, financial_year, time_limit_seconds}
  OUTPUT: boolean

  stopsOnWallClock  ← solveStatus(F, X) ≠ OPTIMAL
  hasObjectiveTies  ← COUNT{ s : s feasible for X AND obj(s) = minObj(X) } > 1
  noCanonicalOrder  ← decisionStrategyCount(model(X)) = 0

  RETURN stopsOnWallClock OR hasObjectiveTies OR noCanonicalOrder
END FUNCTION
```

### Examples

- 11 s limit, one machine under CPU load, identical model proto fingerprint on all three runs: objective
  `73927958` twice and `73867926` once. Expected: one objective, one schedule.
- Same model with `max_deterministic_time = 7.0`: deterministic time `7.0001` every run, one
  schedule fingerprint, wall time varying 8.85–8.97 s. This is the target behaviour.
- 5 wells, 2 identical rigs, current weights: 10 distinct schedules at optimal objective 3244.
  Expected: exactly one schedule is selectable.
- Two selected wells with the same `Well.name` (no `unique=True` at `scheduler/models.py:394`):
  `self.assignments[(wid, rid)]` (`scheduler/optimization.py:891`) creates one variable pair for
  two wells, the distance and ILM matrices get duplicate index labels
  (`:697-716`, `:759-764`), and `wells_df.loc[wells_df["name"] == wid].iloc[0]`
  (`:1809`) silently picks the first. Expected: the run is rejected naming the duplicates.
- Edge case — a request that already proves `OPTIMAL` with a unique optimum: must return exactly
  today's schedule, today's objective value, and today's `schedule_hash`.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**

- A request that proves `OPTIMAL` today with a unique optimum returns the identical schedule and
  the identical `objective_value` after the fix (clause 3.8, and the Preservation property).
- All hard constraints continue to hold: one rig per well, per-rig `AddNoOverlap`, rig availability
  windows, well RTD, HP / depth / BOP / TDS compatibility, FY start bounds, circuit-based ILM gaps
  (`scheduler/optimization.py:999-1204`).
- The lexicographic priority order stays: maximise assigned wells, then minimise total cost, then
  minimise project duration, with `BIG_M_WELLS` dominating every lower tier
  (`:1367-1376`, `:1412-1428`). No tie-break change may let the solver trade a well for cost.
- The existing input-ordering fixes stay: sort rigs and wells before matrix construction
  (`:686-693`), `.order_by('name')` on the queryset paths (`scheduler/views.py:1911-1912`,
  `:1717-1718`), `deterministic=True` at all eight call sites and as the parameter default
  (`optimization.py:1514`, `:1688`), `num_search_workers = 1` and `random_seed = 42`
  (`:932`, `:935`), SHA-256 model fingerprint logging (`:1735-1738`, `:1560-1563`).
- `solve_with_actuals()` continues to pin actuals exactly (`:1458-1513`) and to sort
  `fixed_actuals` by `(well, rig)` first (`:1527-1528`).
- `deterministic=False` continues to offer the multi-threaded performance mode with no determinism
  promise (`:962-978`).
- The SEM re-optimization endpoint (`scheduler/sem_views.py:1125-1131`) continues to work and
  inherits the guarantees, since it shares `DrillingScheduler`.
- Saving continues to derive per-rig `sequence_order` from start date
  (`scheduler/views.py:1996-2002`) and to record unassigned wells with rejection analysis
  (`:2069-2084`).

**Scope:**

All requests that already close to a unique proven optimum are unaffected. Concretely, the design
achieves that by construction: stage 2 only ever selects among solutions whose stage-1 objective
equals `V*`, so when that set has one member the output cannot change.

Also unaffected:

- The performance mode path (`deterministic=False`).
- The Gantt, map, comparison and export views, which read persisted `Assignment` rows.
- The response contract: `assignment_data['rig']` and `['well']` remain well/rig *names*, so the
  save logic at `scheduler/views.py:1988-1989`, the SEM mapping at `sem_views.py:1137-1145` and
  `WellRejectionAnalyzer` (`well_rejection_analyzer.py:38`) need no change.

## Hypothesized Root Cause

1. **The stopping criterion is not a function of the input.** `max_time_in_seconds` at
   `scheduler/optimization.py:927`/`:954` terminates the search at whatever node the process
   happened to reach inside that wall-clock window. The incumbent at that node is the answer. On a
   single machine the reachable node moves with the machine's own CPU load, which is not part of the
   request — precisely the measured failure (1 distinct schedule idle, 2 of 3 runs differing under
   load at an 11 s limit, same machine).

2. **The comment at `:947-953` misdiagnoses the LNS interaction.** LNS in CP-SAT does not consume
   "real CPU cycles" as its budget unit — its sub-solves and neighborhood difficulty adaptation are
   already metered in deterministic time. The parameter block itself is evidence:
   `probing_deterministic_time_limit`, `presolve_probing_deterministic_time_limit`,
   `shaving_search_deterministic_time`, `symmetry_detection_deterministic_time_limit` are all
   work-metered subroutine budgets. `max_deterministic_time` changes only the *unit of the total
   budget*, so LNS performs the same number of operations — it just performs the same number every
   time instead of however many fit in the wall-clock window.

3. **The tie-break tiers are not a hierarchy.** With both weights at 1
   (`:1358-1359`), `start_time_sum` and `rig_well_order` are commensurate and trade off. The
   previous fix (dominating `START_TIME_WEIGHT = num_pairs+1`) did produce an ordering but inflated
   the tie-break contribution to ~69 M against a Big-M of ~2.7 G — 2.5 % — which weakened the LP
   relaxation enough to leave a ~1.7 % gap and slow the optimality proof. So the *weights* are not
   the problem; putting a dominating tie-break in the same minimisation as Big-M is.

4. **Even a dominating weight does not give a strict total order.** The requirements measured 2
   distinct schedules remaining at the optimum with the previously-dominating start-time weight.
   Two schedules that swap equal-duration wells between two identical rigs can agree on unassigned
   count, cost, project end, `start_time_sum` *and* `rig_well_order`. Clause 2.5's literal goal
   ("no two distinct schedules share an objective value") is not reachable with
   polynomially-bounded integer weights, because the solution space is exponential and an injective
   linear objective over it would need exponential coefficients. The design therefore treats 2.5 as
   "select a single canonical one" (its opening words) and secures the residual by the deterministic
   stop.

5. **Well name is used as a primary key without being one.** `Well.name` has no `unique=True`
   (`scheduler/models.py:394`) while every optimizer structure keys on it. `Rig.name` *is* unique
   (`scheduler/models.py:228`), so the asymmetry is a data-model oversight, not a design intent.

6. **Several orderings are left to the database or to an unstable sort.** `.order_by('name')`
   with non-unique names (`scheduler/views.py:1912`), `sort_values(by="name")` with pandas' default
   non-stable quicksort (`optimization.py:686-687`), `order_by('-priority', 'category')` on
   `RigBuildingAdjustment` (`views.py:10791`, `:11087`, and the same pattern at
   `models.py:737`, `:816`, `:881`, `:952`), and an unordered `WellPairDistance` fetch whose
   symmetric writes overwrite each other (`optimization.py:781-790`).

7. **The evidence is only in the logs.** The model fingerprint (`optimization.py:1738`) and the
   solve summary are logged; `Schedule.schedule_hash` is persisted (`views.py:1973`) and shown
   (`schedule_detail.html:413-421`), but the fingerprint is not, and nothing records *why* the
   solver stopped, so a non-reproducible run looks identical to a reproducible one.

## Correctness Properties

Property 1: Bug Condition - Repeated runs return one schedule

_For any_ scheduling request where the bug condition holds (`isBugCondition` returns true) — the
solver stops before proving optimality, or several schedules tie at the optimal objective, or no
canonical branching order is imposed — the fixed `solve()` SHALL return byte-identical output on
every run *on the same machine*: one distinct `schedule_hash`, one distinct `model_fingerprint`, one
distinct `objective_value`, and identical `(well → rig, start day, end day, sequence order)`
assignments, including runs executed while that machine is under CPU load (clause 2.3).

**Validates: Requirements 2.1, 2.2, 2.3, 2.5, 2.6**

Property 2: Preservation - Unique proven optima are untouched

_For any_ scheduling request where the bug condition does NOT hold (`isBugCondition` returns
false) — the model closes to a proven `OPTIMAL` with a unique optimum — the fixed `solve()` SHALL
produce the same result as the original, preserving the well-to-rig mapping, the start and end
dates, the sequence order, the reported `objective_value` and the `schedule_hash`.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.10, 3.11, 3.12, 3.13**

Property 3: Feasibility Preservation - hard constraints and economics never regress

_For any_ scheduling request, the schedule returned by the fixed `solve()` SHALL satisfy every hard
constraint listed in clause 3.7, SHALL assign no fewer wells than the current code, and SHALL cost
no more than the current code when the number of wells assigned is equal.

**Validates: Requirements 3.6, 3.7**

Property 4: Performance Bound - the page stays usable

_For any_ scheduling request, total wall time across both solve stages SHALL NOT exceed the
selected `time_limit_seconds × 1.2`, enforced by the wall-clock backstop, and the binding stop
reason SHALL be reported so that a run stopped by the backstop is distinguishable from a run
stopped by the deterministic budget.

**Validates: Requirements 2.4, 2.7, 3.9**

Property 5: Total input ordering - duplicates are rejected, ties are ordered

_For any_ input set, the row order feeding matrix construction SHALL be fully determined by the
input set, and _for any_ input set containing two wells with the same `name` the run SHALL be
rejected with a message naming the duplicates rather than silently collapsing them.

**Validates: Requirements 2.8, 2.9, 2.10**

Property 6: Provenance is surfaced

_For any_ completed schedule, the model fingerprint, the schedule hash and the binding stop reason
SHALL be present in the API response and on the schedule detail page.

**Validates: Requirements 2.11**

## Fix Implementation

### Design decision 1 — Stopping criterion: deterministic time is the binding limit

**File**: `scheduler/optimization.py`  **Function**: `_configure_solver_for_determinism` (`:905-984`)

Replace the wall-clock-only block (`:927`, `:954`) with:

```
max_deterministic_time = D            # binding limit
max_time_in_seconds    = 1.15 × T     # backstop only, never expected to bind
num_search_workers     = 1            # unchanged (3.4)
random_seed            = 42           # unchanged (3.4)
search_branching       = AUTOMATIC_SEARCH   # unchanged (see decision 4)
symmetry_level         = 2            # unchanged
use_lns                = True         # unchanged (see decision 2)
interleave_search      = True         # unchanged (see decision 2)
cp_model_presolve      = True         # unchanged
```

Delete the comment block at `:947-953`; it asserts the opposite of what was measured. Replace it
with a short note recording the measurement and the mechanism.

**Why the stop must be work-based.** CPU load varies between runs on the *same* machine, and that
alone changed the answer. The reproduction recorded in this document was gathered on one machine:
idle, it produced 1 distinct schedule; under CPU load, 2 of 3 runs differed at an identical model
proto fingerprint (`de7ec4d44a8297a2`), with deterministic time drifting 7.1256 → 7.3596. The same
model run with `max_deterministic_time = 7.0` consumed `7.0001` units on every run and produced a
single schedule fingerprint, even though wall time varied 8.85–8.97 s. Wall-clock time is not a
function of the input on a single machine, because the machine's own load is not part of the input.
Deterministic time is. That is the whole argument and it is sufficient: `max_deterministic_time`
replaces the wall-clock stop, and `max_time_in_seconds` is demoted to a backstop that is not expected
to bind.

**Calibration: how T maps to D.** Deterministic time is a work counter whose unit is "as close as
possible to a second" (OR-Tools parameter documentation), not a second. The mapping is therefore an
empirical ratio, not a conversion:

```
D = RATIO × T
```

`RATIO` default **0.60**. Derivation from the measurements in the requirements: an 11 s wall-clock run
consumed 7.1–7.4 deterministic units, and a 7.0-unit budget consumed 8.85–8.97 s of wall time — about
1.27 s of wall time per unit of work on this machine while idle. At `RATIO = 0.60`, a 300 s selection
yields `D = 180`, which costs ≈ 229 s of wall time when the machine is idle — 76 % of T, leaving
~1.5× headroom before the `1.15 × T = 345 s` backstop.

**What the headroom is for.** `D` fixes the amount of work; how long that work takes depends on what
else this machine is doing at the time. The headroom is a **contention allowance** — it exists so the
fixed work budget still finishes inside the backstop when the machine is busy, which is exactly the
case clause 2.3 is about. Tune `RATIO` so the work budget comfortably fits this machine even when the
machine is under load: lower it if real runs on this host hit the backstop while busy, raise it to use
more of the user's budget if they never do. If the backstop does bind, the run is flagged rather than
silently non-reproducible (clause 2.4).

`RATIO` is **configurable**, because it is the one number in this design that is a property of the
machine the app runs on rather than of the problem. Add to `drilling_scheduler/settings.py` alongside
the existing `VIDEO_PROCESSING` dict precedent (`:227-243`):

```python
IDRS_SOLVER_DETERMINISM = {
    # Deterministic-time units granted per wall-clock second the user selected.
    # Headroom knob against CPU contention on this machine. Schedule-affecting: changing it
    # changes how much search is done, so it is part of the solver fingerprint.
    'DETERMINISTIC_TIME_RATIO': float(os.getenv('IDRS_DETERMINISTIC_TIME_RATIO', '0.60')),
    # Wall-clock backstop as a multiple of the selected limit. Must stay <= 1.2 (Property 4).
    'WALL_BACKSTOP_FACTOR': float(os.getenv('IDRS_WALL_BACKSTOP_FACTOR', '1.15')),
    # Share of the deterministic budget given to the canonicalising second stage.
    'CANONICALIZE_BUDGET_SHARE': float(os.getenv('IDRS_CANONICALIZE_BUDGET_SHARE', '0.15')),
    # Optional: pin the search tree as well (see decision 4). Off by default.
    'FIXED_SEARCH': os.getenv('IDRS_FIXED_SEARCH', 'False').lower() == 'true',
}
```

Tuning `RATIO` changes *how much search* is done, which can change the answer — so the value belongs
in the solver fingerprint (decision 7) and must be treated as a schedule-affecting configuration
change, not a performance knob. Document that in the setting comment.

> Footnote, out of scope: the guarantee here is same-machine reproducibility. CP-SAT's LP layer works
> in double precision, so identical results across different CPU architectures are neither claimed
> nor required by `bugfix.md`.

**Budget split across the two stages.** `D₁ = (1 − share) × D`, `D₂ = share × D`, default share
0.15. Both are deterministic, so their sum is deterministic.

**Hard rule: every solver parameter must be a pure function of the request.** No parameter may be
derived from a measured wall time. This rule matters *more* under a same-machine-only scope, not less:
the only thing left that can vary between two runs of the same request is this machine's elapsed time,
so any parameter computed from elapsed time is the one remaining channel through which the bug can
return. In particular stage 2's backstop is
`0.25 × WALL_BACKSTOP_FACTOR × T` computed from `T`, *not* "whatever wall time is left after stage
1" — a remaining-time computation would feed elapsed time back into the parameter proto and
reintroduce the bug through the back door. Stage 1's backstop is
`0.90 × WALL_BACKSTOP_FACTOR × T`. The two shares sum to 1.15 × T, satisfying Property 4.

**Stop-reason detection and reporting.** After each `Solve()`, read `solver.deterministic_time` and
`solver.wall_time` (both available on `CpSolver` in ortools 9.15) and classify:

| Condition | `stop_reason` | `deterministic_stop` |
|---|---|---|
| `status == OPTIMAL` | `OPTIMAL_PROVEN` | `True` |
| `status == INFEASIBLE` | `INFEASIBLE` | `True` |
| `deterministic_time ≥ 0.995 × D` | `DETERMINISTIC_BUDGET` | `True` |
| `wall_time ≥ 0.98 × backstop` | `WALL_CLOCK_BACKSTOP` | `False` |
| otherwise | `OTHER` | `False` |

Order matters: check `OPTIMAL` first (a proof needs no budget), then the deterministic budget, then
the backstop. The `0.995` threshold reflects the measured overshoot (`7.0001` against a 7.0
budget). The aggregate for a two-stage solve is
`deterministic_stop = stage1.deterministic_stop AND stage2.deterministic_stop`, and `stop_reason`
reports the first non-deterministic stop if there is one, otherwise stage 1's.

### Design decision 2 — LNS and `interleave_search` both stay on

`use_lns = True` (`:942`) and `interleave_search = True` (`:945`) are **kept**. Reasoning, not
assumption:

- `interleave_search` is not a determinism risk; it is CP-SAT's *deterministic scheduling mode*.
  The parameter documentation states the search is deterministic independently of the worker count,
  and that the solver schedules and waits for `interleave_batch_size` tasks to complete before
  synchronising and scheduling the next batch. Batch boundaries are therefore work boundaries, not
  wall-clock boundaries. Turning it off would remove a determinism *aid* and cost solution quality,
  because with one worker the interleaved portfolio is what gives access to strategies beyond the
  single subsolver implied by `search_branching`.
- `use_lns` is deterministic under this configuration for the same reason: with one worker and
  interleaved batches, each LNS sub-solve gets a work-metered slice and the difficulty adaptation
  reacts to work-metered outcomes. The variance the requirements measured was not LNS randomness —
  the seed is fixed at `:935` — it was the *total* budget being wall-clock.
- The two interact with decision 1 in the right direction: LNS is exactly the component whose
  progress varies most with how much CPU is actually available, so putting the total budget on a
  work counter is what makes an LNS-heavy search reproducible run to run.

This is a documented-behaviour argument, so the determinism test (decision 8) is the gate rather
than the documentation. If the repeat-run test shows drift, apply this ladder in order, re-testing
at each step, and record which rung was needed:

1. Pin `interleave_batch_size` explicitly (currently unset → OR-Tools derives it from the worker
   count, so an upgrade can change it silently).
2. `use_lns = False` — loses incumbent quality on large models, keeps the portfolio.
3. `interleave_search = False` — falls back to a single subsolver; largest quality cost.

Rung 1 is worth doing pre-emptively if the fingerprint work (decision 7) is in place, since it
converts an invisible default into a recorded parameter.

### Design decision 3 — Two-stage lexicographic solve, not a re-inflated tie-break

**Chosen: two-phase / lexicographic staged solve, with the stage-1 lock on the *full* current
objective value.**

**Files**: `scheduler/optimization.py` — `set_objective` (`:1206-1430`), `solve` (`:1688-1763`),
`solve_with_actuals` (`:1514-1573`), `_extract_solution` (`:1764-1922`).

Stage 1 minimises exactly the expression built today at `:1412-1428`, weights unchanged
(`START_TIME_WEIGHT = RIG_WELL_ORDER_WEIGHT = 1`, `:1358-1359`). It yields `V*` and a solution.
Stage 2, on the same `CpModel`, adds `Add(P-expr == V*)` and replaces the objective with
`Minimize(W₁·start_time_sum + W₂·rig_well_order)` where `W₂ = 1` and
`W₁ = max(rig_well_order) + 1`.

Why the lock is on the *full* objective rather than on tiers 1–3 only: locking the full value means
stage 2's feasible set is exactly the set of solutions today's solver is free to return
arbitrarily. So stage 2 can only ever replace an arbitrary choice with a canonical one — it can
never change the economics, and when the optimum is unique it cannot change anything at all. That
is what makes Property 2 and clause 3.8 hold literally, including the reported `objective_value`.
Locking only tiers 1–3 would give the canonicaliser more freedom (and arguably prettier schedules)
at the cost of changing answers on requests that are correct today. Not worth it.

Why this does not re-create the optimality gap:

- Stage 1's objective is byte-identical to today's. Its Big-M, its relaxation and its proof
  difficulty are unchanged, so `3.8` and the current gap behaviour are preserved by construction.
  There is no `num_pairs+1` weight anywhere in stage 1.
- Stage 2 contains no Big-M *in its objective at all*. `BIG_M_WELLS` appears only inside the
  equality constraint. The dominating weights therefore cannot be "a percentage of Big-M" — the
  quantity that caused the 1.7 % gap does not exist in stage 2.
- Stage 2's own objective range is small: with ~30 wells and ~13 rigs (`num_pairs ≈ 390`),
  `max(rig_well_order) = num_wells × num_pairs ≈ 11 700`, so `W₁ ≈ 11 701` and the stage-2
  objective maximum is `W₁ × horizon × num_pairs ≈ 1.8 × 10⁹` — comfortably inside int64 and far
  below the coefficient magnitudes that degrade CP-SAT's LP scaling.
- Stage 2 always starts from a known feasible point. Hint the stage-1 solution via `AddHint` on the
  assignment BoolVars and start-time IntVars, so stage 2 has an incumbent immediately and its only
  work is improving the tie-break. Its budget `D₂` is 15 % of `D`.
- Stage 2 does not need to prove optimality for determinism. Its stop is deterministic, so its
  incumbent is reproducible whether or not it closed. If it closes, the selection is canonical; if
  it does not, the selection is still reproducible and no worse than today's. Report
  `canonicalization_status` so the distinction is visible.

Note while implementing: `max_order_tiebreak = num_pairs × num_pairs` at `:1362` is a loose bound —
each well contributes at most one active assignment, so the true bound is
`num_wells × num_pairs`. Use the tight bound for `W₁`, and correct `:1362` as well so Big-M is not
padded unnecessarily.

Why the alternatives were rejected:

- **Deterministic post-solve canonicalization as the primary mechanism.** Rejected. The residual
  ties are not local: two tied schedules can differ in the well→rig mapping, and converting one to
  the other requires re-checking `AddNoOverlap`, the circuit/ILM gaps, rig windows and RTD — i.e.
  re-implementing the solver in Python, with no proof that the canonical member was reached.
  Canonical *output ordering* is worth keeping (and largely already exists: `assignments` is built
  in canonical `(well, rig)` insertion order at `:1807`, and `schedule_hash` sorts by
  `(rig, well)` at `:1852-1855`) but that orders a schedule's rows, it does not choose between
  schedules.
- **Tighter Big-M derivation so a dominating weight is no longer a meaningful fraction of it.**
  Rejected as a solution to *this* problem, and it is worth being precise about why, because it
  looks plausible. The current bound at `:1335-1338` is valid but loose: `max_total_cost` assumes
  every well pays the global maximum daily cost × the global maximum duration plus the global
  maximum ILM. Tightening it (per-well maxima over compatible rigs, summed) would shrink Big-M
  meaningfully. But a *dominating* `START_TIME_WEIGHT` must exceed `max(rig_well_order)`, which
  makes the tie-break's own contribution grow to roughly `num_wells × num_pairs²` — the ~69 M that
  caused the gap. Shrinking Big-M while the tie-break grows makes the ratio that damages the
  relaxation *worse*, not better. Tightening Big-M is a good independent optimisation for solve
  speed and should be raised as separate work; it is not the tie-break enabler.
- **Enumerating all solutions at `V*` and picking the minimum in Python** (via
  `enumerate_all_solutions` and a solution callback). Rejected for production: the tied set can be
  exponential. It is, however, exactly the right tool for the *test* — see decision 8.

Implementation notes that the two-stage structure forces, all of which must be handled or the
detail page shows nonsense:

- Reported metrics come from **stage 1**: `objective_value`, `best_bound`, `optimality_gap`,
  `solver_status`, `is_optimal`. `_extract_solution` currently reads these from `self.solver`
  at `:1793-1803`; it must read stage-1's captured values instead. Stage 2's objective is a
  tie-break index and is meaningless to the business.
- Variable *values* come from **stage 2** when stage 2 succeeded, otherwise from stage 1. Capture
  stage 1's values into a plain dict before mutating the model, and give `_extract_solution` an
  optional value-lookup so it can extract from either source. Stage 2 must never be able to worsen
  or lose a result.
- Skip stage 2 entirely when stage 1 returned neither `OPTIMAL` nor `FEASIBLE`, and when
  `deterministic=False` (performance mode makes no determinism promise, clause 3.12).
- `solve_with_actuals` (`:1514`) goes through the same two stages, so SEM re-optimization
  (`sem_views.py:1125-1131`) and the locked-actuals path inherit it (clauses 3.10, 3.11).
- Both stage protos get a fingerprint. Stage 2's proto is a deterministic function of stage 1's
  result, so the chain `fp₁ → V* → fp₂` is itself reproducible and worth reporting.

### Design decision 4 — Decision strategy yes, `FIXED_SEARCH` no (by default)

**File**: `scheduler/optimization.py` — `_add_decision_strategy` (`:986-994`), `search_branching`
(`:938`).

Clause 2.7 poses this as a tradeoff and permits either resolution. It resolves as follows.

Run-to-run determinism is secured by decision 1 plus deterministic model construction. Given the
same proto and the same parameters on one worker with a fixed seed and a work-metered stop, CP-SAT
follows the same path and returns the same answer — no branching order needs to be forced. What
`AddDecisionStrategy` + `FIXED_SEARCH` adds is *path stability*: the answer stops depending on
which heuristic CP-SAT prefers, so it survives an OR-Tools upgrade or a parameter change. That is
valuable but it is a robustness property, not the bug. And `FIXED_SEARCH` is what was removed for
being too slow.

So:

- **Give `_add_decision_strategy` a real body** (clause 2.6). Two strategies in canonical order —
  which is already the dict insertion order of `self.assignments` and `self.start_times`, since
  `preprocess_data` sorts both frames (`:686-687`) and `setup_variables` iterates wells then rigs
  (`:886-908`):
  1. assignment BoolVars, `CHOOSE_FIRST`, `SELECT_MAX_VALUE` — try assigning before dropping;
  2. start-time IntVars, `CHOOSE_FIRST`, `SELECT_MIN_VALUE` — try earlier before later.
  Both are the same preference direction the tie-break objective encodes, so the first solutions
  found are closer to the canonical one and stage 2 has less to do.
- **Keep `search_branching = AUTOMATIC_SEARCH`** (`:938`). Without `FIXED_SEARCH` the strategy is a
  hint on first-branch preference, not a mandate — that is the point: near-zero cost, and it
  cannot cripple the search the way the removed version did.
- **Expose `FIXED_SEARCH` as an off-by-default setting** (`IDRS_SOLVER_DETERMINISM['FIXED_SEARCH']`)
  for audit runs where path stability matters more than quality. Its cost is now *bounded*, which
  is a direct consequence of decision 1: with a work-based budget, a slower search cannot overrun
  the wall clock — it returns a worse incumbent within the same budget instead. That converts an
  unbounded risk into a measurable quality tradeoff, and it is the reason this knob can exist at
  all. Because it changes the answer, it belongs in the solver fingerprint.
- Apply the same strategies to stage 2.

Risk to verify during implementation: presolve remaps variables, and decision strategies over
variables that presolve removes are handled by CP-SAT but the interaction is worth a check that
`cp_model_presolve = True` (`:981`) stays on and that no warning appears in the solver log.

### Design decision 5 — Reject duplicate well names; do not re-key the model on id

**Chosen: validate and reject.** Clause 2.9 permits either.

Blast radius of re-keying on `Well.id`, all in `scheduler/optimization.py` unless noted:
`assignments` / `start_times` / `end_times` / `intervals` keys (`:891-901`), the distance matrix
index and columns (`:697-716`), the per-rig ILM matrices (`:759-764`, `:795-822`),
`circuit_arcs` (`:1168`), every objective term (`:1239-1270`, `:1399-1410`),
`wells_df.loc[wells_df["name"] == wid]` in extraction (`:1809`), the assignment payload keys
`{"rig": rid, "well": wid}` (`:1818-1829`), `_calculate_ilm_costs` (`:2226-2277`),
`analyze_infeasible_solution` (`:1598-1610`), `merge_wells_for_scenario`'s
`drop_duplicates(subset=["name"])` (`:2341`), `_apply_actuals_duration_adjustments` (`:1454`) and
`apply_actual_constraints` (`:1480-1513`) — the latter two receive `fixed_actuals` carrying well
and rig *names* from persisted rows. Downstream: `wells.get(name=...)` in the save path
(`views.py:1988-1989`), `rigs_by_name` / `wells_by_name` (`views.py:2422-2423`), the analyzer
dataframes (`views.py:2506`, `:2520`), `WellRejectionAnalyzer.analyze_well_rejection`
(`well_rejection_analyzer.py:38`), and SEM's `new_assignments[ad['well']]` and name-built
`fixed_actuals` (`sem_views.py:1107`, `:1137-1145`).

That is a cross-module contract change touching the result payload the frontend and the save logic
both consume, to defend against a state that is already fatal today: `wells.get(name=...)` at
`views.py:1988` raises `MultipleObjectsReturned` inside `transaction.atomic()`, so a duplicate name
already aborts the save — just with an opaque error, after the solve has been paid for.

Rejecting is a one-line invariant with a good error message:

- **`DrillingScheduler.preprocess_data()`** (`scheduler/optimization.py:653-696`), immediately
  before the sort at `:686-687`: if `wells_df["name"]` has duplicates, raise a typed
  `DuplicateWellNameError` listing them. Placing it here covers all eight `solve` /
  `solve_with_actuals` call sites plus SEM at once, and it fires before any expensive work.
  Assert the same for `rigs_df["name"]` — `Rig.name` is unique at `models.py:228` so it cannot
  trigger, but the invariant is free and documents the assumption.
- **`ScheduleViewSet.create_schedule`** (`scheduler/views.py:1911-1913`), before creating the
  `Schedule` row: check the selected wells for duplicate names and return HTTP 400 naming them, so
  the user gets an actionable message and no `FAILED` schedule row is left behind. The optimizer
  check is the invariant; this one is the user experience.
- Map `DuplicateWellNameError` through `_friendly_error_message` so the existing exception handler
  at `views.py:2100-2110` produces a clear message on the other call paths.

Out of scope but worth raising: a `unique=True` (or `unique_together('location', 'name')`)
constraint on `Well.name`, plus a management command to report existing duplicates. The migration
can fail on live data, so it needs its own change with a data-cleanup step.

Also flag while in the area: `well_name_to_obj` at `scheduler/optimization.py:744-754` is dead —
built with `WellModel.objects.get(name=wname)` and never read. With duplicate names that `get`
raises `MultipleObjectsReturned`, which the outer `except Exception` at `:753` swallows after
aborting the loop. It is harmless today only because the dict is unused. Delete it; it is one
fewer name-keyed lookup and one fewer swallowed exception.

### Design decision 6 — Ordering hardening

**Total orderings on querysets** — `.order_by('name', 'id')`:

- `scheduler/views.py:1911-1912` — the `/scheduling/` path (clause 2.8).
- `scheduler/views.py:1717-1718` — `run_full_optimization`. Note this function is dead: it calls
  `rig.to_dict()` / `well.to_dict()` (`:1719-1720`) which do not exist on the models, and nothing
  in the app calls it. Harden it for consistency with clause 3.2 but do not treat it as a live path.
- `scheduler/views.py:2422-2423`, `:2506`, `:2520`, `:2976-2977`, `:3112-3113`, `:3175-3176` — the
  re-optimize, reschedule and add/delete-well paths.

`Well.sn` is also unique (`models.py:383`), so `('name', 'sn')` would be an equally total and more
human-legible key; `('name', 'id')` is specified because clause 2.8 names it and because `id` is
present in every `.values()` payload the optimizer receives.

**Stable, total pandas sorts** — `scheduler/optimization.py:686-687`:

```python
sort_keys = ["name", "id"] if "id" in df.columns else ["name"]
df = df.sort_values(by=sort_keys, kind="stable").reset_index(drop=True)
```

`kind="stable"` alone is not sufficient and it matters to say why: a stable sort preserves the
*input* order of tied rows, so it only helps if the input order is already total. The `id` column
(present because both paths build the frames from `.values()`) is what makes the key total; the
stable kind is belt-and-braces for the frames that arrive without it.

**`RigBuildingAdjustment` rule ordering** — `.order_by('-priority', 'category', 'id')` (clause
2.10). `calculate_ilm_days` applies the first matching `replace` rule and then sets
`base_replaced = True` (`views.py:10831-10839`), so the row order decides the ILM value:

- `scheduler/views.py:10791` — inside `calculate_ilm_days`, the non-prefetched branch.
- `scheduler/views.py:11087` — the bulk ILM refresh that prefetches the rules.
- `scheduler/models.py:737`, `:816`, `:881`, `:952` — the same pattern in the model-side helpers
  that populate `WellPairDistance`'s cached ILM values. These feed the numbers the optimizer reads
  at `optimization.py:781-790`, so leaving them unordered would keep the hazard alive one layer
  down.

**`WellPairDistance` fetch order** — `scheduler/optimization.py:781-783`. The queryset is
unordered and each row writes both directions into `distance_cache` (`:789-790`), so overlapping
rows overwrite each other in database order. Add `.order_by('well_1__name', 'well_2__name', 'id')`.
Note the filter is `rig=rig_obj` with no location predicate, which is why overlaps are possible at
all.

**Total sort keys on assignment lists** (cheap, removes a latent class of hazard even though rig
`AddNoOverlap` makes same-rig start-date ties impossible today):

- `scheduler/optimization.py:2243` — `arr.sort(key=lambda x: (x["well_start_date"], x["well"]))`.
- `scheduler/views.py:1997` and `:3268` — same, for the `sequence_order` derivation.

**Do not change** `for (wid, rid), a in self.assignments.items()` at `optimization.py:1807`. Dict
insertion order is the canonical `(well, rig)` order and the assignments list inherits it. This is
load-bearing; a future refactor to a set or a comprehension over a set would silently reintroduce
non-determinism. Add a comment saying so.

### Design decision 7 — Observability

**Result payload** — add to both `self.results` branches of `_extract_solution`
(`optimization.py:1858-1887` and `:1889-1920`):

| Key | Meaning |
|---|---|
| `model_fingerprint` | stage-1 proto SHA-256 (already computed at `:1735-1738`, `:1560-1563`) |
| `model_fingerprint_canonical` | stage-2 proto SHA-256, null when stage 2 was skipped |
| `solver_fingerprint` | SHA-256 over the explicitly-set parameter proto text + `ortools.__version__` + the `IDRS_SOLVER_DETERMINISM` values |
| `deterministic_stop` | bool — was the binding stop reproducible |
| `stop_reason` | `OPTIMAL_PROVEN` / `DETERMINISTIC_BUDGET` / `WALL_CLOCK_BACKSTOP` / `INFEASIBLE` / `OTHER` |
| `deterministic_time_used`, `deterministic_budget` | work consumed vs granted |
| `wall_backstop_seconds` | the backstop actually configured |
| `canonicalization_status` | stage-2 solver status, or `SKIPPED` |

Keep every existing log line (clause 3.5) and add one line reporting the stop reason and the
deterministic time against its budget.

**Persistence** — new nullable fields on `Schedule` (`scheduler/models.py:1498-1540` block) and
migration `0063_add_determinism_provenance.py`: `model_fingerprint` (CharField 64),
`solver_fingerprint` (CharField 64), `deterministic_stop` (BooleanField, null),
`stop_reason` (CharField 32), `deterministic_time_used` (FloatField, null),
`deterministic_budget` (FloatField, null). Populate them next to the existing assignments at
`scheduler/views.py:1966-1974`, and on the other save paths (`:2394`, `:2775`, `:3405`).

**API response** — `ScheduleSerializer` uses `fields = '__all__'` (`serializers.py:202-204`), so the
new model fields appear in the `create_schedule` response and the detail endpoint with no
serializer change. Add them to `ScheduleListSerializer`'s explicit field list
(`serializers.py:246-257`) so the schedules list can show a determinism badge. The
`to_representation` override hides `optimality_gap_percent` from non-admins
(`serializers.py:222-230`, `:272-279`); leave the determinism fields visible to everyone — the
detail page already shows the full `schedule_hash` (`schedule_detail.html:413-421`), and the stop
reason is a trust signal operators need more than admins do.

**Schedule detail page** — `templates/scheduler/schedule_detail.html`. The metadata block at
`:393-421` already renders Optimality Gap and Schedule Hash in a two-column row. Add a third row:
Model Fingerprint as a `<code>` element next to the existing hash, and a Reproducibility badge from
`stop_reason` — green for `OPTIMAL_PROVEN` and `DETERMINISTIC_BUDGET`, amber for
`WALL_CLOCK_BACKSTOP` with the text "stopped on the wall-clock backstop — this run is not
guaranteed reproducible", muted for the rest. Show `deterministic_time_used` / `deterministic_budget`
as small muted text beside it.

**Scheduling page** — `templates/scheduler/scheduling.html`, `showResults()` (`:1275-1296`). It
currently reads only assignments, unassigned, cost and solve time from the response. Add the
schedule hash (truncated, `title` with the full value), the model fingerprint, and a warning line
rendered only when `result.deterministic_stop === false`. Follow the existing escaping pattern at
`:1315-1317` for any interpolated text.

### Design decision 8 — Verification

Everything runs through the Django test runner against the test database — no live server, no
`runserver`, no HTTP. `scheduler/tests.py` is an empty placeholder; replace it with a
`scheduler/tests/` package (Django discovers tests in a package the same way).

```
scheduler/tests/__init__.py
scheduler/tests/factories.py             # in-memory rig/well builders + DB row creation
scheduler/tests/test_determinism.py      # clause 2.12, Property 1 & 4
scheduler/tests/test_tie_enumeration.py  # Property 1's tie half
scheduler/tests/test_preservation.py     # Property 2
scheduler/tests/test_ordering.py         # Property 5
scheduler/tests/fixtures/preservation_golden.json
```

`TestCase` (not `SimpleTestCase`) is required: `_calculate_ilm_days_matrix` queries `Rig`, `Well`
and `WellPairDistance` and calls `calculate_ilm_days` (`optimization.py:733-734`, `:781-783`,
`:813`). The factories create the matching DB rows so the real ILM path is exercised rather than
the fallback.

**`test_determinism.py`** — clause 2.12.

- `test_repeat_runs_yield_one_schedule_hash`: N = 5 solves, a fresh `DrillingScheduler` per run
  from the same input dicts. Assert exactly one distinct value each of `schedule_hash`,
  `model_fingerprint`, `objective_value`, and that every run's assignment tuple list
  `(well, rig, start_day, end_day)` equals run 1's. Sized so the solver does *not* prove optimality
  (that is the interesting regime) by using a small `time_limit_seconds` against a model with
  enough wells to stay open.
- `test_repeat_runs_under_cpu_load`: two of the runs execute while background `multiprocessing`
  busy-loops saturate the cores, then assert the hash matches the idle runs. Gated behind an
  environment flag (`IDRS_TEST_CPU_LOAD=1`) so a shared CI box is not wrecked, and documented as
  required before sign-off. This is the test that would have caught the original bug.
- `test_stop_reason_is_deterministic_budget`: same open model, assert `deterministic_stop is True`
  and `stop_reason == 'DETERMINISTIC_BUDGET'`.
- `test_wall_backstop_is_flagged`: `override_settings` with a tiny `WALL_BACKSTOP_FACTOR` so the
  backstop binds, assert `deterministic_stop is False` and `stop_reason == 'WALL_CLOCK_BACKSTOP'`
  (clause 2.4 — proves the flag actually fires rather than being dead code).
- `test_wall_time_within_tolerance`: Property 4 — total wall time ≤ `time_limit_seconds × 1.2`.

**`test_tie_enumeration.py`** — the 5-well / 2-identical-rig model from the requirements, the case
that produced 10 tied schedules.

- Solve stage 1, capture `V*`; solve stage 2, capture the tie-break optimum `T*`.
- Build a third model constrained to `P-expr == V*` *and* `T-expr == T*`, set
  `enumerate_all_solutions = True` with `num_search_workers = 1`, and collect distinct
  `schedule_hash` values through a `CpSolverSolutionCallback`.
- Assert the count is exactly 1. Cap the callback at 50 solutions and fail on the cap, so a
  regression fails fast instead of hanging.
- Also log the distinct count at `P-expr == V*` alone (expected > 1, it is the tied set) so the
  test documents what the canonicalisation is doing rather than just asserting a number.
- If a future model shows a count > 1 here, that is the trigger to add the third tie-break tier
  (arc-order index over `circuit_arcs`) described in decision 3 — the test tells you when it is
  needed instead of paying for it speculatively.

**`test_preservation.py`** — Property 2. A model small enough to prove `OPTIMAL` with a unique
optimum. Assert the assignments and `objective_value` equal a golden JSON fixture. Capture the
golden by running the *current* code once against the same factory input and committing the
output; record the commit SHA it came from in the fixture so the provenance is auditable. This is
the test that would catch stage 2 changing an answer it should not touch.

**`test_ordering.py`** — Property 5.

- Two wells sharing a `name` → `preprocess_data()` raises `DuplicateWellNameError` naming both, and
  `create_schedule` returns 400 with the names, and no `Schedule` row is left behind.
- Two `RigBuildingAdjustment` rows with equal `priority` and `category` → `calculate_ilm_days`
  returns the same value regardless of insertion order, and the applied rule is the lower `id`.
- Two `WellPairDistance` rows covering the same name pair → the ILM matrix value is stable across
  repeated `_calculate_ilm_days_matrix()` calls.

**Verification on the deployed host** — `scheduler/management/commands/check_determinism.py`,
alongside the existing commands (`refresh_ilm_cache.py` etc.):

```
python manage.py check_determinism --schedule-id <uuid> --runs 5 [--under-load]
```

Re-solves an existing schedule's exact rig/well/FY/time-limit selection N times and prints a table
of `schedule_hash`, `model_fingerprint`, `solver_fingerprint`, `objective_value`, `stop_reason`,
`deterministic_time_used` and `wall_time`, exiting non-zero if more than one distinct
`schedule_hash` appears. `--under-load` saturates the cores for some of the runs, so the command
verifies the requirement's own criterion — "the same selection under heavy CPU load yields the same
hash" — on the real host with real data, under load, which the unit tests cannot do. Same host,
varying load, is exactly the scope that matters. It also writes nothing to the database.

**Test runtime** — the determinism tests use small `time_limit_seconds` with a
`DETERMINISTIC_TIME_RATIO` override. A pleasant side effect of decision 1: the suite's own runtime
becomes stable, because the solver stops on work rather than on clock.

### Requirement conflict to resolve before implementation

Clause 3.8 asks for the same optimal schedule **and the same objective value** after the fix. This
design satisfies it literally — stage 1's objective function is byte-identical to today's, so `V*`
is today's value — and that is precisely why decision 3 locks the *full* objective rather than
tiers 1–3 only. Worth stating explicitly so the constraint is not relaxed later by accident: any
future move to lock only tiers 1–3 (which would produce cleaner canonical schedules) breaks 3.8
and the Preservation property, and would need a requirements change first.

One clause needs interpretation rather than a change. Clause 2.5 asks for "a strictly dominating
weight hierarchy … so that no two distinct schedules share an objective value". Strict uniqueness
of objective values across an exponential solution space is not achievable with
polynomially-bounded integer weights (root cause 4), and the requirements' own measurement — 2
schedules still tied under the previously-dominating weight — shows the previous attempt did not
achieve it either. This design delivers 2.5's stated goal ("select a single canonical one") via the
dominating hierarchy in stage 2 plus the deterministic stop, and makes the residual *measurable*
through the tie-enumeration test. If you want clause 2.5 reworded to match that reading, say so and
I will return to the requirements phase before implementation.

## Testing Strategy

### Validation Approach

Two phases. First, reproduce the bug on the unfixed code so the root-cause analysis is confirmed
rather than assumed. Then verify the fix closes it and that nothing else moved.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples on the UNFIXED code, confirming or refuting the hypothesised root
causes. A refutation sends us back to re-hypothesise before writing any fix.

**Test Plan**: Run the repeat-run harness (`test_determinism.py`, written first) against the
current code with a model large enough not to close inside a short limit. Run it idle and under
CPU load. Separately enumerate solutions at the optimal objective on the 5-well / 2-rig symmetric
model to count the tied set under today's weights.

**Test Cases**:

1. **Repeat-run divergence under load**: 5 solves of the same input at a short limit with the cores
   saturated; expect more than one distinct `schedule_hash` (will fail on unfixed code — this is
   the bug).
2. **Deterministic-time drift**: record `solver.deterministic_time` on each of those runs; expect
   it to vary (the requirements measured 7.1256 → 7.3596), which is the direct evidence that the
   wall-clock stop is the mechanism.
3. **Tied-optimum count**: enumerate at the optimal objective with `START_TIME_WEIGHT = 1` and
   `RIG_WELL_ORDER_WEIGHT = 1`; expect ≫ 1 (10 on the requirements' model) (will fail on unfixed
   code).
4. **Duplicate well name**: build two wells with the same `name` and solve; expect a silently
   collapsed model — `len(assignments)` short by one, no error raised (will fail on unfixed code).
5. **Edge case — `RigBuildingAdjustment` tie**: two rules with equal `priority` and `category`;
   re-create them in the opposite insertion order and expect a different ILM value (may fail on
   unfixed code, depending on how the database returns them).

**Expected Counterexamples**:

- Two or three distinct `schedule_hash` values across five runs at an identical
  `model_fingerprint`, with `deterministic_time` differing between them.
- Possible causes to discriminate between: the wall-clock stop landing on different search nodes
  (expected primary), tied optima being resolved differently by heuristic state, and — if the hash
  differs while `deterministic_time` is *identical* — something in model construction is unstable
  after all, which would move the diagnosis to the ordering hazards instead.

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the
expected behavior.

**Pseudocode:**

```
FOR ALL input WHERE isBugCondition(input) DO
  results := [ solve_fixed(input) for k in 1..N ]     // N >= 5, >= 2 under CPU load
  ASSERT COUNT(DISTINCT scheduleHash(r)      FOR r IN results) = 1
    AND  COUNT(DISTINCT modelFingerprint(r)  FOR r IN results) = 1
    AND  COUNT(DISTINCT objectiveValue(r)    FOR r IN results) = 1
    AND  ALL r IN results : assignments(r) = assignments(results[1])
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function
produces the same result as the original function.

**Pseudocode:**

```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT solve_original(input) = solve_fixed(input)
END FOR
```

**Testing Approach**: Property-based testing is the right tool for preservation here because:

- it generates many rig/well configurations automatically across the input domain;
- it catches the edge cases a handful of hand-written models will not — zero-duration wells,
  single-rig sets, wells whose RTD precedes the FY start, rigs with no compatible well;
- it gives real confidence that behaviour is unchanged for *all* non-buggy inputs, which a golden
  fixture on one model cannot.

Generate over: well count, rig count, durations, daily costs, ILM cost parameters, RTD offsets and
FY windows; keep the generated models small enough to prove `OPTIMAL` quickly, since that is the
`¬isBugCondition` regime. The golden-fixture test (`test_preservation.py`) is the concrete anchor;
the generated version is the general claim.

**Test Plan**: Observe behaviour on UNFIXED code first for the preserved paths — proven-optimal
small models, `deterministic=False` performance mode, `solve_with_actuals` with pinned dates — and
record it as golden fixtures. Then assert the fixed code reproduces them.

**Test Cases**:

1. **Unique proven optimum**: observe that a small model proves `OPTIMAL` with one optimum on
   unfixed code, record assignments and `objective_value`, then verify both are identical after the
   fix.
2. **Performance mode untouched**: observe `deterministic=False` behaviour on unfixed code
   (`optimization.py:962-978`), then verify the parameter block and results are unchanged after the
   fix — no deterministic budget, no stage 2 (clause 3.12).
3. **Locked actuals still pinned**: observe `solve_with_actuals` pinning actual start/end dates
   exactly on unfixed code (`:1458-1513`), then verify the fixed two-stage path still pins them and
   still sorts `fixed_actuals` by `(well, rig)` (`:1527-1528`) — stage 2 must not move a pinned
   well.
4. **Hard constraints intact**: verify one rig per well, per-rig no-overlap, rig windows, RTD,
   HP/depth/BOP/TDS compatibility, FY start bounds and ILM gaps on every schedule produced by the
   generated models (clause 3.7).
5. **Economics not regressed**: for each generated model, assert wells assigned ≥ unfixed and total
   cost ≤ unfixed when wells assigned are equal (Property 3).
6. **Save path unchanged**: verify `sequence_order` is still derived per rig from start date
   (`views.py:1996-2002`) and unassigned wells still carry rejection analysis (`:2069-2084`).

### Unit Tests

- Budget calibration: `T → (D, backstop)` for every dropdown value at
  `templates/scheduler/scheduling.html:447-459`, including the `RATIO` and `WALL_BACKSTOP_FACTOR`
  overrides and the stage split, asserting the backstop never exceeds `1.2 × T`.
- Stop-reason classification: table-driven over `(status, deterministic_time, wall_time, D,
  backstop)` covering all five outcomes and the boundary thresholds (`0.995`, `0.98`).
- Tie-break weight derivation: `W₁ > max(rig_well_order)` for a range of well/rig counts, and the
  stage-2 objective maximum stays inside a safe coefficient bound.
- Stage-2 fallback: with stage 2 forced to `INFEASIBLE` (inject a contradictory extra constraint),
  the stage-1 solution is returned intact and `canonicalization_status` reports the failure.
- Stage-1 metric provenance: `objective_value`, `best_bound`, `optimality_gap` and `solver_status`
  in the payload come from stage 1, not stage 2.
- `_add_decision_strategy` adds exactly two strategies in canonical `(well, rig)` order and
  `search_branching` remains `AUTOMATIC_SEARCH` unless `FIXED_SEARCH` is enabled.
- Duplicate well names raise `DuplicateWellNameError` naming every duplicate.
- Fingerprints: identical inputs give identical `model_fingerprint` and `solver_fingerprint`;
  changing `DETERMINISTIC_TIME_RATIO` or `FIXED_SEARCH` changes `solver_fingerprint` and leaves
  `model_fingerprint` alone.

### Property-Based Tests

- Repeat-run determinism over generated rig/well sets: for every generated input, N solves yield
  one distinct `schedule_hash` (Property 1).
- Preservation over generated inputs that prove `OPTIMAL`: fixed output equals unfixed output
  (Property 2).
- Feasibility and economics over all generated inputs: hard constraints hold, wells assigned do not
  decrease, cost does not increase at equal wells assigned (Property 3).
- Ordering invariance: for every generated input, shuffling the input row order and the DB
  insertion order of wells, rigs, `RigBuildingAdjustment` and `WellPairDistance` rows leaves the
  `model_fingerprint` unchanged (Property 5). This is the strongest single test of the ordering
  work, because it tests the invariant rather than each individual `order_by`.
- Budget monotonicity: a larger `time_limit_seconds` never produces a worse objective, over
  generated inputs — catches a stage-split or calibration mistake that starves the search.

### Integration Tests

- Full `POST /api/schedules/create_schedule/` twice with an identical payload through the Django
  test client (`views.py:1882`): both responses carry the same `schedule_hash` and
  `model_fingerprint`, and both persisted `Schedule` rows agree on every determinism field.
- A backstop-bound run through the same endpoint surfaces `deterministic_stop = false` and
  `stop_reason = WALL_CLOCK_BACKSTOP` in the response body, and the detail page renders the amber
  badge (assert on the rendered template context and the presence of the warning text).
- Re-optimize with locked actuals (`views.py:2361-2365`) and the SEM re-optimization endpoint
  (`sem_views.py:1125-1131`) each run twice and produce identical assignments, confirming clauses
  3.10 and 3.11 inherit the guarantee.
- A duplicate-well-name payload returns 400 naming the duplicates and creates no `Schedule` row.
- The schedule detail page (`templates/scheduler/schedule_detail.html`) renders the model
  fingerprint, the schedule hash and the reproducibility badge for a completed schedule
  (clause 2.11).
