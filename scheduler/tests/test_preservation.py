"""Golden baseline for the paths the deterministic-schedule-fix must NOT move.

**Property 2: Preservation — unique proven optima are untouched.**

*Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.10, 3.11,
3.12, 3.13*

``design.md`` defines Property 2 against **today's** behaviour: a request where
``isBugCondition`` is false — the model closes to a proven, *unique* optimum —
must return the same well-to-rig mapping, the same start and end dates, the same
sequence order, the same ``objective_value`` and the same ``schedule_hash``
after the fix as before it.

"Before it" is the problem.  Once task 3 changes the stopping criterion, the
pre-fix answers no longer exist anywhere, and a preservation test written after
that point can only compare fixed code against itself.  So these tests are
capture-first: they run against the unfixed code, record what it did in
``fixtures/preservation_golden.json`` together with the commit it came from, and
from then on assert against that recording.  Tasks 3.6, 4.7, 5.5 and 6.4 re-run
this file unchanged.

What is recorded, and what is deliberately not
----------------------------------------------
Every recorded value is a function of the inputs alone.  Nothing timing-derived
is recorded — not ``solve_time_seconds``, not ``wall_time``, not
``deterministic_time`` — because those vary run to run on any machine and would
make the fixture fail for reasons that have nothing to do with the schedule.
(Their variation is task 1's subject, measured in ``test_determinism.py``.)

The four observations correspond one-to-one to task 2's bullets:

1. ``unique_optimum`` / ``optimum_uniqueness`` — the ¬``isBugCondition``
   schedule, plus a proof that its optimum really is unique.
2. ``performance_mode`` — ``deterministic=False``
   (``scheduler/optimization.py:962-978``), clause 3.12.
3. ``solve_with_actuals`` — pinned actual dates
   (``scheduler/optimization.py:1458-1513``) and the ``(well, rig)`` sort at
   ``:1527-1528``, clauses 3.10 and 3.11.
4. ``save_path`` — per-rig ``sequence_order`` from start date
   (``scheduler/views.py:1988-1997``) and unassigned wells carrying rejection
   analysis (``:2069-2084``), clause 3.13.

Why uniqueness of the optimum is verified rather than assumed
------------------------------------------------------------
Property 2 only says anything about requests with a *unique* optimum.  If the
scenario's optimum were tied, the golden would be one arbitrary member of the
tied set, and task 4's canonicalising solve would be free to legitimately pick a
different member — the test would then fail on correct code.
``test_optimum_is_unique`` closes that hole by enumerating every schedule that
attains the optimal objective and requiring exactly one, reusing the no-good
enumeration from ``test_tie_enumeration`` so both tests count the same thing the
same way.

Regenerating
------------
``IDRS_REGENERATE_GOLDEN=1 python manage.py test scheduler.tests.test_preservation``
rewrites the fixture, and ``scheduler/tests/golden.py`` refuses to do it once any
production file the golden depends on has changed.  Read that module before
reaching for the flag: regenerating after a solver change destroys the baseline
rather than fixing anything.
"""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any, Dict, List

from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in
from django.test import TestCase
from django.urls import reverse
from ortools.sat.python import cp_model

from scheduler.models import Assignment, Schedule, UnassignedWell
from scheduler.optimization import (
    DETERMINISTIC_INTERLEAVE_BATCH_SIZE,
    calibrate_solver_budget,
    calibrate_two_stage_budgets,
)
from scheduler.signals import log_user_login

from .factories import (
    FY_API_LABEL,
    FY_START,
    UNIQUE_OPTIMUM_TIME_LIMIT_SECONDS,
    build_unique_optimum_scenario,
)
from .golden import (
    FIXTURE_PATH,
    REGENERATE_ENV_FLAG,
    assert_regeneration_is_safe,
    golden_exists,
    jsonable,
    load_golden,
    production_file_drift,
    REBASELINEABLE_FIELDS,
    regeneration_requested,
    write_golden,
)
from .support import (
    derive_sequence_orders,
    schedule_hash_of,
    solve_once,
    solve_with_actuals_once,
)
from .test_tie_enumeration import (
    ENUMERATION_CAP,
    _forbid_schedule,
    _selected_triples,
)
from .support import build_model_with_objective

CASE_UNIQUE_OPTIMUM = "unique_optimum"
CASE_OPTIMUM_UNIQUENESS = "optimum_uniqueness"
CASE_PERFORMANCE_MODE = "performance_mode"
CASE_SOLVE_WITH_ACTUALS = "solve_with_actuals"
CASE_SAVE_PATH = "save_path"

#: Every case the fixture must contain.  A partial capture is never written, so
#: the fixture is either complete or absent.
CASE_NAMES = (
    CASE_UNIQUE_OPTIMUM,
    CASE_OPTIMUM_UNIQUENESS,
    CASE_PERFORMANCE_MODE,
    CASE_SOLVE_WITH_ACTUALS,
    CASE_SAVE_PATH,
)

#: Accumulates records during a regeneration run.  Django rolls each
#: ``TestCase`` back independently, so the fixture is assembled here in memory
#: and written once from ``tearDownModule``.
_CAPTURED: Dict[str, Any] = {}

#: Actual dates to pin in the ``solve_with_actuals`` observation.
#:
#: Deliberately *later* than the free optimum, which starts both rigs' first
#: well on day 0.  Pinning a well where the solver would have put it anyway
#: would make the observation vacuous — it has to be visible that the pin, not
#: the objective, decided the date.  ``end`` is inclusive and consistent with
#: the well's duration so ``_apply_actuals_duration_adjustments``
#: (``optimization.py:1440-1456``) leaves the duration alone and the pin is
#: purely temporal.
PINNED_ACTUALS = (
    {"well": "WELL-002", "rig": "RIG-01", "start_offset": 60, "duration": 33},
    {"well": "WELL-004", "rig": "RIG-02", "start_offset": 45, "duration": 29},
)


def _fixed_actuals(order=(0, 1)) -> List[Dict[str, Any]]:
    """Build the ``fixed_actuals`` payload in a chosen input order.

    ``order`` exists so the same records can be submitted in both orders, which
    is how the ``(well, rig)`` sort at ``optimization.py:1527-1528`` is
    observed: it must make the input order irrelevant.
    """
    records = []
    for index in order:
        spec = PINNED_ACTUALS[index]
        start = FY_START + timedelta(days=spec["start_offset"])
        end = start + timedelta(days=spec["duration"] - 1)
        records.append(
            {
                "well": spec["well"],
                "rig": spec["rig"],
                "actual_start_date": start,
                "actual_end_date": end,
            }
        )
    return records


# ---------------------------------------------------------------------------
# Module-level capture lifecycle
# ---------------------------------------------------------------------------


def setUpModule():
    """Fail fast if this run would destroy an existing baseline."""
    if regeneration_requested():
        # Checked here as well as at write time so a refusal costs nothing
        # instead of arriving after every solve has been paid for.
        assert_regeneration_is_safe()
        print(
            f"\n[{REGENERATE_ENV_FLAG}=1] capturing preservation goldens into "
            f"{FIXTURE_PATH}"
        )


def tearDownModule():
    """Write the fixture, but only if every case was captured."""
    if not regeneration_requested():
        return
    missing = [name for name in CASE_NAMES if name not in _CAPTURED]
    if missing:
        raise AssertionError(
            "Refusing to write a partial preservation golden. Missing cases: "
            f"{missing}. Some observation failed during the capture run — fix "
            "that first, because a fixture with holes in it silently stops "
            "checking whatever is missing."
        )
    write_golden(_CAPTURED)


# ---------------------------------------------------------------------------
# Record builders — shared by capture and verification
# ---------------------------------------------------------------------------


def _assignment_records(results: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The schedule, as the fixture stores it.

    ``(well, rig, start_day, end_day, sequence_order)`` per task 2's first
    bullet, plus the dates and the per-assignment costs, sorted by
    ``(rig, well)`` so the list is a canonical description of the schedule
    rather than of the optimizer's emission order.
    """
    sequence_orders = derive_sequence_orders(results.get("assignments", []))
    records = [
        {
            "well": str(a["well"]),
            "rig": str(a["rig"]),
            "start_day": int(a["well_start_day"]),
            "end_day": int(a["well_end_day"]),
            "start_date": a["well_start_date"],
            "end_date": a["well_end_date"],
            "duration_days": int(a["duration_days"]),
            "sequence_order": sequence_orders[(str(a["rig"]), str(a["well"]))],
            "drilling_cost_inr": a.get("drilling_cost_inr"),
            "ilm_cost": a.get("ilm_cost"),
            "ilm_days": a.get("ilm_days"),
        }
        for a in results.get("assignments", [])
    ]
    return sorted(records, key=lambda r: (r["rig"], r["well"]))


def _solve_record(observation) -> Dict[str, Any]:
    """Everything about a solve that is a pure function of its inputs."""
    results = observation.results
    return {
        "solver_status": results.get("solver_status"),
        "is_optimal": bool(results.get("is_optimal")),
        "is_feasible": bool(results.get("is_feasible")),
        "objective_value": results.get("objective_value"),
        "best_bound": results.get("best_bound"),
        "optimality_gap": results.get("optimality_gap"),
        "schedule_hash": results.get("schedule_hash"),
        "model_fingerprint": observation.model_fingerprint,
        "wells_assigned_count": results.get("wells_assigned_count"),
        "wells_unassigned_count": results.get("wells_unassigned_count"),
        "wells_total_count": results.get("wells_total_count"),
        "rigs_used_count": results.get("rigs_used_count"),
        "rigs_total_count": results.get("rigs_total_count"),
        "unassigned_wells": sorted(results.get("unassigned_wells", [])),
        "total_drilling_cost": results.get("total_drilling_cost"),
        "total_ilm_cost": results.get("total_ilm_cost"),
        "total_cost": results.get("total_cost"),
        "project_end_day": results.get("project_end_day"),
        "project_end_date": results.get("project_end_date"),
        "fy_start_date": results.get("fy_start_date"),
        "fy_end_date": results.get("fy_end_date"),
        "fy_constrained": results.get("fy_constrained"),
        "assignments": _assignment_records(results),
        "solver_parameters_explicit": observation.solver_parameters,
        "solver_parameters_effective": observation.solver_parameters_effective,
    }


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------


#: The three solver parameters task 3 exists in order to change.
#:
#: The golden records the *whole* parameter block, and on the deterministic path
#: these three are exactly what design decision 1 replaces: the wall-clock stop
#: becomes a backstop (``max_time_in_seconds`` 10 -> 12.75 at a 10 s limit,
#: stage 1's 0.85 share of 1.5 x 10), the work budget becomes the binding limit
#: (``max_deterministic_time`` inf -> 5.1, stage 1's 0.85 share of 0.60 x 10)
#: and the interleaved batch size is pinned instead of derived
#: (``interleave_batch_size`` 0 -> 1).  Task 2's own capture notes say so:
#: "max_deterministic_time = inf (unset — the wall clock is the only limit
#: today, which is precisely what task 3 changes)".
#:
#: So these keys are exempted from the *equality* check on the deterministic
#: cases and asserted positively instead, against the calibration the settings
#: block prescribes.  Nothing else is exempted: every schedule value — the
#: assignments, the dates, the costs, ``objective_value``, ``schedule_hash``,
#: ``model_fingerprint`` — is still compared byte for byte, and the golden file
#: itself is untouched.  Performance mode gets no exemption at all, because
#: clause 3.12 promises that block does not move.
STOP_CRITERION_PARAMETER_KEYS = (
    "max_time_in_seconds",
    "max_deterministic_time",
    "interleave_batch_size",
)

#: The two recorded parameter dicts the exemption applies to.
_PARAMETER_RECORD_KEYS = (
    "solver_parameters_explicit",
    "solver_parameters_effective",
)


def _without_stop_criterion_parameters(record: Dict[str, Any]) -> Dict[str, Any]:
    """A copy of ``record`` with the task-3-owned parameter keys removed."""
    stripped = dict(record)
    for record_key in _PARAMETER_RECORD_KEYS:
        block = stripped.get(record_key)
        if isinstance(block, dict):
            stripped[record_key] = {
                key: value
                for key, value in block.items()
                if key not in STOP_CRITERION_PARAMETER_KEYS
            }
    return stripped


def assert_stop_criterion_parameters(
    test, observation, time_limit_seconds: float
) -> None:
    """The stopping criterion is the calibration, not the pre-fix wall clock.

    The replacement for the equality check the exemption above removes.  It is a
    stronger statement than "these three keys differ from the golden": it pins
    them to ``calibrate_two_stage_budgets``, so a wrong ratio, a lost pin or a
    mis-sized stage split fails here rather than passing unnoticed.

    **Why the stage-1 share and not the whole-request budget.** ``observation``
    records the parameters of the solver the *reported metrics* come from, which
    is stage 1's (``optimization.py`` gives stage 2 its own ``CpSolver`` so
    ``self.solver`` keeps holding stage 1's counters). Since task 4 that solver
    carries ``D1 = (1 - CANONICALIZE_BUDGET_SHARE) x D`` and
    ``0.85 x FACTOR x T``, not the undivided budget. Asserting the whole-request
    numbers here would be asserting a quantity no single solver is ever
    configured with.

    Nothing is relaxed by the change: the two shares are additionally asserted to
    sum back to the whole-request budget and to exactly ``FACTOR x T``, so the
    total ceiling Property 4 bounds is pinned as well as the share.
    """
    whole = calibrate_solver_budget(time_limit_seconds)
    budgets = calibrate_two_stage_budgets(time_limit_seconds)
    budget = budgets.stage_one
    stage_two = budgets.stage_two
    effective = observation.solver_parameters_effective

    test.assertAlmostEqual(
        effective["max_deterministic_time"],
        budget.deterministic_budget,
        places=6,
        msg="The deterministic budget must be the binding limit (design "
        "decision 1), at stage 1's share of it. If this is 'inf' the work "
        "budget was never applied and the run is back on the wall clock.",
    )
    test.assertAlmostEqual(
        effective["max_time_in_seconds"],
        budget.wall_backstop_seconds,
        places=6,
        msg="max_time_in_seconds must be the backstop, not the binding limit.",
    )
    # The split must not leak budget in either direction: the two shares add
    # back up to the whole-request calibration, exactly.
    assert stage_two is not None
    test.assertTrue(
        budgets.deterministic_budgets_sum_exactly,
        "D1 + D2 must equal D exactly.",
    )
    test.assertTrue(
        budgets.wall_backstops_sum_exactly,
        "The two stage backstops must sum to exactly WALL_BACKSTOP_FACTOR x T, "
        "which is the total wall ceiling Property 4 bounds.",
    )
    test.assertAlmostEqual(
        budget.wall_backstop_seconds + stage_two.wall_backstop_seconds,
        whole.wall_backstop_factor * time_limit_seconds,
        places=6,
    )
    # No ``<= 1.2 x T`` ceiling is asserted on the backstop. The design's
    # Property 4 bound is superseded: holding the *work* fixed is what makes the
    # answer reproducible, and a contended machine needs more elapsed time for
    # the same work, so a tight wall bound and same-machine determinism are
    # mutually exclusive. Determinism wins, and WALL_BACKSTOP_FACTOR is sized
    # from measured contention instead (see drilling_scheduler/settings.py).
    # What is asserted is that the backstop in force is exactly stage 1's share
    # of the configured multiple of the selected limit — and, just above, that
    # the two shares add back up to that multiple.
    test.assertAlmostEqual(
        effective["max_time_in_seconds"],
        budget.stage_share * budget.wall_backstop_factor * time_limit_seconds,
        places=6,
        msg="The backstop must be stage 1's share of the configured "
        "WALL_BACKSTOP_FACTOR x T.",
    )
    test.assertEqual(
        effective["interleave_batch_size"],
        DETERMINISTIC_INTERLEAVE_BATCH_SIZE,
        "interleave_batch_size must be pinned rather than derived, so an "
        "OR-Tools upgrade cannot change the search path silently.",
    )


class GoldenCaseMixin:
    """Capture-or-verify plus a readable diff."""

    def check_case(
        self,
        name: str,
        record: Dict[str, Any],
        exempt_stop_criterion_parameters: bool = False,
    ) -> None:
        record = jsonable(record)

        if regeneration_requested():
            _CAPTURED[name] = record
            print(f"\n=== CAPTURED [{name}] ===\n{json.dumps(record, indent=2)}")
            return

        golden = load_golden()
        cases = golden.get("cases") or {}
        self.assertIn(
            name,
            cases,
            f"Case '{name}' is missing from {FIXTURE_PATH}. The fixture predates "
            "this observation and must be recaptured from unfixed code.",
        )
        expected = cases[name]
        if exempt_stop_criterion_parameters:
            expected = _without_stop_criterion_parameters(expected)
            record = _without_stop_criterion_parameters(record)
        self._assert_matches(name, expected, record)

    def _assert_matches(
        self, name: str, expected: Dict[str, Any], actual: Dict[str, Any]
    ) -> None:
        if expected == actual:
            return

        differences: List[str] = []
        for key in sorted(set(expected) | set(actual)):
            want = expected.get(key, "<absent>")
            got = actual.get(key, "<absent>")
            if want == got:
                continue
            if key == "assignments" and isinstance(want, list) and isinstance(got, list):
                differences.append(self._assignment_diff(want, got))
            else:
                differences.append(f"  {key}:\n    golden : {want!r}\n    now    : {got!r}")

        drift = production_file_drift(load_golden())
        drift_note = (
            "\nProduction files changed since the golden was captured:\n"
            + "\n".join(f"  - {path}" for path in sorted(drift))
            if drift
            else "\nNo production file has changed since the golden was captured, "
            "so this difference comes from the environment (library version, "
            "database, platform) rather than from a code change."
        )

        self.fail(
            f"Preservation violated for case '{name}'.\n\n"
            "This request closes to a proven, unique optimum, so clause 3.8 and "
            "Property 2 require byte-identical output to the pre-fix baseline "
            f"recorded in {FIXTURE_PATH}.\n\n"
            + "\n".join(differences)
            + "\n"
            + drift_note
            + "\n\nDo NOT regenerate the fixture to clear this. The golden is the "
            "only record of the pre-fix answer; regenerating replaces it with the "
            "answer that is currently under suspicion."
        )

    @staticmethod
    def _assignment_diff(expected: List[Dict], actual: List[Dict]) -> str:
        def key(record):
            return (record.get("rig"), record.get("well"))

        want = {key(r): r for r in expected}
        got = {key(r): r for r in actual}
        lines = ["  assignments:"]
        for missing in sorted(set(want) - set(got)):
            lines.append(f"    only in golden: {want[missing]}")
        for added in sorted(set(got) - set(want)):
            lines.append(f"    only now      : {got[added]}")
        for shared in sorted(set(want) & set(got)):
            if want[shared] == got[shared]:
                continue
            changed = {
                field: (want[shared].get(field), got[shared].get(field))
                for field in sorted(set(want[shared]) | set(got[shared]))
                if want[shared].get(field) != got[shared].get(field)
            }
            lines.append(f"    {shared} changed: {changed}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Case 1 — the ¬isBugCondition schedule, and its uniqueness
# ---------------------------------------------------------------------------


class UniqueOptimumPreservationTests(GoldenCaseMixin, TestCase):
    """A proven, unique optimum must survive the fix untouched."""

    def test_optimum_is_unique(self):
        """The scenario has exactly one schedule at the optimal objective.

        *Validates: Requirement 3.8 (precondition), Property 2*

        This is the precondition that makes every other test in this file
        meaningful.  Property 2 is defined over requests where
        ``isBugCondition`` is **false**, and ``hasObjectiveTies`` is one of that
        predicate's three disjuncts — so if this scenario's optimum were tied,
        it would be a bug-condition request and the golden below would be one
        arbitrary member of a tied set rather than *the* answer.

        The enumeration is the one from ``test_tie_enumeration``, imported
        rather than copied so both files count schedules identically: solve,
        record the schedule, add a no-good clause forbidding exactly that
        schedule, repeat until ``INFEASIBLE``.  Counting schedules (assignment
        pattern plus the start day of each selected pair) rather than full
        variable assignments matters here — ``start_time_sum``
        (``optimization.py:1394``) sums the start variables of unselected pairs
        too, and ``project_end >= e`` (``:1277``) leaves unselected end
        variables slack, so one schedule corresponds to many full solutions.
        """
        scenario = build_unique_optimum_scenario(suffix="UNIQENUM")
        scheduler, objective_expr = build_model_with_objective(scenario)
        model = scheduler.model
        assert model is not None

        solver = cp_model.CpSolver()
        solver.parameters.num_search_workers = 1
        solver.parameters.random_seed = 42
        solver.parameters.max_time_in_seconds = 60.0
        status = solver.Solve(model)
        self.assertEqual(
            status,
            cp_model.OPTIMAL,
            "The preservation scenario must prove OPTIMAL, otherwise it is not "
            "in the not-isBugCondition regime Property 2 is about; got "
            f"{solver.StatusName(status)}.",
        )
        v_star = int(round(solver.ObjectiveValue()))

        model.Add(objective_expr == v_star)

        hashes: List[str] = []
        hit_cap = True
        for iteration in range(ENUMERATION_CAP):
            enumerator = cp_model.CpSolver()
            enumerator.parameters.num_search_workers = 1
            enumerator.parameters.random_seed = 42
            enumerator.parameters.max_time_in_seconds = 60.0
            enum_status = enumerator.Solve(model)
            if enum_status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                hit_cap = False
                break
            hashes.append(schedule_hash_of(_selected_triples(scheduler, enumerator)))
            _forbid_schedule(scheduler, enumerator, iteration)

        tied = sorted(set(hashes))
        print(
            f"\n=== PRESERVATION SCENARIO UNIQUENESS ===\n"
            f"optimal objective V*   : {v_star}\n"
            f"schedules attaining V* : {len(tied)}\n"
            f"hashes                 : {tied}\n"
            f"enumeration exhausted  : {not hit_cap}"
        )

        self.assertFalse(
            hit_cap,
            f"Enumeration hit the {ENUMERATION_CAP}-schedule cap without "
            f"exhausting the set at V* = {v_star}, so uniqueness is unproven.",
        )
        self.assertEqual(
            len(tied),
            1,
            f"The preservation scenario has {len(tied)} schedules tied at the "
            f"optimal objective {v_star}, so it is a bug-condition request, not "
            "a preservation one. Property 2 would be asserting that an "
            "arbitrary member of a tied set never changes, which task 4 is "
            "entitled to change. Make the scenario's optimum unique "
            "(factories.build_unique_optimum_scenario) rather than relaxing "
            f"this assertion. Tied hashes: {tied}",
        )

        self.check_case(
            CASE_OPTIMUM_UNIQUENESS,
            {
                "optimal_objective_value": v_star,
                "schedules_at_optimal_objective": len(tied),
                "schedule_hash": tied[0],
                "enumeration_exhausted": not hit_cap,
            },
        )

    def test_unique_optimum_matches_golden(self):
        """The proven-optimal schedule equals the pre-fix baseline.

        *Validates: Requirements 3.1, 3.4, 3.5, 3.6, 3.7, 3.8*

        This is Property 2's core assertion and the one that catches task 4's
        stage-2 solve changing an answer it must not touch.
        """
        scenario = build_unique_optimum_scenario()
        observation = solve_once(
            scenario,
            time_limit_seconds=UNIQUE_OPTIMUM_TIME_LIMIT_SECONDS,
            deterministic=True,
        )

        self.assertEqual(
            observation.solver_status,
            "OPTIMAL",
            "The golden is only meaningful in the proven-optimal regime; this "
            f"solve returned {observation.solver_status}.",
        )
        # Clause 3.4: these two must survive the fix. Asserted directly as well
        # as through the recorded parameter block, because they are the two
        # parameters the requirements name.
        effective = observation.solver_parameters_effective
        self.assertEqual(effective["num_search_workers"], 1)
        self.assertEqual(effective["random_seed"], 42)
        self.assertEqual(effective["search_branching"], cp_model.AUTOMATIC_SEARCH)

        # The stopping criterion is task 3's, so it is asserted against the
        # calibration rather than against the pre-fix golden. Everything else in
        # the record — the whole schedule — still has to match exactly, and does:
        # this model proves OPTIMAL in well under a second, so the stop never
        # binds and there is only one answer available to return.
        assert_stop_criterion_parameters(
            self, observation, UNIQUE_OPTIMUM_TIME_LIMIT_SECONDS
        )

        self.check_case(
            CASE_UNIQUE_OPTIMUM,
            _solve_record(observation),
            exempt_stop_criterion_parameters=True,
        )


# ---------------------------------------------------------------------------
# Case 2 — performance mode (clause 3.12)
# ---------------------------------------------------------------------------


class PerformanceModePreservationTests(GoldenCaseMixin, TestCase):
    """``deterministic=False`` keeps its parameter block and its answer."""

    def test_performance_mode_matches_golden(self):
        """*Validates: Requirement 3.12*

        Clause 3.12 promises the performance path
        (``scheduler/optimization.py:962-978``) keeps working with no
        determinism guarantee attached.  The fix must not give it a
        deterministic budget or a second canonicalising stage, so what is
        recorded here is primarily the **parameter block**: multi-threaded
        (``num_search_workers = 0``, auto-detect), ``PORTFOLIO_SEARCH``, seed
        42, no ``max_deterministic_time``.

        The schedule is recorded too, and that is sound despite the mode being
        multi-threaded: this scenario has a unique optimum (see
        ``test_optimum_is_unique``), so every solver that proves optimality has
        exactly one schedule available to return, whatever path it took.  A
        difference here therefore means the model or the economics moved, not
        that a race resolved differently.
        """
        scenario = build_unique_optimum_scenario(suffix="PERF")
        observation = solve_once(
            scenario,
            time_limit_seconds=UNIQUE_OPTIMUM_TIME_LIMIT_SECONDS,
            deterministic=False,
        )

        self.assertEqual(observation.solver_status, "OPTIMAL")
        effective = observation.solver_parameters_effective
        self.assertEqual(
            effective["num_search_workers"],
            0,
            "Performance mode must stay multi-threaded (0 = auto-detect).",
        )
        self.assertEqual(effective["search_branching"], cp_model.PORTFOLIO_SEARCH)
        self.assertEqual(
            effective["max_deterministic_time"],
            "inf",
            "Performance mode must not be given a deterministic budget — "
            "clause 3.12 attaches no determinism promise to it, and task 3's "
            "budget belongs to the deterministic path only. Unbudgeted is "
            "spelled 'inf' here: this parameter's proto default is infinity, "
            "not zero, and support._jsonable_parameter_value renders a "
            "non-finite float as the text-format spelling. Zero would be the "
            "opposite claim — a budget of no work at all.",
        )

        self.check_case(CASE_PERFORMANCE_MODE, _solve_record(observation))


# ---------------------------------------------------------------------------
# Case 3 — locked actuals (clauses 3.10, 3.11)
# ---------------------------------------------------------------------------


class SolveWithActualsPreservationTests(GoldenCaseMixin, TestCase):
    """``solve_with_actuals`` pins actuals exactly and ignores input order."""

    def test_actuals_are_pinned_and_match_golden(self):
        """*Validates: Requirements 3.10, 3.11*

        Two wells are pinned to dates the free optimum would not have chosen
        (both rigs start their first well on day 0 when left alone), so the
        assertion below can only pass if ``apply_actual_constraints``
        (``optimization.py:1458-1513``) really did fix the dates.  Task 4 routes
        this path through the same two stages, and stage 2 must not move a
        pinned well — this is the test that says so.
        """
        scenario = build_unique_optimum_scenario(suffix="ACT")
        observation = solve_with_actuals_once(
            scenario,
            _fixed_actuals(),
            time_limit_seconds=UNIQUE_OPTIMUM_TIME_LIMIT_SECONDS,
        )

        self.assertIn(observation.solver_status, ("OPTIMAL", "FEASIBLE"))

        by_well = {
            str(a["well"]): a for a in observation.results.get("assignments", [])
        }
        for spec in PINNED_ACTUALS:
            well = spec["well"]
            expected_start = FY_START + timedelta(days=spec["start_offset"])
            expected_end = expected_start + timedelta(days=spec["duration"] - 1)
            self.assertIn(
                well,
                by_well,
                f"{well} was pinned to {spec['rig']} but is not in the result.",
            )
            assignment = by_well[well]
            self.assertEqual(assignment["rig"], spec["rig"])
            self.assertEqual(
                assignment["well_start_date"],
                expected_start,
                f"{well}'s actual start date was not pinned exactly.",
            )
            self.assertEqual(
                assignment["well_end_date"],
                expected_end,
                f"{well}'s actual end date was not pinned exactly.",
            )

        # Same exemption as case 1, same reason: the re-optimization path shares
        # _configure_solver_for_determinism, so its stopping criterion moved too.
        assert_stop_criterion_parameters(
            self, observation, UNIQUE_OPTIMUM_TIME_LIMIT_SECONDS
        )

        self.check_case(
            CASE_SOLVE_WITH_ACTUALS,
            _solve_record(observation),
            exempt_stop_criterion_parameters=True,
        )

    def test_fixed_actuals_input_order_is_irrelevant(self):
        """*Validates: Requirement 3.10*

        ``solve_with_actuals`` sorts ``fixed_actuals`` by ``(well, rig)`` before
        applying it (``optimization.py:1527-1528``).  That sort is not directly
        observable, but its consequence is: ``apply_actual_constraints`` adds
        constraints in list order, so without the sort the two input orders
        would build different model protos and produce different fingerprints.
        Comparing fingerprints tests the guarantee the sort exists to provide,
        rather than the presence of the sort call.

        No golden case is needed — this is an invariant of the current code and
        of the fixed code alike.
        """
        scenario = build_unique_optimum_scenario(suffix="ACTORD")
        forward = solve_with_actuals_once(
            scenario, _fixed_actuals((0, 1)),
            time_limit_seconds=UNIQUE_OPTIMUM_TIME_LIMIT_SECONDS,
        )
        reverse_order = solve_with_actuals_once(
            scenario, _fixed_actuals((1, 0)),
            time_limit_seconds=UNIQUE_OPTIMUM_TIME_LIMIT_SECONDS,
        )

        self.assertEqual(
            forward.model_fingerprint,
            reverse_order.model_fingerprint,
            "Reversing the fixed_actuals input order changed the model proto, "
            "so the (well, rig) sort at optimization.py:1527-1528 is not doing "
            "its job and the re-optimization path is input-order dependent.",
        )
        self.assertEqual(forward.schedule_hash, reverse_order.schedule_hash)
        self.assertEqual(forward.objective_value, reverse_order.objective_value)


# ---------------------------------------------------------------------------
# Case 4 — the save path (clause 3.13)
# ---------------------------------------------------------------------------


class SavePathPreservationTests(GoldenCaseMixin, TestCase):
    """The persisted schedule keeps its shape.

    Driven through the real ``POST /api/schedules/create_schedule/`` endpoint
    (``scheduler/views.py:1882``) rather than by re-implementing the save
    logic, so what is recorded is what Django actually wrote: ``Assignment``
    rows with per-rig ``sequence_order``, and ``UnassignedWell`` rows with a
    rejection reason.
    """

    def setUp(self):
        super().setUp()
        self.user = get_user_model().objects.create_superuser(
            username="preservation-harness",
            email="harness@example.invalid",
            password="harness-not-a-real-password",
        )
        self._login_without_audit_signal()

    def _login_without_audit_signal(self) -> None:
        """Log the client in with the login-audit receiver disconnected.

        ``force_login`` does not go through a view: Django's
        ``Client._login`` sends ``user_logged_in`` with a bare
        ``HttpRequest()``, whose ``method`` is ``None``.  The production
        receiver ``scheduler.signals.log_user_login`` passes that straight to
        ``UserActivity.log``, which stores ``request_method = request.method``
        (``scheduler/models.py:3513``) into a NOT NULL column — so PostgreSQL
        raises ``NotNullViolation``.  The receiver's own ``except Exception``
        swallows the error, but by then the ``TestCase`` atomic block is
        poisoned and every later query in the test fails, including
        ``force_login``'s own ``request.session.save()``.

        This is an artifact of the synthetic request, not a production defect:
        a real login arrives through a view where ``method`` is always set.
        The receiver is therefore disconnected for the login only, and
        reconnected via ``addCleanup`` so no other test is affected.  Nothing
        this case observes concerns login auditing.
        """
        user_logged_in.disconnect(log_user_login)
        self.addCleanup(user_logged_in.connect, log_user_login)
        self.client.force_login(self.user)

    def test_save_path_matches_golden(self):
        """*Validates: Requirement 3.13*

        Two invariants, per task 2's fourth bullet:

        * ``sequence_order`` is derived per rig from the start date
          (``views.py:1988-1997``) — asserted against
          ``support.derive_sequence_orders``, which is also what case 1's golden
          uses, so this doubles as the cross-check that the helper agrees with
          production.
        * unassigned wells are persisted with rejection analysis
          (``views.py:2069-2084``).

        Two defects in the current code are captured here as-is, because this
        is an observation task and Property 2 is about preserving today's
        behaviour, not today's intentions.  Both are out of scope for this spec
        and neither is fixed here:

        * ``UnassignedWell.reason`` comes back as an analyser error string.
          ``WellRejectionAnalyzer`` reads ``rigs_df['capacity_hp']``
          (``well_rejection_analyzer.py:49``) while ``views.py:2044`` builds
          that frame with a ``rig_capacity_hp`` column, so the lookup raises
          ``KeyError`` and the broad ``except`` turns it into the stored text.
        * ``Schedule.unassigned_wells_count`` stays 0.  ``views.py:1968`` reads
          ``results['unassigned_wells_count']`` but ``_extract_solution``
          publishes ``wells_unassigned_count`` (``optimization.py:1868``), so
          the ``.get(..., 0)`` default always wins.
        """
        scenario = build_unique_optimum_scenario(suffix="SAVE")

        response = self.client.post(
            reverse("schedule-create-schedule"),
            data={
                "name": "Preservation Golden",
                "financial_year": FY_API_LABEL,
                "rig_ids": [str(rig.id) for rig in scenario.rigs],
                "well_ids": [str(well.id) for well in scenario.wells],
                "time_limit_seconds": UNIQUE_OPTIMUM_TIME_LIMIT_SECONDS,
            },
            content_type="application/json",
        )
        self.assertEqual(
            response.status_code,
            200,
            f"create_schedule failed: {response.status_code} {response.content!r}",
        )

        schedule = Schedule.objects.get(id=response.json()["id"])
        self.assertEqual(schedule.status, "COMPLETED")

        assignments = list(
            Assignment.objects.filter(schedule=schedule)
            .select_related("rig", "well")
            .order_by("rig__name", "sequence_order")
        )
        self.assertTrue(assignments, "No Assignment rows were persisted.")

        # sequence_order must be a per-rig 1..n ranking by start date.
        by_rig: Dict[str, List[Assignment]] = {}
        for assignment in assignments:
            by_rig.setdefault(assignment.rig.name, []).append(assignment)
        for rig_name, rows in by_rig.items():
            expected = sorted(rows, key=lambda a: a.well_start_date)
            self.assertEqual(
                [row.sequence_order for row in expected],
                list(range(1, len(rows) + 1)),
                f"sequence_order on {rig_name} is not a 1..n ranking by start "
                "date (views.py:1988-1997).",
            )

        # ... and it must agree with the derivation case 1's golden relies on.
        derived = derive_sequence_orders(
            [
                {
                    "rig": assignment.rig.name,
                    "well": assignment.well.name,
                    "well_start_date": assignment.well_start_date,
                }
                for assignment in assignments
            ]
        )
        for assignment in assignments:
            self.assertEqual(
                assignment.sequence_order,
                derived[(assignment.rig.name, assignment.well.name)],
                "Persisted sequence_order disagrees with "
                "support.derive_sequence_orders, so the helper the other "
                "goldens use no longer mirrors the save path.",
            )

        unassigned = list(
            UnassignedWell.objects.filter(schedule=schedule)
            .select_related("well")
            .order_by("well__name")
        )
        self.assertTrue(
            unassigned, "No UnassignedWell rows were persisted (clause 3.13)."
        )
        for row in unassigned:
            self.assertTrue(
                (row.reason or "").strip(),
                f"UnassignedWell for {row.well.name} carries no reason.",
            )

        record = {
            "response_status_code": response.status_code,
            "schedule_status": schedule.status,
            "solver_status": schedule.solver_status,
            "schedule_hash": schedule.schedule_hash,
            "optimality_gap_percent": schedule.optimality_gap_percent,
            "total_drilling_cost": schedule.total_drilling_cost,
            "total_ilm_cost": schedule.total_ilm_cost,
            "project_end_date": schedule.project_end_date,
            "input_rigs_count": schedule.input_rigs_count,
            "input_wells_count": schedule.input_wells_count,
            # Recorded knowing it is wrong today (see the docstring); the
            # golden's job is to notice if it changes, not to endorse it.
            "unassigned_wells_count_field": schedule.unassigned_wells_count,
            "assignments": sorted(
                (
                    {
                        "rig": assignment.rig.name,
                        "well": assignment.well.name,
                        "start_date": assignment.well_start_date,
                        "end_date": assignment.well_end_date,
                        "sequence_order": assignment.sequence_order,
                        "drilling_cost": assignment.drilling_cost,
                        "ilm_cost": assignment.ilm_cost,
                        "ilm_days": assignment.ilm_days,
                    }
                    for assignment in assignments
                ),
                key=lambda row: (row["rig"], row["well"]),
            ),
            "unassigned": [
                {"well": row.well.name, "reason": row.reason} for row in unassigned
            ],
        }
        self.check_case(CASE_SAVE_PATH, record)


# ---------------------------------------------------------------------------
# The fixture's own provenance
# ---------------------------------------------------------------------------


class GoldenProvenanceTests(TestCase):
    """The fixture must say where it came from.

    A golden without provenance is folklore: when it eventually disagrees with
    the code there is no way to tell whether the code regressed or the baseline
    was captured from something else entirely.  These assertions keep the
    audit trail from rotting quietly.
    """

    def test_provenance_is_complete(self):
        if regeneration_requested():
            self.skipTest("fixture is being rewritten in this run")
        golden = load_golden()
        provenance = golden.get("provenance") or {}

        commit = provenance.get("git_commit")
        self.assertIsInstance(commit, str, "No git commit recorded in the fixture.")
        self.assertEqual(
            len(commit),
            40,
            f"Expected a full 40-character commit SHA, got {commit!r}. The "
            "short form is ambiguous over a repository's lifetime.",
        )

        for key in (
            "captured_at",
            "ortools_version",
            "python_version",
            "django_version",
            "platform",
            "production_file_sha256",
        ):
            self.assertTrue(
                provenance.get(key),
                f"Provenance field '{key}' is missing from the fixture, so the "
                "baseline is not self-describing.",
            )

        history = golden.get("provenance_history") or []

        if not history:
            # A first capture must correspond to the commit it names, full stop.
            self.assertTrue(
                provenance.get("working_tree_clean_of_production_files"),
                "The golden was captured from a working tree with modified "
                "production files, so it does not correspond to commit "
                f"{commit}: "
                f"{provenance.get('working_tree_production_files_modified')}",
            )
        else:
            # A *surgical* re-baseline (golden.rebaseline_fields) re-anchors a
            # named field on an existing fixture rather than re-capturing it, and
            # by construction that happens while the change responsible for the
            # move is still in the working tree. So "the tree was clean" cannot
            # hold, and asserting it would only be satisfiable by committing
            # first — which would say nothing extra, since the recorded
            # production_file_sha256 already identifies the exact code involved.
            #
            # Nothing is relaxed: what replaces it is a stricter set of
            # requirements that a re-baseline must satisfy to be auditable at
            # all. In particular the *original* capture is still required to have
            # been clean, so the pre-fix baseline's correspondence to its commit
            # is still asserted — just from the history entry that now holds it.
            self.assertTrue(
                history[0].get("git_commit"),
                "provenance_history[0] must record the commit the original "
                "pre-fix baseline came from; that SHA is the root of the audit "
                "trail and must not be lost to a re-baseline.",
            )
            self.assertEqual(
                len(history[0]["git_commit"]),
                40,
                "The superseded baseline's commit must be a full 40-character "
                "SHA, for the same reason the current one must.",
            )
            self.assertEqual(
                provenance.get("supersedes_git_commit"),
                history[-1].get("git_commit"),
                "provenance.supersedes_git_commit must name the baseline this "
                "one replaced, so the chain is followable from the top.",
            )
            for key in ("rebaseline_reason", "rebaselined_fields"):
                self.assertTrue(
                    provenance.get(key),
                    f"A re-baselined fixture must record '{key}'. Without it "
                    "the file says a value moved but not why or which, which is "
                    "exactly the folklore this test exists to prevent.",
                )
            self.assertTrue(
                all(
                    field.split(".", 1)[1].split(":", 1)[0].strip()
                    in REBASELINEABLE_FIELDS
                    for field in provenance["rebaselined_fields"]
                ),
                "A re-baseline may only re-anchor "
                f"{list(REBASELINEABLE_FIELDS)}. Anything else means an answer "
                "field was overwritten, which destroys the baseline instead of "
                "re-anchoring it: "
                f"{provenance['rebaselined_fields']}",
            )
            for entry in history:
                self.assertTrue(
                    entry.get("reason"),
                    "Every superseded baseline must carry the reason it was "
                    f"superseded; this one does not: {entry.get('git_commit')}",
                )
                self.assertTrue(
                    entry.get("production_file_sha256"),
                    "Every superseded baseline must keep the production-file "
                    "hashes it was captured against, or the chain cannot be "
                    "verified after the fact.",
                )

        self.assertEqual(
            sorted(golden.get("cases") or {}),
            sorted(CASE_NAMES),
            "The fixture's case set does not match this module's.",
        )

    def test_model_fingerprint_is_still_compared_byte_for_byte(self):
        """Re-baselining a value must not stop the value being checked.

        Task 7 moved two ``model_fingerprint`` values and they were re-anchored
        rather than exempted, on the explicit grounds that re-anchoring keeps the
        field under comparison while an exemption would blind the test to it
        permanently.  That reasoning is only true if it stays true, so it is
        asserted here rather than left as an intention in a commit message.

        Two things are checked, because the first alone is not enough:

        1. ``model_fingerprint`` is not in the exemption list.
        2. The comparison actually fails when the value differs.  A field can be
           absent from an exemption list and still go unchecked if the comparison
           never reaches it — for example if it were dropped before comparison
           or compared only when some other field already matched.
        """
        self.assertNotIn(
            "model_fingerprint",
            STOP_CRITERION_PARAMETER_KEYS,
            "model_fingerprint must never join the exemption list. Option 2 "
            "(re-anchor) was chosen over Option 1 (exempt) precisely so this "
            "field keeps being compared.",
        )

        golden = load_golden()
        case = dict((golden.get("cases") or {})[CASE_UNIQUE_OPTIMUM])
        self.assertIn(
            "model_fingerprint",
            case,
            "PRECONDITION: the case must carry a model_fingerprint, or the "
            "mutation below proves nothing.",
        )

        mutated = dict(case)
        mutated["model_fingerprint"] = "0" * 64

        # The exemption applied to the deterministic cases must not hide it
        # either, so run the mutation through the same stripping the real
        # comparison uses.
        stripped_expected = _without_stop_criterion_parameters(case)
        stripped_actual = _without_stop_criterion_parameters(mutated)

        checker = UniqueOptimumPreservationTests("run")
        with self.assertRaises(
            AssertionError,
            msg="A differing model_fingerprint did NOT fail the comparison, so "
            "the field is effectively unchecked and the re-baseline silently "
            "became an exemption.",
        ):
            checker._assert_matches(
                CASE_UNIQUE_OPTIMUM, stripped_expected, stripped_actual
            )

    def test_production_file_drift_is_reported(self):
        """Report, do not fail, when the code has moved on.

        After task 3 the production files are *expected* to differ from the
        captured baseline while every golden value must still hold — so drift
        is context for a failure elsewhere, never a failure in itself.
        """
        if not golden_exists():
            self.skipTest("no fixture yet")
        drift = production_file_drift(load_golden())
        if drift:
            print(
                "\n=== PRODUCTION FILES CHANGED SINCE THE GOLDEN WAS CAPTURED ===\n"
                + "\n".join(f"  - {path}" for path in sorted(drift))
                + "\nThe golden values above must still hold; that is the point "
                "of Property 2."
            )
        else:
            print(
                "\n[preservation golden] production files are byte-identical to "
                "the captured baseline."
            )
