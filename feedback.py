from groq import Groq
import os, json
from dotenv import load_dotenv
from utils import json_to_cpp, compile_and_run_project

load_dotenv()
api_key = os.getenv("GROQ_API_KEY")
client = Groq(api_key=api_key)

def reinforcement_loop(label, original_json, baseline_time, iterations=3, clang_args=None, run_args=None):
    print(f"Baseline runtime: {baseline_time:.6f}s")
    
    best_json = original_json.copy()
    best_time = baseline_time if baseline_time else float('inf')

    for i in range(iterations):
        print(f"\n--- Iteration {i+1} ---")

        # 1. System Prompt ( Allowed structural changes and required scope resolution)
        system_msg = (
            "You are a C++ Performance Expert.\n"
            "Goal: Optimize the C++ code to reduce execution time. Architectural refactors (like AoS to SoA) are highly encouraged.\n"
            "Format: Return a JSON object with 'functions' and/or 'classes' keys containing ONLY the items you modified.\n"
            "Ensure class methods maintain their scope resolution (e.g., ClassName::MethodName) if moved outside the class definition.\n"
            "Do NOT return the full file."
        )

        # 2. User Prompt (FIXED: Encouraged memory layout optimization)
        user_msg = (
            f"Current Runtime: {best_time:.6f}s\n"
            "Identify bottlenecks (loops, memory layout, AoS vs SoA) and optimize them.\n"
            "Use -O3 friendly code (std::move, references, SIMD-friendly layouts).\n\n"
            f"Code State:\n{json.dumps(best_json)}"
        )

        try:
            response = client.chat.completions.create(
                model="openai/gpt-oss-120b",
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_msg}
                ],
                temperature=0.2, # Low temp = more valid JSON
                response_format={"type": "json_object"}
            )
            
            # 3. Merge Strategy (Now handles both functions and classes)
            changes = json.loads(response.choices[0].message.content.strip())
            candidate_json = best_json.copy()
            
            # Merge Functions
            if "functions" in changes:
                print(f"    AI optimized {len(changes['functions'])} functions")
                for name, code in changes["functions"].items():
                    candidate_json["functions"][name] = code
            
            # Merge Classes
            if "classes" in changes:
                print(f"    AI optimized {len(changes['classes'])} classes")
                if "classes" not in candidate_json:
                    candidate_json["classes"] = {}
                    
                for class_name, class_data in changes["classes"].items():
                    if class_name in candidate_json["classes"]:
                        # Overwrite the main class definition (strips out old inline methods)
                        if "definition" in class_data:
                            candidate_json["classes"][class_name]["definition"] = class_data["definition"]
                        # Overwrite specific methods if provided
                        if "methods" in class_data:
                            for method_name, method_code in class_data["methods"].items():
                                candidate_json["classes"][class_name]["methods"][method_name] = method_code
                    else:
                        # If the AI generated a completely new class structure
                        candidate_json["classes"][class_name] = class_data
            
            # Merge new headers if needed
            if "headers" in changes:
                old_h = set(candidate_json.get("headers", []))
                new_h = set(changes["headers"])
                candidate_json["headers"] = list(old_h.union(new_h))

        except Exception as e:
            print(f"❌ JSON Error: {e}")
            continue

        # 4. Test
        cpp_file = json_to_cpp(candidate_json, f"iter_{i+1}.cpp")
        runtime = compile_and_run_project([cpp_file], run_args=run_args, clang_args=clang_args)
        
        if runtime is not None and runtime < best_time:
            print(f" Improvement! {best_time:.6f}s -> {runtime:.6f}s")
            best_time = runtime
            best_json = candidate_json
        else:
            print(f"⚠️ No improvement ({runtime}s)")
            if os.path.exists(cpp_file): os.remove(cpp_file)

    return best_json, best_time