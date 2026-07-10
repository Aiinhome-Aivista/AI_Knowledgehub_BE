import os
import requests
import json
from dotenv import load_dotenv

# We need to import our prompts from the parent directory
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from prompts import get_extraction_prompt, get_rag_system_prompt, get_graph_extraction_prompt, get_knowledge_gathering_prompt

load_dotenv()

from utils.settings_manager import load_settings

def get_llm_config():
    settings = load_settings()
    url = settings.get("llm_url", os.getenv("MISTRAL_LOCAL_URL", "http://122.163.121.176:3041"))
    model = settings.get("llm_model", os.getenv("MISTRAL_LOCAL_MODEL", "mistral:latest"))
    return url, model

def safe_text(text):
    """
    Sanitizes text before sending to Ollama by removing characters that cannot
    be encoded on Windows (e.g., curly quotes, em-dashes, emojis).
    Encodes to ASCII and back, silently dropping unencodable characters.
    """
    if not text:
        return ""
    return text.encode("ascii", errors="ignore").decode("ascii")

def extract_proper_nouns(text):
    """
    Calls the local Mistral LLM to extract proper nouns in JSON format.
    """
    url, model = get_llm_config()
    prompt = get_extraction_prompt(text)
    
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json", # Ollama supports forcing JSON format
        "keep_alive": -1 # Keep the model loaded indefinitely in memory
    }
    
    try:
        response = requests.post(f"{url}/api/generate", json=payload, timeout=120)
        response.raise_for_status()
        data = response.json()
        
        # The response from Ollama should be in data['response']
        raw_output = data.get("response", "{}")
        
        try:
            parsed_json = json.loads(raw_output)
            return parsed_json
        except json.JSONDecodeError:
            print("Failed to parse JSON from LLM output:", raw_output)
            return {"proper_nouns": []}
            
    except Exception as e:
        print(f"Error calling LLM for extraction: {e}")
        return {"proper_nouns": []}

def extract_entities_and_relationships(text):
    """
    Calls the local Mistral LLM to extract entities and their semantic relationships in JSON format.
    """
    url, model = get_llm_config()
    prompt = get_graph_extraction_prompt(text)
    
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json", # Ollama supports forcing JSON format
        "keep_alive": -1 # Keep the model loaded indefinitely in memory
    }
    
    try:
        response = requests.post(f"{url}/api/generate", json=payload, timeout=120)
        response.raise_for_status()
        data = response.json()
        
        # The response from Ollama should be in data['response']
        raw_output = data.get("response", "{}")
        
        try:
            parsed_json = json.loads(raw_output)
            # Ensure return schema has empty defaults if keys are missing
            if "entities" not in parsed_json:
                parsed_json["entities"] = []
            if "relationships" not in parsed_json:
                parsed_json["relationships"] = []
            return parsed_json
        except json.JSONDecodeError:
            print("Failed to parse JSON graph output from LLM:", raw_output)
            return {"entities": [], "relationships": []}
            
    except Exception as e:
        print(f"Error calling LLM for graph extraction: {e}")
        return {"entities": [], "relationships": []}


def generate_rag_response(query, context):
    """
    Calls the local Mistral LLM to answer a user's query based on the context.
    """
    url, model = get_llm_config()
    system_prompt = get_rag_system_prompt(context)
    
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query}
        ],
        "stream": False,
        "keep_alive": -1 # Keep the model loaded indefinitely in memory
    }
    
    try:
        response = requests.post(f"{url}/api/chat", json=payload, timeout=120)
        response.raise_for_status()
        data = response.json()
        
        # Extract the message content
        message = data.get("message", {}).get("content", "Sorry, I could not generate a response.")
        return message
            
    except Exception as e:
        print(f"Error calling LLM for RAG: {e}")
        return "I'm currently unable to process your request. Please try again later."


def gather_knowledge_for_entity(name, category, wiki_summary):
    """
    Calls the local Mistral LLM to synthesize a knowledge description for a proper noun.
    """
    url, model = get_llm_config()
    prompt = get_knowledge_gathering_prompt(name, category, wiki_summary)
    
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "keep_alive": -1
    }
    
    try:
        response = requests.post(f"{url}/api/generate", json=payload, timeout=120)
        response.raise_for_status()
        data = response.json()
        return data.get("response", "").strip()
    except Exception as e:
        print(f"Error calling LLM for knowledge gathering on {name}: {e}")
        return wiki_summary or f"Entity {name} of category {category}."

