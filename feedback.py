from groq import Groq
import os
import json
import uuid
import tempfile
from dotenv import load_dotenv
from utils import json_to_cpp, compile_and_run_project

# Load .env file variables into environment
load_dotenv()
api_key = os.getenv("GROQ_API_KEY")

if not api_key:
    raise ValueError("❌ Missing GROQ_API_KEY. Make sure it's set in your .env or shell environment.")

client = Groq(api_key=api_key)


def validate_json_structure(data):
    """Validate that AI returned proper JSON structure."""
    required = {"headers", "functions", "classes", "enums", "diagnostics", "globals"}
    if not all(k in data for k in required):
        raise ValueError(f"Missing required fields: {required - set(data.keys())}")
    
    # Type checks
    if not isinstance(data["headers"], list):
        raise TypeError("headers must be a list")
    if not isinstance(data["functions"], dict):
        raise TypeError("functions must be a dict")
    if not isinstance(data["classes"], dict):
        raise TypeError("classes must be a dict")
    if not isinstance(data["enums"], dict):
        raise TypeError("enums must be a dict")
    if not isinstance(data["diagnostics"], list):
        raise TypeError("diagnostics must be a list")
    if not isinstance(data["globals"], list):
        raise TypeError("globals must be a list")
    
    return True


def get_program_output(json_data, run_args=None, clang_args=None, timeout=10):
    """Get program output for correctness verification."""
    import subprocess
    
    work_id = uuid.uuid4().hex[:8]
    cpp_file = json_to_cpp(json_data, filename=f"/tmp/verify_{work_id}.cpp")
    exe_path = f"/tmp/verify_{work_id}.out"
    
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


def detect_duplicate_declarations(code_dict):
    """Detect obvious duplicate declarations in globals."""
    globals_list = code_dict.get("globals", [])
    seen = set()
    duplicates = []
    
    for g in globals_list:
        # Normalize by removing whitespace
        normalized = " ".join(g.split())
        if normalized in seen:
            duplicates.append(g)
        seen.add(normalized)
    
    return duplicates


def reinforcement_loop(label, original_json, baseline_time, iterations=3, 
                      clang_args=None, run_args=None, timeout=10, baseline_output=None, num_runs=10):
    """Iteratively optimize code via Groq with runtime feedback loop."""
    
    # Determine if we're using runtime optimization or compile-only mode
    use_runtime = baseline_time is not None
    
    if not use_runtime:
        print("⚠️ No baseline runtime (compile-only mode).")
        print("   Optimizing for code quality, not execution speed.\n")
    else:
        print(f"✅ Baseline runtime: {baseline_time:.6f}s\n")

    best_json = original_json
    best_time = baseline_time if baseline_time else float('inf')
    failures = 0
    
    for i in range(iterations):
        print(f"\n{'='*60}")
        print(f"🔄 Iteration {i+1}/{iterations}")
        print(f"{'='*60}")

        # Build intelligent feedback
        if use_runtime:
            improvement = ((baseline_time - best_time) / baseline_time * 100) if best_time != float('inf') else 0
            feedback = f"""Current best runtime: {best_time:.6f}s ({improvement:+.1f}% vs baseline of {baseline_time:.6f}s).
Compilation failures so far: {failures}/{i}.

Focus on:
1. Reducing redundant operations in hot loops
2. Improving memory access patterns (cache locality)
3. Removing unnecessary copies or allocations
4. Using const references where appropriate
5. Inlining small frequently-called functions
6. Avoiding repeated lookups (cache values in locals)

CRITICAL: Do not duplicate variable declarations or add broken code."""
        else:
            feedback = """Compile-only mode (no runtime measurement).

Focus on code quality improvements:
1. Remove redundant code
2. Improve const-correctness
3. Better variable naming if unclear
4. Add helpful comments for complex logic
5. Ensure proper memory management
6. Use modern C++ best practices (C++17)

CRITICAL: Preserve all functionality. Do not duplicate declarations."""

        # Groq API call with lower temperature for code
        try:
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",  
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an expert C++ performance optimization assistant. "
                            "Your goal is to improve runtime efficiency while maintaining correctness. "
                            "CRITICAL RULES:\n"
                            "1. NEVER duplicate variable declarations\n"
                            "2. NEVER remove necessary headers\n"
                            "3. NEVER change program behavior or output\n"
                            "4. Focus on algorithmic improvements, not cosmetic changes\n"
                            "5. Preserve all original headers from input\n"
                            "6. If unsure, make conservative changes"
                        )
                    },
                    {
                        "role": "system",
                        "content": (
                            "Output ONLY valid JSON with these exact fields:\n"
                            "- headers (list of strings): ALL headers from original code\n"
                            "- classes (object): class definitions\n"
                            "- functions (object): function definitions\n"
                            "- enums (object): enum definitions\n"
                            "- globals (list): global variable declarations (NO DUPLICATES)\n"
                            "- diagnostics (list of strings): performance notes and warnings\n\n"
                            "Do NOT include explanations outside the JSON. "
                            "Empty sections should be {} or []."
                        )
                    },
                    {"role": "user", "content": json.dumps(best_json, indent=2)},
                    {"role": "user", "content": feedback}
                ],
                temperature=0.4,  # Lower temperature for more conservative changes
                max_completion_tokens=8192,
                top_p=0.9,
                stream=False,
                response_format={"type": "json_object"},
                stop=None
            )
        except Exception as e:
            print(f"❌ API call failed: {e}")
            failures += 1
            continue

        # Parse and validate response
        try:
            new_json = json.loads(response.choices[0].message.content.strip())
            validate_json_structure(new_json)
            
            # Check for duplicate declarations
            dupes = detect_duplicate_declarations(new_json)
            if dupes:
                print(f"⚠️  Detected {len(dupes)} duplicate declarations! Rejecting.")
                print(f"   First duplicate: {dupes[0][:80]}...")
                failures += 1
                continue
            
            # Preserve original headers (critical for correctness)
            orig_headers = set(original_json.get("headers", []))
            new_headers = set(new_json.get("headers", []))
            if not orig_headers.issubset(new_headers):
                missing = orig_headers - new_headers
                print(f"⚠️  Warning: {len(missing)} header(s) were removed. Restoring.")
                print(f"   Missing: {', '.join(list(missing)[:3])}")
                new_json["headers"] = sorted(list(orig_headers.union(new_headers)))
                
        except json.JSONDecodeError as e:
            print(f"❌ Invalid JSON from model: {e}")
            failures += 1
            continue
        except (ValueError, TypeError) as e:
            print(f"❌ Invalid structure: {e}")
            failures += 1
            continue

        # Write and test with unique filenames to avoid collisions
        work_id = uuid.uuid4().hex[:8]
        cpp_file = json_to_cpp(new_json, f"/tmp/opt_{work_id}_iter_{i+1}.cpp")
        
        # Compile and run
        runtime = compile_and_run_project([cpp_file], run_args=run_args, clang_args=clang_args, 
                                            timeout=timeout, num_runs=num_runs)
        
        # Clean up temp file
        if os.path.exists(cpp_file):
            os.remove(cpp_file)
        
        # Check if compilation failed
        if runtime is None and use_runtime:
            print(f"❌ Compilation or execution failed")
            failures += 1
            continue
        
        # Verify correctness if we have baseline output
        if baseline_output and use_runtime:
            new_output = get_program_output(new_json, run_args, clang_args, timeout)
            if new_output != baseline_output:
                print("❌ Output changed! Program behavior was altered. Rejecting.")
                failures += 1
                continue
        
        # After getting runtime, before checking improvement:
        MIN_IMPROVEMENT = 0.05  # Require 5% improvement 

        if use_runtime:
            improvement_pct = ((best_time - runtime) / best_time * 100) if best_time else 0
            
            if runtime < best_time * (1 - MIN_IMPROVEMENT):  # At least 2% faster
                print(f"✅ IMPROVEMENT! {runtime:.6f}s < {best_time:.6f}s ({improvement_pct:.2f}% faster)")
                best_time = runtime
                best_json = new_json
            elif runtime < best_time:
                print(f"⚠️  Marginal improvement ({improvement_pct:.2f}%) below {MIN_IMPROVEMENT*100}% threshold. Rejecting as likely noise.")
            else:
                slowdown_pct = ((runtime - best_time) / best_time * 100)
                print(f"⚠️  No improvement. Runtime = {runtime:.6f}s ({slowdown_pct:+.2f}%)")

    # Final summary
    print(f"\n{'='*60}")
    print(f"📊 Optimization Summary")
    print(f"{'='*60}")
    
    if use_runtime:
        improvement = ((baseline_time - best_time) / baseline_time * 100) if baseline_time else 0
        print(f"Baseline:          {baseline_time:.6f}s")
        print(f"Best:              {best_time:.6f}s")
        print(f"Improvement:       {improvement:+.2f}%")
        print(f"Failures:          {failures}/{iterations}")
    else:
        print(f"Mode:              Compile-only")
        print(f"Failures:          {failures}/{iterations}")
    
    print(f"{'='*60}\n")
    
    return best_json, best_time