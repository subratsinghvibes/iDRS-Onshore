# Deterministic and Optimal Scheduling Plan for iDRS

## Purpose

This document provides a **clear, step‑by‑step implementation plan** to
resolve the non‑deterministic scheduling issue and ensure that the
drilling schedule produced by the system is:

1.  Deterministic (same input → same output)
2.  Optimized (minimum cost / best objective)
3.  Scalable to larger datasets

This plan is written so **any AI system or developer can directly
implement the fixes**.

------------------------------------------------------------------------

# Problem Overview

The Intelligent Drilling Rig Scheduler currently produces **different
schedules on repeated runs** for the same data.

Root causes identified:

1.  Solver runs in **multi‑threaded mode**
2.  **Decision strategy not defined**
3.  Deterministic mode **not activated from Django views**
4.  **Pairwise ILM ordering variables explode model size**
5.  Time limits insufficient for deterministic optimal proof

These lead to:

-   Non‑deterministic solutions
-   Suboptimal schedules
-   Slow solve times

------------------------------------------------------------------------

# High-Level Solution Strategy

The solution will be implemented in **three phases**.

  Phase     Objective
  --------- ------------------------------------------
  Phase 1   Stabilize solver (deterministic results)
  Phase 2   Guarantee optimal schedules
  Phase 3   Improve model efficiency and scalability

------------------------------------------------------------------------

# Phase 1 --- Enforce Deterministic Solver Behaviour

## Goal

Ensure that **the same inputs always produce the same schedule**.

------------------------------------------------------------------------

## Step 1: Force Single Threaded Solver

Inside the solver configuration function:

``` python
solver.parameters.num_search_workers = 1
```

Reason:

Multi-threading allows workers to explore different parts of the search
tree simultaneously which produces different valid solutions.

------------------------------------------------------------------------

## Step 2: Force Fixed Search Strategy

Add:

``` python
solver.parameters.search_branching = cp_model.FIXED_SEARCH
```

Reason:

Without FIXED_SEARCH, the solver automatically changes search
strategies.

------------------------------------------------------------------------

## Step 3: Fix Random Seed

Add:

``` python
solver.parameters.random_seed = 42
```

Reason:

Prevents stochastic solver behaviour.

------------------------------------------------------------------------

## Step 4: Disable Strategy Interleaving

Add:

``` python
solver.parameters.interleave_search = False
```

Reason:

Prevents solver from switching between heuristics.

------------------------------------------------------------------------

# Phase 2 --- Define Explicit Branching Strategy

This is the **most critical fix**.

Without this, the solver still explores variables in a non‑deterministic
order.

------------------------------------------------------------------------

## Step 1: Create Variable Lists

Inside `setup_variables()`:

``` python
assignment_vars = []
start_vars = []
```

Populate them in a deterministic order:

``` python
for well in sorted(wells):
    for rig in sorted(rigs):
        assignment_vars.append(assign[well, rig])
        start_vars.append(start_time[well, rig])
```

------------------------------------------------------------------------

## Step 2: Add Decision Strategy

``` python
model.AddDecisionStrategy(
    assignment_vars,
    cp_model.CHOOSE_FIRST,
    cp_model.SELECT_MAX_VALUE
)

model.AddDecisionStrategy(
    start_vars,
    cp_model.CHOOSE_FIRST,
    cp_model.SELECT_MIN_VALUE
)
```

Meaning:

Solver explores decisions in the following order:

1.  Assign wells to rigs
2.  Then schedule start times
3.  Prefer earlier schedules

------------------------------------------------------------------------

# Phase 3 --- Activate Deterministic Mode in Django

All solver calls must include:

``` python
scheduler.solve(..., deterministic=True)
```

The following functions must be updated in `views.py`:

-   run_full_optimization
-   schedule generation endpoint
-   reschedule logic
-   scenario simulation
-   any background optimization tasks

Every call must pass the deterministic flag.

------------------------------------------------------------------------

# Phase 4 --- Increase Solve Time

Deterministic mode is slower because parallel search is disabled.

Recommended limit:

``` python
time_limit_seconds = 1800
```

(30 minutes)

Typical expected behaviour:

  Wells   Rigs   Expected Solve Time
  ------- ------ ---------------------
  20      4      1--5 min
  50      6      5--15 min
  100     8      15--45 min

------------------------------------------------------------------------

# Phase 5 --- Enforce Optimality Validation

Only accept schedules where:

    solver_status == OPTIMAL
    optimality_gap == 0

Implementation already exists in `OptimalityValidator`.

Add validation after solve:

``` python
if result["solver_status"] != "OPTIMAL":
    raise Exception("Schedule not proven optimal")
```

Optional:

Run solver twice and compare schedule hashes.

------------------------------------------------------------------------

# Phase 6 --- Model Optimization (Major Speed Improvement)

Current model uses **pairwise ILM ordering variables**.

Complexity:

    O(wells² × rigs)

For 100 wells this creates **\~79,000 variables**.

------------------------------------------------------------------------

## Replace With Interval Scheduling

Instead of pairwise ordering:

Create interval variables.

Example:

``` python
interval = model.NewOptionalIntervalVar(
    start,
    duration,
    end,
    assignment_var
)
```

Then for each rig:

``` python
model.AddNoOverlap(intervals_for_rig)
```

This automatically determines order.

New complexity:

    O(wells × rigs)

------------------------------------------------------------------------

# Phase 7 --- Long-Term Architecture Upgrade

Convert model to **rig routing formulation**.

Each rig becomes a route:

    Rig → Well A → Well B → Well C

Implementation uses:

    model.AddCircuit(arcs)

Arc variable example:

``` python
x[A,B] = 1 if rig travels from A to B
```

Mobilization cost becomes arc cost.

This formulation is widely used in industrial planning software.

Benefits:

-   Massive reduction in variables
-   Faster optimal solutions
-   Scales to 300+ wells

------------------------------------------------------------------------

# Final Architecture

Final solver structure:

    Input Data
         ↓
    Assignment Variables
         ↓
    Routing / Interval Scheduling
         ↓
    Movement Constraints
         ↓
    Objective Minimization
         ↓
    Optimality Validation
         ↓
    Certified Schedule

------------------------------------------------------------------------

# Expected Outcomes

After implementing Phases 1--4:

• deterministic schedules\
• mathematically optimal results\
• stable solver behaviour

After implementing Phase 6:

• 10--50× faster solving\
• scalability to large field planning

------------------------------------------------------------------------

# Implementation Priority

  Priority   Task
  ---------- ------------------------------------
  1          Deterministic solver configuration
  2          Decision strategy
  3          Update Django solver calls
  4          Increase time limit
  5          Optimality validation
  6          Interval scheduling refactor
  7          Routing model upgrade

------------------------------------------------------------------------

# Conclusion

The scheduler will transition from:

**heuristic-style exploration**

to

**deterministic mathematical optimization**.

This ensures:

-   reproducible schedules
-   provable optimality
-   industrial-scale performance.
