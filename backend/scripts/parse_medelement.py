import asyncio
import os
import sys
import json
import httpx
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin
import psycopg2

# Add backend dir to python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import get_settings

def save_protocols_sync(protocols_data):
    """Save protocols using plain psycopg2 — no async, no pool, no timeouts."""
    if not protocols_data:
        return
    conn = psycopg2.connect(get_settings().sync_database_url)
    try:
        cur = conn.cursor()
        for data in protocols_data:
            cur.execute("SELECT id FROM clinical_protocols WHERE url = %s", (data["url"],))
            if cur.fetchone() is None:
                cur.execute(
                    """INSERT INTO clinical_protocols (title, category, year, url, text_content)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (data["title"], data["category"], data["year"], data["url"], data["text_content"])
                )
        conn.commit()
        cur.close()
    except Exception as e:
        conn.rollback()
        print(f"  DB error: {e}")
    finally:
        conn.close()

# --- Web scraping (async for speed) ---
BASE_URL = "https://diseases.medelement.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

async def fetch_html(client, url):
    try:
        response = await client.get(url, headers=HEADERS)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return ""

async def extract_sections(client):
    url = f"{BASE_URL}/search?searched_data=diseases&diseases_filter_type=section_medicine&section_medicine=4571385460025&diseases_content_type=4"
    html = await fetch_html(client, url)
    soup = BeautifulSoup(html, "lxml")
    
    sections = {}
    for a in soup.find_all("a", href=True):
        href = a["href"]
        match = re.search(r"section_medicine=(\d+)", href)
        if match and "diseases_filter_type=section_medicine" in href:
            section_id = match.group(1)
            if section_id != "0":
                sections[section_id] = a.text.strip()
    return sections

async def parse_disease_links(client, section_id):
    links = []
    skip = 0
    while True:
        url = f"{BASE_URL}/search?searched_data=diseases&diseases_filter_type=section_medicine&section_medicine={section_id}&diseases_content_type=4&skip={skip}"
        html = await fetch_html(client, url)
        soup = BeautifulSoup(html, "lxml")
        
        disease_links = soup.find_all("a", href=re.compile(r"/disease/"))
        if not disease_links:
            break
            
        added_in_page = 0
        for a in disease_links:
            href = a["href"]
            if not href.startswith("http"):
                href = urljoin(BASE_URL, href)
            if href not in links:
                links.append(href)
                added_in_page += 1
                
        if added_in_page == 0:
            break
            
        skip += 10
    return links

async def parse_protocol(client, url, category):
    html = await fetch_html(client, url)
    if not html:
        return None
    soup = BeautifulSoup(html, "lxml")
    
    title_elem = soup.find("h1") or soup.find("title")
    title = title_elem.text.strip() if title_elem else "Unknown"
    
    content_div = soup.find("div", class_="material-content") or soup.find("div", class_="box-content") or soup.find("body")
    if not content_div:
        return None
    
    from markdownify import markdownify as md
    for el in content_div.find_all(['script', 'style', 'nav', 'header', 'footer']):
        el.decompose()
        
    html_str = str(content_div)
    text_content = md(html_str, heading_style='ATX').strip()
    
    year_match = re.search(r"- (\d{4})", title) or re.search(r"(\d{4})", text_content[:200])
    year = int(year_match.group(1)) if year_match else None
    
    return {
        "title": title,
        "category": category,
        "year": year,
        "url": url,
        "text_content": text_content
    }

async def main():
    cache_file = os.path.join(os.path.dirname(__file__), "total_links.json")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # --- Step 1: collect or load links ---
        if os.path.exists(cache_file):
            print("Loading cached links from file...")
            with open(cache_file, "r", encoding="utf-8") as f:
                total_links = json.load(f)
            print(f"Loaded {len(total_links)} links.")
        else:
            print("Extracting sections...")
            sections = await extract_sections(client)
            print(f"Found {len(sections)} sections.")
            
            total_links = []
            for sec_id, sec_name in sections.items():
                print(f"Parsing section: {sec_name} ({sec_id})")
                links = await parse_disease_links(client, sec_id)
                print(f"  Found {len(links)} protocols.")
                for link in links:
                    if [link, sec_name] not in total_links:
                        total_links.append([link, sec_name])
            
            print(f"Total unique protocols to fetch: {len(total_links)}")
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(total_links, f, ensure_ascii=False, indent=2)
        
        # --- Step 2: fetch & save in batches ---
        batch_size = 5
        total = len(total_links)
        for i in range(0, total, batch_size):
            batch = total_links[i:i+batch_size]
            protocols_data = []
            for link, cat in batch:
                print(f"  [{i+1}-{min(i+batch_size, total)}/{total}] {link}")
                data = await parse_protocol(client, link, cat)
                if data and data["text_content"]:
                    protocols_data.append(data)
            
            save_protocols_sync(protocols_data)
            print(f"  OK batch {i//batch_size + 1}/{(total + batch_size - 1)//batch_size}")

if __name__ == "__main__":
    asyncio.run(main())
