from groq import Groq
import os
from dotenv import load_dotenv

# Load .env file variables into environment
load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

resp = client.chat.completions.create(
    model="openai/gpt-oss-20b",
    messages=[{"role": "user", "content": "What is 2 + 2?"}]
)

print("Response:", resp.choices[0].message.content)
