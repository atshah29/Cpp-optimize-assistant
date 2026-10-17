"""Fixed validation gates around bounded model proposals."""

import difflib
import json
from pathlib import Path
import shutil
import time
import zipfile

from feedback import ModelUnavailable, propose
from context import select_sources
from runner import Cancelled, Runner
from utils import apply_edits, project_digest, source_files


def make_context(root, options, baseline, history):
    files = source_files(root)
    allowed = set(options["editable_files"] or files)
    # Test sources remain immutable even if included in the build.
    allowed = {
        name
        for name in allowed
        if name in files
        and not any(
            part.lower() in {"test", "tests", "testing"}
            or part.lower().startswith("test_")
            or part.lower().endswith("_test.cpp")
            for part in Path(name).parts
        )
    }
    report = baseline.get("profile", {}).get("report", "")
    selected, windows = select_sources(
        files, allowed, baseline.get("analysis", {}), report, attempt=len(history)
    )
    allowed &= selected.keys()
    if not allowed:
        raise ValueError("No editable source could be selected within the prompt budget")
    context = {
        "sources": selected,
        "source_windows": windows,
        "editable_files": sorted(allowed),
        "omitted_files": sorted(files.keys() - selected.keys()),
        "benchmarks": baseline.get("benchmarks", {}),
        "profile": baseline.get("profile", {}),
        "symbols": baseline.get("analysis", {}).get("symbols", [])[:20],
        "history": [
            {key: str(item[key])[:1200] for key in ("explanation", "status", "reason") if key in item}
            for item in history[-2:]
        ],
        "constraints": "Same observable behavior; workload fixtures and build configuration are immutable. SOURCE EXCERPT markers are context annotations, not source text. Use exact existing source text for edits.",
    }
    context["profile"] = dict(context["profile"])
    if "report" in context["profile"]:
        context["profile"]["report"] = context["profile"]["report"][:2000]
    if len(json.dumps(context).encode()) > 14000:
        context["symbols"] = []
    return context, allowed


def optimize(directory: Path, options: dict, cancel, update, proposer=propose, runner_factory=Runner):
    runner = runner_factory(cancel, time.monotonic() + 900)
    original = directory / "original"
    best = directory / "best"
    shutil.copytree(original, best)
    update(stage="Building and validating original", progress=5)
    baseline = runner.evaluate(original, options)
    result = {
        "mode": options["mode"],
        "runner": runner.mode,
        "baseline": baseline,
        "attempts": [],
        "accepted_count": 0,
        "warnings": [],
        "options": options,
        "original_sha256": project_digest(original),
    }
    if runner.mode == "native":
        result["warnings"].append(
            "Native mode runs trusted code with your local permissions; it is not a sandbox."
        )
    if options["mode"] != "compile":
        result["warnings"].append(
            "Correctness is checked only on supplied workloads; this is not a proof for all inputs."
        )
    if options["mode"] == "optimize":
        failures, seen = 0, set()
        for i in range(options["attempts"]):
            if cancel.is_set():
                raise Cancelled("Job cancelled")
            update(
                stage=f"Preparing proposal {i + 1}/{options['attempts']}",
                progress=15 + i * 70 // options["attempts"],
            )
            candidate = directory / f"candidate-{i}"
            record = {"number": i + 1, "status": "rejected"}
            try:
                context, allowed = make_context(best, options, baseline, result["attempts"])
                proposal = proposer(context)
                if cancel.is_set():
                    raise Cancelled("Job cancelled")
                record["explanation"] = proposal.explanation
                record["model_call"] = proposal._metadata
                if not proposal.edits:
                    record.update(status="no_change", reason="Model found no justified change")
                    result["attempts"].append(record)
                    break
                shutil.copytree(best, candidate)
                record["diff"] = apply_edits(
                    candidate, [edit.model_dump() for edit in proposal.edits], allowed
                )
                fingerprint = project_digest(candidate)
                if fingerprint in seen:
                    raise ValueError("Repeated candidate; no extra benchmark was run")
                seen.add(fingerprint)
                update(stage=f"Testing and benchmarking proposal {i + 1}")
                evaluation = runner.evaluate(best, options, candidate, baseline["references"])
                record["evaluation"] = evaluation
                record["reason"] = evaluation["reason"]
                if evaluation["accepted"]:
                    # Refresh context/profile after structural changes; validation remains against original signatures.
                    update(stage="Refreshing accepted baseline")
                    refreshed = runner.evaluate(
                        candidate, options, references=result["baseline"]["references"]
                    )
                    shutil.rmtree(best)
                    shutil.copytree(candidate, best)
                    baseline = refreshed
                    record["status"] = "accepted"
                    result["accepted_count"] += 1
                    failures = 0
                else:
                    failures += 1
            except Cancelled:
                raise
            except ModelUnavailable as exc:
                result["warnings"].append(str(exc))
                record.update(status="unavailable", reason=str(exc))
                result["attempts"].append(record)
                break
            except (ValueError, RuntimeError) as exc:
                record["reason"] = str(exc)[:7000]
                failures += 1
            finally:
                if candidate.exists():
                    shutil.rmtree(candidate)
            result["attempts"].append(record)
            if failures >= 2:
                result["warnings"].append(
                    "Stopped after two unsuccessful proposals to conserve the model quota."
                )
                break
    if cancel.is_set():
        raise Cancelled("Job cancelled")
    result["final"] = baseline
    # Verify the complete result against the original, not just successive local improvements.
    if result["accepted_count"]:
        update(stage="Confirming final result against original", progress=90)
        try:
            final_check = runner.evaluate(original, options, best, result["baseline"]["references"])
        except Cancelled:
            raise
        except RuntimeError as exc:
            final_check = {"accepted": False, "reason": str(exc)}
        result["final_comparison"] = final_check
        if not final_check["accepted"]:
            shutil.rmtree(best)
            shutil.copytree(original, best)
            result["warnings"].append(
                "Final confirmation did not pass; the download contains the unchanged original."
            )
            result["accepted_count"] = 0
            result["final"] = result["baseline"]
    result["outcome"] = (
        "compiled"
        if options["mode"] == "compile"
        else "benchmarked"
        if options["mode"] == "benchmark"
        else "improved"
        if result["accepted_count"]
        else "unchanged"
    )
    old, new = source_files(original), source_files(best)
    result["diff"] = "".join(
        "".join(
            difflib.unified_diff(
                old[name].splitlines(keepends=True),
                new[name].splitlines(keepends=True),
                fromfile=f"a/{name}",
                tofile=f"b/{name}",
            )
        )
        for name in old
        if old[name] != new[name]
    )
    result["result_sha256"] = project_digest(best)
    (directory / "report.json").write_text(json.dumps(result, indent=2))
    (directory / "changes.diff").write_text(result["diff"])
    with zipfile.ZipFile(directory / "result.zip", "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(best.rglob("*")):
            if path.is_file():
                bundle.write(path, f"project/{path.relative_to(best).as_posix()}")
        bundle.write(directory / "report.json", "report.json")
        bundle.write(directory / "changes.diff", "changes.diff")
    return result
