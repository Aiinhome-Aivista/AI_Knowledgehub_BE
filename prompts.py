import json
import datetime




def get_extraction_prompt(text_content):
    return f"""
You are an expert Named Entity Recognition (NER) system.

Your task is to extract ONLY proper nouns (named entities) from the text.

A proper noun refers to a unique named entity such as:

- Person
- Organization
- Company
- Government Body
- Country
- City
- State/Province
- Region
- Building
- Landmark
- Product
- Brand
- Event
- Sports Event
- Tournament
- Movie
- TV Show
- Book
- Song
- Technology
- Software
- Programming Language
- Currency
- Law
- Policy
- Award
- Scientific Discovery

DO NOT extract:

- common nouns
- professions
- job titles alone
- pronouns
- adjectives
- verbs
- numbers
- prices
- dates
- durations
- measurements
- generic words
- "homeowners"
- "regulator"
- "punters"
- "two years"
- "people"
- "government"
- "company"
- "country"

If a title appears with a person's name:

"President Donald Trump"

extract only

"Donald Trump"

If a title appears with an organization:

"Prime Minister Keir Starmer"

extract

"Keir Starmer"

NOT

"Prime Minister"

Normalize entities.

Example:

US -> United States

USA -> United States

UK -> United Kingdom

Do not output duplicates.

Return ONLY valid JSON.

Output format:

{{
  "proper_nouns": [
    {{
      "name": "",
      "category": ""
    }}
  ]
}}

Categories must be one of:

Person
Organization
Company
Location
Country
City
Product
Brand
Event
Movie
Book
Song
Technology
Software
Sports Event
Award
Law
Policy
Currency
Other

Text:

{text_content}
"""

# def get_extraction_prompt(text_content):
#     return f"""
# You are an expert Named Entity Recognition (NER) engine.

# Extract ONLY named entities.

# A named entity is a unique name of:

# - Person
# - Organization
# - Company
# - Country
# - City
# - State
# - Region
# - Landmark
# - Product
# - Brand
# - Event
# - Movie
# - Book
# - Song
# - Technology
# - Software

# DO NOT extract:

# - Common nouns
# - Professions
# - Job titles
# - Roles
# - Money
# - Dates
# - Numbers
# - Percentages
# - Quantities
# - Time expressions
# - Generic descriptions
# - Adjectives

# Examples of INVALID entities:

# homeowners
# regulator
# punters
# two years
# £45
# millionaire
# government
# company
# people

# If an entity contains a title:

# President Donald Trump

# extract ONLY

# Donald Trump

# Prime Minister Keir Starmer

# extract ONLY

# Keir Starmer

# US -> United States

# UK -> United Kingdom

# Return ONLY JSON.

# {
#     "proper_nouns":[
#         {
#             "name":"",
#             "category":""
#         }
#     ]
# }

# Text:

# {text_content}
# """


# def get_extraction_prompt(text_content):
#     return f"""
#     You are an expert Named Entity Recognition (NER) model.
#     Your task is to extract all Proper Nouns (named entities) from the provided text.
    
#     A proper noun represents a specific, unique person, organization, location, product, technology, brand, or event.
    
#     Guidelines:
#     1. Extract ONLY proper nouns that are explicitly mentioned in the text.
#     2. Do NOT extract common nouns (e.g., "internet", "website", "computer", "users", "police", "officer").
#     3. Proper nouns in English are capitalized (e.g., "Tim Berners-Lee", "World Wide Web", "CERN", "HTTP", "HTML").
#     4. Return the output STRICTLY in JSON format. Do not add any conversational text or markdown formatting.
    
#     Output JSON format:
#     {{
#       "proper_nouns": [
#         {{"name": "Entity Name", "category": "Person/Organization/Location/Product/Technology/Event"}}
#       ]
#     }}
    
#     Text content to extract:
#     "{text_content}"
#     """

# def get_extraction_prompt(text_content):
#     return f"""
#     You are an NLP model designed to extract proper nouns (people, organizations, locations, products, events) from the given text.
#     Your output MUST be strictly in JSON format. Do not include any conversational text or markdown formatting outside of the JSON block.
    
#     The JSON should follow this structure:
#     {{
#         "proper_nouns": [
#             {{"name": "...", "category": "Person/Organization/Location/Product/Event"}}
#         ]
#     }}

#     Text:
#     "{text_content}"
#     """

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
