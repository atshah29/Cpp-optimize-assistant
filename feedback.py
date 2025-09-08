from groq import Groq
import os
from dotenv import load_dotenv

# Load .env file variables into environment
load_dotenv()

# Now this should work if you have GROQ_API_KEY=... in your .env
api_key = os.getenv("GROQ_API_KEY")

if not api_key:
    raise ValueError("❌ Missing GROQ_API_KEY. Make sure it's set in your .env or shell environment.")

client = Groq(api_key=api_key)

def get_ai_feedback(code_snippet: str) -> str:
    """Send a function snippet to Groq for optimization feedback."""
    response = client.chat.completions.create(
        model="openai/gpt-oss-20b",   # change if needed
        messages=[
            {"role": "system", "content": "You are a C++ performance optimization assistant. Focus on runtime efficiency, memory usage, and best practices."},
            {"role": "user", "content": f"Analyze this C++ function and suggest optimizations:\n\n{code_snippet}"}
        ]
    )
    return response.choices[0].message.content.strip()
