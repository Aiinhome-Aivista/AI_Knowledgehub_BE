from flask import request, jsonify
from database.dbConnection import get_mysql_connection
from services.llm_processor import call_llm_chat
from prompts import get_rag_system_prompt
from utils.logger import sys_logger

def handle_chat():
    """
    RAG Chat endpoint handler.
    Expects a JSON payload with 'message'.
    """
    data = request.json
    if not data or 'message' not in data:
        return jsonify({"status": "error", "message": "Message is required", "status_code": 400})

        
    user_message = data['message']
    
    # Persist the search query to search_logs
    try:
        conn = get_mysql_connection()
        if conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO search_logs (query, count)
                VALUES (%s, 1)
                ON DUPLICATE KEY UPDATE count = count + 1
            """, (user_message.strip(),))
            conn.commit()
            cursor.close()
            conn.close()
    except Exception as e:
        sys_logger.log(f"Failed to log search query to DB: {e}", level="ERROR")
    
    # Dynamic Hybrid Search: Combine Chronological Recency and Semantic Search
    context = ""
    context_pieces = []
    seen_urls = set()
    
    # 1. Timeline/Recency Context (Briefly list the headlines of the latest 3 articles)
    recency_text = "Latest News Headlines:\n"
    try:
        conn = get_mysql_connection()
        if conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT source_url, title FROM articles_meta ORDER BY id DESC LIMIT 3")
            latest_articles = cursor.fetchall()
            cursor.close()
            conn.close()
            
            if latest_articles:
                for art in latest_articles:
                    recency_text += f"- Title: {art['title']} (Source: {art['source_url']})\n"
                context_pieces.append(recency_text)
    except Exception as e:
        sys_logger.log(f"Error fetching chronological context: {e}", level="ERROR")

    # 2. Semantic Search & Combined Retrieval Flow
    try:
        from database.dbConnection import get_chroma_collection
        collection = get_chroma_collection()
        
        # Query ChromaDB for top 5 semantically similar documents (can be articles or Wikipedia search summaries)
        results = collection.query(
            query_texts=[user_message],
            n_results=5
        )
        
        article_urls = set()
        
        if results and results.get('documents') and results['documents'][0]:
            for i, doc in enumerate(results['documents'][0]):
                meta = results['metadatas'][0][i] if results.get('metadatas') and results['metadatas'][0] else {}
                doc_type = meta.get('type')
                
                if doc_type == 'article':
                    url = meta.get('source_url')
                    if url:
                        article_urls.add(url)
                elif doc_type == 'proper_noun_search':
                    assoc_url = meta.get('associated_article_url')
                    if assoc_url:
                        article_urls.add(assoc_url)
                else:
                    # Fallback for documents that do not have type metadata
                    url = meta.get('source_url')
                    if url:
                        if "wikipedia.org" not in url:
                            article_urls.add(url)
                            
        # For each matched article, fetch both:
        # A. The full article content chunks from ChromaDB
        # B. The Wikipedia search content of all proper nouns extracted from that article
        for url in article_urls:
            article_title = "Unknown Article"
            
            # Fetch article chunks
            art_res = collection.get(where={"$and": [{"source_url": url}, {"type": "article"}]})
            if art_res and art_res.get('documents'):
                art_docs = art_res['documents']
                if art_res.get('metadatas') and art_res['metadatas']:
                    article_title = art_res['metadatas'][0].get('title', 'Unknown Article')
                
                art_content = "\n".join(art_docs)
                context_pieces.append(f"Original Article Content:\nTitle: {article_title}\nSource URL: {url}\n\nContent:\n{art_content}")
                seen_urls.add(url)
                
            # Fetch associated Wikipedia search results for the proper nouns of this article
            wiki_res = collection.get(where={"$and": [{"associated_article_url": url}, {"type": "proper_noun_search"}]})
            if wiki_res and wiki_res.get('documents'):
                for j, doc in enumerate(wiki_res['documents']):
                    wiki_meta = wiki_res['metadatas'][j]
                    pn_name = wiki_meta.get('proper_noun', 'Entity')
                    # Keep context compact: only include Wikipedia content for entities mentioned in the query, truncated to 2000 chars
                    if pn_name.lower() in user_message.lower():
                        context_pieces.append(f"Wikipedia Context for proper noun '{pn_name}' associated with article '{article_title}':\n{doc[:2000]}")
                    
    except Exception as e:
        sys_logger.log(f"Error fetching context from ChromaDB: {e}", level="ERROR")
            
    # Check if we have context and meaningful overlap
    has_overlap = False
    meaningful_query_words = []
    if context_pieces:
        import re
        user_words = re.findall(r'\b[a-zA-Z]{3,}\b', user_message.lower())
        query_stopwords = {
            'what', 'who', 'where', 'when', 'why', 'how', 'is', 'are', 'was', 'were', 'the', 'a', 'an', 'and', 'or', 
            'about', 'tell', 'me', 'info', 'information', 'details', 'status', 'please', 'explain', 'show'
        }
        meaningful_query_words = [w for w in user_words if w not in query_stopwords]
        
        context_lower = "\n\n---\n\n".join(context_pieces).lower()
        has_overlap = any(word in context_lower for word in meaningful_query_words)
        
        if meaningful_query_words and not has_overlap:
            sys_logger.log(f"Bypassed LLM: No overlap found between user query keywords {meaningful_query_words} and context.", level="WARN")
            return jsonify({"response": "I couldn't find any relevant information for your query in the current knowledge base."})
        
        context = "\n\n---\n\n".join(context_pieces)
    else:
        sys_logger.log("No specific knowledge found in the database. Bypassing LLM.", level="WARN")
        return jsonify({"response": "I couldn't find any relevant information for your query in the current knowledge base."})
        
    # 4. Call the LLM to generate the RAG response
    sys_logger.log(f"Querying LLM with context length: {len(context)}", level="INFO")
    system_prompt = get_rag_system_prompt(context)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ]
    response = call_llm_chat(messages)
    if not response:
        response = "I'm currently unable to process your request. Please try again later."
    
    # Check if the LLM response is a refusal/unavailability message
    refusal_keywords = [
        "i do not have", "i don't have", "sorry", "not mentioned in the context", 
        "not found in the context", "unable to answer", "cannot answer", 
        "not enough information", "don't find", "couldn't find"
    ]
    response_lower = response.lower()
    if any(k in response_lower for k in refusal_keywords):
        response = "I couldn't find any relevant information for your query in the current knowledge base."
        
    sys_logger.log("Generated RAG response successfully.", level="SUCCESS")
    
    return jsonify({
    "status": "success", 
    "message": "Response generated successfully", 
    "status_code": 200, 
    "data": {"response": response}
})


