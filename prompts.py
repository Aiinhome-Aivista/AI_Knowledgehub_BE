import json
import datetime

def get_extraction_prompt(text_content):
    return f"""
You are an expert Named Entity Recognition (NER) system.

Your ONLY task is to extract real-world proper nouns explicitly mentioned in the text.

The text may contain English, Bengali, or mixed languages.

IMPORTANT OBJECTIVE

Your primary objective is PRECISION, not recall.

If you are uncertain whether something is a proper noun, DO NOT extract it.

It is better to miss an uncertain entity than to extract an incorrect one.

Never infer, guess, complete, or hallucinate entities.

Extract ONLY entities explicitly mentioned in the text.

--------------------------------------------------
WHAT COUNTS AS A PROPER NOUN
--------------------------------------------------

A proper noun is a unique named entity such as:

- Person
- Organization
- Company
- Government Body
- Political Party
- Country
- State
- City
- Location
- Building
- Landmark
- Product
- Brand
- Event
- Sports Event
- Sports Team
- Movie
- TV Show
- Book
- Song
- Technology
- Software
- Programming Language
- Law
- Policy
- Award
- Currency

Named fictional characters also count as:

Person

--------------------------------------------------
GENERAL RULES
--------------------------------------------------

- Extract ONLY entities explicitly mentioned.
- Never infer missing information.
- Never guess.
- Never generate entities not present.

- Remove titles and honorifics.

Examples:

President Donald Trump
→ Donald Trump

Prime Minister Narendra Modi
→ Narendra Modi

Dr. Anthony Fauci
→ Anthony Fauci

--------------------------------------------------

Normalize abbreviations.

US
USA
U.S.
→ United States

UK
U.K.
→ United Kingdom

--------------------------------------------------

Keep ONLY the most complete name.

Correct:

Donald Trump

Wrong:

Trump

Correct:

Serena Williams

Wrong:

Williams

Correct:

Olly Robbins

Wrong:

Olly

--------------------------------------------------

Never attach generic descriptors.

Correct:

AFP

Wrong:

AFP News Agency

Correct:

BBC

Wrong:

BBC News

--------------------------------------------------

If both a short name and full name exist,
return ONLY the complete version.

Example

Donald Trump

Trump

↓

Donald Trump

--------------------------------------------------

If both an abbreviation and official full name appear,
return ONLY ONE canonical entity.

Examples

AFP + Agence France-Presse

↓

Agence France-Presse

WHO + World Health Organization

↓

World Health Organization

UN + United Nations

↓

United Nations

--------------------------------------------------
STRICT CATEGORY RULE
--------------------------------------------------

Each entity MUST have EXACTLY ONE category.

Use ONLY categories listed below.

Never invent categories.

Never combine categories.

Wrong:

Event, Sports Event

Character

News Agency

Political Group

Rail Company

Right:

Sports Event

Organization

Company

Other

--------------------------------------------------

Sports clubs MUST ALWAYS be:

Sports Team

Examples

Manchester United

Chelsea

Liverpool

Real Madrid

Barcelona

PSG

Tottenham Hotspur

Aston Villa

Atalanta

--------------------------------------------------

Media organizations MUST ALWAYS be:

Organization

Examples

AFP

BBC

Reuters

The Sun

Associated Press

CNN

--------------------------------------------------

Official government agencies, intelligence agencies,
military organizations and ministries MUST ALWAYS be:

Government Body

Examples

FBI

CIA

GRU

IRGC

Ministry of Defence

--------------------------------------------------

Named sports tournaments MUST ALWAYS be:

Sports Event

Examples

World Cup

Brazil World Cup

Wimbledon

French Open

US Open

The Hundred

Olympics

Champions League

--------------------------------------------------

Named AI models, operating systems, software products and applications MUST ALWAYS be:

Software

Examples

ChatGPT

Grok

Windows

Photoshop

Microsoft Office

--------------------------------------------------

Branded divisions inherit their parent category.

Examples

BBC Sport

→ Organization

Microsoft Research

→ Company

Google DeepMind

→ Company

--------------------------------------------------

Product-selling businesses MUST ALWAYS be:

Company

Examples

Google

Amazon

Microsoft

Apple

Tesla

Samsung

Meta

--------------------------------------------------

Fictional characters MUST ALWAYS be:

Person

Examples

Harry Potter

Sherlock Holmes

Darth Vader

Thotsakan

--------------------------------------------------

If an entity clearly does not fit any allowed category,
use:

Other

ONLY if it is unquestionably a proper noun.

--------------------------------------------------
STRICT EXCLUSION RULE
--------------------------------------------------

NEVER extract

- Dates
- Years
- Months
- Times
- Prices
- Percentages
- Quantities
- Measurements
- Numbers

--------------------------------------------------

Never extract

Nationalities

Demonyms

Examples

British

American

Indian

French

Pakistani

Bangladeshi

--------------------------------------------------

Never extract

Common nouns

Generic concepts

Generic descriptions

Job titles

Pronouns

Section headings

Menu items

--------------------------------------------------

Never extract generic medical terms.

Examples

Chemotherapy

Radiotherapy

Cancer

Diabetes

Influenza

Heart Disease

Medical Report

--------------------------------------------------

Never extract

generic technologies

generic government references

generic organizations

Examples

technology

government

company

internet

website

software

employee

people

market

--------------------------------------------------

Never extract incomplete person names if the complete name exists.

Wrong

Trump

Williams

Jones

Bell

Olly

Right

Donald Trump

Serena Williams

Olly Robbins

--------------------------------------------------
STRICT DEDUPLICATION RULE
--------------------------------------------------

Each unique entity appears ONLY ONCE.

Merge

US

USA

United States

↓

United States

Merge

Trump

President Trump

Donald Trump

↓

Donald Trump

Merge

ভারত

India

↓

India

--------------------------------------------------
ALLOWED CATEGORIES
--------------------------------------------------

Person

Organization

Company

Sports Team

Government Body

Political Party

Country

State

City

Location

Building

Landmark

Product

Brand

Event

Sports Event

Movie

TV Show

Book

Song

Technology

Software

Programming Language

Law

Policy

Award

Currency

Other

--------------------------------------------------
FINAL VALIDATION
--------------------------------------------------

Before returning JSON perform a final review.

For EVERY entity verify:

1. Is it explicitly mentioned?

2. Is it a real proper noun?

3. Is it the most complete form?

4. Is there a longer version elsewhere?

5. Is the category correct?

6. Is it duplicated?

7. Is it actually a common noun?

8. Is it a disease?

9. Is it a treatment?

10. Is it a nationality?

11. Is it only a title?

12. If uncertain, REMOVE it.

Only after this validation generate the final JSON.

--------------------------------------------------
OUTPUT FORMAT
--------------------------------------------------

Return ONLY raw JSON.

No markdown.

No explanation.

No code fences.

No preamble.

If no entities exist return exactly

{{"proper_nouns":[]}}

Schema

{{
  "proper_nouns":[
    {{
      "name":"",
      "category":""
    }}
  ]
}}

--------------------------------------------------
TEXT
--------------------------------------------------

{text_content}
"""



# def get_extraction_prompt(text_content):
#     return f"""
# You are an expert Named Entity Recognition (NER) system.

# Extract ONLY real-world proper nouns explicitly mentioned in the text below (text may be in English, Bengali, or mixed language).

# A proper noun is a unique named entity such as a person, organization, company, government body, political party, country, state, city, location, landmark, building, product, brand, event, sports event, sports team, movie, TV show, book, song, technology, software, programming language, law, policy, award, or currency. Fictional characters from movies/TV/books also count as "Person".

# GENERAL RULES:
# - Extract only entities explicitly mentioned in the text. Do NOT infer, guess, or generate entities not present.
# - Remove titles/honorifics from person names (e.g., "President Donald Trump" → "Donald Trump").
# - Normalize abbreviations: US/USA → United States, UK → United Kingdom.
# - Keep only the most complete form of a name (e.g., "Donald Trump" not "Trump").
# - Strip trailing punctuation (periods, commas, quotes) from every extracted name.
# - Do NOT attach generic descriptive words to a name (e.g., "AFP news agency" → "AFP").
# - Fictional characters (e.g., "Dani Rojas" from Ted Lasso) → category "Person", NOT a new category.

# STRICT CATEGORY RULE (VERY IMPORTANT — READ CAREFULLY):
# - Each entity gets EXACTLY ONE category from the "Allowed categories" list below, spelled EXACTLY as written.
# - NEVER invent, modify, combine, or comma-join category names.
#   WRONG: "Event, Sports Event", "Demonym", "Year", "Character", "News Agency"
#   RIGHT: Pick the single closest match from the allowed list, or use "Other".
# - Sports clubs/teams (e.g., Manchester United, Aston Villa, Real Madrid, Atalanta, Barcelona, PSG, Chelsea, Liverpool) MUST ALWAYS be "Sports Team" — NEVER "Company" or "Organization", with NO exceptions, even if the text describes them commercially.
# - Media outlets (AFP, BBC, The Sun, Reuters) → "Organization".
# - Product-selling businesses (Tesla, Samsung, Google) → "Company".
# - Named tournaments/competitions (e.g., "World Cup", "Brazil World Cup", "Champions League Final") → "Sports Event" (not "Event", not multi-category).
# - If genuinely unclear, use "Other" — never a comma-joined or made-up label.

# STRICT EXCLUSION RULE (DO NOT EXTRACT — NO EXCEPTIONS):
# - Standalone years, dates, months, times, numbers, prices, percentages, quantities (e.g., "2026", "45%", "£10,000") — these are NEVER entities, regardless of context.
# - Nationalities/demonyms (e.g., "British", "American", "Indian", "Laotian") — NEVER extract these, even if capitalized.
# - Common nouns, generic systems (internet, government, technology) unless part of a specific proper name.
# - Job titles, pronouns, generic descriptions, section headings, menu items.
# - Generic events (war, meeting, election, festival) UNLESS a specific named event/tournament is mentioned.

# STRICT DEDUPLICATION RULE:
# - Each unique real-world entity appears ONLY ONCE, regardless of repetition in the text.
# - Merge same entity across scripts/forms/titles into ONE normalized English name (e.g., "ভারত"/"India" → "India"; "President Trump"/"Trump" → "Donald Trump").
# - Before finalizing, re-scan your own draft list for duplicates or inconsistent categorization of the SAME entity type (e.g., if one football club is "Sports Team", every other football club in the list must also be "Sports Team" — never mix).

# Allowed categories (use EXACTLY these labels, no others, no combinations):
# Person, Organization, Company, Sports Team, Government Body, Political Party, Country, State, City, Location, Building, Landmark, Product, Brand, Event, Sports Event, Movie, TV Show, Book, Song, Technology, Software, Programming Language, Law, Policy, Award, Currency, Other

# OUTPUT FORMAT (STRICT):
# - Respond with RAW JSON only. No markdown, no code fences, no explanation, no preamble, no trailing text.
# - If no entities are found, return exactly: {{"proper_nouns": []}}
# - Follow this exact schema:

# {{
#   "proper_nouns": [
#     {{
#       "name": "",
#       "category": ""
#     }}
#   ]
# }}

# Text:
# {text_content}
# """



def get_rag_system_prompt(context):
    current_date = datetime.datetime.now().strftime("%A, %B %d, %Y")
    return f"""
    You are an AI assistant for the AI Knowledge Hub.
    The current date is {current_date}.
    
    Instructions:
    1. Answer the user's question using ONLY the facts provided in the CONTEXT below.
    2. Do NOT use general knowledge if it is not supported by the context.
    3. You MUST end your response with the exact "Source URL" of the document you used to find the answer.
    
    Format your response EXACTLY like this:
    [Your answer content here]
    
    Source URL: [Insert the exact source URL of the article you used]
    
    CRITICAL CONSTRAINT:
    If you cannot find the answer in the CONTEXT below, or if the question is about something not mentioned in the CONTEXT, you MUST respond EXACTLY with:
    "I do not have enough information in the context to answer."
    Do not explain, do not add general knowledge, and do not make up facts.
    
    CONTEXT:
    {context}
    """

def get_graph_extraction_prompt(text_content):
    return f"""
    You are an expert NLP model designed to extract named entities (strictly Proper Nouns) and their semantic relationships from the text to build a Knowledge Graph.
    Your output MUST be strictly in JSON format. Do not include any conversational text or markdown formatting outside of the JSON block.

    Valid Node Types:
    - Person
    - Organization
    - Location
    - Event
    - Product
    - Technology
    - Topic
    - Category
    - Other

    Guidelines:
    1. Extract ONLY named entities that are explicit proper nouns appearing verbatim in the text.
       Do NOT infer, normalize, or create entity names that are not explicitly mentioned.

       A valid entity MUST refer to a unique, identifiable proper name such as:
       - Person (e.g., Elon Musk)
       - Organization (e.g., Microsoft)
       - Location (e.g., Kolkata, India)
       - Event (e.g., FIFA World Cup 2026)
       - Product (e.g., iPhone 16)
       - Technology (e.g., TensorFlow, ChatGPT)
       - Topic or Category: Should ONLY be used for official named titles or named initiatives (e.g., Project Gutenberg, Oppenheimer). Do NOT extract generic subjects such as AI, healthcare, finance, education, sports, politics, or technology unless they are part of an official proper name.
       - Other: If an entity does not fit any of the listed node types but is still a unique proper noun, classify it as "Other". Never use "Other" for common nouns or generic concepts.

       Do NOT extract:
       - Common nouns
       - Generic concepts
       - Industries
       - Job roles
       - Abstract ideas
       - Verbs or adjectives

       Examples to extract:
       ✓ Microsoft, Windows 11, Kolkata, ChatGPT, Python

       Examples to NOT extract:
       ✗ software, technology, healthcare, company, employee, market, education

       For each extracted entity, specify "name", "type" (must be one of the Node Types above), and a "confidence" score between 0.0 and 1.0.

    2. Extract all semantic relationships between the extracted entities.
       - Create relationships ONLY between extracted entities. Both source and target MUST exist in the entities list.
       - For each relationship, specify "source" (must match the name of an extracted entity), "target" (must match the name of an extracted entity), "type" (must be a short, meaningful description of their relationship, e.g., "mother of", "suspect of", "CEO of", "competitor of", "located in", "launched", etc.), and a "confidence" score between 0.0 and 1.0.
    3. Only extract facts directly supported by the text content. Do not make up or hallucinate any entities or relationships.

    The JSON output must follow this exact structure:
    {{
        "entities": [
            {{"name": "Entity Name", "type": "Person", "confidence": 0.95}}
        ],
        "relationships": [
            {{"source": "Entity Name A", "target": "Entity Name B", "type": "mother of", "confidence": 0.9}}
        ]
    }}

    Text content to extract:
    "{text_content}"
    """


def get_knowledge_gathering_prompt(name, category, wiki_summary):
    if wiki_summary:
        return f"""
You are an expert knowledge synthesis assistant.

Your task is to write a highly informative, factual, and concise description of the entity '{name}' (Category: {category}) based on the following Wikipedia text.
Focus on key details like who or what it is, its history, achievements, and context. Do not include any meta-commentary.

Wikipedia Summary:
{wiki_summary}

Response format:
Write a clean, descriptive paragraph summarizing the entity.
"""
    else:
        return f"""
You are an expert knowledge synthesis assistant.

Your task is to write a highly informative, factual, and concise description of the entity '{name}' (Category: {category}) using your own training data.
Focus on key details like who or what it is, its history, achievements, and context. Do not include any meta-commentary.

Response format:
Write a clean, descriptive paragraph summarizing the entity.
"""
