"""Task 9.4 — performance and quality measurement. NOT a test; run on demand.

Deliberately not named ``test_*``: it takes minutes, and a suite that takes
minutes stops being run. It is committed rather than thrown away because clause
2.7 requires the budget calibration be *measured*, and a measurement whose script
is gone cannot be repeated or challenged.

What it reports, per time limit ``T``:

* wall time across **both** solve stages, and the ratio against stage 1's
  wall-clock backstop (``0.85 x WALL_BACKSTOP_FACTOR x T``) — the quantity that
  decides whether a run classifies ``WALL_CLOCK_BACKSTOP`` and is therefore
  reported as not reproducible;
* wells assigned and total cost, for the clause 3.9 no-material-regression check;
* the stop reason, so a starved search shows up as such rather than as a quiet
  quality drop.

On Property 4's ``<= 1.2 x T`` bound
------------------------------------
That bound is **superseded**, deliberately, and this script does not assert it.
Holding the *work* fixed is what makes the answer reproducible, and a contended
machine needs more elapsed time for the same work — so a tight wall bound and
same-machine determinism are mutually exclusive. Determinism won, and
``WALL_BACKSTOP_FACTOR`` is sized from measured contention on this host instead
(see its comment in ``drilling_scheduler/settings.py``). What matters is the
ratio against the backstop actually in force, which is what gets printed.

Run::

    .venv/bin/python manage.py shell < scheduler/tests/measure_performance.py

or, with the test database and fixtures available::

    .venv/bin/python -m scheduler.tests.measure_performance
"""

from __future__ import annotations

import time
from typing import List, Tuple

DEFAULT_TIME_LIMITS: Tuple[int, ...] = (6, 60)


def measure(time_limits: Tuple[int, ...] = DEFAULT_TIME_LIMITS) -> List[dict]:
    from .factories import build_hard_open_scenario
    from .support import new_scheduler
    from scheduler.optimization import calibrate_two_stage_budgets

    scenario = build_hard_open_scenario(suffix="PERF")
    rows: List[dict] = []

    header = (
        f"{'T (s)':>7} {'e2e (s)':>8} {'solver':>8} {'build':>7} "
        f"{'backstop':>9} {'slv/bs':>7} {'s1/s1bs':>8} "
        f"{'det used':>9} {'det bud':>9} {'asgn':>5} "
        f"{'total_cost':>17} {'stop reason':<22} {'hash':<18}"
    )
    print("=" * len(header))
    print("TASK 9.4 PERFORMANCE AND QUALITY MEASUREMENT")
    print("=" * len(header))
    print(header)

    for limit in time_limits:
        scheduler = new_scheduler(scenario)
        started = time.perf_counter()
        results = scheduler.solve(time_limit_seconds=limit, deterministic=True)
        elapsed = time.perf_counter() - started

        # The backstop bounds CP-SAT's own Solve() calls, NOT the end-to-end
        # request. Separating the two matters: at small T the fixed cost of
        # building the model (frames, distance matrix, per-rig ILM matrices,
        # constraints, objective, and the 480 decision-strategy expressions) is a
        # large fraction of elapsed time, so comparing end-to-end wall against
        # the backstop overstates how close a run is to binding.
        stage_one_wall = float(scheduler.solver.wall_time) if scheduler.solver else 0.0
        stage_two_wall = (
            float(scheduler.canonicalization.wall_time)
            if scheduler.canonicalization
            and scheduler.canonicalization.wall_time is not None
            else 0.0
        )
        solver_wall = stage_one_wall + stage_two_wall
        overhead = elapsed - solver_wall

        budgets = calibrate_two_stage_budgets(limit)
        # Stage 1's backstop is what binds first and what the classifier
        # compares against; the two stages' shares sum to FACTOR x T.
        backstop = budgets.stage_one.wall_backstop_seconds
        whole_backstop = (
            budgets.stage_one.wall_backstop_seconds
            + budgets.stage_two.wall_backstop_seconds
        )

        row = {
            "time_limit": limit,
            "wall_seconds": elapsed,
            "solver_wall_seconds": solver_wall,
            "stage_one_wall_seconds": stage_one_wall,
            "stage_two_wall_seconds": stage_two_wall,
            "model_build_overhead_seconds": overhead,
            "stage_one_backstop": backstop,
            "whole_backstop": whole_backstop,
            "solver_wall_over_backstop": solver_wall / whole_backstop,
            "stage_one_wall_over_its_backstop": (
                stage_one_wall / backstop if backstop else None
            ),
            "deterministic_time_used": results["deterministic_time_used"],
            "deterministic_budget": results["deterministic_budget"],
            "wells_assigned": results["wells_assigned_count"],
            "total_cost": results["total_cost"],
            "objective_value": results["objective_value"],
            "stop_reason": results["stop_reason"],
            "deterministic_stop": results["deterministic_stop"],
            "schedule_hash": results["schedule_hash"],
        }
        rows.append(row)

        print(
            f"{limit:>7} {elapsed:>8.2f} {solver_wall:>8.2f} {overhead:>7.2f} "
            f"{whole_backstop:>9.2f} "
            f"{row['solver_wall_over_backstop']:>7.1%} "
            f"{row['stage_one_wall_over_its_backstop']:>8.1%} "
            f"{row['deterministic_time_used']:>9.4f} "
            f"{row['deterministic_budget']:>9.4f} "
            f"{row['wells_assigned']:>5} "
            f"{row['total_cost']:>17,.0f} {str(row['stop_reason']):<22} "
            f"{row['schedule_hash']:<18}"
        )

    print()
    print("Columns:")
    print("  e2e      end-to-end wall time of solve(), including model build")
    print("  solver   CP-SAT Solve() wall time, stage 1 + stage 2")
    print("  build    e2e - solver: frames, distance matrix, per-rig ILM")
    print("           matrices, constraints, objective, decision strategies")
    print("  backstop WHOLE-request wall ceiling "
          "(stage 1 + stage 2 = WALL_BACKSTOP_FACTOR x T)")
    print("  slv/bs   solver wall against that ceiling")
    print("  s1/s1bs  stage-1 solver wall against STAGE 1's own share, which is")
    print("           the ratio the classifier actually tests at 98%")
    print()
    print("Notes:")
    print("  * The backstop bounds CP-SAT's Solve() calls, NOT the end-to-end")
    print("    request. Comparing e2e against it overstates how close a run is")
    print("    to binding, because model-build time is not budgeted.")
    print("  * Property 4's 1.2 x T bound is superseded; see the module")
    print("    docstring and settings.py.")
    return rows


if __name__ == "__main__":  # pragma: no cover - manual invocation
    measure()
