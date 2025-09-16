import sys
import json
import os
from clang import cindex
from clang.cindex import TranslationUnit
from feedback import reinforcement_loop
from utils import compile_and_run, json_to_cpp

# Point Python to libclang
cindex.Config.set_library_file("/opt/homebrew/opt/llvm/lib/libclang.dylib")

# Global containers
headers = set()
functions = {}
diagnostics = []
classes = {}
enums = {}


def analyze_cpp_file(filepath, with_ai=False):
    global headers, functions, diagnostics, classes, enums
    headers, functions, diagnostics, classes, enums = set(), {}, [], {}, {}

    baseline = compile_and_run(filepath)
    print(f"Baseline runtime: {baseline:.6f}s")

    index = cindex.Index.create()
    tu = index.parse(
        filepath,
        args=[
            "-std=c++17",
            "-I/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/include/c++/v1",
            "-I/Library/Developer/CommandLineTools/usr/include/c++/v1",
            "-isysroot", "/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk"
        ],
        options=TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD
    )

    print(f"Analyzing {filepath}...\n")
    recursiveSearch(tu.cursor, filepath)

    # Collect diagnostics
    severity_map = {0: "Ignored", 1: "Note", 2: "Warning", 3: "Error", 4: "Fatal"}
    for element in tu.diagnostics:
        if element.location.file and element.location.file.name != filepath:
            continue
        diagnostics.append(f"{severity_map[element.severity]}: {element.spelling} at {element.location}")

    results = {
        "headers": sorted(headers),
        "functions": functions,
        "diagnostics": diagnostics,
        "classes": classes,
        "enums": enums
    }

    # Optionally run AI feedback loop
    if with_ai and functions:
        best_json, best_time = reinforcement_loop(filepath, results, baseline, iterations=3)
        return results, best_json, best_time

    return results, None, None


def recursiveSearch(node, filepath, current_class=None):
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

        # Classes / structs / templates
        elif child.kind in (cindex.CursorKind.CLASS_DECL, cindex.CursorKind.STRUCT_DECL, cindex.CursorKind.CLASS_TEMPLATE):
            if child.location.file and child.location.file.name == filepath:
                name = child.spelling or "<anonymous>"
                with open(child.location.file.name) as f:
                    lines = f.readlines()
                    code = "".join(lines[child.extent.start.line - 1 : child.extent.end.line])
                classes[name] = {"definition": code.strip(), "methods": {}}
                recursiveSearch(child, filepath, current_class=name)
                continue

        # Methods inside a class
        elif child.kind in (cindex.CursorKind.CXX_METHOD, cindex.CursorKind.CONSTRUCTOR, cindex.CursorKind.DESTRUCTOR, cindex.CursorKind.FUNCTION_TEMPLATE):
            if current_class and child.location.file and child.location.file.name == filepath:
                with open(child.location.file.name) as f:
                    lines = f.readlines()
                    code = "".join(lines[child.extent.start.line - 1 : child.extent.end.line])
                    classes[current_class]["methods"][child.spelling] = code.strip()

        # Enums
        elif child.kind == cindex.CursorKind.ENUM_DECL:
            if child.location.file and child.location.file.name == filepath:
                name = child.spelling or "<anonymous_enum>"
                with open(child.location.file.name) as f:
                    lines = f.readlines()
                    code = "".join(lines[child.extent.start.line - 1 : child.extent.end.line])
                    enums[name] = code.strip()

        # Recurse
        recursiveSearch(child, filepath, current_class)


# =========================
# CLI
# =========================
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python analyze.py file.cpp [--ai]")
        sys.exit(1)

    filepath = sys.argv[1]
    use_ai = "--ai" in sys.argv

    results, best_json, best_time = analyze_cpp_file(filepath, with_ai=use_ai)

    if use_ai and best_json:
        # Only print AI output JSON; avoids circular reference
        print(json.dumps(best_json, indent=2, ensure_ascii=False))
        cpp_file = json_to_cpp(best_json)
        print(f"Generated best optimized C++ file: {cpp_file}")
        print(f"Best runtime: {best_time:.6f}s")
    else:
        print(json.dumps(results, indent=2))
