# import json
# import re

# ALLOWED_CATEGORIES = {
#     "Person", "Organization", "Company", "Sports Team", "Government Body", 
#     "Political Party", "Country", "State", "City", "Location", "Building", 
#     "Landmark", "Product", "Brand", "Event", "Sports Event", "Movie", 
#     "TV Show", "Book", "Song", "Technology", "Software", "Programming Language", 
#     "Law", "Policy", "Award", "Currency", "Other"
# }

# STOPWORDS = {
#     "the", "a", "an", "this", "that", "it", "he", "she", "they", "we", "i", "you", 
#     "officer", "officers", "police", "news", "website", "government", "company", 
#     "people", "business", "technology", "politics", "economy", "science", "health", 
#     "year", "years", "day", "days", "month", "months", "time", "date", "president", 
#     "minister", "prime minister", "governor", "mayor", "doctor", "professor", "man", "woman",
#     "child", "officials", "spokesperson", "agency", "reporter", "channel"
# }

# def clean_json_string(raw_output):
#     """
#     Clean the raw LLM output string to extract only the JSON part.
#     Removes markdown code block markers and leading/trailing whitespace/text.
#     """
#     if not raw_output:
#         return "{}"
#     raw_output = raw_output.strip()
    
#     # Remove markdown code fences if present (e.g. ```json ... ```)
#     raw_output = re.sub(r"^```(?:json)?\s*", "", raw_output, flags=re.IGNORECASE)
#     raw_output = re.sub(r"\s*```$", "", raw_output)
    
#     # Try to find the first '{' and last '}'
#     start_idx = raw_output.find('{')
#     end_idx = raw_output.rfind('}')
#     if start_idx != -1 and end_idx != -1 and start_idx < end_idx:
#         return raw_output[start_idx:end_idx+1]
#     return raw_output

# def clean_entity_name(name):
#     """
#     Normalize and clean the entity name:
#     - Strips whitespace, quotes, and punctuation at start/end
#     - Removes common honorifics/titles (e.g., President, Dr., Prime Minister)
#     - Normalizes abbreviations (e.g., US -> United States)
#     """
#     if not name:
#         return ""
#     # Strip whitespace and common punctuation from start/end
#     name = str(name).strip().strip("'\"`.,;:!?-")
    
#     # Remove common honorifics/titles at start (case-insensitive)
#     titles_pattern = r"^(president|prime minister|pm|governor|mayor|dr|mr|mrs|ms|sir|lord|professor|chief|reporter|editor)\.?\s+"
#     name = re.sub(titles_pattern, "", name, flags=re.IGNORECASE)
    
#     # Normalize abbreviations
#     name = re.sub(r"\bU\.\s*S\.\s*A\.\b", "United States", name, flags=re.IGNORECASE)
#     name = re.sub(r"\bU\.\s*S\.\b", "United States", name, flags=re.IGNORECASE)
#     name = re.sub(r"\bU\.\s*K\.\b", "United Kingdom", name, flags=re.IGNORECASE)
    
#     if name.lower() in ["us", "usa"]:
#         return "United States"
#     if name.lower() == "uk":
#         return "United Kingdom"
        
#     return " ".join(name.split()) # clean extra internal spaces

# def is_valid_entity(name):
#     """
#     Determine if the cleaned entity name is valid:
#     - Minimum length of 2 characters
#     - Must contain at least one alphanumeric character
#     - Must not be a standalone number/year
#     - Must not be in the stop words list
#     """
#     if not name or len(name) < 2:
#         return False
        
#     # Check if only contains non-alphanumeric chars
#     if not any(c.isalnum() for c in name):
#         return False
        
#     # Exclude standalone years or numbers
#     if re.match(r"^\d+$", name):
#         return False
        
#     # Check against stopwords (case-insensitive)
#     if name.lower() in STOPWORDS:
#         return False
        
#     return True

# def post_process_proper_nouns(raw_output):
#     """
#     Parses LLM JSON, cleans entity names, filters out duplicates and stopwords,
#     and normalizes categories to match the allowed list.
#     """
#     clean_json = clean_json_string(raw_output)
#     try:
#         data = json.loads(clean_json)
#     except Exception:
#         return {"proper_nouns": []}
        
#     raw_list = data.get("proper_nouns", [])
#     if not isinstance(raw_list, list):
#         return {"proper_nouns": []}
        
#     processed_nouns = []
#     seen_names = set()
    
#     for item in raw_list:
#         if not isinstance(item, dict):
#             continue
            
#         raw_name = item.get("name")
#         raw_category = item.get("category", "Other")
        
#         # 1. Clean the name
#         cleaned_name = clean_entity_name(raw_name)
        
#         # 2. Validate name
#         if not is_valid_entity(cleaned_name):
#             continue
            
#         # 3. Normalize category
#         category = "Other"
#         for cat in ALLOWED_CATEGORIES:
#             if cat.lower() == str(raw_category).strip().lower():
#                 category = cat
#                 break
                
#         # 4. Check for duplicates (case-insensitive deduplication)
#         name_lower = cleaned_name.lower()
#         if name_lower not in seen_names:
#             seen_names.add(name_lower)
#             processed_nouns.append({
#                 "name": cleaned_name,
#                 "category": category
#             })
            
#     return {"proper_nouns": processed_nouns}


import json
import re
import unicodedata

ALLOWED_CATEGORIES = {
    "Person", "Organization", "Company", "Sports Team", "Government Body",
    "Political Party", "Country", "State", "City", "Location", "Building",
    "Landmark", "Product", "Brand", "Event", "Sports Event", "Movie",
    "TV Show", "Book", "Song", "Technology", "Software", "Programming Language",
    "Law", "Policy", "Award", "Currency", "Other"
}

CATEGORY_ALIASES = {
    "news agency": "Organization",
    "news organization": "Organization",
    "rail company": "Company",
    "political group": "Political Party",
    "character": "Person",
    "fictional character": "Person",
    "demonym": None,
    "nationality": None,
    "year": None,
    "date": None,
}

STOPWORDS = {
    "the", "a", "an", "this", "that", "it", "he", "she", "they", "we", "i", "you",
    "officer", "officers", "police", "news", "website", "government", "company",
    "people", "business", "technology", "politics", "economy", "science", "health",
    "year", "years", "day", "days", "month", "months", "time", "date", "president",
    "minister", "prime minister", "governor", "mayor", "doctor", "professor", "man", "woman",
    "child", "officials", "spokesperson", "agency", "reporter", "channel"
}

DEMONYMS = {
    "british", "american", "indian", "pakistani", "bangladeshi", "chinese",
    "french", "german", "russian", "japanese", "korean", "australian",
    "canadian", "brazilian", "mexican", "italian", "spanish", "dutch",
    "african", "european", "asian", "arab", "laotian", "english", "scottish",
    "welsh", "irish"
}

KNOWN_ENTITY_OVERRIDES = {
    "manchester united": "Sports Team",
    "man utd": "Sports Team",
    "man united": "Sports Team",
    "aston villa": "Sports Team",
    "real madrid": "Sports Team",
    "barcelona": "Sports Team",
    "chelsea": "Sports Team",
    "liverpool": "Sports Team",
    "arsenal": "Sports Team",
    "atalanta": "Sports Team",
    "psg": "Sports Team",
    "afp": "Organization",
    "bbc": "Organization",
    "the sun": "Organization",
    "reuters": "Organization",
}

GENERIC_SUFFIXES = [
    "news agency", "football club", "national team", "government",
    "administration", "authority", "department", "ministry",
]

# Legal/company suffixes to strip (longest first so "private limited" matches before "limited")
COMPANY_SUFFIXES = [
    "private limited", "pvt ltd", "pvt. ltd.", "public limited company",
    "corporation", "incorporated", "limited", "co ltd", "co. ltd.",
    "inc.", "inc", "ltd.", "ltd", "llc", "llp", "plc", "corp.", "corp",
    "gmbh", "s.a.", "sa", "co.", "co",
]

# Known short entity names that must NOT be rejected by the length check,
# grouped by the category that legitimizes them.
SHORT_NAME_WHITELIST = {
    "Programming Language": {"c", "r", "go", "d", "j"},
}

# Alias dictionary: alternate/short forms -> canonical name
ENTITY_ALIASES = {
    "man utd": "Manchester United",
    "man united": "Manchester United",
    "man city": "Manchester City",
    "spurs": "Tottenham Hotspur",
    "psg": "Paris Saint-Germain",
    "us": "United States",
    "usa": "United States",
    "uk": "United Kingdom",
    "uae": "United Arab Emirates",
}


def clean_json_string(raw_output):
    """Extract clean JSON from raw LLM text (handles code fences, stray text)."""
    if not raw_output:
        return "{}"
    raw_output = raw_output.strip()
    raw_output = re.sub(r"^```(?:json)?\s*", "", raw_output, flags=re.IGNORECASE)
    raw_output = re.sub(r"\s*```$", "", raw_output)
    start_idx = raw_output.find('{')
    end_idx = raw_output.rfind('}')
    if start_idx != -1 and end_idx != -1 and start_idx < end_idx:
        return raw_output[start_idx:end_idx + 1]
    return raw_output


def normalize_unicode(name):
    """
    Normalize unicode to NFC form so visually-identical characters
    (common with Bengali conjuncts / mixed-script text) match consistently
    during deduplication. Also strips zero-width and invisible characters.
    """
    if not name:
        return ""
    name = unicodedata.normalize("NFC", name)
    # Strip zero-width space/joiner characters that sometimes leak in from web text
    name = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", name)
    return name


def strip_company_suffix(name):
    """Remove trailing legal/company suffixes, e.g. 'Google Inc.' -> 'Google'."""
    for suffix in COMPANY_SUFFIXES:
        pattern = r"[\s,.]+" + re.escape(suffix) + r"\.?$"
        new_name = re.sub(pattern, "", name, flags=re.IGNORECASE)
        if new_name != name:
            name = new_name.strip()
            break  # only strip one suffix layer
    return name


def clean_entity_name(name):
    """Normalize entity name: unicode, punctuation, titles, suffixes, abbreviations."""
    if not name:
        return ""
    name = normalize_unicode(str(name))
    name = name.strip().strip("'\"`.,;:!?-")

    titles_pattern = r"^(president|prime minister|pm|governor|mayor|dr|mr|mrs|ms|sir|lord|professor|chief|reporter|editor)\.?\s+"
    name = re.sub(titles_pattern, "", name, flags=re.IGNORECASE)

    for suffix in GENERIC_SUFFIXES:
        pattern = r"\s+" + re.escape(suffix) + r"$"
        name = re.sub(pattern, "", name, flags=re.IGNORECASE)

    name = strip_company_suffix(name)

    name = re.sub(r"\bU\.\s*S\.\s*A\.\b", "United States", name, flags=re.IGNORECASE)
    name = re.sub(r"\bU\.\s*S\.\b", "United States", name, flags=re.IGNORECASE)
    name = re.sub(r"\bU\.\s*K\.\b", "United Kingdom", name, flags=re.IGNORECASE)

    name = " ".join(name.split())

    # Resolve alias -> canonical form
    alias_match = ENTITY_ALIASES.get(name.lower())
    if alias_match:
        return alias_match

    return name


def is_valid_entity(name, category=None):
    """
    Check name isn't empty, a number, a stopword, or a demonym.
    Short names (e.g. "C", "R") are allowed when the category legitimizes them
    (e.g. Programming Language) instead of being rejected outright.
    """
    if not name:
        return False

    if len(name) < 2:
        whitelist = SHORT_NAME_WHITELIST.get(category, set())
        if name.lower() not in whitelist:
            return False

    if not any(c.isalnum() for c in name):
        return False
    if re.match(r"^\d+$", name):
        return False
    if name.lower() in STOPWORDS:
        return False
    if name.lower() in DEMONYMS:
        return False
    return True


def normalize_category(raw_category, cleaned_name):
    """
    Resolve final category:
    1. Known-entity override wins (fixes LLM inconsistency).
    2. Exact match against allowed list.
    3. Alias mapping.
    4. Fallback to "Other".
    Returns None if the entity should be dropped entirely.
    """
    name_key = cleaned_name.lower()
    if name_key in KNOWN_ENTITY_OVERRIDES:
        return KNOWN_ENTITY_OVERRIDES[name_key]

    raw_category_clean = str(raw_category).strip().lower()

    for cat in ALLOWED_CATEGORIES:
        if cat.lower() == raw_category_clean:
            return cat

    if raw_category_clean in CATEGORY_ALIASES:
        return CATEGORY_ALIASES[raw_category_clean]

    return "Other"


def post_process_proper_nouns(raw_output):
    """
    Parse LLM JSON, clean names (unicode/suffix/alias normalized),
    filter invalid/duplicate entities, and normalize categories.
    """
    clean_json = clean_json_string(raw_output)
    try:
        data = json.loads(clean_json)
    except Exception:
        return {"proper_nouns": []}

    raw_list = data.get("proper_nouns", [])
    if not isinstance(raw_list, list):
        return {"proper_nouns": []}

    processed_nouns = []
    seen_names = set()

    for item in raw_list:
        if not isinstance(item, dict):
            continue

        raw_name = item.get("name")
        raw_category = item.get("category", "Other")

        cleaned_name = clean_entity_name(raw_name)
        category = normalize_category(raw_category, cleaned_name)

        # Validate AFTER category resolution, so Programming Language whitelist applies
        if not is_valid_entity(cleaned_name, category):
            continue

        if category is None:
            continue

        name_lower = cleaned_name.lower()
        if name_lower not in seen_names:
            seen_names.add(name_lower)
            processed_nouns.append({
                "name": cleaned_name,
                "category": category
            })

    return {"proper_nouns": processed_nouns}
