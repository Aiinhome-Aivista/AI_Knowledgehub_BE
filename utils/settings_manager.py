import os
import json

SETTINGS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "storage", "settings.json")

DEFAULT_SETTINGS = {
    "rss_urls": [
        "http://feeds.bbci.co.uk/news/rss.xml"
    ],
    "llm_url": "http://122.163.121.176:3041",
    "llm_model": "mistral:latest",
    "scheduler_interval_hours": 6,
    "max_articles_per_source": 3
}

def load_settings():
    """Load settings from storage/settings.json, falling back to defaults if missing or corrupted."""
    if not os.path.exists(SETTINGS_FILE):
        return DEFAULT_SETTINGS
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Ensure all default keys exist
            updated = False
            for k, v in DEFAULT_SETTINGS.items():
                if k not in data:
                    data[k] = v
                    updated = True
            if updated:
                save_settings(data)
            return data
    except Exception:
        return DEFAULT_SETTINGS

def save_settings(settings):
    """Save settings to storage/settings.json."""
    try:
        os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
        return True
    except Exception:
        return False
