"""Task 8 — determinism provenance: payload, persistence, migration, rendering.

*Validates: Requirements 2.8, 3.5, 3.14*

Task 8 adds no solver behaviour. It makes the behaviour tasks 3-7 delivered
*visible*: which model was solved, under which machinery, why the solve stopped,
and whether that stop reason implies the answer will come back the same.

The distinction that runs through the whole file is **two fingerprints**:

* ``model_fingerprint`` identifies the *question* — the CP-SAT model proto.
* ``solver_fingerprint`` identifies the *machinery* — the explicitly-set
  parameters, the OR-Tools version, and the ``IDRS_SOLVER_DETERMINISM`` block.

They have to move independently, and that is asserted rather than assumed:
changing ``DETERMINISTIC_TIME_RATIO`` or ``FIXED_SEARCH`` must move the solver
fingerprint and leave the model fingerprint alone. If a settings change moved
both, the model fingerprint would be useless for deciding whether two runs
answered the same question.

The other thing asserted here is that **null means "not recorded"**, never "not
reproducible". Rows written before migration 0063 have no provenance, and both
the serializer and the detail template have to treat that as unknown rather than
as a failure. ``deterministic_stop`` is a nullable Boolean for exactly this
reason.

Run independently::

    python manage.py test scheduler.tests.test_provenance --keepdb
"""

from __future__ import annotations

from typing import Any, Dict

from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.operations.fields import AddField
from django.test import TestCase, override_settings
from django.urls import reverse
from ortools.sat.python import cp_model

from scheduler.models import Schedule
from scheduler.optimization import (
    compute_solver_fingerprint,
    determinism_settings,
)
from scheduler.serializers import ScheduleListSerializer, ScheduleSerializer
from scheduler.signals import log_user_login
from scheduler.views import DETERMINISM_PROVENANCE_FIELDS

from .factories import build_unique_optimum_scenario
from .support import new_scheduler

#: The nine keys task 8.1 adds to the result payload.
PROVENANCE_PAYLOAD_KEYS = (
    "model_fingerprint",
    "model_fingerprint_canonical",
    "solver_fingerprint",
    "deterministic_stop",
    "stop_reason",
    "deterministic_time_used",
    "deterministic_budget",
    "wall_backstop_seconds",
    "canonicalization_status",
)

#: A complete settings block, so ``override_settings`` in these tests replaces
#: the whole dict rather than relying on partial-dict fallback behaviour.
_BASE_DETERMINISM_SETTINGS: Dict[str, Any] = {
    "DETERMINISTIC_TIME_RATIO": 0.60,
    "WALL_BACKSTOP_FACTOR": 1.5,
    "CANONICALIZE_BUDGET_SHARE": 0.15,
    "FIXED_SEARCH": False,
}


def _settings_with(**overrides: Any) -> Dict[str, Any]:
    return {**_BASE_DETERMINISM_SETTINGS, **overrides}


class SolverFingerprintTests(TestCase):
    """The solver fingerprint is a pure function of the configuration."""

    def _parameters(self):
        solver = cp_model.CpSolver()
        solver.parameters.num_search_workers = 1
        solver.parameters.random_seed = 42
        solver.parameters.max_deterministic_time = 3.06
        return solver.parameters

    def test_identical_configuration_gives_identical_fingerprint(self):
        self.assertEqual(
            compute_solver_fingerprint(self._parameters()),
            compute_solver_fingerprint(self._parameters()),
            "The solver fingerprint must be stable for an identical "
            "configuration, or it cannot be compared between runs — which is "
            "the only thing it is for.",
        )

    def test_a_different_parameter_gives_a_different_fingerprint(self):
        first = compute_solver_fingerprint(self._parameters())
        other = self._parameters()
        other.random_seed = 43
        self.assertNotEqual(
            first,
            compute_solver_fingerprint(other),
            "Changing a solver parameter must change the solver fingerprint.",
        )

    def test_it_contains_no_measured_quantity(self):
        """Twice in a row, with real time passing, must still agree.

        A fingerprint that folded in wall time or deterministic time used would
        differ between two calls and would silently never match across runs.
        """
        import time

        first = compute_solver_fingerprint(self._parameters())
        time.sleep(0.05)
        self.assertEqual(first, compute_solver_fingerprint(self._parameters()))

    @override_settings(IDRS_SOLVER_DETERMINISM=_settings_with())
    def test_ratio_change_moves_the_solver_fingerprint(self):
        baseline = compute_solver_fingerprint(self._parameters())
        with override_settings(
            IDRS_SOLVER_DETERMINISM=_settings_with(DETERMINISTIC_TIME_RATIO=0.30)
        ):
            changed = compute_solver_fingerprint(self._parameters())
        self.assertNotEqual(
            baseline,
            changed,
            "DETERMINISTIC_TIME_RATIO decides how much work a solve is allowed, "
            "so it changes the answer and must change the solver fingerprint.",
        )

    @override_settings(IDRS_SOLVER_DETERMINISM=_settings_with())
    def test_fixed_search_change_moves_the_solver_fingerprint(self):
        baseline = compute_solver_fingerprint(self._parameters())
        with override_settings(
            IDRS_SOLVER_DETERMINISM=_settings_with(FIXED_SEARCH=True)
        ):
            changed = compute_solver_fingerprint(self._parameters())
        self.assertNotEqual(
            baseline,
            changed,
            "FIXED_SEARCH promotes the decision strategies from hint to mandate "
            "and materially changes the answer (task 7.2), so it must be part "
            "of the solver fingerprint.",
        )


class FingerprintIndependenceTests(TestCase):
    """A settings change moves the solver fingerprint, not the model one."""

    @classmethod
    def setUpTestData(cls):
        cls.scenario = build_unique_optimum_scenario(suffix="PROV")

    def _solve_and_collect(self) -> Dict[str, Any]:
        scheduler = new_scheduler(self.scenario)
        results = scheduler.solve(time_limit_seconds=10)
        return {
            "model_fingerprint": results["model_fingerprint"],
            "solver_fingerprint": results["solver_fingerprint"],
            "schedule_hash": results["schedule_hash"],
            "objective_value": results["objective_value"],
        }

    @override_settings(IDRS_SOLVER_DETERMINISM=_settings_with())
    def test_repeat_runs_agree_on_both_fingerprints(self):
        first = self._solve_and_collect()
        second = self._solve_and_collect()
        self.assertEqual(
            first["model_fingerprint"],
            second["model_fingerprint"],
            "Identical inputs must produce an identical model fingerprint; a "
            "difference here is a model-construction ordering defect.",
        )
        self.assertEqual(
            first["solver_fingerprint"],
            second["solver_fingerprint"],
            "Identical inputs and settings must produce an identical solver "
            "fingerprint.",
        )
        self.assertEqual(first["schedule_hash"], second["schedule_hash"])

    def test_ratio_change_leaves_the_model_fingerprint_alone(self):
        """The two fingerprints must be independent.

        This is the assertion that makes ``model_fingerprint`` useful. If a
        settings change moved it too, it could not answer "did these two runs
        solve the same problem?" — which is the question it exists for.
        """
        with override_settings(IDRS_SOLVER_DETERMINISM=_settings_with()):
            baseline = self._solve_and_collect()
        with override_settings(
            IDRS_SOLVER_DETERMINISM=_settings_with(DETERMINISTIC_TIME_RATIO=0.30)
        ):
            changed = self._solve_and_collect()

        self.assertEqual(
            baseline["model_fingerprint"],
            changed["model_fingerprint"],
            "The model proto does not depend on the time ratio, so the model "
            "fingerprint must not move when the ratio changes.",
        )
        self.assertNotEqual(
            baseline["solver_fingerprint"],
            changed["solver_fingerprint"],
            "The solver fingerprint must move when the ratio changes.",
        )

    def test_fixed_search_leaves_the_model_fingerprint_alone(self):
        with override_settings(IDRS_SOLVER_DETERMINISM=_settings_with()):
            baseline = self._solve_and_collect()
        with override_settings(
            IDRS_SOLVER_DETERMINISM=_settings_with(FIXED_SEARCH=True)
        ):
            changed = self._solve_and_collect()

        self.assertEqual(
            baseline["model_fingerprint"],
            changed["model_fingerprint"],
            "FIXED_SEARCH is a solver parameter, not a model change. The "
            "decision strategies are on the model either way (task 7.1); what "
            "changes is whether CP-SAT is obliged to follow them.",
        )
        self.assertNotEqual(
            baseline["solver_fingerprint"], changed["solver_fingerprint"]
        )


class ProvenancePayloadTests(TestCase):
    """Both result branches carry the whole block."""

    @classmethod
    def setUpTestData(cls):
        cls.scenario = build_unique_optimum_scenario(suffix="PAYL")

    def test_solved_branch_carries_every_provenance_key(self):
        scheduler = new_scheduler(self.scenario)
        results = scheduler.solve(time_limit_seconds=10)
        for key in PROVENANCE_PAYLOAD_KEYS:
            self.assertIn(
                key,
                results,
                f"Result payload is missing '{key}'. Task 8.1 requires the "
                "whole provenance block on the payload.",
            )
        self.assertTrue(results["is_feasible"], "PRECONDITION: must have solved.")
        self.assertIsNotNone(results["model_fingerprint"])
        self.assertIsNotNone(results["solver_fingerprint"])
        self.assertIsNotNone(results["stop_reason"])

    def test_unsolved_branch_carries_every_provenance_key(self):
        """The failure branch is the one that most needs provenance.

        A run that produced no schedule is exactly when an operator wants to
        know why the solver stopped. The two ``self.results`` branches have
        drifted apart before, so this asserts they have not again.
        """
        # Reuse the class scenario rather than building a second one: this
        # factory hard-codes rig names (RIG-01 / RIG-02) and Rig.name is unique,
        # so a second build in the same class collides on the constraint.
        scheduler = new_scheduler(self.scenario)
        scheduler.preprocess_data()
        scheduler.setup_variables()
        scheduler.add_constraints()
        scheduler.add_ilm_constraints()
        scheduler.set_objective()

        # Force infeasibility rather than simulating it, so the real unsolved
        # branch runs.
        assert scheduler.model is not None
        first_well = scheduler.wells_df["name"].iloc[0]
        first_rig = scheduler.rigs_df["name"].iloc[0]
        assignment = scheduler.assignments[(first_well, first_rig)]
        scheduler.model.Add(assignment == 1)
        scheduler.model.Add(assignment == 0)

        results = scheduler._run_two_stage_solve(10, True, "forced-infeasible")

        self.assertFalse(
            results["is_feasible"],
            "PRECONDITION: this test needs the UNSOLVED branch to run.",
        )
        for key in PROVENANCE_PAYLOAD_KEYS:
            self.assertIn(
                key,
                results,
                f"The unsolved result branch is missing '{key}'.",
            )
        self.assertIsNotNone(
            results["stop_reason"],
            "A failed run must still say why the solver stopped.",
        )


class ProvenancePersistenceTests(TestCase):
    """The six columns, the four save paths, and null tolerance."""

    def test_the_field_tuple_matches_the_model(self):
        model_fields = {f.name for f in Schedule._meta.get_fields()}
        for field in DETERMINISM_PROVENANCE_FIELDS:
            self.assertIn(
                field,
                model_fields,
                f"views.DETERMINISM_PROVENANCE_FIELDS names '{field}', which is "
                "not a Schedule field. The helper would raise at save time.",
            )

    def test_apply_determinism_provenance_copies_and_does_not_save(self):
        from scheduler.views import apply_determinism_provenance

        schedule = Schedule.objects.create(name="prov-apply", status="RUNNING")
        results = {
            "model_fingerprint": "m" * 64,
            "solver_fingerprint": "s" * 64,
            "deterministic_stop": True,
            "stop_reason": "DETERMINISTIC_BUDGET",
            "deterministic_time_used": 3.06,
            "deterministic_budget": 5.1,
        }
        apply_determinism_provenance(schedule, results)

        self.assertEqual(schedule.stop_reason, "DETERMINISTIC_BUDGET")
        self.assertEqual(schedule.deterministic_time_used, 3.06)

        # Not saved: the caller owns the write.
        reloaded = Schedule.objects.get(pk=schedule.pk)
        self.assertIsNone(
            reloaded.stop_reason,
            "apply_determinism_provenance must not save. The caller is mid-way "
            "through building its own field set and owns the save().",
        )

    def test_missing_keys_become_null_not_stale(self):
        from scheduler.views import apply_determinism_provenance

        schedule = Schedule.objects.create(
            name="prov-stale",
            status="COMPLETED",
            stop_reason="WALL_CLOCK_BACKSTOP",
            deterministic_stop=False,
        )
        # A result dict from a path that predates task 8.1.
        apply_determinism_provenance(schedule, {"schedule_hash": "abc"})

        self.assertIsNone(
            schedule.stop_reason,
            "A result without provenance must null the columns, not leave the "
            "previous run's values on the row.",
        )
        self.assertIsNone(schedule.deterministic_stop)

    def test_pre_migration_rows_read_back_as_null(self):
        """A row written before 0063 has no provenance, and that is fine.

        Null must read as "not recorded". It must not raise, and it must not be
        confused with ``deterministic_stop = False`` ("recorded, and not
        reproducible") — which is why the column is a nullable Boolean.
        """
        schedule = Schedule.objects.create(name="prov-legacy", status="COMPLETED")
        reloaded = Schedule.objects.get(pk=schedule.pk)

        for field in DETERMINISM_PROVENANCE_FIELDS:
            self.assertIsNone(
                getattr(reloaded, field),
                f"'{field}' should default to NULL for a row that carries no "
                "provenance. Migration 0063 adds no default and no backfill.",
            )

        self.assertIsNot(
            reloaded.deterministic_stop,
            False,
            "deterministic_stop must be None, not False, when unrecorded. "
            "False means 'measured, and not reproducible'.",
        )

    def test_serializers_expose_all_six_to_every_user(self):
        """Not gated behind the admin check, deliberately.

        ``optimality_gap_percent`` is an internal solver diagnostic and is
        hidden from non-admins. ``stop_reason`` is a trust signal about the
        schedule the user is about to act on, so hiding it would hide the
        warning from exactly the people who need it.
        """
        schedule = Schedule.objects.create(
            name="prov-serialize",
            status="COMPLETED",
            stop_reason="DETERMINISTIC_BUDGET",
            deterministic_stop=True,
            model_fingerprint="m" * 64,
            solver_fingerprint="s" * 64,
            deterministic_time_used=3.06,
            deterministic_budget=5.1,
        )

        for serializer_class in (ScheduleSerializer, ScheduleListSerializer):
            # No request in context => treated as a non-admin, which is the
            # case the admin gate would strip.
            data = serializer_class(schedule).data
            for field in DETERMINISM_PROVENANCE_FIELDS:
                self.assertIn(
                    field,
                    data,
                    f"{serializer_class.__name__} drops '{field}' for a "
                    "non-admin. The determinism fields must stay visible to "
                    "everyone.",
                )
            self.assertNotIn(
                "optimality_gap_percent",
                data,
                "PRECONDITION: the admin gate must still be active, or the "
                "assertion above proves nothing about it being bypassed.",
            )


class MigrationReversibilityTests(TestCase):
    """0063 is additive and reversible, structurally asserted."""

    MIGRATION = "0063_add_determinism_provenance"

    def _migration(self):
        loader = MigrationLoader(connection)
        return loader.get_migration("scheduler", self.MIGRATION)

    def test_it_depends_on_0062(self):
        self.assertIn(
            ("scheduler", "0062_add_schedule_input_metadata"),
            self._migration().dependencies,
            "0063 must chain onto 0062, or migrate will branch the history.",
        )

    def test_every_operation_is_a_plain_add_field(self):
        operations = self._migration().operations
        self.assertEqual(
            len(operations),
            len(DETERMINISM_PROVENANCE_FIELDS),
            "0063 must contain exactly one operation per provenance field. An "
            "extra operation means unrelated model drift was swept in.",
        )
        for operation in operations:
            self.assertIsInstance(
                operation,
                AddField,
                f"{operation} is not an AddField. 0063 must stay purely "
                "additive: no AlterField, no RemoveField, no RunPython.",
            )

    def test_every_operation_is_reversible(self):
        for operation in self._migration().operations:
            self.assertTrue(
                operation.reversible,
                f"{operation} is not reversible, so 0063 could not be rolled "
                "back on the VM.",
            )

    def test_every_added_field_is_nullable_with_no_default(self):
        """Nullable with no default is what makes this safe on live data.

        A non-null column, or a column with a default, would rewrite the table
        and would invent provenance for rows that have none.
        """
        from django.db.models import NOT_PROVIDED

        for operation in self._migration().operations:
            field = operation.field
            self.assertTrue(
                field.null,
                f"'{operation.name}' must be nullable — rows predating this "
                "migration genuinely have no provenance.",
            )
            self.assertIs(
                field.default,
                NOT_PROVIDED,
                f"'{operation.name}' must have no default. A default would "
                "invent a value for historical rows and force a table rewrite.",
            )

    def test_the_migration_graph_can_plan_the_reverse(self):
        """Django can actually build the backwards plan, not just claim to.

        Plans only — nothing is executed, so the test database schema is
        untouched. A migration whose reverse cannot even be planned would fail
        on the VM at the worst possible moment.
        """
        executor = MigrationExecutor(connection)
        plan = executor.migration_plan(
            [("scheduler", "0062_add_schedule_input_metadata")]
        )
        backwards = [
            (migration, is_backwards)
            for migration, is_backwards in plan
            if migration.name == self.MIGRATION
        ]
        self.assertEqual(
            len(backwards),
            1,
            "The backwards plan to 0062 must include 0063 exactly once; got "
            f"{[(m.name, b) for m, b in plan]}",
        )
        self.assertTrue(
            backwards[0][1],
            "0063 must appear in the plan as a backwards (unapply) step.",
        )


class DetailPageRenderTests(TestCase):
    """The detail page renders fingerprint, hash and badge."""

    def setUp(self):
        super().setUp()
        self.user = get_user_model().objects.create_superuser(
            username="provenance-harness",
            email="provenance@example.invalid",
            password="harness-not-a-real-password",
        )
        # Same workaround, and same reasoning, as
        # test_preservation.SavePathPreservationTests: force_login sends
        # user_logged_in with a bare HttpRequest whose method is None, which the
        # login-audit receiver writes into a NOT NULL column and poisons the
        # test's atomic block.
        user_logged_in.disconnect(log_user_login)
        self.addCleanup(user_logged_in.connect, log_user_login)
        self.client.force_login(self.user)

    def _render(self, **provenance):
        schedule = Schedule.objects.create(
            name="prov-render",
            status="COMPLETED",
            schedule_hash="1a6136917eac05eb",
            **provenance,
        )
        response = self.client.get(
            reverse("schedule_detail", args=[schedule.id])
        )
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_green_badge_for_a_deterministic_budget_stop(self):
        html = self._render(
            stop_reason="DETERMINISTIC_BUDGET",
            deterministic_stop=True,
            model_fingerprint="c9c1909ea5c26ed1e63d528b743c1206a3529c352f9d8f6770bd83c0a3f431e6",
            deterministic_time_used=3.06,
            deterministic_budget=5.1,
        )

        self.assertIn("1a6136917eac05eb", html, "The schedule hash must render.")
        self.assertIn(
            "c9c1909ea5c26ed1e63d528b743c1206a3529c352f9d8f6770bd83c0a3f431e6",
            html,
            "The model fingerprint must render.",
        )
        self.assertIn("badge bg-success", html)
        # State in TEXT, not colour alone.
        self.assertIn("Reproducible", html)
        # Advisory wording plus the authoritative command, in the accessible name.
        self.assertIn("aria-label", html)
        self.assertIn("check_determinism", html)
        self.assertIn("advisory", html.lower())

    def test_amber_badge_and_warning_for_a_wall_clock_stop(self):
        html = self._render(
            stop_reason="WALL_CLOCK_BACKSTOP",
            deterministic_stop=False,
            model_fingerprint="f" * 64,
        )
        self.assertIn("badge bg-warning", html)
        self.assertIn("Not guaranteed reproducible", html)
        self.assertIn(
            "may produce a different schedule",
            html,
            "The amber state must explain the consequence, not just flag it.",
        )
        self.assertIn("check_determinism", html)

    def test_muted_and_no_false_alarm_when_provenance_is_absent(self):
        """A pre-0063 row must not be reported as irreproducible."""
        html = self._render()
        self.assertIn("not recorded", html)
        self.assertNotIn(
            "Not guaranteed reproducible",
            html,
            "A row with NO provenance must not be labelled irreproducible. "
            "Null means 'not recorded'.",
        )

    def test_badge_state_survives_stripping_colour(self):
        """Colour is not the only carrier of meaning (accessibility).

        Removing every Bootstrap colour class must leave the state readable.
        """
        import re

        html = self._render(
            stop_reason="WALL_CLOCK_BACKSTOP", deterministic_stop=False
        )
        without_colour = re.sub(r"\bbg-(success|warning|secondary|danger)\b", "", html)
        without_colour = re.sub(r"\btext-(success|warning|danger|muted)\b", "", without_colour)
        self.assertIn(
            "Not guaranteed reproducible",
            without_colour,
            "With every colour class stripped the state must still be stated "
            "in text.",
        )


class SchedulingPageProvenanceMarkupTests(TestCase):
    """The scheduling page carries the hooks showResults() writes into."""

    def test_results_panel_has_the_provenance_targets(self):
        from django.template.loader import get_template

        source = get_template("scheduler/scheduling.html").template.source

        for element_id in (
            "result-hash",
            "result-fingerprint",
            "result-determinism-warning",
            "result-determinism-warning-text",
        ):
            self.assertIn(
                f'id="{element_id}"',
                source,
                f"showResults() writes into #{element_id}, which is not in the "
                "template.",
            )

    def test_the_warning_is_gated_on_an_explicit_false(self):
        """`=== false`, not falsy.

        A null ``deterministic_stop`` means "not recorded" and must not raise a
        warning. A truthiness check would warn on null and cry wolf on every
        pre-0063 schedule.
        """
        from django.template.loader import get_template

        source = get_template("scheduler/scheduling.html").template.source
        self.assertIn(
            "result.deterministic_stop === false",
            source,
            "The warning must be gated on a strict === false so that a null "
            "(not recorded) does not trigger it.",
        )

    def test_it_names_the_authoritative_check_and_says_advisory(self):
        from django.template.loader import get_template

        source = get_template("scheduler/scheduling.html").template.source
        self.assertIn("check_determinism", source)
        self.assertIn("advisory", source.lower())

    def test_provenance_is_written_without_innerhtml(self):
        """Escaping: textContent / setAttribute only, never innerHTML.

        Stronger than the manual ``<``/``>`` replacement ``showError`` needs,
        because nothing here builds markup.
        """
        from django.template.loader import get_template

        source = get_template("scheduler/scheduling.html").template.source
        start = source.index("function showDeterminismProvenance")
        body = source[start : source.index("\n    }", start)]
        self.assertNotIn(
            "innerHTML",
            body,
            "showDeterminismProvenance must not use innerHTML; hashes and "
            "fingerprints go in via textContent / setAttribute.",
        )
        self.assertIn("textContent", body)
