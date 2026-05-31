import os
import subprocess
import time

def compile_and_run_project(filepaths, run_args=None, clang_args=None):
    """Compile and run C++ project, returning execution time."""
    # Filter for source files
    cpp_files = [fp for fp in filepaths if fp.endswith((".cpp", ".cc", ".c", ".cxx"))]
    if not cpp_files:
        return None

    exe_path = "optimized_bin"
    
    # FORCE -O3. If we don't use -O3, the AI is optimizing against a slow baseline.
    compile_cmd = ["clang++", "-O3", "-std=c++17"]
    
    if clang_args:
        # Only add flags that aren't optimization levels
        clean_args = [a for a in clang_args if not a.startswith("-O")]
        compile_cmd.extend(clean_args)
        
    compile_cmd.extend(cpp_files)
    compile_cmd.extend(["-o", exe_path])
    
    try:
        # Compile
        result = subprocess.run(compile_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Compilation failed:")
            print("\n".join(result.stderr.splitlines()[:10])) # Print first 10 lines of error
            return None
        
        # Run
        start = time.time()
        cmd = [f"./{exe_path}"] + (run_args or [])
        
        # Increase timeout to 20s to be safe
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        
        if result.returncode != 0:
            print(f"⚠️ Runtime Error (Exit {result.returncode}): {result.stderr}")
            return None
            
        return time.time() - start
        
    except Exception as e:
        print(f" Execution error: {e}")
        return None
    finally:
        if os.path.exists(exe_path):
            os.remove(exe_path)

def json_to_cpp(data: dict, filename: str = "project_combined.cpp"):
    """Convert JSON to C++ with deduplication and header fixing."""
    lines = []
    
    # Helper to extract code string
    def get_code(item):
        if isinstance(item, str): return item
        if isinstance(item, dict):
            return item.get('code', item.get('definition', list(item.values())[0]))
        return str(item)

    # 1. System Headers ONLY
    headers = data.get("headers", [])
    if isinstance(headers, dict): headers = list(headers.values())
    
    seen_headers = set()
    for h in headers:
        h_clean = get_code(h).strip()
        
        # Skip local includes (quoted)
        if '"' in h_clean:
            continue
            
        if h_clean.startswith("#"):
            include_stmt = h_clean
        elif h_clean.startswith("<"):
            include_stmt = f"#include {h_clean}"
        else:
            include_stmt = f"#include <{h_clean}>"
            
        if include_stmt not in seen_headers:
            lines.append(include_stmt)
            seen_headers.add(include_stmt)
            
    lines.append("\nusing namespace std;\n")

    # 2. Definitions (Enums, Classes)
    for category in ["enums", "classes"]:
        items = data.get(category, {})
        if isinstance(items, list):
            for item in items: lines.append(get_code(item) + ";")
        elif isinstance(items, dict):
            for name, body in items.items():
                code = get_code(body)
                if not code.strip().endswith(";"): code += ";"
                lines.append(code)

    # 3. Globals (only if not using header)
    globals_list = data.get("globals", [])
    if isinstance(globals_list, dict): globals_list = list(globals_list.values())
    
    seen_globals = set()
    for g in globals_list:
        code = get_code(g).strip()
        if not code.endswith(";"): code += ";"
        if code not in seen_globals:
            lines.append(code)
            seen_globals.add(code)

    lines.append("")
    # 4. Functions
    funcs = data.get("functions", {})
    
    # Forward declarations
    for name, body in funcs.items():
        if name != "main":
            sig = get_code(body).split("{")[0].strip()
            if "::" not in sig:
                lines.append(sig + ";")
            
    lines.append("")

    # Function Bodies
    for name, body in funcs.items():
        lines.append(get_code(body))
        lines.append("")

    with open(filename, "w") as f:
        f.write("\n".join(lines))
    
    return filename