import os
import shutil
import subprocess
import threading
import time

import pytest

from runner import Cancelled, Runner
from schemas import Options
from worker import StageError, command, run


def compiler_available():
    if not shutil.which("clang++"):
        return False
    return subprocess.run(["clang++", "--version"], capture_output=True).returncode == 0


compiler = pytest.mark.skipif(not compiler_available(), reason="Clang toolchain unavailable")


def options(**changes):
    return Options(mode="benchmark", profile=False, repeats=5, **changes).model_dump()


def test_timeout_kills_program(tmp_path):
    import sys

    with pytest.raises(StageError, match="timed out"):
        command([sys.executable, "-c", "import time; time.sleep(10)"], tmp_path, 0.05)


def test_output_is_bounded(tmp_path):
    import sys

    with pytest.raises(StageError, match="output limit"):
        command([sys.executable, "-c", "print('x' * 2000000)"], tmp_path)


@compiler
def test_compile_only_does_not_execute(tmp_path):
    (tmp_path / "main.cpp").write_text("int main() { for (;;) {} }")
    result = run({"baseline": str(tmp_path), "options": Options(mode="compile").model_dump()})
    assert result["compiled"] and not result["executed"]
    assert "clang" in result["environment"]["compiler"].lower()


@compiler
@pytest.mark.parametrize("extension", ["cpp", "cc", "cxx", "c"])
def test_baseline_all_supported_extensions(tmp_path, extension):
    (tmp_path / f"main.{extension}").write_text('#include <stdio.h>\nint main() { puts("42"); }')
    result = run({"baseline": str(tmp_path), "options": options()})
    assert result["executed"]
    assert len(result["benchmarks"]["default"]["samples"]) == 5


@compiler
def test_wrong_candidate_rejected_even_if_fast(tmp_path):
    baseline, candidate = tmp_path / "old", tmp_path / "new"
    baseline.mkdir()
    candidate.mkdir()
    (baseline / "main.cpp").write_text('#include <cstdio>\nint main() { puts("42"); }')
    (candidate / "main.cpp").write_text('#include <cstdio>\nint main() { puts("43"); }')
    with pytest.raises(StageError, match="candidate output differs"):
        run({"baseline": str(baseline), "candidate": str(candidate), "options": options()})


@compiler
def test_expected_outputs_enforced(tmp_path):
    (tmp_path / "main.cpp").write_text('#include <cstdio>\nint main() { puts("42"); }')
    with pytest.raises(StageError, match="expected stdout mismatch"):
        run({"baseline": str(tmp_path), "options": options(cases=[{"expected_stdout": "43\n"}])})


@compiler
def test_nondeterministic_output_rejected(tmp_path):
    (tmp_path / "main.cpp").write_text(
        '#include <cstdio>\n#include <unistd.h>\nint main() { printf("%d", getpid()); }'
    )
    with pytest.raises(StageError, match="nondeterministic"):
        run({"baseline": str(tmp_path), "options": options()})


@compiler
def test_working_directory_stdin_args_and_reset_fixtures(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data/input.txt").write_text("7")
    (tmp_path / "main.cpp").write_text("""#include <fstream>
#include <iostream>
int main(int argc, char** argv) {
 int a, b; std::ifstream("input.txt") >> a; std::cin >> b;
 std::ofstream("input.txt") << 999;
 std::ofstream("answer.txt") << a+b;
 std::cout << argv[1] << ":" << a+b << "\\n";
}""")
    result = run(
        {
            "baseline": str(tmp_path),
            "options": options(
                working_dir="data",
                cases=[
                    {
                        "args": ["answer"],
                        "stdin": "5",
                        "expected_stdout": "answer:12\n",
                        "output_files": ["answer.txt"],
                    }
                ],
            ),
        }
    )
    assert result["references"]["default"]["files"]["answer.txt"]
    assert (tmp_path / "data/input.txt").read_text() == "7"


@compiler
def test_native_runner_protocol(tmp_path, monkeypatch):
    monkeypatch.setenv("OPTIMIZER_RUNNER", "native")
    (tmp_path / "main.cpp").write_text("int main() {}")
    runner = Runner(threading.Event(), time.monotonic() + 30)
    assert not runner.evaluate(tmp_path, Options(mode="compile").model_dump())["executed"]


@compiler
@pytest.mark.skipif(
    not shutil.which("cmake") or not (shutil.which("ninja") or shutil.which("make")),
    reason="CMake/build tool unavailable",
)
def test_cmake_project_build_and_workloads(tmp_path):
    import json
    from pathlib import Path

    source = Path(__file__).resolve().parents[1] / "examples/cmake"
    project = tmp_path / "project"
    shutil.copytree(source, project)
    config = Options.model_validate(json.loads((project / "optimizer.json").read_text())).model_dump()
    result = run({"baseline": str(project), "options": config})
    assert set(result["benchmarks"]) == {"positive", "negative"}


def test_cancel_before_launch(tmp_path):
    event = threading.Event()
    event.set()
    with pytest.raises(Cancelled):
        Runner(event, time.monotonic() + 1).evaluate(tmp_path, options())


@pytest.mark.skipif(os.getenv("TEST_DOCKER") != "1", reason="Set TEST_DOCKER=1 after building runner image")
def test_docker_runner_isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("OPTIMIZER_RUNNER", "docker")
    tmp_path.chmod(0o755)
    (tmp_path / "main.cpp").write_text("""#include <cstdlib>
#include <cstdio>
int main() { puts(getenv("GROQ_API_KEY") ? "LEAK" : "isolated"); }
""")
    result = Runner(threading.Event(), time.monotonic() + 120).evaluate(
        tmp_path,
        Options(
            mode="benchmark", profile=False, repeats=5, cases=[{"expected_stdout": "isolated\n"}]
        ).model_dump(),
    )
    assert result["executed"]
