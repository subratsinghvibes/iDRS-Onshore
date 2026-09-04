"""Repeat-run determinism harness for the ``deterministic-schedule-fix`` spec.

**Property 1: Bug Condition — repeated runs return one schedule.**

*Validates: Requirements 2.1, 2.2, 2.3, 2.12*

These tests encode the **expected** behaviour, not the current behaviour.  On
the unfixed code ``test_repeat_runs_under_cpu_load`` fails, and that failure is
the evidence that the diagnosis in ``bugfix.md`` is correct.  They are re-run
unchanged to verify the fix (tasks 3.5, 4.7 and 9.3) — never rewritten.

Scope
-----
``bugfix.md`` clause 2.3 and its verification criterion set the scope: *same*
machine, *different* CPU load, identical ``schedule_hash``.  Comparing
schedules across machines or CPU architectures is explicitly out of scope, so
nothing here attempts it.

Why the two repeat-run tests are not redundant
----------------------------------------------
``test_repeat_runs_yield_one_schedule_hash`` runs five solves on an idle
machine.  Measured on the unfixed code it **passes** — and the requirements
found the same thing ("1 distinct schedule on an idle machine").  That is not a
contradiction of the diagnosis, it is a property of the mechanism: on an idle
machine the same amount of work happens to fit inside the same wall-clock
window every time, so the stop lands on the same search node.  The idle test is
therefore the clause-2.12 regression guard; it is not the reproduction.

``test_repeat_runs_under_cpu_load`` is the reproduction.  It compares idle runs
against runs executed while the cores are saturated, which is exactly the
situation clause 1.2 describes and the only situation in which a wall-clock
stopping criterion can be observed to be non-reproducible.

Discriminating the mechanism
----------------------------
Both tests record ``solver.deterministic_time``, CP-SAT's work counter.  It is
the measurement that tells the two candidate root causes apart:

* ``schedule_hash`` differs **and** ``deterministic_time`` differs → the stop
  is being taken at different amounts of completed work, i.e. the wall-clock
  stopping criterion (design root cause 1).
* ``schedule_hash`` differs **while** ``deterministic_time`` is identical → the
  stop is not the mechanism and the diagnosis moves to the ordering hazards
  (design root cause 6).
* ``schedule_hash`` never differs at all → there is nothing to fix here and the
  requirements phase has to be revisited.

The harness prints the full table on failure so whichever case applies is
visible without re-running anything.

The fix's own unit tests — budget calibration and stop-reason classification —
live in ``test_solver_budget.py``.  Nothing is added to this file, so that it
stays a fixed baseline rather than a moving target.
"""

from __future__ import annotations

import unittest
from typing import List

from django.test import TestCase

from .factories import (
    HARD_OPEN_TIME_LIMIT_SECONDS,
    build_hard_open_scenario,
)
from .support import (
    CPU_LOAD_ENV_FLAG,
    SolveObservation,
    cpu_load,
    cpu_load_enabled,
    distinct,
    format_observation_table,
    solve_once,
)

#: Repeat count.  ``bugfix.md``'s own property asks for N >= 5.
REPEAT_RUNS = 5

#: How many of the runs execute under load in the mixed test.  Design decision
#: 8: "2 of the runs execute while background busy-loops saturate the cores".
IDLE_RUNS_IN_MIXED = 3
LOADED_RUNS_IN_MIXED = 2

#: ``deterministic_time`` is a work counter, not a clock, so after the fix it is
#: expected to be identical run to run apart from the overshoot past the budget
#: that CP-SAT allows itself (the requirements measured 7.0001 against a 7.0
#: budget, i.e. ~0.0015%).  1% of the smallest observed value is a generous
#: band that still fails loudly on the drift seen today.
DETERMINISTIC_TIME_TOLERANCE_FRACTION = 0.01


class _DeterminismAssertions:
    """Shared reporting and assertions for a set of measured solves."""

    def _report(self, label: str, observations: List[SolveObservation]) -> str:
        det_times = [obs.deterministic_time for obs in observations]
        spread = max(det_times) - min(det_times) if det_times else 0.0
        return "\n".join(
            [
                f"\n=== {label} ===",
                format_observation_table(observations),
                (
                    f"distinct schedule_hash    : {len(distinct(o.schedule_hash for o in observations))}"
                ),
                (
                    f"distinct model_fingerprint: {len(distinct(o.model_fingerprint for o in observations))}"
                ),
                (
                    f"distinct objective_value  : {len(distinct(o.objective_value for o in observations))}"
                ),
                f"deterministic_time spread : {spread:.4f} "
                f"(min {min(det_times):.4f}, max {max(det_times):.4f})"
                if det_times
                else "",
            ]
        )

    def _diagnose(self, observations: List[SolveObservation]) -> str:
        """Plain-language reading of what the numbers imply."""
        hashes = distinct(o.schedule_hash for o in observations)
        det_times = [o.deterministic_time for o in observations]
        det_varies = (max(det_times) - min(det_times)) > 1e-6
        if len(hashes) == 1:
            return (
                "DIAGNOSIS: schedule_hash did not vary in this run set. On the "
                "unfixed code that means this set did not reach the bug "
                "condition; on the fixed code it is the expected outcome."
            )
        if det_varies:
            return (
                "DIAGNOSIS: schedule_hash varies AND deterministic_time varies. "
                "The stop is being taken at different amounts of completed "
                "search work, which is the wall-clock stopping criterion "
                "(scheduler/optimization.py:927, :954) — design root cause 1. "
                "This is the hypothesised mechanism, confirmed."
            )
        return (
            "DIAGNOSIS: schedule_hash varies while deterministic_time is "
            "IDENTICAL. The stopping criterion is therefore NOT the mechanism. "
            "Model construction must be unstable instead — move the diagnosis "
            "to the ordering hazards (design root cause 6) before writing any "
            "fix to the solver configuration."
        )

    def _assert_single_schedule(
        self, label: str, observations: List[SolveObservation]
    ) -> None:
        """Assert Property 1 over a set of solves, reporting every violation."""
        report = self._report(label, observations)
        print(report)

        problems: List[str] = []

        statuses = distinct(o.solver_status for o in observations)
        if statuses == ["OPTIMAL"]:
            problems.append(
                "PRECONDITION: every run proved OPTIMAL, so this scenario no "
                "longer exercises the stops-before-optimality regime that "
                "bugfix.md clause 1.1 is about. The scenario must be resized "
                "(factories.HARD_OPEN_CONFIG) or the assertion is vacuous."
            )

        fingerprints = distinct(o.model_fingerprint for o in observations)
        if len(fingerprints) != 1:
            problems.append(
                f"model_fingerprint is not unique ({len(fingerprints)} distinct: "
                f"{fingerprints}). The input model itself differs between runs, "
                "so this is a model-construction (ordering) failure rather than "
                "a solver-stop failure."
            )

        hashes = distinct(o.schedule_hash for o in observations)
        if len(hashes) != 1:
            problems.append(
                f"schedule_hash is not unique ({len(hashes)} distinct: {hashes})."
            )

        objectives = distinct(o.objective_value for o in observations)
        if len(objectives) != 1:
            problems.append(
                f"objective_value is not unique ({len(objectives)} distinct: "
                f"{objectives})."
            )

        baseline = observations[0]
        for obs in observations[1:]:
            if obs.assignment_tuples != baseline.assignment_tuples:
                only_in_first = sorted(
                    set(baseline.assignment_tuples) - set(obs.assignment_tuples)
                )
                only_in_other = sorted(
                    set(obs.assignment_tuples) - set(baseline.assignment_tuples)
                )
                problems.append(
                    f"run {obs.run_index} assignments differ from run "
                    f"{baseline.run_index}: "
                    f"{len(baseline.assignment_tuples)} vs "
                    f"{len(obs.assignment_tuples)} rows; "
                    f"only in run {baseline.run_index}: {only_in_first[:5]}; "
                    f"only in run {obs.run_index}: {only_in_other[:5]}"
                )

        det_times = [o.deterministic_time for o in observations]
        tolerance = max(min(det_times) * DETERMINISTIC_TIME_TOLERANCE_FRACTION, 1e-6)
        spread = max(det_times) - min(det_times)
        if spread > tolerance:
            problems.append(
                f"deterministic_time is not stable: spread {spread:.4f} exceeds "
                f"tolerance {tolerance:.4f} (values {sorted(det_times)}). Every "
                "run must perform the same amount of search (clause 2.2), which "
                "a wall-clock stop cannot guarantee."
            )

        if problems:
            self.fail(
                "\n".join(
                    [
                        report,
                        "",
                        self._diagnose(observations),
                        "",
                        f"{len(problems)} violation(s) of Property 1:",
                        *(f"  - {p}" for p in problems),
                    ]
                )
            )


class RepeatRunDeterminismTests(_DeterminismAssertions, TestCase):
    """Solve the same request repeatedly and require one schedule."""

    def test_repeat_runs_yield_one_schedule_hash(self):
        """Five identical solves on an idle machine must agree.

        *Validates: Requirements 2.1, 2.12*

        Same rigs, same wells, same financial year, same time limit, a fresh
        ``DrillingScheduler`` per run — exactly what two clicks of Run on
        ``/scheduling/`` do (``scheduler/views.py:1953-1959``).
        """
        scenario = build_hard_open_scenario(suffix="IDLE")
        observations = [
            solve_once(
                scenario,
                time_limit_seconds=HARD_OPEN_TIME_LIMIT_SECONDS,
                run_index=k,
            )
            for k in range(1, REPEAT_RUNS + 1)
        ]
        self._assert_single_schedule(
            f"IDLE x{REPEAT_RUNS} @ {HARD_OPEN_TIME_LIMIT_SECONDS}s", observations
        )

    @unittest.skipUnless(
        cpu_load_enabled(),
        f"set {CPU_LOAD_ENV_FLAG}=1 to run the CPU-load determinism check "
        "(it saturates every core)",
    )
    def test_repeat_runs_under_cpu_load(self):
        """The same request must survive the machine being busy.

        *Validates: Requirements 2.1, 2.2, 2.3, 2.12*

        This is the test that would have caught the original regression, and it
        is the one that reproduces it: three runs on an idle machine and two
        while every core is saturated, all compared as one set.  Clause 2.3
        requires the whole set to agree.

        Gated behind ``IDRS_TEST_CPU_LOAD=1`` so a shared box is not wrecked by
        an unattended run.  The design records it as required before sign-off.
        """
        scenario = build_hard_open_scenario(suffix="LOAD")
        observations: List[SolveObservation] = []
        run_index = 0

        for _ in range(IDLE_RUNS_IN_MIXED):
            run_index += 1
            observations.append(
                solve_once(
                    scenario,
                    time_limit_seconds=HARD_OPEN_TIME_LIMIT_SECONDS,
                    run_index=run_index,
                )
            )

        with cpu_load() as burners:
            print(f"\n[cpu_load: {burners} burner processes]")
            for _ in range(LOADED_RUNS_IN_MIXED):
                run_index += 1
                observations.append(
                    solve_once(
                        scenario,
                        time_limit_seconds=HARD_OPEN_TIME_LIMIT_SECONDS,
                        run_index=run_index,
                        under_load=True,
                    )
                )

        self._assert_single_schedule(
            f"MIXED {IDLE_RUNS_IN_MIXED} idle + {LOADED_RUNS_IN_MIXED} loaded "
            f"@ {HARD_OPEN_TIME_LIMIT_SECONDS}s",
            observations,
        )

