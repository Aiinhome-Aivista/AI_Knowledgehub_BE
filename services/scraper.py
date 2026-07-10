import feedparser
import requests
from bs4 import BeautifulSoup
import time
import os
from .llm_processor import extract_proper_nouns

def fetch_rss_feed(feed_url):
    """
    Fetches an RSS feed and returns a list of entries with their links and titles,
    sorted by publication date (newest first).
    """
    print(f"Visiting URL: {feed_url}", flush=True)
    feed = feedparser.parse(feed_url)
    
    # Sort entries newest first. Fallback to epoch time if published_parsed is missing.
    sorted_entries = sorted(
        feed.entries,
        key=lambda x: x.get("published_parsed") or time.gmtime(0),
        reverse=True
    )
    
    entries = []
    for entry in sorted_entries:
        entries.append({
            "title": entry.title,
            "link": entry.link,
            "published": entry.get("published", ""),
            "summary": getattr(entry, "summary", "") or getattr(entry, "description", "")
        })
    return entries

def scrape_article_content(url):
    """
    Scrapes the text content of a given article URL using BeautifulSoup.
    """
    print(f"Visiting URL: {url}", flush=True)
    try:
        try:
            import cloudscraper
            scraper = cloudscraper.create_scraper()
            response = scraper.get(url, timeout=15)
        except ImportError:
            import requests
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            response = requests.get(url, headers=headers, timeout=15)
            
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Save Original HTML to local storage (optional step in flow)
        try:
            import hashlib
            raw_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "storage", "raw_html")
            os.makedirs(raw_dir, exist_ok=True)
            file_name = hashlib.md5(url.encode()).hexdigest() + ".html"
            with open(os.path.join(raw_dir, file_name), "w", encoding="utf-8") as f:
                f.write(response.text)
        except Exception:
            pass
            
        # Basic article text extraction - usually paragraphs are a safe bet
        paragraphs = soup.find_all('p')
        text_content = "\n".join([p.get_text() for p in paragraphs])
        
        return text_content.strip()
    except Exception as e:
        from utils.logger import sys_logger
        sys_logger.log(f"Scraper error for {url}: {e}", level="ERROR")
        return ""

def process_source(url, is_rss=False):
    """
    Given a URL, scrapes it, processes text, and extracts proper nouns using LLM.
    Returns processed data.
    """
    results = []
    
    if is_rss:
        entries = fetch_rss_feed(url)
        for entry in entries[:3]: # Process only the first 3 articles in the feed
            content = scrape_article_content(entry['link'])
            
            # Fallback to RSS summary if scraping the full article gets blocked
            if not content and entry.get('summary'):
                content = entry['summary']
                
            if content:
                # Limit content size for LLM extraction
                short_content = content[:2000]
                proper_nouns_data = extract_proper_nouns(short_content)
                
                results.append({
                    "title": entry["title"],
                    "url": entry["link"],
                    "content": content,
                    "published": entry.get("published", ""),
                    "extracted_topics": proper_nouns_data.get("proper_nouns", [])
                })
    else:
        content = scrape_article_content(url)
        if content:
            short_content = content[:2000]
            proper_nouns_data = extract_proper_nouns(short_content)
            
            import datetime
            now_str = datetime.datetime.now().strftime("%a, %d %b %Y %H:%M:%S GMT")
            results.append({
                "title": "Direct URL Scraping",
                "url": url,
                "content": content,
                "published": now_str,
                "extracted_topics": proper_nouns_data.get("proper_nouns", [])
            })
            
    return results
