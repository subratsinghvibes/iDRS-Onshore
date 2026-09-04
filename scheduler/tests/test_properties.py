"""Task 9.1 — property-based tests over *generated* inputs.

*Validates: Properties 1, 2, 3, 5 (requirements 2.1, 2.8, 2.10, 3.1, 3.2, 3.6,
3.7, 3.8)*

Every other test file in this package pins one hand-built scenario. This one
generates them, and that difference is the point: a fixed scenario can only show
that the fix works *there*, and the ordering hardening in task 5 in particular is
a claim about all inputs, not about one. ``hypothesis`` searches for the
counter-example instead of waiting for production to find it.

Four properties, in the order they matter:

1. **Determinism (Property 1).** Repeated solves of the same generated inputs
   return one ``schedule_hash``.
2. **Optimum stability (Property 2, general form).** Where a generated model
   proves ``OPTIMAL``, the objective equals its own bound and re-solving returns
   the identical schedule.
3. **Feasibility and economics (Property 3).** Every hard constraint in clause
   3.7 holds on whatever schedule comes back.
4. **Ordering invariance (Property 5).** Shuffling the input row order leaves
   ``model_fingerprint`` byte-identical. This is the strongest single test of
   task 5, because it asserts the invariant rather than checking each individual
   ``order_by`` call.

Honest limitation on Property 2
-------------------------------
The spec's wording is "fixed output equals unfixed output". That comparison is
**not** available here: the unfixed code no longer exists in the tree, and
running the current code twice would compare the fix to itself. The concrete
anchor for that claim is the task 2 golden fixture, captured from the unfixed
code at commit ``3561731c`` and still asserted byte-for-byte in
``test_preservation.py``. What is generalised here is the checkable half — that a
*proven* optimum is stable and self-consistent (``objective == best_bound``,
gap 0, and the same schedule on a re-solve). A proven optimum is unique in value
by definition, so an implementation that returned a different objective for the
same model would be caught.

Why the models are small and the example counts low
---------------------------------------------------
Each example builds a location, rigs, wells, ILM adjustment rules and the
``WellPairDistance`` cache, then runs a real CP-SAT solve — tens of database
writes plus a solve per example. Sizes are kept in the range that proves
``OPTIMAL`` in well under a second, because that is the ``¬isBugCondition``
regime the properties are stated over, and ``max_examples`` is tuned so the whole
file stays inside a few seconds rather than dominating the suite. The scenarios
that deliberately *do not* close (the bug's own regime) are covered by
``test_determinism.py``'s calibrated ``HARD_OPEN`` harness.

Run independently::

    python manage.py test scheduler.tests.test_properties --keepdb
"""

from __future__ import annotations

import random
from datetime import timedelta
from decimal import Decimal
from typing import Any, Dict, List

from hypothesis import HealthCheck, assume, given, settings, strategies as st
from hypothesis.extra.django import TestCase as HypothesisTestCase

from scheduler.optimization import DrillingScheduler

from .factories import build_open_scenario

#: Hypothesis profile shared by every test here. ``deadline=None`` because a
#: CP-SAT solve is not a bounded-latency operation and a per-example deadline
#: would flake under load — which is precisely the failure mode this whole spec
#: exists to remove. ``too_slow`` is suppressed for the same reason: the fixture
#: work per example is genuinely slow and is not a sign of a bad strategy.
SOLVE_SETTINGS = settings(
    max_examples=8,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)

#: Small enough to prove OPTIMAL quickly. Two rigs minimum, or "which rig"
#: becomes a non-choice and the compatibility constraints are never exercised.
SMALL_MODEL = st.builds(
    dict,
    num_rigs=st.integers(min_value=2, max_value=3),
    num_wells=st.integers(min_value=3, max_value=6),
    seed=st.integers(min_value=1, max_value=10_000),
    duration_choices=st.sampled_from([(20, 30), (15, 25, 35), (30, 40)]),
    norm_days_choices=st.sampled_from([(8,), (8, 10), (10, 12)]),
    per_unit_days=st.sampled_from([Decimal("0.50"), Decimal("1.00")]),
    stagger_windows=st.booleans(),
    spread_degrees=st.sampled_from([0.5, 1.5, 3.0]),
)

TIME_LIMIT = 10


class NonVacuityMixin:
    """Filter degenerate generated models without letting them hide a green test.

    ``build_open_scenario`` draws rig horsepower, depth rating, BOP stack and TDS
    availability from its own seeded generator, independently of the well
    requirements. For some seeds nothing is compatible with anything and the
    optimum is an empty schedule. That is a degenerate *model*, not a defect, and
    it has to be skipped — every per-assignment assertion would pass trivially
    over an empty list.

    Skipping alone is not safe, though: if every example were degenerate the test
    would be green while asserting nothing at all. So each example is counted,
    and ``tearDownClass`` fails if none of them turned out to be useful. The
    counters are class-level because hypothesis runs many examples inside one test
    method, and "did any example exercise the property?" is only answerable across
    all of them.
    """

    #: Overridden per subclass so the message names what "useful" meant.
    USEFUL_DESCRIPTION = "non-degenerate"

    _examples_seen = 0
    _useful_seen = 0

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._examples_seen = 0
        cls._useful_seen = 0

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        print(
            f"\n[properties] {cls.__name__}: {cls._useful_seen} of "
            f"{cls._examples_seen} generated examples were "
            f"{cls.USEFUL_DESCRIPTION}"
        )
        if cls._examples_seen and not cls._useful_seen:
            raise AssertionError(
                f"No generated example was {cls.USEFUL_DESCRIPTION}, so "
                f"{cls.__name__} asserted nothing. The SMALL_MODEL strategy has "
                "drifted out of the regime this property is stated over and must "
                "be resized."
            )

    def _record_example(self, useful: bool) -> None:
        type(self)._examples_seen += 1
        if useful:
            type(self)._useful_seen += 1


def _solve(scenario, *, time_limit: int = TIME_LIMIT) -> Dict[str, Any]:
    """One solve over copies of the scenario's inputs.

    Copies because ``preprocess_data`` rewrites date and duration columns in
    place, so a second solve over the same dicts would not be solving the same
    input.
    """
    scheduler = DrillingScheduler(
        [dict(r) for r in scenario.rigs_data],
        [dict(w) for w in scenario.wells_data],
        **scenario.scheduler_kwargs(),
    )
    return scheduler.solve(time_limit_seconds=time_limit, deterministic=True)


def _fingerprint_of(rigs_data, wells_data, scenario) -> str:
    """The stage-1 model fingerprint for a given input row order.

    Stops after model construction — no solve — because the property under test
    is about how the *model* is built from unordered input, and solving would
    only add time and noise.
    """
    scheduler = DrillingScheduler(
        [dict(r) for r in rigs_data],
        [dict(w) for w in wells_data],
        **scenario.scheduler_kwargs(),
    )
    scheduler.preprocess_data()
    scheduler.setup_variables()
    scheduler.add_constraints()
    scheduler.add_ilm_constraints()
    scheduler.set_objective()
    import hashlib

    assert scheduler.model is not None
    return hashlib.sha256(str(scheduler.model.Proto()).encode()).hexdigest()


class GeneratedDeterminismTests(NonVacuityMixin, HypothesisTestCase):
    """Property 1 — repeated solves of generated inputs agree."""

    USEFUL_DESCRIPTION = "able to assign at least one well"

    @SOLVE_SETTINGS
    @given(config=SMALL_MODEL)
    def test_repeat_solves_yield_one_schedule_hash(self, config):
        scenario = build_open_scenario(suffix="PROP", **config)

        first = _solve(scenario)

        # Two runs that both assigned nothing would agree trivially.
        self._record_example(first["wells_assigned_count"] > 0)
        assume(first["wells_assigned_count"] > 0)

        second = _solve(scenario)

        self.assertEqual(
            first["schedule_hash"],
            second["schedule_hash"],
            "Two solves of identical generated inputs returned different "
            f"schedules. config={config}",
        )
        self.assertEqual(
            first["model_fingerprint"],
            second["model_fingerprint"],
            "The model proto itself differed between runs, so this is a "
            f"model-construction defect rather than a search one. config={config}",
        )
        self.assertEqual(first["objective_value"], second["objective_value"])
        self.assertEqual(
            first["wells_assigned_count"], second["wells_assigned_count"]
        )


class GeneratedOptimumStabilityTests(NonVacuityMixin, HypothesisTestCase):
    """Property 2 (general form) — a proven optimum is stable."""

    USEFUL_DESCRIPTION = "proven OPTIMAL with at least one well assigned"

    @SOLVE_SETTINGS
    @given(config=SMALL_MODEL)
    def test_a_proven_optimum_is_self_consistent_and_repeatable(self, config):
        scenario = build_open_scenario(suffix="PROPOPT", **config)
        first = _solve(scenario)

        # A model that does not close is not the regime this property is stated
        # over, and an empty optimum proves nothing. Both are legitimate outputs
        # of the generator; test_determinism.py covers the non-closing regime
        # deliberately.
        useful = first["is_optimal"] and first["wells_assigned_count"] > 0
        self._record_example(useful)
        assume(useful)

        self.assertEqual(
            first["optimality_gap"],
            0,
            "A run reporting is_optimal must report a zero gap. config="
            f"{config}",
        )
        self.assertAlmostEqual(
            float(first["objective_value"]),
            float(first["best_bound"]),
            places=4,
            msg="A proven optimum must equal its own bound; a gap between them "
            f"means 'optimal' is being reported for a solve that is not. config={config}",
        )

        second = _solve(scenario)
        self.assertEqual(
            first["schedule_hash"],
            second["schedule_hash"],
            f"A proven optimum was not reproduced on re-solve. config={config}",
        )
        self.assertEqual(
            first["objective_value"],
            second["objective_value"],
            "A proven optimum is unique in value by definition, so a different "
            f"objective on re-solve is a real defect. config={config}",
        )


class GeneratedFeasibilityAndEconomicsTests(NonVacuityMixin, HypothesisTestCase):
    """Property 3 — clause 3.7's hard constraints hold on generated inputs."""

    USEFUL_DESCRIPTION = "able to assign at least one well"

    @SOLVE_SETTINGS
    @given(config=SMALL_MODEL)
    def test_every_hard_constraint_holds(self, config):
        scenario = build_open_scenario(suffix="PROPFEAS", **config)
        results = _solve(scenario)

        assignments: List[Dict[str, Any]] = results["assignments"]
        # Every per-assignment loop below would pass trivially on an empty list.
        self._record_example(len(assignments) > 0)
        assume(len(assignments) > 0)

        rigs_by_name = {r.name: r for r in scenario.rigs}
        wells_by_name = {w.name: w for w in scenario.wells}
        base = min(r.start_date for r in scenario.rigs)

        # --- one rig per well -------------------------------------------------
        assigned_wells = [a["well"] for a in assignments]
        self.assertEqual(
            len(assigned_wells),
            len(set(assigned_wells)),
            f"A well was assigned to more than one rig. config={config}",
        )

        # --- per-rig non-overlap ---------------------------------------------
        by_rig: Dict[str, List[Dict[str, Any]]] = {}
        for a in assignments:
            by_rig.setdefault(a["rig"], []).append(a)
        for rig_name, rig_assignments in by_rig.items():
            ordered = sorted(rig_assignments, key=lambda x: x["well_start_day"])
            for earlier, later in zip(ordered, ordered[1:]):
                self.assertLessEqual(
                    earlier["well_end_day"],
                    later["well_start_day"],
                    f"Rig {rig_name} has overlapping wells "
                    f"({earlier['well']} ends {earlier['well_end_day']}, "
                    f"{later['well']} starts {later['well_start_day']}). "
                    f"config={config}",
                )

        for a in assignments:
            rig = rigs_by_name[a["rig"]]
            well = wells_by_name[a["well"]]
            context = f"{a['well']} on {a['rig']}, config={config}"

            # --- rig availability window ----------------------------------
            start_date = base + timedelta(days=a["well_start_day"])
            end_date = base + timedelta(days=a["well_end_day"])
            self.assertGreaterEqual(
                start_date,
                rig.start_date,
                f"Well starts before the rig is available: {context}",
            )
            self.assertLessEqual(
                end_date,
                rig.end_date,
                f"Well ends after the rig's window closes: {context}",
            )

            # --- well RTD (ready-to-drill) --------------------------------
            self.assertGreaterEqual(
                start_date,
                well.rtd,
                f"Well starts before its RTD: {context}",
            )

            # --- FY start bound -------------------------------------------
            if scenario.fy_start_date is not None:
                self.assertGreaterEqual(
                    start_date,
                    scenario.fy_start_date,
                    f"Well starts before the financial year opens: {context}",
                )

            # --- compatibility: HP, depth, BOP, TDS -----------------------
            self.assertGreaterEqual(
                rig.rig_capacity_hp,
                well.rig_capacity_required_hp,
                f"Rig horsepower is below the well's requirement: {context}",
            )
            self.assertGreaterEqual(
                rig.drilling_capacity_m,
                well.depth,
                f"Rig depth rating is below the well's depth: {context}",
            )
            self.assertGreaterEqual(
                rig.bop_stack,
                well.bop_stack,
                f"Rig BOP stack is below the well's requirement: {context}",
            )
            if str(well.tds_requirement).upper() == "Y":
                self.assertEqual(
                    str(rig.tds_availability).upper(),
                    "Y",
                    f"A TDS-requiring well was put on a rig without TDS: {context}",
                )

            # --- duration honoured ----------------------------------------
            self.assertEqual(
                a["well_end_day"] - a["well_start_day"],
                well.duration,
                f"Scheduled span does not equal the well's duration: {context}",
            )

        # --- economics ---------------------------------------------------
        self.assertGreaterEqual(results["total_cost"], 0)
        self.assertEqual(
            results["wells_assigned_count"],
            len(assignments),
            f"wells_assigned_count disagrees with the assignment list. config={config}",
        )
        self.assertEqual(
            results["wells_assigned_count"] + results["wells_unassigned_count"],
            results["wells_total_count"],
            f"Assigned + unassigned must account for every well. config={config}",
        )


class GeneratedOrderingInvarianceTests(NonVacuityMixin, HypothesisTestCase):
    """Property 5 — input row order does not reach the model.

    The strongest test of task 5. Each individual ``order_by`` could be checked
    separately; this asserts the invariant those calls exist to produce, so a
    future query that forgets one is caught here even though no test names it.
    """

    USEFUL_DESCRIPTION = "usable for an order-invariance comparison"

    @settings(
        max_examples=10,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
    )
    @given(config=SMALL_MODEL, shuffle_seed=st.integers(min_value=1, max_value=10_000))
    def test_shuffling_input_rows_leaves_the_model_fingerprint_unchanged(
        self, config, shuffle_seed
    ):
        scenario = build_open_scenario(suffix="PROPORD", **config)

        # Always meaningful: a model proto exists whether or not any well turns
        # out to be assignable, and the property is about how it is built.
        self._record_example(True)

        canonical = _fingerprint_of(
            scenario.rigs_data, scenario.wells_data, scenario
        )

        rng = random.Random(shuffle_seed)
        shuffled_rigs = list(scenario.rigs_data)
        shuffled_wells = list(scenario.wells_data)
        rng.shuffle(shuffled_rigs)
        rng.shuffle(shuffled_wells)

        shuffled = _fingerprint_of(shuffled_rigs, shuffled_wells, scenario)

        self.assertEqual(
            canonical,
            shuffled,
            "Shuffling the input row order changed the model proto, so the "
            "sort in preprocess_data is not making the model order-independent. "
            f"config={config}, shuffle_seed={shuffle_seed}",
        )

    @settings(
        max_examples=6,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
    )
    @given(config=SMALL_MODEL, shuffle_seed=st.integers(min_value=1, max_value=10_000))
    def test_shuffled_input_produces_the_same_schedule(self, config, shuffle_seed):
        """The end-to-end version: same schedule, not merely the same model.

        Kept separate from the fingerprint test because it costs two solves per
        example rather than two model builds, so it runs at a lower example
        count. Both are worth having: an identical fingerprint proves the model
        is order-independent, and this proves nothing downstream of the model
        reintroduces an order dependency.
        """
        scenario = build_open_scenario(suffix="PROPORD2", **config)

        baseline = _solve(scenario)
        self._record_example(baseline["wells_assigned_count"] > 0)
        assume(baseline["wells_assigned_count"] > 0)

        rng = random.Random(shuffle_seed)
        shuffled_rigs = [dict(r) for r in scenario.rigs_data]
        shuffled_wells = [dict(w) for w in scenario.wells_data]
        rng.shuffle(shuffled_rigs)
        rng.shuffle(shuffled_wells)

        scheduler = DrillingScheduler(
            shuffled_rigs, shuffled_wells, **scenario.scheduler_kwargs()
        )
        shuffled = scheduler.solve(
            time_limit_seconds=TIME_LIMIT, deterministic=True
        )

        self.assertEqual(
            baseline["schedule_hash"],
            shuffled["schedule_hash"],
            "Shuffling the input row order changed the resulting schedule. "
            f"config={config}, shuffle_seed={shuffle_seed}",
        )
        self.assertEqual(
            baseline["objective_value"],
            shuffled["objective_value"],
            f"Shuffled input changed the objective. config={config}",
        )
