"""Golden-fixture I/O, provenance capture and the anti-regeneration guard.

The preservation fixture (``fixtures/preservation_golden.json``) records what
the solver did **before** the deterministic-schedule-fix touched it.  Property 2
in ``design.md`` is defined against *today's* behaviour, so the fixture is the
only surviving record of that behaviour once task 3 lands.  It cannot be
re-derived: re-running the capture on fixed code produces the fixed code's
answers, which would turn the preservation test into a tautology that passes no
matter what task 3 broke.

Everything in this module exists to make that failure mode hard to reach by
accident:

* Regeneration requires ``IDRS_REGENERATE_GOLDEN=1``.  A plain test run never
  writes.
* The fixture records a SHA-256 of every production file whose behaviour it
  captures.  If any of those files has changed since capture, regeneration is
  **refused** — because at that point regenerating is exactly the mistake this
  module is here to prevent.  Overriding needs a second, deliberately
  unwieldy flag.
* A normal test run reports a production-file drift as information, not a
  failure.  After task 3 the files are *expected* to differ while the golden
  values must still hold — that is the whole point of the test.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

#: ``scheduler/tests/golden.py`` -> repo root.
REPO_ROOT = Path(__file__).resolve().parents[2]

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
FIXTURE_PATH = FIXTURE_DIR / "preservation_golden.json"

#: Set to 1 to rewrite the fixture from the current code.
REGENERATE_ENV_FLAG = "IDRS_REGENERATE_GOLDEN"

#: The override for the production-file drift guard.  Long and unpleasant on
#: purpose: nobody types this by accident, and anybody who does has read why.
FORCE_ENV_FLAG = "IDRS_GOLDEN_OVERWRITE_EVEN_THOUGH_THE_SOLVER_CHANGED"

#: One-line justification recorded alongside a re-baseline.  Required when
#: overwriting an existing fixture whose production code has drifted: the audit
#: trail has to say *why* a value moved, not merely that it did.
REBASELINE_REASON_ENV = "IDRS_GOLDEN_REBASELINE_REASON"

#: The only case fields a surgical re-baseline may re-anchor.
#:
#: ``model_fingerprint`` is a SHA-256 of the *input model proto*.  It describes
#: what was handed to CP-SAT, not what CP-SAT answered, so a deliberate model
#: change can move it while leaving the answer provably untouched — which is
#: exactly what adding a decision strategy does (task 7).  Nothing else is
#: listed, and in particular no answer field is: ``objective_value``,
#: ``schedule_hash``, ``assignments`` and the cost and date fields are the
#: baseline, and re-anchoring one of those would be replacing the record of the
#: pre-fix answer with the current answer, which is the exact failure mode this
#: module exists to prevent.
#:
#: Why a surgical re-baseline rather than a full ``write_golden`` re-capture:
#: a full re-capture rewrites *every* field from current behaviour, including the
#: pre-task-3 solver parameter block (``max_deterministic_time`` inf,
#: ``max_time_in_seconds`` 10, ``interleave_batch_size`` 0) that
#: ``STOP_CRITERION_PARAMETER_KEYS`` in ``test_preservation.py`` exempts from
#: equality and asserts positively instead.  That exemption is only meaningful
#: while the golden still holds the *pre-fix* values; re-capturing them turns it
#: into a no-op and quietly deletes the record of what the parameters used to be.
REBASELINEABLE_FIELDS = ("model_fingerprint",)

#: Production files whose behaviour the golden captures.  A change to any of
#: these can move the golden values, so their content hashes are the drift
#: signal.  Paths are relative to the repo root.
PRODUCTION_FILES = (
    "scheduler/optimization.py",
    "scheduler/views.py",
    "scheduler/models.py",
    "scheduler/serializers.py",
    "scheduler/well_rejection_analyzer.py",
    "drilling_scheduler/settings.py",
)

#: Paths that are allowed to be dirty at capture time without the capture being
#: considered contaminated: the spec documents and the test package itself.
#: ``scheduler/tests.py`` is in here because task 1 replaced that placeholder
#: module with the ``scheduler/tests/`` package, so git reports it deleted.
_TEST_AND_DOC_PREFIXES = (
    ".kiro/",
    "scheduler/tests/",
    "scheduler/tests.py",
)

_BANNER_WIDTH = 78


# ---------------------------------------------------------------------------
# JSON coercion
# ---------------------------------------------------------------------------


def jsonable(value: Any) -> Any:
    """Coerce solver output into JSON types without losing information.

    ``_extract_solution`` hands back ``date`` objects and the input dicts carry
    ``Decimal`` columns, neither of which ``json`` will serialise.  Dates become
    ISO strings and ``Decimal`` becomes ``str`` (not ``float``) so a money value
    survives the round trip exactly.
    """
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return value


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


def _git(*args: str, strip: bool = True) -> Optional[str]:
    """Run a git command and return stdout, or ``None`` if it could not run.

    ``strip=False`` is required for ``status --porcelain``: its first two
    characters are the staged/unstaged status columns, and an unstaged
    modification puts a **space** in column 1. Stripping the block would eat
    that space and shift every subsequent column left by one, so a path would
    lose its first character.
    """
    try:
        out = subprocess.run(
            ["git", *args],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip() if strip else out.stdout


def _porcelain_paths() -> List[str]:
    """Paths git reports as changed, from ``git status --porcelain``.

    Read unstripped — see ``_git``. With the block stripped, a leading
    ``" M .kiro/..."`` became ``"M .kiro/..."`` and the ``line[3:]`` slice
    returned ``"kiro/..."``, which then failed to match the ``.kiro/`` prefix
    in ``_TEST_AND_DOC_PREFIXES`` and got misreported as a modified production
    file.
    """
    status = _git("status", "--porcelain", strip=False)
    if not status or not status.strip():
        return []
    paths: List[str] = []
    for line in status.splitlines():
        if not line.strip():
            continue
        # "XY <path>" or "XY <old> -> <new>" for renames.
        payload = line[3:].strip()
        if " -> " in payload:
            payload = payload.split(" -> ", 1)[1]
        paths.append(payload.strip('"'))
    return paths


def file_hashes() -> Dict[str, Optional[str]]:
    """SHA-256 of each production file the golden depends on."""
    hashes: Dict[str, Optional[str]] = {}
    for rel in PRODUCTION_FILES:
        path = REPO_ROOT / rel
        if not path.is_file():
            hashes[rel] = None
            continue
        hashes[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def provenance() -> Dict[str, Any]:
    """Everything needed to audit where the golden came from.

    The commit SHA is the headline, but on its own it is not enough: a working
    tree can differ from its commit.  So the dirty-path list is recorded too,
    split into paths that are harmless for a capture (spec docs, the test
    package) and paths that mean the capture did **not** come from the recorded
    commit's production code.
    """
    dirty = _porcelain_paths()
    contaminating = [
        path
        for path in dirty
        if not any(path.startswith(prefix) for prefix in _TEST_AND_DOC_PREFIXES)
    ]

    try:
        import django

        django_version = django.get_version()
    except Exception:  # pragma: no cover - django is a hard dependency here
        django_version = None
    try:
        import ortools

        ortools_version = getattr(ortools, "__version__", None)
    except Exception:  # pragma: no cover
        ortools_version = None

    return {
        "git_commit": _git("rev-parse", "HEAD"),
        "git_commit_short": _git("rev-parse", "--short", "HEAD"),
        "git_branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "captured_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "captured_on": date.today().isoformat(),
        "working_tree_dirty_paths": sorted(dirty),
        "working_tree_production_files_modified": sorted(contaminating),
        "working_tree_clean_of_production_files": not contaminating,
        "production_file_sha256": file_hashes(),
        "ortools_version": ortools_version,
        "python_version": sys.version.split()[0],
        "django_version": django_version,
        "platform": platform.platform(),
        "cpu_count": os.cpu_count(),
    }


def production_file_drift(golden: Dict[str, Any]) -> Dict[str, Dict[str, Optional[str]]]:
    """Production files whose content differs from the fixture's record.

    Returns ``{path: {"golden": sha, "current": sha}}`` for each mismatch.  An
    empty dict means the code under test is byte-identical to the code the
    golden was captured from.
    """
    recorded = (golden.get("provenance") or {}).get("production_file_sha256") or {}
    current = file_hashes()
    drift: Dict[str, Dict[str, Optional[str]]] = {}
    for rel, recorded_hash in recorded.items():
        current_hash = current.get(rel)
        if recorded_hash != current_hash:
            drift[rel] = {"golden": recorded_hash, "current": current_hash}
    return drift


# ---------------------------------------------------------------------------
# Read / write
# ---------------------------------------------------------------------------

_README = [
    "PRESERVATION GOLDEN BASELINE - captured from the UNFIXED code.",
    "",
    "This file records what scheduler/optimization.py and the save path did",
    "BEFORE the deterministic-schedule-fix spec changed them. It is the",
    "reference for Property 2 (Preservation) in",
    ".kiro/specs/deterministic-schedule-fix/design.md: a request that already",
    "closes to a proven, UNIQUE optimum must keep returning exactly this",
    "schedule, this objective_value and this schedule_hash after the fix.",
    "",
    "DO NOT REGENERATE THIS FILE TO MAKE A FAILING TEST PASS.",
    "A test failing against this fixture is the fixture doing its job: it",
    "means a change moved an answer that was already correct. Regenerating",
    "would overwrite the only record of the pre-fix behaviour with the",
    "post-fix behaviour and turn the preservation test into a tautology that",
    "can never fail again.",
    "",
    "Regeneration is gated on IDRS_REGENERATE_GOLDEN=1 and is refused",
    "outright once any production file listed under",
    "provenance.production_file_sha256 has changed. See scheduler/tests/",
    "golden.py for the guard.",
]

#: Appended to the README when the fixture has been re-baselined at least once,
#: i.e. when ``provenance_history`` is non-empty.  Without this the header would
#: keep claiming the whole file came from unfixed code, which stops being true
#: for any field a re-baseline moved.
_REBASELINE_README = [
    "",
    "---",
    "",
    "THIS FIXTURE HAS BEEN RE-BASELINED. See provenance_history.",
    "",
    "Read the header above with that in mind: the ANSWER fields (objective_",
    "value, schedule_hash, assignments, dates, sequence_order, costs) still",
    "trace back to the original pre-fix capture, because a re-baseline is only",
    "permitted after proving those fields did not move. What a re-baseline",
    "re-anchors is a field that describes the MODEL or the SOLVER rather than",
    "the answer -- model_fingerprint being the case this mechanism was built",
    "for.",
    "",
    "provenance_history is ordered oldest-first. Entry 0 is the original",
    "pre-fix capture; each entry records the commit it came from, the",
    "production files that had changed by the time it was superseded, and the",
    "one-line reason given for superseding it.",
    "",
    "The rule the re-baseline does NOT relax: every field in the fixture,",
    "model_fingerprint included, stays under byte-for-byte comparison. A",
    "re-baseline re-anchors a value; it never stops the value being checked.",
]


def golden_exists() -> bool:
    return FIXTURE_PATH.is_file()


def load_golden() -> Dict[str, Any]:
    """Read the fixture, or explain how to create it."""
    if not golden_exists():
        raise AssertionError(
            f"Preservation golden fixture is missing at {FIXTURE_PATH}.\n"
            "It must be captured from the UNFIXED code (spec task 2) before any "
            "solver change lands. Capture it with:\n\n"
            f"    {REGENERATE_ENV_FLAG}=1 python manage.py test "
            "scheduler.tests.test_preservation\n"
        )
    with FIXTURE_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def regeneration_requested() -> bool:
    return os.environ.get(REGENERATE_ENV_FLAG, "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def _banner(lines: List[str]) -> str:
    edge = "!" * _BANNER_WIDTH
    body = "\n".join(f"!! {line}".ljust(_BANNER_WIDTH - 2)[: _BANNER_WIDTH - 2] + "!!" for line in lines)
    return f"\n{edge}\n{body}\n{edge}\n"


def assert_regeneration_is_safe() -> None:
    """Refuse to overwrite a golden captured from different production code.

    This is the guard that matters.  Regenerating before task 3 is routine —
    the fixture is being created or a scenario was adjusted, and the production
    code is untouched.  Regenerating *after* task 3 is the mistake, because the
    baseline it would overwrite is unrecoverable.  The production-file hashes
    tell the two situations apart without needing anyone to remember which
    tasks have landed.
    """
    if not golden_exists():
        return  # First capture; there is nothing to destroy.

    drift = production_file_drift(load_golden())
    if not drift:
        return

    if os.environ.get(FORCE_ENV_FLAG, "").strip() == "1":
        print(
            _banner(
                [
                    "OVERWRITING THE PRESERVATION BASELINE ON CHANGED CODE.",
                    "",
                    f"{FORCE_ENV_FLAG} is set, so the drift guard was skipped.",
                    "The pre-fix baseline is being replaced by whatever the",
                    "current code produces. Property 2 can no longer detect a",
                    "regression introduced before this moment.",
                    "",
                    *(f"changed: {path}" for path in sorted(drift)),
                ]
            )
        )
        return

    golden = load_golden()
    commit = (golden.get("provenance") or {}).get("git_commit")
    changed = "\n".join(f"      - {path}" for path in sorted(drift))
    raise AssertionError(
        "REFUSING to regenerate the preservation golden.\n\n"
        f"The fixture at {FIXTURE_PATH}\n"
        f"was captured from commit {commit}, and these production files have\n"
        f"changed since then:\n{changed}\n\n"
        "Regenerating now would overwrite the pre-fix baseline with the current\n"
        "code's output. That baseline is the only record of how the solver\n"
        "behaved before this spec's changes, and Property 2 (Preservation) is\n"
        "defined against it — so overwriting it does not fix a failure, it\n"
        "deletes the ability to detect one.\n\n"
        "If a preservation test is failing, the change under test moved an\n"
        "answer that was already correct. Fix the change, not the fixture.\n\n"
        "If you genuinely need a new baseline (for example the spec is complete\n"
        "and you are re-baselining deliberately), set\n"
        f"    {FORCE_ENV_FLAG}=1\n"
        "and commit the result as its own reviewable change."
    )


def superseded_provenance_entry(
    golden: Dict[str, Any], reason: Optional[str]
) -> Dict[str, Any]:
    """The history record for a baseline that is about to be replaced.

    Carries the essentials of the outgoing capture — which commit it came from,
    when, against which ortools, and the production-file hashes that were in
    force — plus the drift that made the re-baseline necessary and the reason
    given for it.

    Why this exists: ``write_golden`` used to overwrite ``provenance``
    wholesale, so a re-baseline erased the identity of the baseline it replaced.
    For a fixture whose entire purpose is provenance, losing the previous
    commit SHA is the one thing that must not happen.  A re-baseline is now
    additive: the chain of what-replaced-what stays readable in the file.
    """
    previous = dict(golden.get("provenance") or {})
    drift = production_file_drift(golden)
    return {
        "superseded_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "reason": reason or "(no reason recorded)",
        "git_commit": previous.get("git_commit"),
        "git_commit_short": previous.get("git_commit_short"),
        "git_branch": previous.get("git_branch"),
        "captured_at": previous.get("captured_at"),
        "captured_on": previous.get("captured_on"),
        "ortools_version": previous.get("ortools_version"),
        "python_version": previous.get("python_version"),
        "django_version": previous.get("django_version"),
        "platform": previous.get("platform"),
        "production_file_sha256": previous.get("production_file_sha256"),
        "production_files_changed_since": sorted(drift),
    }


def rebaseline_fields(
    updates: Dict[str, Dict[str, Any]], *, reason: str
) -> Dict[str, Any]:
    """Re-anchor a few named leaf fields, leaving every other field untouched.

    The narrow alternative to a full ``write_golden`` re-capture, for the case
    where a deliberate change moves a field that describes the *model* while the
    *answer* is provably unchanged.

    ``updates`` is ``{case_name: {field_name: new_value}}``.  Every field named
    must be in :data:`REBASELINEABLE_FIELDS`, must already exist in that case,
    and must actually differ — so this cannot be used to introduce a field, to
    edit an answer, or to silently no-op.

    Guarded exactly like ``write_golden``: ``IDRS_REGENERATE_GOLDEN=1`` to run at
    all, and the drift override once production code has moved.  A reason is
    mandatory here rather than optional, because a surgical edit is even less
    self-explanatory after the fact than a full re-capture.
    """
    if not regeneration_requested():
        raise AssertionError(
            f"rebaseline_fields() requires {REGENERATE_ENV_FLAG}=1."
        )
    if not (reason or "").strip():
        raise AssertionError(
            "A re-baseline needs a one-line reason for the audit trail. "
            f"Pass reason= or set {REBASELINE_REASON_ENV}."
        )
    if not golden_exists():
        raise AssertionError(
            "There is no fixture to re-baseline. Capture one with "
            f"{REGENERATE_ENV_FLAG}=1 first."
        )

    golden = load_golden()
    cases = golden.get("cases") or {}

    planned: List[str] = []
    for case_name, fields in updates.items():
        if case_name not in cases:
            raise AssertionError(
                f"Case '{case_name}' is not in the fixture; cannot re-baseline it."
            )
        for field, new_value in fields.items():
            if field not in REBASELINEABLE_FIELDS:
                raise AssertionError(
                    f"Refusing to re-baseline '{case_name}.{field}'. Only "
                    f"{list(REBASELINEABLE_FIELDS)} may be re-anchored; "
                    "everything else in the fixture is the pre-fix baseline and "
                    "re-anchoring it would delete the record it exists to keep."
                )
            if field not in cases[case_name]:
                raise AssertionError(
                    f"'{case_name}.{field}' is not in the fixture, so there is "
                    "nothing to re-anchor. This mechanism updates existing "
                    "values; it does not add fields."
                )
            old_value = cases[case_name][field]
            if old_value == new_value:
                raise AssertionError(
                    f"'{case_name}.{field}' already equals the supplied value. "
                    "A re-baseline that changes nothing means the caller is "
                    "working from a stale diff."
                )
            planned.append(f"{case_name}.{field}: {old_value} -> {new_value}")

    # Drift guard last, so a malformed request is rejected on its own terms
    # rather than behind the override prompt.
    assert_regeneration_is_safe()

    history = list(golden.get("provenance_history") or [])
    history.append(superseded_provenance_entry(golden, reason))

    new_provenance = provenance()
    new_provenance["rebaseline_reason"] = reason.strip()
    new_provenance["supersedes_git_commit"] = history[-1].get("git_commit")
    new_provenance["rebaseline_kind"] = "surgical"
    new_provenance["rebaselined_fields"] = sorted(planned)

    for case_name, fields in updates.items():
        for field, new_value in fields.items():
            cases[case_name][field] = new_value

    readme = [line for line in golden.get("_README") or _README]
    if not any("RE-BASELINED" in line for line in readme):
        readme = readme + _REBASELINE_README

    payload: Dict[str, Any] = {
        "_README": readme,
        "schema_version": golden.get("schema_version", 1),
        "provenance": new_provenance,
        "provenance_history": history,
        "cases": cases,
    }

    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    with FIXTURE_PATH.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=False)
        handle.write("\n")

    print(
        _banner(
            [
                "PRESERVATION GOLDEN RE-BASELINED (surgical).",
                "",
                f"file    : {FIXTURE_PATH.relative_to(REPO_ROOT)}",
                f"reason  : {reason.strip()[:60]}",
                f"replaces: {history[-1].get('git_commit')}",
                "",
                "fields re-anchored:",
                *(f"  {line[:66]}" for line in planned),
                "",
                "Every other field is byte-identical to the previous baseline.",
            ]
        )
    )
    return payload


def write_golden(cases: Dict[str, Any]) -> Dict[str, Any]:
    """Write the fixture.  Only reachable when regeneration was requested."""
    existing = load_golden() if golden_exists() else None
    reason = (os.environ.get(REBASELINE_REASON_ENV) or "").strip() or None

    # Computed *before* the file is replaced: after the write, the outgoing
    # provenance is gone and the drift cannot be recomputed.
    history: List[Dict[str, Any]] = []
    if existing is not None:
        history = list(existing.get("provenance_history") or [])
        history.append(superseded_provenance_entry(existing, reason))

    assert_regeneration_is_safe()

    current_provenance = provenance()
    if history:
        current_provenance["rebaseline_reason"] = reason or "(no reason recorded)"
        current_provenance["supersedes_git_commit"] = history[-1].get("git_commit")

    payload: Dict[str, Any] = {
        "_README": _README + (_REBASELINE_README if history else []),
        "schema_version": 1,
        "provenance": current_provenance,
    }
    if history:
        # Ordered oldest-first, so provenance_history[0] is the original
        # pre-fix capture that Property 2 was first defined against.
        payload["provenance_history"] = history
    payload["cases"] = jsonable(cases)

    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    with FIXTURE_PATH.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=False)
        handle.write("\n")

    prov = payload["provenance"]
    lines = [
        "PRESERVATION GOLDEN REWRITTEN.",
        "",
        f"file   : {FIXTURE_PATH.relative_to(REPO_ROOT)}",
        f"commit : {prov['git_commit']}",
        f"cases  : {', '.join(sorted(cases))}",
        "",
        "This baseline must come from the UNFIXED code. If any solver change",
        "has already landed, discard this file and restore the committed one.",
    ]
    if not prov["working_tree_clean_of_production_files"]:
        lines += [
            "",
            "WARNING: production files were modified in the working tree at",
            "capture time, so this baseline does NOT correspond to the commit",
            "above:",
            *(
                f"  {path}"
                for path in prov["working_tree_production_files_modified"]
            ),
        ]
    print(_banner(lines))
    return payload
