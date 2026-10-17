from benchmark_suite import summarize
from benchmarks.catalog import CATALOG, oracle, workloads
from feedback import model_settings


def test_suite_has_22_distinct_benchmarks_with_oracles():
    assert len(CATALOG) == len({entry[0] for entry in CATALOG}) == 22
    for entry in CATALOG:
        cases = workloads(entry)
        assert len(cases) == 6
        assert sum(case.get("benchmark", True) for case in cases) == 2
        assert cases[0]["expected_stdout"] == "0\n"
        assert oracle(entry[0], 8, 19) >= 0


def test_summary_includes_unchanged_and_rejects_partial_claim():
    results = {entry[0]: {"status": "completed", "reduction": 0.8, "speedup": 5.0} for entry in CATALOG}
    results[CATALOG[0][0]].update(reduction=0, speedup=1)
    summary = summarize({"results": results})
    assert abs(summary["mean_runtime_reduction_percent"] - (21 * 80 / 22)) < 0.001
    assert summary["claim_70_percent_supported"]
    results[CATALOG[1][0]]["status"] = "deferred"
    assert not summarize({"results": results})["claim_70_percent_supported"]
    for row in results.values():
        row.update(status="completed", reduction=None)
    assert summarize({"results": results})["mean_runtime_reduction_percent"] is None


def test_model_configuration_preserves_requested_model(monkeypatch):
    for name in ("GROQ_MODEL", "GROQ_TEMPERATURE", "GROQ_REASONING_EFFORT", "GROQ_MAX_COMPLETION_TOKENS"):
        monkeypatch.delenv(name, raising=False)
    settings = model_settings()
    assert settings["model"] == "openai/gpt-oss-120b"
    assert settings["max_completion_tokens"] == 2048
    assert settings["reasoning_effort"] == "medium"
    assert settings["stream"] is False
