"""
Intelligent Drilling Rig Scheduler (iDRS) – optimisation.py
Minimal edits from original:
 - setup_variables() now resets model/solver & variable dicts so model is rebuilt each run
 - solve() now runs full pipeline (preprocess_data -> setup_variables -> add_constraints -> add_ilm_constraints -> set_objective)
 - merge_wells_for_scenario(...) helper added for scenario re-runs
Other logic unchanged.

OPTIMALITY VALIDATION FRAMEWORK (v2.0):
 - Strict acceptance criteria: Only OPTIMAL status accepted
 - Zero optimality gap verification  
 - Dual-run determinism validation
 - Time-limit termination detection
 - Management-friendly certification reporting
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import logging
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Any, Dict, Iterable, List, Tuple, Optional, Union

import pandas as pd
from django.conf import settings
from ortools.sat.python import cp_model

logger = logging.getLogger(__name__)

# ==============================================================================
# DETERMINISTIC STOPPING CRITERION
# ==============================================================================
# The deterministic solve path stops on CP-SAT's *deterministic time* (a work
# counter) rather than on the wall clock. Wall-clock time is not a function of
# the request — the machine's own load is not part of the request — so a
# wall-clock stop lands on a different search node whenever the box is busy and
# returns a different schedule for identical inputs. Deterministic time is a
# function of the work performed, so the stop lands in the same place every run.
#
# See .kiro/specs/deterministic-schedule-fix/design.md, design decision 1.

#: Defaults for ``settings.IDRS_SOLVER_DETERMINISM``. Duplicated here rather
#: than assumed present so the optimizer still runs against a settings module
#: that predates the block, and so ``override_settings`` with a partial dict
#: behaves sensibly in tests.
#:
#: These must stay in step with ``drilling_scheduler/settings.py``, which is
#: where the reasoning for each value is recorded — in particular why
#: ``DETERMINISTIC_TIME_RATIO`` is 0.60 (search quality) and why
#: ``WALL_BACKSTOP_FACTOR`` is sized from measured contention on this host
#: rather than from a wall-time target.
DETERMINISM_SETTING_DEFAULTS: Dict[str, Any] = {
    "DETERMINISTIC_TIME_RATIO": 0.60,
    "WALL_BACKSTOP_FACTOR": 1.5,
    "CANONICALIZE_BUDGET_SHARE": 0.15,
    "FIXED_SEARCH": False,
}

#: Number of interleaved tasks CP-SAT completes before synchronising and
#: scheduling the next batch.
#:
#: Pinned rather than left at the proto default of 0, which means "derive it
#: from the worker count". Verified against the pinned ortools 9.15.6755: with
#: ``num_search_workers = 1`` the solver log reads "Setting number of tasks in
#: each batch of interleaved search to 1", so 1 is exactly the value the
#: derivation produces today and pinning it preserves current behaviour. What
#: the pin buys is that an OR-Tools upgrade can no longer change the batch size
#: — and with it the search path, and with it the schedule — silently: the value
#: is now a recorded parameter instead of an invisible default.
DETERMINISTIC_INTERLEAVE_BATCH_SIZE = 1

STOP_REASON_OPTIMAL_PROVEN = "OPTIMAL_PROVEN"
STOP_REASON_INFEASIBLE = "INFEASIBLE"
STOP_REASON_DETERMINISTIC_BUDGET = "DETERMINISTIC_BUDGET"
STOP_REASON_WALL_CLOCK_BACKSTOP = "WALL_CLOCK_BACKSTOP"
STOP_REASON_OTHER = "OTHER"

#: Fraction of the deterministic budget that counts as "the budget bound".
#: CP-SAT overshoots its own budget slightly — measured 7.0001 units against a
#: 7.0 budget — and can land a hair under it, so the test is a tolerance rather
#: than an equality.
#:
#: Relaxed from 0.995 to 0.93 after the task 3 follow-on measurement. Under
#: contention (8 of 12 cores busy) a run stopped at 3.4378 of its 3.6000 budget
#: — 95.49 % — while returning the *identical* schedule: same ``schedule_hash``
#: (``1a6136917eac05eb``), same objective, same 23 wells, five runs out of five.
#: At 0.995 that run classified ``OTHER`` with ``deterministic_stop = False``,
#: i.e. a false amber on a run that was in fact reproducible. 0.93 rather than
#: 0.95: the observed short stop is at 95.49 %, so 0.95 leaves no margin and
#: would false-amber again on the next slightly busier host.
#:
#: Why relaxing this is safe:
#:
#: * The single-solve ``deterministic_stop`` badge is **advisory**. It is a
#:   proxy for reproducibility, and one solve cannot actually prove
#:   reproducibility — that needs more than one run to compare.
#: * The **authoritative** check is the cross-run ``schedule_hash`` comparison
#:   in the ``check_determinism`` management command (task 10).
#: * The two genuinely non-reproducible modes are caught by *separate*
#:   classifiers, neither of which depends on this threshold: a run cut short by
#:   the clock is caught by ``WALL_BACKSTOP_BINDING_FRACTION`` as
#:   ``WALL_CLOCK_BACKSTOP``, and a genuinely divergent schedule is caught as a
#:   different ``schedule_hash``.
#: * The ``OTHER``/short-stop case this absorbs is a benign contention
#:   artefact: CP-SAT stopping a hair short of its own work budget while
#:   producing the same answer.
DETERMINISTIC_BUDGET_BINDING_FRACTION = 0.93

#: Fraction of the wall-clock backstop that counts as "the backstop bound".
WALL_BACKSTOP_BINDING_FRACTION = 0.98


# ==============================================================================
# INPUT VALIDATION — DUPLICATE NAMES
# ==============================================================================
# The optimizer keys *everything* on ``name``: the assignment / start / end /
# interval variable dicts, the distance matrix index and columns, the per-rig ILM
# matrices, the circuit arcs, every objective term, the extraction lookup and the
# assignment payload the save path consumes.  ``Well.name`` carries no
# ``unique=True``, so two selected wells can share a name — and when they do the
# two wells silently collapse onto one set of model variables and the run dies
# later with an error that names no well at all.
#
# Design decision 5 chooses to *reject* that input rather than re-key the model
# on ``Well.id``: re-keying is a cross-module contract change reaching into
# views.py, sem_views.py and well_rejection_analyzer.py, all to defend against a
# state that is already fatal today (``wells.get(name=...)`` in the save path
# raises ``MultipleObjectsReturned`` inside ``transaction.atomic()``).  Rejecting
# is a cheap invariant with an actionable message.
#
# See .kiro/specs/deterministic-schedule-fix/design.md, design decision 5.


class DuplicateNameError(ValueError):
    """A frame the optimizer keys by name contains a repeated name.

    Subclasses :class:`ValueError` so callers that already funnel bad input
    through ``except ValueError`` keep working; the typed class exists so the
    API layer can recognise this specific condition and translate it.
    """

    #: What the duplicated names label, for the message ("well" / "rig").
    entity = "record"

    def __init__(self, duplicate_names: Iterable[str]) -> None:
        self.duplicate_names: List[str] = sorted({str(n) for n in duplicate_names})
        super().__init__(self._build_message())

    def _build_message(self) -> str:
        names = ", ".join(self.duplicate_names)
        plural = "s" if len(self.duplicate_names) != 1 else ""
        return (
            f"Duplicate {self.entity} name{plural}: {names}. "
            f"The scheduler identifies each {self.entity} by its name, so two "
            f"{self.entity}s sharing a name cannot be scheduled separately. "
            f"Rename or remove the duplicate {self.entity}{plural} and run again."
        )


class DuplicateWellNameError(DuplicateNameError):
    """Two or more selected wells share a ``name`` (clauses 1.6 / 1.7, 2.9)."""

    entity = "well"


class DuplicateRigNameError(DuplicateNameError):
    """Two or more selected rigs share a ``name``.

    ``Rig.name`` is ``unique=True`` in the model, so this cannot fire from the
    database paths.  The check is free and documents the assumption for callers
    that build the frames by hand.
    """

    entity = "rig"


def find_duplicate_names(names: Iterable[Any]) -> List[str]:
    """Names appearing more than once, sorted, de-duplicated.

    Works on any iterable (a pandas ``Series``, a list of dicts' values, a
    queryset's ``values_list``) so the same helper serves the optimizer
    invariant and the API-boundary check.
    """
    seen: Dict[str, int] = {}
    for raw in names:
        key = str(raw)
        seen[key] = seen.get(key, 0) + 1
    return sorted(name for name, count in seen.items() if count > 1)


def determinism_settings() -> Dict[str, Any]:
    """The in-force ``IDRS_SOLVER_DETERMINISM`` values, defaults filled in.

    Read at call time and never cached, so ``override_settings`` works and a
    deployment can change the ratio without a code change.
    """
    configured = getattr(settings, "IDRS_SOLVER_DETERMINISM", None) or {}
    return {
        key: configured.get(key, default)
        for key, default in DETERMINISM_SETTING_DEFAULTS.items()
    }


def compute_solver_fingerprint(parameters: Any) -> str:
    """SHA-256 over everything that decides *how* the search runs.

    The companion to ``model_fingerprint``. That one identifies the *question*
    put to CP-SAT; this one identifies the *machinery* used to answer it. Two
    runs are only expected to agree when **both** match — a schedule produced
    under a different time ratio, or under ``FIXED_SEARCH``, is a different
    experiment even though the model is identical.

    Three components, and each is load-bearing:

    * ``str(parameters)`` — the protobuf text format of the ``SatParameters``
      message, which by protobuf's rules lists only the fields that were
      explicitly set. So it is the parameter *block the code chose*, not a dump
      of every default, and an OR-Tools upgrade that changes an unset default
      cannot silently perturb the fingerprint.
    * ``ortools.__version__`` — a solver upgrade can change the search path for
      an unchanged model and unchanged parameters, so the version is part of the
      identity of a run. This is the component that makes the fingerprint honest
      about reproducibility across a dependency bump.
    * The ``IDRS_SOLVER_DETERMINISM`` block plus
      ``DETERMINISTIC_INTERLEAVE_BATCH_SIZE`` — mostly redundant against the
      parameter text (the ratio reaches it through ``max_deterministic_time``,
      ``FIXED_SEARCH`` through ``search_branching``) and included anyway, because
      relying on that indirection would be relying on a coincidence. A future
      setting that changed behaviour without landing in the parameter proto would
      otherwise be invisible here.

    Deliberately **not** included: anything measured. No wall time, no
    deterministic time used, no timestamp. The fingerprint has to be a pure
    function of the configuration, or it could not be compared between runs —
    which is the only thing it is for.
    """
    try:
        import ortools

        ortools_version = getattr(ortools, "__version__", None)
    except Exception:  # pragma: no cover - ortools is a hard dependency
        ortools_version = None

    config = determinism_settings()
    payload = json.dumps(
        {
            # Text format rather than SerializeToString(): protobuf does not
            # guarantee deterministic binary output across versions, but the
            # text format of a message with a fixed field set is stable and is
            # additionally readable in a log when a mismatch needs diagnosing.
            "parameters": str(parameters),
            "ortools_version": ortools_version,
            "determinism_settings": {key: config[key] for key in sorted(config)},
            "interleave_batch_size": DETERMINISTIC_INTERLEAVE_BATCH_SIZE,
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


#: Identifies which solve stage a :class:`SolverBudget` was cut for.
STAGE_WHOLE_REQUEST = 0
STAGE_PRIMARY = 1
STAGE_CANONICALIZE = 2


@dataclass(frozen=True)
class SolverBudget:
    """How one selected time limit maps onto the solver's stopping parameters.

    Every field is a pure function of ``time_limit_seconds`` and the settings
    block. Nothing here is derived from a measured elapsed time — that is the
    whole point: a parameter computed from "time remaining" would feed this
    machine's clock back into the parameter proto and reintroduce the defect.
    """

    time_limit_seconds: float
    #: Binding limit for the deterministic path, in deterministic-time units.
    #: ``None`` on the performance path, which is given no work budget at all.
    deterministic_budget: Optional[float]
    #: Backstop only. Bounds the damage if the fixed work budget cannot be
    #: completed in time on a heavily contended machine.
    wall_backstop_seconds: float
    deterministic_time_ratio: float
    wall_backstop_factor: float
    #: Which stage this budget belongs to: ``STAGE_WHOLE_REQUEST`` for the
    #: undivided calibration, ``STAGE_PRIMARY`` / ``STAGE_CANONICALIZE`` for the
    #: two shares of the two-stage lexicographic solve.
    stage: int = STAGE_WHOLE_REQUEST
    #: Fraction of the whole-request budget this share represents. ``1.0`` for
    #: the undivided calibration.
    stage_share: float = 1.0


def calibrate_solver_budget(
    time_limit_seconds: float, deterministic: bool = True
) -> SolverBudget:
    """Map the user's selected time limit ``T`` onto ``(D, backstop)``.

    ``D = DETERMINISTIC_TIME_RATIO x T`` in deterministic-time units and
    ``backstop = WALL_BACKSTOP_FACTOR x T`` in seconds.

    Deterministic time is a work counter whose unit is only "as close as
    possible to a second", so the ratio is an empirical headroom allowance and
    not a unit conversion: the fixed work budget still has to complete inside
    the backstop when the machine is busy.

    ``deterministic=False`` reproduces the performance path's pre-existing
    wall-clock limit exactly (``max(1, int(T))``) and grants no work budget,
    because clause 3.12 attaches no determinism promise to that path.
    """
    limit = float(time_limit_seconds)
    config = determinism_settings()
    ratio = float(config["DETERMINISTIC_TIME_RATIO"])
    backstop_factor = float(config["WALL_BACKSTOP_FACTOR"])

    if not deterministic:
        return SolverBudget(
            time_limit_seconds=limit,
            deterministic_budget=None,
            wall_backstop_seconds=float(max(1, int(limit))),
            deterministic_time_ratio=ratio,
            wall_backstop_factor=backstop_factor,
        )

    return SolverBudget(
        time_limit_seconds=limit,
        deterministic_budget=ratio * limit,
        wall_backstop_seconds=backstop_factor * limit,
        deterministic_time_ratio=ratio,
        wall_backstop_factor=backstop_factor,
    )


@dataclass(frozen=True)
class TwoStageBudget:
    """The whole-request budget, split between the two lexicographic stages.

    ``stage_two`` is ``None`` on the performance path, which runs one stage and
    is promised no determinism at all (clause 3.12).
    """

    time_limit_seconds: float
    canonicalize_budget_share: float
    #: The undivided calibration, kept so the split can be checked against it.
    whole_request: SolverBudget
    stage_one: SolverBudget
    stage_two: Optional[SolverBudget]

    @property
    def deterministic_budgets_sum_exactly(self) -> bool:
        """Do the two work shares add back up to the whole-request budget?"""
        if self.stage_two is None or self.whole_request.deterministic_budget is None:
            return True
        return (
            self.stage_one.deterministic_budget + self.stage_two.deterministic_budget  # type: ignore[operator]
        ) == self.whole_request.deterministic_budget

    @property
    def wall_backstops_sum_exactly(self) -> bool:
        """Do the two wall shares add back up to ``FACTOR x T``?"""
        if self.stage_two is None:
            return True
        return (
            self.stage_one.wall_backstop_seconds + self.stage_two.wall_backstop_seconds
        ) == self.whole_request.wall_backstop_seconds


def calibrate_two_stage_budgets(
    time_limit_seconds: float, deterministic: bool = True
) -> TwoStageBudget:
    """Split ``(D, backstop)`` between the primary and canonicalising stages.

    ``D1 = (1 - share) x D`` and ``D2 = share x D`` in deterministic-time units;
    the wall backstop is split on the *same* share, so::

        stage_one.wall_backstop_seconds + stage_two.wall_backstop_seconds
            == WALL_BACKSTOP_FACTOR x T          (exactly)

    which is the total wall ceiling Property 4 bounds. Mirroring the split keeps
    each stage's wall allowance proportional to the work it was granted, and the
    two shares can never sum above the factor — if they did, the two-stage solve
    would silently exceed the ceiling the design states.

    **Both shares come from ``T`` and the settings block only.** Neither is
    "whatever wall time is left after stage 1". That is not a stylistic
    preference: a remaining-time computation would feed this machine's elapsed
    time back into the parameter proto, which is the exact defect this whole
    spec exists to remove. Under a same-machine scope it is the *only* channel
    left through which the bug could return, so it is closed by construction —
    this function cannot see a clock.

    The far share is computed first and the near share by subtraction
    (``D1 = D - D2``) rather than as ``(1 - share) x D``. Both spell the same
    quantity, but subtraction makes the two shares sum back to the whole exactly
    in floating point instead of within a rounding error, and "sums to exactly
    ``1.0 x FACTOR x T``" is the property the design asserts.

    On the performance path (``deterministic=False``) there is no second stage:
    ``stage_one`` is the pre-existing single-stage performance budget, unchanged.
    """
    whole = calibrate_solver_budget(time_limit_seconds, deterministic=deterministic)
    share = float(determinism_settings()["CANONICALIZE_BUDGET_SHARE"])

    if not deterministic:
        return TwoStageBudget(
            time_limit_seconds=whole.time_limit_seconds,
            canonicalize_budget_share=share,
            whole_request=whole,
            stage_one=whole,
            stage_two=None,
        )

    stage_two_backstop = share * whole.wall_backstop_seconds
    stage_one_backstop = whole.wall_backstop_seconds - stage_two_backstop

    whole_budget = whole.deterministic_budget
    assert whole_budget is not None, "the deterministic path always has a budget"
    stage_two_budget = share * whole_budget
    stage_one_budget = whole_budget - stage_two_budget

    def _share(stage: int, budget: float, backstop: float, fraction: float) -> SolverBudget:
        return SolverBudget(
            time_limit_seconds=whole.time_limit_seconds,
            deterministic_budget=budget,
            wall_backstop_seconds=backstop,
            deterministic_time_ratio=whole.deterministic_time_ratio,
            wall_backstop_factor=whole.wall_backstop_factor,
            stage=stage,
            stage_share=fraction,
        )

    return TwoStageBudget(
        time_limit_seconds=whole.time_limit_seconds,
        canonicalize_budget_share=share,
        whole_request=whole,
        stage_one=_share(
            STAGE_PRIMARY, stage_one_budget, stage_one_backstop, 1.0 - share
        ),
        stage_two=_share(
            STAGE_CANONICALIZE, stage_two_budget, stage_two_backstop, share
        ),
    )


# ------------------------------------------------------------------------------
# Stage-2 tie-break weights (design decision 3)
# ------------------------------------------------------------------------------

def max_rig_well_order(num_wells: int, num_rigs: int) -> int:
    """Upper bound on ``rig_well_order`` over all feasible assignments.

    ``rig_well_order`` sums ``well_index x num_rigs + rig_index`` over the
    *selected* ``(well, rig)`` pairs. Each well is assigned to at most one rig,
    so at most ``num_wells`` order indices are ever active and the bound is
    ``num_wells x num_pairs`` — not ``num_pairs x num_pairs``, which assumes
    every pair can be active at once and is loose by a factor of ``num_rigs``.

    Used to derive the dominating start-time weight. Deliberately *not* used to
    re-derive ``BIG_M_WELLS``: the design offers that as a padding correction,
    but Big-M is a coefficient of the stage-1 objective, and stage 1's objective
    has to stay byte-identical to today's or the reported ``objective_value``
    moves on requests that are already correct. Measured on the preservation
    scenario: tightening the padding shifted ``objective_value`` from
    698,525,729 to 698,525,679 and changed the model fingerprint. Tightening
    Big-M remains available as separate, independently-verified work.
    """
    return int(num_wells) * int(num_wells) * int(num_rigs)


def tiebreak_weights(num_wells: int, num_rigs: int) -> Tuple[int, int]:
    """``(W1, W2)`` for the stage-2 tie-break objective.

    ``W2 = 1`` and ``W1 = max(rig_well_order) + 1``, so ``W1`` strictly
    dominates every value the finer tier can take and the two tiers form a real
    hierarchy: start times decide first, and the canonical ``(well, rig)`` order
    only breaks what start times leave tied. With both weights at 1 — which is
    what stage 1 uses, unchanged — they are commensurate and form no order at
    all, which is the tie the canonicalising stage exists to resolve.

    These weights live only in stage 2, whose objective contains no Big-M, so
    they cannot be "a percentage of Big-M" and cannot widen any LP relaxation.
    That is the whole reason the tie-break moved into its own solve.
    """
    return max_rig_well_order(num_wells, num_rigs) + 1, 1


# ------------------------------------------------------------------------------
# Canonicalization outcomes (stage 2)
# ------------------------------------------------------------------------------

#: Stage 2 closed: the tie-break minimum is proven, so the selection is
#: canonical.
CANONICALIZATION_CANONICAL_OPTIMAL = "CANONICAL_OPTIMAL"
#: Stage 2 improved the tie-break but did not prove its minimum. The selection
#: is reproducible (its stop is deterministic) but not provably canonical.
CANONICALIZATION_CANONICAL_INCUMBENT = "CANONICAL_INCUMBENT"
#: Stage 2 found nothing better than stage 1, so stage 1's solution is kept.
CANONICALIZATION_ALREADY_CANONICAL = "ALREADY_CANONICAL"
#: Not attempted: performance mode makes no determinism promise (clause 3.12).
CANONICALIZATION_SKIPPED_PERFORMANCE_MODE = "SKIPPED_PERFORMANCE_MODE"
#: Not attempted: stage 1 returned neither OPTIMAL nor FEASIBLE, so there is no
#: solution to canonicalise and no ``V*`` to lock.
CANONICALIZATION_SKIPPED_NO_STAGE_1_SOLUTION = "SKIPPED_NO_STAGE_1_SOLUTION"
#: Not attempted: ``set_objective`` did not publish the expressions.
CANONICALIZATION_SKIPPED_NO_EXPRESSIONS = "SKIPPED_NO_EXPRESSIONS"
#: Attempted and failed. Stage 1's solution is returned intact in every case.
CANONICALIZATION_FAILED_INFEASIBLE = "FAILED_INFEASIBLE"
CANONICALIZATION_FAILED_NO_SOLUTION = "FAILED_NO_SOLUTION"
CANONICALIZATION_FAILED_EXCEPTION = "FAILED_EXCEPTION"

#: Every outcome in which stage 1's solution is what the caller receives.
CANONICALIZATION_STAGE_ONE_PRESERVED = (
    CANONICALIZATION_ALREADY_CANONICAL,
    CANONICALIZATION_SKIPPED_PERFORMANCE_MODE,
    CANONICALIZATION_SKIPPED_NO_STAGE_1_SOLUTION,
    CANONICALIZATION_SKIPPED_NO_EXPRESSIONS,
    CANONICALIZATION_FAILED_INFEASIBLE,
    CANONICALIZATION_FAILED_NO_SOLUTION,
    CANONICALIZATION_FAILED_EXCEPTION,
)


@dataclass(frozen=True)
class CanonicalizationOutcome:
    """What the canonicalising stage did, and whether its answer was adopted."""

    status: str
    #: True only when stage 2's variable values replaced stage 1's.
    adopted: bool
    stage_two_solver_status: Optional[str] = None
    #: Tie-break objective value of stage 1's solution, and of stage 2's.
    tiebreak_before: Optional[int] = None
    tiebreak_after: Optional[int] = None
    deterministic_time: Optional[float] = None
    wall_time: Optional[float] = None
    model_fingerprint: Optional[str] = None
    detail: Optional[str] = None
    #: Stage 2's variable values, keyed by variable index. Never part of the
    #: result payload — the payload gets the *status*, because stage 2's
    #: objective is a tie-break index with no business meaning.
    values: Optional[Dict[int, int]] = field(default=None, repr=False)

    def as_dict(self) -> Dict[str, Any]:
        """The reportable fields. Excludes ``values``."""
        return {
            "canonicalization_status": self.status,
            "canonicalization_adopted": self.adopted,
            "canonicalization_solver_status": self.stage_two_solver_status,
            "canonicalization_tiebreak_before": self.tiebreak_before,
            "canonicalization_tiebreak_after": self.tiebreak_after,
            "canonicalization_deterministic_time": self.deterministic_time,
            "canonicalization_wall_time": self.wall_time,
            "canonicalization_model_fingerprint": self.model_fingerprint,
            "canonicalization_detail": self.detail,
        }


@dataclass(frozen=True)
class StopClassification:
    """Why the solver stopped, and whether that reason is reproducible."""

    stop_reason: str
    deterministic_stop: bool
    deterministic_time_used: float
    deterministic_budget: Optional[float]
    wall_backstop_seconds: Optional[float]

    def as_dict(self) -> Dict[str, Any]:
        """The five fields, ready for the result payload (task 8's work)."""
        return {
            "stop_reason": self.stop_reason,
            "deterministic_stop": self.deterministic_stop,
            "deterministic_time_used": self.deterministic_time_used,
            "deterministic_budget": self.deterministic_budget,
            "wall_backstop_seconds": self.wall_backstop_seconds,
        }


def classify_stop_reason(
    status: Any,
    deterministic_time: float,
    wall_time: float,
    deterministic_budget: Optional[float],
    wall_backstop_seconds: Optional[float],
) -> StopClassification:
    """Classify the stop, in the order the design fixes.

    ``OPTIMAL`` is checked first because a proof needs no budget: a run that
    proved optimality is reproducible whatever the clock did. ``INFEASIBLE`` is
    likewise a complete answer. Only then does the budget matter, and the
    wall-clock backstop comes last because it is the one outcome that is *not*
    reproducible — it is flagged rather than hidden (clause 2.4).
    """
    used = float(deterministic_time)
    elapsed = float(wall_time)

    if status == cp_model.OPTIMAL:
        reason, deterministic_stop = STOP_REASON_OPTIMAL_PROVEN, True
    elif status == cp_model.INFEASIBLE:
        reason, deterministic_stop = STOP_REASON_INFEASIBLE, True
    elif deterministic_budget and used >= (
        DETERMINISTIC_BUDGET_BINDING_FRACTION * float(deterministic_budget)
    ):
        reason, deterministic_stop = STOP_REASON_DETERMINISTIC_BUDGET, True
    elif wall_backstop_seconds and elapsed >= (
        WALL_BACKSTOP_BINDING_FRACTION * float(wall_backstop_seconds)
    ):
        reason, deterministic_stop = STOP_REASON_WALL_CLOCK_BACKSTOP, False
    else:
        reason, deterministic_stop = STOP_REASON_OTHER, False

    return StopClassification(
        stop_reason=reason,
        deterministic_stop=deterministic_stop,
        deterministic_time_used=used,
        deterministic_budget=deterministic_budget,
        wall_backstop_seconds=wall_backstop_seconds,
    )


# ==============================================================================
# OPTIMALITY VALIDATION FRAMEWORK
# ==============================================================================

class AcceptanceStatus(Enum):
    """Schedule acceptance status with clear business meaning."""
    ACCEPTED = "ACCEPTED"           # Schedule is provably optimal and certified
    REJECTED = "REJECTED"           # Schedule failed one or more validation criteria
    PENDING_REVIEW = "PENDING"      # Schedule requires manual review (edge cases)


class RejectionReason(Enum):
    """Specific reasons for schedule rejection - for audit trail."""
    SOLVER_NOT_OPTIMAL = "Solver did not return OPTIMAL status"
    TIME_LIMIT_REACHED = "Solver terminated due to time limit before proving optimality"
    OPTIMALITY_GAP_NONZERO = "Optimality gap is non-zero (solution not proven optimal)"
    DETERMINISM_FAILURE = "Dual-run verification failed (different results on identical inputs)"
    INFEASIBLE_PROBLEM = "No feasible solution exists for the given constraints"
    NO_SOLUTION_FOUND = "Solver could not find any solution"
    SOLVER_ERROR = "Solver encountered an internal error"
    VALIDATION_ERROR = "Validation process encountered an error"


@dataclass
class SolverMetrics:
    """Raw metrics captured from a single solver execution."""
    status_code: int                          # OR-Tools status code
    status_name: str                          # Human-readable status
    objective_value: Optional[float] = None   # Solution's objective function value
    best_bound: Optional[float] = None        # Best proven bound on optimal objective
    optimality_gap: Optional[float] = None    # Gap between objective and bound (%)
    wall_time_seconds: float = 0.0            # Actual solve time
    time_limit_seconds: float = 0.0           # Configured time limit
    time_limit_reached: bool = False          # Did we hit the time limit?
    num_solutions: int = 0                    # Number of solutions found
    num_conflicts: int = 0                    # Search conflicts (complexity indicator)
    num_branches: int = 0                     # Search branches explored


@dataclass
class ValidationResult:
    """Complete validation result for a scheduling run."""
    # Acceptance decision
    is_accepted: bool
    acceptance_status: AcceptanceStatus
    rejection_reasons: List[RejectionReason] = field(default_factory=list)
    
    # Solver metrics from primary run
    primary_metrics: Optional[SolverMetrics] = None
    
    # Dual-run verification (if enabled)
    dual_run_enabled: bool = False
    dual_run_passed: bool = False
    verification_metrics: Optional[SolverMetrics] = None
    schedule_hash_primary: Optional[str] = None
    schedule_hash_verification: Optional[str] = None
    
    # Validation criteria used
    criteria: Dict[str, Any] = field(default_factory=dict)
    
    # Timestamps for audit
    validation_timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    # Management summary
    summary: str = ""
    recommendations: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "is_accepted": self.is_accepted,
            "acceptance_status": self.acceptance_status.value,
            "rejection_reasons": [r.value for r in self.rejection_reasons],
            "dual_run_enabled": self.dual_run_enabled,
            "dual_run_passed": self.dual_run_passed,
            "criteria": self.criteria,
            "validation_timestamp": self.validation_timestamp,
            "summary": self.summary,
            "recommendations": self.recommendations,
        }
        if self.primary_metrics:
            result["primary_metrics"] = asdict(self.primary_metrics)
        if self.verification_metrics:
            result["verification_metrics"] = asdict(self.verification_metrics)
        if self.schedule_hash_primary:
            result["schedule_hash_primary"] = self.schedule_hash_primary
        if self.schedule_hash_verification:
            result["schedule_hash_verification"] = self.schedule_hash_verification
        return result


@dataclass 
class CertifiedSchedule:
    """A schedule with full optimality certification - the auditable output."""
    # The actual schedule data
    schedule_data: Dict[str, Any]
    
    # Validation and certification
    validation_result: ValidationResult
    
    # Certification metadata
    certification_id: str = ""
    certified_at: str = ""
    certified_optimal: bool = False
    
    def __post_init__(self):
        if not self.certification_id:
            self.certification_id = self._generate_certification_id()
        if not self.certified_at:
            self.certified_at = datetime.now().isoformat()
        self.certified_optimal = self.validation_result.is_accepted
    
    def _generate_certification_id(self) -> str:
        """Generate unique certification ID based on schedule content."""
        content = json.dumps(self.schedule_data.get("assignments", []), sort_keys=True, default=str)
        hash_obj = hashlib.sha256(content.encode())
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        return f"CERT-{timestamp}-{hash_obj.hexdigest()[:12].upper()}"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "certification_id": self.certification_id,
            "certified_at": self.certified_at,
            "certified_optimal": self.certified_optimal,
            "schedule": self.schedule_data,
            "validation": self.validation_result.to_dict(),
        }
    
    def get_management_report(self) -> Dict[str, Any]:
        """Generate executive summary for management review."""
        v = self.validation_result
        m = v.primary_metrics
        
        report = {
            "certification_id": self.certification_id,
            "decision": v.acceptance_status.value,
            "is_certified_optimal": self.certified_optimal,
            "timestamp": self.certified_at,
            
            # Key metrics (management-friendly)
            "solver_status": m.status_name if m else "Unknown",
            "solve_time_seconds": round(m.wall_time_seconds, 2) if m else 0,
            "optimality_gap_percent": round(m.optimality_gap * 100, 4) if m and m.optimality_gap is not None else None,
            
            # Verification status
            "dual_run_verification": "PASSED" if v.dual_run_passed else ("NOT PERFORMED" if not v.dual_run_enabled else "FAILED"),
            
            # Summary for executives
            "executive_summary": v.summary,
            
            # If rejected, explain why
            "rejection_reasons": [r.value for r in v.rejection_reasons] if not self.certified_optimal else [],
            
            # Actionable recommendations
            "recommendations": v.recommendations,
            
            # Schedule summary
            "wells_assigned": len(self.schedule_data.get("assignments", [])),
            "wells_unassigned": len(self.schedule_data.get("unassigned_wells", [])),
            "project_end_date": str(self.schedule_data.get("project_end_date", "")),
            "total_cost": self.schedule_data.get("total_drilling_cost", 0) + self.schedule_data.get("total_ilm_cost", 0),
        }
        
        return report


class OptimalityValidator:
    """
    Strict Optimality Validation Framework.
    
    Ensures schedules are accepted ONLY when:
    1. Solver returns OPTIMAL status (not just FEASIBLE)
    2. No time-limit termination occurred  
    3. Optimality gap is zero (objective == best bound)
    4. Dual-run verification passes (determinism check)
    
    This provides mathematically defensible, auditable schedule certification.
    """
    
    # Tolerance for floating-point comparison in gap calculation
    GAP_TOLERANCE = 1e-9
    
    def __init__(
        self,
        require_optimal_status: bool = True,
        require_zero_gap: bool = True,
        require_dual_run: bool = True,
        max_gap_tolerance: float = 0.0,
    ):
        """
        Initialize validator with acceptance criteria.
        
        Args:
            require_optimal_status: Reject if solver status != OPTIMAL
            require_zero_gap: Reject if optimality gap > 0
            require_dual_run: Run solver twice and compare results
            max_gap_tolerance: Maximum acceptable gap (0.0 = zero tolerance)
        """
        self.require_optimal_status = require_optimal_status
        self.require_zero_gap = require_zero_gap
        self.require_dual_run = require_dual_run
        self.max_gap_tolerance = max_gap_tolerance
    
    def extract_solver_metrics(
        self,
        solver: cp_model.CpSolver,
        status: Any,  # CpSolverStatus or int
        wall_time: float,
        time_limit: float,
    ) -> SolverMetrics:
        """Extract comprehensive metrics from solver after execution."""
        status_name = solver.StatusName(status) if hasattr(solver, "StatusName") else str(status)
        
        metrics = SolverMetrics(
            status_code=status,
            status_name=status_name,
            wall_time_seconds=wall_time,
            time_limit_seconds=time_limit,
        )
        
        # Extract objective and bound for gap calculation
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            try:
                metrics.objective_value = solver.ObjectiveValue()
                metrics.best_bound = solver.BestObjectiveBound()
                
                # Calculate optimality gap using standard MIP convention:
                #   gap = |objective - bound| / max(|objective|, epsilon)
                #
                # IMPORTANT: For this pure-minimisation model every objective
                # term is non-negative, so the true optimum is always >= 0.
                # CP-SAT's LP relaxation of Big-M models can produce deeply
                # negative best_bound values when it hasn't converged (common
                # for large problems with short time-limits).  A negative
                # bound is mathematically valid but useless — it inflates the
                # gap to millions of percent.  Clamping the bound to 0 gives
                # a tight, meaningful gap that never exceeds 100%.
                obj = metrics.objective_value
                bound = max(metrics.best_bound, 0.0)  # true optimal >= 0
                denom = max(abs(obj), 1e-10)
                gap = abs(obj - bound) / denom
                metrics.optimality_gap = gap
                
            except Exception as e:
                logger.warning(f"Could not extract objective/bound: {e}")
        
        # Check if time limit was reached (solve time very close to limit)
        time_ratio = wall_time / time_limit if time_limit > 0 else 0
        metrics.time_limit_reached = time_ratio >= 0.95  # Within 5% of limit
        
        # Additional diagnostics
        try:
            metrics.num_conflicts = solver.NumConflicts()
            metrics.num_branches = solver.NumBranches()
        except Exception:
            pass
        
        return metrics
    
    def compute_schedule_hash(self, schedule_data: Dict[str, Any]) -> str:
        """Compute deterministic hash of schedule for comparison."""
        # Extract and sort assignments for consistent hashing
        assignments = schedule_data.get("assignments", [])
        sorted_assignments = sorted(
            assignments, 
            key=lambda x: (x.get("rig", ""), x.get("well", ""), x.get("well_start_day", 0))
        )
        
        # Create canonical representation
        canonical = {
            "assignments": [
                {
                    "rig": a.get("rig"),
                    "well": a.get("well"),
                    "start_day": a.get("well_start_day"),
                    "end_day": a.get("well_end_day"),
                }
                for a in sorted_assignments
            ],
            "unassigned": sorted(schedule_data.get("unassigned_wells", [])),
            "project_end_day": schedule_data.get("project_end_day"),
        }
        
        content = json.dumps(canonical, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()
    
    def validate_single_run(self, metrics: SolverMetrics) -> Tuple[bool, List[RejectionReason]]:
        """
        Validate a single solver run against acceptance criteria.
        
        Returns:
            Tuple of (passed, list of rejection reasons)
        """
        reasons = []
        
        # Check 1: OPTIMAL status required
        if self.require_optimal_status:
            if metrics.status_code != cp_model.OPTIMAL:
                if metrics.status_code == cp_model.INFEASIBLE:
                    reasons.append(RejectionReason.INFEASIBLE_PROBLEM)
                elif metrics.status_code == cp_model.MODEL_INVALID:
                    reasons.append(RejectionReason.SOLVER_ERROR)
                elif metrics.status_code == cp_model.UNKNOWN:
                    reasons.append(RejectionReason.NO_SOLUTION_FOUND)
                else:
                    reasons.append(RejectionReason.SOLVER_NOT_OPTIMAL)
        
        # Check 2: Time limit not reached
        if metrics.time_limit_reached and metrics.status_code != cp_model.OPTIMAL:
            reasons.append(RejectionReason.TIME_LIMIT_REACHED)
        
        # Check 3: Zero optimality gap
        if self.require_zero_gap and metrics.optimality_gap is not None:
            if metrics.optimality_gap > self.max_gap_tolerance + self.GAP_TOLERANCE:
                reasons.append(RejectionReason.OPTIMALITY_GAP_NONZERO)
        
        passed = len(reasons) == 0
        return passed, reasons
    
    def validate_dual_run(
        self,
        primary_result: Dict[str, Any],
        verification_result: Dict[str, Any],
    ) -> Tuple[bool, str, str]:
        """
        Compare two solver runs for determinism.
        
        Returns:
            Tuple of (passed, primary_hash, verification_hash)
        """
        primary_hash = self.compute_schedule_hash(primary_result)
        verification_hash = self.compute_schedule_hash(verification_result)
        
        passed = primary_hash == verification_hash
        return passed, primary_hash, verification_hash
    
    def generate_summary(
        self,
        is_accepted: bool,
        metrics: SolverMetrics,
        reasons: List[RejectionReason],
        dual_passed: Optional[bool] = None,
    ) -> str:
        """Generate human-readable summary for management."""
        if is_accepted:
            return (
                f"✓ SCHEDULE CERTIFIED OPTIMAL. "
                f"Solver proved global optimality in {metrics.wall_time_seconds:.1f}s. "
                f"Optimality gap: 0%. "
                f"{'Dual-run verification passed.' if dual_passed else ''}"
            )
        else:
            reason_text = "; ".join([r.value for r in reasons])
            return (
                f"✗ SCHEDULE REJECTED. "
                f"Solver status: {metrics.status_name}. "
                f"Solve time: {metrics.wall_time_seconds:.1f}s / {metrics.time_limit_seconds}s limit. "
                f"Reasons: {reason_text}"
            )
    
    def generate_recommendations(
        self,
        is_accepted: bool,
        metrics: SolverMetrics,
        reasons: List[RejectionReason],
    ) -> List[str]:
        """Generate actionable recommendations based on validation results."""
        if is_accepted:
            return ["Schedule is certified optimal. Safe to proceed with execution."]
        
        recommendations = []
        
        if RejectionReason.TIME_LIMIT_REACHED in reasons:
            recommendations.append(
                f"Increase time limit from {int(metrics.time_limit_seconds)}s. "
                f"Problem complexity may require 2-5x more time for optimality proof."
            )
        
        if RejectionReason.SOLVER_NOT_OPTIMAL in reasons and metrics.status_name == "FEASIBLE":
            recommendations.append(
                "Solver found a feasible solution but couldn't prove optimality. "
                "Options: (1) Increase time limit, (2) Simplify constraints, (3) Accept with documented risk."
            )
        
        if RejectionReason.OPTIMALITY_GAP_NONZERO in reasons:
            gap_pct = (metrics.optimality_gap or 0) * 100
            recommendations.append(
                f"Optimality gap is {gap_pct:.2f}%. "
                f"This means the solution could be up to {gap_pct:.2f}% worse than true optimal. "
                f"Increase time limit or reduce problem size for zero-gap proof."
            )
        
        if RejectionReason.INFEASIBLE_PROBLEM in reasons:
            recommendations.append(
                "No feasible solution exists. Review constraints: "
                "rig availability windows, well requirements, actual date locks."
            )
        
        if RejectionReason.DETERMINISM_FAILURE in reasons:
            recommendations.append(
                "Different results on identical runs indicate non-determinism. "
                "Check solver configuration (random_seed, num_workers, search strategy)."
            )
        
        if not recommendations:
            recommendations.append("Contact technical support for detailed analysis.")
        
        return recommendations
    
    def create_validation_result(
        self,
        is_accepted: bool,
        primary_metrics: SolverMetrics,
        rejection_reasons: List[RejectionReason],
        dual_run_enabled: bool = False,
        dual_run_passed: bool = False,
        verification_metrics: Optional[SolverMetrics] = None,
        schedule_hash_primary: Optional[str] = None,
        schedule_hash_verification: Optional[str] = None,
    ) -> ValidationResult:
        """Create comprehensive validation result."""
        status = AcceptanceStatus.ACCEPTED if is_accepted else AcceptanceStatus.REJECTED
        
        return ValidationResult(
            is_accepted=is_accepted,
            acceptance_status=status,
            rejection_reasons=rejection_reasons,
            primary_metrics=primary_metrics,
            dual_run_enabled=dual_run_enabled,
            dual_run_passed=dual_run_passed,
            verification_metrics=verification_metrics,
            schedule_hash_primary=schedule_hash_primary,
            schedule_hash_verification=schedule_hash_verification,
            criteria={
                "require_optimal_status": self.require_optimal_status,
                "require_zero_gap": self.require_zero_gap,
                "require_dual_run": self.require_dual_run,
                "max_gap_tolerance": self.max_gap_tolerance,
            },
            summary=self.generate_summary(is_accepted, primary_metrics, rejection_reasons, dual_run_passed),
            recommendations=self.generate_recommendations(is_accepted, primary_metrics, rejection_reasons),
        )


class DrillingScheduler:
    """
    Main scheduler class implementing the iDRS_main.py logic while keeping the
    optimisation.py public surface compatible for the hosting app.
    """

    def __init__(self, rigs_data: Iterable[Dict[str, Any]], wells_data: Iterable[Dict[str, Any]], 
                 base_start_date: Optional[date] = None,
                 fy_start_date: Optional[date] = None,
                 fy_end_date: Optional[date] = None):
        """
        Initialize the drilling scheduler.
        
        Args:
            rigs_data: Rig data as list of dicts or DataFrame
            wells_data: Well data as list of dicts or DataFrame
            base_start_date: The reference date for day 0 in optimization (defaults to earliest rig start)
            fy_start_date: Financial year start date (e.g., April 1, 2024). 
                          If provided, wells can only start on or after this date.
            fy_end_date: Financial year end date (e.g., March 31, 2025).
                        If provided, wells must START on or before this date.
                        Note: Wells can FINISH after this date to accommodate drilling duration.
        """
        # keep original input containers (we will normalize in preprocess_data)
        self.rigs_df = self._to_dataframe(rigs_data, kind="rigs")
        self.wells_df = self._to_dataframe(wells_data, kind="wells")

        if base_start_date is None:
            if fy_start_date is not None:
                # When scheduling within a Financial Year, use FY start as day 0.
                # This keeps all day indices small (0–~400 instead of 0–14000+),
                # which dramatically tightens the LP relaxation and lets the
                # solver prove optimality much faster.
                # RTD dates / rig dates earlier than FY start simply become
                # negative day indices → their >= constraints are trivially
                # satisfied (start_time is always ≥ 0).
                base_start_date = fy_start_date
            else:
                # No FY: fall back to earliest rig start
                try:
                    ts = pd.to_datetime(self.rigs_df["start_date"], errors="coerce").dropna()
                    if len(ts) > 0:
                        base_start_date = ts.dt.date.min()
                    else:
                        base_start_date = date.today()
                except Exception:
                    base_start_date = date.today()
        self.base_start_date: date = base_start_date  # date (not datetime)
        
        # Financial Year constraints
        self.fy_start_date: Optional[date] = fy_start_date
        self.fy_end_date: Optional[date] = fy_end_date

        # Model will be created/reset in setup_variables()
        self.model: Optional[cp_model.CpModel] = None
        self.solver: Optional[cp_model.CpSolver] = None

        # variable containers
        self.assignments: Dict[Tuple[str, str], cp_model.IntVar] = {}
        self.start_times: Dict[Tuple[str, str], cp_model.IntVar] = {}
        self.end_times: Dict[Tuple[str, str], cp_model.IntVar] = {}
        self.intervals: Dict[Tuple[str, str], cp_model.IntervalVar] = {}

        # These store BoolVar.Not() which returns a negated literal, not IntVar
        self.unassigned_vars: List[Any] = []
        self.high_priority_unassigned: List[Any] = []

        self.horizon: int = 3650
        self.project_end: Optional[cp_model.IntVar] = None

        self.status = None
        #: The stopping-criterion calibration applied by the last
        #: ``_configure_solver_for_determinism`` call.
        self.solver_budget: Optional[SolverBudget] = None

        # --- Two-stage lexicographic solve (design decision 3) --------------
        #: The full composite expression stage 1 minimises (P-expr). Published
        #: by ``set_objective`` so stage 2 can lock it as an equality.
        self.primary_objective_expr: Optional[Any] = None
        #: ``W1 x start_time_sum + W2 x rig_well_order`` (T-expr), the only
        #: thing stage 2 minimises.
        self.tiebreak_objective_expr: Optional[Any] = None
        self.tiebreak_weights: Optional[Tuple[int, int]] = None
        #: ``(well, rig) -> canonical order index``, in the canonical insertion
        #: order. Lets the tie-break value be evaluated for a captured solution
        #: without going back to a solver.
        self.rig_well_order_index: Dict[Tuple[str, str], int] = {}
        #: Metrics captured from **stage 1**, which are the only ones the
        #: business may see. Stage 2's objective is a tie-break index.
        self.stage_one_metrics: Optional[Dict[str, Any]] = None
        #: What the canonicalising stage did.
        self.canonicalization: Optional[CanonicalizationOutcome] = None
        #: Fingerprint of the stage-1 model proto, recorded before stage 2
        #: mutates the model. This is *the* model fingerprint of the request.
        self.model_fingerprint: Optional[str] = None
        #: Fingerprint of the stage-2 proto. A deterministic function of stage
        #: 1's result, so the chain fp1 -> V* -> fp2 is itself reproducible.
        self.model_fingerprint_stage_two: Optional[str] = None
        #: The budget split in force for the last solve.
        self.two_stage_budget: Optional[TwoStageBudget] = None
        #: Why the last ``Solve()`` stopped. Set by ``solve`` and
        #: ``solve_with_actuals``; consumed by the result payload.
        self.stop_classification: Optional[StopClassification] = None
        self.distance_matrix: pd.DataFrame = pd.DataFrame()
        self.ilm_days_matrix: Dict[str, pd.DataFrame] = {}  # Per-rig ILM days matrices
        self.circuit_arcs: Dict[Tuple[str, str, str], cp_model.IntVar] = {}  # Circuit arc variables: (well_i, well_j, rig) -> BoolVar
        self.results: Dict[str, Any] = {}

    def _to_dataframe(self, data: Iterable[Dict[str, Any]], kind: str) -> pd.DataFrame:
        """Best-effort conversion from list/QuerySet to DataFrame with normalized columns."""
        if isinstance(data, pd.DataFrame):
            df = data.copy()
        else:
            df = pd.DataFrame(list(data))

        rename_map = {
            "Name": "name",
            "Rig": "name",
            "Well": "name",
            "Start Date": "start_date",
            "End Date": "end_date",
            "RTD": "rtd",
            "Duration": "duration",
            "Rig Capacity HP": "rig_capacity_hp",
            "Drilling Capacity (m)": "drilling_capacity_m",
            "BOP Stack": "bop_stack",
            "TDS Availability": "tds_availability",
            "Daily Cost INR": "daily_cost_inr",
            "ILM COST FIXED": "ilm_cost_fixed",
            "ILM COST per km": "ilm_cost_per_km",
            "ILM COST CLUSTER": "ilm_cost_cluster",
            "Rig Capacity Required HP": "rig_capacity_required_hp",
            "Depth": "depth",
            "BOP Stack Required": "bop_stack",
            "TDS Requirement": "tds_requirement",
            "Priority": "priority",
            "Latitude": "latitude",
            "Longitude": "longitude",
        }
        df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

        if kind == "rigs":
            defaults = {
                "name": None,
                "start_date": None,
                "end_date": None,
                "rig_capacity_hp": 0,
                "drilling_capacity_m": 0,
                "bop_stack": 0,
                "tds_availability": "N",
                "daily_cost_inr": 0,
                "ilm_cost_fixed": 0,
                "ilm_cost_per_km": 0,
                "ilm_cost_cluster": 0,
            }
        else:
            defaults = {
                "name": None,
                "duration": None,
                "rtd": None,
                "rig_capacity_required_hp": 0,
                "depth": 0,
                "bop_stack": 0,
                "tds_requirement": "N",
                "priority": "MEDIUM",
                "latitude": 0.0,
                "longitude": 0.0,
            }
        for col, val in defaults.items():
            if col not in df.columns:
                df[col] = val

        return df

    # --------------------------
    # Preprocessing
    # --------------------------
    # Maximum date that pandas Timestamp can represent (ns precision)
    _PANDAS_DATE_CAP = date(2260, 1, 1)

    def _safe_to_datetime(self, series: pd.Series, col_name: str, default_date: date | None = None) -> pd.Series:
        """Convert a series to pandas datetime, capping dates beyond year 2260
        and filling NaT with a sensible default.  Prevents the NaTType crash."""
        # First, cap any Python date / datetime objects that exceed Pandas Timestamp.max
        def _cap_date(val):
            if val is None or (isinstance(val, float) and pd.isna(val)):
                return pd.NaT
            try:
                if hasattr(val, 'year') and val.year > 2260:
                    return pd.Timestamp(self._PANDAS_DATE_CAP)
            except Exception:
                pass
            return val

        capped = series.apply(_cap_date)
        ts = pd.to_datetime(capped, errors="coerce", dayfirst=True)

        # Fill remaining NaT with a safe default
        if ts.isna().any():
            fallback = pd.Timestamp(default_date or date.today())
            na_count = ts.isna().sum()
            logger.warning(f"Column '{col_name}': {na_count} invalid/missing date(s) replaced with {fallback.date()}")
            ts = ts.fillna(fallback)
        return ts

    @staticmethod
    def _sort_frame_totally(df: pd.DataFrame) -> pd.DataFrame:
        """Sort a rig/well frame on a TOTAL key, stably, and reindex.

        Design decision 6 (ordering hardening).  ``name`` on its own is not a
        total key — ``Well.name`` has no ``unique=True`` — so rows that tie on it
        would keep whatever relative position the upstream queryset, DataFrame
        construction or dict iteration happened to give them.  Adding ``id``
        makes the key total; ``kind="stable"`` guarantees that when ``id`` is
        absent the caller's order is preserved instead of being permuted by the
        default (introsort) algorithm.
        """
        sort_keys = ["name", "id"] if "id" in df.columns else ["name"]
        return df.sort_values(by=sort_keys, kind="stable").reset_index(drop=True)

    def _reject_duplicate_names(self) -> None:
        """Refuse a run whose rig or well names are not unique (clause 2.9).

        Raises :class:`DuplicateWellNameError` / :class:`DuplicateRigNameError`
        naming *every* duplicate.  ``Rig.name`` is ``unique=True`` in the model
        so the rig branch cannot fire from a database-built frame, but the check
        is free and documents the assumption for hand-built frames.
        """
        duplicate_wells = find_duplicate_names(self.wells_df["name"])
        if duplicate_wells:
            logger.error(
                "Rejecting run: duplicate well name(s) %s among %d wells",
                duplicate_wells,
                len(self.wells_df),
            )
            raise DuplicateWellNameError(duplicate_wells)

        duplicate_rigs = find_duplicate_names(self.rigs_df["name"])
        if duplicate_rigs:
            logger.error(
                "Rejecting run: duplicate rig name(s) %s among %d rigs",
                duplicate_rigs,
                len(self.rigs_df),
            )
            raise DuplicateRigNameError(duplicate_rigs)

    def preprocess_data(self) -> None:
        """Normalize types, compute rig windows & distance matrix."""
        # Dates – safely convert and cap extreme years (e.g. 9999)
        today = date.today()
        far_future = today + timedelta(days=365 * 10)  # 10 years out as default end

        self.rigs_df["start_date"] = self._safe_to_datetime(
            self.rigs_df["start_date"], "rig start_date", default_date=today
        )
        self.rigs_df["end_date"] = self._safe_to_datetime(
            self.rigs_df["end_date"], "rig end_date", default_date=far_future
        )
        self.wells_df["rtd"] = self._safe_to_datetime(
            self.wells_df["rtd"], "well rtd", default_date=today
        )

        # Rig window length
        self.rigs_df["duration_days"] = (self.rigs_df["end_date"] - self.rigs_df["start_date"]).dt.days + 1

        # Duration sanity – compute from drl_days + pt_days if provided
        if ("duration" not in self.wells_df.columns) or self.wells_df["duration"].isna().any() or (self.wells_df["duration"] <= 0).any():
            drl = self.wells_df.get("drl_days", pd.Series([0] * len(self.wells_df))).fillna(0).astype(int)
            pt = self.wells_df.get("pt_days", pd.Series([0] * len(self.wells_df))).fillna(0).astype(int)
            self.wells_df["duration"] = (drl + pt).replace(0, 1)  # avoid zero-length intervals

        self.wells_df["duration"] = self.wells_df["duration"].astype(int)

        # Priority normalization
        self.wells_df["priority"] = self.wells_df["priority"].fillna("MEDIUM").astype(str).str.upper()

        # Reject duplicate names BEFORE the sort, and before any expensive work.
        #
        # Design decision 5.  Everything downstream of here is keyed by name —
        # the distance matrix, the per-rig ILM matrices, the assignment /
        # start / end / interval variable dicts, every objective term and the
        # assignment payload the save path consumes — so a repeated name does
        # not produce a wrong answer, it produces *no* answer for one of the
        # colliding wells: the two collapse onto one set of variables and the
        # pipeline dies further downstream naming no well at all.
        #
        # This is the single choke point for the invariant: every ``solve`` /
        # ``solve_with_actuals`` call site and the SEM path all route through
        # ``preprocess_data``.  The message names the duplicates so the operator
        # has something to act on.
        self._reject_duplicate_names()

        # Sort rigs and wells by name BEFORE building matrices
        # so that variable IDs, constraint ordering, and the model proto
        # are identical across runs regardless of upstream row order.
        #
        # The key must be TOTAL, not merely sorted: ``name`` alone ties whenever
        # two rows share a name (Well.name carries no unique=True), and a tied
        # sort leaves those rows wherever the input happened to put them.  The
        # ``id`` column — present because both production paths build these
        # frames from ``.values()`` — is what makes the key total.
        # ``kind="stable"`` is belt-and-braces for frames that arrive without
        # ``id``: it at least preserves the caller's order rather than letting
        # NumPy's default quicksort permute tied rows unpredictably.
        self.rigs_df = self._sort_frame_totally(self.rigs_df)
        self.wells_df = self._sort_frame_totally(self.wells_df)

        # Distance matrix (km, Haversine)
        self._calculate_distance_matrix()
        
        # ILM days matrix (per-rig) - uses Data Management norms
        self._calculate_ilm_days_matrix()

        logger.info(f"Preprocessing complete: {len(self.rigs_df)} rigs, {len(self.wells_df)} wells")

    def _calculate_distance_matrix(self) -> None:
        wells = self.wells_df
        n = len(wells)
        dm = pd.DataFrame(index=wells["name"], columns=wells["name"], dtype=float)
        for i in range(n):
            for j in range(n):
                if i == j:
                    dm.iat[i, j] = 0.0
                else:
                    dm.iat[i, j] = self._haversine_distance(
                        float(wells.iloc[i]["latitude"]),
                        float(wells.iloc[i]["longitude"]),
                        float(wells.iloc[j]["latitude"]),
                        float(wells.iloc[j]["longitude"]),
                    )
        self.distance_matrix = dm.fillna(0.0)

    @staticmethod
    def _haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        R = 6371.0
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
        return 2 * R * math.asin(math.sqrt(a))

    def _calculate_ilm_days_matrix(self) -> None:
        """
        Build ILM days matrix using pre-calculated data from WellPairDistance table.
        
        The Data Management module already calculates ILM days for each well pair
        using RigBuildingNorm and RigBuildingAdjustment rules. This method retrieves
        those values from the WellPairDistance table and the calculate_ilm_days function.
        
        Creates a per-rig ILM days matrix stored in self.ilm_days_matrix[rig_name]
        """
        from .models import WellPairDistance, Rig as RigModel
        from .views import calculate_ilm_days
        
        wells = self.wells_df
        rigs = self.rigs_df
        n_wells = len(wells)
        well_names = list(wells["name"])
        
        logger.info("Building ILM days matrix from WellPairDistance table...")
        
        # NOTE: a ``well name -> Well object`` lookup used to be built here with
        # ``Well.objects.get(name=...)`` per well.  It was never read, and its
        # broad ``except Exception`` swallowed the ``MultipleObjectsReturned``
        # that duplicate well names raise — aborting the loop silently.  Deleted
        # under design decision 5: one fewer name-keyed database lookup and one
        # fewer swallowed exception.  Duplicate names are now rejected up front
        # in ``_reject_duplicate_names``.
        
        for _, rig_row in rigs.iterrows():
            rig_name = rig_row["name"]
            
            # Create empty matrix for this rig
            ilm_matrix = pd.DataFrame(
                index=wells["name"], 
                columns=wells["name"], 
                dtype=float
            )
            ilm_matrix.values[:] = 0.0  # Initialize all to 0
            
            # Try to get the rig from database
            try:
                rig_obj = RigModel.objects.select_related('rig_building_norm', 'location').get(name=rig_name)
                norm_days = rig_obj.rig_building_norm.days if rig_obj.rig_building_norm else None
                location = rig_obj.location
            except RigModel.DoesNotExist:
                logger.warning(f"Rig {rig_name} not found in database, using fallback ILM calculation")
                rig_obj = None
                norm_days = None
                location = None
            
            # Try to get pre-calculated distances from WellPairDistance table
            distance_cache: Dict[Tuple[str, str], float] = {}
            if rig_obj:
                try:
                    # TOTAL ordering (design decision 6).  Each row below writes
                    # BOTH directions into distance_cache, and the filter is
                    # rig=rig_obj with no location predicate, so two rows can
                    # cover the same (well_1.name, well_2.name) pair.  Unordered,
                    # whichever the database returned last silently won.
                    well_pair_distances = WellPairDistance.objects.filter(
                        rig=rig_obj
                    ).select_related('well_1', 'well_2').order_by(
                        'well_1__name', 'well_2__name', 'id'
                    )
                    
                    for wpd in well_pair_distances:
                        w1_name = wpd.well_1.name
                        w2_name = wpd.well_2.name
                        distance_m = float(wpd.distance_km)  # Field stores meters despite name
                        distance_cache[(w1_name, w2_name)] = distance_m
                        distance_cache[(w2_name, w1_name)] = distance_m  # Symmetric
                except Exception as e:
                    logger.warning(f"Error loading WellPairDistance for rig {rig_name}: {e}")
            
            # Calculate ILM days for each well pair
            for i in range(n_wells):
                for j in range(n_wells):
                    if i == j:
                        continue  # Already 0
                    
                    w1_name = well_names[i]
                    w2_name = well_names[j]
                    
                    # Get distance - prefer from WellPairDistance, fallback to distance matrix
                    if (w1_name, w2_name) in distance_cache:
                        distance_m = distance_cache[(w1_name, w2_name)]
                    else:
                        # Convert from km to m using our calculated distance matrix
                        distance_m = self.distance_matrix.iat[i, j] * 1000
                    
                    # Calculate ILM days using Data Management function
                    if rig_obj and location and norm_days is not None:
                        try:
                            ilm_result = calculate_ilm_days(rig_obj, distance_m, location, norm_days)
                            ilm_days = ilm_result.get('ilm_days', 0) or 0
                        except Exception as e:
                            logger.warning(f"Error calculating ILM days for {w1_name}->{w2_name}: {e}")
                            ilm_days = self._get_ilm_days(distance_m / 1000)  # Fallback
                    else:
                        # Fallback to simple formula
                        ilm_days = self._get_ilm_days(distance_m / 1000)
                    
                    ilm_matrix.iat[i, j] = float(ilm_days)
            
            self.ilm_days_matrix[rig_name] = ilm_matrix
        
        logger.info(f"ILM days matrix built for {len(rigs)} rigs using Data Management norms")

    # --------------------------
    # Variables
    # --------------------------
    def setup_variables(self) -> None:
        """Create OR-Tools variables aligned with iDRS_main."""
        logger.info("Setting up variables...")

        # Reset model & solver to ensure clean rebuild on every run
        self.model = cp_model.CpModel()
        self.solver = cp_model.CpSolver()

        # Reset variable containers (important for re-runs)
        self.assignments = {}
        self.start_times = {}
        self.end_times = {}
        self.intervals = {}
        self.unassigned_vars = []
        self.high_priority_unassigned = []
        self.project_end = None
        self.circuit_arcs = {}  # Reset circuit arcs for fresh model

        # Horizon: upper bound on all start_time / end_time variables.
        # Base horizon from rig availability windows (guard against zero).
        try:
            self.horizon = int(max(1, self.rigs_df["duration_days"].max()) * 2)
        except Exception:
            self.horizon = 365 * 2

        # Cap horizon to FY window + max well duration so that variable
        # domains reflect the actual scheduling window.  The FY end constraint
        # already prevents wells from starting after FY end, so this cap
        # removes unreachable days and dramatically tightens the LP relaxation
        # (smaller Big-M coefficients → solver proves optimality faster).
        # Wells that finish AFTER FY end are still allowed (end_time can
        # exceed fy_end_day by up to max_well_duration).
        if self.fy_end_date is not None:
            try:
                fy_end_day = int((self.fy_end_date - self.base_start_date).days)
                max_well_dur = int(max(
                    (int(w.get("duration", 0) or 0) for _, w in self.wells_df.iterrows()),
                    default=0,
                ))
                # Allow end_time up to fy_end_day + max_well_duration (well can
                # finish past FY).  Add small buffer for safety.
                fy_capped_horizon = fy_end_day + max_well_dur + 30
                if fy_capped_horizon < self.horizon:
                    logger.info(
                        f"Horizon capped from {self.horizon} to {fy_capped_horizon} "
                        f"(FY end day {fy_end_day} + max well duration {max_well_dur} + 30 day buffer)"
                    )
                    self.horizon = fy_capped_horizon
            except Exception as e:
                logger.warning(f"Could not cap horizon to FY window: {e}")

        # Type narrowing assertions for Pylance
        assert self.model is not None, "Model must be initialized"
        assert self.solver is not None, "Solver must be initialized"

        for _, w in self.wells_df.iterrows():
            wid = w["name"]
            dur = int(w["duration"])
            for _, r in self.rigs_df.iterrows():
                rid = r["name"]
                self.assignments[(wid, rid)] = self.model.NewBoolVar(f"assign_{wid}_{rid}")
                self.start_times[(wid, rid)] = self.model.NewIntVar(0, self.horizon, f"start_{wid}_{rid}")
                self.end_times[(wid, rid)] = self.model.NewIntVar(0, self.horizon, f"end_{wid}_{rid}")
                self.intervals[(wid, rid)] = self.model.NewOptionalIntervalVar(
                    self.start_times[(wid, rid)],
                    dur,
                    self.end_times[(wid, rid)],
                    self.assignments[(wid, rid)],
                    f"interval_{wid}_{rid}",
                )

    # --------------------------
    # Solver Configuration
    # --------------------------
    def _configure_solver_for_determinism(
        self,
        time_limit_seconds: float,
        deterministic: bool = True,
        *,
        budget: Optional[SolverBudget] = None,
        solver: Optional[cp_model.CpSolver] = None,
        record: bool = True,
    ) -> SolverBudget:
        """Configure the solver's stopping criterion and search parameters.

        Args:
            time_limit_seconds: The time limit the user selected, ``T``.
            deterministic: If True, stop on a fixed work budget so the run is
                          reproducible. If False, use the performance path
                          (multi-threaded, wall-clock stop, no guarantee).
            budget: A pre-cut budget to apply instead of the whole-request
                   calibration. Used to hand each stage of the two-stage solve
                   its own share. Still a pure function of ``T`` and the
                   settings block — see ``calibrate_two_stage_budgets``.
            solver: Configure this solver instead of ``self.solver``. Stage 2
                   runs on its own ``CpSolver`` so that ``self.solver`` keeps
                   holding stage 1's parameters and counters, which is what the
                   reported metrics and the stop classification are read from.
            record: Whether to retain the applied budget as
                   ``self.solver_budget``. False for stage 2, so the stop
                   classification stays stage 1's.

        Returns:
            The :class:`SolverBudget` that was applied, so the caller can
            classify the stop after ``Solve()``.

        Deterministic mode stops on **work, not elapsed time**:

        - ``max_deterministic_time = RATIO x T`` is the binding limit
        - ``max_time_in_seconds = WALL_BACKSTOP_FACTOR x T`` is a backstop only
        - ``num_search_workers = 1``, ``random_seed = 42``,
          ``AUTOMATIC_SEARCH``, ``symmetry_level = 2``, ``use_lns = True``,
          ``interleave_search = True``, ``interleave_batch_size`` pinned

        Scope of the guarantee: **same machine.** The same request run
        repeatedly on this machine performs the same amount of search and
        returns the same schedule regardless of how busy the machine is, because
        the stop is metered in work rather than in elapsed time. ``ortools`` is
        pinned in ``requirements.txt`` (``ortools==9.15.6755``), so the solver
        build is a fixed, recorded input to that guarantee. Nothing here claims
        anything about a different machine or a different CPU architecture.

        Hard rule, and the reason this function takes only ``T``: no solver
        parameter may be derived from a measured wall time. Every parameter is a
        pure function of ``T`` and the settings block. A "time remaining"
        computation would feed this machine's clock back into the parameter
        proto, which is precisely the defect being fixed.

        Performance mode (``deterministic=False``) is deliberately left exactly
        as it was — wall-clock limit, ``num_search_workers = 0``,
        ``PORTFOLIO_SEARCH``, no work budget. Clause 3.12 attaches no
        determinism promise to it.
        """
        target = solver if solver is not None else self.solver
        assert target is not None, "Solver must be initialized"

        if budget is None:
            budget = calibrate_solver_budget(
                time_limit_seconds, deterministic=deterministic
            )
        if record:
            self.solver_budget = budget

        if deterministic:
            # --- Stopping criterion -------------------------------------------
            # Measured, not assumed. On this machine, at an identical model
            # proto fingerprint: idle, five runs returned 1 schedule; under CPU
            # load, 2 of 3 runs differed, with deterministic_time drifting
            # (0.7595 / 0.8579 loaded against 3.4378 idle). The stop was being
            # taken at different amounts of completed search work, which is what
            # a wall-clock limit does when the cores are contended. The earlier
            # comment here claimed CP-SAT is "perfectly deterministic
            # out-of-the-box" with a wall-clock stop; the measurement says the
            # opposite, so the claim is gone.
            #
            # It also claimed max_deterministic_time cripples LNS because LNS
            # "relies on real CPU cycles". It does not: LNS is already metered in
            # deterministic time. Its sibling parameters say so in their names —
            # probing_deterministic_time_limit, shaving_search_deterministic_time,
            # lns_initial_deterministic_limit, feasibility_jump_batch_dtime — and
            # the solver log reports a dtime limit per LNS subsolver. Putting the
            # global budget on the same counter is what makes an LNS-heavy search
            # reproducible run to run.
            target.parameters.max_deterministic_time = budget.deterministic_budget
            # Backstop only, never expected to bind. When it does bind the run is
            # flagged as a non-deterministic stop (clause 2.4) rather than being
            # silently irreproducible.
            target.parameters.max_time_in_seconds = budget.wall_backstop_seconds

            # --- Search parameters, unchanged (clause 3.4) ---------------------
            # Single worker: prevents non-deterministic branching.
            target.parameters.num_search_workers = 1

            # Fixed random seed for reproducibility.
            target.parameters.random_seed = 42

            # AUTOMATIC_SEARCH keeps solver speed, and it is what makes the two
            # decision strategies from _add_decision_strategy a *hint*: CP-SAT
            # consults them for the first descent, then branches as it sees fit.
            #
            # FIXED_SEARCH promotes those same strategies to a mandate — the
            # solver follows them and explores nothing else. That is the setting
            # for an audit run, where a stable search *path* matters more than
            # the quality of the answer. It stays off by default because it
            # costs a great deal of solution quality on large models; it is the
            # knob that was removed once for exactly that reason, and its cost
            # is only bounded at all now because task 3 stops the solve on
            # completed work rather than on the clock.
            #
            # It changes the answer, so it belongs in the solver fingerprint
            # (task 8) — a run made under FIXED_SEARCH is not comparable to one
            # made without it.
            if determinism_settings()["FIXED_SEARCH"]:
                target.parameters.search_branching = cp_model.FIXED_SEARCH
                branching_label = "FIXED_SEARCH"
                logger.warning(
                    "IDRS_FIXED_SEARCH is enabled: the decision strategies are "
                    "now a mandate, not a hint. Expect materially worse "
                    "objective values on large models. This belongs in the "
                    "solver fingerprint — schedules produced under it are not "
                    "comparable to schedules produced without it."
                )
            else:
                target.parameters.search_branching = cp_model.AUTOMATIC_SEARCH
                branching_label = "AUTO_SEARCH"

            # Symmetry breaking and LNS are deterministic under this
            # configuration, and both are worth real solution quality.
            target.parameters.symmetry_level = 2
            target.parameters.use_lns = True

            # Interleaved search is CP-SAT's deterministic scheduling mode: it
            # completes a batch of tasks, synchronises, then schedules the next
            # batch. Batch boundaries are work boundaries, not clock boundaries.
            target.parameters.interleave_search = True

            # Pin the batch size instead of letting OR-Tools derive it from the
            # worker count. 1 is the derived value today, so behaviour is
            # unchanged; see DETERMINISTIC_INTERLEAVE_BATCH_SIZE.
            target.parameters.interleave_batch_size = DETERMINISTIC_INTERLEAVE_BATCH_SIZE

            logger.info(
                f"Solver configured: DETERMINISTIC mode "
                f"(single-threaded, {branching_label}, seed=42, LNS=True, interleave=True, "
                f"batch={DETERMINISTIC_INTERLEAVE_BATCH_SIZE}), "
                f"stage={budget.stage} share={budget.stage_share:.4f}, "
                f"binding limit: max_deterministic_time={budget.deterministic_budget:.4f} "
                f"units (ratio {budget.deterministic_time_ratio} x {time_limit_seconds}s "
                f"x share {budget.stage_share:.4f}), "
                f"wall-clock backstop: {budget.wall_backstop_seconds:.2f}s "
                f"(factor {budget.wall_backstop_factor} x share {budget.stage_share:.4f})"
            )
        else:
            # Performance mode: UNCHANGED behaviour, deliberately.
            # The wall-clock limit used to be assigned before this branch, so
            # this is the same expression that ran before, moved in here now the
            # deterministic branch no longer wants it. int() truncates, and that
            # truncation is part of the recorded pre-fix parameter block.
            target.parameters.max_time_in_seconds = budget.wall_backstop_seconds

            # Performance mode: use all available workers
            target.parameters.num_search_workers = 0  # 0 = auto-detect
            
            # Still use fixed seed for some reproducibility
            target.parameters.random_seed = 42
            
            # Portfolio search works well with multi-threading
            target.parameters.search_branching = cp_model.PORTFOLIO_SEARCH
            
            # Enable symmetry breaking and LNS for better solutions in performance mode
            target.parameters.symmetry_level = 2
            target.parameters.use_lns = True
            
            logger.info(
                f"Solver configured: PERFORMANCE mode (multi-threaded), "
                f"time_limit={time_limit_seconds}s"
            )
        
        # Enable presolve (always beneficial)
        target.parameters.cp_model_presolve = True
        
        # Disable solution enumeration
        target.parameters.enumerate_all_solutions = False

        return budget

    def _classify_stop(self) -> StopClassification:
        """Classify why the solver stopped, from the counters it just reported.

        Reads ``deterministic_time`` and ``wall_time`` off the solver and
        compares them against the budget that was configured for this solve.
        Read-only: nothing here changes a parameter, so the classification
        cannot influence the answer it describes.
        """
        assert self.solver is not None, "Solver must be initialized"
        budget = self.solver_budget
        return classify_stop_reason(
            self.status,
            self.solver.deterministic_time,
            self.solver.wall_time,
            budget.deterministic_budget if budget else None,
            budget.wall_backstop_seconds if budget else None,
        )

    def _record_stop_classification(self, label: str) -> StopClassification:
        """Classify the stop, retain it on the instance and log it."""
        classification = self._classify_stop()
        self.stop_classification = classification
        logger.info(
            f"Stop reason ({label}): {classification.stop_reason} "
            f"(deterministic_stop={classification.deterministic_stop}, "
            f"deterministic_time_used={classification.deterministic_time_used:.4f}, "
            f"deterministic_budget={classification.deterministic_budget}, "
            f"wall_backstop_seconds={classification.wall_backstop_seconds})"
        )
        if not classification.deterministic_stop:
            logger.warning(
                f"Stop was NOT deterministic ({classification.stop_reason}): this run "
                "is not guaranteed to be reproducible. "
                f"deterministic_time_used={classification.deterministic_time_used:.4f} "
                f"of budget {classification.deterministic_budget}, "
                f"wall_time={self.solver.wall_time:.2f}s of backstop "  # type: ignore[union-attr]
                f"{classification.wall_backstop_seconds}s."
            )
        return classification

    # --------------------------
    # Two-stage lexicographic solve (design decision 3)
    # --------------------------
    def _reset_two_stage_state(self) -> None:
        """Clear everything the previous solve recorded about its two stages.

        ``solve()`` is documented as safe to call repeatedly, so stale stage-1
        metrics from an earlier call must never survive into a later payload.
        """
        self.stage_one_metrics = None
        self.canonicalization = None
        self.model_fingerprint = None
        self.model_fingerprint_stage_two = None
        self.two_stage_budget = None

    def _capture_variable_values(
        self, solver: cp_model.CpSolver
    ) -> Dict[int, int]:
        """Snapshot the decision variables into a plain ``{index: value}`` dict.

        Taken **before** stage 2 touches the model, because that is the only
        moment stage 1's answer exists anywhere retrievable: the model is mutated
        in place, and ``self.solver`` holds counters rather than an immutable
        solution. Keyed by variable index rather than by the variable object
        because ``IntVar.__eq__`` builds a linear constraint instead of
        comparing, so the variables are not usable as dict keys.
        """
        values: Dict[int, int] = {}
        for mapping in (self.assignments, self.start_times, self.end_times):
            for var in mapping.values():
                values[var.index] = int(solver.Value(var))
        if self.project_end is not None:
            values[self.project_end.index] = int(solver.Value(self.project_end))
        return values

    def _value_reader(self, values: Optional[Dict[int, int]] = None):
        """A ``var -> int`` lookup, from a captured dict or from the solver.

        This is the seam that lets ``_extract_solution`` read variable values
        from either stage without knowing which one it is reading. ``None``
        means "ask ``self.solver``", i.e. stage 1.
        """
        if values is None:
            solver = self.solver
            assert solver is not None, "Solver must be initialized"
            return lambda var: int(solver.Value(var))
        return lambda var: int(values[var.index])

    def _capture_stage_one_metrics(self) -> Dict[str, Any]:
        """Record the objective metrics **stage 1** reported.

        These are the only metrics the business may see. Stage 2 minimises a
        tie-break index whose value has no meaning outside the canonicalisation,
        so letting it reach the payload would put nonsense on the detail page.
        Captured here rather than read later so the provenance is a fact about
        the code path, not a consequence of which solver object happens to still
        be reachable.
        """
        assert self.solver is not None, "Solver must be initialized"
        metrics: Dict[str, Any] = {
            "solver_status_code": self.status,
            "objective_value": None,
            "best_bound": None,
            "optimality_gap": None,
        }
        if self.status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            try:
                objective_value = self.solver.ObjectiveValue()
                best_bound = self.solver.BestObjectiveBound()
                # Standard MIP gap, computed exactly as the single-stage code
                # computed it: divide by |objective|, and clamp the bound at 0
                # because every term of this pure-minimisation objective is >= 0.
                clamped_bound = max(best_bound, 0.0)
                denom = max(abs(objective_value), 1e-10)
                metrics["objective_value"] = objective_value
                metrics["best_bound"] = best_bound
                metrics["optimality_gap"] = (
                    abs(objective_value - clamped_bound) / denom
                )
            except Exception as e:
                logger.warning(f"Could not extract stage-1 objective metrics: {e}")
        self.stage_one_metrics = metrics
        return metrics

    def _tiebreak_objective_value(self, values: Dict[int, int]) -> int:
        """Evaluate T-expr for a captured solution, without a solver.

        Lets stage 1's tie-break value be compared against stage 2's, which is
        how "stage 2 found nothing better" is detected.
        """
        assert self.tiebreak_weights is not None, "set_objective must have run"
        start_weight, order_weight = self.tiebreak_weights
        start_sum = sum(values[var.index] for var in self.start_times.values())
        order_sum = sum(
            values[self.assignments[key].index] * order_index
            for key, order_index in self.rig_well_order_index.items()
        )
        return start_weight * start_sum + order_weight * order_sum

    def _prepare_canonical_stage(
        self, stage_one_objective_value: int, stage_one_values: Dict[int, int]
    ) -> None:
        """Lock stage 1's objective at ``V*`` and swap in the tie-break objective.

        Stage 2 locks the full stage-1 objective as an equality
        (``Add(P-expr == V*)``), then minimises only the tie-break expression, so
        it cannot change economics and cannot touch a unique optimum.

        Locking the **full** objective rather than tiers 1-3 is what makes that
        true: stage 2's feasible set becomes exactly the set of solutions today's
        solver is already free to return arbitrarily, so the only thing it can do
        is replace an arbitrary choice with a canonical one. When that set has
        one member — a unique proven optimum — stage 2 has nothing to choose
        between and the output cannot move.

        Stage 1's solution is hinted onto the assignment and start-time
        variables, so stage 2 opens with a known feasible incumbent and its only
        work is improving the tie-break rather than re-finding a solution.

        A separate seam from the solve itself so a test can subclass and inject a
        contradiction, which is how the stage-2 failure path is exercised.
        """
        model = self.model
        assert model is not None, "Model must be initialized"
        assert self.primary_objective_expr is not None
        assert self.tiebreak_objective_expr is not None

        model.Add(self.primary_objective_expr == stage_one_objective_value)

        model.ClearHints()
        # Iteration order is dict insertion order, which is the canonical
        # (well, rig) order built in setup_variables. Load-bearing: the hint
        # order is part of the model proto, so iterating a set here would make
        # the proto — and with it the search — vary between runs.
        for var in self.assignments.values():
            model.AddHint(var, stage_one_values[var.index])
        for var in self.start_times.values():
            model.AddHint(var, stage_one_values[var.index])

        # Minimize replaces the objective outright (CpModel._set_objective calls
        # clear_objective first), so P-expr survives only as the equality above.
        model.Minimize(self.tiebreak_objective_expr)

    def _canonicalize_stage_one_solution(
        self,
        *,
        time_limit_seconds: float,
        stage_budget: SolverBudget,
        stage_one_values: Dict[int, int],
        stage_one_objective_value: float,
        label: str,
    ) -> CanonicalizationOutcome:
        """Run stage 2 and decide whether to adopt its answer.

        Never raises and never returns stage 1's result in a worse state than it
        received it. Every failure — infeasible, no solution, no improvement, an
        exception from the solver — comes back as an outcome with ``adopted``
        false, and the caller then extracts from stage 1's captured values.
        """
        model = self.model
        assert model is not None, "Model must be initialized"

        v_star = int(round(stage_one_objective_value))
        tiebreak_before = self._tiebreak_objective_value(stage_one_values)

        try:
            self._prepare_canonical_stage(v_star, stage_one_values)

            # Stage 2 gets its own CpSolver so that self.solver keeps holding
            # stage 1's parameters and counters: the reported metrics and the
            # stop classification are read from there.
            stage_two_solver = cp_model.CpSolver()
            self._configure_solver_for_determinism(
                time_limit_seconds,
                deterministic=True,
                budget=stage_budget,
                solver=stage_two_solver,
                record=False,
            )

            fingerprint = hashlib.sha256(str(model.Proto()).encode()).hexdigest()
            self.model_fingerprint_stage_two = fingerprint
            logger.info(f"MODEL FINGERPRINT ({label}, stage 2): {fingerprint}")

            status = stage_two_solver.Solve(model)
            status_name = stage_two_solver.StatusName(status)
            deterministic_time = float(stage_two_solver.deterministic_time)
            wall_time = float(stage_two_solver.wall_time)

            if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                failure = (
                    CANONICALIZATION_FAILED_INFEASIBLE
                    if status == cp_model.INFEASIBLE
                    else CANONICALIZATION_FAILED_NO_SOLUTION
                )
                logger.warning(
                    f"Canonicalization ({label}) found no solution: {status_name}. "
                    "Returning the stage-1 schedule unchanged — stage 2 is only "
                    "allowed to improve the tie-break, never to lose a result."
                )
                return CanonicalizationOutcome(
                    status=failure,
                    adopted=False,
                    stage_two_solver_status=status_name,
                    tiebreak_before=tiebreak_before,
                    deterministic_time=deterministic_time,
                    wall_time=wall_time,
                    model_fingerprint=fingerprint,
                    detail=f"stage 2 returned {status_name}",
                )

            stage_two_values = self._capture_variable_values(stage_two_solver)
            tiebreak_after = self._tiebreak_objective_value(stage_two_values)

            if tiebreak_after >= tiebreak_before:
                # Stage 1 was already at or below the tie-break value stage 2
                # reached, so there is nothing to gain and no reason to swap one
                # member of the tied set for another.
                logger.info(
                    f"Canonicalization ({label}): stage 1 already canonical "
                    f"(tie-break {tiebreak_before} <= {tiebreak_after})."
                )
                return CanonicalizationOutcome(
                    status=CANONICALIZATION_ALREADY_CANONICAL,
                    adopted=False,
                    stage_two_solver_status=status_name,
                    tiebreak_before=tiebreak_before,
                    tiebreak_after=tiebreak_after,
                    deterministic_time=deterministic_time,
                    wall_time=wall_time,
                    model_fingerprint=fingerprint,
                )

            adopted_status = (
                CANONICALIZATION_CANONICAL_OPTIMAL
                if status == cp_model.OPTIMAL
                else CANONICALIZATION_CANONICAL_INCUMBENT
            )
            logger.info(
                f"Canonicalization ({label}): {adopted_status}, tie-break "
                f"{tiebreak_before} -> {tiebreak_after}, stage-2 status "
                f"{status_name}, deterministic_time={deterministic_time:.4f} of "
                f"budget {stage_budget.deterministic_budget:.4f}"
            )
            return CanonicalizationOutcome(
                status=adopted_status,
                adopted=True,
                stage_two_solver_status=status_name,
                tiebreak_before=tiebreak_before,
                tiebreak_after=tiebreak_after,
                deterministic_time=deterministic_time,
                wall_time=wall_time,
                model_fingerprint=fingerprint,
                values=stage_two_values,
            )
        except Exception as e:  # pragma: no cover - defensive
            logger.exception(
                f"Canonicalization ({label}) raised; returning the stage-1 "
                f"schedule unchanged: {e}"
            )
            return CanonicalizationOutcome(
                status=CANONICALIZATION_FAILED_EXCEPTION,
                adopted=False,
                tiebreak_before=tiebreak_before,
                detail=f"{type(e).__name__}: {e}",
            )

    def _run_two_stage_solve(
        self, time_limit_seconds: float, deterministic: bool, label: str
    ) -> Dict[str, Any]:
        """Solve stage 1, canonicalise with stage 2, extract one payload.

        Both entry points (``solve`` and ``solve_with_actuals``) funnel through
        here after building their model, so the canonicalisation guarantee cannot
        be present on one path and missing on the other.

        Reported metrics come from stage 1. Variable *values* come from stage 2
        only when stage 2 succeeded and actually improved the tie-break.
        """
        assert self.model is not None, "Model must be initialized"
        assert self.solver is not None, "Solver must be initialized"

        self._reset_two_stage_state()
        budgets = calibrate_two_stage_budgets(
            time_limit_seconds, deterministic=deterministic
        )
        self.two_stage_budget = budgets

        self._configure_solver_for_determinism(
            time_limit_seconds, deterministic=deterministic, budget=budgets.stage_one
        )

        # Model fingerprint: SHA-256 of the serialised stage-1 model proto.
        # Taken before stage 2 mutates the model, so this stays the fingerprint
        # of the model whose objective value is reported. If two runs produce the
        # same fingerprint the solver MUST return the same solution (given
        # deterministic settings).
        self.model_fingerprint = hashlib.sha256(
            str(self.model.Proto()).encode()
        ).hexdigest()
        logger.info(f"MODEL FINGERPRINT ({label}): {self.model_fingerprint}")

        import time
        stage_one_started = time.time()
        self.status = self.solver.Solve(self.model)
        stage_one_seconds = time.time() - stage_one_started
        self.solve_time_seconds = stage_one_seconds

        self._record_stop_classification(label)
        stage_one_metrics = self._capture_stage_one_metrics()

        stage_one_values: Optional[Dict[int, int]] = None
        if self.status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            stage_one_values = self._capture_variable_values(self.solver)

        outcome = self._resolve_canonicalization(
            time_limit_seconds=time_limit_seconds,
            budgets=budgets,
            deterministic=deterministic,
            stage_one_values=stage_one_values,
            stage_one_objective_value=stage_one_metrics.get("objective_value"),
            label=label,
        )
        self.canonicalization = outcome
        if outcome.wall_time:
            self.solve_time_seconds = stage_one_seconds + outcome.wall_time

        value_lookup = outcome.values if outcome.adopted else stage_one_values
        return self._extract_solution(time_limit_seconds, value_lookup=value_lookup)

    def _resolve_canonicalization(
        self,
        *,
        time_limit_seconds: float,
        budgets: TwoStageBudget,
        deterministic: bool,
        stage_one_values: Optional[Dict[int, int]],
        stage_one_objective_value: Optional[float],
        label: str,
    ) -> CanonicalizationOutcome:
        """Decide whether stage 2 runs at all, and run it if so.

        Stage 2 is skipped when ``deterministic=False`` — performance mode makes
        no determinism promise (clause 3.12) and its recorded parameter block is
        asserted unchanged — and when stage 1 returned neither ``OPTIMAL`` nor
        ``FEASIBLE``, because there is then no solution to canonicalise and no
        ``V*`` to lock.
        """
        if not deterministic or budgets.stage_two is None:
            return CanonicalizationOutcome(
                status=CANONICALIZATION_SKIPPED_PERFORMANCE_MODE,
                adopted=False,
                detail="deterministic=False makes no determinism promise",
            )
        if stage_one_values is None or stage_one_objective_value is None:
            return CanonicalizationOutcome(
                status=CANONICALIZATION_SKIPPED_NO_STAGE_1_SOLUTION,
                adopted=False,
                detail="stage 1 returned neither OPTIMAL nor FEASIBLE",
            )
        if self.primary_objective_expr is None or self.tiebreak_objective_expr is None:
            return CanonicalizationOutcome(
                status=CANONICALIZATION_SKIPPED_NO_EXPRESSIONS,
                adopted=False,
                detail="set_objective did not publish P-expr / T-expr",
            )
        return self._canonicalize_stage_one_solution(
            time_limit_seconds=time_limit_seconds,
            stage_budget=budgets.stage_two,
            stage_one_values=stage_one_values,
            stage_one_objective_value=stage_one_objective_value,
            label=label,
        )

    def _add_decision_strategy(self, deterministic: bool = True) -> None:
        """Prefer a canonical first branch. A hint, not a mandate.

        Two strategies, both in canonical ``(well, rig)`` order:

        * the assignment ``BoolVar``s — ``CHOOSE_FIRST`` / ``SELECT_MAX_VALUE``:
          branch on the variables in order and try **1** (assign the well)
          before **0** (drop it);
        * the start-time ``IntVar``s — ``CHOOSE_FIRST`` / ``SELECT_MIN_VALUE``:
          branch in order and try the **earlier** start before the later one.

        **What this buys.** ``search_branching`` stays ``AUTOMATIC_SEARCH``
        (see ``_configure_solver_for_determinism``), so CP-SAT consults these
        strategies for the first descent and is then free to diverge. That makes
        the addition cheap, and it is deliberately *not* a correctness
        mechanism: the schedule was already reproducible run-to-run after tasks
        3-5. What it improves is the *incumbent a truncated run happens to be
        holding* when the deterministic budget expires — first branch biased
        towards "assigned, as early as possible" rather than towards whatever
        the automatic heuristic reached first. Clause 2.7 requires this be
        measured rather than assumed; the measurement lives in the task 7 notes.

        **Why the order is already canonical.** No sorting happens here.
        ``preprocess_data`` sorts ``wells_df`` and ``rigs_df`` on
        ``["name", "id"]`` with ``kind="stable"`` (task 5.2), and
        ``setup_variables`` then populates ``self.assignments`` and
        ``self.start_times`` with wells in the outer loop and rigs in the inner
        one. Python dicts preserve insertion order, so iterating them *is* the
        canonical (well, rig) order. This is the same load-bearing property the
        extraction loop relies on — do not re-sort either dict here, or the two
        orders can drift apart.

        **Stage 2 needs no second call.** ``_canonicalize_stage_one_solution``
        solves the *same* ``self.model`` object with a second ``CpSolver``; it
        adds the ``P-expr == V*`` equality and swaps the objective but never
        rebuilds the model. Search strategies live on the model proto, so both
        stages inherit these two automatically. Calling this again for stage 2
        would append duplicate strategies rather than replace them.

        **Performance mode gets nothing.** Clause 3.12 promises the performance
        block does not move, and its preservation golden carries no exemption —
        a strategy there would change both the model proto and, under
        ``PORTFOLIO_SEARCH``, plausibly the schedule. The canonical-incumbent
        goal is a determinism goal, so the strategies are scoped to the
        deterministic path.
        """
        if not deterministic:
            logger.debug(
                "Decision strategy not added: performance mode keeps its "
                "pre-fix model proto (clause 3.12)."
            )
            return

        assert self.model is not None, "Model must be initialized"

        # Iteration order == insertion order == canonical (well, rig). See the
        # docstring: this is inherited from preprocess_data's sort, not redone.
        assignment_vars = list(self.assignments.values())
        start_time_vars = list(self.start_times.values())

        if not assignment_vars:
            logger.warning(
                "Decision strategy not added: no assignment variables exist, "
                "so there is nothing to order."
            )
            return

        # Try to assign before dropping.
        self.model.AddDecisionStrategy(
            assignment_vars, cp_model.CHOOSE_FIRST, cp_model.SELECT_MAX_VALUE
        )
        # Try earlier before later.
        self.model.AddDecisionStrategy(
            start_time_vars, cp_model.CHOOSE_FIRST, cp_model.SELECT_MIN_VALUE
        )

        logger.info(
            "Decision strategy added: 2 strategies in canonical (well, rig) "
            f"order — {len(assignment_vars)} assignment BoolVars "
            f"(CHOOSE_FIRST/SELECT_MAX_VALUE), {len(start_time_vars)} start-time "
            "IntVars (CHOOSE_FIRST/SELECT_MIN_VALUE). Advisory under "
            "AUTOMATIC_SEARCH; inherited by stage 2 via the shared model."
        )

    # --------------------------
    # Constraints
    # --------------------------
    def add_constraints(self) -> None:
        """Constraints as in iDRS_main: assignment, NoOverlap, windows, RTD, compatibility."""
        logger.info("Adding constraints...")
        
        # Type narrowing for Pylance
        assert self.model is not None, "Model must be initialized before adding constraints"
        
        # 1) Each well assigned to at most one rig; track unassigned via indicator
        self.unassigned_vars = []
        self.high_priority_unassigned = []
        for _, w in self.wells_df.iterrows():
            wid = w["name"]
            rig_assigns = [self.assignments[(wid, r["name"])] for _, r in self.rigs_df.iterrows()]
            self.model.Add(sum(rig_assigns) <= 1)

            is_assigned = self.model.NewBoolVar(f"well_assigned_{wid}")
            self.model.Add(sum(rig_assigns) == 1).OnlyEnforceIf(is_assigned)
            self.model.Add(sum(rig_assigns) == 0).OnlyEnforceIf(is_assigned.Not())
            self.unassigned_vars.append(is_assigned.Not())
            if str(w.get("priority", "MEDIUM")).upper() == "HIGH":
                self.high_priority_unassigned.append(is_assigned.Not())

        # 2) No overlap on a rig
        for _, r in self.rigs_df.iterrows():
            rid = r["name"]
            self.model.AddNoOverlap([self.intervals[(w["name"], rid)] for _, w in self.wells_df.iterrows()])

        # 3) Rig availability windows
        for _, r in self.rigs_df.iterrows():
            rid = r["name"]
            r_start = int((r["start_date"].date() - self.base_start_date).days)
            r_end = int((r["end_date"].date() - self.base_start_date).days)
            for _, w in self.wells_df.iterrows():
                wid = w["name"]
                a = self.assignments[(wid, rid)]
                self.model.Add(self.start_times[(wid, rid)] >= r_start).OnlyEnforceIf(a)
                self.model.Add(self.end_times[(wid, rid)] <= r_end).OnlyEnforceIf(a)

        # 4) Well RTD
        for _, w in self.wells_df.iterrows():
            wid = w["name"]
            try:
                rtd = int((pd.Timestamp(w["rtd"]).date() - self.base_start_date).days)
            except Exception:
                rtd = 0
            for _, r in self.rigs_df.iterrows():
                rid = r["name"]
                a = self.assignments[(wid, rid)]
                self.model.Add(self.start_times[(wid, rid)] >= rtd).OnlyEnforceIf(a)

        # 5) Capability compatibility (hard forbids)
        for _, w in self.wells_df.iterrows():
            for _, r in self.rigs_df.iterrows():
                wid = w["name"]; rid = r["name"]
                if int(r["rig_capacity_hp"]) < int(w["rig_capacity_required_hp"]):
                    self.model.Add(self.assignments[(wid, rid)] == 0); continue
                if float(r["drilling_capacity_m"]) < float(w["depth"]):
                    self.model.Add(self.assignments[(wid, rid)] == 0); continue
                if float(r["bop_stack"]) < float(w["bop_stack"]):
                    self.model.Add(self.assignments[(wid, rid)] == 0); continue
                if str(w.get("tds_requirement", "N")).upper() == "Y" and str(r.get("tds_availability", "N")).upper() != "Y":
                    self.model.Add(self.assignments[(wid, rid)] == 0); continue

        # 6) Financial Year constraints - wells must START within the FY period
        # Note: Wells can FINISH after FY end if they started before it (to accommodate drilling duration)
        if self.fy_start_date is not None or self.fy_end_date is not None:
            logger.info(f"Adding Financial Year constraints: start={self.fy_start_date}, end={self.fy_end_date}")
            
            # Calculate FY boundaries as day indices relative to base_start_date
            fy_start_day = None
            fy_end_day = None
            
            if self.fy_start_date is not None:
                fy_start_day = max(0, int((self.fy_start_date - self.base_start_date).days))
                logger.info(f"FY start day (relative): {fy_start_day}")
            
            if self.fy_end_date is not None:
                fy_end_day = int((self.fy_end_date - self.base_start_date).days)
                logger.info(f"FY end day (relative): {fy_end_day}")
            
            # Apply FY constraints to all well-rig assignments
            for _, w in self.wells_df.iterrows():
                wid = w["name"]
                for _, r in self.rigs_df.iterrows():
                    rid = r["name"]
                    a = self.assignments[(wid, rid)]
                    
                    # Well must start on or after FY start date
                    if fy_start_day is not None:
                        self.model.Add(self.start_times[(wid, rid)] >= fy_start_day).OnlyEnforceIf(a)
                    
                    # Well must START on or before FY end date (key constraint)
                    # Note: We do NOT constrain end_times, allowing drilling to continue past FY end
                    if fy_end_day is not None:
                        self.model.Add(self.start_times[(wid, rid)] <= fy_end_day).OnlyEnforceIf(a)
            
            logger.info("Financial Year constraints added.")

        logger.info("Core constraints added.")

    def add_ilm_constraints(self) -> None:
        """Circuit-based rig routing with ILM gap enforcement.
        
        Replaces the previous pairwise ordering approach (O(wells² × rigs) order
        variables with weak propagation) with a circuit constraint per rig.
        
        Each rig is modelled as a route:
            depot → Well A → Well B → Well C → depot
        
        The AddCircuit constraint efficiently determines the optimal well sequence
        on each rig. ILM gap constraints are enforced only between directly
        consecutive wells in the route (not between all pairs), which is both
        more efficient and more correct.
        
        Uses pre-calculated ILM days from Data Management norms.
        """
        logger.info("Adding circuit-based ILM routing constraints using Data Management norms...")
        
        assert self.model is not None, "Model must be initialized before adding ILM constraints"
        
        if self.distance_matrix.empty:
            logger.warning("Distance matrix is empty; ILM gaps will be zero.")
        
        well_names = list(self.wells_df["name"])
        n_wells = len(well_names)
        
        total_arcs = 0
        total_gap_constraints = 0
        
        for _, r in self.rigs_df.iterrows():
            rid = r["name"]
            ilm_matrix = self.ilm_days_matrix.get(rid)
            
            # Circuit nodes: 0 = depot (rig start/end), 1..n = wells
            arcs: list = []
            
            # Depot self-arc: rig has no wells assigned at all
            depot_idle = self.model.NewBoolVar(f"depot_idle_{rid}")
            arcs.append((0, 0, depot_idle))
            
            for i, wi_name in enumerate(well_names):
                wi_node = i + 1  # node index (1-based for wells)
                ai = self.assignments[(wi_name, rid)]
                
                # Self-arc: well NOT assigned to this rig → excluded from circuit
                skip_i = self.model.NewBoolVar(f"skip_{wi_name}_{rid}")
                arcs.append((wi_node, wi_node, skip_i))
                # Link: skip_i == 1 iff well is NOT assigned to this rig
                self.model.Add(skip_i == 1).OnlyEnforceIf(ai.Not())
                self.model.Add(skip_i == 0).OnlyEnforceIf(ai)
                
                # Arc: depot → well i (well i is FIRST on this rig)
                first_i = self.model.NewBoolVar(f"first_{wi_name}_{rid}")
                arcs.append((0, wi_node, first_i))
                
                # Arc: well i → depot (well i is LAST on this rig)
                last_i = self.model.NewBoolVar(f"last_{wi_name}_{rid}")
                arcs.append((wi_node, 0, last_i))
                
                # Arcs: well i → well j (well j directly follows well i)
                for j, wj_name in enumerate(well_names):
                    if i == j:
                        continue
                    wj_node = j + 1
                    
                    arc_ij = self.model.NewBoolVar(f"arc_{wi_name}_{wj_name}_{rid}")
                    arcs.append((wi_node, wj_node, arc_ij))
                    
                    # Store arc variable for reuse in objective (ILM cost)
                    self.circuit_arcs[(wi_name, wj_name, rid)] = arc_ij
                    
                    # Get ILM gap from pre-calculated matrix (Data Management norms)
                    if ilm_matrix is not None and not ilm_matrix.empty:
                        try:
                            gap = int(float(ilm_matrix.loc[wi_name, wj_name]))
                        except (KeyError, ValueError):
                            gap = 0
                    else:
                        if not self.distance_matrix.empty:
                            try:
                                dist = float(self.distance_matrix.loc[wi_name, wj_name])
                            except KeyError:
                                dist = 0.0
                        else:
                            dist = 0.0
                        gap = int(self._get_ilm_days(dist))
                    
                    # Enforce ILM gap: if arc active, well j starts after well i ends + gap
                    if gap > 0:
                        ei = self.end_times[(wi_name, rid)]
                        sj = self.start_times[(wj_name, rid)]
                        self.model.Add(sj >= ei + gap).OnlyEnforceIf(arc_ij)
                        total_gap_constraints += 1
                    
                    total_arcs += 1
            
            # Add circuit constraint for this rig
            self.model.AddCircuit(arcs)
        
        logger.info(
            f"Circuit-based ILM routing added: {len(self.rigs_df)} rigs, "
            f"{total_arcs} inter-well arcs, {total_gap_constraints} ILM gap constraints"
        )

    # --------------------------
    # Objective
    # --------------------------
    def set_objective(self) -> None:
        """
        Lexicographic objective for deterministic, optimal drilling schedules.
        
        Priority order (strictly enforced via dynamically-computed Big-M):
          1. MAXIMISE number of assigned wells  (primary)
          2. MINIMISE total cost               (secondary – drilling + ILM)
          3. MINIMISE project duration          (tertiary)
          4. TIE-BREAK with start-time sum      (quaternary – determinism)
        
        Implementation:
            model.Minimize(
                BIG_M_WELLS   * num_unassigned
              + BIG_M_HP_UNA  * num_high_priority_unassigned
              + 1             * total_cost
              + DURATION_WT   * project_end
              + 1             * start_time_sum
            )
        
        BIG_M_WELLS is computed from the actual data so that dropping any single
        well can never be offset by cost or duration improvements.  This guarantees
        the solver will never trade a well for cost.
        """
        logger.info("Setting lexicographic objective (maximise wells > minimise cost > minimise duration)…")
        
        assert self.model is not None, "Model must be initialised before setting objective"
        
        # ================================================================
        # 1. ILM transition costs (using circuit arc variables)
        # ================================================================
        # Reuse arc variables from circuit-based ILM routing.
        # Each arc (i → j on rig) = 1 iff well j directly follows well i,
        # so ILM cost is only charged for consecutive well pairs (correct).
        ilm_cost_terms = []
        for w1 in self.wells_df["name"]:
            for w2 in self.wells_df["name"]:
                if w1 == w2:
                    continue
                if not self.distance_matrix.empty:
                    try:
                        dist = float(self.distance_matrix.loc[w1, w2])
                    except KeyError:
                        dist = 0.0
                else:
                    dist = 0.0
                for _, r in self.rigs_df.iterrows():
                    rid = r["name"]
                    arc_var = self.circuit_arcs.get((w1, w2, rid))
                    if arc_var is not None:
                        cost = float(r["ilm_cost_fixed"]) + float(r["ilm_cost_per_km"]) * dist
                        if cost > 0:
                            ilm_cost_terms.append(arc_var * int(cost))

        # ================================================================
        # 2. Drilling costs per assignment
        # ================================================================
        drilling_cost_terms = []
        for _, w in self.wells_df.iterrows():
            wid = w["name"]
            dur = int(w["duration"])
            for _, r in self.rigs_df.iterrows():
                rid = r["name"]
                daily_cost = float(r.get("daily_cost_inr", 0) or 0)
                drilling_cost = int(daily_cost * dur)
                drilling_cost_terms.append(self.assignments[(wid, rid)] * drilling_cost)

        # ================================================================
        # 3. Project-end tracking
        # ================================================================
        self.project_end = self.model.NewIntVar(0, self.horizon, "project_end")
        for (_, _), e in self.end_times.items():
            self.model.Add(self.project_end >= e)

        # ================================================================
        # 4. Assigned / unassigned well counts
        # ================================================================
        num_wells = len(self.wells_df)

        num_unassigned = self.model.NewIntVar(0, num_wells, "num_unassigned")
        self.model.Add(num_unassigned == sum(self.unassigned_vars))

        num_high_unassigned = self.model.NewIntVar(0, num_wells, "num_high_unassigned")
        if self.high_priority_unassigned:
            self.model.Add(num_high_unassigned == sum(self.high_priority_unassigned))
        else:
            self.model.Add(num_high_unassigned == 0)

        num_assigned = self.model.NewIntVar(0, num_wells, "num_assigned")
        self.model.Add(num_assigned == num_wells - num_unassigned)

        # ================================================================
        # 5. Compute Big-M dynamically from data bounds
        # ================================================================
        # Upper-bound on total cost change from any single assignment:
        #   max_single_drilling = max(daily_cost) * max(duration)
        #   max_single_ilm      = max(ilm_cost_fixed + ilm_cost_per_km * max_dist)
        # With circuit-based ILM routing each well has exactly one incoming
        # arc, so max total ILM = num_wells × max_single_ilm (linear, not n²).
        # BIG_M_WELLS must exceed the sum of ALL secondary+tertiary terms
        # so that removing one well is never worthwhile.
        
        max_daily_cost = max(
            (float(r.get("daily_cost_inr", 0) or 0) for _, r in self.rigs_df.iterrows()),
            default=0,
        )
        max_duration = max(
            (int(w.get("duration", 0) or 0) for _, w in self.wells_df.iterrows()),
            default=0,
        )
        max_drilling_one = max_daily_cost * max_duration
        
        # Maximum single-pair ILM cost
        if not self.distance_matrix.empty:
            max_dist = float(self.distance_matrix.max().max())
        else:
            max_dist = 0.0
        max_ilm_fixed = max(
            (float(r.get("ilm_cost_fixed", 0) or 0) for _, r in self.rigs_df.iterrows()),
            default=0,
        )
        max_ilm_per_km = max(
            (float(r.get("ilm_cost_per_km", 0) or 0) for _, r in self.rigs_df.iterrows()),
            default=0,
        )
        max_ilm_one = max_ilm_fixed + max_ilm_per_km * max_dist  # single transition
        
        # Worst-case total cost across ALL wells + ILM transitions.
        # With circuit-based ILM routing each assigned well has exactly one
        # incoming arc, so the total ILM transitions = num_wells (not n²/2).
        max_total_cost = int(
            num_wells * max_drilling_one
            + num_wells * max_ilm_one
        )
        
        # Duration contribution upper bound
        DURATION_WEIGHT = max(1, int(max_daily_cost * 0.2))   # ~20 % of one rig-day
        max_duration_contribution = DURATION_WEIGHT * self.horizon
        
        # Tie-break upper bounds
        # Sub-tier 4a: prefer earlier start times (dominates 4b)
        # Sub-tier 4b: prefer lexicographic rig-well ordering (finest tie-breaker)
        num_rigs = len(self.rigs_df)
        num_pairs = num_wells * num_rigs
        
        # Rig-well ordering weight is 1; start-time weight is also 1.
        # Both are epsilon tie-breakers that deterministically resolve ties
        # without inflating the LP relaxation or the Big-M.
        # Previously START_TIME_WEIGHT was num_pairs+1 (=391) to dominate
        # rig_well_order, but that inflated tiebreak contribution to ~69M
        # which was ~2.5% of Big-M and directly caused the ~1.7% optimality
        # gap.  With weight 1 the max tiebreak is ~330K (0.01% of Big-M)
        # so the solver can prove optimality much faster.
        RIG_WELL_ORDER_WEIGHT = 1
        START_TIME_WEIGHT = 1
        
        max_start_tiebreak = START_TIME_WEIGHT * self.horizon * num_pairs
        # Loose by a factor of num_rigs — the tight bound is num_wells x
        # num_pairs, since each well contributes at most one active assignment.
        # Deliberately NOT tightened here: this expression is a coefficient of
        # BIG_M_WELLS and therefore of the stage-1 objective, which has to stay
        # byte-identical to today's or requests that are already correct return a
        # different objective_value. Measured on the preservation scenario:
        # tightening it moved objective_value 698,525,729 -> 698,525,679 and
        # changed the model fingerprint, with the schedule itself unchanged. The
        # tight bound *is* used where it matters — deriving W1 for stage 2, via
        # max_rig_well_order() — and padding Big-M costs only solve speed, which
        # design decision 3 lists as separate work.
        max_order_tiebreak = RIG_WELL_ORDER_WEIGHT * num_pairs * num_pairs
        max_tiebreak = max_start_tiebreak + max_order_tiebreak
        
        # BIG_M must exceed ALL secondary + tertiary + quaternary combined
        # Add 1 so that the preference is strict.
        BIG_M_WELLS = int(max_total_cost + max_duration_contribution + max_tiebreak) + 1
        
        # Extra penalty for high-priority unassigned (10 % of well Big-M — always
        # dominates cost but doesn't interfere with the well-count tier)
        BIG_M_HP_EXTRA = max(1, BIG_M_WELLS // 10)
        
        # Safety floor: never let Big-M be trivially small
        BIG_M_WELLS = max(BIG_M_WELLS, 10_000_000)
        BIG_M_HP_EXTRA = max(BIG_M_HP_EXTRA, 1_000_000)
        
        logger.info(
            f"Lexicographic weights computed from data: "
            f"BIG_M_WELLS={BIG_M_WELLS:,}, BIG_M_HP_EXTRA={BIG_M_HP_EXTRA:,}, "
            f"DURATION_WEIGHT={DURATION_WEIGHT:,}, START_TIME_WEIGHT={START_TIME_WEIGHT}, "
            f"RIG_WELL_ORDER_WEIGHT={RIG_WELL_ORDER_WEIGHT}"
        )

        # ================================================================
        # 6. Composite objective  (single Minimize call)
        # ================================================================
        # Equivalent to lexicographic:
        #   max assigned_wells  →  min unassigned * BIG_M
        #   then min cost       →  + cost * 1
        #   then min duration   →  + project_end * DURATION_WEIGHT
        #   then determinism    →  + start_time_sum * START_TIME_WEIGHT
        #                         + rig_well_order * RIG_WELL_ORDER_WEIGHT
        
        start_time_sum = sum(sv for sv in self.start_times.values())

        # Deterministic rig-well ordering preference:
        # Wells and rigs are already sorted by name in preprocess_data().
        # Assign a canonical index to each (well, rig) pair so that the
        # solver consistently prefers lower well-index and lower rig-index
        # assignments when all higher-priority tiers are tied.
        rig_well_order_terms = []
        self.rig_well_order_index = {}
        for w_idx, (_, w) in enumerate(self.wells_df.iterrows()):
            wid = w["name"]
            for r_idx, (_, r) in enumerate(self.rigs_df.iterrows()):
                rid = r["name"]
                order_index = w_idx * num_rigs + r_idx
                self.rig_well_order_index[(wid, rid)] = order_index
                rig_well_order_terms.append(
                    self.assignments[(wid, rid)] * order_index
                )
        rig_well_order = sum(rig_well_order_terms)

        # ── P-expr: exactly the expression this model has always minimised ──
        # Bound to a name only so stage 2 can lock it as an equality. The terms,
        # their order and their weights are unchanged, so the proto CP-SAT sees
        # is byte-identical to the single-stage code's and stage 1's Big-M, LP
        # relaxation and proof difficulty are untouched.
        primary_objective = (
            # ── Tier 1: maximise well assignments ─────────────────
            BIG_M_WELLS   * num_unassigned
            + BIG_M_HP_EXTRA * num_high_unassigned
            
            # ── Tier 2: minimise total cost (drilling + ILM) ─────
            + 1 * (sum(drilling_cost_terms) + sum(ilm_cost_terms))
            
            # ── Tier 3: minimise project duration ─────────────────
            + DURATION_WEIGHT * self.project_end
            
            # ── Tier 4a: tie-break — prefer earlier starts ────────
            + START_TIME_WEIGHT * start_time_sum
            
            # ── Tier 4b: tie-break — prefer canonical rig-well order
            + RIG_WELL_ORDER_WEIGHT * rig_well_order
        )

        # ── T-expr: the stage-2 tie-break objective ────────────────────────
        # W1 dominates max(rig_well_order) so the two tiers form a hierarchy
        # instead of trading off. This expression is never minimised in stage 1
        # and contributes nothing to stage 1's proto — the weights exist only
        # inside the canonicalising solve, which has no Big-M in its objective.
        stage_two_start_weight, stage_two_order_weight = tiebreak_weights(
            num_wells, num_rigs
        )
        tiebreak_objective = (
            stage_two_start_weight * start_time_sum
            + stage_two_order_weight * rig_well_order
        )

        self.primary_objective_expr = primary_objective
        self.tiebreak_objective_expr = tiebreak_objective
        self.tiebreak_weights = (stage_two_start_weight, stage_two_order_weight)

        logger.info(
            f"Stage-2 tie-break weights: W1={stage_two_start_weight:,} "
            f"(> max(rig_well_order)={max_rig_well_order(num_wells, num_rigs):,}), "
            f"W2={stage_two_order_weight}, stage-2 objective max ~"
            f"{stage_two_start_weight * self.horizon * num_pairs:,}"
        )

        self.model.Minimize(primary_objective)
        
        logger.info("Lexicographic objective set (with deterministic tie-breakers).")

    # --------------------------
    # Actuals support (re-scheduling)
    # --------------------------
    def _apply_actuals_duration_adjustments(self, fixed_actuals: List[Dict[str, Any]]) -> None:
        """If both actual start and end are provided for a well, adjust duration to match actuals.

        This ensures interval size (duration) matches the fixed dates when we later pin start/end.
        """
        if not fixed_actuals:
            return
        name_to_idx = {str(row["name"]): idx for idx, row in self.wells_df.reset_index().iterrows()}
        for rec in fixed_actuals:
            well = str(rec.get("well"))
            astart = rec.get("actual_start_date")
            aend = rec.get("actual_end_date")
            if not well or not astart or not aend:
                continue
            try:
                s = pd.to_datetime(astart).date()
                e = pd.to_datetime(aend).date()
                dur = (e - s).days + 1
                if dur > 0 and well in name_to_idx:
                    self.wells_df.loc[self.wells_df["name"] == well, "duration"] = int(dur)
            except Exception:
                logger.warning("Could not adjust duration for well %s with actuals %s-%s", well, astart, aend)

    def apply_actual_constraints(self, fixed_actuals: List[Dict[str, Any]]) -> None:
        """Pin assignments/times for wells with provided actual dates.

        fixed_actuals: list of dicts with keys:
          - well: str (well name)
          - rig: str (rig name)
          - actual_start_date: date/str (optional)
          - actual_end_date: date/str (optional)
        """
        if not fixed_actuals:
            return

        logger.info("Applying actual constraints for %d records", len(fixed_actuals))
        
        # Type narrowing for Pylance
        assert self.model is not None, "Model must be initialized before applying actual constraints"

        for rec in fixed_actuals:
            well = str(rec.get("well"))
            rig = str(rec.get("rig"))
            if not well or not rig:
                continue

            # Pin selection to this rig
            if (well, rig) in self.assignments:
                self.model.Add(self.assignments[(well, rig)] == 1)
            # For all other rigs, forbid this well
            for _, r in self.rigs_df.iterrows():
                rid = r["name"]
                if rid == rig:
                    continue
                if (well, rid) in self.assignments:
                    self.model.Add(self.assignments[(well, rid)] == 0)

            # Convert dates to day indices
            s_day = None
            e_day = None
            if rec.get("actual_start_date"):
                try:
                    s_date = pd.to_datetime(rec["actual_start_date"]).date()
                    s_day = int((s_date - self.base_start_date).days)
                except Exception:
                    s_day = None
            if rec.get("actual_end_date"):
                try:
                    e_date = pd.to_datetime(rec["actual_end_date"]).date()
                    # end_days in model is exclusive end, we store end_date as inclusive; align with extract logic
                    e_day = int((e_date - self.base_start_date).days) + 1
                except Exception:
                    e_day = None

            if (well, rig) in self.start_times and s_day is not None:
                self.model.Add(self.start_times[(well, rig)] == s_day)
            if (well, rig) in self.end_times and e_day is not None:
                self.model.Add(self.end_times[(well, rig)] == e_day)

    def solve_with_actuals(self, fixed_actuals: List[Dict[str, Any]], time_limit_seconds: int = 300, deterministic: bool = True) -> Dict[str, Any]:
        """Re-run optimization while pinning actuals (start/end) and using same core logic.
        
        Args:
            fixed_actuals: List of dicts with keys: well, rig, actual_start_date, actual_end_date
            time_limit_seconds: Maximum solver time (default 300s; use 1800s for production)
            deterministic: If True (default), use single-threaded for full reproducibility.
                          If False, use multi-threaded for faster solutions.
        """
        logger.info("Solving with actuals, count=%d, deterministic=%s", 
                   len(fixed_actuals) if fixed_actuals else 0, deterministic)

        # Sort fixed_actuals by (well, rig) for deterministic constraint ordering
        if fixed_actuals:
            fixed_actuals = sorted(fixed_actuals, key=lambda a: (a.get('well', ''), a.get('rig', '')))

        # Normalize and compute distance matrix
        self.preprocess_data()

        # Adjust durations if both actual dates are given
        self._apply_actuals_duration_adjustments(fixed_actuals)

        # Build model
        self.setup_variables()

        # Core constraints and objective
        self.add_constraints()

        # Pin actuals (after core constraints, before sequencing/objective)
        self.apply_actual_constraints(fixed_actuals)

        # Sequencing and objective
        self.add_ilm_constraints()
        self.set_objective()

        # Type narrowing for Pylance
        assert self.model is not None, "Model must be initialized"
        assert self.solver is not None, "Solver must be initialized"

        # Add explicit decision strategy for deterministic variable ordering
        self._add_decision_strategy(deterministic=deterministic)

        # Same two stages as solve(), so SEM re-optimization
        # (sem_views.py:1125-1131) and the locked-actuals endpoint inherit the
        # canonical selection (clauses 3.10, 3.11).
        #
        # Stage 2 cannot move a pinned actual: apply_actual_constraints has
        # already added the start/end equalities to this model, stage 2 runs on
        # the same model, and it only ever *adds* the P-expr == V* equality and
        # replaces the objective. A pin is a hard constraint in both stages, so
        # it constrains stage 2's feasible set exactly as it constrained
        # stage 1's.
        return self._run_two_stage_solve(
            time_limit_seconds, deterministic, "solve_with_actuals"
        )

    def analyze_infeasible_solution(self, fixed_actuals: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze why the solution is infeasible and provide detailed reasons."""
        analysis = {
            "status": "INFEASIBLE_ANALYSIS",
            "failure_reasons": [],
            "constraint_violations": [],
            "recommendations": []
        }

        # Check for common infeasibility causes
        if not fixed_actuals:
            analysis["failure_reasons"].append("No fixed actuals provided")
            return analysis

        # Analyze each fixed actual for potential conflicts
        for rec in fixed_actuals:
            well_name = str(rec.get("well", ""))
            rig_name = str(rec.get("rig", ""))
            actual_start = rec.get("actual_start_date")
            actual_end = rec.get("actual_end_date")

            if not well_name or not rig_name:
                analysis["failure_reasons"].append(f"Invalid well/rig specification: well={well_name}, rig={rig_name}")
                continue

            # Check if well exists
            well_row = self.wells_df[self.wells_df["name"] == well_name]
            if well_row.empty:
                analysis["failure_reasons"].append(f"Well '{well_name}' not found in current schedule")
                continue

            # Check if rig exists
            rig_row = self.rigs_df[self.rigs_df["name"] == rig_name]
            if rig_row.empty:
                analysis["failure_reasons"].append(f"Rig '{rig_name}' not found in current schedule")
                continue

            well_data = well_row.iloc[0]
            rig_data = rig_row.iloc[0]

            # Check compatibility constraints
            violations = []
            if int(rig_data["rig_capacity_hp"]) < int(well_data["rig_capacity_required_hp"]):
                violations.append(f"Horsepower mismatch: Rig {rig_name} has {rig_data['rig_capacity_hp']}HP but well {well_name} requires {well_data['rig_capacity_required_hp']}HP")

            if float(rig_data["drilling_capacity_m"]) < float(well_data["depth"]):
                violations.append(f"Depth capability mismatch: Rig {rig_name} can drill {rig_data['drilling_capacity_m']}m but well {well_name} is {well_data['depth']}m deep")

            if float(rig_data["bop_stack"]) < float(well_data["bop_stack"]):
                violations.append(f"BOP Stack mismatch: Rig {rig_name} has {rig_data['bop_stack']} but well {well_name} requires {well_data['bop_stack']}")

            if str(well_data.get("tds_requirement", "N")).upper() == "Y" and str(rig_data.get("tds_availability", "N")).upper() != "Y":
                violations.append(f"TDS requirement mismatch: Well {well_name} requires TDS but rig {rig_name} doesn't have it")

            if violations:
                analysis["constraint_violations"].extend(violations)

            # Check date constraints
            try:
                if actual_start:
                    start_date = pd.to_datetime(actual_start).date()
                    rig_start = pd.to_datetime(rig_data["start_date"]).date()
                    rig_end = pd.to_datetime(rig_data["end_date"]).date()
                    well_rtd = pd.to_datetime(well_data["rtd"]).date()

                    if start_date < rig_start:
                        violations.append(f"Actual start date {start_date} is before rig {rig_name} availability start {rig_start}")
                    
                    if start_date > rig_end:
                        violations.append(f"Actual start date {start_date} is after rig {rig_name} availability end {rig_end}")

                    if start_date < well_rtd:
                        violations.append(f"Actual start date {start_date} is before well {well_name} RTD {well_rtd}")

                if actual_end:
                    end_date = pd.to_datetime(actual_end).date()
                    rig_end = pd.to_datetime(rig_data["end_date"]).date()
                    
                    if end_date > rig_end:
                        violations.append(f"Actual end date {end_date} is after rig {rig_name} availability end {rig_end}")

                if actual_start and actual_end:
                    start_date = pd.to_datetime(actual_start).date()
                    end_date = pd.to_datetime(actual_end).date()
                    duration = (end_date - start_date).days + 1
                    original_duration = int(well_data["duration"])
                    
                    if duration <= 0:
                        violations.append(f"Invalid duration: Actual end date {end_date} is not after start date {start_date}")
                    elif abs(duration - original_duration) > original_duration * 0.5:  # More than 50% difference
                        violations.append(f"Duration mismatch: Actual duration {duration} days differs significantly from planned {original_duration} days")

            except Exception as e:
                violations.append(f"Date parsing error for well {well_name}: {str(e)}")

            if violations:
                analysis["constraint_violations"].extend(violations)

        # Generate recommendations
        if analysis["constraint_violations"]:
            analysis["recommendations"].append("Review the compatibility between selected rigs and wells")
            analysis["recommendations"].append("Check if actual dates fall within rig availability windows")
            analysis["recommendations"].append("Verify that actual dates respect well RTD requirements")
            analysis["recommendations"].append("Consider adjusting actual dates or selecting different rigs")
        
        if not analysis["failure_reasons"] and not analysis["constraint_violations"]:
            analysis["failure_reasons"].append("The combination of fixed actuals creates scheduling conflicts with other wells")
            analysis["recommendations"].append("Try fixing fewer actuals at once to identify specific conflicts")
            analysis["recommendations"].append("Check if there's sufficient rig availability for remaining wells")

        return analysis

    # --------------------------
    # Solve & extract
    # --------------------------
    def solve(self, time_limit_seconds: int = 300, minimum_solve_time_seconds: Optional[int] = None, deterministic: bool = True) -> Dict[str, Any]:
        """
        Run the optimizer to create a drilling schedule.
        
        For simplicity and to ensure re-runs are correct, the solve() method
        runs the full pipeline (preprocess -> setup_variables -> add_constraints -> 
        add_ilm_constraints -> set_objective) before calling the CP-SAT solver.
        This makes solve idempotent and safe to call multiple times.
        
        Args:
            time_limit_seconds: Maximum time for solver in seconds (default 300).
                               Deterministic mode needs more time since it runs single-threaded.
                               Recommended: 300-600s for typical problems, 1800s for large ones.
            minimum_solve_time_seconds: Deprecated, kept for compatibility
            deterministic: If True (default), use single-threaded mode with fixed search
                          strategy for fully reproducible results (same input → same output).
                          If False, use multi-threaded mode for faster solutions.
                          
        Returns:
            Dict with schedule results, assignments, costs, and metrics
        """
        logger.info(f"Solving: time_limit={time_limit_seconds}s, deterministic={deterministic}")

        # ensure inputs normalized and distance matrix ready
        self.preprocess_data()

        # rebuild model & variables to avoid stale constraints on re-run
        self.setup_variables()

        # add constraints and objective
        self.add_constraints()
        self.add_ilm_constraints()
        self.set_objective()

        # Type narrowing for Pylance
        assert self.model is not None, "Model must be initialized"
        assert self.solver is not None, "Solver must be initialized"

        # Add explicit decision strategy for deterministic variable ordering
        self._add_decision_strategy(deterministic=deterministic)

        # Stage 1 (today's objective, today's V*) then stage 2 (canonicalising
        # tie-break). See _run_two_stage_solve.
        result = self._run_two_stage_solve(time_limit_seconds, deterministic, "solve")
        
        # Log optimality warning if not proven optimal
        if self.status == cp_model.FEASIBLE:
            logger.warning(
                "Schedule NOT proven optimal (FEASIBLE only). "
                f"Solve time: {self.solve_time_seconds:.1f}s / {time_limit_seconds}s limit. "
                "Consider increasing time_limit_seconds for optimality proof."
            )
        elif self.status == cp_model.OPTIMAL:
            logger.info(
                f"Schedule PROVEN OPTIMAL in {self.solve_time_seconds:.1f}s. "
                f"Optimality gap: {result.get('optimality_gap_percent', 0):.4f}%"
            )
        
        return result

    def _provenance_payload(self) -> Dict[str, Any]:
        """The determinism provenance block, identical in both result branches.

        Built in one place and splatted into both ``self.results`` dicts rather
        than written out twice. The two branches (solved / not solved) have
        drifted apart before — the failure branch is the one nobody looks at —
        and provenance that is present only when a run succeeded is useless for
        diagnosing the runs that did not.

        Every value is read off the instance; nothing is recomputed here. A
        helper that re-derived, say, the stop classification could agree with
        itself while production's own classification was wrong.

        Nulls are meaningful and are preserved rather than defaulted:

        * ``model_fingerprint_canonical`` is ``None`` when stage 2 was skipped
          (performance mode, or stage 1 not OPTIMAL/FEASIBLE) — distinct from
          stage 2 having run and produced the same proto, which cannot happen.
        * ``deterministic_budget`` and ``wall_backstop_seconds`` are ``None`` on
          the performance path, which is granted no work budget at all.
        * ``canonicalization_status`` is ``None`` when stage 2 never ran, as
          opposed to one of the ``CANONICALIZATION_*`` outcomes.
        """
        classification = self.stop_classification
        stop_fields: Dict[str, Any] = (
            classification.as_dict()
            if classification is not None
            else {
                "stop_reason": None,
                "deterministic_stop": None,
                "deterministic_time_used": None,
                "deterministic_budget": None,
                "wall_backstop_seconds": None,
            }
        )

        solver_fingerprint = (
            compute_solver_fingerprint(self.solver.parameters)
            if self.solver is not None
            else None
        )

        return {
            # Identifies the question. Recorded before stage 2 mutates the model,
            # so this is the fingerprint of the request as posed.
            "model_fingerprint": self.model_fingerprint,
            # Identifies the stage-2 question. None when stage 2 was skipped.
            "model_fingerprint_canonical": self.model_fingerprint_stage_two,
            # Identifies the machinery. See compute_solver_fingerprint.
            "solver_fingerprint": solver_fingerprint,
            **stop_fields,
            # Which of the two stages decided the schedule. Stage 2's objective
            # VALUE is deliberately absent: it is a tie-break index and means
            # nothing to the business.
            "canonicalization_status": (
                self.canonicalization.status if self.canonicalization else None
            ),
        }

    def _log_provenance(self, provenance: Dict[str, Any]) -> None:
        """One line tying the stop reason to the work actually done.

        Additive: every pre-existing log line is untouched (clause 3.5). What
        this adds over ``_record_stop_classification``'s line is the *payload*
        view — the two fingerprints alongside the stop reason — so a support log
        contains everything needed to decide whether two runs are comparable
        before anyone opens the database.
        """
        budget = provenance.get("deterministic_budget")
        used = provenance.get("deterministic_time_used")
        if budget:
            consumed = f"{used:.4f} of {budget:.4f} units ({used / budget:.1%})"
        elif used is not None:
            consumed = f"{used:.4f} units (no work budget — performance path)"
        else:
            consumed = "not recorded"

        logger.info(
            "Determinism provenance: stop_reason=%s deterministic_stop=%s, "
            "deterministic_time %s, wall backstop=%s, canonicalization=%s, "
            "model_fingerprint=%s, model_fingerprint_canonical=%s, "
            "solver_fingerprint=%s",
            provenance.get("stop_reason"),
            provenance.get("deterministic_stop"),
            consumed,
            provenance.get("wall_backstop_seconds"),
            provenance.get("canonicalization_status"),
            provenance.get("model_fingerprint"),
            provenance.get("model_fingerprint_canonical"),
            provenance.get("solver_fingerprint"),
        )

    def _extract_solution(
        self,
        time_limit_seconds: float = 60,
        value_lookup: Optional[Dict[int, int]] = None,
    ) -> Dict[str, Any]:
        """Extract solution from solver with comprehensive metrics for validation.

        ``value_lookup`` is an optional ``{variable index: value}`` snapshot to
        read the schedule out of, instead of asking ``self.solver``. That is how
        the two-stage solve keeps its two sources straight:

        * **Metrics** — ``objective_value``, ``best_bound``, ``optimality_gap``,
          ``solver_status``, ``is_optimal`` — always describe **stage 1**. They
          come from ``self.stage_one_metrics`` and ``self.status``, both captured
          from stage 1. Stage 2's objective is a tie-break index with no business
          meaning, so it must never appear here.
        * **Variable values** — the assignments, start days and end days — come
          from **stage 2** when stage 2 succeeded, otherwise from stage 1.

        ``None`` means "read ``self.solver``", which is the single-stage
        behaviour and is also stage 1's, since stage 2 runs on its own solver.
        """
        # Type narrowing for Pylance
        assert self.solver is not None, "Solver must be initialized"

        value_of = self._value_reader(value_lookup)
        
        status_name = self.solver.StatusName(self.status) if hasattr(self.solver, "StatusName") else str(self.status)
        logger.info(f"Solver status: {status_name}")
        
        # Explicit optimality verification
        if self.status == cp_model.FEASIBLE:
            logger.warning(
                "Solver returned FEASIBLE (not OPTIMAL). The solver likely stopped "
                "early due to the time limit — the result may not be the true optimum. "
                "Consider increasing time_limit_seconds or using solve_validated()."
            )
        elif self.status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            logger.warning(f"Solver did not find a solution. Status: {status_name}")

        assignments: List[Dict[str, Any]] = []
        total_drilling_cost = 0.0
        
        # Extract solver metrics for validation
        solve_time = getattr(self, 'solve_time_seconds', 0.0)
        objective_value = None
        best_bound = None
        optimality_gap = None
        
        if self.status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            # Metrics come from STAGE 1, captured before stage 2 existed. The
            # fallback path (no captured metrics) is the single-stage behaviour
            # and reads the same numbers off self.solver, which is stage 1's
            # solver; the capture is preferred so provenance is explicit rather
            # than incidental.
            if self.stage_one_metrics is not None:
                objective_value = self.stage_one_metrics.get("objective_value")
                best_bound = self.stage_one_metrics.get("best_bound")
                optimality_gap = self.stage_one_metrics.get("optimality_gap")
            else:
                try:
                    objective_value = self.solver.ObjectiveValue()
                    best_bound = self.solver.BestObjectiveBound()
                    # Standard MIP gap: divide by |objective|, not |bound|.
                    # Clamp best_bound to 0 because this is a pure-minimisation
                    # model where every objective term >= 0 (the true optimum is
                    # always >= 0).  CP-SAT's LP relaxation of Big-M models can
                    # produce deeply negative bounds before convergence, which
                    # inflates the gap to millions of percent.
                    clamped_bound = max(best_bound, 0.0)
                    denom = max(abs(objective_value), 1e-10)
                    optimality_gap = abs(objective_value - clamped_bound) / denom
                except Exception as e:
                    logger.warning(f"Could not extract objective metrics: {e}")
            
            # Do NOT replace this with a set or a re-sort. Dict insertion order
            # here IS the canonical (well, rig) order — setup_variables inserts
            # in sorted well-then-rig order — and it decides the order rows are
            # emitted in, which feeds sequence_order derivation downstream. A
            # refactor to an unordered container would silently reintroduce the
            # non-determinism this whole spec removes.
            for (wid, rid), a in self.assignments.items():
                if value_of(a) == 1:
                    w = self.wells_df.loc[self.wells_df["name"] == wid].iloc[0]
                    r = self.rigs_df.loc[self.rigs_df["name"] == rid].iloc[0]
                    s_day = value_of(self.start_times[(wid, rid)])
                    e_day = value_of(self.end_times[(wid, rid)])
                    start_date = self.base_start_date + timedelta(days=s_day)
                    end_date = self.base_start_date + timedelta(days=e_day - 1)

                    drilling_cost = float(r.get("daily_cost_inr", 0) or 0) * int(w["duration"])
                    total_drilling_cost += drilling_cost

                    assignments.append(
                        {
                            "rig": rid,
                            "well": wid,
                            "well_start_day": s_day,
                            "well_end_day": e_day,
                            "well_start_date": start_date,
                            "well_end_date": end_date,
                            "duration_days": int(w["duration"]),
                            "drilling_cost_inr": drilling_cost,
                        }
                    )

            assignments = self._calculate_ilm_costs(assignments)

            project_end_day = value_of(self.project_end) if self.project_end is not None else 0
            project_end_date = self.base_start_date + timedelta(days=project_end_day)

            assigned_wells = {a["well"] for a in assignments}
            unassigned = [w for w in self.wells_df["name"].tolist() if w not in assigned_wells]
            
            # Count unique rigs used
            rigs_used = set(a["rig"] for a in assignments)
            total_ilm_cost = sum(a.get("ilm_cost", 0) for a in assignments)
            total_cost = total_drilling_cost + total_ilm_cost
            
            # Log summary for debugging
            logger.info(
                f"Solution: {len(assignments)} wells assigned, {len(unassigned)} unassigned, "
                f"{len(rigs_used)} rigs used, total_cost={total_cost:,.0f} INR"
            )

            # Compute deterministic schedule hash for verification
            hash_content = json.dumps(
                [(a["rig"], a["well"], a["well_start_day"], a["well_end_day"]) for a in sorted(assignments, key=lambda x: (x["rig"], x["well"]))],
                sort_keys=True,
            )
            schedule_hash = hashlib.sha256(hash_content.encode()).hexdigest()[:16]

            self.results = {
                "status": status_name,
                "solver_status": status_name,
                "solver_status_code": self.status,
                "solve_time_seconds": solve_time,
                "time_limit_seconds": time_limit_seconds,
                "objective_value": objective_value,
                "best_bound": best_bound,
                "optimality_gap": optimality_gap,
                "optimality_gap_percent": (optimality_gap * 100) if optimality_gap is not None else None,
                "is_optimal": self.status == cp_model.OPTIMAL,
                "is_feasible": self.status in (cp_model.OPTIMAL, cp_model.FEASIBLE),
                "schedule_hash": schedule_hash,
                "assignments": assignments,
                "unassigned_wells": unassigned,
                "wells_assigned_count": len(assignments),
                "wells_unassigned_count": len(unassigned),
                "wells_total_count": len(self.wells_df),
                "rigs_used_count": len(rigs_used),
                "rigs_total_count": len(self.rigs_df),
                "total_drilling_cost": total_drilling_cost,
                "total_ilm_cost": total_ilm_cost,
                "total_cost": total_cost,
                "project_end_day": project_end_day,
                "project_end_date": project_end_date,
                # Financial Year constraints applied
                "fy_start_date": self.fy_start_date,
                "fy_end_date": self.fy_end_date,
                "fy_constrained": self.fy_start_date is not None or self.fy_end_date is not None,
                # Determinism provenance (task 8.1). Same block in both branches.
                **self._provenance_payload(),
            }
        else:
            self.results = {
                "status": status_name,
                "solver_status": status_name,
                "solver_status_code": self.status,
                "solve_time_seconds": solve_time,
                "time_limit_seconds": time_limit_seconds,
                "objective_value": None,
                "best_bound": None,
                "optimality_gap": None,
                "optimality_gap_percent": None,
                "is_optimal": False,
                "is_feasible": False,
                "assignments": [],
                "unassigned_wells": self.wells_df["name"].tolist(),
                "wells_assigned_count": 0,
                "wells_unassigned_count": len(self.wells_df),
                "wells_total_count": len(self.wells_df),
                "rigs_used_count": 0,
                "rigs_total_count": len(self.rigs_df),
                "total_drilling_cost": 0,
                "total_ilm_cost": 0,
                "total_cost": 0,
                "project_end_day": 0,
                "project_end_date": None,
                # Financial Year constraints applied
                "fy_start_date": self.fy_start_date,
                "fy_end_date": self.fy_end_date,
                "fy_constrained": self.fy_start_date is not None or self.fy_end_date is not None,
                # Determinism provenance (task 8.1). Same block in both branches:
                # a run that failed to produce a schedule is exactly when the
                # stop reason and the fingerprints matter most.
                **self._provenance_payload(),
            }

        self._log_provenance(self.results)
        return self.results

    # ==============================================================================
    # VALIDATED SOLVE - STRICT OPTIMALITY CERTIFICATION
    # ==============================================================================
    
    def solve_validated(
        self,
        time_limit_seconds: int = 600,
        require_optimal: bool = True,
        require_dual_run: bool = True,
        max_gap_tolerance: float = 0.0,
        fixed_actuals: Optional[List[Dict[str, Any]]] = None,
    ) -> CertifiedSchedule:
        """
        Solve with strict optimality validation and certification.
        
        This is the RECOMMENDED method for production use. It ensures that only
        provably optimal schedules are accepted, with full audit trail.
        
        Args:
            time_limit_seconds: Maximum solve time in seconds (default 600s = 10 minutes).
                               No upper limit enforced - use longer times for complex problems.
                               Recommended: 600-1800s for production, 60-120s for testing.
            require_optimal: Reject if solver status != OPTIMAL (default True)
            require_dual_run: Run solver twice to verify determinism (default True)
            max_gap_tolerance: Maximum acceptable optimality gap (default 0.0 = zero)
            fixed_actuals: Optional list of actual dates to pin (for re-optimization)
        
        Returns:
            CertifiedSchedule with validation result and management report
            
        Usage:
            # Production (10 minutes for optimality proof)
            certified = scheduler.solve_validated(time_limit_seconds=600)
            
            # Complex schedules (30 minutes)
            certified = scheduler.solve_validated(time_limit_seconds=1800)
            
            if certified.certified_optimal:
                # Safe to use schedule
                save_schedule(certified.schedule_data)
            else:
                # Handle rejection
                print(certified.validation_result.summary)
                print(certified.validation_result.recommendations)
        """
        import time
        
        logger.info(
            f"Starting validated solve: time_limit={time_limit_seconds}s, "
            f"require_optimal={require_optimal}, require_dual_run={require_dual_run}"
        )
        
        # Create validator with specified criteria
        validator = OptimalityValidator(
            require_optimal_status=require_optimal,
            require_zero_gap=max_gap_tolerance == 0.0,
            require_dual_run=require_dual_run,
            max_gap_tolerance=max_gap_tolerance,
        )
        
        # Store original data state for dual-run
        original_rigs_df = self.rigs_df.copy()
        original_wells_df = self.wells_df.copy()
        
        try:
            # === PRIMARY RUN ===
            logger.info("=== PRIMARY RUN ===")
            if fixed_actuals:
                primary_result = self.solve_with_actuals(fixed_actuals, time_limit_seconds)
            else:
                primary_result = self.solve(time_limit_seconds)
            
            # Extract metrics from primary run
            assert self.solver is not None, "Solver must be initialized"
            assert self.status is not None, "Status must be set after solve"
            primary_metrics = validator.extract_solver_metrics(
                self.solver,
                self.status,  # type: ignore[arg-type]
                self.solve_time_seconds,
                time_limit_seconds,
            )
            
            # Validate primary run
            primary_passed, rejection_reasons = validator.validate_single_run(primary_metrics)
            
            logger.info(
                f"Primary run: status={primary_metrics.status_name}, "
                f"gap={primary_metrics.optimality_gap}, passed={primary_passed}"
            )
            
            # === DUAL-RUN VERIFICATION ===
            dual_run_passed = False
            verification_metrics = None
            schedule_hash_primary = None
            schedule_hash_verification = None
            
            if require_dual_run and primary_passed:
                logger.info("=== VERIFICATION RUN ===")
                
                # Reset state for clean second run
                self.rigs_df = original_rigs_df.copy()
                self.wells_df = original_wells_df.copy()
                self.model = None
                self.solver = None
                
                # Run again with identical inputs
                if fixed_actuals:
                    verification_result = self.solve_with_actuals(fixed_actuals, time_limit_seconds)
                else:
                    verification_result = self.solve(time_limit_seconds)
                
                assert self.solver is not None, "Solver must be initialized"
                assert self.status is not None, "Status must be set after solve"
                verification_metrics = validator.extract_solver_metrics(
                    self.solver,
                    self.status,  # type: ignore[arg-type]
                    self.solve_time_seconds,
                    time_limit_seconds,
                )
                
                # Compare schedules
                dual_run_passed, schedule_hash_primary, schedule_hash_verification = \
                    validator.validate_dual_run(primary_result, verification_result)
                
                logger.info(
                    f"Dual-run verification: passed={dual_run_passed}, "
                    f"hash_match={schedule_hash_primary == schedule_hash_verification}"
                )
                
                if not dual_run_passed:
                    rejection_reasons.append(RejectionReason.DETERMINISM_FAILURE)
            
            elif require_dual_run and not primary_passed:
                logger.info("Skipping dual-run verification: primary run failed")
            
            # === FINAL DECISION ===
            is_accepted = primary_passed and (not require_dual_run or dual_run_passed)
            
            # Create validation result
            validation_result = validator.create_validation_result(
                is_accepted=is_accepted,
                primary_metrics=primary_metrics,
                rejection_reasons=rejection_reasons,
                dual_run_enabled=require_dual_run,
                dual_run_passed=dual_run_passed,
                verification_metrics=verification_metrics,
                schedule_hash_primary=schedule_hash_primary,
                schedule_hash_verification=schedule_hash_verification,
            )
            
            # Create certified schedule
            certified = CertifiedSchedule(
                schedule_data=primary_result,
                validation_result=validation_result,
            )
            
            # Log result
            if is_accepted:
                logger.info(f"✓ Schedule CERTIFIED OPTIMAL: {certified.certification_id}")
            else:
                reasons_str = ", ".join([r.value for r in rejection_reasons])
                logger.warning(f"✗ Schedule REJECTED: {reasons_str}")
            
            return certified
            
        except Exception as e:
            logger.error(f"Validation error: {e}")
            
            # Create error result
            error_metrics = SolverMetrics(
                status_code=-1,
                status_name="ERROR",
                wall_time_seconds=0,
                time_limit_seconds=time_limit_seconds,
            )
            
            validation_result = validator.create_validation_result(
                is_accepted=False,
                primary_metrics=error_metrics,
                rejection_reasons=[RejectionReason.VALIDATION_ERROR],
                dual_run_enabled=require_dual_run,
                dual_run_passed=False,
            )
            validation_result.summary = f"Validation error: {str(e)}"
            validation_result.recommendations = ["Check input data and constraints", "Review error logs"]
            
            return CertifiedSchedule(
                schedule_data={"status": "ERROR", "assignments": [], "unassigned_wells": []},
                validation_result=validation_result,
            )
    
    def solve_with_actuals_validated(
        self,
        fixed_actuals: List[Dict[str, Any]],
        time_limit_seconds: int = 600,
        require_optimal: bool = True,
        require_dual_run: bool = True,
        max_gap_tolerance: float = 0.0,
    ) -> CertifiedSchedule:
        """
        Re-optimize with actual dates pinned, with full optimality validation.
        
        Convenience wrapper for solve_validated with fixed_actuals.
        No upper limit on time_limit_seconds - use as much time as needed for optimality proof.
        """
        return self.solve_validated(
            time_limit_seconds=time_limit_seconds,
            require_optimal=require_optimal,
            require_dual_run=require_dual_run,
            max_gap_tolerance=max_gap_tolerance,
            fixed_actuals=fixed_actuals,
        )
    
    def get_validation_summary(self) -> Dict[str, Any]:
        """
        Get validation summary from the last solve operation.
        
        Returns summary of solver metrics useful for understanding schedule quality.
        """
        if not self.results:
            return {"error": "No solve results available"}
        
        return {
            "status": self.results.get("solver_status", "Unknown"),
            "is_optimal": self.results.get("is_optimal", False),
            "is_feasible": self.results.get("is_feasible", False),
            "solve_time_seconds": round(self.results.get("solve_time_seconds", 0), 2),
            "time_limit_seconds": self.results.get("time_limit_seconds", 0),
            "objective_value": self.results.get("objective_value"),
            "best_bound": self.results.get("best_bound"),
            "optimality_gap_percent": self.results.get("optimality_gap_percent"),
            "wells_assigned": len(self.results.get("assignments", [])),
            "wells_unassigned": len(self.results.get("unassigned_wells", [])),
        }

    # --------------------------
    # Output helpers
    # --------------------------
    def export_to_dataframe(self, assignments: List[Dict[str, Any]]) -> pd.DataFrame:
        if not assignments:
            return pd.DataFrame(columns=["rig", "well", "well_start_date", "well_end_date", "duration_days", "drilling_cost_inr", "ilm_cost"])
        df = pd.DataFrame(assignments).sort_values(["rig", "well_start_date"]).reset_index(drop=True)
        return df

    # --------------------------
    # Cost/gap helpers
    # --------------------------
    def _get_ilm_days(self, distance_km: float, base_ilm_distance: float = 20.0, base_ilm_days: int = 10) -> int:
        """
        Fallback ILM days calculation using simple formula.
        
        This is only used when Data Management norms are not available.
        The primary ILM calculation is done via _calculate_ilm_days_matrix() using
        actual RigBuildingNorm and RigBuildingAdjustment rules.
        
        Args:
            distance_km: Distance between wells in kilometers
            base_ilm_distance: Distance threshold before extra days are added (default 20km)
            base_ilm_days: Base ILM days (default 10)
        
        Returns:
            Calculated ILM days as integer
        """
        if distance_km <= base_ilm_distance:
            return int(base_ilm_days)
        extra = math.ceil((distance_km - base_ilm_distance) / 10.0)
        return int(base_ilm_days + max(0, extra))
    
    def _get_ilm_days_from_matrix(self, well1: str, well2: str, rig: str) -> int:
        """
        Get ILM days from pre-calculated matrix for a specific rig and well pair.
        
        Uses Data Management norms if available, otherwise falls back to simple formula.
        
        Args:
            well1: Name of first well
            well2: Name of second well  
            rig: Name of rig
        
        Returns:
            ILM days as integer
        """
        ilm_matrix = self.ilm_days_matrix.get(rig)
        
        if ilm_matrix is not None and not ilm_matrix.empty:
            try:
                from typing import cast
                return int(cast(float, ilm_matrix.loc[well1, well2]))
            except KeyError:
                pass
        
        # Fallback to simple formula
        if not self.distance_matrix.empty:
            try:
                from typing import cast
                dist = float(cast(float, self.distance_matrix.loc[well1, well2]))
                return self._get_ilm_days(dist)
            except KeyError:
                pass
        
        return 0

    def _get_ilm_cost(self, distance_km: float, rig_row: pd.Series) -> float:
        return float(rig_row["ilm_cost_fixed"]) + float(rig_row["ilm_cost_per_km"]) * float(distance_km)

    def _calculate_ilm_costs(self, assignments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Calculate ILM costs and add ILM days to assignment records.
        
        Uses the pre-calculated ILM days matrix from Data Management norms.
        """
        if not assignments:
            return assignments

        by_rig: Dict[str, List[Dict[str, Any]]] = {}
        for a in assignments:
            by_rig.setdefault(a["rig"], []).append(a)

        total_ilm_cost = 0.0
        total_ilm_days = 0.0
        for rid in sorted(by_rig.keys()):
            arr = by_rig[rid]
            # Total sort key: start date alone can tie, and the tie would then be
            # resolved by list order.  Per-rig AddNoOverlap makes same-rig
            # start-date ties impossible today, so this is latent-hazard removal.
            arr.sort(key=lambda x: (x["well_start_date"], x["well"]))
            rig_row = self.rigs_df.loc[self.rigs_df["name"] == rid].iloc[0]
            
            # Get ILM matrix for this rig (from Data Management norms)
            ilm_matrix = self.ilm_days_matrix.get(rid)
            
            for i in range(1, len(arr)):
                prev = arr[i - 1]["well"]
                curr = arr[i]["well"]
                
                # Get ILM days from pre-calculated matrix
                ilm_days = 0.0
                if ilm_matrix is not None and not ilm_matrix.empty:
                    try:
                        from typing import cast
                        ilm_days = float(cast(float, ilm_matrix.loc[prev, curr]))
                    except KeyError:
                        pass
                
                # Get distance from matrix
                if not self.distance_matrix.empty:
                    from typing import cast
                    dist = float(cast(float, self.distance_matrix.loc[prev, curr]))
                else:
                    dist = 0.0
                
                cost = self._get_ilm_cost(dist, rig_row)
                arr[i]["ilm_cost"] = cost
                arr[i]["ilm_days"] = ilm_days
                arr[i]["ilm_distance_km"] = round(dist, 2)
                arr[i]["ilm_from_well"] = prev
                total_ilm_cost += cost
                total_ilm_days += ilm_days

        self.results["total_ilm_cost"] = total_ilm_cost
        self.results["total_ilm_days"] = total_ilm_days
        return assignments

    # --------------------------
    # Scenario helper (merge wells for re-run)
    # --------------------------
    def merge_wells_for_scenario(self, current_wells: Any, previous_rejected: Optional[List[Any]]) -> pd.DataFrame:
        """
        Merge current wells visible on Gantt with previously rejected wells to form the
        candidate set for re-running the optimizer.

        - current_wells: list/dict or pandas.DataFrame of wells currently visible on Gantt.
        - previous_rejected: list of well names (strings) or list of dict rows (preferred).
        """
        if pd is None:
            raise ImportError("pandas is required for merge_wells_for_scenario")

        # normalize current
        if isinstance(current_wells, pd.DataFrame):
            cur_df = current_wells.copy()
        else:
            cur_df = pd.DataFrame(list(current_wells))

        if "name" not in cur_df.columns:
            if "well" in cur_df.columns:
                cur_df = cur_df.rename(columns={"well": "name"})
            elif "well_id" in cur_df.columns:
                cur_df = cur_df.rename(columns={"well_id": "name"})
            else:
                cur_df = cur_df.reset_index().rename(columns={"index": "name"})

        rej_df = pd.DataFrame(columns=cur_df.columns)
        if previous_rejected:
            # list of names
            if all(isinstance(x, str) for x in previous_rejected):
                for nm in previous_rejected:
                    if nm in cur_df["name"].astype(str).tolist():
                        continue
                    try:
                        found = self.wells_df.loc[self.wells_df["name"].astype(str) == str(nm)]
                        if not found.empty:
                            rej_df = pd.concat([rej_df, found.iloc[[0]]], ignore_index=True, sort=False)
                        else:
                            rej_df = pd.concat([rej_df, pd.DataFrame([{"name": str(nm), "duration": 1}])], ignore_index=True, sort=False)
                    except Exception:
                        rej_df = pd.concat([rej_df, pd.DataFrame([{"name": str(nm), "duration": 1}])], ignore_index=True, sort=False)
            # list of dicts
            elif all(isinstance(x, dict) for x in previous_rejected):
                rr = pd.DataFrame(previous_rejected)
                if "name" not in rr.columns and "well" in rr.columns:
                    rr = rr.rename(columns={"well": "name"})
                rej_df = pd.concat([rej_df, rr], ignore_index=True, sort=False)
            else:
                # unsupported type -> ignore
                logger.warning("merge_wells_for_scenario: previous_rejected has unsupported element types; ignoring")

        merged = pd.concat([cur_df, rej_df], ignore_index=True, sort=False)
        if "duration" not in merged.columns:
            merged["duration"] = 1
        else:
            merged["duration"] = merged["duration"].fillna(1).astype(int)
            merged.loc[merged["duration"] <= 0, "duration"] = 1

        merged = merged.drop_duplicates(subset=["name"], keep="first").reset_index(drop=True)
        logger.info("merge_wells_for_scenario: merged current(%d) + rejected_added(%d) -> total(%d)", len(cur_df), len(rej_df), len(merged))
        return merged

    def generate_geographical_map(self):
        """Generate geographical map showing rig movement paths"""
        if not self.results or not self.results.get('assignments'):
            return None
            
        try:
            import plotly.graph_objects as go
            import plotly.express as px
        except ImportError:
            logger.error("Plotly is required for map generation")
            return None
            
        assignments = self.results['assignments']
        
        # Convert assignments to DataFrame for easier processing
        output_data = []
        for assignment in assignments:
            output_data.append({
                'Rig': assignment['rig'],
                'Well': assignment['well'],
                'Well Start Date': assignment['well_start_date'],
                'Well End Date': assignment['well_end_date'],
                'Latitude': float(assignment['latitude']),
                'Longitude': float(assignment['longitude']),
                'Duration (days)': assignment['duration'],
                'RTD': assignment['rtd'],
                'required_depth': assignment['depth'],
                'required_hp': assignment['required_hp'],
                'Sequence Order': assignment.get('sequence_order', 1)
            })
        
        if not output_data:
            return None
            
        output_df = pd.DataFrame(output_data)
        
        # Extract unique rigs and assign colors
        rigs = output_df['Rig'].unique()
        rig_colors = px.colors.qualitative.Set1
        if len(rigs) > len(rig_colors):
            rig_colors = px.colors.qualitative.Plotly
        
        # Create a mapping of rig to color
        rig_color_map = {rig: color for rig, color in zip(rigs, rig_colors)}
        
        # Create the geographical plot
        fig = go.Figure()
        
        # Loop through each rig to plot its wells and paths
        for rig in rigs:
            rig_df = output_df[output_df['Rig'] == rig].copy()
            rig_df = rig_df.sort_values(by="Well Start Date")
            
            latitudes = rig_df['Latitude'].tolist()
            longitudes = rig_df['Longitude'].tolist()
            well_names = rig_df['Well'].tolist()
            sequence_numbers = list(range(1, len(well_names) + 1))
            
            # Plot the path of the rig
            fig.add_trace(go.Scattermapbox(
                lat=latitudes, 
                lon=longitudes,
                mode='lines+markers',
                line=dict(width=2, color=rig_color_map[rig]),
                marker=dict(size=10, color=rig_color_map[rig], opacity=0.7),
                text=[f"Well: {well} - Rig: {rig}" for well in well_names],
                hoverinfo='text',
                name=rig
            ))
            
            # Annotate start and end points
            if latitudes and longitudes:
                fig.add_annotation(
                    x=longitudes[0], y=latitudes[0],
                    text=f"Start ({well_names[0]})",
                    showarrow=True, arrowhead=2,
                    ax=20, ay=-30,
                    font=dict(size=10, color="black"),
                    arrowcolor=rig_color_map[rig],
                    bgcolor="white"
                )
                
                fig.add_annotation(
                    x=longitudes[-1], y=latitudes[-1],
                    text=f"End ({well_names[-1]})",
                    showarrow=True, arrowhead=2,
                    ax=20, ay=30,
                    font=dict(size=10, color="black"),
                    arrowcolor=rig_color_map[rig],
                    bgcolor="white"
                )
                
                # Add sequence numbers
                for i, (lat, lon, seq_num, well) in enumerate(zip(latitudes, longitudes, sequence_numbers, well_names)):
                    fig.add_annotation(
                        x=lon, y=lat,
                        text=str(seq_num),
                        showarrow=False,
                        font=dict(size=10, color="black"),
                        bgcolor="white", opacity=0.7,
                        yshift=10 if i % 2 == 0 else -10
                    )
        
        # Plot wells with color coding by rig
        fig.add_trace(go.Scattermapbox(
            lat=output_df['Latitude'], 
            lon=output_df['Longitude'],
            mode='markers',
            marker=dict(size=10, color=output_df['Rig'].map(rig_color_map), opacity=0.7),
            text=output_df.apply(lambda row: f"Well: {row['Well']} - Rig: {row['Rig']}", axis=1),
            hoverinfo='text',
            showlegend=False
        ))
        
        # Set map layout
        fig.update_layout(
            title="Wells by Rig on Map with Rig Paths",
            mapbox=dict(
                style="carto-positron",
                center=dict(
                    lat=output_df['Latitude'].mean(),
                    lon=output_df['Longitude'].mean()
                ),
                zoom=5
            ),
            showlegend=True,
            height=600
        )
        
        return fig.to_html(include_plotlyjs='cdn')
    
    def generate_gantt_chart(self):
        """Generate Gantt chart showing drilling schedule"""
        if not self.results or not self.results.get('assignments'):
            return None
            
        try:
            import plotly.express as px
            import plotly.graph_objects as go
        except ImportError:
            logger.error("Plotly is required for Gantt chart generation")
            return None
            
        assignments = self.results['assignments']
        
        # Convert assignments to DataFrame
        output_data = []
        for assignment in assignments:
            output_data.append({
                'Rig': assignment['rig'],
                'Well': assignment['well'],
                'Well Start Date': assignment['well_start_date'],
                'Well End Date': assignment['well_end_date'],
                'Duration (days)': assignment['duration'],
                'RTD': assignment['rtd'],
                'required_depth': assignment['depth'],
                'required_hp': assignment['required_hp']
            })
        
        if not output_data:
            return None
            
        output_df = pd.DataFrame(output_data)
        
        # Create Gantt chart
        fig = px.timeline(
            output_df,
            x_start="Well Start Date",
            x_end="Well End Date",
            y="Rig",
            color="RTD",
            hover_data=["Well", "Duration (days)", "RTD", "required_depth", "required_hp"],
            title="Drilling Rig Schedule Gantt Chart"
        )
        
        # Update layout
        fig.update_yaxes(autorange="reversed")
        fig.update_layout(
            xaxis_title="Date",
            yaxis_title="Rig",
            height=600,
            margin=dict(l=20, r=20, t=40, b=20)
        )
        
        # Add rig availability bands
        rigs_list = list(output_df["Rig"].unique())
        rig_y_index = {rig: i for i, rig in enumerate(reversed(rigs_list))}
        total_rigs = len(rigs_list)
        
        # Get rig availability data
        for _, rig_data in self.rigs_df.iterrows():
            rig = rig_data["name"]
            start_date = rig_data["start_date"]
            end_date = rig_data["end_date"]
            y_index = rig_y_index.get(rig)
            
            if y_index is not None:
                band_height = 1.0 / total_rigs
                y0 = y_index * band_height
                y1 = y0 + band_height * 0.9
                
                fig.add_shape(
                    type="rect",
                    x0=start_date, x1=end_date,
                    y0=y0, y1=y1,
                    xref="x", yref="paper",
                    fillcolor="lightgreen",
                    opacity=0.35,
                    layer="below",
                    line_width=0
                )
                
                fig.add_annotation(
                    x=start_date, y=rig,
                    text="Available",
                    showarrow=False,
                    yshift=15,
                    font=dict(size=10, color="green"),
                    bgcolor="white",
                    opacity=0.7
                )
        
        return fig.to_html(include_plotlyjs='cdn')