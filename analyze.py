import sys
import json
from clang import cindex
from feedback import get_ai_feedback  # Import from feedback.py
from clang.cindex import TranslationUnit

# Point Python to libclang
cindex.Config.set_library_file("/opt/homebrew/opt/llvm/lib/libclang.dylib")

headers = set()
functions = {}
diagnostics = []
classes = {}
enums = {}

def analyze_cpp_file(filepath, with_ai=False):
    global headers, functions, diagnostics, classes, enums
    headers, functions, diagnostics, classes, enums = set(), {}, [], {}, {}

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

    # Diagnostics
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

    # Optionally add AI feedback
    if with_ai and functions:
        results["ai_feedback"] = {
            filepath: get_ai_feedback(results)
        }

    return results


def recursiveSearch(node, filepath, current_class=None):
    for child in node.get_children():
        # Header includes
        if child.kind == cindex.CursorKind.INCLUSION_DIRECTIVE and child.location.file and child.location.file.name==filepath:
            headers.add(child.spelling)

        # Free functions (outside of classes)
        elif child.kind == cindex.CursorKind.FUNCTION_DECL and current_class is None:
            if child.location.file and child.location.file.name == filepath:
                with open(child.location.file.name) as f:
                    lines = f.readlines()
                    code = "".join(
                        lines[child.extent.start.line - 1 : child.extent.end.line]
                    )
                    functions[child.spelling] = code.strip()

        # Class / struct / class template
        elif child.kind in (
            cindex.CursorKind.CLASS_DECL,
            cindex.CursorKind.STRUCT_DECL,
            cindex.CursorKind.CLASS_TEMPLATE,
        ):
            if child.location.file and child.location.file.name == filepath:
                name = child.spelling if child.spelling else "<anonymous>"
                with open(child.location.file.name) as f:
                    lines = f.readlines()
                    code = "".join(
                        lines[child.extent.start.line - 1 : child.extent.end.line]
                    )

                # Initialize structure for this class
                classes[name] = {"definition": code.strip(), "methods": {}}

                # Recurse with class context
                recursiveSearch(child, filepath, current_class=name)
                continue  # already handled recursion

        # Methods inside a class
        elif child.kind in (
            cindex.CursorKind.CXX_METHOD,
            cindex.CursorKind.CONSTRUCTOR,
            cindex.CursorKind.DESTRUCTOR,
            cindex.CursorKind.FUNCTION_TEMPLATE,
        ):
            if (
                current_class
                and child.location.file
                and child.location.file.name == filepath
            ):
                with open(child.location.file.name) as f:
                    lines = f.readlines()
                    code = "".join(
                        lines[child.extent.start.line - 1 : child.extent.end.line]
                    )
                    classes[current_class]["methods"][child.spelling] = code.strip()

        # Enums
        elif child.kind == cindex.CursorKind.ENUM_DECL:
            if child.location.file and child.location.file.name == filepath:
                name = child.spelling if child.spelling else "<anonymous_enum>"
                with open(child.location.file.name) as f:
                    lines = f.readlines()
                    code = "".join(
                        lines[child.extent.start.line - 1 : child.extent.end.line]
                    )
                    enums[name] = code.strip()

        # Recurse normally
        recursiveSearch(child, filepath, current_class)

def json_to_cpp(data: dict, filename: str = "optimized.cpp"):
    parts = []

    # 0. Diagnostics as comments
    diagnostics = data.get("diagnostics", [])
    if diagnostics:
        parts.append("// === Diagnostics ===")
        for diagnostic in diagnostics:
            parts.append(f"// {diagnostic}")
        parts.append("")  # spacing after diagnostics

    # 1. Headers
    for header in data.get("headers", []):
        parts.append(f"#include <{header}>")

    parts.append("")  # spacing

    # 2. Classes
    for _, cls in data.get("classes", {}).items():
        definition = cls.get("definition")
        if definition:
            parts.append(definition)
            parts.append("")

    # 3. Functions (excluding main)
    functions = data.get("functions", {})
    for name, func in functions.items():
        if name != "main" and func:
            parts.append(func)
            parts.append("")

    # 4. Main
    main_func = functions.get("main") or data.get("main")
    if main_func:
        parts.append(main_func)
        parts.append("")

    # Join and write
    code = "\n".join(parts).strip() + "\n"
    with open(filename, "w") as f:
        f.write(code)

    return filename




if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python analyze.py file.cpp [--ai]")
        sys.exit(1)

    filepath = sys.argv[1]
    use_ai = "--ai" in sys.argv

    results = analyze_cpp_file(filepath, with_ai=use_ai)

    if use_ai:
        if "ai_feedback" in results:
            print(json.dumps(results["ai_feedback"], indent=2))
            cpp_file = json_to_cpp(results["ai_feedback"]["test.cpp"])
            print(f"Generated C++ file: {cpp_file}")
        else:
            print("No functions found for AI feedback.")
    else:
        print(json.dumps(results, indent=2))
