"""Measurement helpers shared by the deterministic-schedule-fix harness.

Nothing in here touches production code.  ``model_fingerprint`` is recomputed
from the retained ``CpModel`` using the *same* expression the optimizer logs at
``scheduler/optimization.py:1735-1738``::

    hashlib.sha256(str(self.model.Proto()).encode()).hexdigest()

so the harness reads the same number that appears in the server log without
needing the payload to carry it (surfacing it in the payload is task 8's job,
not task 1's).

``deterministic_time`` and ``wall_time`` come straight off the ``CpSolver``
instance the scheduler retains after ``Solve()``.  They are the discriminating
measurement for this spec: if ``schedule_hash`` drifts *while*
``deterministic_time`` also drifts, the wall-clock stopping criterion is the
mechanism (design root cause 1).  If ``schedule_hash`` drifts while
``deterministic_time`` is identical, the diagnosis moves to the ordering
hazards (root cause 6) instead.
"""

from __future__ import annotations

import hashlib
import json
import math
import multiprocessing
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from scheduler.optimization import DrillingScheduler, StopClassification

from .cpu_burn import burn
from .factories import Scenario

#: Environment flag gating the CPU-load runs.  Saturating every core is fine on
#: a developer machine and hostile on a shared CI box, so the load test only
#: runs when it is asked for.
CPU_LOAD_ENV_FLAG = "IDRS_TEST_CPU_LOAD"

#: Burner processes per core.  See ``cpu_load`` for why this is 3 and not 1.
CPU_LOAD_OVERSUBSCRIPTION = 3

#: Optional absolute burner count, overriding the ``3 x cores`` default.
#:
#: The default is a deliberate torture level — it exists to expose the defect,
#: not to model a realistic box.  Sizing ``WALL_BACKSTOP_FACTOR`` needs the
#: opposite: contention a production host actually sees.  Setting this to an
#: absolute number of burners (``IDRS_TEST_CPU_LOAD_WORKERS=4``) measures that
#: regime without editing test code.  Unset, nothing changes.
CPU_LOAD_WORKERS_ENV_VAR = "IDRS_TEST_CPU_LOAD_WORKERS"

AssignmentTuple = Tuple[str, str, int, int]


@dataclass
class SolveObservation:
    """One measured solve."""

    run_index: int
    under_load: bool
    schedule_hash: Optional[str]
    model_fingerprint: str
    objective_value: Optional[float]
    solver_status: Optional[str]
    is_optimal: bool
    deterministic_time: float
    wall_time: float
    elapsed_seconds: float
    wells_assigned: int
    total_cost: float
    assignment_tuples: List[AssignmentTuple] = field(default_factory=list)
    results: Dict[str, Any] = field(default_factory=dict, repr=False)
    #: The solver parameters that were actually set for this solve.  Only the
    #: explicitly-set fields, so it is the parameter *block* the code chose
    #: rather than the whole proto's defaults.  Recorded because clause 3.12
    #: (performance mode unchanged) is a claim about this block, not about the
    #: schedule.
    solver_parameters: Dict[str, Any] = field(default_factory=dict, repr=False)
    #: The in-force value of each parameter in ``PARAMETERS_OF_INTEREST``,
    #: including any that were set to their proto default and are therefore
    #: absent from ``solver_parameters``.
    solver_parameters_effective: Dict[str, Any] = field(
        default_factory=dict, repr=False
    )
    #: Why this solve stopped, as the optimizer itself classified it
    #: (``DrillingScheduler.stop_classification``).  Read off the instance, not
    #: recomputed here: a test that recomputed the classification could agree
    #: with itself while the production classification was wrong.  ``None`` if
    #: the solve predates the classification being recorded.
    stop_classification: Optional[StopClassification] = None

    @property
    def stop_reason(self) -> Optional[str]:
        return self.stop_classification.stop_reason if self.stop_classification else None

    @property
    def deterministic_stop(self) -> Optional[bool]:
        return (
            self.stop_classification.deterministic_stop
            if self.stop_classification
            else None
        )

    def summary(self) -> str:
        return (
            f"run={self.run_index} load={'Y' if self.under_load else 'N'} "
            f"status={self.solver_status} hash={self.schedule_hash} "
            f"obj={self.objective_value} det_time={self.deterministic_time:.4f} "
            f"wall={self.wall_time:.2f}s assigned={self.wells_assigned}"
        )


def model_fingerprint(scheduler: DrillingScheduler) -> str:
    """The optimizer's own model-proto fingerprint, for the **stage-1** model.

    Task 4 made recomputing this from ``scheduler.model`` after the solve wrong:
    the canonicalising stage adds ``P-expr == V*``, replaces the objective and
    hints the incumbent, all on the same ``CpModel``, so the post-solve proto is
    stage 2's.  The fingerprint that identifies the request — and the one the
    golden fixture recorded, and the one whose objective value is reported — is
    stage 1's, taken before that mutation.

    So this now *reads* the value the optimizer recorded
    (``DrillingScheduler.model_fingerprint``) rather than recomputing it.  That
    is strictly better as an observation: it checks the number production
    actually logs and will persist, instead of a number the harness derives in
    parallel and could agree with itself about.  The recomputation is kept as a
    fallback for a scheduler that never solved.
    """
    recorded = getattr(scheduler, "model_fingerprint", None)
    if recorded:
        return recorded
    assert scheduler.model is not None, "model must exist after solve()"
    return hashlib.sha256(str(scheduler.model.Proto()).encode()).hexdigest()


#: Key prefix used to park a line of the parameter block that does not parse as
#: ``key: value``.  See ``explicit_solver_parameters``.
UNPARSED_PARAMETER_KEY_PREFIX = "__unparsed_line_"


def _parse_parameter_value(raw: str) -> Any:
    """Coerce one text-format proto value into a JSON-serialisable Python value.

    The forms that actually occur in this parameter block, in the order they
    are tried: ``true``/``false`` -> ``bool``; a quoted string -> ``str``
    without the quotes; an integer literal -> ``int``; a decimal literal ->
    ``float``; anything else -> the raw text.

    "Anything else" is in practice an enum name such as ``AUTOMATIC_SEARCH`` or
    ``FIXED_SEARCH``.  It is kept as the **name** rather than mapped to an
    ordinal: the name is what the spec talks about, it stays readable in the
    golden fixture, and it does not silently change meaning if OR-Tools ever
    renumbers the enum.
    """
    text = raw.strip()
    if text in {"true", "false"}:
        return text == "true"
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        return text[1:-1]
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        pass
    return text


def explicit_solver_parameters(solver) -> Dict[str, Any]:
    """The solver parameters that were explicitly set, as a plain dict.

    This is the parameter *block* ``_configure_solver_for_determinism``
    (``scheduler/optimization.py:905-984``) chose, with none of the hundreds of
    surrounding defaults — which is what makes it a meaningful thing to record
    and to compare between runs.

    It is read out of ``str(solver.parameters)``.  Under ``ortools 9.15.6755``
    ``solver.parameters`` is not a protobuf python message but a pybind11
    wrapper (``ortools.sat.python.cp_model_helper.SatParameters``): it has no
    ``ListFields``, no ``SerializeToString`` and no ``DESCRIPTOR``.  What it
    does have is a ``__str__`` that emits the text-format proto containing one
    ``key: value`` line per field that was set, which carries exactly the same
    information.

    A read-only observation: nothing here assigns to the solver.

    An unrecognised line is parked under ``UNPARSED_PARAMETER_KEY_PREFIX``
    rather than raising, so an OR-Tools upgrade that changes the text format
    shows up loudly in the recorded dict instead of breaking the capture.
    """
    parsed: Dict[str, Any] = {}
    unparsed = 0
    for line in str(solver.parameters).splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        key, separator, value = stripped.partition(":")
        key = key.strip()
        if not separator or not key or " " in key:
            # Not a scalar field line — a nested-message opener such as
            # ``subsolver_params {``, or a format this parser has not seen.
            unparsed += 1
            parsed[f"{UNPARSED_PARAMETER_KEY_PREFIX}{unparsed}"] = stripped
            continue
        parsed[key] = _parse_parameter_value(value)
    return dict(sorted(parsed.items()))


#: Parameters this spec makes claims about, read back by name.
#:
#: This is a deliberate, explicit record rather than a fallback for something
#: ``explicit_solver_parameters`` misses.  Under this OR-Tools build the two
#: agree on any parameter the code set: a field assigned its default value
#: *does* still appear in ``str(solver.parameters)`` — performance mode's
#: ``num_search_workers = 0`` (``scheduler/optimization.py:963``) and
#: ``enumerate_all_solutions: false`` both show up there, verified against the
#: installed 9.15.6755.  What reading by name adds is the in-force value of
#: every parameter the spec argues about, present in the record at a fixed set
#: of keys whether or not the code chose to set it — so a claim like "clause 3.4
#: leaves ``num_search_workers`` at 1" can be asserted against the same key in
#: every observation.
PARAMETERS_OF_INTEREST = (
    "max_time_in_seconds",
    "max_deterministic_time",
    "num_search_workers",
    "random_seed",
    "search_branching",
    "symmetry_level",
    "use_lns",
    "interleave_search",
    "interleave_batch_size",
    "cp_model_presolve",
    "enumerate_all_solutions",
)


def _jsonable_parameter_value(value: Any) -> Any:
    """Coerce one in-force parameter value into a JSON-native one.

    Two of the values read off this pybind wrapper are not JSON types:

    * ``search_branching`` is a ``SatParameters.SearchBranching`` enum object.
      It becomes its **ordinal**.  The ordinal is chosen over the name because
      the pybind enum compares equal to its own integer (``0 ==
      cp_model.AUTOMATIC_SEARCH`` is ``True``), so a recorded ``0`` still
      satisfies an assertion written against ``cp_model.AUTOMATIC_SEARCH``.
      The readable spelling is not lost — ``explicit_solver_parameters``
      records ``search_branching: AUTOMATIC_SEARCH`` by name in the same
      observation.
    * ``max_time_in_seconds`` and ``max_deterministic_time`` default to
      **infinity**, not to zero, and ``json`` writes a bare ``Infinity`` which
      is not valid JSON for any parser outside Python.  Non-finite floats
      become the string the proto text format itself uses (``"inf"``,
      ``"-inf"``, ``"nan"``), which keeps the golden fixture strictly parseable
      and self-describing.
    """
    if isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if math.isnan(value):
            return "nan"
        if math.isinf(value):
            return "inf" if value > 0 else "-inf"
        return value
    inner = getattr(value, "value", None)
    if isinstance(inner, int):
        return int(inner)
    return str(value)


def effective_solver_parameters(solver) -> Dict[str, Any]:
    """The in-force value of every parameter in ``PARAMETERS_OF_INTEREST``."""
    params = solver.parameters
    return {
        name: _jsonable_parameter_value(getattr(params, name))
        for name in PARAMETERS_OF_INTEREST
    }


def derive_sequence_orders(
    assignments: List[Dict[str, Any]],
) -> Dict[Tuple[str, str], int]:
    """``(rig, well) -> sequence_order``, derived the way the save path derives it.

    Mirrors the save path in ``ScheduleViewSet.create_schedule``: group the
    assignments by rig, sort each group on the total key
    ``(well_start_date, well)``, then number from 1.  Task 5.4 made the
    production key total; this replica tracks it.

    This is a *replica* of production logic living in test code, which is
    normally a smell — a replica can agree with itself while disagreeing with
    the real thing.  It is safe here because it is cross-checked:
    ``test_save_path_matches_golden`` drives the real
    ``POST /api/schedules/create_schedule/`` endpoint and asserts the
    ``sequence_order`` values Django actually persisted equal the values this
    function derives.  If the two ever diverge, that test fails.
    """
    by_rig: Dict[str, List[Dict[str, Any]]] = {}
    for assignment in assignments:
        by_rig.setdefault(str(assignment["rig"]), []).append(assignment)

    orders: Dict[Tuple[str, str], int] = {}
    for rig_name, rig_assignments in by_rig.items():
        ordered = sorted(
            rig_assignments, key=lambda a: (a["well_start_date"], str(a["well"]))
        )
        for index, assignment in enumerate(ordered, start=1):
            orders[(rig_name, str(assignment["well"]))] = index
    return orders


def assignment_tuples(results: Dict[str, Any]) -> List[AssignmentTuple]:
    """``(well, rig, start_day, end_day)`` sorted canonically.

    Sorted so the comparison is about the *schedule*, not about the order the
    optimizer happened to emit rows in.
    """
    return sorted(
        (
            str(a["well"]),
            str(a["rig"]),
            int(a["well_start_day"]),
            int(a["well_end_day"]),
        )
        for a in results.get("assignments", [])
    )


def schedule_hash_of(triples) -> str:
    """Reproduce ``_extract_solution``'s schedule hash from raw tuples.

    Mirrors ``scheduler/optimization.py:1852-1856`` exactly: the tuples are
    ``(rig, well, start_day, end_day)`` sorted by ``(rig, well)``, JSON encoded
    with ``sort_keys=True``, SHA-256'd and truncated to 16 hex characters.
    Needed by the tie-enumeration test, which reads variable values straight off
    a solver rather than going through ``_extract_solution``.
    """
    payload = json.dumps(
        [tuple(t) for t in sorted(triples, key=lambda t: (t[0], t[1]))],
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def build_model_with_objective(scenario: Scenario):
    """Run the model-building half of ``solve()`` and capture the objective.

    ``solve()`` (``scheduler/optimization.py:1688``) is
    ``preprocess_data → setup_variables → add_constraints → add_ilm_constraints
    → set_objective`` followed by ``Solve``.  This helper stops before ``Solve``
    and additionally returns the linear expression ``set_objective`` hands to
    ``model.Minimize`` (``:1412-1428``).

    The expression is obtained by shadowing ``Minimize`` on the ``CpModel``
    *instance* for the duration of the call.  That is a read-only observation —
    the real ``Minimize`` still runs, so the model is built exactly as
    production builds it — and it is what lets the tie-enumeration test pin the
    objective to ``V*`` without the optimizer having to expose the expression.

    Returns ``(scheduler, objective_expression)``.
    """
    scheduler = DrillingScheduler(
        [dict(r) for r in scenario.rigs_data],
        [dict(w) for w in scenario.wells_data],
        **scenario.scheduler_kwargs(),
    )
    scheduler.preprocess_data()
    scheduler.setup_variables()
    scheduler.add_constraints()
    scheduler.add_ilm_constraints()

    model = scheduler.model
    assert model is not None
    captured: List[Any] = []
    real_minimize = model.Minimize

    def _spy(expression):
        captured.append(expression)
        return real_minimize(expression)

    model.Minimize = _spy  # type: ignore[method-assign]
    try:
        scheduler.set_objective()
    finally:
        del model.Minimize  # type: ignore[attr-defined]

    if not captured:
        raise AssertionError(
            "set_objective() did not call model.Minimize(); the optimizer's "
            "objective wiring changed and this helper needs updating."
        )
    if captured[0] is not scheduler.primary_objective_expr:
        raise AssertionError(
            "The expression set_objective() passed to Minimize() is not the one "
            "it published as primary_objective_expr. Stage 2 locks the published "
            "expression, so if the two ever differ the equality would pin the "
            "wrong quantity and this helper would measure the wrong tied set."
        )
    return scheduler, captured[0]


def tiebreak_objective_of(scheduler: DrillingScheduler):
    """The T-expr the optimizer's stage 2 minimises.

    Read straight off the scheduler rather than rebuilt here, so the
    tie-enumeration test measures the canonical set production actually selects
    within.  A locally reconstructed copy could agree with itself while the
    production weights had drifted.
    """
    expression = scheduler.tiebreak_objective_expr
    if expression is None:
        raise AssertionError(
            "set_objective() did not publish tiebreak_objective_expr; the "
            "two-stage wiring changed and this helper needs updating."
        )
    return expression


def new_scheduler(scenario: Scenario) -> DrillingScheduler:
    """A **fresh** ``DrillingScheduler`` over copies of the scenario's inputs.

    A fresh instance per run is deliberate: it is what the endpoint does
    (``scheduler/views.py:1953-1959`` constructs one per request), and it means
    any state carried between runs cannot be the explanation for a difference.
    The input dicts are copied so one run cannot mutate the next run's input —
    ``preprocess_data`` rewrites date and duration columns in place.
    """
    return DrillingScheduler(
        [dict(r) for r in scenario.rigs_data],
        [dict(w) for w in scenario.wells_data],
        **scenario.scheduler_kwargs(),
    )


def _observe(
    scheduler: DrillingScheduler,
    results: Dict[str, Any],
    *,
    elapsed: float,
    run_index: int,
    under_load: bool,
) -> SolveObservation:
    """Package one finished solve into a ``SolveObservation``."""
    assert scheduler.solver is not None, "solver must exist after solve()"
    return SolveObservation(
        run_index=run_index,
        under_load=under_load,
        schedule_hash=results.get("schedule_hash"),
        model_fingerprint=model_fingerprint(scheduler),
        objective_value=results.get("objective_value"),
        solver_status=results.get("solver_status"),
        is_optimal=bool(results.get("is_optimal")),
        deterministic_time=float(scheduler.solver.deterministic_time),
        wall_time=float(scheduler.solver.wall_time),
        elapsed_seconds=elapsed,
        wells_assigned=int(results.get("wells_assigned_count", 0) or 0),
        total_cost=float(results.get("total_cost", 0) or 0),
        assignment_tuples=assignment_tuples(results),
        results=results,
        solver_parameters=explicit_solver_parameters(scheduler.solver),
        solver_parameters_effective=effective_solver_parameters(scheduler.solver),
        stop_classification=scheduler.stop_classification,
    )


def solve_once(
    scenario: Scenario,
    *,
    time_limit_seconds: int,
    run_index: int = 0,
    under_load: bool = False,
    deterministic: bool = True,
) -> SolveObservation:
    """Build a fresh ``DrillingScheduler`` and solve the scenario once."""
    scheduler = new_scheduler(scenario)
    started = time.perf_counter()
    results = scheduler.solve(
        time_limit_seconds=time_limit_seconds, deterministic=deterministic
    )
    elapsed = time.perf_counter() - started
    return _observe(
        scheduler,
        results,
        elapsed=elapsed,
        run_index=run_index,
        under_load=under_load,
    )


def solve_with_actuals_once(
    scenario: Scenario,
    fixed_actuals: List[Dict[str, Any]],
    *,
    time_limit_seconds: int,
    run_index: int = 0,
    deterministic: bool = True,
) -> SolveObservation:
    """The same, through ``solve_with_actuals`` (``optimization.py:1514``).

    This is the re-optimization path: the locked-actuals endpoint
    (``scheduler/views.py:2361-2365``) and SEM re-optimization
    (``scheduler/sem_views.py:1125-1131``) both reach the solver this way, so
    clauses 3.10 and 3.11 are claims about this function.
    """
    scheduler = new_scheduler(scenario)
    started = time.perf_counter()
    results = scheduler.solve_with_actuals(
        [dict(a) for a in fixed_actuals],
        time_limit_seconds=time_limit_seconds,
        deterministic=deterministic,
    )
    elapsed = time.perf_counter() - started
    return _observe(
        scheduler,
        results,
        elapsed=elapsed,
        run_index=run_index,
        under_load=False,
    )


# ---------------------------------------------------------------------------
# CPU load
# ---------------------------------------------------------------------------


def requested_cpu_load_workers() -> int:
    """How many burner processes to run when the caller does not say.

    ``IDRS_TEST_CPU_LOAD_WORKERS``, if set, is an **absolute** burner count.
    Unset, the default is three burners per core.  That default is calibrated,
    not guessed: at one burner per core the solver still completed ~60% of its
    idle work and the harness measured no divergence at all.  At 3x it completes
    ~20%, which lands the stop in a materially different place and is what
    actually exposes the defect.  See ``CPU_LOAD_OVERSUBSCRIPTION``.

    Zero is rejected.  A load harness that can be configured down to no load at
    all would let an under-load test pass by measuring an idle machine, which is
    exactly the false pass ``cpu_load``'s liveness check exists to prevent.
    """
    raw = os.environ.get(CPU_LOAD_WORKERS_ENV_VAR, "").strip()
    if not raw:
        return CPU_LOAD_OVERSUBSCRIPTION * (os.cpu_count() or 4)
    try:
        workers = int(raw)
    except ValueError as exc:
        raise ValueError(
            f"{CPU_LOAD_WORKERS_ENV_VAR}={raw!r} is not an integer. It is an "
            "absolute burner-process count, e.g. 4."
        ) from exc
    if workers < 1:
        raise ValueError(
            f"{CPU_LOAD_WORKERS_ENV_VAR}={workers} would establish no CPU load. "
            "Measuring an idle machine would make the under-load determinism "
            "result meaningless; unset the variable instead."
        )
    return workers


@contextmanager
def cpu_load(workers: Optional[int] = None):
    """Saturate the machine's cores for the duration of the block.

    This is the crux of clause 2.3: *same* machine, *different* load, identical
    output.  A wall-clock stopping criterion cannot satisfy that, because the
    amount of search completed inside a fixed wall-clock window shrinks when
    the cores are contended.

    The load is verified rather than assumed — if a child dies on startup the
    block raises instead of quietly measuring an idle machine, which would turn
    the whole test into a false pass.
    """
    if workers is None:
        workers = requested_cpu_load_workers()
    ctx = multiprocessing.get_context("spawn")
    stop_flag = ctx.Value("i", 0)
    procs = [
        ctx.Process(target=burn, args=(stop_flag,), daemon=True) for _ in range(workers)
    ]
    for proc in procs:
        proc.start()
    # Give the children time to spawn, import and actually get scheduled.
    time.sleep(3.0)
    alive = sum(1 for proc in procs if proc.is_alive())
    if alive < workers:
        stop_flag.value = 1
        for proc in procs:
            proc.terminate()
        raise RuntimeError(
            f"CPU load could not be established: only {alive}/{workers} burner "
            "processes are alive. Measuring an idle machine would make the "
            "under-load determinism result meaningless."
        )
    try:
        yield alive
    finally:
        stop_flag.value = 1
        for proc in procs:
            proc.join(timeout=10)
            if proc.is_alive():  # pragma: no cover - defensive
                proc.terminate()
                proc.join(timeout=5)


def cpu_load_enabled() -> bool:
    return os.environ.get(CPU_LOAD_ENV_FLAG, "").strip().lower() in {"1", "true", "yes"}


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def distinct(values) -> List[Any]:
    """Distinct values, order of first appearance, tolerant of unhashables."""
    seen: List[Any] = []
    for value in values:
        if value not in seen:
            seen.append(value)
    return seen


def format_observation_table(observations: List[SolveObservation]) -> str:
    """Human-readable table.  Printed by the harness so a failing run leaves
    the counterexample in the test output rather than only in an assertion
    message."""
    header = (
        f"{'run':>3} {'load':>4} {'status':>9} {'schedule_hash':>18} "
        f"{'objective':>16} {'det_time':>9} {'wall_s':>8} {'assigned':>8} "
        f"{'total_cost':>18} {'stop_reason':>22}"
    )
    lines = [header, "-" * len(header)]
    for obs in observations:
        lines.append(
            f"{obs.run_index:>3} {'Y' if obs.under_load else 'N':>4} "
            f"{str(obs.solver_status):>9} {str(obs.schedule_hash):>18} "
            f"{('%d' % obs.objective_value) if obs.objective_value is not None else 'None':>16} "
            f"{obs.deterministic_time:>9.4f} {obs.wall_time:>8.2f} "
            f"{obs.wells_assigned:>8} {obs.total_cost:>18,.0f} "
            f"{str(obs.stop_reason):>22}"
        )
    return "\n".join(lines)
