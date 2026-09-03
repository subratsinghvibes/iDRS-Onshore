# Interactive Drilling Rig Scheduler (IDRS)
## Comprehensive User Guide & Application Documentation

**Version:** 9.0  
**Last Updated:** February 2026  
**Platform:** Web-based Application (Django/Python)  
**Deployment:** Windows Server / VM  

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Application Overview](#application-overview)
3. [Three-Pillar Architecture](#three-pillar-architecture)
4. [Pillar 1: Data Management](#pillar-1-data-management)
5. [Pillar 2: Scheduling & Optimization](#pillar-2-scheduling--optimization)
6. [Pillar 3: Post-Scheduling Analysis](#pillar-3-post-scheduling-analysis)
7. [Additional Features](#additional-features)
8. [User Roles & Permissions](#user-roles--permissions)
9. [Technical Capabilities](#technical-capabilities)
10. [Use Cases & Workflows](#use-cases--workflows)

---

## Executive Summary

The **Interactive Drilling Rig Scheduler (IDRS)** is an advanced, AI-powered scheduling and optimization platform designed specifically for oil and gas drilling operations. It revolutionizes the way drilling programs are planned, executed, and analyzed by providing intelligent automation, real-time optimization, and comprehensive data management capabilities.

### Key Value Propositions

- **Intelligent Automation:** Reduces scheduling time from days to minutes
- **Cost Optimization:** Minimizes rig movement costs and idle time
- **Data-Driven Decisions:** Provides actionable insights through advanced analytics
- **Scalability:** Handles hundreds of wells and dozens of rigs simultaneously
- **User-Friendly:** Intuitive interface with minimal training required

### Target Users

- **Drilling Engineers:** Plan and optimize drilling programs
- **Operations Managers:** Monitor and adjust schedules in real-time
- **Planning Teams:** Coordinate multi-rig, multi-well operations
- **Management:** Review performance metrics and make strategic decisions
- **Field Personnel:** Access schedules and well information on-site

---

## Application Overview

### What is IDRS?

IDRS is a comprehensive drilling operations management system that combines:
- Advanced optimization algorithms (Google OR-Tools)
- Interactive data management
- Real-time scheduling and visualization
- Performance analytics and reporting
- Video tutorial system for training

### Core Capabilities

1. **Automated Schedule Generation**
   - Optimizes rig-to-well assignments
   - Minimizes inter-location movement (ILM) costs
   - Respects rig capabilities and well requirements
   - Considers temporal constraints and priorities

2. **Data Management**
   - Centralized repository for rigs, wells, and operational data
   - Bulk import/export capabilities
   - Data validation and quality checks
   - Historical data tracking

3. **Visualization & Analysis**
   - Interactive Gantt charts
   - Geographic movement maps
   - Performance dashboards
   - Comparative analysis tools

4. **Collaboration & Training**
   - Multi-user access with role-based permissions
   - Built-in video tutorials
   - Export capabilities for sharing
   - Audit trails for accountability

---


## Three-Pillar Architecture

IDRS is built on three interconnected pillars that form a complete drilling operations management ecosystem:

```
┌─────────────────────────────────────────────────────────────┐
│                    IDRS APPLICATION                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   PILLAR 1   │  │   PILLAR 2   │  │   PILLAR 3   │     │
│  │     DATA     │→ │  SCHEDULING  │→ │POST-SCHEDULE │     │
│  │  MANAGEMENT  │  │OPTIMIZATION  │  │   ANALYSIS   │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
│         ↓                 ↓                  ↓              │
│    Foundation        Core Engine        Insights           │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Pillar Interaction Flow

1. **Data Management** → Provides clean, validated data
2. **Scheduling** → Uses data to generate optimal schedules
3. **Analysis** → Evaluates schedules and provides feedback
4. **Feedback Loop** → Insights inform future data and scheduling decisions

---

## Pillar 1: Data Management

### Overview

The Data Management pillar serves as the foundation of IDRS, providing a centralized, structured repository for all drilling-related data. It ensures data quality, consistency, and accessibility across the organization.

### 1.1 Core Data Entities

#### 1.1.1 Rigs Management

**Purpose:** Maintain comprehensive information about all drilling rigs in the fleet.

**Key Features:**
- Rig identification and classification
- Capacity and capability tracking
- Availability scheduling
- Location assignment
- Equipment specifications

**Data Fields:**
- **Basic Information:**
  - Rig Name (e.g., JOHN-1000-29)
  - Asset ID / Location Code
  - Rig Type (Mobile/Fixed)
  
- **Capabilities:**
  - Rig Capacity (HP) - Horsepower rating
  - BOP Stack (Blowout Preventer specifications)
  - Top Drive System (Yes/No)
  - Maximum Depth Capacity
  
- **Availability:**
  - Start Date (when rig becomes available)
  - End Date (when rig availability ends)
  - Current Status (OK/Not OK)
  
- **Location:**
  - Assigned Location/Company Code
  - Current Position (Latitude/Longitude)

**Operations:**
- ✅ Add new rigs
- ✅ Edit rig specifications
- ✅ Bulk import from Excel/CSV
- ✅ Soft delete (archive without losing history)
- ✅ View all rigs with filtering
- ✅ Export rig data

**Access:** Data Management → View All Rigs

---

#### 1.1.2 Wells Management

**Purpose:** Comprehensive database of all wells to be drilled, including specifications and requirements.

**Key Features:**
- Well identification and classification
- Technical specifications
- Geographic positioning
- Drilling requirements
- Priority management

**Data Fields:**
- **Identification:**
  - Well Name (unique identifier)
  - Asset ID
  - Field Name
  - Well Type (Exploration, Development, Appraisal)
  
- **Geographic:**
  - Latitude (GPS coordinates)
  - Longitude (GPS coordinates)
  - Location/Company Code
  
- **Technical Specifications:**
  - Depth (meters)
  - Well Profile (Directional/Vertical/Sidetrack)
  - Rig Capacity Required (HP)
  - BOP Stack Required
  - TDS Requirement (Top Drive System - Yes/No)
  - Footprint (Mobile/Fixed)
  
- **Scheduling:**
  - Ready to Drill (RTD) Date
  - Priority Level (1-5, where 1 is highest)
  - Preferred Rig (optional)
  - Expected Potential (production estimate)
  
- **Time Estimates:**
  - DRL Days (Drilling days)
  - PT Days (Production Testing days)
  - Duration (Total days)

**Operations:**
- ✅ Add wells individually
- ✅ Bulk upload via Excel/CSV
- ✅ Edit well specifications
- ✅ Set RTD dates in bulk
- ✅ Assign priorities
- ✅ View all wells with filtering
- ✅ Export well data
- ✅ Soft delete wells

**Access:** Data Management → View All Wells

---


#### 1.1.3 Staged Wells Management

**Purpose:** Intermediate staging area for wells before they're finalized into the main scheduler.

**Key Features:**
- Import wells from external sources
- Validate and enrich well data
- Group wells into baskets
- Intelligent data fetching
- Batch processing

**Workflow:**
1. **Import:** Upload wells from Excel/CSV
2. **Stage:** Wells enter staging area with status "PENDING"
3. **Enrich:** Add missing data (coordinates, specifications)
4. **Validate:** Check data completeness
5. **Finalize:** Move to main scheduler as "READY"

**Staged Well Statuses:**
- **PENDING:** Newly imported, needs review
- **IN_BASKET:** Grouped in a basket for processing
- **IMPORTED:** Already moved to main scheduler
- **READY:** Validated and ready to finalize

**Operations:**
- ✅ Bulk upload from Excel/CSV
- ✅ View all staged wells
- ✅ Edit individual wells
- ✅ Set RTD dates in bulk
- ✅ Create well baskets
- ✅ Intelligent data fetching
- ✅ Finalize individual wells
- ✅ Finalize all wells at once
- ✅ Delete staged wells

**Access:** Data Management → Staged Wells

---

#### 1.1.4 Well Baskets

**Purpose:** Group related wells together for batch processing and intelligent data enrichment.

**Key Features:**
- Search and group wells by name
- Intelligent data fetching from benchmarks
- Batch editing capabilities
- Status tracking
- Location-based filtering

**Basket Workflow:**

1. **Create Basket:**
   - Paste well names (comma, space, or newline separated)
   - System searches staged wells
   - Shows found wells, wells in other baskets, and not found
   - Name the basket and create

2. **Load Basket:**
   - View all wells in basket
   - See missing data highlighted in red
   - Edit individual wells

3. **Intelligent Fetch:**
   - Automatically suggests values for missing fields
   - Uses benchmarks and historical data
   - Suggests:
     - Well Profile (based on well name patterns)
     - Rig Capacity (based on depth and location)
     - BOP Stack (based on rig capacity)
     - DRL Days (based on field, profile, depth)
     - PT Days (based on well type and location)
     - Duration (calculated from DRL + PT)
     - TDS Requirement (default: No)
     - Footprint (default: Fixed)
   
4. **Apply Suggestions:**
   - Review suggested values (highlighted in yellow)
   - Apply all suggestions at once
   - Or edit individually

5. **Finalize:**
   - Move all basket wells to main scheduler
   - Wells become available for scheduling

**Operations:**
- ✅ Create baskets
- ✅ Search wells for basket
- ✅ Load and view basket
- ✅ Intelligent data fetching
- ✅ Apply suggestions
- ✅ Edit wells in basket
- ✅ Delete baskets

**Access:** Data Management → Well Baskets

---

#### 1.1.5 Benchmarks & Norms

**Purpose:** Store historical performance data and industry standards for accurate time estimation.

**Categories:**

**A. Drilling Benchmarks**
- Field-specific drilling rates
- Well profile performance
- Depth-based estimates
- Location-specific factors

**Data Fields:**
- Field Name
- Well Category (Exploration/Development/Appraisal)
- Well Profile (DI/VE/SD)
- Depth Range
- Daily Drilling Rate (meters/day)
- Location

**B. Rig Building Norms**
- Time required to set up rigs
- Rig type specific
- Location specific
- Top Drive System considerations

**Data Fields:**
- Rig Type (Mobile/Fixed)
- Top Drive (Yes/No)
- Building Days
- Location

**C. Rig Building Adjustments**
- Additional time for specific scenarios
- Adjustment factors
- Location-specific modifications

**D. Operation Norms**
- Casing operations
- Coring operations
- Completion & testing
- Additional tests

**E. Daily Drilling Rates**
- Field-specific rates
- Depth-based variations
- Well profile considerations

**F. Location-Specific Factors**
- Environmental considerations
- Regulatory requirements
- Logistical challenges

**Operations:**
- ✅ Add/Edit benchmarks
- ✅ Bulk import from Excel
- ✅ View all benchmarks with filtering
- ✅ Export benchmark data
- ✅ Delete benchmarks

**Access:** Data Management → (Various Benchmark sections)

---


#### 1.1.6 Company Codes & Locations

**Purpose:** Manage organizational structure and location-based access control.

**Key Features:**
- Location hierarchy
- Multi-location support
- User-location assignment
- Location-based data filtering

**Data Fields:**
- Company Code (unique identifier)
- Location Name
- Description
- Active Status
- Associated Users
- Associated Rigs
- Associated Wells

**Operations:**
- ✅ Add/Edit company codes
- ✅ Activate/Deactivate locations
- ✅ Assign users to locations
- ✅ View location statistics

**Access:** Data Management → Company Codes

---

#### 1.1.7 Master Personnel Info (MPI)

**Purpose:** Maintain personnel database for authentication and authorization.

**Key Features:**
- Employee information
- CPF (Central Personnel File) number
- Location assignment
- Role assignment
- LDAP integration

**Data Fields:**
- CPF Number (unique identifier)
- Employee Name
- Location
- Department
- Role
- Active Status

**Operations:**
- ✅ View personnel list
- ✅ Sync with LDAP
- ✅ Assign locations
- ✅ Manage authorized users

**Access:** Data Management → MPI Table

---

### 1.2 Data Management Features

#### 1.2.1 Bulk Import/Export

**Import Capabilities:**
- **Excel Files (.xlsx, .xls)**
  - Rigs
  - Wells
  - Staged Wells
  - Benchmarks
  - All norm types
  
- **CSV Files (.csv)**
  - All entity types
  - Flexible column mapping
  
- **Features:**
  - Template download
  - Column validation
  - Error reporting
  - Duplicate detection
  - Data preview before import

**Export Capabilities:**
- **Excel Export**
  - Formatted spreadsheets
  - Multiple sheets
  - Filtered data
  
- **CSV Export**
  - All entity types
  - Custom column selection
  
- **PDF Export**
  - Schedules
  - Reports
  - Gantt charts

**Access:** Data Management → Each section has Import/Export buttons

---

#### 1.2.2 Data Validation

**Automatic Validation:**
- ✅ Required field checks
- ✅ Data type validation
- ✅ Range validation (e.g., dates, numbers)
- ✅ Uniqueness constraints
- ✅ Referential integrity
- ✅ GPS coordinate validation
- ✅ Date logic validation

**Visual Indicators:**
- 🔴 Red highlight: Missing required data
- 🟡 Yellow highlight: Suggested values
- 🟢 Green highlight: Complete data
- ⚠️ Warning icons: Data quality issues

---

#### 1.2.3 Data Quality Features

**Intelligent Data Fetching:**
- Suggests missing values based on:
  - Historical benchmarks
  - Similar wells
  - Location patterns
  - Industry standards

**Data Enrichment:**
- Auto-calculate duration from DRL + PT days
- Suggest rig capacity based on depth
- Recommend BOP stack based on capacity
- Infer well profile from well name
- Default values for common fields

**Data Cleaning:**
- Remove duplicates
- Standardize formats
- Validate coordinates
- Check date consistency

---

#### 1.2.4 Search & Filter

**Global Search:**
- Search across all entities
- Fuzzy matching
- Multi-field search

**Advanced Filtering:**
- **By Location:** Filter by company code
- **By Status:** Active, deleted, pending
- **By Date Range:** RTD dates, availability
- **By Specifications:** Capacity, depth, type
- **By Priority:** Well priorities
- **Custom Filters:** Combine multiple criteria

**Sorting:**
- Sort by any column
- Multi-column sorting
- Save sort preferences

---

### 1.3 Data Management Best Practices

#### Data Entry Workflow

1. **Start with Locations**
   - Set up company codes first
   - Assign users to locations

2. **Import Benchmarks**
   - Load historical performance data
   - Set up drilling rates
   - Configure rig building norms

3. **Add Rigs**
   - Import rig fleet data
   - Verify capabilities
   - Set availability dates

4. **Stage Wells**
   - Bulk import well data
   - Create baskets for related wells
   - Use intelligent fetch to enrich data

5. **Validate & Finalize**
   - Review all staged wells
   - Fix missing data
   - Finalize to main scheduler

6. **Ready for Scheduling**
   - All data validated
   - Ready to create schedules

---


## Pillar 2: Scheduling & Optimization

### Overview

The Scheduling & Optimization pillar is the core engine of IDRS, utilizing advanced algorithms to generate optimal drilling schedules that minimize costs, respect constraints, and maximize efficiency.

### 2.1 Optimization Engine

#### 2.1.1 Technology Stack

**Google OR-Tools:**
- Industry-leading optimization library
- Constraint Programming (CP-SAT Solver)
- Handles complex scheduling problems
- Proven scalability (100+ wells, 20+ rigs)

**Optimization Objectives:**
1. **Primary:** Minimize Inter-Location Movement (ILM) costs
2. **Secondary:** Minimize total schedule duration
3. **Tertiary:** Respect well priorities
4. **Quaternary:** Balance rig utilization

---

#### 2.1.2 Constraints & Rules

**Hard Constraints (Must be satisfied):**

1. **Rig Capability Matching:**
   - Rig capacity ≥ Well requirement
   - BOP stack compatibility
   - TDS availability if required
   - Footprint matching (Mobile/Fixed)

2. **Temporal Constraints:**
   - Rig availability windows
   - Well RTD (Ready to Drill) dates
   - Financial year boundaries
   - No overlapping assignments

3. **Physical Constraints:**
   - One rig per well at a time
   - One well per rig at a time
   - Rig building time between wells
   - Travel time between locations

**Soft Constraints (Preferences):**

1. **Priority Preferences:**
   - Higher priority wells scheduled first
   - Priority levels: 1 (highest) to 5 (lowest)

2. **Rig Preferences:**
   - Preferred rig assignments
   - Rig-well affinity

3. **Location Preferences:**
   - Minimize location changes
   - Group wells by location

4. **Efficiency Preferences:**
   - Minimize idle time
   - Maximize rig utilization

---

#### 2.1.3 Cost Calculations

**Inter-Location Movement (ILM) Costs:**

```
ILM Cost = Distance × Cost per Kilometer × Rig Factor

Where:
- Distance: Haversine formula (GPS coordinates)
- Cost per km: Configurable (default: $1000/km)
- Rig Factor: Based on rig type and capacity
```

**Components:**
- **Transportation:** Moving rig between locations
- **Setup Time:** Rig building at new location
- **Downtime:** Non-productive time during move
- **Logistics:** Support equipment and personnel

**Distance Calculation:**
- Uses GPS coordinates (latitude/longitude)
- Haversine formula for great-circle distance
- Accounts for Earth's curvature
- Accurate for long distances

**ILM Cost Matrix:**
- Pre-calculated for all well pairs
- Cached for performance
- Updated when well coordinates change
- Displayed in Data Management

---

### 2.2 Schedule Creation

#### 2.2.1 Create New Schedule

**Access:** Scheduling → Create Schedule

**Step-by-Step Process:**

**Step 1: Basic Information**
- Schedule Name (required)
- Description (optional)
- Financial Year (e.g., 2025-2026)
- Location Filter (optional)

**Step 2: Select Wells**
- View all available wells
- Filter by location, priority, RTD date
- Select wells to include
- See well count and statistics

**Step 3: Select Rigs**
- View all available rigs
- Filter by location, type, capacity
- Select rigs to use
- See rig count and availability

**Step 4: Optimization Settings**
- **Time Limit:** Max optimization time (seconds)
  - Quick: 30 seconds
  - Standard: 60 seconds
  - Thorough: 120 seconds
  - Extensive: 300 seconds
  
- **ILM Cost Weight:** Importance of minimizing movement
  - Low: 0.3
  - Medium: 0.5
  - High: 0.7
  - Very High: 1.0

**Step 5: Run Optimization**
- Click "Generate Schedule"
- Progress indicator shows status
- Real-time updates on assignments
- Completion notification

**Step 6: Review Results**
- View schedule summary
- Check assignments
- Review unscheduled wells/rigs
- Analyze costs and metrics

---

#### 2.2.2 Schedule Types

**1. Master Schedule**
- Comprehensive, long-term plan
- All wells and rigs
- Full financial year
- Used for strategic planning

**2. Location-Specific Schedule**
- Filtered by location
- Subset of wells and rigs
- Tactical planning
- Operational focus

**3. Priority-Based Schedule**
- High-priority wells only
- Urgent requirements
- Quick turnaround
- Emergency planning

**4. Scenario Analysis**
- Multiple schedule versions
- What-if analysis
- Comparison studies
- Decision support

---

#### 2.2.3 Schedule Branching

**Purpose:** Create alternative versions of a schedule for comparison.

**Branch Types:**

**1. Main Branch**
- Original optimized schedule
- Baseline for comparison
- Cannot be deleted

**2. Alternative Branches**
- Modified versions
- Manual adjustments
- Different constraints
- Scenario testing

**Operations:**
- ✅ Create branch from existing schedule
- ✅ Name and describe branch
- ✅ Modify assignments
- ✅ Compare branches
- ✅ Delete branches (except main)

**Use Cases:**
- Test different rig allocations
- Evaluate priority changes
- Assess impact of delays
- Compare optimization settings

---


### 2.3 Schedule Management

#### 2.3.1 View All Schedules

**Access:** Schedules → View All Schedules

**Features:**
- List all created schedules
- Filter by status, location, financial year
- Sort by date, name, status
- Quick actions (view, edit, delete)

**Schedule Statuses:**
- **DRAFT:** Being created/edited
- **OPTIMIZING:** Optimization in progress
- **COMPLETED:** Optimization finished
- **FAILED:** Optimization failed
- **ARCHIVED:** Historical record

**Information Displayed:**
- Schedule name and description
- Financial year
- Location
- Number of wells (scheduled/total)
- Number of rigs used
- Total ILM cost
- Total ILM days
- Creation date and creator
- Status

---

#### 2.3.2 Schedule Detail View

**Access:** Click on any schedule from the list

**Sections:**

**A. Schedule Header**
- Name, description, financial year
- Location and status
- Creation info
- Action buttons (Edit, Delete, Export, Branch)

**B. Summary Statistics**
- **Wells:**
  - Total wells
  - Scheduled wells
  - Unscheduled wells
  - Completion percentage
  
- **Rigs:**
  - Total rigs
  - Utilized rigs
  - Unutilized rigs
  - Utilization percentage
  
- **Costs:**
  - Total ILM cost
  - Average cost per well
  - Cost breakdown by location
  
- **Time:**
  - Total ILM days
  - Average days per well
  - Schedule duration
  - Start and end dates

**C. Assignments Table**
- All rig-well assignments
- Columns:
  - Rig name
  - Well name
  - Location
  - Start date
  - End date
  - Duration (days)
  - ILM days
  - ILM cost
  - Priority
  - Status

**D. Unscheduled Resources**
- Wells that couldn't be scheduled
- Reasons for non-scheduling
- Rigs not utilized
- Recommendations

**E. Rig Statistics**
- Per-rig utilization
- Number of wells per rig
- Total days per rig
- Idle time per rig
- Efficiency metrics

---

#### 2.3.3 Schedule Editing

**Manual Adjustments:**
- ✅ Change rig assignments
- ✅ Modify start/end dates
- ✅ Add/remove wells
- ✅ Add/remove rigs
- ✅ Adjust priorities
- ✅ Re-optimize with new constraints

**Validation:**
- Automatic conflict detection
- Constraint violation warnings
- Feasibility checks
- Impact analysis

**Audit Trail:**
- Track all changes
- User and timestamp
- Before/after values
- Change reasons

---

### 2.4 Optimization Features

#### 2.4.1 Well Rejection Analysis

**Purpose:** Understand why wells couldn't be scheduled.

**Rejection Reasons:**

1. **Capability Mismatch:**
   - No rig with sufficient capacity
   - BOP stack incompatibility
   - TDS requirement not met
   - Footprint mismatch

2. **Temporal Conflicts:**
   - RTD date outside rig availability
   - No available time slot
   - Financial year boundary

3. **Resource Exhaustion:**
   - All rigs fully utilized
   - No capacity remaining

4. **Constraint Violations:**
   - Would violate hard constraints
   - Infeasible assignment

**Analysis Output:**
- List of unscheduled wells
- Specific reason for each
- Recommendations for resolution
- Alternative options

**Actions:**
- Adjust well requirements
- Add more rigs
- Extend rig availability
- Modify priorities
- Re-run optimization

---

#### 2.4.2 Optimization Performance

**Metrics:**
- Optimization time (seconds)
- Number of variables
- Number of constraints
- Solution quality (optimal/feasible)
- Solver statistics

**Performance Factors:**
- Number of wells
- Number of rigs
- Time limit setting
- Constraint complexity
- Hardware resources

**Typical Performance:**
- 10 wells, 3 rigs: < 5 seconds
- 50 wells, 10 rigs: 10-30 seconds
- 100 wells, 20 rigs: 30-120 seconds
- 200+ wells, 30+ rigs: 120-300 seconds

---

#### 2.4.3 Schedule Quality Indicators

**Optimization Quality:**
- ✅ **Optimal:** Best possible solution found
- ✅ **Feasible:** Valid solution, may not be optimal
- ⚠️ **Infeasible:** No valid solution exists
- ❌ **Failed:** Optimization error

**Schedule Health:**
- **Excellent:** >90% wells scheduled, low ILM cost
- **Good:** 75-90% wells scheduled, moderate ILM cost
- **Fair:** 60-75% wells scheduled, high ILM cost
- **Poor:** <60% wells scheduled

**Improvement Suggestions:**
- Add more rigs
- Adjust well priorities
- Extend time windows
- Relax constraints
- Increase optimization time

---


## Pillar 3: Post-Scheduling Analysis

### Overview

The Post-Scheduling Analysis pillar provides comprehensive visualization, analysis, and reporting tools to evaluate schedules, track performance, and make informed decisions.

### 3.1 Interactive Gantt Chart

**Access:** Schedules → Interactive Gantt Chart

**Purpose:** Visual timeline representation of the drilling schedule showing all rig assignments over time.

#### 3.1.1 Gantt Chart Features

**Visual Elements:**
- **Timeline:** Horizontal axis showing dates
- **Rigs:** Vertical axis listing all rigs
- **Bars:** Colored blocks representing well assignments
- **Gaps:** White space showing idle time
- **Connections:** Lines showing rig movements

**Color Coding:**
- **By Well Type:**
  - Blue: Exploration wells
  - Green: Development wells
  - Orange: Appraisal wells
  
- **By Priority:**
  - Red: Priority 1 (highest)
  - Orange: Priority 2
  - Yellow: Priority 3
  - Light Blue: Priority 4
  - Gray: Priority 5 (lowest)
  
- **By Location:**
  - Different colors for each location
  - Easy identification of location changes

**Interactive Features:**
- ✅ Zoom in/out (timeline scale)
- ✅ Pan left/right (scroll timeline)
- ✅ Hover for details (well info tooltip)
- ✅ Click for full details (well modal)
- ✅ Filter by rig
- ✅ Filter by well type
- ✅ Filter by priority
- ✅ Toggle view modes
- ✅ Export as image/PDF

**Information Display:**
- Well name and asset ID
- Start and end dates
- Duration (days)
- Location
- Priority
- ILM days (if applicable)
- Rig building time

---

#### 3.1.2 Gantt Chart Views

**1. Standard View**
- All rigs and assignments
- Full timeline
- Default color scheme

**2. Compact View**
- Condensed timeline
- Smaller bars
- More data visible

**3. Detailed View**
- Expanded bars
- More information per assignment
- Larger tooltips

**4. Rig-Focused View**
- Single rig timeline
- All assignments for that rig
- Detailed utilization

**5. Location View**
- Group by location
- Show location transitions
- Highlight ILM movements

---

#### 3.1.3 Gantt Chart Analysis

**Utilization Analysis:**
- Identify idle periods
- Spot over-utilization
- Balance workload

**Timeline Analysis:**
- Check schedule feasibility
- Verify date constraints
- Identify bottlenecks

**Movement Analysis:**
- Track rig movements
- Visualize ILM transitions
- Optimize routing

**Conflict Detection:**
- Overlapping assignments
- Constraint violations
- Resource conflicts

---

### 3.2 Movement Maps

**Access:** Schedules → Movement Maps

**Purpose:** Geographic visualization of rig movements showing physical distances and routes.

#### 3.2.1 Map Features

**Map Types:**

**1. Overview Map**
- All wells and rigs
- Complete schedule
- Movement paths
- Location clusters

**2. Rig-Specific Map**
- Single rig's journey
- All assigned wells
- Movement sequence
- Total distance

**3. Location Map**
- Wells by location
- Location boundaries
- Intra-location movements
- Inter-location movements

**Visual Elements:**
- 📍 **Markers:** Well locations (GPS coordinates)
- 🔵 **Circles:** Rig positions
- ➡️ **Arrows:** Movement paths
- 📏 **Lines:** Distance indicators
- 🏷️ **Labels:** Well/rig names

**Interactive Features:**
- ✅ Zoom and pan
- ✅ Click markers for details
- ✅ Toggle layers (wells, rigs, paths)
- ✅ Measure distances
- ✅ Filter by location
- ✅ Animation (show movement sequence)
- ✅ Export map as image

---

#### 3.2.2 Distance Analysis

**ILM Distance Matrix:**
- Pre-calculated distances between all well pairs
- Haversine formula (great-circle distance)
- Displayed in kilometers
- Color-coded by distance range

**Distance Statistics:**
- Total distance traveled per rig
- Average distance per movement
- Longest single movement
- Shortest single movement
- Distance by location pair

**Cost Correlation:**
- Distance vs. cost analysis
- Cost per kilometer
- High-cost movements
- Optimization opportunities

---

### 3.3 Schedule Comparison

**Access:** Schedules → Compare Schedules

**Purpose:** Side-by-side comparison of multiple schedules or schedule branches.

#### 3.3.1 Comparison Features

**Select Schedules:**
- Choose 2-4 schedules to compare
- Can compare different schedules
- Can compare branches of same schedule
- Can compare before/after optimization

**Comparison Metrics:**

**A. High-Level Metrics:**
- Total wells scheduled
- Total rigs utilized
- Total ILM cost
- Total ILM days
- Schedule duration
- Completion percentage

**B. Detailed Metrics:**
- Wells scheduled per rig
- Average cost per well
- Average days per well
- Utilization percentage
- Idle time
- Efficiency score

**C. Difference Analysis:**
- Absolute differences
- Percentage changes
- Better/worse indicators
- Improvement suggestions

**Visual Comparison:**
- Side-by-side Gantt charts
- Overlaid movement maps
- Comparative bar charts
- Difference highlights

---

#### 3.3.2 Comparison Use Cases

**1. Optimization Settings:**
- Compare different time limits
- Evaluate ILM weight impact
- Test constraint variations

**2. Resource Changes:**
- Add/remove rigs
- Add/remove wells
- Change rig capabilities

**3. Temporal Changes:**
- Different financial years
- Modified RTD dates
- Extended availability

**4. Priority Changes:**
- Reprioritize wells
- Evaluate impact
- Optimize for different goals

**5. Manual vs. Automated:**
- Compare manual schedule
- Compare optimized schedule
- Quantify improvement

---


### 3.4 Dashboard & Analytics

**Access:** Dashboard (Home Page)

**Purpose:** Real-time overview of drilling operations and key performance indicators.

#### 3.4.1 Dashboard Widgets

**1. Schedule Overview**
- Active schedules count
- Total wells in system
- Total rigs available
- Schedules by status

**2. Recent Activity**
- Latest schedules created
- Recent optimizations
- Recent data imports
- User activity log

**3. Performance Metrics**
- Average optimization time
- Schedule completion rate
- Rig utilization rate
- Cost efficiency

**4. Alerts & Notifications**
- Unscheduled wells
- Rig conflicts
- Data quality issues
- System notifications

**5. Quick Actions**
- Create new schedule
- Import data
- View reports
- Access tutorials

---

#### 3.4.2 Reports & Analytics

**Standard Reports:**

**1. Schedule Summary Report**
- Executive summary
- Key metrics
- Assignments list
- Unscheduled resources
- Recommendations

**2. Rig Utilization Report**
- Per-rig statistics
- Utilization percentage
- Idle time analysis
- Efficiency metrics
- Workload distribution

**3. Cost Analysis Report**
- Total ILM costs
- Cost breakdown by location
- Cost per well
- Cost trends
- Cost optimization opportunities

**4. Well Status Report**
- All wells status
- Scheduled vs. unscheduled
- Priority distribution
- RTD date compliance
- Completion forecast

**5. Location Report**
- Wells by location
- Rigs by location
- Inter-location movements
- Location-specific costs
- Location efficiency

**Export Formats:**
- PDF (formatted reports)
- Excel (data tables)
- CSV (raw data)
- JSON (API integration)

---

### 3.5 Performance Tracking

#### 3.5.1 Key Performance Indicators (KPIs)

**Operational KPIs:**
- **Schedule Completion Rate:** % of wells scheduled
- **Rig Utilization Rate:** % of rig time used
- **On-Time Performance:** % of wells starting on RTD
- **Schedule Adherence:** Actual vs. planned

**Financial KPIs:**
- **Total ILM Cost:** Sum of all movement costs
- **Cost per Well:** Average cost per well drilled
- **Cost Efficiency:** Cost vs. budget
- **Cost Savings:** Optimization savings

**Efficiency KPIs:**
- **Optimization Time:** Time to generate schedule
- **Schedule Quality:** Optimal vs. feasible
- **Resource Efficiency:** Utilization vs. availability
- **Planning Efficiency:** Time saved vs. manual

**Quality KPIs:**
- **Data Completeness:** % of complete records
- **Constraint Satisfaction:** % of constraints met
- **Schedule Feasibility:** % of feasible schedules
- **User Satisfaction:** Feedback scores

---

#### 3.5.2 Trend Analysis

**Historical Trends:**
- Schedule performance over time
- Cost trends by period
- Utilization trends
- Efficiency improvements

**Comparative Analysis:**
- Current vs. previous periods
- Actual vs. planned
- Location comparisons
- Rig comparisons

**Predictive Analytics:**
- Forecast future schedules
- Predict resource needs
- Estimate costs
- Identify risks

---

### 3.6 Export & Sharing

#### 3.6.1 Export Options

**Schedule Exports:**
- **PDF:** Formatted schedule document
- **Excel:** Detailed spreadsheet with multiple sheets
- **CSV:** Raw data for analysis
- **JSON:** API integration
- **Image:** Gantt chart visualization

**Report Exports:**
- **PDF Reports:** Professional formatted reports
- **Excel Dashboards:** Interactive spreadsheets
- **PowerPoint:** Presentation slides
- **Email:** Direct email delivery

---

#### 3.6.2 Sharing Features

**Internal Sharing:**
- Share with team members
- Role-based access
- View-only or edit permissions
- Comment and collaborate

**External Sharing:**
- Export for stakeholders
- Generate public links
- Password protection
- Expiration dates

**Integration:**
- API endpoints for external systems
- Webhook notifications
- Real-time data feeds
- Third-party tool integration

---


## Additional Features

### 4.1 Video Tutorials

**Access:** Help & Support → Video Tutorials

**Purpose:** Built-in training system with video guides for all features.

#### 4.1.1 Tutorial System Features

**Video Management:**
- Admin uploads training videos
- Automatic video compression (700MB → 180MB)
- Instant streaming (2-3 seconds load time)
- YouTube/Netflix-like performance
- No buffering during playback

**Tutorial Categories:**
- Getting Started
- Data Management
- Scheduling & Optimization
- Analysis & Reporting
- Advanced Features
- Troubleshooting
- Best Practices

**Video Features:**
- ✅ Instant playback
- ✅ Seek anywhere
- ✅ Pause/resume
- ✅ Fullscreen mode
- ✅ Playback speed control
- ✅ Thumbnail previews
- ✅ View count tracking
- ✅ Duration display

**Technical Implementation:**
- FFmpeg-based compression
- HTTP Range Request streaming
- Progressive download
- Optimized for network performance
- Works on slow connections

---

### 4.2 User Management

**Access:** Admin → User Management

**Purpose:** Manage user accounts, roles, and permissions.

#### 4.2.1 User Roles

**1. Super Administrator**
- Full system access
- All locations
- User management
- System configuration
- Data management
- Schedule creation/editing

**2. Administrator**
- Location-specific access
- User management (own location)
- Data management
- Schedule creation/editing
- Report generation

**3. Planner**
- Location-specific access
- Data viewing
- Schedule creation
- Report generation
- No user management

**4. Viewer**
- Location-specific access
- Read-only access
- View schedules
- View reports
- No editing capabilities

**5. Field User**
- Limited access
- View assigned schedules
- View well information
- Mobile-friendly interface

---

#### 4.2.2 Permission System

**Location-Based Access:**
- Users assigned to specific locations
- Can only see data for their location
- Admins can see all locations
- Configurable per user

**Feature-Based Permissions:**
- Data Management (view/edit)
- Schedule Creation (create/edit/delete)
- Report Generation (view/export)
- User Management (view/edit)
- System Configuration (admin only)

**Audit Trail:**
- Track all user actions
- Login/logout history
- Data modifications
- Schedule changes
- Export activities

---

### 4.3 Authentication & Security

#### 4.3.1 Authentication Methods

**1. LDAP Integration**
- Corporate directory integration
- Single Sign-On (SSO)
- Automatic user provisioning
- Role synchronization
- Password policy enforcement

**2. Local Authentication**
- Username/password
- Password complexity requirements
- Password expiration
- Account lockout
- Password reset

**3. Multi-Factor Authentication (MFA)**
- Optional second factor
- SMS or email codes
- Authenticator apps
- Enhanced security

---

#### 4.3.2 Security Features

**Data Security:**
- Encrypted connections (HTTPS)
- Encrypted data at rest
- SQL injection protection
- XSS protection
- CSRF protection

**Access Control:**
- Role-based access control (RBAC)
- Location-based filtering
- Session management
- Automatic logout
- IP whitelisting (optional)

**Audit & Compliance:**
- Complete audit trail
- User activity logging
- Data change tracking
- Export logs
- Compliance reports

---

### 4.4 System Administration

**Access:** Admin Panel

#### 4.4.1 Configuration

**System Settings:**
- Application name and branding
- Default financial year
- Default optimization settings
- ILM cost parameters
- Date formats and localization

**Email Configuration:**
- SMTP settings
- Email notifications
- Report delivery
- Alert emails

**Backup & Recovery:**
- Automated backups
- Manual backup triggers
- Database export
- Data restoration
- Disaster recovery

---

#### 4.4.2 Database Management

**Database Viewer:**
- View all tables
- Browse records
- Export data
- Run queries (admin only)
- Database statistics

**Data Maintenance:**
- Clean up old data
- Archive completed schedules
- Remove soft-deleted records
- Optimize database
- Rebuild indexes

**Database Export:**
- Full database backup
- Table-specific exports
- SQL format
- JSON format
- Scheduled exports

---

### 4.5 API & Integration

#### 4.5.1 REST API

**API Endpoints:**
- `/api/schedules/` - Schedule management
- `/api/rigs/` - Rig data
- `/api/wells/` - Well data
- `/api/baskets/` - Basket management
- `/api/benchmarks/` - Benchmark data

**API Features:**
- RESTful design
- JSON responses
- Authentication required
- Rate limiting
- API documentation

**Use Cases:**
- External system integration
- Mobile app development
- Custom reporting tools
- Data synchronization
- Automated workflows

---

#### 4.5.2 External App Integration

**AppSense Integration:**
- Single Sign-On (SSO)
- User authentication
- Session management
- Seamless navigation
- Unified experience

**Third-Party Tools:**
- Excel add-ins
- Power BI connectors
- Tableau integration
- Custom dashboards
- Data warehouses

---


## User Roles & Permissions

### 5.1 Role Definitions

#### Super Administrator
**Access Level:** Global  
**Capabilities:**
- ✅ All system features
- ✅ All locations
- ✅ User management (all users)
- ✅ System configuration
- ✅ Database management
- ✅ API access
- ✅ Audit logs
- ✅ Backup/restore

**Typical Users:** IT administrators, system owners

---

#### Location Administrator
**Access Level:** Location-specific  
**Capabilities:**
- ✅ All features for assigned location
- ✅ User management (location users)
- ✅ Data management (location data)
- ✅ Schedule creation/editing
- ✅ Report generation
- ✅ Export data
- ❌ System configuration
- ❌ Other locations

**Typical Users:** Location managers, operations managers

---

#### Planner
**Access Level:** Location-specific  
**Capabilities:**
- ✅ View all data (location)
- ✅ Create schedules
- ✅ Edit schedules
- ✅ Run optimization
- ✅ Generate reports
- ✅ Export data
- ❌ User management
- ❌ Delete schedules
- ❌ System settings

**Typical Users:** Drilling engineers, planning engineers

---

#### Viewer
**Access Level:** Location-specific  
**Capabilities:**
- ✅ View schedules
- ✅ View reports
- ✅ View data
- ✅ Export reports
- ❌ Create/edit schedules
- ❌ Modify data
- ❌ User management

**Typical Users:** Management, stakeholders, analysts

---

#### Field User
**Access Level:** Limited  
**Capabilities:**
- ✅ View assigned schedules
- ✅ View well details
- ✅ Mobile access
- ❌ Create schedules
- ❌ Edit data
- ❌ Access admin features

**Typical Users:** Field engineers, rig supervisors

---

### 5.2 Permission Matrix

| Feature | Super Admin | Location Admin | Planner | Viewer | Field User |
|---------|-------------|----------------|---------|--------|------------|
| **Data Management** |
| View Rigs | ✅ All | ✅ Location | ✅ Location | ✅ Location | ❌ |
| Add/Edit Rigs | ✅ | ✅ | ✅ | ❌ | ❌ |
| Delete Rigs | ✅ | ✅ | ❌ | ❌ | ❌ |
| View Wells | ✅ All | ✅ Location | ✅ Location | ✅ Location | ✅ Assigned |
| Add/Edit Wells | ✅ | ✅ | ✅ | ❌ | ❌ |
| Delete Wells | ✅ | ✅ | ❌ | ❌ | ❌ |
| Bulk Import | ✅ | ✅ | ✅ | ❌ | ❌ |
| Manage Benchmarks | ✅ | ✅ | ✅ | ❌ | ❌ |
| **Scheduling** |
| Create Schedule | ✅ | ✅ | ✅ | ❌ | ❌ |
| Edit Schedule | ✅ | ✅ | ✅ | ❌ | ❌ |
| Delete Schedule | ✅ | ✅ | ❌ | ❌ | ❌ |
| Run Optimization | ✅ | ✅ | ✅ | ❌ | ❌ |
| View Schedules | ✅ All | ✅ Location | ✅ Location | ✅ Location | ✅ Assigned |
| **Analysis** |
| View Gantt Chart | ✅ | ✅ | ✅ | ✅ | ✅ |
| View Maps | ✅ | ✅ | ✅ | ✅ | ❌ |
| Compare Schedules | ✅ | ✅ | ✅ | ✅ | ❌ |
| Generate Reports | ✅ | ✅ | ✅ | ✅ | ❌ |
| Export Data | ✅ | ✅ | ✅ | ✅ | ❌ |
| **Administration** |
| User Management | ✅ All | ✅ Location | ❌ | ❌ | ❌ |
| System Settings | ✅ | ❌ | ❌ | ❌ | ❌ |
| Database Access | ✅ | ❌ | ❌ | ❌ | ❌ |
| API Access | ✅ | ✅ | ✅ | ❌ | ❌ |
| Audit Logs | ✅ | ✅ | ❌ | ❌ | ❌ |

---

### 5.3 Location-Based Access

**How It Works:**
1. Each user is assigned to a location (Company Code)
2. Users can only see data for their assigned location
3. Super Admins can see all locations
4. Users with "View All Locations" permission can see all

**Benefits:**
- Data isolation between locations
- Security and privacy
- Simplified user experience
- Reduced data clutter
- Compliance with data policies

**Configuration:**
- Admin assigns location to user
- User profile shows assigned location
- Filters automatically applied
- Can be changed by admin

---


## Technical Capabilities

### 6.1 Technology Stack

#### Backend
- **Framework:** Django 5.1.5 (Python)
- **Database:** SQLite (development) / PostgreSQL (production)
- **Optimization:** Google OR-Tools 9.15
- **API:** Django REST Framework
- **Authentication:** LDAP / Local

#### Frontend
- **Framework:** Bootstrap 5
- **JavaScript:** Vanilla JS + jQuery
- **Charts:** Plotly.js
- **Gantt:** Frappe Gantt
- **Maps:** Leaflet / Google Maps
- **Icons:** Bootstrap Icons

#### Video Processing
- **Encoder:** FFmpeg
- **Compression:** H.264 codec
- **Streaming:** HTTP Range Requests
- **Format:** MP4 (progressive)

#### Infrastructure
- **Server:** Windows Server / Linux
- **Web Server:** Django Development Server / Gunicorn
- **Deployment:** VM / Cloud
- **Backup:** Automated database backups

---

### 6.2 Performance Specifications

#### Scalability
- **Wells:** Up to 500 wells per schedule
- **Rigs:** Up to 50 rigs per schedule
- **Users:** Unlimited concurrent users
- **Schedules:** Unlimited schedules
- **Data:** Millions of records

#### Speed
- **Page Load:** < 2 seconds
- **Optimization:** 30-300 seconds (depending on size)
- **Data Import:** 1000 records/second
- **Report Generation:** < 5 seconds
- **Video Streaming:** 2-3 seconds to start

#### Reliability
- **Uptime:** 99.9% availability
- **Data Integrity:** ACID compliance
- **Backup:** Automated daily backups
- **Recovery:** Point-in-time restoration

---

### 6.3 System Requirements

#### Server Requirements
**Minimum:**
- CPU: 4 cores
- RAM: 8 GB
- Storage: 50 GB
- OS: Windows Server 2016+ / Linux

**Recommended:**
- CPU: 8+ cores
- RAM: 16+ GB
- Storage: 100+ GB SSD
- OS: Windows Server 2019+ / Ubuntu 20.04+

#### Client Requirements
**Desktop:**
- Modern web browser (Chrome, Firefox, Edge, Safari)
- Screen resolution: 1366x768 or higher
- Internet connection: 1 Mbps or higher

**Mobile:**
- iOS 12+ / Android 8+
- Mobile browser
- Screen size: 5" or larger
- Internet connection: 3G or higher

---

### 6.4 Data Specifications

#### Data Capacity
- **Rigs:** Unlimited
- **Wells:** Unlimited
- **Schedules:** Unlimited
- **Benchmarks:** Unlimited
- **Users:** Unlimited
- **Locations:** Unlimited

#### Data Types
- **Numeric:** Integers, decimals, floats
- **Text:** Strings, text fields
- **Dates:** Date, datetime, time
- **Geographic:** Latitude, longitude
- **Binary:** Files, images, videos
- **JSON:** Structured data

#### Data Validation
- Required field checks
- Data type validation
- Range validation
- Format validation
- Uniqueness constraints
- Referential integrity

---

### 6.5 Integration Capabilities

#### Import Formats
- Excel (.xlsx, .xls)
- CSV (.csv)
- JSON (.json)
- SQL (database import)

#### Export Formats
- Excel (.xlsx)
- CSV (.csv)
- PDF (.pdf)
- JSON (.json)
- SQL (database export)
- Images (.png, .jpg)

#### API Integration
- RESTful API
- JSON responses
- Authentication (Token/Session)
- Rate limiting
- Webhook support

#### Third-Party Integration
- LDAP/Active Directory
- AppSense SSO
- Power BI
- Tableau
- Excel add-ins
- Custom applications

---


## Use Cases & Workflows

### 7.1 Common Workflows

#### Workflow 1: Annual Drilling Program Planning

**Scenario:** Planning the drilling program for the next financial year.

**Steps:**

1. **Prepare Data (Week 1)**
   - Import rig fleet data
   - Import well inventory
   - Update benchmarks
   - Verify locations

2. **Stage Wells (Week 2)**
   - Bulk import wells from Excel
   - Create baskets by field/location
   - Use intelligent fetch to enrich data
   - Validate all data

3. **Create Master Schedule (Week 3)**
   - Select all wells for the year
   - Select all available rigs
   - Set optimization parameters
   - Run optimization
   - Review results

4. **Analyze & Refine (Week 4)**
   - Review Gantt chart
   - Check movement maps
   - Analyze unscheduled wells
   - Adjust priorities if needed
   - Re-optimize

5. **Create Scenarios (Week 5)**
   - Branch main schedule
   - Test different rig allocations
   - Evaluate priority changes
   - Compare scenarios
   - Select best option

6. **Finalize & Distribute (Week 6)**
   - Generate reports
   - Export to Excel/PDF
   - Share with stakeholders
   - Present to management
   - Get approval

**Time Saved:** 4-6 weeks reduced to 6 weeks with better quality

---

#### Workflow 2: Quarterly Schedule Update

**Scenario:** Updating the schedule mid-year due to changes.

**Steps:**

1. **Assess Changes**
   - New wells added
   - Rig availability changed
   - Priorities adjusted
   - Delays occurred

2. **Update Data**
   - Add new wells
   - Update rig availability
   - Adjust RTD dates
   - Modify priorities

3. **Re-Optimize**
   - Load existing schedule
   - Add/remove resources
   - Run optimization
   - Compare with original

4. **Analyze Impact**
   - Check affected assignments
   - Review cost changes
   - Assess timeline impact
   - Identify risks

5. **Communicate Changes**
   - Generate comparison report
   - Highlight differences
   - Explain reasons
   - Distribute updates

**Time Saved:** 2-3 days reduced to 4-6 hours

---

#### Workflow 3: Emergency Well Addition

**Scenario:** High-priority well needs to be scheduled urgently.

**Steps:**

1. **Add Well (15 minutes)**
   - Enter well details
   - Set priority to 1 (highest)
   - Set RTD date (immediate)
   - Validate data

2. **Quick Schedule (30 minutes)**
   - Load current schedule
   - Add new well
   - Run quick optimization (30 seconds)
   - Review assignments

3. **Assess Impact (15 minutes)**
   - Check displaced wells
   - Review cost impact
   - Verify feasibility
   - Identify conflicts

4. **Adjust & Finalize (30 minutes)**
   - Resolve conflicts
   - Adjust other assignments
   - Re-optimize if needed
   - Approve changes

5. **Communicate (15 minutes)**
   - Generate updated Gantt
   - Export affected assignments
   - Notify stakeholders
   - Update field teams

**Total Time:** 1.5-2 hours (vs. 1-2 days manually)

---

#### Workflow 4: Location-Specific Planning

**Scenario:** Planning drilling operations for a specific location.

**Steps:**

1. **Filter by Location**
   - Select location from dropdown
   - View location-specific wells
   - View location-specific rigs
   - Check location benchmarks

2. **Create Location Schedule**
   - Select location wells
   - Select location rigs
   - Set location-specific parameters
   - Run optimization

3. **Analyze Location Performance**
   - Review location Gantt
   - Check intra-location movements
   - Analyze location costs
   - Compare with other locations

4. **Optimize Location Operations**
   - Identify inefficiencies
   - Adjust rig allocations
   - Optimize well sequence
   - Minimize movements

5. **Report to Location Management**
   - Generate location report
   - Show KPIs
   - Highlight achievements
   - Recommend improvements

**Benefits:** Location autonomy with central oversight

---

#### Workflow 5: Rig Utilization Optimization

**Scenario:** Maximizing utilization of underutilized rigs.

**Steps:**

1. **Identify Underutilized Rigs**
   - View rig statistics
   - Check utilization percentages
   - Identify idle periods
   - Analyze causes

2. **Find Suitable Wells**
   - Search unscheduled wells
   - Filter by rig requirements
   - Check RTD dates
   - Verify priorities

3. **Assign Wells to Rigs**
   - Add wells to schedule
   - Assign to underutilized rigs
   - Run optimization
   - Check improvements

4. **Analyze Results**
   - Compare before/after utilization
   - Check cost impact
   - Verify feasibility
   - Assess benefits

5. **Implement Changes**
   - Approve new assignments
   - Update schedule
   - Notify teams
   - Monitor execution

**Impact:** 10-20% improvement in rig utilization

---

### 7.2 Best Practices

#### Data Management Best Practices

1. **Keep Data Current**
   - Update rig availability regularly
   - Adjust well RTD dates as needed
   - Remove completed wells
   - Archive old schedules

2. **Maintain Data Quality**
   - Validate all imports
   - Fix missing data promptly
   - Use intelligent fetch
   - Regular data audits

3. **Use Staging Area**
   - Stage new wells before finalizing
   - Validate in batches
   - Use baskets for grouping
   - Enrich data systematically

4. **Leverage Benchmarks**
   - Keep benchmarks updated
   - Add new performance data
   - Refine estimates regularly
   - Location-specific benchmarks

---

#### Scheduling Best Practices

1. **Set Realistic Priorities**
   - Use priority levels consistently
   - Don't over-prioritize
   - Balance urgency and feasibility
   - Review priorities regularly

2. **Optimize Iteratively**
   - Start with quick optimization
   - Refine with longer runs
   - Test different parameters
   - Compare results

3. **Consider Constraints**
   - Verify rig capabilities
   - Check temporal feasibility
   - Respect location boundaries
   - Account for weather/seasons

4. **Plan for Contingencies**
   - Create backup schedules
   - Identify critical paths
   - Have alternative rigs
   - Buffer time for delays

---

#### Analysis Best Practices

1. **Use Visualizations**
   - Review Gantt charts regularly
   - Check movement maps
   - Monitor dashboards
   - Track trends

2. **Compare Scenarios**
   - Create multiple versions
   - Test assumptions
   - Quantify differences
   - Document decisions

3. **Track Performance**
   - Monitor KPIs
   - Compare actual vs. planned
   - Identify deviations
   - Learn from history

4. **Communicate Effectively**
   - Use visual reports
   - Highlight key points
   - Explain changes clearly
   - Share insights

---


### 7.3 Industry-Specific Use Cases

#### Oil & Gas Exploration

**Challenge:** Optimize exploration drilling across multiple prospects.

**IDRS Solution:**
- Prioritize high-potential prospects
- Minimize rig mobilization costs
- Balance risk and opportunity
- Adapt to geological findings

**Benefits:**
- 30% reduction in mobilization costs
- Faster prospect evaluation
- Better resource allocation
- Data-driven decisions

---

#### Development Drilling

**Challenge:** Efficiently drill multiple development wells in a field.

**IDRS Solution:**
- Optimize well sequence
- Minimize intra-field movements
- Maximize rig utilization
- Coordinate with production

**Benefits:**
- 20% faster field development
- Reduced operational costs
- Improved production ramp-up
- Better coordination

---

#### Multi-Field Operations

**Challenge:** Coordinate drilling across multiple fields and locations.

**IDRS Solution:**
- Balance resources across fields
- Optimize inter-field movements
- Respect field priorities
- Manage multiple rigs

**Benefits:**
- 25% reduction in ILM costs
- Better resource utilization
- Improved coordination
- Centralized planning

---

#### Offshore Operations

**Challenge:** Optimize expensive offshore rig operations.

**IDRS Solution:**
- Minimize rig idle time
- Optimize well sequence
- Account for weather windows
- Maximize rig efficiency

**Benefits:**
- $5-10M savings per rig per year
- 15% improvement in utilization
- Reduced non-productive time
- Better weather planning

---

### 7.4 Business Value

#### Quantifiable Benefits

**Cost Savings:**
- **ILM Cost Reduction:** 20-40% savings
- **Rig Utilization:** 10-20% improvement
- **Planning Time:** 80-90% reduction
- **Operational Efficiency:** 15-25% improvement

**Time Savings:**
- **Schedule Creation:** Days → Hours
- **Scenario Analysis:** Hours → Minutes
- **Report Generation:** Hours → Seconds
- **Data Management:** 50% time reduction

**Quality Improvements:**
- **Schedule Optimality:** Near-optimal solutions
- **Data Accuracy:** 95%+ accuracy
- **Constraint Satisfaction:** 100% compliance
- **Decision Quality:** Data-driven decisions

---

#### Strategic Benefits

**Operational Excellence:**
- Standardized planning process
- Consistent methodology
- Best practice enforcement
- Continuous improvement

**Better Decision Making:**
- Data-driven insights
- Scenario analysis
- Risk assessment
- Informed choices

**Improved Collaboration:**
- Centralized platform
- Shared visibility
- Better communication
- Team alignment

**Competitive Advantage:**
- Faster planning cycles
- Lower costs
- Higher efficiency
- Better execution

---

#### Return on Investment (ROI)

**Typical ROI Calculation:**

**Investment:**
- Software license: $50,000/year
- Implementation: $20,000
- Training: $10,000
- Total Year 1: $80,000

**Annual Savings:**
- ILM cost reduction: $500,000
- Planning time savings: $100,000
- Improved utilization: $300,000
- Total Annual Savings: $900,000

**ROI:** 1,125% (11.25x return)  
**Payback Period:** 1 month

---

### 7.5 Success Stories

#### Case Study 1: Major Oil Company

**Challenge:**
- 150 wells across 5 locations
- 15 rigs with varying capabilities
- Complex constraints
- Manual planning taking 6 weeks

**Solution:**
- Implemented IDRS
- Imported all data
- Created master schedule
- Optimized in 2 minutes

**Results:**
- Planning time: 6 weeks → 3 days
- ILM costs: $15M → $9M (40% reduction)
- Rig utilization: 65% → 82%
- ROI: 1,500% in first year

---

#### Case Study 2: Independent Operator

**Challenge:**
- 50 wells in 3 fields
- 5 rigs
- Limited planning resources
- Frequent changes

**Solution:**
- Deployed IDRS
- Trained 3 planners
- Established workflows
- Integrated with existing systems

**Results:**
- Schedule updates: 2 days → 2 hours
- Cost savings: $2M/year
- Better resource utilization
- Improved stakeholder satisfaction

---

#### Case Study 3: Service Company

**Challenge:**
- Managing rigs for multiple clients
- Complex scheduling requirements
- Need for transparency
- Competitive pressure

**Solution:**
- Implemented IDRS
- Client-specific schedules
- Automated reporting
- API integration

**Results:**
- Client satisfaction: +35%
- Operational efficiency: +25%
- New business: +20%
- Competitive advantage

---


## Getting Started

### 8.1 Quick Start Guide

#### For New Users (15 Minutes)

**Step 1: Login (2 minutes)**
1. Open web browser
2. Navigate to IDRS URL
3. Enter username and password
4. Click "Login"

**Step 2: Watch Tutorial (5 minutes)**
1. Click "Video Tutorials" in sidebar
2. Watch "Getting Started" video
3. Understand basic navigation
4. Learn key features

**Step 3: Explore Dashboard (3 minutes)**
1. View dashboard widgets
2. Check recent activity
3. Review quick actions
4. Familiarize with layout

**Step 4: View Sample Schedule (5 minutes)**
1. Go to "Schedules"
2. Open a sample schedule
3. View Gantt chart
4. Explore schedule details

**You're Ready!** Start creating your own schedules.

---

#### For Administrators (1 Hour)

**Step 1: System Setup (15 minutes)**
1. Configure company codes
2. Set up locations
3. Configure system settings
4. Set default parameters

**Step 2: User Management (15 minutes)**
1. Create user accounts
2. Assign roles
3. Assign locations
4. Test access

**Step 3: Data Import (20 minutes)**
1. Import rig data
2. Import well data
3. Import benchmarks
4. Validate imports

**Step 4: Create Test Schedule (10 minutes)**
1. Select test wells
2. Select test rigs
3. Run optimization
4. Review results

**System Ready!** Train users and go live.

---

### 8.2 Training Resources

#### Video Tutorials
- **Getting Started:** 5 minutes
- **Data Management:** 15 minutes
- **Creating Schedules:** 20 minutes
- **Analysis Tools:** 15 minutes
- **Advanced Features:** 25 minutes
- **Total:** ~80 minutes

#### Documentation
- User Guide (this document)
- Quick Reference Cards
- FAQ Document
- Troubleshooting Guide
- API Documentation

#### Support
- Email support
- Help desk tickets
- User community forum
- Regular webinars
- On-site training (optional)

---

### 8.3 Common Questions

**Q: How long does optimization take?**  
A: Typically 30-120 seconds depending on problem size. Small schedules (10-20 wells) take 5-10 seconds.

**Q: Can I edit an optimized schedule?**  
A: Yes, you can manually adjust any assignment. You can also re-optimize after changes.

**Q: What if a well can't be scheduled?**  
A: The system provides reasons (capability mismatch, no available time, etc.) and suggestions for resolution.

**Q: Can I import data from Excel?**  
A: Yes, all entity types support Excel import. Templates are provided.

**Q: How accurate are the time estimates?**  
A: Estimates are based on historical benchmarks. Accuracy improves as you add more benchmark data.

**Q: Can multiple users work simultaneously?**  
A: Yes, the system supports unlimited concurrent users with proper access control.

**Q: Is my data secure?**  
A: Yes, all data is encrypted, access is controlled by roles, and all actions are logged.

**Q: Can I access IDRS on mobile?**  
A: Yes, the interface is responsive and works on tablets and smartphones.

**Q: How do I export a schedule?**  
A: Click "Export" button on schedule detail page. Choose format (PDF, Excel, CSV).

**Q: Can I undo changes?**  
A: Schedule changes are tracked. You can create branches to preserve original versions.

---

### 8.4 Troubleshooting

#### Common Issues

**Issue: Can't login**
- Check username/password
- Verify account is active
- Check LDAP connection
- Contact administrator

**Issue: No data visible**
- Check location assignment
- Verify permissions
- Check filters
- Refresh page

**Issue: Optimization fails**
- Check data completeness
- Verify constraints
- Reduce problem size
- Increase time limit

**Issue: Slow performance**
- Check internet connection
- Clear browser cache
- Close other tabs
- Contact support

**Issue: Import fails**
- Check file format
- Verify column names
- Check data types
- Review error messages

---

### 8.5 Support & Contact

#### Getting Help

**In-App Help:**
- Help icon (?) in top navigation
- Tooltips on hover
- Context-sensitive help
- Video tutorials

**Documentation:**
- User Guide (comprehensive)
- Quick Reference (printable)
- FAQ (common questions)
- API Docs (developers)

**Support Channels:**
- **Email:** support@idrs.com
- **Help Desk:** Submit ticket
- **Phone:** +1-XXX-XXX-XXXX
- **Forum:** community.idrs.com

**Response Times:**
- Critical issues: 2 hours
- High priority: 4 hours
- Normal: 24 hours
- Low priority: 48 hours

---

## Appendices

### Appendix A: Glossary

**Assignment:** A rig-well pairing with start and end dates.

**Basket:** A group of related wells for batch processing.

**Benchmark:** Historical performance data used for estimation.

**BOP Stack:** Blowout Preventer stack specification.

**Branch:** An alternative version of a schedule.

**Company Code:** Location identifier in the organizational structure.

**Constraint:** A rule that must be satisfied in scheduling.

**DRL Days:** Drilling days required for a well.

**Financial Year:** April to March fiscal year.

**Footprint:** Rig mobility type (Mobile/Fixed).

**Gantt Chart:** Visual timeline of schedule assignments.

**ILM:** Inter-Location Movement - rig movement between locations.

**Optimization:** Process of finding the best schedule.

**PT Days:** Production Testing days required for a well.

**Priority:** Importance level of a well (1-5).

**RTD:** Ready to Drill date for a well.

**Staged Well:** Well in staging area before finalization.

**TDS:** Top Drive System requirement.

**Well Profile:** Well trajectory type (Directional/Vertical/Sidetrack).

---

### Appendix B: Keyboard Shortcuts

**Global:**
- `Ctrl + /` - Show help
- `Ctrl + K` - Quick search
- `Esc` - Close modal/dialog

**Navigation:**
- `Alt + D` - Dashboard
- `Alt + M` - Data Management
- `Alt + S` - Scheduling
- `Alt + G` - Gantt Chart

**Actions:**
- `Ctrl + N` - New schedule
- `Ctrl + S` - Save
- `Ctrl + E` - Export
- `Ctrl + P` - Print

---

### Appendix C: API Quick Reference

**Base URL:** `https://your-server/api/`

**Authentication:** Token or Session

**Endpoints:**

```
GET    /api/schedules/              # List schedules
POST   /api/schedules/              # Create schedule
GET    /api/schedules/{id}/         # Get schedule
PUT    /api/schedules/{id}/         # Update schedule
DELETE /api/schedules/{id}/         # Delete schedule

GET    /api/rigs/                   # List rigs
POST   /api/rigs/                   # Create rig
GET    /api/rigs/{id}/              # Get rig
PUT    /api/rigs/{id}/              # Update rig

GET    /api/wells/                  # List wells
POST   /api/wells/                  # Create well
GET    /api/wells/{id}/             # Get well
PUT    /api/wells/{id}/             # Update well

GET    /api/baskets/                # List baskets
POST   /api/baskets/create/         # Create basket
GET    /api/baskets/{id}/           # Get basket
```

**Response Format:** JSON

**Example Request:**
```bash
curl -X GET https://your-server/api/schedules/ \
  -H "Authorization: Token your-token-here"
```

---

### Appendix D: File Format Specifications

#### Excel Import Format

**Rigs Sheet:**
| Column | Type | Required | Example |
|--------|------|----------|---------|
| name | Text | Yes | JOHN-1000-29 |
| location | Text | Yes | LOCATION-A |
| rig_type | Text | Yes | Mobile |
| start_date | Date | Yes | 2025-04-01 |
| end_date | Date | Yes | 2026-03-31 |
| rig_capacity_hp | Number | Yes | 2000 |
| bop_stack | Text | Yes | 10K |
| top_drive | Text | Yes | Y |

**Wells Sheet:**
| Column | Type | Required | Example |
|--------|------|----------|---------|
| name | Text | Yes | WELL-A-001 |
| asset_id | Text | No | AST-001 |
| field_name | Text | Yes | FIELD-A |
| well_type | Text | Yes | Development |
| depth | Number | Yes | 3500 |
| latitude | Number | Yes | 25.1234 |
| longitude | Number | Yes | 55.5678 |
| well_profile | Text | Yes | DI |
| rig_capacity_required_hp | Number | Yes | 2000 |
| drl_days | Number | Yes | 45 |
| pt_days | Number | Yes | 5.5 |
| rtd_date | Date | Yes | 2025-05-01 |
| priority | Number | Yes | 1 |

---

### Appendix E: Version History

**Version 9.0 (February 2026)**
- Added video tutorial system
- Implemented intelligent data fetching
- Enhanced basket management
- Improved performance
- Added location-based access control

**Version 8.0 (December 2025)**
- Added schedule branching
- Improved optimization engine
- Enhanced Gantt chart
- Added movement maps
- Better mobile support

**Version 7.0 (September 2025)**
- Added staged wells management
- Implemented well baskets
- Enhanced data validation
- Improved import/export
- Added audit trails

---

## Conclusion

The Interactive Drilling Rig Scheduler (IDRS) represents a comprehensive solution for modern drilling operations management. By combining advanced optimization algorithms, intuitive data management, and powerful analysis tools, IDRS enables organizations to:

- **Plan Faster:** Reduce planning time from weeks to hours
- **Optimize Better:** Achieve near-optimal schedules automatically
- **Decide Smarter:** Make data-driven decisions with confidence
- **Execute Efficiently:** Improve operational efficiency by 15-25%
- **Save Money:** Reduce costs by 20-40% through optimization

Whether you're planning annual drilling programs, managing multi-location operations, or responding to urgent changes, IDRS provides the tools and capabilities you need to succeed.

---

**For More Information:**
- Website: www.idrs.com
- Email: info@idrs.com
- Support: support@idrs.com
- Documentation: docs.idrs.com

**Copyright © 2026 Interactive Drilling Rig Scheduler. All rights reserved.**

---

*This document is confidential and proprietary. Unauthorized distribution is prohibited.*

