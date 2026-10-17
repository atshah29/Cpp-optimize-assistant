"""Standard-library execution worker, normally run inside the restricted container.

Never imports the API or the model client. Timing is measured inside the worker,
excluding container startup, compilation, and fixture preparation.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
from pathlib import Path
import random
import shutil
import signal
import statistics
import subprocess
import sys
import tempfile
import time

from analyze import analyze_project
from utils import IGNORED, inside, source_files

OUTPUT_LIMIT = 1024 * 1024


class StageError(RuntimeError):
    pass


def interrupted(_signal, _frame):
    raise KeyboardInterrupt("Worker cancelled")


def terminate(process):
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except PermissionError:
        # macOS can report EPERM for a process group whose leader just exited.
        # If the child is still alive, fall back to terminating that owned process.
        if process.poll() is None:
            process.kill()


def command(args, cwd, timeout=120, stdin=""):
    """Bound output and kill the whole process group, including on successful exit."""
    environment = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(cwd),
        "LANG": "C",
        "LC_ALL": "C",
        "OMP_NUM_THREADS": "1",
    }
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err, tempfile.TemporaryFile() as inp:
        inp.write(stdin.encode())
        inp.seek(0)
        started = time.perf_counter()
        try:
            process = subprocess.Popen(
                args, cwd=cwd, env=environment, stdin=inp, stdout=out, stderr=err, start_new_session=True
            )
        except OSError as exc:
            raise StageError(f"Cannot start {args[0]}: {exc}") from exc
        failure = None
        try:
            while process.poll() is None:
                if time.perf_counter() - started > timeout:
                    failure = f"Command timed out after {timeout}s"
                    break
                if os.fstat(out.fileno()).st_size + os.fstat(err.fileno()).st_size > OUTPUT_LIMIT:
                    failure = "Command exceeded the output limit"
                    break
                time.sleep(0.001)
        finally:
            elapsed = time.perf_counter() - started
            terminate(process)
            process.wait()
        out.seek(0)
        err.seek(0)
        stdout, stderr = out.read(OUTPUT_LIMIT + 1), err.read(OUTPUT_LIMIT + 1)
        if failure or len(stdout) + len(stderr) > OUTPUT_LIMIT:
            raise StageError(failure or "Command exceeded the output limit")
        if process.returncode != 0:
            raise StageError(f"Exit {process.returncode}: {stderr.decode(errors='replace')[-6000:]}")
        return stdout, stderr, elapsed


def copy_project(source, target):
    shutil.copytree(source, target, ignore=shutil.ignore_patterns(*IGNORED), symlinks=False)


def build(root: Path, options: dict) -> Path:
    directory = root / ".optimizer-build"
    directory.mkdir()
    if options["build"] == "cmake":
        command(
            [
                "cmake",
                "-S",
                str(root),
                "-B",
                str(directory),
                "-G",
                "Ninja" if shutil.which("ninja") else "Unix Makefiles",
                "-DCMAKE_BUILD_TYPE=Release",
                "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON",
                "-DCMAKE_C_FLAGS_RELEASE=-O3 -DNDEBUG -g",
                "-DCMAKE_CXX_FLAGS_RELEASE=-O3 -DNDEBUG -g",
            ],
            root,
        )
        command(["cmake", "--build", str(directory), "--target", options["cmake_target"], "-j", "1"], root)
        executable = inside(directory, options["executable"])
    else:
        names = options["sources"] or [
            name for name in source_files(root) if Path(name).suffix in {".cpp", ".cc", ".cxx", ".c"}
        ]
        if not names:
            raise StageError("No C/C++ source files found")
        objects, database = [], []
        for i, name in enumerate(names):
            source = inside(root, name)
            if source.suffix not in {".cpp", ".cc", ".cxx", ".c"} or not source.is_file():
                raise StageError(f"Invalid source file: {name}")
            obj = directory / f"{i}.o"
            compiler = "clang" if source.suffix == ".c" else "clang++"
            standard = "c17" if source.suffix == ".c" else options["standard"]
            args = [
                compiler,
                "-O3",
                "-g",
                f"-std={standard}",
                f"-I{root}",
                *[f"-I{inside(root, inc)}" for inc in options["include_dirs"]],
                "-c",
                str(source),
                "-o",
                str(obj),
            ]
            command(args, root)
            objects.append(str(obj))
            database.append({"directory": str(root), "file": str(source), "arguments": args})
        (directory / "compile_commands.json").write_text(json.dumps(database))
        executable = directory / "program"
        command(["clang++", "-O3", *objects, "-o", str(executable)], root)
    if not executable.is_file():
        raise StageError("Build did not produce the configured executable")
    return executable


def execute(root, executable, options, case, parent, prefix=None):
    with tempfile.TemporaryDirectory(dir=parent) as folder:
        fixture = Path(folder) / "project"
        copy_project(root, fixture)
        cwd = inside(fixture, options["working_dir"])
        if not cwd.is_dir():
            raise StageError("Working directory does not exist")
        stdout, stderr, elapsed = command(
            [*(prefix or []), str(executable), *case["args"]],
            cwd,
            timeout=options["run_timeout"] if not prefix else 30,
            stdin=case["stdin"],
        )
        outputs = {}
        for name in case["output_files"]:
            path = inside(cwd, name)
            if not path.is_file() or path.stat().st_size > OUTPUT_LIMIT:
                raise StageError(f"Missing or oversized output file: {name}")
            outputs[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        for name, actual in [("stdout", stdout), ("stderr", stderr)]:
            expected = case.get(f"expected_{name}")
            if expected is not None and actual != expected.encode():
                raise StageError(f"{case['name']}: expected {name} mismatch; got {actual[:300]!r}")
        signature = {
            "stdout": hashlib.sha256(stdout).hexdigest(),
            "stderr": hashlib.sha256(stderr).hexdigest(),
            "files": outputs,
        }
        return {"seconds": elapsed, "signature": signature, "observable": bool(stdout or stderr or outputs)}


def summary(values):
    median = statistics.median(values)
    mad = statistics.median(abs(value - median) for value in values)
    return {"median_seconds": median, "mad_seconds": mad, "samples": values}


def compare_samples(before: dict, after: dict, minimum: float) -> dict:
    """Paired bootstrap across complete workload rounds; require gains above noise."""
    names = list(before)
    old = [sum(before[name][i] for name in names) for i in range(len(before[names[0]]))]
    new = [sum(after[name][i] for name in names) for i in range(len(after[names[0]]))]
    gains = [(a - b) / a for a, b in zip(old, new)]
    rng = random.Random(2026)
    boots = sorted(statistics.median(rng.choices(gains, k=len(gains))) for _ in range(2000))
    lower = boots[50]
    gain = statistics.median(gains)
    regressions = []
    for name in names:
        a, b = summary(before[name]), summary(after[name])
        noise = 3 * (a["mad_seconds"] + b["mad_seconds"])
        if b["median_seconds"] - a["median_seconds"] > max(a["median_seconds"] * 0.01, noise):
            regressions.append(name)
    too_short = any(statistics.median(before[name]) < 0.005 for name in names)
    accepted = lower >= minimum and not regressions and not too_short
    reason = (
        "Workloads are shorter than 5 ms; increase input size for reliable timing"
        if too_short
        else f"Regression on: {', '.join(regressions)}"
        if regressions
        else "Improvement did not clear the configured threshold with 95% bootstrap confidence"
        if not accepted
        else "Outputs matched and measured improvement cleared the acceptance threshold"
    )
    return {
        "accepted": accepted,
        "gain": gain,
        "lower_confidence_gain": lower,
        "reason": reason,
        "before": {name: summary(values) for name, values in before.items()},
        "after": {name: summary(values) for name, values in after.items()},
    }


def profile(root, executable, options, parent):
    if not options["profile"]:
        return {"available": False, "reason": "Profiling disabled"}
    if not shutil.which("valgrind") or not shutil.which("callgrind_annotate"):
        return {"available": False, "reason": "Callgrind is unavailable on this runner"}
    output = parent / "callgrind.out"
    workload = next(case for case in options["cases"] if case.get("benchmark", True))
    try:
        execute(
            root,
            executable,
            options,
            workload,
            parent,
            ["valgrind", "--tool=callgrind", f"--callgrind-out-file={output}", "--quiet"],
        )
        stdout, _, _ = command(["callgrind_annotate", "--auto=no", "--threshold=95", str(output)], parent, 15)
        return {
            "available": True,
            "metric": "instruction counts (not wall-clock time)",
            "workload": workload["name"],
            "report": stdout.decode(errors="replace")[:7000],
        }
    except (StageError, ValueError) as exc:
        return {"available": False, "reason": str(exc)[:1000]}


def run(payload: dict) -> dict:
    options = payload["options"]
    with tempfile.TemporaryDirectory() as folder:
        parent = Path(folder)
        baseline = parent / "baseline"
        copy_project(Path(payload["baseline"]), baseline)
        executable = build(baseline, options)
        compiler, _, _ = command(["clang++", "--version"], baseline, 10)
        environment = {
            "compiler": compiler.decode(errors="replace").strip(),
            "system": platform.platform(),
            "architecture": platform.machine(),
            "optimization": "-O3",
            "timer": "time.perf_counter",
            "omp_num_threads": 1,
        }
        if options["mode"] == "compile":
            return {"compiled": True, "executed": False, "environment": environment}
        candidate = parent / "candidate"
        candidate_exe = None
        if payload.get("candidate"):
            copy_project(Path(payload["candidate"]), candidate)
            candidate_exe = build(candidate, options)
        references, before, after = {}, {}, {}
        for case in options["cases"]:
            name = case["name"]
            warmup = execute(baseline, executable, options, case, parent)
            if not warmup["observable"] and options["mode"] == "optimize":
                raise StageError(
                    f"{name}: no observable output. Print a deterministic result/checksum or declare output_files."
                )
            expected = payload.get("references", {}).get(name, warmup["signature"])
            if warmup["signature"] != expected:
                raise StageError(f"{name}: original behavior changed between evaluations")
            references[name] = expected
            if candidate_exe:
                checked = execute(candidate, candidate_exe, options, case, parent)
                if checked["signature"] != expected:
                    raise StageError(f"{name}: candidate output differs from the original")
            before[name], after[name] = [], []
            for i in range(options["repeats"] if case.get("benchmark", True) else 2):
                order = [(baseline, executable, before[name])]
                if candidate_exe:
                    order.append((candidate, candidate_exe, after[name]))
                    if i % 2:
                        order.reverse()
                for root, program, times in order:
                    measured = execute(root, program, options, case, parent)
                    if measured["signature"] != expected:
                        raise StageError(
                            f"{name}: output mismatch or nondeterministic behavior; use deterministic workloads"
                        )
                    times.append(measured["seconds"])
            if not case.get("benchmark", True):
                del before[name]
                del after[name]
        if candidate_exe:
            return {
                "compiled": True,
                "executed": True,
                "correctness": "passed supplied workloads",
                **compare_samples(before, after, options["min_improvement"]),
            }
        try:
            analysis = analyze_project(
                baseline, baseline / ".optimizer-build", options["standard"], options["include_dirs"]
            )
        except Exception as exc:
            analysis = {"available": False, "reason": str(exc)[:1000], "symbols": []}
        return {
            "compiled": True,
            "executed": True,
            "environment": environment,
            "references": references,
            "benchmarks": {name: summary(values) for name, values in before.items()},
            "profile": profile(baseline, executable, options, parent),
            "analysis": analysis,
        }


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, interrupted)
    try:
        print(json.dumps({"ok": True, "result": run(json.load(sys.stdin))}, allow_nan=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)[:7000]}))
