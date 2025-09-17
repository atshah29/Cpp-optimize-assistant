from groq import Groq
import os, json
from dotenv import load_dotenv
from utils import json_to_cpp, compile_and_run_project



# Load .env file variables into environment
load_dotenv()

# Now this should work if you have GROQ_API_KEY=... in your .env
api_key = os.getenv("GROQ_API_KEY")

if not api_key:
    raise ValueError("❌ Missing GROQ_API_KEY. Make sure it's set in your .env or shell environment.")


# Load .env file variables into environment
load_dotenv()
api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    raise ValueError("❌ Missing GROQ_API_KEY. Make sure it's set in your .env or shell environment.")

client = Groq(api_key=api_key)

def reinforcement_loop(label, original_json, baseline_time, iterations=3):
    """Iteratively optimize code via Groq with runtime feedback loop."""
    print(f"Baseline runtime: {baseline_time:.6f}s")

    best_json = original_json
    best_time = baseline_time

    for i in range(iterations):
        print(f"\n--- Iteration {i+1} ---")

        # Construct runtime feedback message
        feedback = f"Last runtime: {best_time:.6f}s. "
        if best_time > baseline_time:
            feedback += "Slower than baseline. Optimize loops, memory usage, or inlining."
        else:
            feedback += "At least as fast as baseline. Try further improving performance."

        # Groq call (same params you had working)
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",  
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a C++ performance optimization assistant. "
                        "Focus on runtime efficiency, memory usage, and best practices."
                    )
                },
                {
                    "role": "system",
                    "content": (
                        "Output only valid JSON with these fields: "
                        "headers (list), classes (object), functions (object), enums (object), "
                        "diagnostics (list of strings describing warnings, runtime notes, or any suggestions). "
                        "Diagnostics should always be filled with any performance warnings or observations. "
                        "Do not include explanations or comments elsewhere. "
                        "Empty sections should be {} or []."
                    )
                },
                {"role": "user", "content": json.dumps(best_json)},
                {"role": "user", "content": feedback}
            ],
            temperature=1,
            max_completion_tokens=8192,
            top_p=1,
            stream=False,
            response_format={"type": "json_object"},
            stop=None
        )

        try:
            new_json = json.loads(response.choices[0].message.content.strip())
        except json.JSONDecodeError:
            print("❌ Invalid JSON from model.")
            continue

        # Write + test
        cpp_file = json_to_cpp(new_json, f"iter_{i+1}.cpp")
        runtime = compile_and_run_project([cpp_file])
        if os.path.exists(cpp_file):
            os.remove(cpp_file)
        if runtime is not None and runtime < best_time:
            print(f"✅ Improvement found! {runtime:.6f}s < {best_time:.6f}s")
            best_time = runtime
            best_json = new_json
        else:
            print(f"⚠️ No improvement. Runtime = {runtime}")

    print(f"\n=== Reinforcement Summary ===")
    print(f"Baseline: {baseline_time:.6f}s | Best: {best_time:.6f}s")
    return best_json, best_time


