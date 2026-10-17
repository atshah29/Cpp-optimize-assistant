import hashlib
import json

import pytest

from benchmark_suite import summarize
from llvm_suite import MANIFEST, catalog, fetch, reference_stdout
from pipeline import validate_drivers


def test_pinned_manifest_and_reference_format():
    data = json.loads(MANIFEST.read_text())
    assert len(data["revision"]) == 40
    assert len(catalog()) == 5
    assert all(len(item["sha256"]) == 64 for item in data["files"].values())
    assert reference_stdout("42\nexit 0\n") == "42\n"
    with pytest.raises(ValueError):
        reference_stdout("42\nexit 1\n")


def test_external_suite_does_not_claim_twenty_benchmarks():
    entries = catalog()
    state = {
        "suite": "llvm",
        "catalog": entries,
        "results": {item[0]: {"status": "completed", "reduction": 0.9, "speedup": 10} for item in entries},
    }
    result = summarize(state)
    assert result["suite_size"] == 5
    assert result["mean_runtime_reduction_percent"] == 90
    assert not result["claim_70_percent_supported"]


def test_verified_cached_files_need_no_network(tmp_path, monkeypatch):
    payload = b"source"
    spec = {
        "revision": "a" * 40,
        "files": {"a.cpp": {"path": "a.cpp", "sha256": hashlib.sha256(payload).hexdigest()}},
    }
    monkeypatch.setattr("llvm_suite.manifest", lambda: spec)
    root = tmp_path / spec["revision"]
    root.mkdir()
    (root / "a.cpp").write_bytes(payload)
    monkeypatch.setattr("llvm_suite.urlopen", lambda *a, **kw: pytest.fail("Unexpected download"))
    assert fetch(tmp_path) == root


def test_benchmark_repetition_cannot_be_removed(tmp_path):
    driver = "int main() { for (int i=0; i<1000; ++i) calculate(); }"
    file = tmp_path / "matrix.cpp"
    file.write_text("void calculate() {}\n" + driver)
    validate_drivers(tmp_path, {"matrix.cpp": driver})
    file.write_text("void calculate() {}\nint main() { calculate(); }")
    with pytest.raises(ValueError, match="Protected benchmark driver changed"):
        validate_drivers(tmp_path, {"matrix.cpp": driver})
