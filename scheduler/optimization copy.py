"""
Intelligent Drilling Rig Scheduler (iDRS) – optimisation.py
Minimal edits from original:
 - setup_variables() now resets model/solver & variable dicts so model is rebuilt each run
 - solve() now runs full pipeline (preprocess_data -> setup_variables -> add_constraints -> add_ilm_constraints -> set_objective)
 - merge_wells_for_scenario(...) helper added for scenario re-runs
Other logic unchanged.
"""

from __future__ import annotations

import math
import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Tuple, Optional, Union

import pandas as pd
from ortools.sat.python import cp_model

logger = logging.getLogger(__name__)


class DrillingScheduler:
    """
    Main scheduler class implementing the iDRS_main.py logic while keeping the
    optimisation.py public surface compatible for the hosting app.
    """

    def __init__(self, rigs_data: Iterable[Dict[str, Any]], wells_data: Iterable[Dict[str, Any]], base_start_date: Optional[date] = None):
        # keep original input containers (we will normalize in preprocess_data)
        self.rigs_df = self._to_dataframe(rigs_data, kind="rigs")
        self.wells_df = self._to_dataframe(wells_data, kind="wells")

        if base_start_date is None:
            # default: earliest rig start (if start_date present)
            try:
                base_start_date = pd.to_datetime(self.rigs_df["start_date"]).dt.date.min()
            except Exception:
                base_start_date = date.today()
        self.base_start_date: date = base_start_date  # date (not datetime)

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
        self.distance_matrix: pd.DataFrame = pd.DataFrame()
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
    def preprocess_data(self) -> None:
        """Normalize types, compute rig windows & distance matrix."""
        # Dates
        try:
            if not pd.api.types.is_datetime64_any_dtype(self.rigs_df["start_date"]):
                self.rigs_df["start_date"] = pd.to_datetime(self.rigs_df["start_date"], errors="coerce", dayfirst=True)
            if not pd.api.types.is_datetime64_any_dtype(self.rigs_df["end_date"]):
                self.rigs_df["end_date"] = pd.to_datetime(self.rigs_df["end_date"], errors="coerce", dayfirst=True)
        except Exception:
            # if start/end missing or invalid, create simple defaults to avoid errors later
            self.rigs_df["start_date"] = pd.to_datetime(self.rigs_df.get("start_date", pd.Series([pd.Timestamp(datetime.today())] * len(self.rigs_df))))
            self.rigs_df["end_date"] = pd.to_datetime(self.rigs_df.get("end_date", pd.Series([pd.Timestamp(datetime.today() + timedelta(days=365))] * len(self.rigs_df))))

        if not pd.api.types.is_datetime64_any_dtype(self.wells_df["rtd"]):
            self.wells_df["rtd"] = pd.to_datetime(self.wells_df["rtd"], errors="coerce", dayfirst=True)

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

        # Distance matrix (km, Haversine)
        self._calculate_distance_matrix()

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

        # Horizon ~ twice longest rig window (guard against zero)
        try:
            self.horizon = int(max(1, self.rigs_df["duration_days"].max()) * 2)
        except Exception:
            self.horizon = 365 * 2

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

        logger.info("Core constraints added.")

    def add_ilm_constraints(self) -> None:
        """Pairwise ILM gap with order variable (prevents overlap + enforces travel/maintenance days)."""
        logger.info("Adding ILM sequencing constraints...")
        
        # Type narrowing for Pylance
        assert self.model is not None, "Model must be initialized before adding ILM constraints"
        
        if self.distance_matrix.empty:
            logger.warning("Distance matrix is empty; ILM gaps will be zero.")
        for _, r in self.rigs_df.iterrows():
            rid = r["name"]
            for _, wi in self.wells_df.iterrows():
                for _, wj in self.wells_df.iterrows():
                    if wi["name"] == wj["name"]:
                        continue
                    i, j = wi["name"], wj["name"]
                    ai = self.assignments[(i, rid)]
                    aj = self.assignments[(j, rid)]
                    si = self.start_times[(i, rid)]
                    sj = self.start_times[(j, rid)]
                    ei = self.end_times[(i, rid)]
                    ej = self.end_times[(j, rid)]

                    # Extract distance from matrix - .loc[scalar, scalar] returns scalar but Pylance needs help
                    if not self.distance_matrix.empty:
                        from typing import cast
                        dist = float(cast(float, self.distance_matrix.loc[i, j]))
                    else:
                        dist = 0.0
                    gap = int(self._get_ilm_days(dist))

                    order = self.model.NewBoolVar(f"ord_{i}_{j}_{rid}")
                    # If order is true => i before j
                    self.model.Add(sj >= ei + gap).OnlyEnforceIf([ai, aj, order])
                    # If order is false => j before i
                    self.model.Add(si >= ej + gap).OnlyEnforceIf([ai, aj, order.Not()])

    # --------------------------
    # Objective
    # --------------------------
    def set_objective(self) -> None:
        """Minimize project_end + ILM travel cost + penalties (as in iDRS_main)."""
        logger.info("Setting objective...")
        
        # Type narrowing for Pylance
        assert self.model is not None, "Model must be initialized before setting objective"
        
        transitions: Dict[Tuple[str, str, str], cp_model.IntVar] = {}
        for w1 in self.wells_df["name"]:
            for w2 in self.wells_df["name"]:
                if w1 == w2:
                    continue
                for _, r in self.rigs_df.iterrows():
                    rid = r["name"]
                    t = self.model.NewBoolVar(f"trans_{w1}_{w2}_{rid}")
                    transitions[(w1, w2, rid)] = t
                    self.model.Add(t <= self.assignments[(w1, rid)])
                    self.model.Add(t <= self.assignments[(w2, rid)])
                    self.model.Add(t >= self.assignments[(w1, rid)] + self.assignments[(w2, rid)] - 1)

        ilm_cost_terms = []
        for w1 in self.wells_df["name"]:
            for w2 in self.wells_df["name"]:
                if w1 == w2:
                    continue
                # Extract distance value - .loc[scalar, scalar] returns scalar but Pylance needs help
                if not self.distance_matrix.empty:
                    from typing import cast
                    dist = float(cast(float, self.distance_matrix.loc[w1, w2]))
                else:
                    dist = 0.0
                for _, r in self.rigs_df.iterrows():
                    rid = r["name"]
                    cost = float(r["ilm_cost_fixed"]) + float(r["ilm_cost_per_km"]) * dist
                    ilm_cost_terms.append(transitions[(w1, w2, rid)] * cost)

        self.project_end = self.model.NewIntVar(0, self.horizon, "project_end")
        for (_, _), e in self.end_times.items():
            self.model.Add(self.project_end >= e)

        avg_duration = float(self.wells_df["duration"].mean()) if len(self.wells_df) else 1.0
        unassigned_penalty = int(20_000_000 * avg_duration)
        high_priority_penalty = int(20_000_000 * avg_duration)

        num_unassigned = self.model.NewIntVar(0, len(self.wells_df), "num_unassigned")
        self.model.Add(num_unassigned == sum(self.unassigned_vars))
        num_high_unassigned = self.model.NewIntVar(0, len(self.wells_df), "num_high_unassigned")
        if self.high_priority_unassigned:
            self.model.Add(num_high_unassigned == sum(self.high_priority_unassigned))
        else:
            self.model.Add(num_high_unassigned == 0)

        self.model.Minimize(
            self.project_end
            + sum(ilm_cost_terms)
            + unassigned_penalty * num_unassigned
            + high_priority_penalty * num_high_unassigned
        )

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

    def solve_with_actuals(self, fixed_actuals: List[Dict[str, Any]], time_limit_seconds: int = 60) -> Dict[str, Any]:
        """Re-run optimization while pinning actuals (start/end) and using same core logic."""
        logger.info("Solving with actuals, count=%d", len(fixed_actuals) if fixed_actuals else 0)

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

        # Solver params
        self.solver.parameters.max_time_in_seconds = max(1, int(time_limit_seconds))
        self.solver.parameters.num_search_workers = 8
        self.solver.parameters.search_branching = cp_model.PORTFOLIO_SEARCH
        self.solver.parameters.cp_model_presolve = True
        self.solver.parameters.symmetry_level = 2
        self.solver.parameters.enumerate_all_solutions = False

        import time
        solve_start_time = time.time()
        self.status = self.solver.Solve(self.model)
        solve_end_time = time.time()
        self.solve_time_seconds = solve_end_time - solve_start_time

        return self._extract_solution()

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
    def solve(self, time_limit_seconds: int = 60, minimum_solve_time_seconds: Optional[int] = None) -> Dict[str, Any]:
        """
        For simplicity and to ensure re-runs are correct, the solve() method now
        runs the full pipeline (preprocess -> setup_variables -> add_constraints -> add_ilm_constraints -> set_objective)
        before calling the CP-SAT solver. This makes solve idempotent and safe to call multiple times.
        """
        logger.info(f"Solving with time_limit_seconds={time_limit_seconds} ...")

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

        # solver params
        self.solver.parameters.max_time_in_seconds = max(1, int(time_limit_seconds))
        self.solver.parameters.num_search_workers = 8
        self.solver.parameters.search_branching = cp_model.PORTFOLIO_SEARCH
        self.solver.parameters.cp_model_presolve = True
        self.solver.parameters.symmetry_level = 2
        self.solver.parameters.enumerate_all_solutions = False

        # Track solve time
        import time
        solve_start_time = time.time()
        self.status = self.solver.Solve(self.model)
        solve_end_time = time.time()
        self.solve_time_seconds = solve_end_time - solve_start_time
        
        return self._extract_solution()

    def _extract_solution(self) -> Dict[str, Any]:
        # Type narrowing for Pylance
        assert self.solver is not None, "Solver must be initialized"
        
        status_name = self.solver.StatusName(self.status) if hasattr(self.solver, "StatusName") else str(self.status)
        logger.info(f"Solver status: {status_name}")

        assignments: List[Dict[str, Any]] = []
        total_drilling_cost = 0.0

        if self.status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            for (wid, rid), a in self.assignments.items():
                if self.solver.Value(a) == 1:
                    w = self.wells_df.loc[self.wells_df["name"] == wid].iloc[0]
                    r = self.rigs_df.loc[self.rigs_df["name"] == rid].iloc[0]
                    s_day = int(self.solver.Value(self.start_times[(wid, rid)]))
                    e_day = int(self.solver.Value(self.end_times[(wid, rid)]))
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

            project_end_day = int(self.solver.Value(self.project_end)) if self.project_end is not None else 0
            project_end_date = self.base_start_date + timedelta(days=project_end_day)

            assigned_wells = {a["well"] for a in assignments}
            unassigned = [w for w in self.wells_df["name"].tolist() if w not in assigned_wells]

            self.results = {
                "status": status_name,
                "solver_status": status_name,  # Add solver status
                "solve_time_seconds": getattr(self, 'solve_time_seconds', 0),  # Add solve time
                "assignments": assignments,
                "unassigned_wells": unassigned,
                "total_drilling_cost": total_drilling_cost,
                "total_ilm_cost": sum(a.get("ilm_cost", 0) for a in assignments),
                "project_end_day": project_end_day,
                "project_end_date": project_end_date,
            }
        else:
            self.results = {
                "status": status_name, 
                "solver_status": status_name,  # Add solver status
                "solve_time_seconds": getattr(self, 'solve_time_seconds', 0),  # Add solve time
                "assignments": [], 
                "unassigned_wells": self.wells_df["name"].tolist()
            }

        return self.results

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
        if distance_km <= base_ilm_distance:
            return int(base_ilm_days)
        extra = math.ceil((distance_km - base_ilm_distance) / 10.0)
        return int(base_ilm_days + max(0, extra))

    def _get_ilm_cost(self, distance_km: float, rig_row: pd.Series) -> float:
        return float(rig_row["ilm_cost_fixed"]) + float(rig_row["ilm_cost_per_km"]) * float(distance_km)

    def _calculate_ilm_costs(self, assignments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not assignments:
            return assignments

        by_rig: Dict[str, List[Dict[str, Any]]] = {}
        for a in assignments:
            by_rig.setdefault(a["rig"], []).append(a)

        total_ilm_cost = 0.0
        for rid, arr in by_rig.items():
            arr.sort(key=lambda x: x["well_start_date"])
            rig_row = self.rigs_df.loc[self.rigs_df["name"] == rid].iloc[0]
            for i in range(1, len(arr)):
                prev = arr[i - 1]["well"]
                curr = arr[i]["well"]
                # Extract distance from matrix - .loc[scalar, scalar] returns scalar but Pylance needs help
                if not self.distance_matrix.empty:
                    from typing import cast
                    dist = float(cast(float, self.distance_matrix.loc[prev, curr]))
                else:
                    dist = 0.0
                cost = self._get_ilm_cost(dist, rig_row)
                arr[i]["ilm_cost"] = cost
                total_ilm_cost += cost

        self.results["total_ilm_cost"] = total_ilm_cost
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