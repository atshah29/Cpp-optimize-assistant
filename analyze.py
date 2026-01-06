import sys
import os
import json
from clang import cindex
from clang.cindex import TranslationUnit
from feedback import reinforcement_loop
from utils import compile_and_run_project, json_to_cpp

# Point Python to libclang
cindex.Config.set_library_file("/opt/homebrew/opt/llvm/lib/libclang.dylib")


def analyze_cpp_file(filepath, clang_args=None):
    """Analyze a single C++ file and extract structure."""
    headers, functions, diagnostics, classes, enums, globals = set(), {}, [], {}, {}, []

    index = cindex.Index.create()
    tu = index.parse(
        filepath,
        args=clang_args if clang_args else [
            "-std=c++17",
            "-I/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/include/c++/v1",
            "-I/Library/Developer/CommandLineTools/usr/include/c++/v1",
            "-isysroot", "/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk"
        ],
        options=TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD
    )

    recursiveSearch(tu.cursor, filepath, headers, functions, classes, enums, globals)

    # Collect diagnostics
    severity_map = {0: "Ignored", 1: "Note", 2: "Warning", 3: "Error", 4: "Fatal"}
    for element in tu.diagnostics:
        if element.location.file and element.location.file.name != filepath:
            continue
        diagnostics.append(
            f"{severity_map[element.severity]}: {element.spelling} at {element.location}"
        )

    return {
        "headers": headers,
        "functions": functions,
        "diagnostics": diagnostics,
        "classes": classes,
        "enums": enums,
        "globals": globals
    }


def recursiveSearch(node, filepath, headers, functions, classes, enums, globals, current_class=None, depth=0):
    """Recursively search AST for code structures."""
    for child in node.get_children():
        # Header includes
        if child.kind == cindex.CursorKind.INCLUSION_DIRECTIVE:
            if child.location.file and child.location.file.name == filepath:
                headers.add(child.spelling)

        # Global variables (only at file scope - check semantic parent is translation unit)
        elif child.kind == cindex.CursorKind.VAR_DECL and current_class is None:
            if child.location.file and child.location.file.name == filepath:
                # Check if semantic parent is translation unit (true global)
                if child.semantic_parent.kind == cindex.CursorKind.TRANSLATION_UNIT:
                    with open(child.location.file.name) as f:
                        lines = f.readlines()
                        code = "".join(lines[child.extent.start.line - 1: child.extent.end.line])
                        globals.append(code.strip())

        # Free functions
        elif child.kind == cindex.CursorKind.FUNCTION_DECL and current_class is None:
            if child.location.file and child.location.file.name == filepath:
                with open(child.location.file.name) as f:
                    lines = f.readlines()
                    code = "".join(lines[child.extent.start.line - 1: child.extent.end.line])
                    functions[child.spelling] = code.strip()

        # Classes
        elif child.kind in (
            cindex.CursorKind.CLASS_DECL,
            cindex.CursorKind.STRUCT_DECL,
            cindex.CursorKind.CLASS_TEMPLATE
        ):
            if child.location.file and child.location.file.name == filepath:
                name = child.spelling if child.spelling else "<anonymous>"
                with open(child.location.file.name) as f:
                    lines = f.readlines()
                    code = "".join(lines[child.extent.start.line - 1: child.extent.end.line])
                classes[name] = {"definition": code.strip(), "methods": {}}
                recursiveSearch(child, filepath, headers, functions, classes, enums, globals, current_class=name, depth=depth+1)
                continue

        # Methods
        elif child.kind in (
            cindex.CursorKind.CXX_METHOD,
            cindex.CursorKind.CONSTRUCTOR,
            cindex.CursorKind.DESTRUCTOR,
            cindex.CursorKind.FUNCTION_TEMPLATE
        ):
            if current_class and child.location.file and child.location.file.name == filepath:
                with open(child.location.file.name) as f:
                    lines = f.readlines()
                    code = "".join(lines[child.extent.start.line - 1: child.extent.end.line])
                    classes[current_class]["methods"][child.spelling] = code.strip()

        # Enums
        elif child.kind == cindex.CursorKind.ENUM_DECL:
            if child.location.file and child.location.file.name == filepath:
                name = child.spelling if child.spelling else "<anonymous_enum>"
                with open(child.location.file.name) as f:
                    lines = f.readlines()
                    code = "".join(lines[child.extent.start.line - 1: child.extent.end.line])
                    enums[name] = code.strip()

        # Don't recurse into function bodies to avoid capturing local variables
        if child.kind != cindex.CursorKind.FUNCTION_DECL:
            recursiveSearch(child, filepath, headers, functions, classes, enums, globals, current_class, depth+1)


def get_program_output(json_data, filepaths, run_args=None, clang_args=None, timeout=10):
    """Get program output for correctness checking."""
    import subprocess
    import tempfile
    
    cpp_file = json_to_cpp(json_data, filename=tempfile.mktemp(suffix=".cpp"))
    exe_path = tempfile.mktemp(suffix=".out")
    
    try:
        # Compile
        compile_cmd = ["clang++", "-std=c++17"]
        if clang_args:
            compile_cmd.extend(clang_args)
        compile_cmd.extend([cpp_file, "-o", exe_path])
        
        result = subprocess.run(compile_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            return None
        
        # Run and get output
        cmd = [exe_path] + (run_args or [])
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        
        return result.stdout if result.returncode == 0 else None
        
    except Exception:
        return None
    finally:
        if os.path.exists(cpp_file):
            os.remove(cpp_file)
        if os.path.exists(exe_path):
            os.remove(exe_path)


def analyze_cpp_project(filepaths, with_ai=False, clang_args=None, run_args=None, timeout=10, num_runs=10):
    """Analyze entire C++ project and optionally optimize with AI."""
    project_results = {
        "headers": set(),
        "functions": {},
        "classes": {},
        "enums": {},
        "globals": [],
        "diagnostics": [],
    }

    # Analyze each file
    for fp in filepaths:
        if not (fp.endswith(".cpp") or fp.endswith(".cc")):
            continue  # skip headers
        
        print(f"📄 Analyzing: {fp}")
        results = analyze_cpp_file(fp, clang_args)
        
        project_results["headers"].update(results["headers"])
        project_results["functions"].update(results["functions"])
        project_results["classes"].update(results["classes"])
        project_results["enums"].update(results["enums"])
        project_results["globals"].extend(results["globals"])
        project_results["diagnostics"].extend(results["diagnostics"])

    # Convert headers set to sorted list for JSON serialization
    project_results["headers"] = sorted(project_results["headers"])

    # Compile and benchmark baseline
    print("\n🔨 Compiling baseline...")
    baseline = compile_and_run_project(filepaths, run_args=run_args, clang_args=clang_args, 
                                    timeout=timeout, num_runs=num_runs)
    
    if baseline is not None:
        print(f"⏱️  Baseline runtime: {baseline:.6f}s")
        
        # Get baseline output for correctness checking
        baseline_output = get_program_output(project_results, filepaths, run_args, clang_args, timeout)
    else:
        print("⚠️  Baseline compilation failed or no runtime available (compile-only mode)")
        baseline_output = None

    # Run AI optimization if requested
    if with_ai and (project_results["functions"] or project_results["classes"]):
        print("\n🤖 Starting AI optimization loop...")
        best_json, best_time = reinforcement_loop(
            "project",
            project_results,
            baseline,
            iterations=5,
            clang_args=clang_args,
            run_args=run_args,
            timeout=timeout,
            baseline_output=baseline_output,
            num_runs=num_runs  # ✅ Add this!
        )
        project_results["ai_feedback"] = {
            "best_json": best_json,
            "best_time": best_time,
            "baseline_time": baseline
        }
    elif with_ai:
        print("⚠️ No functions or classes found to optimize")

    return project_results


# CLI
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python analyze_project.py file1.cpp [file2.cpp ...] [--ai] [--timeout SECONDS]")
        print("\nOptions:")
        print("  --ai              Enable AI optimization")
        print("  --timeout N       Set execution timeout in seconds (default: 10)")
        sys.exit(1)

    args = sys.argv[1:]
    use_ai = "--ai" in args
    
    # Parse timeout
    timeout = 10
    if "--timeout" in args:
        idx = args.index("--timeout")
        if idx + 1 < len(args):
            try:
                timeout = int(args[idx + 1])
            except ValueError:
                print("❌ Invalid timeout value")
                sys.exit(1)
    
    filepaths = [a for a in args if a.endswith(".cpp") or a.endswith(".cc")]

    if not filepaths:
        print("❌ No C++ files provided")
        sys.exit(1)

    print(f"🚀 Analyzing {len(filepaths)} file(s)...")
    results = analyze_cpp_project(filepaths, with_ai=use_ai, clang_args=None, timeout=timeout)

    if use_ai and "ai_feedback" in results:
        final_json = results["ai_feedback"]["best_json"]
        
        # Generate optimized file
        cpp_file = json_to_cpp(final_json, filename="project_combined.cpp")
        print(f"\n✅ Generated optimized file: {cpp_file}")
        
        # Output feedback
        baseline = results["ai_feedback"]["baseline_time"]
        best = results["ai_feedback"]["best_time"]
        improvement = ((baseline - best) / baseline * 100) if baseline and best else 0
        
        safe_feedback = {
            "baseline_time": baseline,
            "best_time": best,
            "improvement_pct": f"{improvement:+.2f}%",
            "headers": final_json.get("headers", []),
            "diagnostics": final_json.get("diagnostics", [])
        }
        print(json.dumps(safe_feedback, indent=2))
    else:
        print(json.dumps({
            "headers": results["headers"],
            "num_functions": len(results["functions"]),
            "num_classes": len(results["classes"]),
            "num_enums": len(results["enums"]),
            "diagnostics": results["diagnostics"]
        }, indent=2))