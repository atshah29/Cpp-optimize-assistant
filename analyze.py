import sys
import os
import json
import copy
from clang import cindex
from clang.cindex import TranslationUnit
from feedback import reinforcement_loop
from utils import compile_and_run_project, json_to_cpp

# Point Python to libclang
cindex.Config.set_library_file("/opt/homebrew/opt/llvm/lib/libclang.dylib")

def analyze_cpp_file(filepath, clang_args = None):
    headers, functions, diagnostics, classes, enums = set(), {}, [], {}, {}



    index = cindex.Index.create()
    tu = index.parse(
        filepath,
        args=clang_args if clang_args else[
            "-std=c++17",
            "-I/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/include/c++/v1",
            "-I/Library/Developer/CommandLineTools/usr/include/c++/v1",
            "-isysroot", "/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk"
        ],
        options=TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD
    )

    recursiveSearch(tu.cursor, filepath, headers, functions, classes, enums)

    # Diagnostics
    severity_map = {0: "Ignored", 1: "Note", 2: "Warning", 3: "Error", 4: "Fatal"}
    for element in tu.diagnostics:
        if element.location.file and element.location.file.name != filepath:
            continue
        diagnostics.append(f"{severity_map[element.severity]}: {element.spelling} at {element.location}")

    return {
        "headers": headers,
        "functions": functions,
        "diagnostics": diagnostics,
        "classes": classes,
        "enums": enums
    }

def recursiveSearch(node, filepath, headers, functions, classes, enums, current_class=None):
    for child in node.get_children():
        # Header includes
        if child.kind == cindex.CursorKind.INCLUSION_DIRECTIVE and child.location.file and child.location.file.name == filepath:
            headers.add(child.spelling)

        # Free functions
        elif child.kind == cindex.CursorKind.FUNCTION_DECL and current_class is None:
            if child.location.file and child.location.file.name == filepath:
                with open(child.location.file.name) as f:
                    lines = f.readlines()
                    code = "".join(lines[child.extent.start.line - 1 : child.extent.end.line])
                    functions[child.spelling] = code.strip()

        # Classes
        elif child.kind in (cindex.CursorKind.CLASS_DECL, cindex.CursorKind.STRUCT_DECL, cindex.CursorKind.CLASS_TEMPLATE):
            if child.location.file and child.location.file.name == filepath:
                name = child.spelling if child.spelling else "<anonymous>"
                with open(child.location.file.name) as f:
                    lines = f.readlines()
                    code = "".join(lines[child.extent.start.line - 1 : child.extent.end.line])
                classes[name] = {"definition": code.strip(), "methods": {}}
                recursiveSearch(child, filepath, headers, functions, classes, enums, current_class=name)
                continue

        # Methods
        elif child.kind in (cindex.CursorKind.CXX_METHOD, cindex.CursorKind.CONSTRUCTOR, cindex.CursorKind.DESTRUCTOR, cindex.CursorKind.FUNCTION_TEMPLATE):
            if current_class and child.location.file and child.location.file.name == filepath:
                with open(child.location.file.name) as f:
                    lines = f.readlines()
                    code = "".join(lines[child.extent.start.line - 1 : child.extent.end.line])
                    classes[current_class]["methods"][child.spelling] = code.strip()

        # Enums
        elif child.kind == cindex.CursorKind.ENUM_DECL:
            if child.location.file and child.location.file.name == filepath:
                name = child.spelling if child.spelling else "<anonymous_enum>"
                with open(child.location.file.name) as f:
                    lines = f.readlines()
                    code = "".join(lines[child.extent.start.line - 1 : child.extent.end.line])
                    enums[name] = code.strip()

        recursiveSearch(child, filepath, headers, functions, classes, enums, current_class)

def analyze_cpp_project(filepaths, with_ai=False, clang_args = None):
    project_results = {
        "headers": set(),
        "functions": {},
        "classes": {},
        "enums": {},
        "diagnostics": [],
    }

    # Analyze each file
    for fp in filepaths:
        if not fp.endswith(".cpp"):
            continue   # <---- skip headers here
        results = analyze_cpp_file(fp, clang_args)
        project_results["headers"].update(results["headers"])
        project_results["functions"].update(results["functions"])
        project_results["classes"].update(results["classes"])
        project_results["enums"].update(results["enums"])
        project_results["diagnostics"].extend(results["diagnostics"])

    # Compile all files together
    baseline = compile_and_run_project(filepaths)
    print(f"Baseline runtime: {baseline:.6f}s" if baseline else "Baseline runtime: None")

    # Convert headers to sorted list
    project_results["headers"] = sorted(project_results["headers"])

    if with_ai and project_results["functions"]:
        best_json, best_time = reinforcement_loop("project", project_results, baseline, iterations=3)
        project_results["ai_feedback"] = {"best_json": best_json, "best_time": best_time}

    return project_results

# CLI
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python analyze_project.py file1.cpp [file2.cpp ...] [--ai]")
        sys.exit(1)

    args = sys.argv[1:]
    use_ai = "--ai" in args
    filepaths = [a for a in args if a.endswith(".cpp")]

    results = analyze_cpp_project(filepaths, with_ai=use_ai, clang_args = None)

    if use_ai and "ai_feedback" in results:
        final_json = results["ai_feedback"]["best_json"]
        safe_feedback = json.loads(json.dumps(results["ai_feedback"]))
        print(json.dumps(safe_feedback, indent=2, ensure_ascii=False))
        cpp_file = json_to_cpp(final_json, filename="project_combined.cpp")
        print(f"Generated best optimized C++ file: {cpp_file}")
    else:
        print(json.dumps(results, indent=2))
