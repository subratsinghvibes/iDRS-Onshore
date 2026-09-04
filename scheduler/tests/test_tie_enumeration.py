"""How many distinct schedules attain the optimal objective value?

**Property 1: Bug Condition — the tie half.**

*Validates: Requirements 2.5, 2.5.1, 2.5.2, 2.12*

``bugfix.md`` clause 1.4: ``START_TIME_WEIGHT`` and ``RIG_WELL_ORDER_WEIGHT``
are both ``1`` (``scheduler/optimization.py:1358-1359``), so the two tie-break
tiers are commensurate and trade off against each other instead of forming a
strict order.  When several schedules share the optimal objective value the
solver is free to return any of them.

This test measures the size of that tied set, and of the *canonical* set stage 2
narrows it to, on the 5-well / 2-identical-rig model the requirements name.

What is asserted, and why it is a measurement rather than a "1"
--------------------------------------------------------------
This test originally asserted the canonical count was exactly **1**.  It is
not, and the reason is structural rather than a bug.  Measured after task 4's
two-stage solve landed:

===========================================  =======  ====================
enumerated at                                count    value
===========================================  =======  ====================
``P-expr == V*`` (the tied set)              **4**    ``V* = 218,583,260``
``P-expr == V*`` AND ``T-expr == T*``        **4**    ``T* = 8,182``
===========================================  =======  ====================

Both enumerations **exhausted** — they terminated ``INFEASIBLE`` with the
50-schedule cap not reached — so 4 is exact, not a lower bound.

The tie-break hierarchy is real: ``W1 = 51 > max(rig_well_order) = 50``, and
this test asserts that directly so a passing count can never be an artefact of
a collapsed hierarchy.  It simply has nothing to bite on.  All four survivors
carry *identical* tie-break components — ``start_time_sum = 160`` and
``rig_well_order = 22`` — because **both tiers are sums**, every well in this
scenario has duration 30 and both rigs are identical, so the four schedules
differ only by permuting interchangeable wells, which leaves a sum invariant.
Swapping W3@0 with W5@80 on one rig leaves ``0 + 80`` unchanged; swapping two
wells between the two identical rigs leaves
``sum(well_index * num_rigs + rig_index)`` unchanged.  No linear objective built
from those two sums can separate them.  That is design root cause 4 reproduced
exactly, with numbers.

**Decision taken (user, Option B): accept the residual and de-scope canonical
path-independence.**  The requirement is same rigs, wells, financial year and
time limit, same machine, same schedule every run — met and measured by task 3's
reproducible stop plus ``test_determinism``'s repeat-run harness (one hash, zero
``deterministic_time`` spread, idle and under representative load).  Separating
four interchangeable permutations would buy path-independence of the *choice*,
not reproducibility, and is not worth the model complexity.  See amended
``bugfix.md`` clauses 2.5, 2.5.1-2.5.3 and design.md *Clause 2.5 — resolved,
reworded, and the residual measured*.

So the canonical count is **pinned** to its measured value in
``MEASURED_CANONICAL_SCHEDULE_COUNT`` and asserted for equality:

* a count **above** the constant is a **regression** — something grew the
  residual, and the equality assertion catches it;
* a count **below** the constant means canonicalisation **improved**.  That is
  good news, but it is still a failure here, deliberately: the constant is a
  measurement of the model and must be revisited on purpose, with the new number
  recorded, rather than silently satisfied by a ``<=``.

Nothing else was relaxed.  The hierarchy assertion, the exhaustiveness
assertions and the "tied set is still > 1" assertion are all still here, and a
cap hit is still a failure — a capped count is only a lower bound, which would
make the equality assertion meaningless.

If a future, non-symmetric model shows a canonical count above its pinned value
that interchangeable permutations do **not** explain, the escalation is the third
tie-break tier from design decision 3 — an arc-order index over ``circuit_arcs``,
which is order-sensitive rather than a sum and so *can* separate permutations.
That tier is the designated escalation and is explicitly out of scope now
(clause 2.5.3); it is not a reason to move this constant.

Method: exhaustive no-good enumeration, not ``enumerate_all_solutions``
----------------------------------------------------------------------
The obvious approach — pin the objective, set
``enumerate_all_solutions = True`` and count distinct ``schedule_hash`` values
from a solution callback — was tried first and does not measure the right
quantity.  ``start_time_sum`` in the objective
(``scheduler/optimization.py:1394``) sums the start-time variables of **every**
``(well, rig)`` pair, including pairs the solution does not select.  Those
variables are otherwise unconstrained, so a single schedule corresponds to a
combinatorial number of full variable assignments.  Measured on this model, the
callback hit a 50-solution cap having seen only 3 distinct schedules — it spent
the budget enumerating irrelevant permutations of unused variables.

The enumeration below instead solves repeatedly and, after each solution, adds
a no-good clause forbidding that *schedule*: the exact assignment pattern plus
the start day of each selected pair.  Unused variables are not part of the
clause, so each iteration returns a genuinely new schedule and the loop
terminates ``INFEASIBLE`` once the tied set is exhausted.  That gives an exact
count rather than a lower bound, and it leaves the model's optimum untouched.

The loop is capped so a regression fails fast instead of hanging.
"""

from __future__ import annotations

from typing import Any, List, Tuple

from django.test import TestCase
from ortools.sat.python import cp_model

from scheduler.optimization import max_rig_well_order, tiebreak_weights

from .factories import build_symmetric_tie_scenario
from .support import (
    build_model_with_objective,
    schedule_hash_of,
    tiebreak_objective_of,
)

#: Hard cap on the enumeration.  Exceeding it is a failure, not a truncation:
#: if a model ever has more than this many tied optima the harness should say so
#: loudly rather than sit there.
ENUMERATION_CAP = 50

#: The **measured** number of distinct schedules at ``(P-expr == V*) AND
#: (T-expr == T*)`` on ``build_symmetric_tie_scenario``'s 5-well /
#: 2-identical-rig model, with both enumerations exhausted.
#:
#: This is not a tolerance and not a weakened target.  It is the size of the
#: interchangeable-permutation residual that amended ``bugfix.md`` clause 2.5.2
#: accepts and requires to be *measured, not eliminated*.  Both tie-break tiers
#: are **sums**; every well in this scenario has duration 30 and both rigs are
#: identical; so the surviving schedules differ only by permuting interchangeable
#: wells, and a permutation leaves a sum invariant.  All four carry the same
#: ``start_time_sum = 160`` and the same ``rig_well_order = 22``, at
#: ``V* = 218,583,260`` and ``T* = 8,182``.  The hierarchy is real and is
#: asserted below (``W1 = 51 > max(rig_well_order) = 50``) — it has nothing to
#: bite on, which is the point.
#:
#: Asserted for **equality**.  Above this value is a regression.  Below it means
#: canonicalisation improved and this constant must be revisited deliberately,
#: with the new measurement recorded here and in the spec — not satisfied
#: silently by a looser comparison.
MEASURED_CANONICAL_SCHEDULE_COUNT = 4


def _selected_triples(scheduler, reader) -> List[Tuple[str, str, int, int]]:
    """``(rig, well, start_day, end_day)`` for the selected assignments."""
    triples = []
    for (wid, rid), var in scheduler.assignments.items():
        if reader.Value(var) == 1:
            triples.append(
                (
                    rid,
                    wid,
                    int(reader.Value(scheduler.start_times[(wid, rid)])),
                    int(reader.Value(scheduler.end_times[(wid, rid)])),
                )
            )
    return triples


def _forbid_schedule(scheduler, reader, iteration: int) -> None:
    """Add a no-good clause excluding exactly the schedule just found.

    A schedule is "which rig each well went to, and when it started".  The
    clause is built from one literal per ``(well, rig)`` pair — the assignment
    variable itself, plus a reified ``start == s`` literal for selected pairs —
    and then negated as a whole.  Start times of *unselected* pairs are
    deliberately excluded, which is what keeps the enumeration counting
    schedules rather than variable assignments.
    """
    model = scheduler.model
    literals = []
    for (wid, rid), var in scheduler.assignments.items():
        if reader.Value(var) == 1:
            literals.append(var)
            start_var = scheduler.start_times[(wid, rid)]
            start_value = int(reader.Value(start_var))
            same_start = model.NewBoolVar(f"nogood{iteration}_start_{wid}_{rid}")
            model.Add(start_var == start_value).OnlyEnforceIf(same_start)
            model.Add(start_var != start_value).OnlyEnforceIf(same_start.Not())
            literals.append(same_start)
        else:
            literals.append(var.Not())
    model.AddBoolOr([lit.Not() for lit in literals])


def _solve_to_optimality(model):
    """Solve ``model`` single-threaded with a fixed seed, requiring a solution."""
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 42
    solver.parameters.max_time_in_seconds = 60.0
    return solver, solver.Solve(model)


def _enumerate_distinct_schedules(scheduler) -> Tuple[List[str], bool]:
    """Exhaustively count the distinct schedules ``scheduler.model`` admits.

    Returns ``(sorted distinct schedule hashes, exhausted)``.  ``exhausted`` is
    False when the loop hit ``ENUMERATION_CAP``, in which case the count is only
    a lower bound and the caller must fail rather than report it as exact.

    Mutates the model by adding one no-good clause per schedule found, so each
    call needs its own freshly-built model.
    """
    hashes: List[str] = []
    hit_cap = True
    for iteration in range(ENUMERATION_CAP):
        enumerator, status = _solve_to_optimality(scheduler.model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            hit_cap = False
            break
        hashes.append(schedule_hash_of(_selected_triples(scheduler, enumerator)))
        _forbid_schedule(scheduler, enumerator, iteration)
    return sorted(set(hashes)), not hit_cap


class TieEnumerationTests(TestCase):
    """Count the schedules that tie at the optimal objective value."""

    def test_the_canonical_set_matches_its_measured_size(self):
        """*Validates: Requirements 2.5, 2.5.1, 2.5.2, 2.12*

        Asserts, in order: the tie-break hierarchy is real on this model; both
        enumerations were exhaustive; the tied set at ``V*`` alone is still
        > 1 (so the test documents what stage 2 chooses within); and the
        canonical set at ``(V*, T*)`` is exactly
        ``MEASURED_CANONICAL_SCHEDULE_COUNT``.
        """
        scenario = build_symmetric_tie_scenario()

        # --- stage 1: find the optimal objective value V* --------------------
        stage_one, primary_expr = build_model_with_objective(scenario)
        assert stage_one.model is not None
        solver, status = _solve_to_optimality(stage_one.model)
        self.assertEqual(
            status,
            cp_model.OPTIMAL,
            "The tie model must close to proven OPTIMAL for the tied set to be "
            f"well defined; got {solver.StatusName(status)}.",
        )
        v_star = int(round(solver.ObjectiveValue()))

        # --- the tie-break hierarchy must be real on this model --------------
        # Read through the production helpers, not reconstructed here, so this
        # checks the weights stage 2 actually uses.  Without this assertion a
        # passing canonical count could be an artefact of a collapsed hierarchy
        # rather than evidence the hierarchy did its job (amended clause 2.5.2).
        num_wells = len(stage_one.wells_df)
        num_rigs = len(stage_one.rigs_df)
        w1, w2 = tiebreak_weights(num_wells, num_rigs)
        order_bound = max_rig_well_order(num_wells, num_rigs)
        self.assertGreater(
            w1,
            order_bound,
            f"The stage-2 tie-break tiers do not form a hierarchy on this model: "
            f"W1={w1} must strictly exceed max(rig_well_order)={order_bound} or "
            "start_time_sum and rig_well_order are commensurate and trade off "
            "(bugfix.md clause 1.4). Any canonical count measured under a "
            "collapsed hierarchy is meaningless.",
        )
        self.assertEqual(
            w2, 1, f"W2 must stay at 1 as the finest tier; got {w2}."
        )

        # --- the tied set: every schedule attaining V* -----------------------
        # Reported, and asserted only to stay > 1: stage 1's objective is
        # unchanged, so the tie is still there.  What stage 2 changes is which
        # subset of it the solver may return.
        stage_one.model.Add(primary_expr == v_star)
        tied_at_v, tied_exhausted = _enumerate_distinct_schedules(stage_one)

        # --- stage 2: minimise T-expr subject to P-expr == V*, giving T* -----
        # A freshly built model, because the enumeration above filled the first
        # one with no-good clauses.
        stage_two, primary_expr_2 = build_model_with_objective(scenario)
        assert stage_two.model is not None
        tiebreak_expr = tiebreak_objective_of(stage_two)
        stage_two.model.Add(primary_expr_2 == v_star)
        # ``minimize``, not ``Minimize``: ortools 9.15 installs the camelCase
        # aliases as *instance* attributes, and build_model_with_objective
        # shadows then deletes ``Minimize`` on this instance to capture the
        # expression, so the alias is gone by the time we get here. The
        # snake_case method is the real one and is unaffected.
        stage_two.model.minimize(tiebreak_expr)
        tiebreak_solver, tiebreak_status = _solve_to_optimality(stage_two.model)
        self.assertEqual(
            tiebreak_status,
            cp_model.OPTIMAL,
            "Stage 2 must close to a proven tie-break minimum on this model for "
            f"T* to be well defined; got {tiebreak_solver.StatusName(tiebreak_status)}.",
        )
        t_star = int(round(tiebreak_solver.ObjectiveValue()))

        # --- the canonical set: schedules at (P == V*) AND (T == T*) ---------
        stage_two.model.Add(tiebreak_expr == t_star)
        canonical, canonical_exhausted = _enumerate_distinct_schedules(stage_two)

        print(
            f"\n=== TIE ENUMERATION ({len(scenario.wells)} wells, "
            f"{len(scenario.rigs)} identical rigs) ===\n"
            f"optimal objective V*           : {v_star}\n"
            f"tie-break minimum T*           : {t_star}\n"
            f"tie-break weights              : W1={w1}, W2={w2}  "
            f"(max(rig_well_order)={order_bound}, hierarchy real: "
            f"{w1 > order_bound})\n"
            f"schedules at P-expr == V*      : {len(tied_at_v)}  (the tied set, "
            "expected > 1)\n"
            f"  hashes                       : {tied_at_v}\n"
            f"  enumeration exhausted        : {tied_exhausted}\n"
            f"schedules at V* AND T*         : {len(canonical)}  (the canonical "
            f"selection, measured value {MEASURED_CANONICAL_SCHEDULE_COUNT} — "
            "interchangeable permutations, clause 2.5.2)\n"
            f"  hashes                       : {canonical}\n"
            f"  enumeration exhausted        : {canonical_exhausted}"
        )

        self.assertTrue(
            tied_exhausted,
            f"Enumeration of the tied set hit the {ENUMERATION_CAP}-schedule "
            "cap, so its size is only a lower bound "
            f"(>= {len(tied_at_v)} at V* = {v_star}).",
        )
        self.assertTrue(
            canonical_exhausted,
            f"Enumeration of the canonical set hit the {ENUMERATION_CAP}-"
            "schedule cap, so the count below is only a lower bound "
            f"(>= {len(canonical)} at V* = {v_star}, T* = {t_star}). A capped "
            "count cannot be compared for equality against the measured value, "
            "so this is a failure and not a truncation.",
        )
        self.assertGreater(
            len(tied_at_v),
            1,
            "The tied set at P-expr == V* alone collapsed to "
            f"{len(tied_at_v)} schedule(s). Stage 1's objective is supposed to "
            "be byte-identical to the pre-fix objective, so this tie must still "
            "exist — it is what stage 2 chooses within, and this test documents "
            "it rather than only asserting a number. A collapse here means "
            "stage 1's objective moved (clause 3.8) or the scenario stopped "
            f"being symmetric. Tied hashes: {tied_at_v}",
        )
        self.assertEqual(
            len(canonical),
            MEASURED_CANONICAL_SCHEDULE_COUNT,
            f"{len(canonical)} distinct schedules share the optimal objective "
            f"{v_star} AND the tie-break minimum {t_star}; the measured value "
            f"for this model is {MEASURED_CANONICAL_SCHEDULE_COUNT}.\n"
            f"  MORE than {MEASURED_CANONICAL_SCHEDULE_COUNT} is a REGRESSION: "
            "something grew the interchangeable-permutation residual. The "
            "hierarchy is asserted real above (W1 > max(rig_well_order)), so "
            "the cause is not a collapsed hierarchy.\n"
            f"  FEWER than {MEASURED_CANONICAL_SCHEDULE_COUNT} means "
            "canonicalisation IMPROVED. That is good news, but the constant is "
            "a measurement of this model: revisit "
            "MEASURED_CANONICAL_SCHEDULE_COUNT deliberately and record the new "
            "number in bugfix.md clause 2.5.2 and the design's clause-2.5 "
            "decision record — do not loosen this assertion.\n"
            "  Note the residual is de-scoped by user decision (Option B), not "
            "unnoticed: both tie-break tiers are sums and the survivors differ "
            "only by permuting equal-duration wells on identical rigs, which "
            "leaves a sum invariant. The escalation for a residual that "
            "permutations do NOT explain is the third tie-break tier from "
            "design decision 3 (arc-order index over circuit_arcs), which is "
            "out of scope now per clause 2.5.3.\n"
            f"  Canonical hashes: {canonical}\n"
            f"  Tied set at V* alone: {len(tied_at_v)} {tied_at_v}",
        )
