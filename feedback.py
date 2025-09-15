from groq import Groq
import os
from dotenv import load_dotenv
import json

# Load .env file variables into environment
load_dotenv()

# Now this should work if you have GROQ_API_KEY=... in your .env
api_key = os.getenv("GROQ_API_KEY")

if not api_key:
    raise ValueError("❌ Missing GROQ_API_KEY. Make sure it's set in your .env or shell environment.")

client = Groq(api_key=api_key)

def get_ai_feedback(results):
    """Send a function snippet to Groq for optimization feedback."""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",  # use the supported model
        messages = [
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
                    "Output only valid JSON with the following fields: "
                    "headers (list of header names), "
                    "classes (object of class definitions and methods), "
                    "functions (object of function definitions), "
                    "diagnostics (list of warnings or notes), "
                    "enums (object of enum definitions). "
                    "If a section is empty, use {} or []. "
                    "Do not include explanations, comments, or markdown fences."
                )
            },
            {
                "role": "user",
                "content": f"Analyze this C++ code and suggest optimizations:\n\n{results}"
            }
        ],
        temperature=1,
        max_completion_tokens=8192,
        top_p=1,
        #reasoning_effort="high",
        stream=False,
        response_format={"type": "json_object"},
        stop=None
    )
    return json.loads(response.choices[0].message.content.strip())

