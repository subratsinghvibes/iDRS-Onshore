"""Authoritative cross-run determinism check (deterministic-schedule-fix, task 10).

The badge on the schedule detail page is **advisory**: a single solve cannot prove
reproducibility, because proving it means comparing more than one run. This is the
command that actually does the comparison, and it is the check the badge's tooltip
names.

What it does: takes an existing schedule, re-solves its *exact* rig / well /
financial-year / time-limit selection N times, and compares the resulting
``schedule_hash`` values. More than one distinct hash means the requirement is not
met, and the command exits non-zero.

Why it has to exist alongside the test suite: the tests run synthetic scenarios on
whatever machine runs them. This runs **real data on the real host**, which is the
only place the requirement — "same rigs, same wells, same FY, same time limit, same
machine, same schedule" — can actually be verified for a deployment. With
``--under-load`` it also saturates the cores for some of the runs, so the "under
heavy CPU load" half of the criterion is exercised rather than assumed.

Read-only, deliberately and defensively
---------------------------------------
Nothing here writes. ``DrillingScheduler.solve`` is a pure computation over frames
read out of the database, and this command never calls ``save()``, never creates a
``Schedule``, and never touches the row it was pointed at. On top of that the whole
run is wrapped in a transaction that is rolled back unconditionally, so even a
future code path that tried to write could not leave anything behind. That is what
makes it safe to run against production data on the VM.

Usage::

    python manage.py check_determinism --schedule-id <uuid> --runs 5
    python manage.py check_determinism --schedule-id <uuid> --runs 5 --under-load
    python manage.py check_determinism --latest --runs 3
    python manage.py check_determinism --list

Exit codes::

    0   every run produced the same schedule_hash
    1   more than one distinct schedule_hash (the requirement is NOT met)
    2   could not run (no such schedule, no selection recorded, bad arguments)
"""

from __future__ import annotations

import multiprocessing
import time
from typing import Any, Dict, List, Optional

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from scheduler.models import Rig, Schedule, Well, parse_financial_year
from scheduler.optimization import DrillingScheduler

#: Exit code for "the check ran and the answer is no".
EXIT_NOT_DETERMINISTIC = 1
#: Exit code for "the check could not run at all".
EXIT_CANNOT_RUN = 2

#: Default solver time limit when the schedule row does not record one (rows
#: created before migration 0062 have no ``time_limit_seconds``). Matches
#: ``ScheduleCreateSerializer``'s own default so a re-solve of an old row uses the
#: same budget the endpoint would have used.
DEFAULT_TIME_LIMIT_SECONDS = 600


def _burn_cpu(stop_after_seconds: float) -> None:  # pragma: no cover - subprocess
    """Spin until told to stop. The payload for ``--under-load``."""
    deadline = time.monotonic() + stop_after_seconds
    x = 0.0
    while time.monotonic() < deadline:
        # Arithmetic in a tight loop; enough to keep a core busy without
        # allocating and without touching the database.
        for _ in range(100_000):
            x = x * 1.000001 + 1.0


class CpuLoad:
    """Saturate the cores for the duration of a ``with`` block.

    Separate processes rather than threads: the GIL would make threads useless
    for producing real CPU contention, which is the entire point.
    """

    def __init__(self, workers: int, expected_seconds: float):
        self.workers = workers
        # Generous: the burners must outlive the solve, and they are terminated
        # explicitly on the way out.
        self.expected_seconds = max(30.0, expected_seconds * 3)
        self._processes: List[multiprocessing.Process] = []

    def __enter__(self):
        for _ in range(self.workers):
            process = multiprocessing.Process(
                target=_burn_cpu, args=(self.expected_seconds,), daemon=True
            )
            process.start()
            self._processes.append(process)
        return self

    def __exit__(self, *exc_info):
        for process in self._processes:
            if process.is_alive():
                process.terminate()
        for process in self._processes:
            process.join(timeout=5)
        self._processes = []
        return False


class Command(BaseCommand):
    help = (
        "Re-solve an existing schedule's exact selection N times and verify "
        "every run returns the same schedule_hash. Read-only; writes nothing."
    )

    def add_arguments(self, parser):
        target = parser.add_mutually_exclusive_group()
        target.add_argument(
            "--schedule-id",
            dest="schedule_id",
            help="UUID of the schedule whose selection should be re-solved.",
        )
        target.add_argument(
            "--latest",
            action="store_true",
            help="Use the most recently completed schedule instead of an id.",
        )
        target.add_argument(
            "--list",
            action="store_true",
            dest="list_schedules",
            help="List completed schedules that carry a re-solvable selection.",
        )
        parser.add_argument(
            "--runs",
            type=int,
            default=3,
            help="Number of re-solves to compare (default 3, minimum 2).",
        )
        parser.add_argument(
            "--under-load",
            action="store_true",
            dest="under_load",
            help=(
                "Saturate the CPU during the second half of the runs, to verify "
                "the 'under heavy load' half of the requirement on this host."
            ),
        )
        parser.add_argument(
            "--load-workers",
            type=int,
            default=0,
            help=(
                "Burner processes for --under-load (default: cpu_count - 1, so "
                "one core is left for the solve)."
            ),
        )
        parser.add_argument(
            "--time-limit",
            type=int,
            default=None,
            help=(
                "Override the solver time limit. Defaults to the limit recorded "
                "on the schedule, which is what makes the re-solve comparable."
            ),
        )

    # -- helpers ---------------------------------------------------------

    def _list(self) -> None:
        rows = (
            Schedule.objects.filter(status="COMPLETED")
            .order_by("-created_at")
            .values(
                "id",
                "name",
                "financial_year",
                "time_limit_seconds",
                "schedule_hash",
                "stop_reason",
                "created_at",
            )[:25]
        )
        if not rows:
            self.stdout.write("No completed schedules found.")
            return

        self.stdout.write(
            f"{'id':<38} {'created':<17} {'FY':<10} {'T':>6} "
            f"{'hash':<18} {'stop reason':<22} name"
        )
        for row in rows:
            self.stdout.write(
                f"{str(row['id']):<38} "
                f"{row['created_at']:%Y-%m-%d %H:%M} "
                f"{row['financial_year']:<10} "
                f"{str(row['time_limit_seconds'] or '-'):>6} "
                f"{str(row['schedule_hash'] or '-'):<18} "
                f"{str(row['stop_reason'] or 'not recorded'):<22} "
                f"{row['name']}"
            )

    def _resolve_schedule(self, schedule_id: Optional[str], latest: bool) -> Schedule:
        if latest:
            schedule = (
                Schedule.objects.filter(status="COMPLETED")
                .order_by("-created_at")
                .first()
            )
            if schedule is None:
                raise CommandError(
                    "No COMPLETED schedule exists to check. Run an optimization "
                    "first, or pass --schedule-id."
                )
            return schedule

        if not schedule_id:
            raise CommandError(
                "Pass --schedule-id <uuid>, or --latest, or --list to see what "
                "is available."
            )
        try:
            return Schedule.objects.get(id=schedule_id)
        except (Schedule.DoesNotExist, ValueError, TypeError) as exc:
            raise CommandError(f"No schedule with id {schedule_id!r}: {exc}")

    def _selection(self, schedule: Schedule):
        """The exact frames ``create_schedule`` would have built.

        Mirrors the endpoint deliberately, including the ``('name', 'id')``
        ordering and ``.values()`` — a re-solve that fed the optimizer a
        differently-shaped or differently-ordered frame would not be re-solving
        the same request, and a hash mismatch would say nothing about the solver.
        """
        rig_ids = list(schedule.selected_rigs.values_list("rig_id", flat=True))
        well_ids = list(schedule.selected_wells.values_list("well_id", flat=True))

        if not rig_ids or not well_ids:
            raise CommandError(
                f"Schedule {schedule.id} records no rig/well selection "
                f"(rigs={len(rig_ids)}, wells={len(well_ids)}), so its request "
                "cannot be reconstructed. ScheduleRig / ScheduleWell rows are "
                "written by create_schedule; schedules produced by other paths, "
                "or before that tracking existed, cannot be re-solved."
            )

        rigs = Rig.all_objects.filter(id__in=rig_ids).order_by("name", "id")
        wells = Well.all_objects.filter(id__in=well_ids).order_by("name", "id")

        missing_rigs = len(rig_ids) - rigs.count()
        missing_wells = len(well_ids) - wells.count()
        if missing_rigs or missing_wells:
            self.stderr.write(
                self.style.WARNING(
                    f"WARNING: {missing_rigs} rig(s) and {missing_wells} well(s) "
                    "from the original selection no longer exist. The re-solve "
                    "is over what remains, so a hash difference against the "
                    "stored value is expected and is NOT a determinism failure. "
                    "Run-to-run agreement below is still meaningful."
                )
            )

        return list(rigs.values()), list(wells.values())

    def _solve_once(
        self, rigs_data, wells_data, fy_start, fy_end, time_limit: int
    ) -> Dict[str, Any]:
        scheduler = DrillingScheduler(
            [dict(r) for r in rigs_data],
            [dict(w) for w in wells_data],
            fy_start_date=fy_start,
            fy_end_date=fy_end,
        )
        started = time.perf_counter()
        results = scheduler.solve(
            time_limit_seconds=time_limit, deterministic=True
        )
        elapsed = time.perf_counter() - started
        return {
            "schedule_hash": results.get("schedule_hash"),
            "model_fingerprint": results.get("model_fingerprint"),
            "solver_fingerprint": results.get("solver_fingerprint"),
            "objective_value": results.get("objective_value"),
            "stop_reason": results.get("stop_reason"),
            "deterministic_stop": results.get("deterministic_stop"),
            "deterministic_time_used": results.get("deterministic_time_used"),
            "wall_time": elapsed,
            "wells_assigned": results.get("wells_assigned_count"),
            "total_cost": results.get("total_cost"),
        }

    # -- entry point -----------------------------------------------------

    def handle(self, *args, **options):
        if options.get("list_schedules"):
            self._list()
            return

        runs = options["runs"]
        if runs < 2:
            raise CommandError(
                f"--runs must be at least 2 to compare anything (got {runs}). "
                "One run cannot demonstrate reproducibility; that is exactly "
                "why the single-solve badge is only advisory."
            )

        schedule = self._resolve_schedule(
            options.get("schedule_id"), options.get("latest", False)
        )
        time_limit = (
            options.get("time_limit")
            or schedule.time_limit_seconds
            or DEFAULT_TIME_LIMIT_SECONDS
        )

        try:
            fy_start, fy_end = parse_financial_year(schedule.financial_year)
        except (ValueError, TypeError) as exc:
            self.stderr.write(
                self.style.WARNING(
                    f"Could not parse financial year "
                    f"{schedule.financial_year!r} ({exc}); re-solving without FY "
                    "constraints, exactly as create_schedule would."
                )
            )
            fy_start, fy_end = None, None

        under_load = options.get("under_load", False)
        load_workers = options.get("load_workers") or max(
            1, (multiprocessing.cpu_count() or 2) - 1
        )

        observations: List[Dict[str, Any]] = []

        # Belt-and-braces: solve() does not write, and nothing below calls save(),
        # but wrapping the run in a transaction that is always rolled back means
        # this command cannot modify production data even if that changed.
        try:
            with transaction.atomic():
                rigs_data, wells_data = self._selection(schedule)

                self.stdout.write("")
                self.stdout.write("=" * 118)
                self.stdout.write("DETERMINISM CHECK (authoritative cross-run comparison)")
                self.stdout.write("=" * 118)
                self.stdout.write(f"  schedule        : {schedule.name} [{schedule.id}]")
                self.stdout.write(f"  financial year  : {schedule.financial_year} ({fy_start} .. {fy_end})")
                self.stdout.write(f"  selection       : {len(rigs_data)} rigs, {len(wells_data)} wells")
                self.stdout.write(f"  time limit      : {time_limit}s")
                self.stdout.write(f"  runs            : {runs}"
                                  + (f"  (last {runs // 2} under CPU load, "
                                     f"{load_workers} burners)" if under_load else ""))
                self.stdout.write(f"  stored hash     : {schedule.schedule_hash or 'not recorded'}")
                self.stdout.write(f"  stored stop     : {schedule.stop_reason or 'not recorded'}")
                self.stdout.write("")

                header = (
                    f"{'run':>4} {'load':>5} {'schedule_hash':<18} "
                    f"{'objective':>18} {'det used':>9} {'wall (s)':>9} "
                    f"{'asgn':>5} {'stop reason':<22} {'det?':>5}"
                )
                self.stdout.write(header)

                # +1 so exactly ``runs // 2`` runs are loaded, matching the count
                # printed in the header above. Without it the boundary run is
                # loaded too and the header undercounts by one.
                loaded_from = (
                    runs - (runs // 2) + 1 if under_load else runs + 1
                )

                for index in range(1, runs + 1):
                    is_loaded = under_load and index >= loaded_from
                    if is_loaded:
                        with CpuLoad(load_workers, time_limit):
                            observation = self._solve_once(
                                rigs_data, wells_data, fy_start, fy_end, time_limit
                            )
                    else:
                        observation = self._solve_once(
                            rigs_data, wells_data, fy_start, fy_end, time_limit
                        )
                    observation["under_load"] = is_loaded
                    observations.append(observation)

                    objective = observation["objective_value"]
                    self.stdout.write(
                        f"{index:>4} {'Y' if is_loaded else 'N':>5} "
                        f"{str(observation['schedule_hash']):<18} "
                        f"{objective if objective is not None else 0:>18,.0f} "
                        f"{observation['deterministic_time_used'] or 0:>9.4f} "
                        f"{observation['wall_time']:>9.2f} "
                        f"{observation['wells_assigned'] or 0:>5} "
                        f"{str(observation['stop_reason']):<22} "
                        f"{'Y' if observation['deterministic_stop'] else 'N':>5}"
                    )

                # Roll the (empty) transaction back explicitly, so the read-only
                # guarantee is enforced rather than merely intended.
                transaction.set_rollback(True)
        except CommandError:
            raise
        except Exception as exc:  # pragma: no cover - defensive
            raise CommandError(f"The check could not complete: {exc}") from exc

        return self._report(schedule, observations)

    def _report(self, schedule: Schedule, observations: List[Dict[str, Any]]):
        def distinct(key: str):
            return sorted({str(o[key]) for o in observations})

        hashes = distinct("schedule_hash")
        fingerprints = distinct("model_fingerprint")
        solver_fingerprints = distinct("solver_fingerprint")
        objectives = distinct("objective_value")

        self.stdout.write("")
        self.stdout.write(f"  distinct schedule_hash     : {len(hashes)} {hashes}")
        self.stdout.write(f"  distinct model_fingerprint : {len(fingerprints)}")
        self.stdout.write(f"  distinct solver_fingerprint: {len(solver_fingerprints)}")
        self.stdout.write(f"  distinct objective_value   : {len(objectives)}")

        det_times = [o["deterministic_time_used"] or 0.0 for o in observations]
        self.stdout.write(
            f"  deterministic_time spread  : {max(det_times) - min(det_times):.4f} "
            f"(min {min(det_times):.4f}, max {max(det_times):.4f})"
        )

        non_deterministic_stops = [
            o for o in observations if not o["deterministic_stop"]
        ]
        self.stdout.write("")

        if len(fingerprints) != 1:
            self.stderr.write(
                self.style.ERROR(
                    f"FAIL: the model proto itself differed between runs "
                    f"({len(fingerprints)} distinct model_fingerprint). This is a "
                    "model-construction (input ordering) defect, not a search "
                    "one — the solver was asked a different question each time."
                )
            )
            raise SystemExit(EXIT_NOT_DETERMINISTIC)

        if len(hashes) != 1:
            self.stderr.write(
                self.style.ERROR(
                    f"FAIL: {len(hashes)} distinct schedules from an identical "
                    "request on this machine. The determinism requirement is NOT "
                    "met.\n"
                    f"  hashes: {hashes}"
                )
            )
            if non_deterministic_stops:
                self.stderr.write(
                    self.style.WARNING(
                        f"  {len(non_deterministic_stops)} of "
                        f"{len(observations)} runs stopped non-deterministically "
                        f"({sorted({o['stop_reason'] for o in non_deterministic_stops})}). "
                        "A wall-clock backstop stop explains a hash difference: "
                        "re-run with a longer --time-limit, or reduce load."
                    )
                )
            raise SystemExit(EXIT_NOT_DETERMINISTIC)

        loaded = [o for o in observations if o["under_load"]]
        summary = (
            f"PASS: {len(observations)} runs, one schedule ({hashes[0]})"
            + (f", including {len(loaded)} under CPU load" if loaded else "")
            + "."
        )
        self.stdout.write(self.style.SUCCESS(summary))

        if non_deterministic_stops:
            self.stdout.write(
                self.style.WARNING(
                    f"NOTE: {len(non_deterministic_stops)} run(s) stopped "
                    "non-deterministically yet still agreed. The answer was "
                    "reproducible here, but the margin is thin — consider a "
                    "longer time limit for headroom."
                )
            )

        if schedule.schedule_hash and schedule.schedule_hash != hashes[0]:
            self.stdout.write(
                self.style.WARNING(
                    f"NOTE: the re-solve hash ({hashes[0]}) differs from the hash "
                    f"stored on the schedule ({schedule.schedule_hash}). The runs "
                    "agree with each other, so the solver is reproducible now. "
                    "The stored value predates some change — input data, solver "
                    "settings, or the OR-Tools version. Compare "
                    "solver_fingerprint to tell which."
                )
            )
        return None
