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
            fname: get_ai_feedback(code)
            for fname, code in functions.items()
        }

    return results


def recursiveSearch(node, filepath):
    for child in node.get_children():
        if child.kind == cindex.CursorKind.INCLUSION_DIRECTIVE:
            headers.add(child.spelling)

        elif child.kind == cindex.CursorKind.FUNCTION_DECL:
            if child.location.file and child.location.file.name == filepath:
                with open(child.location.file.name) as f:
                    lines = f.readlines()
                    code = "".join(lines[child.extent.start.line - 1 : child.extent.end.line])
                    functions[child.spelling] = code.strip()

        elif child.kind == cindex.CursorKind.ENUM_DECL:
            if child.location.file and child.location.file.name == filepath:
                with open(child.location.file.name) as f:
                    lines = f.readlines()
                    code = "".join(lines[child.extent.start.line - 1 : child.extent.end.line])
                    enums[child.spelling] = code.strip()

        elif child.kind == cindex.CursorKind.CLASS_DECL:
            if child.location.file and child.location.file.name == filepath:
                with open(child.location.file.name) as f:
                    lines = f.readlines()
                    code = "".join(lines[child.extent.start.line - 1 : child.extent.end.line])
                    classes[child.spelling] = code.strip()

        recursiveSearch(child, filepath)


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
        else:
            print("No functions found for AI feedback.")
    else:
        print(json.dumps(results, indent=2))
