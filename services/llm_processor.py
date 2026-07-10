import os
import requests
import json
from dotenv import load_dotenv


load_dotenv()
url = os.getenv("MISTRAL_LOCAL_URL")
model = os.getenv("MISTRAL_LOCAL_MODEL")

def safe_text(text):
    """
    Sanitizes text before sending to Ollama by removing characters that cannot
    be encoded on Windows (e.g., curly quotes, em-dashes, emojis).
    Encodes to ASCII and back, silently dropping unencodable characters.
    """
    if not text:
        return ""
    return text.encode("ascii", errors="ignore").decode("ascii")

def call_llm_generate(prompt, format_json=False):
    """
    Calls the local LLM using the /api/generate endpoint with a prompt.
    """
    
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "keep_alive": -1 # Keep the model loaded indefinitely in memory
    }
    if format_json:
        payload["format"] = "json"
        
    try:
        response = requests.post(f"{url}/api/generate", json=payload, timeout=120)
        response.raise_for_status()
        data = response.json()
        return data.get("response", "").strip()
    except Exception as e:
        print(f"Error calling LLM generate: {e}")
        return ""

def call_llm_chat(messages):
    """
    Calls the local LLM using the /api/chat endpoint with messages history.
    """
    
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "keep_alive": -1 # Keep the model loaded indefinitely in memory
    }
    try:
        response = requests.post(f"{url}/api/chat", json=payload, timeout=120)
        response.raise_for_status()
        data = response.json()
        return data.get("message", {}).get("content", "").strip()
    except Exception as e:
        print(f"Error calling LLM chat: {e}")
        return ""
