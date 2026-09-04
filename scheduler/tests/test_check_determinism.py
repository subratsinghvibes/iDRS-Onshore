"""Task 10 — the ``check_determinism`` management command.

*Validates: Requirements 2.1, 2.3, 2.12*

The command is the authoritative half of the reproducibility story: the detail
page's badge is advisory because one solve cannot prove reproducibility, and this
is what actually compares runs. So it needs tests of its own — a broken
verification tool is worse than no tool, because it reports success.

Exercised here against the **test** database, which has migration 0063 applied by
the test runner. The development database deliberately does not: 0063 is generated
and verified but not deployed, so ``manage.py check_determinism`` against
``idrs_db`` fails on the missing column until the migration is applied. That is
the expected state, not a defect.

Four things are asserted, and the last is the one that makes the command safe to
point at production:

1. It refuses ``--runs 1`` — one run cannot demonstrate anything.
2. It agrees with itself on a real schedule and reports PASS.
3. It exits non-zero when the hashes disagree.
4. **It writes nothing.** Row counts and the target row's own fields are
   unchanged afterwards.

Run independently::

    python manage.py test scheduler.tests.test_check_determinism --keepdb
"""

from __future__ import annotations

from io import StringIO

from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in
from django.core.management import CommandError, call_command
from django.test import TestCase
from django.urls import reverse

from scheduler.models import Assignment, Schedule
from scheduler.signals import log_user_login

from .factories import (
    FY_API_LABEL,
    UNIQUE_OPTIMUM_TIME_LIMIT_SECONDS,
    build_unique_optimum_scenario,
)


class CheckDeterminismCommandTests(TestCase):
    """The command, end to end, against a schedule created by the endpoint."""

    @classmethod
    def setUpTestData(cls):
        # One scenario per class: the factory hard-codes RIG-01 / RIG-02 and
        # Rig.name is unique.
        cls.scenario = build_unique_optimum_scenario(suffix="CHECKCMD")

    def setUp(self):
        super().setUp()
        self.user = get_user_model().objects.create_superuser(
            username="checkcmd-harness",
            email="checkcmd@example.invalid",
            password="harness-not-a-real-password",
        )
        # force_login sends user_logged_in with a bare HttpRequest whose method
        # is None; the login-audit receiver writes that into a NOT NULL column
        # and poisons the atomic block. Same workaround as the other suites.
        user_logged_in.disconnect(log_user_login)
        self.addCleanup(user_logged_in.connect, log_user_login)
        self.client.force_login(self.user)

    def _create_schedule(self) -> Schedule:
        """Create through the endpoint, so ScheduleRig/ScheduleWell exist.

        The command reconstructs the request from those rows, so a schedule built
        directly with ``Schedule.objects.create`` would not be re-solvable — which
        is itself covered by ``test_it_refuses_a_schedule_with_no_selection``.
        """
        response = self.client.post(
            reverse("schedule-create-schedule"),
            data={
                "name": "Determinism Check Target",
                "financial_year": FY_API_LABEL,
                "rig_ids": [str(rig.id) for rig in self.scenario.rigs],
                "well_ids": [str(well.id) for well in self.scenario.wells],
                "time_limit_seconds": UNIQUE_OPTIMUM_TIME_LIMIT_SECONDS,
            },
            content_type="application/json",
        )
        self.assertEqual(
            response.status_code,
            200,
            f"create_schedule failed: {response.content!r}",
        )
        return Schedule.objects.get(id=response.json()["id"])

    def _run(self, **kwargs):
        out, err = StringIO(), StringIO()
        call_command("check_determinism", stdout=out, stderr=err, **kwargs)
        return out.getvalue(), err.getvalue()

    # -- guard rails ----------------------------------------------------

    def test_it_refuses_a_single_run(self):
        schedule = self._create_schedule()
        with self.assertRaises(CommandError) as caught:
            self._run(schedule_id=str(schedule.id), runs=1)
        self.assertIn(
            "at least 2",
            str(caught.exception),
            "The refusal must explain why one run is not enough.",
        )

    def test_it_refuses_an_unknown_schedule_id(self):
        with self.assertRaises(CommandError):
            self._run(
                schedule_id="00000000-0000-0000-0000-000000000000", runs=2
            )

    def test_it_refuses_a_schedule_with_no_selection(self):
        """A row with no ScheduleRig/ScheduleWell cannot be reconstructed."""
        orphan = Schedule.objects.create(
            name="no selection recorded", status="COMPLETED"
        )
        with self.assertRaises(CommandError) as caught:
            self._run(schedule_id=str(orphan.id), runs=2)
        message = str(caught.exception)
        self.assertIn("no rig/well selection", message)
        self.assertIn(
            "cannot be reconstructed",
            message,
            "The error must say why, so an operator knows this is a data-shape "
            "limitation rather than a determinism failure.",
        )

    def test_list_runs_without_a_target(self):
        self._create_schedule()
        out, _ = self._run(list_schedules=True)
        self.assertIn("Determinism Check Target", out)

    # -- the actual check -----------------------------------------------

    def test_it_reports_pass_and_one_hash_for_a_real_schedule(self):
        schedule = self._create_schedule()
        self.assertTrue(
            Assignment.objects.filter(schedule=schedule).exists(),
            "PRECONDITION: the target schedule must have assignments, or the "
            "command would be comparing empty schedules.",
        )

        out, err = self._run(schedule_id=str(schedule.id), runs=2)

        self.assertIn("PASS", out, f"stdout:\n{out}\nstderr:\n{err}")
        self.assertIn("distinct schedule_hash     : 1", out)
        self.assertIn("distinct model_fingerprint : 1", out)
        self.assertIn("distinct solver_fingerprint: 1", out)
        self.assertIn(
            "deterministic_time spread  : 0.0000",
            out,
            "Identical work budgets must produce an identical work count.",
        )

    def test_the_resolve_agrees_with_the_stored_hash(self):
        """No 'differs from the stored hash' note on an unchanged database.

        That note exists for the case where inputs or solver settings moved since
        the schedule was saved. Here nothing has moved, so its absence confirms
        the re-solve really is reconstructing the same request rather than an
        approximation of it.
        """
        schedule = self._create_schedule()
        out, _ = self._run(schedule_id=str(schedule.id), runs=2)
        self.assertNotIn(
            "differs from the hash",
            out,
            "The re-solve produced a different schedule from the stored one, so "
            "the request reconstruction in _selection() does not match what "
            "create_schedule actually solved.",
        )

    def test_latest_selects_the_most_recent_completed_schedule(self):
        schedule = self._create_schedule()
        out, _ = self._run(latest=True, runs=2)
        self.assertIn(str(schedule.id), out)
        self.assertIn("PASS", out)

    def test_under_load_loads_exactly_the_number_it_reports(self):
        """The header count and the actual loaded runs must agree.

        They did not initially: the boundary run was loaded as well, so a
        ``--runs 4`` run reported "last 2 under CPU load" while loading three. A
        verification tool that misreports its own conditions undermines the
        result it prints.
        """
        schedule = self._create_schedule()
        out, _ = self._run(
            schedule_id=str(schedule.id), runs=4, under_load=True, load_workers=1
        )

        self.assertIn("(last 2 under CPU load", out)

        # Count the 'Y' flags in the load column of the per-run table.
        loaded = [
            line
            for line in out.splitlines()
            if line.strip().startswith(("1 ", "2 ", "3 ", "4 "))
            and " Y " in line[:14]
        ]
        self.assertEqual(
            len(loaded),
            2,
            f"Header promised 2 loaded runs; the table shows {len(loaded)}.\n{out}",
        )
        self.assertIn("including 2 under CPU load", out)

    # -- the read-only guarantee ----------------------------------------

    def test_it_writes_nothing(self):
        """The property that makes it safe against production data."""
        schedule = self._create_schedule()

        before_counts = (
            Schedule.objects.count(),
            Assignment.objects.count(),
        )
        before_row = {
            field: getattr(schedule, field)
            for field in (
                "status",
                "schedule_hash",
                "model_fingerprint",
                "solver_fingerprint",
                "stop_reason",
                "deterministic_stop",
                "deterministic_time_used",
                "deterministic_budget",
                "total_drilling_cost",
                "total_ilm_cost",
                "updated_at",
            )
        }

        self._run(schedule_id=str(schedule.id), runs=2)

        self.assertEqual(
            (Schedule.objects.count(), Assignment.objects.count()),
            before_counts,
            "The command created or deleted rows. It must be read-only: it is "
            "documented as safe to run against production data on the VM.",
        )

        reloaded = Schedule.objects.get(pk=schedule.pk)
        for field, value in before_row.items():
            self.assertEqual(
                getattr(reloaded, field),
                value,
                f"The command modified Schedule.{field}. It must not write.",
            )


class CheckDeterminismFailureReportingTests(TestCase):
    """It must exit non-zero when the answer is no."""

    def test_disagreeing_hashes_exit_non_zero(self):
        """Patched at the solve boundary to force a disagreement.

        There is no input that reliably produces a non-deterministic result any
        more — that is the point of the whole spec — so the failure path is
        exercised by making two solves return different hashes. Without this the
        command's most important branch would never be executed by any test, and
        a verification tool whose failure path is untested is a tool that reports
        success.
        """
        from unittest.mock import patch

        scenario = build_unique_optimum_scenario(suffix="CHECKFAIL")
        schedule = Schedule.objects.create(
            name="forced disagreement",
            status="COMPLETED",
            financial_year=FY_API_LABEL,
            time_limit_seconds=UNIQUE_OPTIMUM_TIME_LIMIT_SECONDS,
        )
        from scheduler.models import ScheduleRig, ScheduleWell

        ScheduleRig.objects.bulk_create(
            [ScheduleRig(schedule=schedule, rig=rig) for rig in scenario.rigs]
        )
        ScheduleWell.objects.bulk_create(
            [ScheduleWell(schedule=schedule, well=well) for well in scenario.wells]
        )

        hashes = iter(["aaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbb"])
        real_solve = None

        def fake_solve(self, *args, **kwargs):
            results = real_solve(self, *args, **kwargs)
            results["schedule_hash"] = next(hashes)
            return results

        from scheduler.optimization import DrillingScheduler

        real_solve = DrillingScheduler.solve

        out, err = StringIO(), StringIO()
        with patch.object(DrillingScheduler, "solve", fake_solve):
            with self.assertRaises(SystemExit) as caught:
                call_command(
                    "check_determinism",
                    schedule_id=str(schedule.id),
                    runs=2,
                    stdout=out,
                    stderr=err,
                )

        self.assertEqual(
            caught.exception.code,
            1,
            "A determinism failure must exit 1 so a deployment script or CI job "
            "can detect it.",
        )
        self.assertIn("FAIL", err.getvalue())
        self.assertIn("2 distinct schedules", err.getvalue())
