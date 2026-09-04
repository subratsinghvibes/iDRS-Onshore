"""Unit tests for the two-stage lexicographic solve (task 4.5).

*Validates: Requirements 2.5, 3.6, 3.8*

**What stage 2 does, in one line:** it locks the full stage-1 objective as an
equality (``Add(P-expr == V*)``) and minimises only the tie-break expression, so
it cannot change economics and cannot touch a unique optimum.

Everything here is a unit test of that structure.  The *behavioural* claims live
elsewhere and are re-run rather than restated: the tied-set count is
``test_tie_enumeration`` (task 4.6) and byte-identical preservation of a unique
proven optimum is ``test_preservation`` (task 4.7).  This file pins the four
things that can silently go wrong inside the mechanism:

1. **Weight derivation.** ``W1`` must strictly dominate every attainable
   ``rig_well_order`` value, or the two tie-break tiers trade off again and the
   canonicalisation selects nothing in particular.  The stage-2 objective
   maximum must also stay far inside int64.
2. **Preservation on failure.** Stage 2 is allowed to improve the tie-break and
   nothing else.  Every failure mode — infeasible, no solution, no improvement,
   skipped, exception — must return stage 1's schedule intact and say so in
   ``canonicalization_status``.
3. **Metric provenance.** ``objective_value``, ``best_bound``,
   ``optimality_gap``, ``solver_status`` and ``is_optimal`` describe **stage 1**.
   Stage 2's objective is a tie-break index with no business meaning and must
   never reach the payload.
4. **Budget arithmetic.** The two wall shares must sum to exactly
   ``WALL_BACKSTOP_FACTOR x T``, and both must come from ``T`` and the settings
   block only — never from remaining or elapsed wall time, which is the defect
   this spec exists to remove.

Run independently::

    .venv/bin/python manage.py test scheduler.tests.test_two_stage --keepdb
"""

from __future__ import annotations

import inspect
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

from django.test import SimpleTestCase, TestCase
from ortools.sat.python import cp_model

from scheduler.optimization import (
    CANONICALIZATION_ALREADY_CANONICAL,
    CANONICALIZATION_CANONICAL_INCUMBENT,
    CANONICALIZATION_CANONICAL_OPTIMAL,
    CANONICALIZATION_FAILED_INFEASIBLE,
    CANONICALIZATION_SKIPPED_PERFORMANCE_MODE,
    CANONICALIZATION_STAGE_ONE_PRESERVED,
    STAGE_CANONICALIZE,
    STAGE_PRIMARY,
    DrillingScheduler,
    calibrate_solver_budget,
    calibrate_two_stage_budgets,
    determinism_settings,
    max_rig_well_order,
    tiebreak_weights,
)

from .factories import FY_START, build_symmetric_tie_scenario
from .support import build_model_with_objective, new_scheduler, solve_once
from .test_solver_budget import TIME_LIMIT_DROPDOWN_SECONDS

#: Time limit for the two-stage integration checks in this file.  The symmetric
#: tie model proves optimality in well under a second, so the limit never binds
#: and these tests stay fast.
TIE_TIME_LIMIT_SECONDS = 10

#: Well / rig shapes to derive weights for.  Spans a single well on a single rig
#: up to a fleet larger than anything the page can select, so the bound is
#: checked at both ends rather than at one comfortable size.
WEIGHT_SHAPES: Tuple[Tuple[int, int], ...] = (
    (1, 1),
    (2, 2),
    (5, 2),
    (12, 5),
    (26, 5),
    (30, 13),
    (40, 6),
    (100, 20),
)

#: Deliberately generous horizon for the coefficient-range check: ~11 years of
#: days, well past any financial-year window the scheduling page produces.
GENEROUS_HORIZON_DAYS = 4_000

#: Coefficient ceiling.  CP-SAT stores integer coefficients in int64; staying
#: under 2**62 leaves room for the intermediate sums it forms internally.
SAFE_INT64_BOUND = 2 ** 62


def _true_max_rig_well_order(num_wells: int, num_rigs: int) -> int:
    """The largest ``rig_well_order`` any feasible assignment can reach.

    ``rig_well_order`` sums ``well_index x num_rigs + rig_index`` over the
    *selected* pairs, and each well is selected at most once, so the maximum is
    reached by sending every well to the last rig::

        sum over wells i of (i x num_rigs + (num_rigs - 1))

    Computed here independently of production so the assertion compares two
    derivations rather than one derivation with itself.
    """
    return sum(i * num_rigs + (num_rigs - 1) for i in range(num_wells))


class TiebreakWeightDerivationTests(SimpleTestCase):
    """``W1 > max(rig_well_order)``, and the coefficients stay small."""

    def test_w1_dominates_every_attainable_rig_well_order(self):
        """*Validates: Requirements 2.5, 3.6*

        The hierarchy is the whole point of stage 2: start times decide first,
        and the canonical ``(well, rig)`` order only breaks what start times
        leave tied.  If ``W1`` failed to dominate, the two tiers would trade off
        exactly as they do in stage 1 and stage 2 would select an arbitrary
        member of the tied set instead of a canonical one.
        """
        for num_wells, num_rigs in WEIGHT_SHAPES:
            with self.subTest(wells=num_wells, rigs=num_rigs):
                w1, w2 = tiebreak_weights(num_wells, num_rigs)
                attainable = _true_max_rig_well_order(num_wells, num_rigs)
                bound = max_rig_well_order(num_wells, num_rigs)

                self.assertEqual(w2, 1, "W2 is the finest tier and must be 1.")
                self.assertGreaterEqual(
                    bound,
                    attainable,
                    f"max_rig_well_order({num_wells}, {num_rigs}) = {bound} is "
                    f"not a valid upper bound: an assignment can reach "
                    f"{attainable}.",
                )
                self.assertGreater(
                    w1,
                    attainable,
                    f"W1 = {w1} does not dominate the attainable rig_well_order "
                    f"maximum {attainable} at {num_wells} wells / {num_rigs} "
                    "rigs, so the two tie-break tiers can trade off and stage 2 "
                    "imposes no order.",
                )
                self.assertEqual(w1, bound + 1)

    def test_the_bound_is_the_tight_one_not_num_pairs_squared(self):
        """*Validates: Requirement 3.6*

        ``num_pairs x num_pairs`` assumes every ``(well, rig)`` pair can be
        active at once.  Each well takes at most one rig, so the tight bound is
        ``num_wells x num_pairs`` — looser by a factor of ``num_rigs``.  Stage 2
        derives ``W1`` from the tight bound, which is what keeps the stage-2
        coefficients an order of magnitude smaller than they would otherwise be.
        """
        for num_wells, num_rigs in WEIGHT_SHAPES:
            with self.subTest(wells=num_wells, rigs=num_rigs):
                num_pairs = num_wells * num_rigs
                self.assertEqual(
                    max_rig_well_order(num_wells, num_rigs),
                    num_wells * num_pairs,
                    "The bound must be num_wells x num_pairs.",
                )
                if num_rigs > 1:
                    self.assertLess(
                        max_rig_well_order(num_wells, num_rigs),
                        num_pairs * num_pairs,
                        "The tight bound must be strictly below the loose one "
                        "whenever there is more than one rig.",
                    )

    def test_stage_two_objective_maximum_stays_inside_a_safe_int64_bound(self):
        """*Validates: Requirement 3.6*

        Stage 2's objective maximum is ``W1 x horizon x num_pairs`` plus the
        order term.  The design's worked example — ~30 wells / ~13 rigs, so
        ``W1 ~ 11 701`` and a maximum around ``1.8 x 10**9`` — is reproduced
        here, and every shape is checked against a ceiling that leaves CP-SAT
        room for the intermediate sums it forms.
        """
        for num_wells, num_rigs in WEIGHT_SHAPES:
            with self.subTest(wells=num_wells, rigs=num_rigs):
                w1, w2 = tiebreak_weights(num_wells, num_rigs)
                num_pairs = num_wells * num_rigs
                maximum = (
                    w1 * GENEROUS_HORIZON_DAYS * num_pairs
                    + w2 * max_rig_well_order(num_wells, num_rigs)
                )
                self.assertLess(
                    maximum,
                    SAFE_INT64_BOUND,
                    f"Stage-2 objective maximum {maximum:,} at {num_wells} "
                    f"wells / {num_rigs} rigs is too close to the int64 "
                    "ceiling.",
                )

        # The design's worked example, at a one-financial-year horizon.
        w1, _ = tiebreak_weights(30, 13)
        self.assertEqual(w1, 11_701)
        self.assertLess(w1 * 366 * (30 * 13), 2 * 10 ** 9)


class TwoStageBudgetSplitTests(SimpleTestCase):
    """The wall shares sum to exactly ``FACTOR x T``, from ``T`` alone."""

    def test_the_two_wall_shares_sum_to_exactly_the_configured_factor(self):
        """*Validates: Requirements 2.4, 3.9*

        Property 4 bounds the **total** wall time of the two-stage solve at
        ``WALL_BACKSTOP_FACTOR x T``.  The shares are 0.85 and 0.15 of that
        factor, so they must add back up to it exactly — not approximately.  A
        split that summed above the factor would let the two stages together
        exceed the ceiling the design states, silently.
        """
        config = determinism_settings()
        factor = float(config["WALL_BACKSTOP_FACTOR"])
        share = float(config["CANONICALIZE_BUDGET_SHARE"])

        for limit in TIME_LIMIT_DROPDOWN_SECONDS:
            with self.subTest(time_limit_seconds=limit):
                budgets = calibrate_two_stage_budgets(limit)
                stage_one = budgets.stage_one
                stage_two = budgets.stage_two
                assert stage_two is not None

                self.assertEqual(
                    stage_one.wall_backstop_seconds
                    + stage_two.wall_backstop_seconds,
                    factor * limit,
                    "The two wall shares must sum to exactly "
                    f"WALL_BACKSTOP_FACTOR x T = {factor} x {limit}.",
                )
                self.assertTrue(budgets.wall_backstops_sum_exactly)
                self.assertAlmostEqual(
                    stage_two.wall_backstop_seconds, share * factor * limit
                )
                self.assertAlmostEqual(
                    stage_one.wall_backstop_seconds,
                    (1.0 - share) * factor * limit,
                )
                self.assertEqual(stage_one.stage, STAGE_PRIMARY)
                self.assertEqual(stage_two.stage, STAGE_CANONICALIZE)

    def test_the_two_work_shares_sum_to_exactly_the_whole_budget(self):
        """*Validates: Requirement 2.4*

        ``D1 + D2 == D``.  Both stages stop on work, so their sum being exact is
        what makes the whole request's stopping behaviour a pure function of the
        request.
        """
        for limit in TIME_LIMIT_DROPDOWN_SECONDS:
            with self.subTest(time_limit_seconds=limit):
                budgets = calibrate_two_stage_budgets(limit)
                whole = calibrate_solver_budget(limit)
                stage_two = budgets.stage_two
                assert stage_two is not None
                assert budgets.stage_one.deterministic_budget is not None
                assert stage_two.deterministic_budget is not None

                self.assertEqual(
                    budgets.stage_one.deterministic_budget
                    + stage_two.deterministic_budget,
                    whole.deterministic_budget,
                )
                self.assertTrue(budgets.deterministic_budgets_sum_exactly)

    def test_the_split_cannot_see_a_clock(self):
        """*Validates: Requirement 2.2*

        The hard rule from design decision 1, asserted rather than trusted: no
        solver parameter may be derived from a measured wall time.  A "time
        remaining after stage 1" computation would feed this machine's elapsed
        time back into the parameter proto, which is exactly the defect being
        fixed — and under a same-machine scope it is the only channel left
        through which it could return.
        """
        parameters = list(
            inspect.signature(calibrate_two_stage_budgets).parameters
        )
        self.assertEqual(parameters, ["time_limit_seconds", "deterministic"])
        for forbidden in (
            "solver",
            "elapsed",
            "remaining",
            "wall_time",
            "started_at",
            "now",
        ):
            self.assertNotIn(forbidden, parameters)

        first = calibrate_two_stage_budgets(300)
        second = calibrate_two_stage_budgets(300)
        self.assertEqual(first, second)

    def test_performance_mode_has_no_second_stage(self):
        """*Validates: Requirement 3.12*

        Performance mode makes no determinism promise, so it is not split and
        not canonicalised: one stage, the pre-existing wall-clock limit, no work
        budget.
        """
        budgets = calibrate_two_stage_budgets(300, deterministic=False)
        self.assertIsNone(budgets.stage_two)
        self.assertEqual(
            budgets.stage_one, calibrate_solver_budget(300, deterministic=False)
        )
        self.assertTrue(budgets.wall_backstops_sum_exactly)


class _InfeasibleStageTwoScheduler(DrillingScheduler):
    """A scheduler whose stage 2 is forced ``INFEASIBLE``.

    The contradiction is injected at the ``_prepare_canonical_stage`` seam,
    *after* the real stage-2 preparation has run, so everything else about the
    stage — the ``P-expr == V*`` equality, the hints, the objective swap, the
    budget, the fingerprint — happens exactly as it does in production.  Only
    the outcome is forced.

    ``project_end`` is declared over ``[0, horizon]``, so pinning it above the
    horizon is an unsatisfiable constraint that presolve resolves immediately.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        #: Stage 1's captured values, recorded on the way past.
        self.observed_stage_one_values: Optional[Dict[int, int]] = None

    def _prepare_canonical_stage(
        self, stage_one_objective_value: int, stage_one_values: Dict[int, int]
    ) -> None:
        self.observed_stage_one_values = dict(stage_one_values)
        super()._prepare_canonical_stage(stage_one_objective_value, stage_one_values)
        assert self.model is not None
        assert self.project_end is not None
        self.model.Add(self.project_end == self.horizon + 1)


class StageTwoFailurePreservesStageOneTests(TestCase):
    """Stage 2 may improve the tie-break and nothing else."""

    def _expected_triples_from(
        self, scheduler: DrillingScheduler, values: Dict[int, int]
    ) -> List[Tuple[str, str, int, int]]:
        """``(rig, well, start_day, end_day)`` read out of a captured snapshot."""
        triples = []
        for (wid, rid), var in scheduler.assignments.items():
            if values[var.index] == 1:
                triples.append(
                    (
                        rid,
                        wid,
                        values[scheduler.start_times[(wid, rid)].index],
                        values[scheduler.end_times[(wid, rid)].index],
                    )
                )
        return sorted(triples)

    def _payload_triples(
        self, results: Dict[str, Any]
    ) -> List[Tuple[str, str, int, int]]:
        return sorted(
            (
                str(a["rig"]),
                str(a["well"]),
                int(a["well_start_day"]),
                int(a["well_end_day"]),
            )
            for a in results.get("assignments", [])
        )

    def test_infeasible_stage_two_returns_the_stage_one_schedule_intact(self):
        """*Validates: Requirements 3.6, 3.8*

        The failure path is the one that matters most: a stage-2 problem must
        never cost the caller a schedule stage 1 already found.  Asserted
        against stage 1's own captured variable values, not against a second
        solve, so the comparison is with the exact snapshot the fallback is
        supposed to return.
        """
        scenario = build_symmetric_tie_scenario(suffix="TIEINF")
        scheduler = _InfeasibleStageTwoScheduler(
            [dict(r) for r in scenario.rigs_data],
            [dict(w) for w in scenario.wells_data],
            **scenario.scheduler_kwargs(),
        )
        results = scheduler.solve(time_limit_seconds=TIE_TIME_LIMIT_SECONDS)

        self.assertEqual(
            results["canonicalization_status"],
            CANONICALIZATION_FAILED_INFEASIBLE,
            "A stage 2 that returns INFEASIBLE must be reported as such.",
        )
        self.assertIn(
            results["canonicalization_status"], CANONICALIZATION_STAGE_ONE_PRESERVED
        )
        assert scheduler.canonicalization is not None
        self.assertFalse(scheduler.canonicalization.adopted)
        self.assertIsNone(scheduler.canonicalization.values)

        self.assertTrue(results["is_feasible"])
        self.assertGreater(results["wells_assigned_count"], 0)

        values = scheduler.observed_stage_one_values
        self.assertIsNotNone(values, "stage 2 preparation never ran")
        assert values is not None
        self.assertEqual(
            self._payload_triples(results),
            self._expected_triples_from(scheduler, values),
            "The payload does not match stage 1's captured solution, so the "
            "stage-2 fallback lost or altered the schedule it was handed.",
        )

        assert scheduler.stage_one_metrics is not None
        self.assertEqual(
            results["objective_value"],
            scheduler.stage_one_metrics["objective_value"],
        )

    def test_performance_mode_skips_stage_two_and_says_so(self):
        """*Validates: Requirement 3.12*

        ``deterministic=False`` carries no determinism promise and its recorded
        parameter block is asserted unchanged by the preservation goldens, so
        stage 2 must not run on that path at all.
        """
        scenario = build_symmetric_tie_scenario(suffix="TIEPERF")
        observation = solve_once(
            scenario,
            time_limit_seconds=TIE_TIME_LIMIT_SECONDS,
            deterministic=False,
        )
        self.assertEqual(
            observation.results["canonicalization_status"],
            CANONICALIZATION_SKIPPED_PERFORMANCE_MODE,
        )
        self.assertTrue(observation.results["is_feasible"])
        self.assertGreater(observation.wells_assigned, 0)


class StageOneMetricProvenanceTests(TestCase):
    """Reported metrics describe stage 1; stage 2's objective never leaks."""

    def test_reported_metrics_come_from_stage_one(self):
        """*Validates: Requirements 3.8, 3.13*

        ``objective_value``, ``best_bound``, ``optimality_gap``,
        ``solver_status`` and ``is_optimal`` are stage 1's.  Stage 2 minimises
        ``W1 x start_time_sum + W2 x rig_well_order`` — a tie-break index with
        no business meaning — so if any of it reached the payload the schedule
        detail page would show nonsense.

        ``V*`` is recomputed here from an independent single-stage solve of the
        same model, so the assertion is that the payload carries *today's*
        objective value rather than merely agreeing with whatever the two-stage
        code captured.
        """
        scenario = build_symmetric_tie_scenario(suffix="TIEPROV")

        # Independent stage-1-only reference: build the model the same way
        # solve() does, minimise the published P-expr, take the optimum.
        reference_scheduler, primary_expr = build_model_with_objective(scenario)
        reference_model = reference_scheduler.model
        assert reference_model is not None
        reference_solver = cp_model.CpSolver()
        reference_solver.parameters.num_search_workers = 1
        reference_solver.parameters.random_seed = 42
        reference_solver.parameters.max_time_in_seconds = 60.0
        reference_status = reference_solver.Solve(reference_model)
        self.assertEqual(reference_status, cp_model.OPTIMAL)
        v_star = int(round(reference_solver.ObjectiveValue()))
        del primary_expr

        scheduler = new_scheduler(scenario)
        results = scheduler.solve(time_limit_seconds=TIE_TIME_LIMIT_SECONDS)

        assert scheduler.stage_one_metrics is not None
        stage_one = scheduler.stage_one_metrics
        self.assertEqual(results["objective_value"], stage_one["objective_value"])
        self.assertEqual(results["best_bound"], stage_one["best_bound"])
        self.assertEqual(results["optimality_gap"], stage_one["optimality_gap"])
        self.assertEqual(results["solver_status_code"], scheduler.status)
        self.assertEqual(
            results["is_optimal"], scheduler.status == cp_model.OPTIMAL
        )
        self.assertEqual(
            int(round(float(results["objective_value"]))),
            v_star,
            "The reported objective_value is not stage 1's optimum, so the "
            "two-stage solve moved the number the business reads.",
        )

        outcome = scheduler.canonicalization
        assert outcome is not None
        self.assertIn(
            outcome.status,
            (
                CANONICALIZATION_CANONICAL_OPTIMAL,
                CANONICALIZATION_CANONICAL_INCUMBENT,
                CANONICALIZATION_ALREADY_CANONICAL,
            ),
            f"Stage 2 did not run cleanly on the tie model: {outcome}",
        )
        for tiebreak in (outcome.tiebreak_before, outcome.tiebreak_after):
            if tiebreak is not None:
                self.assertNotEqual(
                    int(round(float(results["objective_value"]))),
                    int(tiebreak),
                    "The payload's objective_value equals a stage-2 tie-break "
                    "index, which means stage 2's objective leaked.",
                )

        leaked = [key for key in results if "tiebreak" in key.lower()]
        self.assertEqual(
            leaked,
            [],
            f"Stage 2's tie-break quantities reached the payload: {leaked}",
        )

    def test_both_stage_protos_are_fingerprinted(self):
        """*Validates: Requirement 2.11 (provenance), 3.8*

        Stage 2's proto is a deterministic function of stage 1's result, so the
        chain ``fp1 -> V* -> fp2`` is itself reproducible and worth recording.
        The two must differ: stage 2 adds the ``P-expr == V*`` equality and
        replaces the objective.
        """
        scenario = build_symmetric_tie_scenario(suffix="TIEFP")
        scheduler = new_scheduler(scenario)
        scheduler.solve(time_limit_seconds=TIE_TIME_LIMIT_SECONDS)

        self.assertIsNotNone(scheduler.model_fingerprint)
        self.assertIsNotNone(scheduler.model_fingerprint_stage_two)
        self.assertNotEqual(
            scheduler.model_fingerprint, scheduler.model_fingerprint_stage_two
        )


class BudgetMonotonicityTests(TestCase):
    """A larger selected limit never returns a worse objective."""

    def test_a_larger_time_limit_never_worsens_the_objective(self):
        """*Validates: Requirements 2.4, 3.9*

        The failure this catches is a stage-split or calibration mistake that
        starves stage 1 of search: if ``D1`` were cut too far, or if the split
        were applied twice, more selected time could buy a *worse* incumbent.
        The symmetric tie model closes to a proven optimum at every limit here,
        so the expected outcome is the same objective value throughout and any
        movement at all is a defect.
        """
        scenario = build_symmetric_tie_scenario(suffix="TIEMONO")
        observed = []
        for limit in (10, 20, 30):
            observation = solve_once(scenario, time_limit_seconds=limit)
            observed.append((limit, observation.objective_value))
            self.assertTrue(
                observation.results["is_feasible"],
                f"No solution at a {limit}s limit.",
            )

        print(
            "\n=== BUDGET MONOTONICITY ===\n"
            + "\n".join(f"limit {limit:>4}s -> objective {obj}" for limit, obj in observed)
        )
        for (small_limit, worse), (large_limit, better) in zip(observed, observed[1:]):
            assert worse is not None and better is not None
            self.assertLessEqual(
                float(better),
                float(worse),
                f"A {large_limit}s limit returned objective {better}, worse "
                f"than {worse} at {small_limit}s. More search must never buy a "
                "worse answer.",
            )


class ActualsGoThroughBothStagesTests(TestCase):
    """Stage 2 runs on the locked-actuals path and cannot move a pin."""

    def test_stage_two_does_not_move_a_pinned_actual(self):
        """*Validates: Requirements 3.10, 3.11*

        A pin is a hard constraint added to the model before either stage runs,
        and stage 2 solves that same model — it only adds the ``P-expr == V*``
        equality and swaps the objective.  So a pinned well is as fixed in
        stage 2 as it is in stage 1, and the canonicalisation cannot trade it
        for a prettier tie-break.
        """
        scenario = build_symmetric_tie_scenario(suffix="TIEACT")
        pinned_start = FY_START + timedelta(days=40)
        pinned_end = pinned_start + timedelta(days=29)  # duration 30, inclusive
        fixed_actuals = [
            {
                "well": "WELL-001",
                "rig": "RIG-02",
                "actual_start_date": pinned_start,
                "actual_end_date": pinned_end,
            }
        ]

        scheduler = new_scheduler(scenario)
        results = scheduler.solve_with_actuals(
            fixed_actuals, time_limit_seconds=TIE_TIME_LIMIT_SECONDS
        )

        self.assertTrue(results["is_feasible"])
        by_well = {str(a["well"]): a for a in results["assignments"]}
        self.assertIn("WELL-001", by_well)
        pinned = by_well["WELL-001"]
        self.assertEqual(pinned["rig"], "RIG-02")
        self.assertEqual(pinned["well_start_date"], pinned_start)
        self.assertEqual(pinned["well_end_date"], pinned_end)

        self.assertIsNotNone(results["canonicalization_status"])
        self.assertNotEqual(
            results["canonicalization_status"],
            CANONICALIZATION_SKIPPED_PERFORMANCE_MODE,
            "solve_with_actuals must be routed through both stages.",
        )
