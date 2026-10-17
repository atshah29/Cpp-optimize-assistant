"""Run compiler workloads outside the API process, with explicit isolation policy."""

import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid


class Cancelled(RuntimeError):
    pass


class Runner:
    def __init__(self, cancel: threading.Event, deadline: float):
        self.cancel = cancel
        self.deadline = deadline
        self.mode = os.getenv("OPTIMIZER_RUNNER", "docker")
        if self.mode not in {"docker", "native"}:
            raise ValueError("OPTIMIZER_RUNNER must be docker or native")

    def evaluate(self, baseline: Path, options: dict, candidate: Path | None = None, references=None):
        if self.cancel.is_set():
            raise Cancelled("Job cancelled")
        container = f"cpp-optimizer-{uuid.uuid4().hex}"
        # macOS container VMs share the project/home tree, not /var/folders.
        # Stage read-only inputs there instead of requiring broad host mounts.
        staging = Path(os.getenv("OPTIMIZER_JOB_DIR", str(Path(__file__).parent / ".optimizer-jobs")))
        staging.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=staging, prefix="runner-") as folder:
            scratch = Path(folder)
            code = scratch / "code"
            code.mkdir()
            for name in ("worker.py", "analyze.py", "utils.py"):
                shutil.copy2(Path(__file__).parent / name, code / name)
            payload = {"options": options, "references": references or {}}
            if self.mode == "docker":
                if not shutil.which("docker"):
                    raise RuntimeError(
                        "Docker is required. Build the runner image using the README, or explicitly configure native mode for trusted local code."
                    )
                staged_baseline = scratch / "baseline"
                shutil.copytree(baseline, staged_baseline)
                staged_candidate = scratch / "candidate"
                if candidate:
                    shutil.copytree(candidate, staged_candidate)
                for path in scratch.rglob("*"):
                    path.chmod(0o755 if path.is_dir() else 0o644)
                args = [
                    "docker",
                    "run",
                    "--rm",
                    "--pull=never",
                    "--name",
                    container,
                    "--network=none",
                    "--read-only",
                    "--cap-drop=ALL",
                    "--security-opt=no-new-privileges",
                    "--pids-limit=128",
                    "--memory=1g",
                    "--memory-swap=1g",
                    "--cpus=1",
                    "--user=65534:65534",
                    "--ulimit",
                    "fsize=67108864:67108864",
                    "--tmpfs",
                    "/tmp:rw,exec,nosuid,size=512m,mode=1777",
                    "--mount",
                    f"type=bind,source={staged_baseline.resolve()},target=/baseline,readonly",
                    "--mount",
                    f"type=bind,source={code.resolve()},target=/code,readonly",
                    "-i",
                ]
                payload["baseline"] = "/baseline"
                if candidate:
                    args += [
                        "--mount",
                        f"type=bind,source={staged_candidate.resolve()},target=/candidate,readonly",
                    ]
                    payload["candidate"] = "/candidate"
                args += [
                    os.getenv("OPTIMIZER_IMAGE", "cpp-optimizer-runner:local"),
                    "python3",
                    "/code/worker.py",
                ]
            else:
                payload["baseline"] = str(baseline.resolve())
                if candidate:
                    payload["candidate"] = str(candidate.resolve())
                args = [sys.executable, str(code / "worker.py")]
            environment = {
                name: os.environ[name]
                for name in ("PATH", "DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_CONFIG", "HOME")
                if name in os.environ
            }
            environment["TMPDIR"] = folder
            with (
                tempfile.TemporaryFile() as inp,
                tempfile.TemporaryFile() as out,
                tempfile.TemporaryFile() as err,
            ):
                inp.write(json.dumps(payload).encode())
                inp.seek(0)
                process = subprocess.Popen(
                    args,
                    cwd=scratch,
                    env=environment,
                    stdin=inp,
                    stdout=out,
                    stderr=err,
                    start_new_session=True,
                )
                try:
                    while process.poll() is None:
                        if self.cancel.is_set():
                            raise Cancelled("Job cancelled")
                        if time.monotonic() > self.deadline:
                            raise RuntimeError("Job reached its 15-minute execution budget")
                        if os.fstat(out.fileno()).st_size + os.fstat(err.fileno()).st_size > 2_000_000:
                            raise RuntimeError("Worker exceeded its output limit")
                        time.sleep(0.1)
                    out.seek(0)
                    err.seek(0)
                    if process.returncode:
                        raise RuntimeError(f"Runner failed: {err.read(4000).decode(errors='replace')}")
                    response = json.loads(out.read(2_000_001))
                    if not response["ok"]:
                        raise RuntimeError(response["error"])
                    return response["result"]
                finally:
                    if process.poll() is None:
                        try:
                            os.killpg(process.pid, signal.SIGTERM)
                        except ProcessLookupError:
                            pass
                        try:
                            process.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            os.killpg(process.pid, signal.SIGKILL)
                            process.wait()
                    if self.mode == "docker":
                        try:
                            subprocess.run(["docker", "rm", "-f", container], capture_output=True, timeout=15)
                        except (OSError, subprocess.TimeoutExpired):
                            pass
