"""Task 7 — the canonical decision strategy, and the FIXED_SEARCH knob.

*Validates: Requirements 2.7, 3.9, 3.12*

What task 7 adds is a **first-branch preference**, not a correctness mechanism.
After tasks 3-5 the schedule was already reproducible run to run; what was still
arbitrary was *which* incumbent a solve that runs out of budget happens to be
holding.  ``_add_decision_strategy`` biases that first descent towards
"assigned, and as early as possible".

Three properties are asserted here, and the distinction between them matters:

1. **Exactly two strategies, in canonical (well, rig) order.**  Not "some
   strategies" — two, the assignment ``BoolVar``s then the start-time
   ``IntVar``s, each listing its variables in the order
   ``preprocess_data``'s sort and ``setup_variables``' loop nesting produce.
   The order is read back out of the *model proto*, resolved through
   ``proto.variables[i].name``, so what is checked is what CP-SAT will actually
   see rather than what the Python dict happened to contain.
2. **It stays a hint.**  ``search_branching`` remains ``AUTOMATIC_SEARCH``
   unless ``FIXED_SEARCH`` is switched on.  This is the guard against the
   strategy quietly becoming a mandate, which is the configuration that was
   removed once already for costing too much solution quality.
3. **Performance mode is untouched.**  Clause 3.12 promises that block does not
   move, and its preservation golden carries no exemption, so the deterministic
   path adding strategies must not leak into it.

Why ``exprs`` and not ``variables``
-----------------------------------
``DecisionStrategyProto`` in the pinned ortools 9.15.6755 carries its variables
in the ``exprs`` field (each a linear expression over one variable with
coefficient 1); the older ``variables`` field is left empty.  These tests read
``exprs`` for that reason.  If an OR-Tools upgrade moves them back, the
precondition test below fails loudly rather than silently asserting over an
empty list.

Run independently::

    python manage.py test scheduler.tests.test_decision_strategy --keepdb
"""

from __future__ import annotations

from typing import List

from django.test import TestCase, override_settings
from ortools.sat.python import cp_model

from scheduler.optimization import determinism_settings
from .factories import build_symmetric_tie_scenario
from .support import new_scheduler


def _built_scheduler(scenario, *, deterministic: bool = True):
    """A scheduler taken up to the point the decision strategy is added.

    Mirrors ``solve()``'s own order — ``preprocess_data``, ``setup_variables``,
    constraints, objective, *then* the strategy — because the strategy's
    canonical order is inherited from that sequence rather than established by
    it.  Calling ``_add_decision_strategy`` on a half-built model would test
    nothing.
    """
    scheduler = new_scheduler(scenario)
    scheduler.preprocess_data()
    scheduler.setup_variables()
    scheduler.add_constraints()
    scheduler.add_ilm_constraints()
    scheduler.set_objective()
    scheduler._add_decision_strategy(deterministic=deterministic)
    return scheduler


def _strategy_variable_names(scheduler, index: int) -> List[str]:
    """The variable names strategy ``index`` branches on, in proto order."""
    proto = scheduler.model.Proto()
    names = [v.name for v in proto.variables]
    strategy = proto.search_strategy[index]
    resolved = []
    for expr in strategy.exprs:
        assert len(expr.vars) == 1, (
            "A decision-strategy expression covers more than one variable; "
            "this helper's name resolution assumes one variable per expression."
        )
        resolved.append(names[expr.vars[0]])
    return resolved


class DecisionStrategyStructureTests(TestCase):
    """The two strategies, their order, and their selection enums."""

    @classmethod
    def setUpTestData(cls):
        cls.scenario = build_symmetric_tie_scenario(suffix="DS")

    def test_exprs_field_is_where_the_variables_live(self):
        """Precondition: the assertions below read a populated field.

        If OR-Tools moves the variables back to the legacy ``variables`` field,
        every order assertion in this file would pass vacuously over an empty
        ``exprs`` list.  Fail here instead.
        """
        scheduler = _built_scheduler(self.scenario)
        strategy = scheduler.model.Proto().search_strategy[0]
        self.assertGreater(
            len(strategy.exprs),
            0,
            "DecisionStrategyProto.exprs is empty, so the order assertions in "
            "this file would be vacuous. Check whether the pinned ortools "
            "version moved the variables to the legacy 'variables' field.",
        )

    def test_exactly_two_strategies_are_added(self):
        scheduler = _built_scheduler(self.scenario)
        self.assertEqual(
            len(scheduler.model.Proto().search_strategy),
            2,
            "Task 7.1 specifies exactly two strategies: the assignment "
            "BoolVars, then the start-time IntVars. A third means something "
            "added a strategy that is not in the spec; one means a strategy "
            "was dropped.",
        )

    def test_first_strategy_is_the_assignment_bools_choose_first_select_max(self):
        """Try assigning a well before dropping it."""
        scheduler = _built_scheduler(self.scenario)
        strategy = scheduler.model.Proto().search_strategy[0]

        self.assertEqual(strategy.variable_selection_strategy, cp_model.CHOOSE_FIRST)
        self.assertEqual(strategy.domain_reduction_strategy, cp_model.SELECT_MAX_VALUE)

        names = _strategy_variable_names(scheduler, 0)
        self.assertTrue(
            all(n.startswith("assign_") for n in names),
            f"Strategy 0 must cover only assignment BoolVars; got {names[:5]}.",
        )
        self.assertEqual(
            len(names),
            len(scheduler.assignments),
            "Strategy 0 must cover every assignment variable.",
        )

    def test_second_strategy_is_the_start_times_choose_first_select_min(self):
        """Try the earlier start before the later one."""
        scheduler = _built_scheduler(self.scenario)
        strategy = scheduler.model.Proto().search_strategy[1]

        self.assertEqual(strategy.variable_selection_strategy, cp_model.CHOOSE_FIRST)
        self.assertEqual(strategy.domain_reduction_strategy, cp_model.SELECT_MIN_VALUE)

        names = _strategy_variable_names(scheduler, 1)
        self.assertTrue(
            all(n.startswith("start_") for n in names),
            f"Strategy 1 must cover only start-time IntVars; got {names[:5]}.",
        )
        self.assertEqual(
            len(names),
            len(scheduler.start_times),
            "Strategy 1 must cover every start-time variable.",
        )

    def test_both_strategies_are_in_canonical_well_then_rig_order(self):
        """The order is (well, rig), sorted, wells outer and rigs inner.

        Asserted against the *sorted* frames rather than against the dicts, so
        this fails if either the frame sort or the loop nesting regresses.  A
        comparison against ``self.assignments.keys()`` would agree with a
        scrambled order as long as both were scrambled the same way.
        """
        scheduler = _built_scheduler(self.scenario)
        well_names = list(scheduler.wells_df["name"])
        rig_names = list(scheduler.rigs_df["name"])

        self.assertEqual(
            well_names,
            sorted(well_names),
            "PRECONDITION: preprocess_data must leave wells_df sorted by name.",
        )
        self.assertEqual(
            rig_names,
            sorted(rig_names),
            "PRECONDITION: preprocess_data must leave rigs_df sorted by name.",
        )

        expected_assign = [
            f"assign_{w}_{r}" for w in well_names for r in rig_names
        ]
        expected_start = [f"start_{w}_{r}" for w in well_names for r in rig_names]

        self.assertEqual(
            _strategy_variable_names(scheduler, 0),
            expected_assign,
            "Strategy 0 is not in canonical (well, rig) order. Wells must be "
            "the outer loop and rigs the inner one, both name-sorted.",
        )
        self.assertEqual(
            _strategy_variable_names(scheduler, 1),
            expected_start,
            "Strategy 1 is not in canonical (well, rig) order.",
        )

    def test_performance_mode_adds_no_strategy(self):
        """Clause 3.12: the performance block does not move."""
        scheduler = _built_scheduler(self.scenario, deterministic=False)
        self.assertEqual(
            len(scheduler.model.Proto().search_strategy),
            0,
            "Performance mode must keep its pre-fix model proto. Its "
            "preservation golden compares model_fingerprint with no exemption, "
            "so a strategy here breaks clause 3.12.",
        )


class SearchBranchingRemainsAutomaticTests(TestCase):
    """The strategy is advisory unless FIXED_SEARCH is explicitly enabled."""

    @classmethod
    def setUpTestData(cls):
        cls.scenario = build_symmetric_tie_scenario(suffix="DSB")

    def _configured_branching(self):
        scheduler = new_scheduler(self.scenario)
        scheduler.preprocess_data()
        scheduler.setup_variables()
        scheduler._configure_solver_for_determinism(10, deterministic=True)
        return scheduler.solver.parameters.search_branching

    def test_fixed_search_is_off_by_default(self):
        self.assertFalse(
            determinism_settings()["FIXED_SEARCH"],
            "FIXED_SEARCH must ship off. On, it costs a great deal of solution "
            "quality on large models.",
        )

    def test_default_branching_is_automatic_search(self):
        self.assertEqual(
            self._configured_branching(),
            cp_model.AUTOMATIC_SEARCH,
            "The decision strategy must stay a hint. Under AUTOMATIC_SEARCH "
            "CP-SAT consults it for the first descent and then branches "
            "freely; that is what keeps its cost near zero.",
        )

    @override_settings(
        IDRS_SOLVER_DETERMINISM={
            **{
                "DETERMINISTIC_TIME_RATIO": 0.60,
                "WALL_BACKSTOP_FACTOR": 1.5,
                "CANONICALIZE_BUDGET_SHARE": 0.15,
            },
            "FIXED_SEARCH": True,
        }
    )
    def test_the_knob_works_when_switched_on(self):
        """Off-by-default is a choice, not a missing implementation."""
        self.assertEqual(
            self._configured_branching(),
            cp_model.FIXED_SEARCH,
            "IDRS_FIXED_SEARCH=True must actually reach the parameter proto, "
            "otherwise the audit-run mode advertised in settings.py does not "
            "exist.",
        )

    def test_presolve_stays_on_in_both_branching_modes(self):
        """Task 7.3: the strategy must not cost us presolve.

        Presolve remaps and can remove variables, so it is the one parameter
        that could plausibly have been traded away to make a decision strategy
        apply cleanly. It was not.
        """
        scheduler = new_scheduler(self.scenario)
        scheduler.preprocess_data()
        scheduler.setup_variables()
        for deterministic in (True, False):
            scheduler._configure_solver_for_determinism(
                10, deterministic=deterministic
            )
            self.assertTrue(
                scheduler.solver.parameters.cp_model_presolve,
                f"cp_model_presolve must stay True (deterministic="
                f"{deterministic}).",
            )


class StageTwoInheritsTheStrategyTests(TestCase):
    """Stage 2 solves the same model, so it inherits the same two strategies."""

    @classmethod
    def setUpTestData(cls):
        cls.scenario = build_symmetric_tie_scenario(suffix="DS2")

    def test_a_full_solve_leaves_exactly_two_strategies_on_the_model(self):
        """Not four.

        ``_canonicalize_stage_one_solution`` reuses ``self.model``: it adds the
        ``P-expr == V*`` equality and swaps the objective, but never rebuilds.
        Search strategies live on the model proto, so stage 2 gets them for
        free — and a second ``_add_decision_strategy`` call for stage 2 would
        *append* duplicates rather than replace them.  Two after a complete
        two-stage solve is the evidence that inheritance is what happens.
        """
        scheduler = new_scheduler(self.scenario)
        scheduler.solve(time_limit_seconds=10)

        self.assertEqual(
            len(scheduler.model.Proto().search_strategy),
            2,
            "A finished two-stage solve must leave exactly two strategies on "
            "the model. Four means stage 2 re-added them instead of "
            "inheriting them.",
        )
        self.assertIsNotNone(
            scheduler.model_fingerprint_stage_two,
            "PRECONDITION: stage 2 must actually have run, or this test "
            "measures nothing about inheritance.",
        )
