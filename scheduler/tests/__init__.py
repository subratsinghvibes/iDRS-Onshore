"""Test package for the ``scheduler`` app.

Replaces the former ``scheduler/tests.py`` placeholder.  Django's test runner
discovers tests inside a package exactly as it does inside a module, so
``python manage.py test scheduler`` keeps working unchanged.

Modules
-------
factories
    Builders that create the DB rows (``CompanyCode``, ``RigBuildingNorm``,
    ``Rig``, ``Well``, ``WellPairDistance``, ``RigBuildingAdjustment``) *and*
    return the matching input dicts, so the optimizer exercises the real ILM
    path rather than its fallback.
test_determinism
    Repeat-run harness for the deterministic-schedule-fix spec (clause 2.12).
test_tie_enumeration
    Counts how many distinct schedules attain the optimal objective value.
"""
