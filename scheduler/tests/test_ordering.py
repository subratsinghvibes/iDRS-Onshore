"""Input-ordering and duplicate-key hazards.

**Property 5: Total input ordering — duplicates are rejected, ties are ordered.**

*Validates: Requirements 2.9, 2.10*

Two hazards from ``bugfix.md`` are probed here.  Both are secondary to the
stopping criterion but both are independently capable of making the same request
produce a different model, and therefore a different schedule:

* **Clause 1.6 / 1.7 — duplicate well names.**  ``Well.name`` has no
  ``unique=True`` (``scheduler/models.py:394``) while the whole optimizer keys
  on it.
* **Clause 1.8 — tied ``RigBuildingAdjustment`` rows.**  The rule fetch was
  ordered only by ``('-priority', 'category')``, and ``calculate_ilm_days``
  applies the first matching ``replace`` rule then latches ``base_replaced``, so
  the row order decides the ILM value that feeds the model's gap constraints.
  Task 5.3 makes the key total by appending ``id``.
* **Clause 2.10 — overlapping ``WellPairDistance`` rows.**  The optimizer's
  fetch filters on ``rig=`` alone and fans each row into both directions of a
  *name*-keyed cache, so two rows sharing a well-name pair overwrite each other.
  Task 5.4 makes that fetch order total as well.

As everywhere in this harness, the assertions state the expected behaviour, so
these tests are re-run unchanged by tasks 5.5 and 6.4.
"""

from __future__ import annotations

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in
from django.test import TestCase
from django.urls import reverse

from scheduler.models import RigBuildingAdjustment, Schedule
from scheduler.optimization import DrillingScheduler, DuplicateWellNameError
from scheduler.signals import log_user_login
from scheduler.views import calculate_ilm_days

from .factories import (
    FY_API_LABEL,
    TIED_RULE_SPECS,
    UNIQUE_OPTIMUM_TIME_LIMIT_SECONDS,
    build_duplicate_well_name_scenario,
    build_overlapping_well_pair_distance_scenario,
    create_location,
    create_rig,
    create_tied_adjustment_pair,
    tied_rule_pk,
)


class DuplicateWellNameTests(TestCase):
    """A run whose well set contains two wells with the same name."""

    def test_duplicate_well_names_are_rejected_naming_the_duplicates(self):
        """*Validates: Requirements 2.9*

        Expected behaviour (clause 2.9): the run is refused with a message
        naming the duplicates.  Today it is not refused at that point — the
        duplicate silently collapses two wells into one set of model variables,
        and the pipeline then dies further downstream with an error that names
        no well at all.  On failure this test reports both facts.
        """
        scenario = build_duplicate_well_name_scenario()
        duplicate_names = sorted(
            {
                well["name"]
                for well in scenario.wells_data
                if [w["name"] for w in scenario.wells_data].count(well["name"]) > 1
            }
        )
        self.assertTrue(
            duplicate_names, "the scenario must actually contain a duplicate name"
        )

        scheduler = DrillingScheduler(
            [dict(r) for r in scenario.rigs_data],
            [dict(w) for w in scenario.wells_data],
            **scenario.scheduler_kwargs(),
        )

        try:
            scheduler.preprocess_data()
        except Exception as exc:  # noqa: BLE001 - any typed rejection is fine
            message = str(exc)
            missing = [name for name in duplicate_names if name not in message]
            self.assertFalse(
                missing,
                f"{type(exc).__name__} was raised but its message does not name "
                f"the duplicate well(s) {missing}: {message!r}. Clause 2.9 "
                "requires the duplicates to be named so the user can fix the "
                "input.",
            )
            return

        # Not rejected. Document exactly how the collision manifests instead.
        expected_pairs = len(scenario.wells) * len(scenario.rigs)
        scheduler.setup_variables()
        actual_pairs = len(scheduler.assignments)

        downstream = "pipeline completed without error"
        try:
            scheduler.add_constraints()
            scheduler.add_ilm_constraints()
        except Exception as exc:  # noqa: BLE001 - recording, not handling
            downstream = f"{type(exc).__name__}: {exc}"

        self.fail(
            "\n".join(
                [
                    "preprocess_data() accepted a well set containing duplicate "
                    f"name(s) {duplicate_names}.",
                    f"  wells supplied            : {len(scenario.wells_data)}",
                    f"  distinct names            : "
                    f"{len({w['name'] for w in scenario.wells_data})}",
                    f"  assignment variables built: {actual_pairs} "
                    f"(one per well x rig would be {expected_pairs})",
                    f"  downstream outcome        : {downstream}",
                    "",
                    "Clause 2.9 requires the run to be rejected with the "
                    "duplicates named. Instead the duplicate wells collapse onto "
                    "one set of variables via self.assignments[(wid, rid)] "
                    "(scheduler/optimization.py:891) and the failure, if any, "
                    "surfaces later without naming a well.",
                ]
            )
        )

    def test_the_rejection_is_the_typed_error_and_fires_before_any_work(self):
        """*Validates: Requirements 2.9*

        The test above accepts *any* typed rejection, because it was written
        before the fix existed.  This one pins the contract task 6.1 actually
        delivers: the specific ``DuplicateWellNameError``, carrying the
        duplicate names as data as well as in the message, raised before the
        distance and ILM matrices are built — i.e. before any expensive work,
        and before the collision can reach ``self.assignments``.
        """
        scenario = build_duplicate_well_name_scenario(suffix="DUPT")

        scheduler = DrillingScheduler(
            [dict(r) for r in scenario.rigs_data],
            [dict(w) for w in scenario.wells_data],
            **scenario.scheduler_kwargs(),
        )

        with self.assertRaises(DuplicateWellNameError) as caught:
            scheduler.preprocess_data()

        self.assertEqual(caught.exception.duplicate_names, ["WELL-001"])
        self.assertIn("WELL-001", str(caught.exception))
        # Fired before the matrices — nothing downstream of the check ran.
        self.assertTrue(
            scheduler.distance_matrix.empty,
            "the rejection must fire before _calculate_distance_matrix",
        )
        self.assertFalse(
            scheduler.ilm_days_matrix,
            "the rejection must fire before _calculate_ilm_days_matrix",
        )

    def test_create_schedule_returns_400_and_leaves_no_schedule_row(self):
        """*Validates: Requirements 2.9*

        The API-boundary half of the fix (task 6.2).  The optimizer invariant is
        what makes the collision unreachable; this is what makes it actionable:
        an HTTP 400 naming the duplicates, raised *before* ``Schedule`` is
        created, so no ``FAILED`` row is left behind for the user to clean up.
        """
        scenario = build_duplicate_well_name_scenario(suffix="DUPA")

        user = get_user_model().objects.create_superuser(
            username="ordering-harness",
            email="ordering@example.invalid",
            password="harness-not-a-real-password",
        )
        # ``force_login`` sends ``user_logged_in`` with a bare HttpRequest whose
        # ``method`` is None, which the login-audit receiver writes into a NOT
        # NULL column and poisons the test's atomic block.  Same workaround, and
        # same reasoning, as ``test_preservation.SavePathPreservationTests``.
        user_logged_in.disconnect(log_user_login)
        self.addCleanup(user_logged_in.connect, log_user_login)
        self.client.force_login(user)

        schedules_before = Schedule.objects.count()

        response = self.client.post(
            reverse("schedule-create-schedule"),
            data={
                "name": "Duplicate Well Names",
                "financial_year": FY_API_LABEL,
                "rig_ids": [str(rig.id) for rig in scenario.rigs],
                "well_ids": [str(well.id) for well in scenario.wells],
                "time_limit_seconds": UNIQUE_OPTIMUM_TIME_LIMIT_SECONDS,
            },
            content_type="application/json",
        )

        self.assertEqual(
            response.status_code,
            400,
            "create_schedule must refuse a duplicate-named well set with 400, "
            f"got {response.status_code}: {response.content!r}",
        )
        body = response.json()
        self.assertIn(
            "WELL-001",
            body.get("error", ""),
            f"the 400 body must name the duplicate well(s): {body!r}",
        )
        self.assertEqual(body.get("duplicate_well_names"), ["WELL-001"])
        self.assertEqual(
            Schedule.objects.count(),
            schedules_before,
            "the rejection must fire before Schedule.objects.create(), so no "
            "FAILED schedule row may be left behind",
        )


class TiedAdjustmentRuleTests(TestCase):
    """Two ``RigBuildingAdjustment`` rows tied on ``priority`` and ``category``."""

    #: Distance both tied rules match.  Above the 25 m cluster band and below
    #: nothing, so the tied ``replace`` rules are the only ones in play.
    DISTANCE_M = 40_000.0
    NORM_DAYS = 10

    def _ilm_days_for_insertion_order(
        self, order: tuple, suffix: str, pk_group: int
    ) -> dict:
        """Create the rule pair in ``order`` and evaluate ``calculate_ilm_days``.

        ``pk_group`` keeps the two halves' primary keys distinct (a pk is unique
        table-wide) while preserving the *relative* key order within each pair,
        so the only thing that differs between the halves is the order the rows
        were inserted in.  See ``factories.tied_rule_pk`` for why the keys have
        to be pinned at all.
        """
        location = create_location(name=f"Tie Order {suffix}", suffix=suffix)
        rig = create_rig(location, name=f"RIG-{suffix}", norm_days=self.NORM_DAYS)
        rules = create_tied_adjustment_pair(location, order=order, pk_group=pk_group)
        result = calculate_ilm_days(
            rig, self.DISTANCE_M, location, self.NORM_DAYS
        )
        lowest_id_rule = min(rules, key=lambda r: r.id)
        return {
            "order": order,
            "ilm_days": result.get("ilm_days"),
            "applied": [r["condition"] for r in result.get("applied_rules", [])],
            "lowest_id_condition": lowest_id_rule.condition,
            "lowest_id_value": float(lowest_id_rule.adjustment_value),
            # Reported with the *production* key, so the printout shows the order
            # calculate_ilm_days actually sees.
            "fetch_order": list(
                RigBuildingAdjustment.objects.filter(location=location)
                .order_by("-priority", "category", "id")
                .values_list("condition", "adjustment_value")
            ),
        }

    def test_ilm_days_do_not_depend_on_rule_insertion_order(self):
        """*Validates: Requirements 2.10*

        The rule *set* is identical in both halves — same conditions, same
        values, same ``priority``, same ``category``.  Only the order the rows
        were inserted in differs.  Clause 2.10 requires the resulting ILM days
        to be identical, because the ILM matrix feeds the model's gap
        constraints and therefore the schedule.
        """
        forward = self._ilm_days_for_insertion_order(("X", "Y"), "TO1", pk_group=1)
        reverse = self._ilm_days_for_insertion_order(("Y", "X"), "TO2", pk_group=2)

        print(
            "\n=== TIED RigBuildingAdjustment RULES ===\n"
            f"rule values            : {dict(TIED_RULE_SPECS)}\n"
            f"insert X,Y -> ilm_days : {forward['ilm_days']} "
            f"applied={forward['applied']}\n"
            f"  fetch order          : {forward['fetch_order']}\n"
            f"  lowest-id rule       : {forward['lowest_id_condition']} "
            f"({forward['lowest_id_value']})\n"
            f"insert Y,X -> ilm_days : {reverse['ilm_days']} "
            f"applied={reverse['applied']}\n"
            f"  fetch order          : {reverse['fetch_order']}\n"
            f"  lowest-id rule       : {reverse['lowest_id_condition']} "
            f"({reverse['lowest_id_value']})"
        )

        self.assertEqual(
            forward["ilm_days"],
            reverse["ilm_days"],
            "calculate_ilm_days returned a different ILM value for the same set "
            "of adjustment rules purely because the rows were inserted in a "
            f"different order ({forward['ilm_days']} vs {reverse['ilm_days']}). "
            "order_by('-priority', 'category') does not separate two rules that "
            "tie on both keys, and the first matching 'replace' rule wins, so "
            "the row order decides the value. The ILM matrix feeds the circuit "
            "gap constraints, so this changes the model the solver sees. The "
            "fix (task 5.3) appends 'id', making the key total.",
        )

        # And the winner must be the one the total ordering names, not merely
        # *a* consistent one: ('-priority', 'category', 'id') puts the lower id
        # first and calculate_ilm_days applies the first matching 'replace' rule.
        for half, label in ((forward, "insert X,Y"), (reverse, "insert Y,X")):
            self.assertEqual(
                half["applied"],
                [half["lowest_id_condition"]],
                f"{label}: the applied rule should be the tied rule with the "
                f"lower id ({half['lowest_id_condition']!r}), because "
                "order_by('-priority', 'category', 'id') hands that one back "
                f"first. Applied instead: {half['applied']}.",
            )
            self.assertEqual(
                half["ilm_days"],
                half["lowest_id_value"],
                f"{label}: the ILM days should equal the lower-id rule's "
                f"adjustment_value ({half['lowest_id_value']}), got "
                f"{half['ilm_days']}.",
            )

        # Guard: the pinned keys must actually order X before Y in both halves,
        # or the two assertions above would be comparing different expectations.
        for pk_group in (1, 2):
            self.assertLess(
                tied_rule_pk("X", pk_group=pk_group),
                tied_rule_pk("Y", pk_group=pk_group),
                "tied_rule_pk must order X before Y within a pk_group",
            )

    def test_tied_rules_are_actually_tied(self):
        """Guard: the two probe rules must genuinely tie, or the test above is
        measuring nothing."""
        location = create_location(name="Tie Guard", suffix="TG")
        rules = create_tied_adjustment_pair(location, order=("X", "Y"))
        self.assertEqual(len({r.priority for r in rules}), 1)
        self.assertEqual(len({r.category for r in rules}), 1)
        self.assertEqual(len({r.adjustment_type for r in rules}), 1)
        self.assertEqual(
            len({r.adjustment_value for r in rules}),
            2,
            "the tied rules must disagree on their value, otherwise the order "
            "cannot be observed",
        )
        self.assertEqual(
            {r.adjustment_value for r in rules},
            set(TIED_RULE_SPECS.values()),
        )
        self.assertTrue(all(r.min_distance is None for r in rules))
        self.assertTrue(all(r.max_distance is None for r in rules))
        self.assertNotEqual(Decimal("0"), rules[0].adjustment_value)

class OverlappingWellPairDistanceTests(TestCase):
    """Two ``WellPairDistance`` rows covering the same well-**name** pair.

    ``_calculate_ilm_days_matrix`` filters the table on ``rig=`` only and writes
    *both* directions of every row into a name-keyed ``distance_cache``, so two
    rows whose ``(well_1.name, well_2.name)`` agree overwrite one another.  Task
    5.4 adds ``('well_1__name', 'well_2__name', 'id')`` so the survivor is named
    by the ordering instead of by the database.
    """

    REPEATS = 5

    def setUp(self):
        self.overlap = build_overlapping_well_pair_distance_scenario()
        self.scenario = self.overlap.scenario
        self.rig_name = self.scenario.rigs[0].name

    def _matrix_value(self, scheduler: DrillingScheduler) -> float:
        well_1, well_2 = self.overlap.pair
        return float(scheduler.ilm_days_matrix[self.rig_name].loc[well_1, well_2])

    def _fresh_scheduler(self) -> DrillingScheduler:
        return DrillingScheduler(
            [dict(r) for r in self.scenario.rigs_data],
            [dict(w) for w in self.scenario.wells_data],
            **self.scenario.scheduler_kwargs(),
        )

    def test_the_scenario_really_contains_an_overlap(self):
        """Guard: without a genuine collision the test below measures nothing."""
        self.assertEqual(len(self.overlap.distances_by_pk), 2)
        self.assertNotEqual(
            self.overlap.winning_distance_m,
            self.overlap.losing_distance_m,
            "the two colliding rows must disagree on distance, otherwise which "
            "one wins is unobservable",
        )

    def test_ilm_matrix_value_is_stable_across_repeated_builds(self):
        """*Validates: Requirements 2.10*

        Repeated ``_calculate_ilm_days_matrix()`` calls — and a fresh
        ``DrillingScheduler`` built from the same inputs — must all agree.
        """
        scheduler = self._fresh_scheduler()
        scheduler.preprocess_data()

        values = [self._matrix_value(scheduler)]
        for _ in range(self.REPEATS - 1):
            scheduler._calculate_ilm_days_matrix()
            values.append(self._matrix_value(scheduler))

        fresh = self._fresh_scheduler()
        fresh.preprocess_data()
        values.append(self._matrix_value(fresh))

        print(
            "\n=== OVERLAPPING WellPairDistance ROWS ===\n"
            f"pair                   : {self.overlap.pair}\n"
            f"colliding distances (m): winning={self.overlap.winning_distance_m} "
            f"losing={self.overlap.losing_distance_m}\n"
            f"ilm matrix values      : {values}"
        )

        self.assertEqual(
            len(set(values)),
            1,
            "the ILM matrix value for a well pair covered by two overlapping "
            f"WellPairDistance rows was not stable: {values}. Each row writes "
            "both directions into distance_cache, so an unordered fetch lets "
            "whichever row the database returns last decide the value.",
        )

    def test_the_surviving_row_is_the_one_the_total_ordering_names(self):
        """*Validates: Requirements 2.10*

        Stability alone could be an accident of one database's heap order.  The
        substantive claim is *which* row wins: the loader iterates in ascending
        ``('well_1__name', 'well_2__name', 'id')`` order and each row overwrites
        the previous, so the last row in that order — the greater ``id`` among
        the tied group — is the survivor.
        """
        scheduler = self._fresh_scheduler()
        scheduler.preprocess_data()

        rig = self.scenario.rigs[0]
        norm_days = rig.rig_building_norm.days
        expected = float(
            calculate_ilm_days(
                rig,
                self.overlap.winning_distance_m,
                self.scenario.location,
                norm_days,
            )["ilm_days"]
        )
        not_expected = float(
            calculate_ilm_days(
                rig,
                self.overlap.losing_distance_m,
                self.scenario.location,
                norm_days,
            )["ilm_days"]
        )
        self.assertNotEqual(
            expected,
            not_expected,
            "the two candidate distances must map to different ILM days",
        )
        self.assertAlmostEqual(
            self._matrix_value(scheduler),
            expected,
            places=6,
            msg="the surviving WellPairDistance row is not the one named by "
            "('well_1__name', 'well_2__name', 'id'); the fetch order is not "
            "total, so the overlap is being resolved by the database.",
        )
