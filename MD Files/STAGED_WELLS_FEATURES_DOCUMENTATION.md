# Staged Wells Features Documentation

This document explains the key features and automated calculations used in the Staged Wells Management page (`/staged-wells/`) and related ILM Cost calculations.

---

## Table of Contents

1. [Set Blank RTD Dates](#set-blank-rtd-dates)
2. [Auto Calculate Days Button](#auto-calculate-days-button)
3. [Auto-Population of Empty Fields](#auto-population-of-empty-fields)
4. [ILM Days Calculation](#ilm-days-calculation)

---

## Set Blank RTD Dates

### What It Does
The "Set Blank RTD Dates" feature allows users to bulk-set the Ready-To-Drill (RTD) date for all staged wells that currently have no RTD value assigned.

### How It Works

1. **Trigger**: Click the **"Set Blank RTD Dates"** button (yellow/warning colored) in the filter/action bar on the Staged Wells page.

2. **Process Flow**:
   - The system counts all wells where `rtd` field is null or empty
   - A modal dialog opens showing the count of wells to be updated
   - User selects a target RTD date (defaults to today's date)
   - On confirmation, the system sends a POST request to `/api/staged-wells/bulk-set-rtd/`

3. **Backend Logic** (`views.py`):
   ```python
   # The API endpoint receives:
   {
       "well_ids": [list of well IDs with blank RTD],
       "rtd": "YYYY-MM-DD"  # User-selected date
   }
   
   # Updates all specified wells with the new RTD date
   ```

4. **Result**:
   - All wells with previously blank RTD dates are updated to the specified date
   - Success message shows count of updated wells
   - Page automatically refreshes to show updated data

### Use Case
This is particularly useful when importing wells from CSV files where RTD dates may not be available initially but need to be set to a common future planning date.

---

## Auto Calculate Days Button

### What It Does
The "Auto-Calculate Days" button in the Complete Well Information modal calculates three critical fields:
- **DRL Days** (Drilling Days)
- **PT Days** (Production Testing Days)
- **Duration** (Total Days = DRL + PT)

### How It Works

#### Step 1: Input Requirements
- **Field Name** (required): The field/pool where the well is located
- **Well Profile**: Automatically detected or manually selected (VE=Vertical, DI=Directional, SD=Sidetrack)
- **Depth**: Well depth in meters (from CSV import)
- **Location**: Asset ID/location identifier

#### Step 2: DRL Days Calculation

The DRL Days calculation uses the **Drilling Benchmark** and **Daily Drilling Rate** tables:

```
DRL Days = Benchmark Days ± (Depth Difference / Daily Drilling Rate)
```

**Detailed Formula**:

1. **Find Matching Benchmark**:
   - Match by: location + field_name + well_category (profile)
   - Well depth must fall within `well_depth_start` and `well_depth_end` range
   - Get: `benchmark_days` and `drilling_depth` from the benchmark record

2. **Calculate Depth Difference**:
   ```
   depth_difference = benchmark_drilling_depth - actual_well_depth
   ```
   - Positive = well is shallower than benchmark
   - Negative = well is deeper than benchmark

3. **Find Daily Drilling Rate**:
   - Match by: location + field + depth range
   - Get: `per_day_depth` (meters drilled per day)

4. **Calculate Time Adjustment**:
   ```
   time_adjustment = |depth_difference| / per_day_depth
   ```

5. **Final DRL Days**:
   ```
   IF well is shallower (positive depth_difference):
       DRL_Days = benchmark_days - time_adjustment
   ELSE (well is deeper):
       DRL_Days = benchmark_days + time_adjustment
   
   DRL_Days = MAX(ceil(DRL_Days), 1)  # Round up, minimum 1 day
   ```

**Example Calculation**:
```
Well: VDEF at 1765m in VADATAL field (Directional profile)
Benchmark: depth_range=1725-2100m, drilling_depth=1870m, benchmark_days=19.5
Daily Rate: 50 m/day for VADATAL

Step 1: depth_difference = 1870 - 1765 = 105m (well is shallower)
Step 2: time_adjustment = 105 / 50 = 2.1 days
Step 3: DRL_Days = 19.5 - 2.1 = 17.4 → ceil(17.4) = 18 days
```

#### Step 3: PT Days Calculation

The PT Days calculation uses the **Completion Testing Norm** table:

```
PT Days = Matching norm days based on location + depth + well_type
```

**Lookup Priority**:
1. Match by: location + depth_range + well_type → use `days` value
2. Match by: depth_range + well_type (any location)
3. Match by: depth_range only
4. **Default**: 7.0 days if no match found

#### Step 4: Duration Calculation

```
Duration = ceil(DRL_Days + PT_Days)
```

### API Endpoint
```
POST /api/calculate-well-parameters/

Request Body:
{
    "field_name": "VADATAL",
    "well_profile": "DI",
    "depth": 1765,
    "location_value": "Mehsana",
    "well_type": "EXP"
}

Response:
{
    "success": true,
    "drl_days": 18,
    "pt_days": 5.50,
    "duration": 24,
    "message": "Parameters calculated successfully"
}
```

---

## Auto-Population of Empty Fields

### What It Does
When editing a staged well, certain fields are automatically populated with recommended values based on existing data and intelligent defaults.

### Fields That Auto-Populate

#### 1. Well Profile (Auto-Detection)
**Trigger**: Opening the edit modal

**Logic**:
- Extract first 2 characters of well name (e.g., "VD" from "VDEF-01")
- Find benchmarks where:
  - `location` matches well's location
  - First 2 characters of `pool` match first 2 characters of well name
- Extract matching `well_category` values (Directional, Vertical, Sidetrack)
- Map to profile codes: DI, VE, SD

**Result**:
- If 1 match → Auto-select that profile
- If multiple matches → Show only matched options in dropdown
- If no matches → Show all options

#### 2. Rig Capacity Required (HP) & BOP Stack
**Trigger**: Opening the edit modal OR clicking Auto-Calculate button

**Logic**:
1. Build a cache of all rigs grouped by location (asset_id)
2. For each rig, store: `drilling_capacity_m`, `rig_capacity_hp`, `bop_stack`
3. Sort rigs by `drilling_capacity_m` ascending

```
For well at location L with depth D:
    Find first rig where: drilling_capacity_m >= D
    Use that rig's: rig_capacity_hp, bop_stack
```

**Code Flow**:
```javascript
function findMatchingRigCapacity(wellLocation, wellDepth) {
    // Get rigs for this location
    locationEntries = rigCapacityCache[wellLocation];
    
    // Find minimum drilling capacity >= well depth
    for (entry of locationEntries) {
        if (entry.drilling_capacity_m >= wellDepth) {
            return {
                rig_capacity_hp: entry.rig_capacity_hp,
                bop_stack: entry.bop_stack
            };
        }
    }
    return null;
}
```

**Example**:
```
Well: 2800m depth in Ankleshwar
Available rigs at Ankleshwar:
  - Rig A: 2500m capacity, 1000 HP, BOP 15
  - Rig B: 3000m capacity, 1200 HP, BOP 18  ← Selected (first ≥ 2800)
  - Rig C: 4000m capacity, 1500 HP, BOP 20

Auto-populated: Rig Capacity = 1200 HP, BOP Stack = 18
```

#### 3. TDS Requirement
**Default**: "N" (No) if not previously set

#### 4. Footprint
**Default**: "Fixed" if not previously set

---

## ILM Days Calculation

### What It Does
ILM (Inter-Location Movement) Days represent the time required to move a rig between two well locations. This is calculated in the **ILM Cost - Well Pair Distances** table on the Data Management page.

### What Triggers the Calculation

1. **Automatic**: When the ILM Cost table is loaded or refreshed
2. **Manual**: When clicking "Recalculate" button on the ILM Cost table
3. **API Call**: `POST /api/ilm-cost/recalculate/`

### The Calculation Formula

ILM Days calculation follows a **rule-based adjustment system**:

```
ILM_Days = Base_Norm_Days + Σ(Adjustment_Rules)
```

#### Step 1: Base Norm Days

Get base norm from **RigBuildingNorm** table:
- Match by: `location` + `rig_type` (Mobile/Fixed)
- Returns: `base_days` (e.g., 45 days for a fixed rig in Cambay)

#### Step 2: Apply Adjustment Rules

Rules from **RigBuildingAdjustment** table are applied sequentially:

**Rule Types**:

1. **Replace Rules** (Cluster Movement):
   - If distance is within cluster range, replace base norm entirely
   - Example: "Distance ≤ 5km → Use 5 days instead of base norm"
   
   ```
   IF distance_m <= 5000 AND adjustment_type == 'replace':
       ILM_Days = adjustment_value  # e.g., 5 days
       base_replaced = True
   ```

2. **Add Rules** (Equipment & Distance):
   - Add fixed days for specific conditions
   
   ```
   IF condition matches:
       ILM_Days += adjustment_value
   
   Examples:
   - TDS Required: +2 days
   - DSA Installation: +3 days
   - Distance > 20km: +1 day per 50km
   ```

3. **Per-Unit Rules** (Distance-Based Additions):
   - Add days proportionally based on distance
   
   ```
   IF distance_m > min_distance:
       extra_distance = distance_m - min_distance
       additional_units = extra_distance / unit_value
       additional_days = additional_units × adjustment_value
       ILM_Days += additional_days
   
   Example: +1 day per 50km after 20km base
   Distance: 120km
   Calculation: (120-20)/50 × 1 = 2 additional days
   ```

#### Step 3: Round Final Value

```
ILM_Days = round(ILM_Days, 1)  # Round to 1 decimal place
```

### Complete Calculation Example

```
Scenario:
- Location: Cambay
- Rig Type: Fixed
- Rig has TDS: Yes
- Distance between wells: 85,000 meters (85km)

Step 1: Base Norm
- RigBuildingNorm for (Cambay, Fixed) = 45 days

Step 2: Check Cluster Rules
- Rule: "Distance ≤ 5km → 5 days" → NOT APPLIED (85km > 5km)

Step 3: Apply Equipment Rules
- Rule: "TDS Available → +2 days"
- Applied: ILM_Days = 45 + 2 = 47 days

Step 4: Apply Distance Rules
- Rule: "Distance > 20km → +1 day per 50km"
- Extra distance: 85 - 20 = 65km
- Additional units: 65 / 50 = 1.3
- Additional days: 1.3 × 1 = 1.3 days
- Applied: ILM_Days = 47 + 1.3 = 48.3 days

Final: ILM_Days = 48.3 days
```

### API Response Structure

```json
{
    "distances": [
        {
            "location": "CAMBAY",
            "rig_name": "ANK-1000-01",
            "rig_building_norm_days": 45,
            "ilm_days": 48.3,
            "ilm_applied_rules": [
                {
                    "condition": "TDS Available",
                    "action": "+2 days"
                },
                {
                    "condition": "Distance > 20km",
                    "action": "+1.3 days (1.3 x 50 km)"
                }
            ],
            "well_1_name": "ANK-EXP-01",
            "well_1_lat": 21.63,
            "well_1_lng": 73.01,
            "well_2_name": "ANK-DEV-02",
            "well_2_lat": 22.15,
            "well_2_lng": 73.42,
            "distance_m": 85000.00
        }
    ]
}
```

### UI Display

The ILM Cost table shows:
- **Base Norm**: Original rig building norm days
- **ILM Days**: Final calculated value (color-coded)
  - Red ↑: Higher than base norm
  - Green ↓: Lower than base norm (cluster movement)
- **Remarks/Formula**: Shows calculation breakdown (e.g., "45 + 3.3 = 48.3d")
- **Info Icon**: Click to see detailed rule breakdown

---

## Related Tables

| Table | Purpose |
|-------|---------|
| `DrillingBenchmark` | Benchmark drilling times by field, depth range, and well category |
| `DailyDrillingRate` | Drilling speed (m/day) by location, field, and depth range |
| `CompletionTestingNorm` | PT days by location, depth range, and well type |
| `RigBuildingNorm` | Base ILM days by location and rig type |
| `RigBuildingAdjustment` | Rules for adjusting ILM days based on conditions |
| `WellPairDistance` | Calculated distances between all well pairs |

---

## Summary

| Feature | Trigger | Key Inputs | Output |
|---------|---------|------------|--------|
| Set Blank RTD | Button click | Date picker | Bulk RTD update |
| Auto-Calculate Days | Button click | Field name, profile, depth | DRL, PT, Duration |
| Auto-Fill Rig/BOP | Modal open | Well location, depth | Rig HP, BOP Stack |
| ILM Days | Table load/refresh | Rig, wells, distance | Adjusted movement days |
