"""Scenario builders for the deterministic-schedule-fix harness.

Every builder in this module creates **real database rows** — ``CompanyCode``,
``RigBuildingNorm``, ``RigBuildingAdjustment``, ``Rig``, ``Well`` and
``WellPairDistance`` — and then returns the optimizer input dicts by reading
those rows back through the *same* queryset call the production endpoint uses::

    scheduler/views.py:1911-1913
        rigs  = Rig.objects.filter(id__in=...).order_by('name', 'id')
        wells = Well.objects.filter(id__in=...).order_by('name', 'id')
        rigs_data  = list(rigs.values())
        wells_data = list(wells.values())

That matters for this spec.  ``DrillingScheduler._calculate_ilm_days_matrix``
(``scheduler/optimization.py:722-816``) only takes the real Data-Management ILM
path when the rig row exists **and** carries a ``rig_building_norm`` **and** a
``location``; otherwise it silently falls back to the ``_get_ilm_days``
formula at ``:2168``.  Falling back would bypass ``calculate_ilm_days``
(``scheduler/views.py:10755``) and with it the ``RigBuildingAdjustment``
ordering hazard the harness is meant to probe, so the builders always populate
the norm, the location and the ``WellPairDistance`` cache.

All generated values come from a seeded ``random.Random`` so a scenario is
itself reproducible.  If the scenario varied between runs, a repeat-run
determinism measurement would be meaningless.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from random import Random
from typing import Any, Dict, List, Optional, Tuple

from scheduler.models import (
    CompanyCode,
    Rig,
    RigBuildingAdjustment,
    RigBuildingNorm,
    Well,
    WellPairDistance,
)

# Financial year used throughout the harness.  Matches the FY strings the
# scheduling page produces (``parse_financial_year`` in scheduler/models.py).
FY_LABEL = "2024-25"
FY_START = date(2024, 4, 1)
FY_END = date(2025, 3, 31)

#: FY string to send to ``POST /api/schedules/create_schedule/``.
#:
#: ``FY_LABEL`` above is the page's display form and is **not** parseable:
#: ``parse_financial_year`` (``scheduler/models.py:167-206``) requires
#: ``end_year == start_year + 1``, so ``"2024-25"`` raises ``ValueError``.  The
#: endpoint catches that and falls back to running with *no* FY constraints
#: (``scheduler/views.py:1948-1950``), which also moves ``base_start_date``
#: (``optimization.py:516-527``) and would silently make an API-driven
#: observation incomparable with a direct ``DrillingScheduler`` observation of
#: the same scenario.  Tests that drive the HTTP layer must use this form so the
#: FY window matches ``FY_START`` / ``FY_END`` exactly.
FY_API_LABEL = "2024-2025"


@dataclass
class Scenario:
    """Everything a test needs to drive ``DrillingScheduler``."""

    location: CompanyCode
    rigs: List[Rig]
    wells: List[Well]
    rigs_data: List[Dict[str, Any]]
    wells_data: List[Dict[str, Any]]
    fy_start_date: date = FY_START
    fy_end_date: date = FY_END
    adjustments: List[RigBuildingAdjustment] = field(default_factory=list)

    @property
    def num_pairs(self) -> int:
        return len(self.rigs) * len(self.wells)

    def scheduler_kwargs(self) -> Dict[str, Any]:
        """Keyword arguments mirroring ``views.create_schedule``'s call."""
        return {
            "fy_start_date": self.fy_start_date,
            "fy_end_date": self.fy_end_date,
        }


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in **metres**.

    Deliberately the same formula as
    ``DrillingScheduler._haversine_distance`` (scheduler/optimization.py:711)
    so the cached ``WellPairDistance`` values agree with the distance matrix
    the optimizer computes for itself.  ``WellPairDistance.distance_km`` stores
    metres despite its name — see the field's help_text and the ``distance_m``
    read at ``scheduler/optimization.py:789``.
    """
    radius_km = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * radius_km * math.asin(math.sqrt(a)) * 1000.0


def create_location(name: str = "Harness Asset", suffix: str = "H1") -> CompanyCode:
    """Create the ``CompanyCode`` row every other row hangs off.

    ``CompanyCode.save()`` title-cases ``location``, so read the value back
    from the instance rather than assuming what was passed in.
    """
    return CompanyCode.objects.create(
        fund_centre=f"FC-{suffix}",
        company_code=f"CC-{suffix}",
        cost_centre=f"COST-{suffix}",
        category="Asset",
        name=name,
        city="Testville",
        state="Teststate",
        location=name,
        is_active=True,
    )


def create_rig_building_norm(
    location: CompanyCode,
    rig_name: str,
    days: int = 10,
    rig_type: str = "Fixed",
) -> RigBuildingNorm:
    """Base rig-building norm.  Without this, ILM falls back to the formula."""
    return RigBuildingNorm.objects.create(
        location=location,
        rig_name=rig_name,
        days=days,
        top_drive=True,
        rig_type=rig_type,
    )


def create_ilm_adjustment_rules(
    location: CompanyCode, per_unit_days: Decimal = Decimal("1.00")
) -> List[RigBuildingAdjustment]:
    """A small but representative set of ILM adjustment rules.

    Chosen so ``calculate_ilm_days`` actually branches on distance: a short-hop
    ``replace`` rule, a long-haul ``add`` rule and a ``per_unit`` rule.  Every
    rule has a distinct ``priority`` so this set is *not* itself an ordering
    hazard — the tied-rule hazard is probed separately by
    ``create_tied_adjustment_pair``.

    ``per_unit_days`` scales how strongly distance feeds into the ILM gap.
    Raising it couples the circuit routing to the well-count tier (a rig fits
    fewer wells if it visits them in a bad order), which is what makes a model
    stay open rather than settling on its first incumbent.
    """
    rules = [
        RigBuildingAdjustment.objects.create(
            location=location,
            condition="Rig dragged within 25 m radius for adjacent well",
            category="cluster_movement",
            adjustment_type="replace",
            adjustment_value=Decimal("2.00"),
            adjustment_display="2 days",
            min_distance=None,
            max_distance=Decimal("25.00"),
            priority=100,
            is_active=True,
        ),
        RigBuildingAdjustment.objects.create(
            location=location,
            condition="Road transportation beyond 25 km",
            category="transportation",
            adjustment_type="add",
            adjustment_value=Decimal("1.00"),
            adjustment_display="+1 day",
            min_distance=Decimal("25000.00"),
            max_distance=None,
            priority=50,
            is_active=True,
        ),
        RigBuildingAdjustment.objects.create(
            location=location,
            condition="Additional haul time per 50 km beyond 25 km",
            category="transportation",
            adjustment_type="per_unit",
            adjustment_value=per_unit_days,
            adjustment_display=f"+{per_unit_days} day per 50 km",
            unit="50 km",
            min_distance=Decimal("25000.00"),
            max_distance=None,
            priority=40,
            is_active=True,
        ),
    ]
    return rules


#: The two tied rules, keyed by label.  Identical ``priority`` **and**
#: ``category``, both ``replace``, both matching every distance — so the only
#: thing separating them is the order the database hands them back.
TIED_RULE_SPECS: Dict[str, Decimal] = {
    "X": Decimal("2.00"),
    "Y": Decimal("7.00"),
}


def tied_rule_pk(label: str, pk_group: int = 0) -> uuid.UUID:
    """Deterministic primary key for a tied rule, ordered by label.

    ``RigBuildingAdjustment.id`` is a ``UUIDField`` defaulting to
    ``uuid.uuid4``, so primary keys are **random**, not insertion-ordered.  The
    total ordering task 5.3 installs is ``('-priority', 'category', 'id')``, so
    with unpinned keys the tie would be broken by ``os.urandom`` — the
    order-independence test would then pass or fail by coin toss rather than
    measure anything.  Pinning the keys makes the two halves of the comparison
    genuinely the *same rule set*, leaving insertion order as the only variable,
    which is exactly what clause 2.10 is about.

    ``pk_group`` separates one call's pair from another's (primary keys are
    unique table-wide, so two locations cannot reuse the same pair).  Within a
    group the label's position in ``sorted(TIED_RULE_SPECS)`` decides the key,
    so ``X`` always sorts before ``Y`` whichever order they were inserted in.

    Integer order is preserved by PostgreSQL, which compares ``uuid`` as a
    byte-wise comparison of the big-endian 16-byte value — the same order
    ``UUID(int=...)`` implies.
    """
    labels = sorted(TIED_RULE_SPECS)
    if label not in labels:
        raise KeyError(f"unknown tied-rule label {label!r}; expected one of {labels}")
    return uuid.UUID(f"1d250000-0000-4000-8000-{pk_group:06d}{labels.index(label):06d}")


def create_tied_adjustment_pair(
    location: CompanyCode,
    order: tuple = ("X", "Y"),
    priority: int = 100,
    category: str = "cluster_movement",
    pk_group: int = 0,
) -> List[RigBuildingAdjustment]:
    """Insert the same two tied ``replace`` rules in a chosen order.

    ``calculate_ilm_days`` applies the first matching ``replace`` rule it sees
    and then latches ``base_replaced = True``
    (``scheduler/views.py:10831-10839``), so whichever of these two the
    database hands back first decides the ILM value.  The fetch is ordered only
    by ``('-priority', 'category')`` (``scheduler/views.py:10791``), which does
    not separate them.

    ``order`` controls **insertion** order only.  The rule *set* is identical
    either way — same conditions, same values, same priority, same category and
    (via ``tied_rule_pk``) the same *relative* primary-key order — which is what
    makes the comparison a clean test of order-dependence rather than a
    comparison of two different rule sets.
    """
    created = []
    for label in order:
        value = TIED_RULE_SPECS[label]
        created.append(
            RigBuildingAdjustment.objects.create(
                id=tied_rule_pk(label, pk_group=pk_group),
                location=location,
                condition=f"Tied rule {label} - replace base norm",
                category=category,
                adjustment_type="replace",
                adjustment_value=value,
                adjustment_display=f"{value} days",
                min_distance=None,
                max_distance=None,
                priority=priority,
                is_active=True,
            )
        )
    return created


def create_rig(
    location: CompanyCode,
    name: str,
    *,
    norm_days: int = 10,
    rig_type: str = "Fixed",
    start_date: date = FY_START,
    end_date: date = FY_END,
    rig_capacity_hp: int = 2000,
    drilling_capacity_m: int = 5000,
    daily_cost_inr: Decimal = Decimal("1500000.00"),
    ilm_cost_fixed: Decimal = Decimal("5000000.00"),
    ilm_cost_per_km: Decimal = Decimal("25000.00"),
    ilm_cost_cluster: Decimal = Decimal("1000000.00"),
    bop_stack: int = 5000,
    tds_availability: str = "Y",
) -> Rig:
    norm = create_rig_building_norm(
        location, rig_name=name, days=norm_days, rig_type=rig_type
    )
    return Rig.objects.create(
        name=name,
        location=location,
        asset_id="HARNESS",
        rig_type=rig_type,
        start_date=start_date,
        end_date=end_date,
        rig_capacity_hp=rig_capacity_hp,
        daily_cost_inr=daily_cost_inr,
        drilling_capacity_m=drilling_capacity_m,
        crew_availability="OK",
        hpht_suitability="N",
        ilm_cost_fixed=ilm_cost_fixed,
        ilm_cost_per_km=ilm_cost_per_km,
        ilm_cost_cluster=ilm_cost_cluster,
        bop_stack=bop_stack,
        tds_availability=tds_availability,
        rig_building_norm=norm,
    )


def create_well(
    location: CompanyCode,
    name: str,
    sn: int,
    *,
    duration: int = 30,
    latitude: float = 20.0,
    longitude: float = 78.0,
    depth: int = 3000,
    rig_capacity_required_hp: int = 1000,
    bop_stack: int = 3000,
    rtd: date = FY_START,
    priority: str = "MEDIUM",
    tds_requirement: str = "N",
    drl_days: Optional[int] = None,
    pt_days: int = 0,
) -> Well:
    if drl_days is None:
        drl_days = duration - pt_days
    return Well.objects.create(
        sn=sn,
        location=location,
        asset_id="HARNESS",
        name=name,
        field_name="Harness Field",
        well_type="Dev",
        well_profile="VE",
        depth=depth,
        rig_capacity_required_hp=rig_capacity_required_hp,
        drl_days=drl_days,
        pt_days=pt_days,
        duration=duration,
        latitude=Decimal(str(round(latitude, 6))),
        longitude=Decimal(str(round(longitude, 6))),
        rtd=rtd,
        bop_stack=bop_stack,
        tds_requirement=tds_requirement,
        footprint="Fixed",
        priority=priority,
    )


def create_well_pair_distances(
    location: CompanyCode, rigs: List[Rig], wells: List[Well]
) -> int:
    """Populate the ``WellPairDistance`` cache the optimizer reads at
    ``scheduler/optimization.py:781-790``.

    One row per rig per unordered well pair, which is how the Data Management
    module writes them.  The optimizer fans each row out into both directions
    of ``distance_cache``.
    """
    rows: List[WellPairDistance] = []
    for rig in rigs:
        for i, w1 in enumerate(wells):
            for w2 in wells[i + 1 :]:
                distance_m = _haversine_m(
                    float(w1.latitude),
                    float(w1.longitude),
                    float(w2.latitude),
                    float(w2.longitude),
                )
                rows.append(
                    WellPairDistance(
                        location=location,
                        rig=rig,
                        well_1=w1,
                        well_2=w2,
                        distance_km=Decimal(str(round(distance_m, 2))),
                    )
                )
    WellPairDistance.objects.bulk_create(rows, batch_size=500)
    return len(rows)


@dataclass
class OverlappingDistanceScenario:
    """A scenario whose ``WellPairDistance`` rows collide on a well-name pair."""

    scenario: Scenario
    pair: Tuple[str, str]
    #: Distances in metres, keyed by the pinned primary key of the row.
    distances_by_pk: Dict[uuid.UUID, float]
    #: The pk that the total ordering makes the winner (see the builder).
    winning_pk: uuid.UUID

    @property
    def winning_distance_m(self) -> float:
        return self.distances_by_pk[self.winning_pk]

    @property
    def losing_distance_m(self) -> float:
        (losing,) = [pk for pk in self.distances_by_pk if pk != self.winning_pk]
        return self.distances_by_pk[losing]


#: Distances (metres) for the two colliding rows.  Chosen either side of every
#: band ``create_ilm_adjustment_rules`` discriminates on, so the two rows give
#: unmistakably different ILM days: 10 m hits the ``replace`` rule (2 days),
#: 60 km hits ``add`` (+1) and ``per_unit`` (+0.7 at 1 day / 50 km).
_OVERLAP_NEAR_M = Decimal("10.00")
_OVERLAP_FAR_M = Decimal("60000.00")


def build_overlapping_well_pair_distance_scenario(
    suffix: str = "WPD",
) -> OverlappingDistanceScenario:
    """Two ``WellPairDistance`` rows covering the same **well-name** pair.

    ``DrillingScheduler._calculate_ilm_days_matrix`` filters the table on
    ``rig=rig_obj`` only — no location predicate and no restriction to the wells
    actually being scheduled — and then fans every row it gets into *both*
    directions of a name-keyed ``distance_cache``.  Two rows whose
    ``(well_1.name, well_2.name)`` agree therefore overwrite each other, and
    before task 5.4 the survivor was whichever the database happened to return
    last.

    The collision is built the way it can really occur: ``Well.name`` carries no
    ``unique=True``, so a **third** well row shares ``WELL-001``'s name while
    taking no part in the schedule.  Its distance row is loaded anyway (the
    filter cannot exclude it) and lands on the same cache key as the scheduled
    well's row.  ``unique_together = ['rig', 'well_1', 'well_2']`` is respected —
    the two rows reference different ``Well`` objects.

    ``WellPairDistance.Meta.ordering`` already sorts on
    ``('location__company_code', 'rig__name', 'well_1__name', 'well_2__name')``,
    which is why the fetch is not arbitrary in general — but every one of those
    keys **ties** for these two rows, which is precisely the gap ``id`` closes.

    Primary keys are pinned for the same reason as ``tied_rule_pk``: the pk is a
    random UUID by default, so an unpinned scenario would have a random winner.
    The far row is given the **greater** key deliberately: the loader iterates in
    ascending order and each row overwrites the previous, so the last row in the
    total order wins.  Encoding that in the fixture makes the expectation a
    stated consequence of the ordering rather than an observation.
    """
    location = create_location(name=f"Harness {suffix}", suffix=suffix)
    adjustments = create_ilm_adjustment_rules(location)
    rig = create_rig(location, name="RIG-01", norm_days=10)

    scheduled = [
        create_well(location, name="WELL-001", sn=6000, duration=20, latitude=20.00),
        create_well(location, name="WELL-002", sn=6001, duration=20, latitude=20.40),
    ]
    # Shares WELL-001's name, is never scheduled, and still contributes a row.
    shadow = create_well(location, name="WELL-001", sn=6002, duration=20, latitude=21.90)

    near_pk = uuid.UUID("d1570000-0000-4000-8000-000000000001")
    far_pk = uuid.UUID("d1570000-0000-4000-8000-000000000002")
    WellPairDistance.objects.bulk_create(
        [
            WellPairDistance(
                id=near_pk,
                location=location,
                rig=rig,
                well_1=scheduled[0],
                well_2=scheduled[1],
                distance_km=_OVERLAP_NEAR_M,
            ),
            WellPairDistance(
                id=far_pk,
                location=location,
                rig=rig,
                well_1=shadow,
                well_2=scheduled[1],
                distance_km=_OVERLAP_FAR_M,
            ),
        ]
    )

    rigs_data, wells_data = _read_back([rig], scheduled)
    scenario = Scenario(
        location=location,
        rigs=[rig],
        wells=scheduled,
        rigs_data=rigs_data,
        wells_data=wells_data,
        adjustments=adjustments,
    )
    return OverlappingDistanceScenario(
        scenario=scenario,
        pair=("WELL-001", "WELL-002"),
        distances_by_pk={
            near_pk: float(_OVERLAP_NEAR_M),
            far_pk: float(_OVERLAP_FAR_M),
        },
        winning_pk=far_pk,
    )


# ---------------------------------------------------------------------------
# Scenario assembly
# ---------------------------------------------------------------------------


def _read_back(rigs: List[Rig], wells: List[Well]):
    """Re-read the rows exactly as ``views.create_schedule`` does.

    Using ``.values()`` off an ``order_by('name', 'id')`` queryset guarantees the
    harness feeds the optimizer the same dict shape (including ``id``,
    ``location_id`` and ``Decimal`` columns) that production feeds it.  The
    second key tracks task 5.1: production orders on ``('name', 'id')`` because
    ``Well.name`` is not unique.
    """
    rig_qs = Rig.objects.filter(id__in=[r.id for r in rigs]).order_by("name", "id")
    well_qs = Well.objects.filter(id__in=[w.id for w in wells]).order_by("name", "id")
    return list(rig_qs.values()), list(well_qs.values())


def build_open_scenario(
    num_rigs: int = 5,
    num_wells: int = 26,
    seed: int = 20240401,
    *,
    with_adjustments: bool = True,
    suffix: str = "OPEN",
    norm_days_choices: tuple = (8, 10, 12),
    duration_choices: tuple = (35, 45, 55, 65, 75),
    per_unit_days: Decimal = Decimal("1.00"),
    stagger_windows: bool = False,
    spread_degrees: float = 1.5,
) -> Scenario:
    """A scenario the solver is **not** expected to close inside a short limit.

    That is the regime the bug lives in: clause 1.1 of ``bugfix.md`` is about
    runs that stop on the wall-clock limit before proving optimality, so the
    harness has to sit there rather than in the easy proven-optimal regime.

    Hardness comes from three things, not from raw size alone:

    * **Oversubscription.**  Total well duration plus ILM gaps exceeds the
      available rig-days, so the Big-M well-count tier is genuinely contested
      and the solver has to reason about *which* wells to drop.
    * **Heterogeneous rigs.**  Capacity, depth rating and daily cost differ per
      rig, so the cost tier cannot be satisfied by a symmetric argument.
    * **Geographic spread.**  Wells are scattered, so ILM days (and therefore
      the circuit gap constraints) vary per pair and per rig.
    """
    rng = Random(seed)
    location = create_location(name=f"Harness {suffix}", suffix=suffix)

    adjustments: List[RigBuildingAdjustment] = []
    if with_adjustments:
        adjustments = create_ilm_adjustment_rules(location, per_unit_days=per_unit_days)

    rigs: List[Rig] = []
    for i in range(num_rigs):
        # Deliberately heterogeneous: capacity, depth rating and cost all move.
        if stagger_windows:
            # Staggered availability makes the packing problem non-symmetric
            # in time, so "which rig" and "which order" stop being separable.
            win_start = FY_START + timedelta(days=(i * 17) % 60)
            win_end = FY_END - timedelta(days=(i * 11) % 40)
        else:
            win_start, win_end = FY_START, FY_END
        rigs.append(
            create_rig(
                location,
                name=f"RIG-{i + 1:02d}",
                norm_days=rng.choice(list(norm_days_choices)),
                rig_type="Mobile" if i % 2 else "Fixed",
                start_date=win_start,
                end_date=win_end,
                rig_capacity_hp=rng.choice([1500, 2000, 2500]),
                drilling_capacity_m=rng.choice([3500, 4500, 5500]),
                daily_cost_inr=Decimal(str(rng.randrange(900_000, 2_100_000, 50_000))),
                ilm_cost_fixed=Decimal(str(rng.randrange(3_000_000, 8_000_000, 500_000))),
                ilm_cost_per_km=Decimal(str(rng.randrange(15_000, 45_000, 5_000))),
                bop_stack=rng.choice([3500, 5000, 7000]),
                tds_availability="Y" if i % 3 else "N",
            )
        )

    wells: List[Well] = []
    for i in range(num_wells):
        # Spread so pair distances land in every band the adjustment rules
        # discriminate on (<25 m, >25 km, >50 km).
        lat = 20.0 + rng.uniform(0.0, spread_degrees)
        lon = 78.0 + rng.uniform(0.0, spread_degrees)
        wells.append(
            create_well(
                location,
                name=f"WELL-{i + 1:03d}",
                sn=1000 + i,
                duration=rng.choice(list(duration_choices)),
                latitude=lat,
                longitude=lon,
                depth=rng.choice([2800, 3400, 4000, 4800]),
                rig_capacity_required_hp=rng.choice([1200, 1600, 2000]),
                bop_stack=rng.choice([3000, 4500, 6500]),
                rtd=FY_START + timedelta(days=rng.choice([0, 10, 25, 45])),
                priority=rng.choice(["HIGH", "MEDIUM", "MEDIUM", "LOW"]),
                tds_requirement=rng.choice(["N", "N", "Y"]),
            )
        )

    create_well_pair_distances(location, rigs, wells)
    rigs_data, wells_data = _read_back(rigs, wells)

    return Scenario(
        location=location,
        rigs=rigs,
        wells=wells,
        rigs_data=rigs_data,
        wells_data=wells_data,
        adjustments=adjustments,
    )


#: Calibrated configuration for the repeat-run harness.
#:
#: Sizing is not arbitrary — it was measured.  ``bugfix.md`` clause 1.1 is about
#: runs that stop before proving optimality, so the model has to stay open, and
#: the *incumbent has to still be improving* at the moment the stop lands.  A
#: model that finds a good incumbent quickly and then plateaus is reproducible
#: by accident: stopping at 2.6 or at 4.4 units of work returns the same
#: schedule, so no amount of CPU load changes the answer.
#:
#: Measured objective-versus-work curve for this configuration (see the task 1
#: notes) shows distinct schedules at roughly 0.8, 1.4, 2.6-4.4, 7.4 and 12.4
#: deterministic-time units, i.e. the answer keeps moving across the whole
#: budget.  That is the regime the bug lives in.
#:
#: Hardness comes from coupling the routing to the well-count tier: large,
#: distance-scaled ILM gaps mean the number of wells that fit on a rig depends
#: on the order they are visited in, which turns the count tier into a
#: routing problem rather than a simple packing one.
HARD_OPEN_CONFIG: Dict[str, Any] = {
    "num_rigs": 6,
    "num_wells": 40,
    "norm_days_choices": (18, 24, 30),
    "per_unit_days": Decimal("3.00"),
    "duration_choices": (26, 33, 39, 44, 51, 58),
    "stagger_windows": True,
    "spread_degrees": 3.0,
}

#: Wall-clock limit paired with ``HARD_OPEN_CONFIG``.  Short enough to keep the
#: harness usable, long enough that the solver is well past its first incumbent
#: and still improving.  Measured on an idle machine: ``FEASIBLE``,
#: ~3.44 deterministic-time units, ~5.8 s wall, 23 of 40 wells assigned.
HARD_OPEN_TIME_LIMIT_SECONDS = 6


def build_hard_open_scenario(suffix: str = "HARD", seed: int = 20240401) -> Scenario:
    """The calibrated scenario used by the repeat-run determinism harness."""
    return build_open_scenario(suffix=suffix, seed=seed, **HARD_OPEN_CONFIG)


def build_symmetric_tie_scenario(
    num_wells: int = 5,
    seed: int = 5150,
    *,
    suffix: str = "TIE",
) -> Scenario:
    """5 wells, 2 **identical** rigs — the model from ``bugfix.md``.

    The two rigs agree on every attribute that reaches the model (capacity,
    depth rating, BOP, TDS, window, daily cost, ILM cost, norm days); only the
    name differs.  Swapping equal-duration wells between them therefore yields
    a genuinely different schedule at an identical objective value, which is
    what makes the tied set large.

    Wells are given equal durations and clustered coordinates for the same
    reason: it removes the cost and duration tiers as tie-breakers and leaves
    the decision to tier 4, which is where ``START_TIME_WEIGHT = 1`` and
    ``RIG_WELL_ORDER_WEIGHT = 1`` (``scheduler/optimization.py:1358-1359``)
    fail to impose an order.
    """
    rng = Random(seed)
    location = create_location(name=f"Harness {suffix}", suffix=suffix)
    create_ilm_adjustment_rules(location)

    rigs = [
        create_rig(
            location,
            name=f"RIG-{i + 1:02d}",
            norm_days=10,
            rig_type="Fixed",
            rig_capacity_hp=2500,
            drilling_capacity_m=5500,
            daily_cost_inr=Decimal("1200000.00"),
            ilm_cost_fixed=Decimal("4000000.00"),
            ilm_cost_per_km=Decimal("20000.00"),
            bop_stack=7000,
            tds_availability="Y",
        )
        for i in range(2)
    ]

    wells = [
        create_well(
            location,
            name=f"WELL-{i + 1:03d}",
            sn=2000 + i,
            duration=30,
            latitude=20.0 + 0.02 * i,
            longitude=78.0 + 0.02 * i,
            depth=3000,
            rig_capacity_required_hp=1500,
            bop_stack=4000,
            rtd=FY_START,
            priority="MEDIUM",
            tds_requirement="N",
        )
        for i in range(num_wells)
    ]
    del rng  # scenario is fully explicit; kept for signature symmetry

    create_well_pair_distances(location, rigs, wells)
    rigs_data, wells_data = _read_back(rigs, wells)

    return Scenario(
        location=location,
        rigs=rigs,
        wells=wells,
        rigs_data=rigs_data,
        wells_data=wells_data,
    )


def build_duplicate_well_name_scenario(suffix: str = "DUP") -> Scenario:
    """Two wells sharing a ``name``.

    ``Well.name`` carries no ``unique=True`` (``scheduler/models.py:394``)
    while the whole optimizer keys on it — ``self.assignments[(wid, rid)]``
    at ``scheduler/optimization.py:891``, the distance and ILM matrices
    indexed by name, and ``wells_df.loc[wells_df["name"] == wid].iloc[0]``
    at ``:1809``.  ``sn`` is unique so the two rows are legitimately distinct
    database records.
    """
    location = create_location(name=f"Harness {suffix}", suffix=suffix)
    create_ilm_adjustment_rules(location)

    rigs = [create_rig(location, name="RIG-01")]
    wells = [
        create_well(location, name="WELL-001", sn=3000, duration=20, latitude=20.00),
        # Same name, different sn / coordinates / duration -> a real collision.
        create_well(location, name="WELL-001", sn=3001, duration=25, latitude=20.30),
        create_well(location, name="WELL-002", sn=3002, duration=20, latitude=20.60),
    ]

    create_well_pair_distances(location, rigs, wells)
    rigs_data, wells_data = _read_back(rigs, wells)

    return Scenario(
        location=location,
        rigs=rigs,
        wells=wells,
        rigs_data=rigs_data,
        wells_data=wells_data,
    )


# ---------------------------------------------------------------------------
# The ¬isBugCondition scenario (task 2 — preservation goldens)
# ---------------------------------------------------------------------------

#: Time limit for the unique-optimum scenario.  10 s is not a guess: it is the
#: floor ``ScheduleCreateSerializer`` enforces (``min_value=10``,
#: ``scheduler/serializers.py:296-300``), so the same number can drive both the
#: direct-``DrillingScheduler`` observations and the HTTP save-path
#: observation.  The model is tiny and proves optimality in well under a
#: second, so the limit never binds.
UNIQUE_OPTIMUM_TIME_LIMIT_SECONDS = 10

#: Wells for ``build_unique_optimum_scenario``, in name order.
#:
#: ``depth`` and ``tds_requirement`` are the load-bearing columns: they make the
#: well -> rig mapping a *hard* consequence of the compatibility forbids at
#: ``scheduler/optimization.py:1049-1060`` rather than an outcome of the cost
#: tier.  See the builder's docstring for why that matters.
_UNIQUE_OPTIMUM_WELLS = (
    # name,        sn,   duration, depth, tds, hp_required, lat,   lon
    ("WELL-001", 4000, 41, 5200, "N", 1500, 20.00, 78.00),
    ("WELL-002", 4001, 33, 5000, "N", 1500, 20.25, 78.10),
    ("WELL-003", 4002, 37, 3200, "Y", 1500, 20.60, 78.35),
    ("WELL-004", 4003, 29, 3000, "Y", 1500, 20.90, 78.05),
    # Structurally impossible: no rig in this scenario has 9000 HP, so the
    # capacity forbid at ``optimization.py:1053`` pins every assignment
    # variable for this well to 0.  It is therefore unassigned in *every*
    # feasible solution, which keeps the well-count tier uncontested (see the
    # builder docstring) while still exercising the unassigned-well save path
    # and ``WellRejectionAnalyzer``.
    ("WELL-005", 4004, 25, 3000, "N", 9000, 21.10, 78.50),
)


def build_unique_optimum_scenario(suffix: str = "UNIQ") -> Scenario:
    """A model that proves ``OPTIMAL`` with a **unique** optimum.

    This is the ``NOT isBugCondition(X)`` regime from ``bugfix.md``, and it is
    the regime Property 2 (Preservation) is defined over: a request that already
    closes to a proven, unique optimum must return exactly the schedule,
    objective value and ``schedule_hash`` it returns today.  Everything about
    the scenario is chosen to make the optimum unique **by construction**, so
    the golden baseline is a property of the inputs rather than a lucky solve.

    Uniqueness is engineered tier by tier against the objective at
    ``scheduler/optimization.py:1385-1430``:

    * **Tier 1 (well count) is uncontested.**  Four wells are assignable and
      ``WELL-005`` is impossible for every rig, so every feasible solution
      assigns exactly four wells.  No "which well do we drop" choice exists,
      which is the single largest source of tied optima in this model.
    * **Tier 2 (cost) does not choose the mapping either — compatibility
      does.**  ``WELL-001`` and ``WELL-002`` are deeper (5200 m, 5000 m) than
      ``RIG-02``'s ``drilling_capacity_m`` of 4000, so only ``RIG-01`` can take
      them.  ``WELL-003`` and ``WELL-004`` require TDS and only ``RIG-02`` has
      it.  The well -> rig mapping is therefore forced by the hard forbids at
      ``:1049-1060``, not selected by an objective that might tie.  Two rigs end
      up used, which is what the save path's *per-rig* ``sequence_order``
      derivation needs in order to be meaningfully exercised.
    * **Tiers 3 and 4 choose the order within each rig, and durations break
      it.**  Each rig gets exactly two wells, so the only remaining freedom is
      which of the two goes first.  Both orders have the same ILM cost (the
      distance matrix at ``:697-716`` is symmetric and so is the ILM days
      matrix), so tier 2 and tier 3 tie and tier 4a decides: minimising
      ``start_time_sum`` puts the *shorter* well first, because the second
      well's start is the first well's duration plus the ILM gap.  Durations are
      pairwise distinct (41 / 33 on ``RIG-01``, 37 / 29 on ``RIG-02``), so
      shortest-first is a strict, unique choice.

    Uniqueness is **verified, not assumed** —
    ``test_preservation.UniqueOptimumScenarioTests`` enumerates every schedule
    attaining the optimal objective and requires the count to be exactly 1.  If
    a future OR-Tools version or model change breaks that, the test fails and
    says so rather than quietly capturing one member of a tied set as "the"
    golden.

    Coordinates and every other value are hard-coded rather than drawn from a
    seeded ``Random``.  The other builders in this module are seeded, which is
    enough for them; a golden fixture is compared for years, so this one leaves
    nothing to a generator at all.
    """
    location = create_location(name=f"Harness {suffix}", suffix=suffix)
    adjustments = create_ilm_adjustment_rules(location)

    rigs = [
        # Cheap, deep-capable, no TDS -> the only rig for WELL-001/002.
        create_rig(
            location,
            name="RIG-01",
            norm_days=10,
            rig_type="Fixed",
            rig_capacity_hp=2500,
            drilling_capacity_m=5500,
            daily_cost_inr=Decimal("1200000.00"),
            ilm_cost_fixed=Decimal("4000000.00"),
            ilm_cost_per_km=Decimal("20000.00"),
            bop_stack=7000,
            tds_availability="N",
        ),
        # Dearer, shallow-rated, TDS-equipped -> the only rig for WELL-003/004.
        create_rig(
            location,
            name="RIG-02",
            norm_days=12,
            rig_type="Mobile",
            rig_capacity_hp=2500,
            drilling_capacity_m=4000,
            daily_cost_inr=Decimal("1500000.00"),
            ilm_cost_fixed=Decimal("4500000.00"),
            ilm_cost_per_km=Decimal("22000.00"),
            bop_stack=7000,
            tds_availability="Y",
        ),
    ]

    wells = [
        create_well(
            location,
            name=name,
            sn=sn,
            duration=duration,
            latitude=lat,
            longitude=lon,
            depth=depth,
            rig_capacity_required_hp=hp,
            bop_stack=3000,
            rtd=FY_START,
            priority="MEDIUM",
            tds_requirement=tds,
        )
        for name, sn, duration, depth, tds, hp, lat, lon in _UNIQUE_OPTIMUM_WELLS
    ]

    create_well_pair_distances(location, rigs, wells)
    rigs_data, wells_data = _read_back(rigs, wells)

    return Scenario(
        location=location,
        rigs=rigs,
        wells=wells,
        rigs_data=rigs_data,
        wells_data=wells_data,
        adjustments=adjustments,
    )
