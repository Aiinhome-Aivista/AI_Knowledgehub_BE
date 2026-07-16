# # import json
# # import re

# # ALLOWED_CATEGORIES = {
# #     "Person", "Organization", "Company", "Sports Team", "Government Body", 
# #     "Political Party", "Country", "State", "City", "Location", "Building", 
# #     "Landmark", "Product", "Brand", "Event", "Sports Event", "Movie", 
# #     "TV Show", "Book", "Song", "Technology", "Software", "Programming Language", 
# #     "Law", "Policy", "Award", "Currency", "Other"
# # }

# # STOPWORDS = {
# #     "the", "a", "an", "this", "that", "it", "he", "she", "they", "we", "i", "you", 
# #     "officer", "officers", "police", "news", "website", "government", "company", 
# #     "people", "business", "technology", "politics", "economy", "science", "health", 
# #     "year", "years", "day", "days", "month", "months", "time", "date", "president", 
# #     "minister", "prime minister", "governor", "mayor", "doctor", "professor", "man", "woman",
# #     "child", "officials", "spokesperson", "agency", "reporter", "channel"
# # }

# # def clean_json_string(raw_output):
# #     """
# #     Clean the raw LLM output string to extract only the JSON part.
# #     Removes markdown code block markers and leading/trailing whitespace/text.
# #     """
# #     if not raw_output:
# #         return "{}"
# #     raw_output = raw_output.strip()
    
# #     # Remove markdown code fences if present (e.g. ```json ... ```)
# #     raw_output = re.sub(r"^```(?:json)?\s*", "", raw_output, flags=re.IGNORECASE)
# #     raw_output = re.sub(r"\s*```$", "", raw_output)
    
# #     # Try to find the first '{' and last '}'
# #     start_idx = raw_output.find('{')
# #     end_idx = raw_output.rfind('}')
# #     if start_idx != -1 and end_idx != -1 and start_idx < end_idx:
# #         return raw_output[start_idx:end_idx+1]
# #     return raw_output

# # def clean_entity_name(name):
# #     """
# #     Normalize and clean the entity name:
# #     - Strips whitespace, quotes, and punctuation at start/end
# #     - Removes common honorifics/titles (e.g., President, Dr., Prime Minister)
# #     - Normalizes abbreviations (e.g., US -> United States)
# #     """
# #     if not name:
# #         return ""
# #     # Strip whitespace and common punctuation from start/end
# #     name = str(name).strip().strip("'\"`.,;:!?-")
    
# #     # Remove common honorifics/titles at start (case-insensitive)
# #     titles_pattern = r"^(president|prime minister|pm|governor|mayor|dr|mr|mrs|ms|sir|lord|professor|chief|reporter|editor)\.?\s+"
# #     name = re.sub(titles_pattern, "", name, flags=re.IGNORECASE)
    
# #     # Normalize abbreviations
# #     name = re.sub(r"\bU\.\s*S\.\s*A\.\b", "United States", name, flags=re.IGNORECASE)
# #     name = re.sub(r"\bU\.\s*S\.\b", "United States", name, flags=re.IGNORECASE)
# #     name = re.sub(r"\bU\.\s*K\.\b", "United Kingdom", name, flags=re.IGNORECASE)
    
# #     if name.lower() in ["us", "usa"]:
# #         return "United States"
# #     if name.lower() == "uk":
# #         return "United Kingdom"
        
# #     return " ".join(name.split()) # clean extra internal spaces

# # def is_valid_entity(name):
# #     """
# #     Determine if the cleaned entity name is valid:
# #     - Minimum length of 2 characters
# #     - Must contain at least one alphanumeric character
# #     - Must not be a standalone number/year
# #     - Must not be in the stop words list
# #     """
# #     if not name or len(name) < 2:
# #         return False
        
# #     # Check if only contains non-alphanumeric chars
# #     if not any(c.isalnum() for c in name):
# #         return False
        
# #     # Exclude standalone years or numbers
# #     if re.match(r"^\d+$", name):
# #         return False
        
# #     # Check against stopwords (case-insensitive)
# #     if name.lower() in STOPWORDS:
# #         return False
        
# #     return True

# # def post_process_proper_nouns(raw_output):
# #     """
# #     Parses LLM JSON, cleans entity names, filters out duplicates and stopwords,
# #     and normalizes categories to match the allowed list.
# #     """
# #     clean_json = clean_json_string(raw_output)
# #     try:
# #         data = json.loads(clean_json)
# #     except Exception:
# #         return {"proper_nouns": []}
        
# #     raw_list = data.get("proper_nouns", [])
# #     if not isinstance(raw_list, list):
# #         return {"proper_nouns": []}
        
# #     processed_nouns = []
# #     seen_names = set()
    
# #     for item in raw_list:
# #         if not isinstance(item, dict):
# #             continue
            
# #         raw_name = item.get("name")
# #         raw_category = item.get("category", "Other")
        
# #         # 1. Clean the name
# #         cleaned_name = clean_entity_name(raw_name)
        
# #         # 2. Validate name
# #         if not is_valid_entity(cleaned_name):
# #             continue
            
# #         # 3. Normalize category
# #         category = "Other"
# #         for cat in ALLOWED_CATEGORIES:
# #             if cat.lower() == str(raw_category).strip().lower():
# #                 category = cat
# #                 break
                
# #         # 4. Check for duplicates (case-insensitive deduplication)
# #         name_lower = cleaned_name.lower()
# #         if name_lower not in seen_names:
# #             seen_names.add(name_lower)
# #             processed_nouns.append({
# #                 "name": cleaned_name,
# #                 "category": category
# #             })
            
# #     return {"proper_nouns": processed_nouns}


# import json
# import re
# import unicodedata

# ALLOWED_CATEGORIES = {
#     "Person", "Organization", "Company", "Sports Team", "Government Body",
#     "Political Party", "Country", "State", "City", "Location", "Building",
#     "Landmark", "Product", "Brand", "Event", "Sports Event", "Movie",
#     "TV Show", "Book", "Song", "Technology", "Software", "Programming Language",
#     "Law", "Policy", "Award", "Currency", "Other"
# }

# CATEGORY_ALIASES = {
#     "news agency": "Organization",
#     "news organization": "Organization",
#     "rail company": "Company",
#     "political group": "Political Party",
#     "character": "Person",
#     "fictional character": "Person",
#     "demonym": None,
#     "nationality": None,
#     "year": None,
#     "date": None,
# }

# STOPWORDS = {
#     "the", "a", "an", "this", "that", "it", "he", "she", "they", "we", "i", "you",
#     "officer", "officers", "police", "news", "website", "government", "company",
#     "people", "business", "technology", "politics", "economy", "science", "health",
#     "year", "years", "day", "days", "month", "months", "time", "date", "president",
#     "minister", "prime minister", "governor", "mayor", "doctor", "professor", "man", "woman",
#     "child", "officials", "spokesperson", "agency", "reporter", "channel"
# }

# DEMONYMS = {
#     "british", "american", "indian", "pakistani", "bangladeshi", "chinese",
#     "french", "german", "russian", "japanese", "korean", "australian",
#     "canadian", "brazilian", "mexican", "italian", "spanish", "dutch",
#     "african", "european", "asian", "arab", "laotian", "english", "scottish",
#     "welsh", "irish"
# }

# KNOWN_ENTITY_OVERRIDES = {
#     "manchester united": "Sports Team",
#     "man utd": "Sports Team",
#     "man united": "Sports Team",
#     "aston villa": "Sports Team",
#     "real madrid": "Sports Team",
#     "barcelona": "Sports Team",
#     "chelsea": "Sports Team",
#     "liverpool": "Sports Team",
#     "arsenal": "Sports Team",
#     "atalanta": "Sports Team",
#     "psg": "Sports Team",
#     "afp": "Organization",
#     "bbc": "Organization",
#     "the sun": "Organization",
#     "reuters": "Organization",
# }

# GENERIC_SUFFIXES = [
#     "news agency", "football club", "national team", "government",
#     "administration", "authority", "department", "ministry",
# ]

# # Legal/company suffixes to strip (longest first so "private limited" matches before "limited")
# COMPANY_SUFFIXES = [
#     "private limited", "pvt ltd", "pvt. ltd.", "public limited company",
#     "corporation", "incorporated", "limited", "co ltd", "co. ltd.",
#     "inc.", "inc", "ltd.", "ltd", "llc", "llp", "plc", "corp.", "corp",
#     "gmbh", "s.a.", "sa", "co.", "co",
# ]

# # Known short entity names that must NOT be rejected by the length check,
# # grouped by the category that legitimizes them.
# SHORT_NAME_WHITELIST = {
#     "Programming Language": {"c", "r", "go", "d", "j"},
# }

# # Alias dictionary: alternate/short forms -> canonical name
# ENTITY_ALIASES = {
#     "man utd": "Manchester United",
#     "man united": "Manchester United",
#     "man city": "Manchester City",
#     "spurs": "Tottenham Hotspur",
#     "psg": "Paris Saint-Germain",
#     "us": "United States",
#     "usa": "United States",
#     "uk": "United Kingdom",
#     "uae": "United Arab Emirates",
# }


# def clean_json_string(raw_output):
#     """Extract clean JSON from raw LLM text (handles code fences, stray text)."""
#     if not raw_output:
#         return "{}"
#     raw_output = raw_output.strip()
#     raw_output = re.sub(r"^```(?:json)?\s*", "", raw_output, flags=re.IGNORECASE)
#     raw_output = re.sub(r"\s*```$", "", raw_output)
#     start_idx = raw_output.find('{')
#     end_idx = raw_output.rfind('}')
#     if start_idx != -1 and end_idx != -1 and start_idx < end_idx:
#         return raw_output[start_idx:end_idx + 1]
#     return raw_output


# def normalize_unicode(name):
#     """
#     Normalize unicode to NFC form so visually-identical characters
#     (common with Bengali conjuncts / mixed-script text) match consistently
#     during deduplication. Also strips zero-width and invisible characters.
#     """
#     if not name:
#         return ""
#     name = unicodedata.normalize("NFC", name)
#     # Strip zero-width space/joiner characters that sometimes leak in from web text
#     name = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", name)
#     return name


# def strip_company_suffix(name):
#     """Remove trailing legal/company suffixes, e.g. 'Google Inc.' -> 'Google'."""
#     for suffix in COMPANY_SUFFIXES:
#         pattern = r"[\s,.]+" + re.escape(suffix) + r"\.?$"
#         new_name = re.sub(pattern, "", name, flags=re.IGNORECASE)
#         if new_name != name:
#             name = new_name.strip()
#             break  # only strip one suffix layer
#     return name


# def clean_entity_name(name):
#     """Normalize entity name: unicode, punctuation, titles, suffixes, abbreviations."""
#     if not name:
#         return ""
#     name = normalize_unicode(str(name))
#     name = name.strip().strip("'\"`.,;:!?-")

#     titles_pattern = r"^(president|prime minister|pm|governor|mayor|dr|mr|mrs|ms|sir|lord|professor|chief|reporter|editor)\.?\s+"
#     name = re.sub(titles_pattern, "", name, flags=re.IGNORECASE)

#     for suffix in GENERIC_SUFFIXES:
#         pattern = r"\s+" + re.escape(suffix) + r"$"
#         name = re.sub(pattern, "", name, flags=re.IGNORECASE)

#     name = strip_company_suffix(name)

#     name = re.sub(r"\bU\.\s*S\.\s*A\.\b", "United States", name, flags=re.IGNORECASE)
#     name = re.sub(r"\bU\.\s*S\.\b", "United States", name, flags=re.IGNORECASE)
#     name = re.sub(r"\bU\.\s*K\.\b", "United Kingdom", name, flags=re.IGNORECASE)

#     name = " ".join(name.split())

#     # Resolve alias -> canonical form
#     alias_match = ENTITY_ALIASES.get(name.lower())
#     if alias_match:
#         return alias_match

#     return name


# def is_valid_entity(name, category=None):
#     """
#     Check name isn't empty, a number, a stopword, or a demonym.
#     Short names (e.g. "C", "R") are allowed when the category legitimizes them
#     (e.g. Programming Language) instead of being rejected outright.
#     """
#     if not name:
#         return False

#     if len(name) < 2:
#         whitelist = SHORT_NAME_WHITELIST.get(category, set())
#         if name.lower() not in whitelist:
#             return False

#     if not any(c.isalnum() for c in name):
#         return False
#     if re.match(r"^\d+$", name):
#         return False
#     if name.lower() in STOPWORDS:
#         return False
#     if name.lower() in DEMONYMS:
#         return False
#     return True


# def normalize_category(raw_category, cleaned_name):
#     """
#     Resolve final category:
#     1. Known-entity override wins (fixes LLM inconsistency).
#     2. Exact match against allowed list.
#     3. Alias mapping.
#     4. Fallback to "Other".
#     Returns None if the entity should be dropped entirely.
#     """
#     name_key = cleaned_name.lower()
#     if name_key in KNOWN_ENTITY_OVERRIDES:
#         return KNOWN_ENTITY_OVERRIDES[name_key]

#     raw_category_clean = str(raw_category).strip().lower()

#     for cat in ALLOWED_CATEGORIES:
#         if cat.lower() == raw_category_clean:
#             return cat

#     if raw_category_clean in CATEGORY_ALIASES:
#         return CATEGORY_ALIASES[raw_category_clean]

#     return "Other"


# def post_process_proper_nouns(raw_output):
#     """
#     Parse LLM JSON, clean names (unicode/suffix/alias normalized),
#     filter invalid/duplicate entities, and normalize categories.
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

#         cleaned_name = clean_entity_name(raw_name)
#         category = normalize_category(raw_category, cleaned_name)

#         # Validate AFTER category resolution, so Programming Language whitelist applies
#         if not is_valid_entity(cleaned_name, category):
#             continue

#         if category is None:
#             continue

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

# ==================================================
# Allowed Categories
# ==================================================

ALLOWED_CATEGORIES = {
    "Person",
    "Organization",
    "Company",
    "Government Body",
    "Political Party",
    "Country",
    "State",
    "City",
    "Location",
    "Building",
    "Landmark",
    "Product",
    "Brand",
    "Event",
    "Sports Event",
    "Sports Team",
    "Movie",
    "TV Show",
    "Book",
    "Song",
    "Technology",
    "Software",
    "Programming Language",
    "Law",
    "Policy",
    "Award",
    "Currency",
    "Other"
}

# ==================================================
# Category Aliases
# ==================================================

CATEGORY_ALIASES = {

    "character": "Person",
    "fictional character": "Person",

    "news agency": "Organization",
    "media organization": "Organization",
    "media": "Organization",

    "government agency": "Government Body",
    "agency": "Government Body",
    "military": "Government Body",

    "political group": "Political Party",

    "rail company": "Company",

    "date": None,
    "year": None,
    "nationality": None,
    "demonym": None,
}

# ==================================================
# Known Entity Overrides
# ==================================================

KNOWN_ENTITY_OVERRIDES = {

    # Sports Teams

    "manchester united": "Sports Team",
    "chelsea": "Sports Team",
    "arsenal": "Sports Team",
    "liverpool": "Sports Team",
    "barcelona": "Sports Team",
    "real madrid": "Sports Team",
    "aston villa": "Sports Team",
    "atalanta": "Sports Team",
    "tottenham hotspur": "Sports Team",
    "paris saint-germain": "Sports Team",

    # Organizations

    "bbc": "Organization",
    "cnn": "Organization",
    "afp": "Organization",
    "reuters": "Organization",
    "associated press": "Organization",

    # Companies

    "google": "Company",
    "apple": "Company",
    "amazon": "Company",
    "microsoft": "Company",
    "meta": "Company",
    "tesla": "Company",
    "samsung": "Company"
}

# ==================================================
# Entity Aliases
# ==================================================

ENTITY_ALIASES = {

    "us": "United States",
    "usa": "United States",
    "u.s.": "United States",

    "uk": "United Kingdom",
    "u.k.": "United Kingdom",

    "uae": "United Arab Emirates",

    "man utd": "Manchester United",
    "man united": "Manchester United",

    "psg": "Paris Saint-Germain",

    "spurs": "Tottenham Hotspur",

}

# ==================================================
# Company Suffixes
# ==================================================

COMPANY_SUFFIXES = [

    "private limited",
    "public limited company",

    "pvt ltd",
    "pvt. ltd.",

    "limited",

    "incorporated",

    "corporation",

    "inc.",
    "inc",

    "ltd.",
    "ltd",

    "corp.",
    "corp",

    "llc",
    "llp",
    "plc",

    "co ltd",
    "co. ltd.",

    "co",
    "co.",

    "gmbh",
    "sa"
]

# ==================================================
# Generic Suffixes
# ==================================================

GENERIC_SUFFIXES = [

    "news agency",

    "football club",

    "national team",

    "government",

    "authority",

    "department",

    "administration",

    "ministry"

]

# ==================================================
# Stopwords
# ==================================================

STOPWORDS = {

    "the","a","an",

    "this","that",

    "he","she","they",

    "we","you","i",

    "it",

    "people",

    "government",

    "technology",

    "software",

    "business",

    "company",

    "organization",

    "market",

    "website",

    "internet",

    "article",

    "report",

    "story",

    "official",

    "officials",

    "minister",

    "president",

    "governor",

    "mayor"

}

# ==================================================
# Generic Words
# ==================================================

GENERIC_WORDS = {

    "technology",

    "government",

    "software",

    "internet",

    "website",

    "business",

    "market",

    "budget",

    "economy",

    "science",

    "health",

    "community",

    "family",

    "mother",

    "father",

    "employee",

    "people"

}

# ==================================================
# Generic Phrases
# ==================================================

GENERIC_PHRASES = {

    "art",
    "athena",
    "ba plane",
    "bill complaints",
    "britain's weather",
    "earth's climate system",
    "news app",
    "buy now pay later",
    "weather",
    "climate system",
    "plane",
    "football team",
    "national team",
    "government officials",
    "official statement",
    "social media",
    "online platform"

}

# ==================================================
# Ambiguous First Names
# ==================================================

AMBIGUOUS_FIRST_NAMES = {

    "art",
    "patrick",
    "tashi",
    "john",
    "david",
    "michael",
    "alex",
    "james",
    "tom",
    "sam",
    "dan",
    "kim",
    "lee",
    "anna",
    "mark"

}

# ==================================================
# Demonyms
# ==================================================

DEMONYMS = {

    "american",

    "british",

    "indian",

    "pakistani",

    "bangladeshi",

    "french",

    "german",

    "italian",

    "spanish",

    "chinese",

    "japanese",

    "korean",

    "russian",

    "canadian",

    "australian"

}

# ==================================================
# Diseases
# ==================================================

DISEASES = {

    "cancer",

    "covid",

    "covid-19",

    "influenza",

    "diabetes",

    "adhd",

    "malaria",

    "stroke",

    "heart disease",

    "tuberculosis",

    "dengue"

}

# ==================================================
# Months
# ==================================================

MONTHS = {

    "january","february","march","april",

    "may","june","july","august",

    "september","october","november","december",

    "jan","feb","mar","apr","jun","jul",

    "aug","sep","sept","oct","nov","dec"

}

# ==================================================
# Weekdays
# ==================================================

WEEKDAYS = {

    "monday",

    "tuesday",

    "wednesday",

    "thursday",

    "friday",

    "saturday",

    "sunday"

}

# ==================================================
# Short Name Whitelist
# ==================================================

SHORT_NAME_WHITELIST = {

    "Programming Language": {

        "C",

        "R",

        "Go",

        "D",

        "J"

    }

}

# ==================================================
# Regex
# ==================================================

YEAR_PATTERN = re.compile(r"^(18|19|20|21)\d{2}$")

NUMBER_PATTERN = re.compile(r"^\d+([.,]\d+)?$")

DATE_PATTERN = re.compile(r"^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}$")

PERCENT_PATTERN = re.compile(r"^\d+(\.\d+)?%$")

MONEY_PATTERN = re.compile(
    r"(₹|Rs\.?|INR|\$|£|€|¥)\s?\d+|\d+\s?(crore|lakh|million|billion|bn|m)",
    re.IGNORECASE
)

QUANTITY_PATTERN = re.compile(

    r"^\d+\s+(people|person|officer|officers|soldiers|children|students|families|houses)$",

    re.IGNORECASE

)

ROMAN_NUMERAL_PATTERN = re.compile(
    r"^[IVXLCDM]+$",
    re.IGNORECASE
)

EMAIL_PATTERN = re.compile(
    r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
)

URL_PATTERN = re.compile(
    r"^(http|https)://",
    re.IGNORECASE
)

PHONE_PATTERN = re.compile(
    r"^\+?\d[\d\s\-()]{7,}$"
)
# ==================================================
# Clean JSON String
# ==================================================

def clean_json_string(raw_output):
    """
    Extract valid JSON from LLM output.

    Handles:
    - Markdown code fences
    - Extra text before/after JSON
    - Empty output
    """

    if not raw_output:
        return "{}"

    raw_output = raw_output.strip()

    # Remove ```json
    raw_output = re.sub(
        r"^```(?:json)?\s*",
        "",
        raw_output,
        flags=re.IGNORECASE
    )

    # Remove ending ```
    raw_output = re.sub(
        r"\s*```$",
        "",
        raw_output
    )

    # Keep only JSON portion
    start = raw_output.find("{")
    end = raw_output.rfind("}")

    if start != -1 and end != -1 and start < end:
        return raw_output[start:end + 1]

    return raw_output


# ==================================================
# Unicode Normalization
# ==================================================

def normalize_unicode(text):
    """
    Normalize Unicode characters.

    Helps with:
    - Bengali Unicode consistency
    - Mixed Unicode forms
    - Invisible characters
    """

    if not text:
        return ""

    text = unicodedata.normalize("NFC", str(text))

    # Remove zero-width characters
    text = re.sub(
        r"[\u200b\u200c\u200d\ufeff]",
        "",
        text
    )

    return text.strip()


# ==================================================
# Strip Company Suffix
# ==================================================

def strip_company_suffix(name):
    """
    Google Inc.
        -> Google

    Apple Ltd.
        -> Apple

    ABC Pvt Ltd
        -> ABC
    """

    if not name:
        return ""

    cleaned = name.strip()

    for suffix in COMPANY_SUFFIXES:

        pattern = rf"[\s,.]+{re.escape(suffix)}\.?$"

        new_name = re.sub(
            pattern,
            "",
            cleaned,
            flags=re.IGNORECASE
        )

        if new_name != cleaned:
            cleaned = new_name.strip()
            break

    return cleaned

# ==================================================
# Clean Entity Name
# ==================================================

def clean_entity_name(name):
    """
    Clean and normalize entity names.

    Examples
    --------
    President Donald Trump
        -> Donald Trump

    Google Inc.
        -> Google

    BBC News
        -> BBC
    """

    if not name:
        return ""

    # Unicode normalization
    name = normalize_unicode(name)

    # Trim spaces
    name = name.strip()

    # Remove surrounding punctuation
    name = name.strip("'\"`.,;:!?()[]{}")

    # Remove multiple spaces
    name = re.sub(r"\s+", " ", name)

    # ---------------------------------------------
    # Remove titles
    # ---------------------------------------------

    TITLE_PATTERN = re.compile(

        r"^(president|prime minister|pm|"
        r"dr|mr|mrs|ms|miss|sir|lord|lady|"
        r"prof|professor|chief|editor|"
        r"governor|mayor|minister|"
        r"captain|capt|general|gen)\.?\s+",

        re.IGNORECASE

    )

    name = TITLE_PATTERN.sub("", name)

    # ---------------------------------------------
    # Remove generic suffixes
    # ---------------------------------------------

    for suffix in GENERIC_SUFFIXES:

        pattern = rf"\s+{re.escape(suffix)}$"

        name = re.sub(
            pattern,
            "",
            name,
            flags=re.IGNORECASE
        )

    # ---------------------------------------------
    # Remove company suffixes
    # ---------------------------------------------

    name = strip_company_suffix(name)

    # ---------------------------------------------
    # Normalize spaces
    # ---------------------------------------------

    name = " ".join(name.split())

    # ---------------------------------------------
    # Alias mapping
    # ---------------------------------------------

    alias = ENTITY_ALIASES.get(name.lower())

    if alias:
        return alias

    return name


# ==================================================
# Normalize Category
# ==================================================

def normalize_category(raw_category, entity_name):
    """
    Normalize model category.

    Example

    Character
        -> Person

    News Agency
        -> Organization

    Agency
        -> Government Body
    """

    if raw_category is None:
        return "Other"

    entity_key = entity_name.lower()

    # ---------------------------------------------
    # Known entity override
    # ---------------------------------------------

    if entity_key in KNOWN_ENTITY_OVERRIDES:
        return KNOWN_ENTITY_OVERRIDES[entity_key]

    category = str(raw_category).strip().lower()

    # ---------------------------------------------
    # Exact match
    # ---------------------------------------------

    for allowed in ALLOWED_CATEGORIES:

        if allowed.lower() == category:
            return allowed

    # ---------------------------------------------
    # Alias mapping
    # ---------------------------------------------

    if category in CATEGORY_ALIASES:

        mapped = CATEGORY_ALIASES[category]

        if mapped is None:
            return None

        return mapped

    # ---------------------------------------------
    # Default
    # ---------------------------------------------

    return "Other"

# ==================================================
# Strong Entity Validation
# ==================================================

def is_valid_entity(name, category):

    if not name:
        return False

    name = normalize_unicode(name).strip()

    if not name:
        return False

    lower = name.lower()

    # -----------------------------
    # Category Validation
    # -----------------------------

    if category not in ALLOWED_CATEGORIES:
        return False

    # -----------------------------
    # Stopwords
    # -----------------------------

    if lower in STOPWORDS:
        return False

    # -----------------------------
    # Generic words
    # -----------------------------

    if lower in GENERIC_WORDS:
        return False

    # -----------------------------
    # Nationalities
    # -----------------------------

    if lower in DEMONYMS:
        return False

    # -----------------------------
    # Diseases
    # -----------------------------

    if lower in DISEASES:
        return False

    # -----------------------------
    # Month / Weekday
    # -----------------------------

    if lower in MONTHS:
        return False

    if lower in WEEKDAYS:
        return False

    # -----------------------------
    # Year
    # -----------------------------

    if YEAR_PATTERN.fullmatch(name):
        return False

    # -----------------------------
    # Number
    # -----------------------------

    if NUMBER_PATTERN.fullmatch(name):
        return False

    # -----------------------------
    # Date
    # -----------------------------

    if DATE_PATTERN.fullmatch(name):
        return False

    # -----------------------------
    # Percentage
    # -----------------------------

    if PERCENT_PATTERN.fullmatch(name):
        return False

    # -----------------------------
    # Money
    # -----------------------------

    if MONEY_PATTERN.search(name):
        return False

    # -----------------------------
    # Quantity
    # -----------------------------

    if QUANTITY_PATTERN.fullmatch(name):
        return False

    # -----------------------------
    # Starts with number
    # -----------------------------

    if re.match(r"^\d", name):
        return False

    # -----------------------------
    # Numeric / Symbol only
    # -----------------------------

    if re.fullmatch(r"[\d\s.,:/%₹$£€¥-]+", name):
        return False

    # -----------------------------
    # Single Character Validation
    # -----------------------------

    if len(name) == 1:

        allowed = SHORT_NAME_WHITELIST.get(category, set())

        if name not in allowed:
            return False

    # -----------------------------
    # Too many digits
    # -----------------------------

    # -----------------------------
# Too many digits
# -----------------------------

    digits = sum(ch.isdigit() for ch in name)

    if digits > 3:
        return False

    # Reject generic phrases
    if lower in GENERIC_PHRASES:
        return False

    # Reject email
    if EMAIL_PATTERN.fullmatch(name):
        return False

    # Reject URL
    if URL_PATTERN.match(name):
        return False

    # Reject phone number
    if PHONE_PATTERN.fullmatch(name):
        return False

    # Reject Roman numerals
    if ROMAN_NUMERAL_PATTERN.fullmatch(name):
        return False

    # Reject ambiguous first names
    if (
        category == "Person"
        and lower in AMBIGUOUS_FIRST_NAMES
    ):
        return False

    # -----------------------------
    # Empty after cleanup
    # -----------------------------

    if not name.replace(".", "").replace("-", "").strip():
        return False

    return True


# ==================================================
# Remove Partial Names
# ==================================================

def remove_partial_names(entities):

    if not entities:
        return []

    names = [e["name"] for e in entities]

    filtered = []

    for entity in entities:

        current = entity["name"]

        current_lower = current.lower()

        remove = False

        for other in names:

            if current == other:
                continue

            other_lower = other.lower()

            if (
                current_lower != other_lower
                and re.search(
                    rf"\b{re.escape(current_lower)}\b",
                    other_lower
                )
            ):

                if len(other) > len(current):

                    remove = True
                    break

        if not remove:
            filtered.append(entity)

    return filtered


# ==================================================
# Deduplicate Entities
# ==================================================

def deduplicate_entities(entities):

    unique = {}

    for entity in entities:

        key = entity["name"].lower()

        if key not in unique:

            unique[key] = entity
            continue

        old = unique[key]

        if len(entity["name"]) > len(old["name"]):

            unique[key] = entity

    return list(unique.values())


# ==================================================
# Sort Entities
# ==================================================

def sort_entities(entities):
    """
    Sort entities alphabetically.
    """

    return sorted(
        entities,
        key=lambda x: (
            x["category"],
            x["name"].lower()
        )
    )
# ==================================================
# Final Post Processing Pipeline
# ==================================================

def post_process_proper_nouns(raw_response, original_text=""):
    """
    Post-process LLM extracted proper nouns.

    Pipeline:
        1. Clean JSON
        2. Parse JSON
        3. Clean entity names
        4. Normalize categories
        5. Validate entities
        6. Remove hallucinations (optional)
        7. Remove partial names
        8. Remove duplicates
        9. Sort entities
    """

    # -----------------------------
    # Clean JSON
    # -----------------------------

    cleaned_json = clean_json_string(raw_response)

    try:
        data = json.loads(cleaned_json)
    except Exception:
        return {"proper_nouns": []}

    entities = data.get("proper_nouns", [])

    if not isinstance(entities, list):
        return {"proper_nouns": []}

    processed = []

    # -----------------------------
    # Process every entity
    # -----------------------------

    for entity in entities:

        if not isinstance(entity, dict):
            continue

        raw_name = entity.get("name", "")
        raw_category = entity.get("category", "")

        # Clean entity

        name = clean_entity_name(raw_name)
        if len(name.split()) == 1:
            if (
                name.lower() in AMBIGUOUS_FIRST_NAMES
                and original_text
            ):

                full_found = False

                for word in original_text.split():

                    if word.lower().startswith(name.lower()):

                        if len(word) > len(name):
                            full_found = True
                            break

                if not full_found:
                    continue

        if not name:
            continue

        # Normalize category

        category = normalize_category(raw_category, name)

        if category is None:
            continue

        # Strong validation

        if not is_valid_entity(name, category):
            continue

        # Optional hallucination check
        # Comment these lines if not required

        if original_text:

            if name.lower() not in original_text.lower():
                continue

        processed.append(
            {
                "name": name,
                "category": category
            }
        )

    # -----------------------------
    # Remove partial names
    # -----------------------------

    processed = remove_partial_names(processed)

    # -----------------------------
    # Remove duplicates
    # -----------------------------

    processed = deduplicate_entities(processed)

    # -----------------------------
    # Sort
    # -----------------------------

    processed = sort_entities(processed)

    # -----------------------------
    # Return
    # -----------------------------

    return {
         "proper_nouns": processed
    }