"""
Well Rejection Analysis Module
Provides detailed analysis of why wells are rejected during optimization
"""

from decimal import Decimal
from datetime import datetime, date
import logging
from typing import Dict, List, Any, Tuple
import pandas as pd

logger = logging.getLogger(__name__)


class WellRejectionAnalyzer:
    """Analyzes wells that couldn't be assigned and provides detailed rejection reasons"""
    
    def __init__(self, wells_df: pd.DataFrame, rigs_df: pd.DataFrame, base_start_date: date):
        self.wells_df = wells_df
        self.rigs_df = rigs_df
        self.base_start_date = base_start_date
        
    def analyze_well_rejection(self, well_name: str, assigned_wells: List[str] | None = None) -> str:
        """
        Provide comprehensive analysis of why a well was rejected
        
        Args:
            well_name: Name of the well to analyze
            assigned_wells: List of wells that were successfully assigned
            
        Returns:
            Detailed rejection reason string
        """
        if assigned_wells is None:
            assigned_wells = []
            
        well = self.wells_df[self.wells_df['name'] == well_name].iloc[0]
        
        reasons = []
        
        # 1. Check compatibility with all rigs
        compatible_rigs = []
        incompatible_reasons = []
        
        for _, rig in self.rigs_df.iterrows():
            compatibility_issues = self._check_rig_compatibility(well, rig)
            if not compatibility_issues:
                compatible_rigs.append(rig['name'])
            else:
                incompatible_reasons.extend([f"{rig['name']}: {issue}" for issue in compatibility_issues])
        
        if not compatible_rigs:
            reasons.append(f"TECHNICAL INCOMPATIBILITY: No compatible rigs available.")
            reasons.extend(incompatible_reasons[:3])  # Show top 3 specific issues
            return " | ".join(reasons)
        
        # 2. Check timing constraints
        timing_issues = self._check_timing_constraints(well, compatible_rigs)
        if timing_issues:
            reasons.append(f"TIMING CONSTRAINTS: {timing_issues}")
        
        # 3. Check if it's a cost optimization decision
        cost_analysis = self._analyze_cost_factors(well, compatible_rigs, assigned_wells)
        if cost_analysis:
            reasons.append(f"COST OPTIMIZATION: {cost_analysis}")
        
        # 4. Check capacity/utilization issues
        capacity_analysis = self._analyze_capacity_utilization(well, compatible_rigs, assigned_wells)
        if capacity_analysis:
            reasons.append(f"CAPACITY UTILIZATION: {capacity_analysis}")
        
        # 5. Check priority vs other wells
        priority_analysis = self._analyze_priority_conflicts(well, assigned_wells)
        if priority_analysis:
            reasons.append(f"PRIORITY CONFLICT: {priority_analysis}")
        
        # 6. If no specific reason found, provide general analysis
        if not reasons:
            reasons.append(f"OPTIMIZATION DECISION: Well was compatible but not selected due to overall project optimization constraints.")
            if compatible_rigs:
                reasons.append(f"Compatible rigs available: {', '.join(compatible_rigs[:3])}")
        
        return " | ".join(reasons)
    
    def _check_rig_compatibility(self, well: pd.Series, rig: pd.Series) -> List[str]:
        """Check technical compatibility between well and rig"""
        issues = []
        
        # Horsepower check
        well_hp = float(well.get('rig_capacity_required_hp', 0))
        rig_hp = float(rig.get('rig_capacity_hp', 0))
        if rig_hp < well_hp:
            issues.append(f"Insufficient HP (need {well_hp}, has {rig_hp})")
        
        # Depth check
        well_depth = float(well.get('depth', 0))
        rig_depth = float(rig.get('drilling_capacity_m', 0))
        if rig_depth < well_depth:
            issues.append(f"Insufficient depth capacity (need {well_depth}m, has {rig_depth}m)")
        
        # BOP Stack check
        well_bop = float(well.get('bop_stack', 0))
        rig_bop = float(rig.get('bop_stack', 0))
        if rig_bop < well_bop:
            issues.append(f"Insufficient BOP stack (need {well_bop}, has {rig_bop})")
        
        # TDS check
        well_tds = str(well.get('tds_requirement', 'N')).upper()
        rig_tds = str(rig.get('tds_availability', 'N')).upper()
        if well_tds == 'Y' and rig_tds != 'Y':
            issues.append("TDS required but not available")
        
        # Rig type compatibility
        well_footprint = str(well.get('footprint', '')).strip()
        rig_type = str(rig.get('rig_type', '')).strip()
        if well_footprint and rig_type and well_footprint != rig_type:
            issues.append(f"Rig type mismatch (need {well_footprint}, rig is {rig_type})")
        
        return issues
    
    def _check_timing_constraints(self, well: pd.Series, compatible_rigs: List[str]) -> str:
        """Check if timing constraints prevented assignment"""
        well_rtd = pd.to_datetime(well['rtd']).date()
        well_duration = int(well.get('duration', 0))
        
        available_days = 0
        timing_issues = []
        
        for _, rig in self.rigs_df[self.rigs_df['name'].isin(compatible_rigs)].iterrows():
            rig_start = pd.to_datetime(rig['start_date']).date()
            rig_end = pd.to_datetime(rig['end_date']).date()
            
            # Check if RTD is after rig availability ends
            if well_rtd > rig_end:
                timing_issues.append(f"{rig['name']} ends before RTD")
                continue
            
            # Check if there's enough time for drilling
            effective_start = max(well_rtd, rig_start)
            available_window = (rig_end - effective_start).days + 1
            available_days = max(available_days, available_window)
            
            if available_window < well_duration:
                timing_issues.append(f"{rig['name']} has only {available_window} days (need {well_duration})")
        
        if timing_issues:
            if available_days == 0:
                return f"No rig available after RTD ({well_rtd.strftime('%Y-%m-%d')})"
            else:
                return f"Insufficient time window (max {available_days} days available, need {well_duration})"
        
        return ""
    
    def _analyze_cost_factors(self, well: pd.Series, compatible_rigs: List[str], assigned_wells: List[str]) -> str:
        """Analyze if cost considerations led to rejection"""
        well_duration = int(well.get('duration', 0))
        well_priority = str(well.get('priority', 'MEDIUM')).upper()
        
        # Find the cheapest compatible rig
        compatible_rig_costs = []
        for _, rig in self.rigs_df[self.rigs_df['name'].isin(compatible_rigs)].iterrows():
            daily_cost = float(rig.get('daily_cost_inr', 0))
            total_cost = daily_cost * well_duration
            compatible_rig_costs.append((rig['name'], total_cost))
        
        if compatible_rig_costs:
            cheapest_rig, cheapest_cost = min(compatible_rig_costs, key=lambda x: x[1])
            avg_cost = sum(cost for _, cost in compatible_rig_costs) / len(compatible_rig_costs)
            
            cost_factors = []
            
            # High cost analysis
            if cheapest_cost > avg_cost * 1.5:
                cost_factors.append(f"High drilling cost (₹{cheapest_cost:,.0f} on cheapest rig {cheapest_rig})")
            
            # Priority vs cost trade-off
            if well_priority == 'LOW':
                cost_factors.append("Low priority well with cost constraints")
            elif well_priority == 'MEDIUM' and cheapest_cost > 1000000:  # 10 Lakh threshold
                cost_factors.append("Medium priority well exceeds cost threshold")
            
            # Long duration penalty
            if well_duration > 30:
                cost_factors.append(f"Long duration ({well_duration} days) increases project timeline")
            
            return " & ".join(cost_factors) if cost_factors else ""
        
        return ""
    
    def _analyze_capacity_utilization(self, well: pd.Series, compatible_rigs: List[str], assigned_wells: List[str]) -> str:
        """Analyze capacity and utilization factors"""
        well_duration = int(well.get('duration', 0))
        
        # Check if rigs are heavily utilized
        if len(assigned_wells) > len(self.rigs_df) * 3:  # More than 3 wells per rig on average
            return "High rig utilization - no capacity for additional wells"
        
        # Check for specific rig capacity issues
        capacity_issues = []
        for rig_name in compatible_rigs:
            rig = self.rigs_df[self.rigs_df['name'] == rig_name].iloc[0]
            rig_duration = (pd.to_datetime(rig['end_date']) - pd.to_datetime(rig['start_date'])).days + 1
            
            if well_duration > rig_duration * 0.8:  # Takes more than 80% of rig's available time
                capacity_issues.append(f"{rig_name} would be {(well_duration/rig_duration)*100:.0f}% utilized")
        
        return " & ".join(capacity_issues) if capacity_issues else ""
    
    def _analyze_priority_conflicts(self, well: pd.Series, assigned_wells: List[str]) -> str:
        """Analyze if priority conflicts led to rejection"""
        well_priority = str(well.get('priority', 'MEDIUM')).upper()
        
        if not assigned_wells:
            return ""
        
        # Check priorities of assigned wells
        assigned_well_priorities = []
        for assigned_well in assigned_wells:
            if assigned_well in self.wells_df['name'].values:
                priority = str(self.wells_df[self.wells_df['name'] == assigned_well]['priority'].iloc[0]).upper()
                assigned_well_priorities.append(priority)
        
        high_priority_assigned = assigned_well_priorities.count('HIGH')
        medium_priority_assigned = assigned_well_priorities.count('MEDIUM')
        
        priority_analysis = []
        
        if well_priority == 'LOW':
            if high_priority_assigned > 0 or medium_priority_assigned > 3:
                priority_analysis.append("Low priority well displaced by higher priority wells")
        elif well_priority == 'MEDIUM':
            if high_priority_assigned > 2:
                priority_analysis.append("Medium priority well displaced by multiple high priority wells")
        
        return " & ".join(priority_analysis) if priority_analysis else ""
    
    def get_well_summary_data(self, well_name: str) -> Dict[str, Any]:
        """Get summary data for a well for display purposes"""
        if well_name not in self.wells_df['name'].values:
            return {}
        
        well = self.wells_df[self.wells_df['name'] == well_name].iloc[0]
        
        return {
            'depth_m': float(well.get('depth', 0)),
            'duration_days': int(well.get('duration', 0)),
            'priority': str(well.get('priority', 'MEDIUM')).upper(),
            'hp_required': float(well.get('rig_capacity_required_hp', 0)),
            'bop_required': float(well.get('bop_stack', 0)),
            'tds_required': str(well.get('tds_requirement', 'N')).upper() == 'Y',
            'rtd': pd.to_datetime(well['rtd']).date().strftime('%Y-%m-%d') if pd.notna(well['rtd']) else 'N/A'
        }
