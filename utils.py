import os
import subprocess
import time

def compile_and_run_project(filepaths, run_args=None, clang_args=None):
    """Compile and run C++ project, returning execution time."""
    cpp_files = [fp for fp in filepaths if fp.endswith(".cpp") or fp.endswith(".cc")]
    if not cpp_files:
        return None

    exe_path = "a.out"
    
    # Build compile command with custom clang args if provided
    compile_cmd = ["clang++", "-std=c++17"]
    if clang_args:
        compile_cmd.extend(clang_args)
    compile_cmd.extend(cpp_files)
    compile_cmd.extend(["-o", exe_path])
    
    try:
        result = subprocess.run(
            compile_cmd,
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"❌ Compilation failed:\n{result.stderr}")
            return None
        
        # Try to run the program
        start = time.time()
        cmd = [f"./{exe_path}"] + (run_args or [])
        result = subprocess.run(
            cmd, 
            capture_output=True,
            text=True,
            timeout=10  # 10 second timeout - adjust if your program needs more time
        )
        
        if result.returncode != 0:
            print(f"⚠️ Program exited with code {result.returncode}")
            print(f"Output: {result.stdout}")
            print(f"Errors: {result.stderr}")
            return None
            
        return time.time() - start
        
    except subprocess.TimeoutExpired:
        print(f"⚠️ Program timed out after 10 seconds")
        print(f"💡 Tip: Your program might be waiting for input or running too long")
        return None
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Execution failed: {e}")
        return None
    finally:
        # Clean up executable
        if os.path.exists(exe_path):
            os.remove(exe_path)


def json_to_cpp(data: dict, filename: str = "optimized.cpp"):
    """Convert JSON structure back to C++ code with proper include handling."""
    parts = []
    
    # Handle headers with proper include syntax
    for header in data.get("headers", []):
        header = header.strip()
        
        # If header already has include syntax, use it as-is
        if header.startswith("#include"):
            parts.append(header)
        # System headers (no extension or common system headers)
        elif not ("." in header) or header in ["iostream", "vector", "string", "map", 
                                                "set", "algorithm", "memory", "cmath",
                                                "cstring", "cstdlib", "cstdio", "queue",
                                                "unordered_map", "limits", "sstream"]:
            parts.append(f"#include <{header}>")
        # Local headers (has extension like .h, .hpp)
        else:
            parts.append(f'#include "{header}"')
    
    if parts:  # Add newline after headers if any exist
        parts.append("")
    
    # Add using namespace std (critical for most C++ code)
    parts.append("using namespace std;")
    parts.append("")
    
    # Add global variables
    for global_var in data.get("globals", []):
        # Don't add semicolon if it already has one
        if global_var.endswith(';'):
            parts.append(global_var)
        else:
            parts.append(global_var + ";")
    if data.get("globals"):
        parts.append("")
    
    # Add diagnostics as comments
    for diagnostic in data.get("diagnostics", []):
        parts.append(f"// {diagnostic}")
    if data.get("diagnostics"):
        parts.append("")
    
    # Add enums
    for enum_name, enum_def in data.get("enums", {}).items():
        if isinstance(enum_def, list):
            parts.append(f"enum {enum_name} {{ {', '.join(enum_def)} }};")
        elif isinstance(enum_def, str):
            parts.append(enum_def)
    if data.get("enums"):
        parts.append("")
    
    # Add classes
    for cls_name, cls in data.get("classes", {}).items():
        if isinstance(cls, dict) and "definition" in cls:
            parts.append(cls["definition"])
            parts.append("")
        elif isinstance(cls, str):
            # If AI returned class as string directly
            parts.append(cls)
            parts.append("")
    
    # Add functions (main last)
    functions = data.get("functions", {})
    for name, func in functions.items():
        if name != "main":
            parts.append(func)
            parts.append("")
    
    # Add main function last if it exists
    if "main" in functions:
        parts.append(functions["main"])
        parts.append("")
    
    code = "\n".join(parts).strip() + "\n"
    
    with open(filename, "w") as f:
        f.write(code)
    
    return filename