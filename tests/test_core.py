import json
import stat
import threading
import zipfile

import pytest

from pipeline import optimize
from schemas import Options, Proposal
from utils import apply_edits, extract_project, inside, source_files
from worker import compare_samples


def archive(tmp_path, entries):
    path = tmp_path / "test.zip"
    with zipfile.ZipFile(path, "w") as bundle:
        for name, value in entries:
            bundle.writestr(name, value)
    return path


@pytest.mark.parametrize(
    "name", ["../evil.cpp", "/tmp/evil.cpp", "a/../../evil.cpp", "C:/evil.cpp", "a\\evil.cpp"]
)
def test_paths_cannot_escape(tmp_path, name):
    with pytest.raises(ValueError):
        inside(tmp_path, name)
    bundle = archive(tmp_path, [(name, "bad")])
    with pytest.raises(ValueError):
        extract_project(bundle, tmp_path / "result")


def test_archive_rejects_symlinks(tmp_path):
    info = zipfile.ZipInfo("link.cpp")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    bundle = archive(tmp_path, [(info, "/etc/passwd")])
    with pytest.raises(ValueError, match="symlinks"):
        extract_project(bundle, tmp_path / "result")


def test_archive_retains_structure_and_filters_build_artifacts(tmp_path):
    bundle = archive(
        tmp_path,
        [
            ("src/a.cpp", "int f() {}"),
            ("include/a.h", "#pragma once"),
            (".env", "secret"),
            ("build/file.o", "artifact"),
        ],
    )
    root = tmp_path / "result"
    extract_project(bundle, root)
    assert set(source_files(root)) == {"src/a.cpp", "include/a.h"}
    assert not (root / ".env").exists()
    assert not (root / "build").exists()


def test_archive_limits(tmp_path, monkeypatch):
    monkeypatch.setattr("utils.MAX_EXTRACTED", 10)
    with pytest.raises(ValueError, match="too large"):
        extract_project(archive(tmp_path, [("a.cpp", "x" * 11)]), tmp_path / "out")


def test_edits_are_transactional(tmp_path):
    source = tmp_path / "a.cpp"
    source.write_text("int f() { return 1; }\n")
    edits = [
        {"path": "a.cpp", "old": "return 1;", "new": "return 2;"},
        {"path": "a.cpp", "old": "missing", "new": "replacement"},
    ]
    with pytest.raises(ValueError):
        apply_edits(tmp_path, edits, {"a.cpp"})
    assert "return 1" in source.read_text()
    diff = apply_edits(tmp_path, edits[:1], {"a.cpp"})
    assert "-int f() { return 1; }" in diff
    assert "return 2" in source.read_text()


def test_overloads_namespaces_and_headers_are_preserved(tmp_path):
    source = "namespace A { int f(int x) { return x + 0; } double f(double x) { return x; } }\n"
    (tmp_path / "a.cpp").write_text(source)
    (tmp_path / "a.hpp").write_text("// untouched header\n")
    apply_edits(tmp_path, [{"path": "a.cpp", "old": "return x + 0;", "new": "return x;"}], {"a.cpp"})
    assert (tmp_path / "a.cpp").read_text() == source.replace("x + 0", "x")
    assert (tmp_path / "a.hpp").read_text() == "// untouched header\n"


def test_acceptance_rejects_noise_regressions_and_tiny_workloads():
    assert compare_samples({"x": [1.0] * 7}, {"x": [0.7] * 7}, 0.03)["accepted"]
    assert not compare_samples({"x": [1.0] * 7}, {"x": [0.99] * 7}, 0.03)["accepted"]
    assert not compare_samples({"x": [0.001] * 7}, {"x": [0.0001] * 7}, 0.03)["accepted"]
    assert not compare_samples({"x": [1.0] * 7}, {"x": [0.5, 1.5, 0.5, 1.5, 0.5, 1.5, 0.5]}, 0.03)["accepted"]
    assert not compare_samples({"x": [1.0] * 7, "y": [0.1] * 7}, {"x": [0.5] * 7, "y": [0.2] * 7}, 0.03)[
        "accepted"
    ]


@pytest.mark.parametrize(
    "options",
    [
        {"working_dir": "../"},
        {"sources": ["/etc/passwd"]},
        {"repeats": 1},
        {"attempts": 100},
        {"build": "cmake"},
        {"unknown": 123},
        {"cases": []},
    ],
)
def test_invalid_options(options):
    with pytest.raises(ValueError):
        Options.model_validate(options)


def test_rejected_candidate_never_mutates_best(tmp_path):
    (tmp_path / "original").mkdir()
    (tmp_path / "original/main.cpp").write_text("int main() { return 0; }\n")
    calls, prompts = [], []

    class FakeRunner:
        mode = "docker"

        def __init__(self, *_):
            pass

        def evaluate(self, root, options, candidate=None, references=None):
            calls.append(root)
            if candidate:
                assert "return 1" in (candidate / "main.cpp").read_text()
                raise RuntimeError("candidate output differs from the original")
            return {"references": {"default": {}}, "benchmarks": {}, "profile": {}, "analysis": {}}

    def proposer(context):
        prompts.append(context)
        if len(prompts) == 2:
            assert "output differs" in context["history"][0]["reason"]
            assert "return 0" in context["sources"]["main.cpp"]
            return Proposal(explanation="No further safe improvement", edits=[])
        return Proposal(
            explanation="Test change", edits=[{"path": "main.cpp", "old": "return 0", "new": "return 1"}]
        )

    report = optimize(
        tmp_path,
        Options(profile=False).model_dump(),
        threading.Event(),
        lambda **_: None,
        proposer,
        FakeRunner,
    )
    assert report["outcome"] == "unchanged"
    assert report["original_sha256"] == report["result_sha256"]
    with zipfile.ZipFile(tmp_path / "result.zip") as bundle:
        assert b"return 0" in bundle.read("project/main.cpp")
        assert json.loads(bundle.read("report.json"))["outcome"] == "unchanged"


def test_compile_mode_never_calls_model(tmp_path):
    (tmp_path / "original").mkdir()
    (tmp_path / "original/main.cpp").write_text("int main() {}")

    class FakeRunner:
        mode = "docker"

        def __init__(self, *_):
            pass

        def evaluate(self, *_):
            return {"compiled": True, "executed": False}

    def forbidden(_):
        pytest.fail("Compile mode called the model")

    result = optimize(
        tmp_path,
        Options(mode="compile").model_dump(),
        threading.Event(),
        lambda **_: None,
        forbidden,
        FakeRunner,
    )
    assert result["outcome"] == "compiled"
    assert not result["baseline"]["executed"]


def test_failed_final_confirmation_restores_original(tmp_path):
    (tmp_path / "original").mkdir()
    (tmp_path / "original/main.cpp").write_text("int main() { return 0; }")

    class FakeRunner:
        mode = "docker"
        comparisons = 0

        def __init__(self, *_):
            pass

        def evaluate(self, root, options, candidate=None, references=None):
            if candidate:
                self.comparisons += 1
                return {"accepted": self.comparisons == 1, "reason": "measurement", "after": {}}
            return {"references": {}, "benchmarks": {}, "profile": {}, "analysis": {}}

    def proposer(_):
        return Proposal(
            explanation="Test change", edits=[{"path": "main.cpp", "old": "return 0", "new": "return 1"}]
        )

    result = optimize(
        tmp_path, Options(attempts=1).model_dump(), threading.Event(), lambda **_: None, proposer, FakeRunner
    )
    assert result["outcome"] == "unchanged"
    assert result["original_sha256"] == result["result_sha256"]
