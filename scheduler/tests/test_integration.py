"""Task 9.3 — integration tests through the HTTP layer.

*Validates: Requirements 2.1, 2.4, 2.8, 2.9, 2.11, 3.12, 3.13*

Every other determinism test in this package drives ``DrillingScheduler``
directly. That is the right level for the solver's own properties, but it leaves a
gap: the endpoint does work the scheduler does not — it builds the input frames
from querysets, persists the result, and derives ``sequence_order`` — and a
determinism defect reintroduced in *that* layer would not be caught by any of
them.

So these tests go through ``POST /api/schedules/create_schedule/`` with the
Django test client and assert on the response body **and** the persisted rows.

What is deliberately NOT duplicated here
----------------------------------------
Several of task 9.3's bullets are already covered, and re-asserting them would
mean two tests failing for one cause:

* **Duplicate well names return 400 with no Schedule row** —
  ``test_ordering.DuplicateWellNameTests.test_create_schedule_returns_400_and_leaves_no_schedule_row``.
* **``sequence_order`` derived per rig, unassigned wells carry rejection
  analysis** — ``test_preservation.SavePathPreservationTests``, which additionally
  compares the whole save-path result against the pre-fix golden.
* **The amber badge renders for a backstop-bound run** —
  ``test_provenance.DetailPageRenderTests.test_amber_badge_and_warning_for_a_wall_clock_stop``.

What is new here is the part only the endpoint can show: that two identical
requests produce the same schedule *and* the same persisted provenance, and that
``deterministic=False`` still reaches the untouched performance path.

Run independently::

    python manage.py test scheduler.tests.test_integration --keepdb
"""

from __future__ import annotations

from typing import Any, Dict

from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in
from django.test import TestCase
from django.urls import reverse

from scheduler.models import Assignment, Schedule
from scheduler.optimization import (
    CANONICALIZATION_SKIPPED_PERFORMANCE_MODE,
    STOP_REASON_DETERMINISTIC_BUDGET,
    STOP_REASON_OPTIMAL_PROVEN,
    calibrate_two_stage_budgets,
)
from scheduler.signals import log_user_login
from scheduler.views import DETERMINISM_PROVENANCE_FIELDS

from .factories import (
    FY_API_LABEL,
    UNIQUE_OPTIMUM_TIME_LIMIT_SECONDS,
    build_unique_optimum_scenario,
)


class EndpointDeterminismTests(TestCase):
    """Two identical requests, one schedule, one set of provenance."""

    @classmethod
    def setUpTestData(cls):
        # One scenario for the class: this factory hard-codes rig names
        # (RIG-01 / RIG-02) and Rig.name is unique, so a second build would
        # collide on the constraint.
        cls.scenario = build_unique_optimum_scenario(suffix="INTEG")

    def setUp(self):
        super().setUp()
        self.user = get_user_model().objects.create_superuser(
            username="integration-harness",
            email="integration@example.invalid",
            password="harness-not-a-real-password",
        )
        # force_login sends user_logged_in with a bare HttpRequest whose method
        # is None; the login-audit receiver writes that into a NOT NULL column
        # and poisons the test's atomic block. Same workaround, and same
        # reasoning, as test_preservation.SavePathPreservationTests.
        user_logged_in.disconnect(log_user_login)
        self.addCleanup(user_logged_in.connect, log_user_login)
        self.client.force_login(self.user)

    def _post(self, name: str, **overrides: Any):
        payload: Dict[str, Any] = {
            "name": name,
            "financial_year": FY_API_LABEL,
            "rig_ids": [str(rig.id) for rig in self.scenario.rigs],
            "well_ids": [str(well.id) for well in self.scenario.wells],
            "time_limit_seconds": UNIQUE_OPTIMUM_TIME_LIMIT_SECONDS,
        }
        payload.update(overrides)
        response = self.client.post(
            reverse("schedule-create-schedule"),
            data=payload,
            content_type="application/json",
        )
        self.assertEqual(
            response.status_code,
            200,
            f"create_schedule failed: {response.status_code} "
            f"{response.content!r}",
        )
        return response

    def test_two_identical_requests_agree_on_schedule_and_provenance(self):
        first = self._post("Integration Run A")
        second = self._post("Integration Run B")

        first_body, second_body = first.json(), second.json()

        # --- the response bodies -----------------------------------------
        self.assertEqual(
            first_body["schedule_hash"],
            second_body["schedule_hash"],
            "Two identical requests through the endpoint returned different "
            "schedules.",
        )
        self.assertEqual(
            first_body.get("model_fingerprint"),
            second_body.get("model_fingerprint"),
            "The endpoint built a different model for an identical request, so "
            "the ordering hardening is not reaching the queryset layer.",
        )
        self.assertEqual(
            first_body.get("solver_fingerprint"),
            second_body.get("solver_fingerprint"),
            "Identical settings must produce an identical solver fingerprint.",
        )
        self.assertIsNotNone(
            first_body.get("model_fingerprint"),
            "The response must carry model_fingerprint (task 8.1).",
        )

        # --- the persisted rows ------------------------------------------
        first_row = Schedule.objects.get(id=first_body["id"])
        second_row = Schedule.objects.get(id=second_body["id"])
        self.assertEqual(first_row.status, "COMPLETED")
        self.assertEqual(second_row.status, "COMPLETED")

        for field in DETERMINISM_PROVENANCE_FIELDS:
            self.assertEqual(
                getattr(first_row, field),
                getattr(second_row, field),
                f"Persisted '{field}' differs between two identical requests.",
            )
            self.assertIsNotNone(
                getattr(first_row, field),
                f"Persisted '{field}' is NULL, so the save path did not record "
                "provenance (task 8.2).",
            )

        self.assertEqual(
            first_row.schedule_hash,
            first_body["schedule_hash"],
            "The persisted hash must match the one the response reported.",
        )

    def test_the_persisted_stop_reason_is_a_reproducible_one(self):
        """This scenario closes, so the stop must be a deterministic one."""
        response = self._post("Integration Stop Reason")
        row = Schedule.objects.get(id=response.json()["id"])

        self.assertIn(
            row.stop_reason,
            (STOP_REASON_OPTIMAL_PROVEN, STOP_REASON_DETERMINISTIC_BUDGET),
            f"A closing scenario stopped for reason {row.stop_reason!r}; that "
            "means the wall clock is binding on a model that should prove out.",
        )
        self.assertTrue(
            row.deterministic_stop,
            "deterministic_stop must be True for a work-budget or proven stop.",
        )

    def test_the_recorded_budget_matches_the_calibration(self):
        """The persisted budget is stage 1's share, not the whole request.

        Stage 2 gets its own solver, so ``self.solver`` — and therefore the
        reported metrics — carry stage 1's numbers. Asserting the whole-request
        budget here would be asserting a quantity no single solver is ever
        configured with.
        """
        response = self._post("Integration Budget")
        row = Schedule.objects.get(id=response.json()["id"])

        budgets = calibrate_two_stage_budgets(UNIQUE_OPTIMUM_TIME_LIMIT_SECONDS)
        self.assertAlmostEqual(
            row.deterministic_budget,
            budgets.stage_one.deterministic_budget,
            places=6,
            msg="The persisted deterministic_budget must equal stage 1's share "
            "of the calibrated budget.",
        )
        self.assertLessEqual(
            row.deterministic_time_used,
            row.deterministic_budget * 1.05,
            "Work used should not materially exceed the budget it was given "
            "(CP-SAT overshoots its own budget only slightly).",
        )

    def test_assignments_persist_with_per_rig_sequence_order(self):
        """Guard: the response identity above must not be over an empty schedule."""
        response = self._post("Integration Assignments")
        schedule = Schedule.objects.get(id=response.json()["id"])

        assignments = list(
            Assignment.objects.filter(schedule=schedule)
            .select_related("rig", "well")
            .order_by("rig__name", "sequence_order")
        )
        self.assertTrue(
            assignments,
            "No Assignment rows persisted, so the determinism assertions in "
            "this class would be comparing two empty schedules.",
        )

        by_rig: Dict[str, list] = {}
        for assignment in assignments:
            by_rig.setdefault(assignment.rig.name, []).append(assignment)
        for rig_name, rows in by_rig.items():
            ordered = sorted(rows, key=lambda a: a.well_start_date)
            self.assertEqual(
                [row.sequence_order for row in ordered],
                list(range(1, len(rows) + 1)),
                f"sequence_order on {rig_name} is not a 1..n ranking by start "
                "date; task 8 must not have disturbed the save path.",
            )


class PerformancePathIsUntouchedTests(TestCase):
    """Clause 3.12 — ``deterministic=False`` keeps its pre-fix behaviour."""

    @classmethod
    def setUpTestData(cls):
        cls.scenario = build_unique_optimum_scenario(suffix="INTEGPERF")

    def test_no_work_budget_and_no_stage_two(self):
        from .support import new_scheduler

        scheduler = new_scheduler(self.scenario)
        results = scheduler.solve(
            time_limit_seconds=UNIQUE_OPTIMUM_TIME_LIMIT_SECONDS,
            deterministic=False,
        )

        self.assertIsNone(
            results["deterministic_budget"],
            "The performance path must be granted no work budget: clause 3.12 "
            "attaches no determinism promise to it.",
        )
        self.assertIsNone(
            results["model_fingerprint_canonical"],
            "Stage 2 must be skipped on the performance path, so there is no "
            "canonical model fingerprint.",
        )
        # Not None: the code records *why* stage 2 was skipped, which is a
        # stronger signal than absence. "Skipped because performance mode" and
        # "skipped because stage 1 found nothing" are different diagnoses.
        self.assertEqual(
            results["canonicalization_status"],
            CANONICALIZATION_SKIPPED_PERFORMANCE_MODE,
            "The performance path must record that canonicalization was "
            "skipped for that reason specifically.",
        )
        # Provenance is still reported — it is the values that differ, not the
        # presence of the block.
        self.assertIsNotNone(results["model_fingerprint"])
        self.assertIsNotNone(results["solver_fingerprint"])
        self.assertIsNotNone(results["stop_reason"])

    def test_the_performance_path_still_uses_portfolio_search(self):
        from ortools.sat.python import cp_model

        from .support import new_scheduler

        scheduler = new_scheduler(self.scenario)
        scheduler.preprocess_data()
        scheduler.setup_variables()
        scheduler._configure_solver_for_determinism(
            UNIQUE_OPTIMUM_TIME_LIMIT_SECONDS, deterministic=False
        )
        self.assertEqual(
            scheduler.solver.parameters.search_branching,
            cp_model.PORTFOLIO_SEARCH,
            "The performance path's parameter block must not move (clause 3.12).",
        )
        self.assertEqual(
            scheduler.solver.parameters.max_deterministic_time,
            float("inf"),
            "The performance path must carry no deterministic-time limit.",
        )
