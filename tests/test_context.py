from context import select_sources


def test_large_file_selects_hot_function_and_reports_partial_context():
    padding = "// unrelated padding\n" * 1000
    function = "int expensive(int x) { return x * 2; }\n"
    files = {"large.cpp": padding + function, "types.hpp": "struct Value { int x; };\n"}
    symbols = [
        {
            "file": "large.cpp",
            "name": "expensive(int)",
            "kind": "FUNCTION_DECL",
            "definition": True,
            "line": 1001,
            "end_line": 1001,
        }
    ]
    selected, windows = select_sources(files, {"large.cpp"}, {"symbols": symbols}, "expensive")
    assert function in selected["large.cpp"]
    assert "types.hpp" in selected
    assert not windows["large.cpp"]["complete"]
    assert [1001, 1001] in windows["large.cpp"]["ranges"]
    assert sum(len(text.encode()) for text in selected.values()) <= 8000


def test_large_file_without_ast_still_gets_a_window():
    selected, windows = select_sources({"a.cpp": "int x;\n" * 5000}, {"a.cpp"}, {}, "")
    assert selected["a.cpp"]
    assert not windows["a.cpp"]["complete"]


def test_small_files_remain_exact_and_editable_files_get_priority():
    selected, windows = select_sources({"a.hpp": "x" * 8000, "z.cpp": "int main() {}"}, {"z.cpp"}, {}, "")
    assert selected["z.cpp"] == "int main() {}"
    assert windows["z.cpp"]["complete"]
