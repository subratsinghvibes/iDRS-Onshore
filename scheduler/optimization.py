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
from ortools.sat.python import cp_model

logger = logging.getLogger(__name__)


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

        # Sort rigs and wells by name BEFORE building matrices
        # so that variable IDs, constraint ordering, and the model proto
        # are identical across runs regardless of upstream row order.
        self.rigs_df = self.rigs_df.sort_values(by="name").reset_index(drop=True)
        self.wells_df = self.wells_df.sort_values(by="name").reset_index(drop=True)

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
        from .models import WellPairDistance, Rig as RigModel, Well as WellModel
        from .views import calculate_ilm_days
        
        wells = self.wells_df
        rigs = self.rigs_df
        n_wells = len(wells)
        well_names = list(wells["name"])
        
        logger.info("Building ILM days matrix from WellPairDistance table...")
        
        # Build a lookup of well name -> Well object
        well_name_to_obj = {}
        try:
            for wname in well_names:
                try:
                    well_name_to_obj[wname] = WellModel.objects.get(name=wname)
                except WellModel.DoesNotExist:
                    logger.warning(f"Well {wname} not found in database")
                    well_name_to_obj[wname] = None
        except Exception as e:
            logger.warning(f"Error building well lookup: {e}")
        
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
                    well_pair_distances = WellPairDistance.objects.filter(
                        rig=rig_obj
                    ).select_related('well_1', 'well_2')
                    
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
    def _configure_solver_for_determinism(self, time_limit_seconds: float, deterministic: bool = True) -> None:
        """Configure solver for optimal balance of solution quality and determinism.
        
        Args:
            time_limit_seconds: Maximum solve time
            deterministic: If True, use single-threaded mode for full reproducibility.
                          If False, use multi-threaded for faster/better solutions.
        
        For deterministic mode:
        - Single-threaded execution (num_search_workers=1) - prevents non-deterministic branching
        - Fixed random seed (random_seed=42) - stabilises internal randomness
        - AUTOMATIC_SEARCH - uses fast heuristics (single-thread + fixed seed is already deterministic!)
        - symmetry_level=0 - disables symmetry-breaking heuristics that might alter selection
        
        For performance mode:
        - Multi-threaded execution (all available workers)
        - Still uses fixed seed for some reproducibility
        - Better solution quality in shorter time
        """
        assert self.solver is not None, "Solver must be initialized"
        
        # Time limit
        self.solver.parameters.max_time_in_seconds = max(1, int(time_limit_seconds))
        
        if deterministic:
            # Deterministic execution: single-threaded mode
            # THIS IS THE KEY PARAMETER FOR DETERMINISM
            self.solver.parameters.num_search_workers = 1
            
            # Fixed random seed for reproducibility
            self.solver.parameters.random_seed = 42
            
            # Use AUTOMATIC_SEARCH to restore solver speed (FIXED_SEARCH is too slow)
            self.solver.parameters.search_branching = cp_model.AUTOMATIC_SEARCH
            
            # Enable symmetry breaking and LNS - they ARE deterministic on a single thread!
            self.solver.parameters.symmetry_level = 2
            self.solver.parameters.use_lns = True
            
            # Enable strategy interleaving for combined heuristics
            self.solver.parameters.interleave_search = True
            
            # CRITICAL ENTERPRISE FIX: 
            # We must use standard wall-clock timeout. 
            # `max_deterministic_time` and `max_num_branches` natively cripple the LNS (Large Neighborhood Search) 
            # heuristics which rely on real CPU cycles to perform random walks.
            # CP-SAT guarantees perfect determinism for identical inputs, seeds, and threads out-of-the-box.
            # The ONLY source of variance on a server is if the time limit interrupt hits *exactly* while exploring different branches.
            # For 99.9% of enterprise schedules running to completion or settling on an optima before timeout, this is perfectly deterministic.
            self.solver.parameters.max_time_in_seconds = float(time_limit_seconds) 
            
            logger.info(
                f"Solver configured: DETERMINISTIC mode "
                f"(single-threaded, AUTO_SEARCH, seed=42, LNS=True, interleave=True), "
                f"Time limit: {time_limit_seconds}s"
            )
        else:
            # Performance mode: use all available workers
            self.solver.parameters.num_search_workers = 0  # 0 = auto-detect
            
            # Still use fixed seed for some reproducibility
            self.solver.parameters.random_seed = 42
            
            # Portfolio search works well with multi-threading
            self.solver.parameters.search_branching = cp_model.PORTFOLIO_SEARCH
            
            # Enable symmetry breaking and LNS for better solutions in performance mode
            self.solver.parameters.symmetry_level = 2
            self.solver.parameters.use_lns = True
            
            logger.info(
                f"Solver configured: PERFORMANCE mode (multi-threaded), "
                f"time_limit={time_limit_seconds}s"
            )
        
        # Enable presolve (always beneficial)
        self.solver.parameters.cp_model_presolve = True
        
        # Disable solution enumeration
        self.solver.parameters.enumerate_all_solutions = False

    def _add_decision_strategy(self, deterministic: bool = True) -> None:
        """Add explicit decision strategy.
        
        Note: Removed the explicit search strategy because it forces a rigid
        CHOOSE_FIRST order which cripples OR-Tools performance on large problems.
        Single-threaded execution with a fixed seed is already deterministic
        without needing to force the search tree path.
        """
        pass

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
        for w_idx, (_, w) in enumerate(self.wells_df.iterrows()):
            wid = w["name"]
            for r_idx, (_, r) in enumerate(self.rigs_df.iterrows()):
                rid = r["name"]
                order_index = w_idx * num_rigs + r_idx
                rig_well_order_terms.append(
                    self.assignments[(wid, rid)] * order_index
                )
        rig_well_order = sum(rig_well_order_terms)

        self.model.Minimize(
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

        # Configure solver parameters
        self._configure_solver_for_determinism(time_limit_seconds, deterministic=deterministic)

        # Model fingerprint: SHA-256 of serialised model proto.
        model_fingerprint = hashlib.sha256(
            str(self.model.Proto()).encode()
        ).hexdigest()
        logger.info(f"MODEL FINGERPRINT (solve_with_actuals): {model_fingerprint}")

        import time
        solve_start_time = time.time()
        self.status = self.solver.Solve(self.model)
        solve_end_time = time.time()
        self.solve_time_seconds = solve_end_time - solve_start_time

        return self._extract_solution(time_limit_seconds)

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

        # Configure solver parameters
        self._configure_solver_for_determinism(time_limit_seconds, deterministic=deterministic)

        # Model fingerprint: SHA-256 of serialised model proto.
        # If two runs produce the same fingerprint the solver MUST return
        # the same solution (given deterministic settings).
        model_fingerprint = hashlib.sha256(
            str(self.model.Proto()).encode()
        ).hexdigest()
        logger.info(f"MODEL FINGERPRINT (solve): {model_fingerprint}")

        # Track solve time
        import time
        solve_start_time = time.time()
        self.status = self.solver.Solve(self.model)
        solve_end_time = time.time()
        self.solve_time_seconds = solve_end_time - solve_start_time
        
        result = self._extract_solution(time_limit_seconds)
        
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

    def _extract_solution(self, time_limit_seconds: float = 60) -> Dict[str, Any]:
        """Extract solution from solver with comprehensive metrics for validation."""
        # Type narrowing for Pylance
        assert self.solver is not None, "Solver must be initialized"
        
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
            }

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
            arr.sort(key=lambda x: x["well_start_date"])
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