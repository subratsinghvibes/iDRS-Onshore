"""
Well Rejection Analyzer
Provides analysis for why wells couldn't be scheduled
"""
import pandas as pd
from datetime import datetime


class WellRejectionAnalyzer:
    """Analyzes why wells were rejected during optimization"""
    
    def __init__(self, wells_df, rigs_df, schedule_start_date):
        """
        Initialize the analyzer
        
        Args:
            wells_df: DataFrame with well data
            rigs_df: DataFrame with rig data
            schedule_start_date: Start date of the schedule
        """
        self.wells_df = wells_df
        self.rigs_df = rigs_df
        self.schedule_start_date = schedule_start_date
    
    def analyze_well_rejection(self, well_name, assigned_well_names):
        """
        Analyze why a well was rejected
        
        Args:
            well_name: Name of the rejected well
            assigned_well_names: List of wells that were successfully assigned
        
        Returns:
            str: Reason for rejection
        """
        try:
            # Find the well in the dataframe
            well_data = self.wells_df[self.wells_df['name'] == well_name]
            
            if well_data.empty:
                return "Well not found in data"
            
            well = well_data.iloc[0]
            
            # Check various rejection reasons
            reasons = []
            
            # Check if rig capacity available
            required_capacity = well.get('rig_capacity_required_hp', 0)
            matching_rigs = self.rigs_df[self.rigs_df['capacity_hp'] >= required_capacity]
            
            if matching_rigs.empty:
                reasons.append(f"No rigs with sufficient capacity (requires {required_capacity} HP)")
            
            # Check priority
            priority = well.get('priority', 'MEDIUM')
            if priority == 'LOW':
                reasons.append("Low priority - limited resources")
            
            # Check asset constraints
            asset_id = well.get('asset_id', '')
            if asset_id:
                asset_rigs = self.rigs_df[self.rigs_df['asset_id'] == asset_id]
                if asset_rigs.empty:
                    reasons.append(f"No rigs available in asset {asset_id}")
            
            # Check timing constraints
            earliest_start = well.get('earliest_start_date')
            latest_completion = well.get('latest_completion_date')
            
            if earliest_start and latest_completion:
                if isinstance(earliest_start, str):
                    earliest_start = pd.to_datetime(earliest_start).date()
                if isinstance(latest_completion, str):
                    latest_completion = pd.to_datetime(latest_completion).date()
                
                duration = well.get('duration', 0)
                time_window = (latest_completion - earliest_start).days
                
                if time_window < duration:
                    reasons.append(f"Insufficient time window ({time_window} days vs {duration} days required)")
            
            # If no specific reason found
            if not reasons:
                reasons.append("Insufficient resources or scheduling conflicts")
            
            return "; ".join(reasons)
            
        except Exception as e:
            return f"Analysis error: {str(e)}"
