import sys
import os
import time
import re
import httpx
from bs4 import BeautifulSoup
import psycopg2

# Ensure UTF-8 output
sys.stdout.reconfigure(encoding='utf-8')

# Add backend directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config import get_settings

BASE_URL = "https://diseases.medelement.com/search"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def clean_name(name):
    if not name:
        return ""
    # Normalize spacing
    name = re.sub(r'\s+', ' ', name)
    return name.strip()

def extract_external_id(href):
    # e.g., /indicator/антитела-к-mycoplasma-pneumoniae-в-сыворотке-крови/845 -> 845
    # e.g., /indicator/1010 -> 1010
    match = re.search(r'/indicator/(?:.*/)?(\d+)', href)
    if match:
        return match.group(1)
    return href.strip('/').split('/')[-1]

def main():
    conn = psycopg2.connect(get_settings().sync_database_url)
    cur = conn.cursor()

    # Load existing lab_test names from DB (lowercased)
    cur.execute("SELECT LOWER(name) FROM medical_nodes WHERE category = 'lab_test'")
    existing_names = {row[0] for row in cur.fetchall()}
    print(f"Loaded {len(existing_names)} existing lab_test nodes from database.")

    added_count = 0
    skipped_count = 0
    total_pages = 76 # from skip=0 to skip=750 (76 pages)

    with httpx.Client(timeout=30.0, headers=HEADERS) as client:
        for page_idx in range(total_pages):
            skip = page_idx * 10
            url = f"{BASE_URL}?searched_data=indicators&q=&mq=&tq=&indicators_filter_type=list&indicators_category=0&parent_indicators_category=0&skip={skip}"
            print(f"[{page_idx + 1}/{total_pages}] Fetching page skip={skip}...")
            
            retries = 3
            html = ""
            for attempt in range(retries):
                try:
                    response = client.get(url)
                    if response.status_code == 200:
                        html = response.text
                        break
                    else:
                        print(f"  Warning: HTTP status {response.status_code}. Retrying...")
                except Exception as e:
                    print(f"  Error on attempt {attempt + 1}: {e}")
                time.sleep(1)
            
            if not html:
                print(f"  Failed to retrieve page skip={skip}")
                continue

            soup = BeautifulSoup(html, "lxml")
            
            # Find all links with /indicator/
            found_on_page = 0
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if "/indicator/" in href:
                    name = clean_name(a.text)
                    if not name:
                        continue
                    
                    ext_id = extract_external_id(href)
                    
                    # Deduplicate
                    norm_name = name.lower()
                    if norm_name in existing_names:
                        skipped_count += 1
                        continue

                    # Insert
                    try:
                        cur.execute(
                            """INSERT INTO medical_nodes (name, category, external_id, source)
                               VALUES (%s, %s, %s, %s)""",
                            (name, 'lab_test', ext_id, 'medelement')
                        )
                        existing_names.add(norm_name)
                        added_count += 1
                        found_on_page += 1
                    except Exception as db_err:
                        print(f"  Database error inserting '{name}': {db_err}")
                        conn.rollback()

            conn.commit()
            print(f"  Processed page skip={skip}. Found on page: {found_on_page} inserted.")
            # Be polite to the server
            time.sleep(0.3)

    cur.close()
    conn.close()

    print("\nScraping Completed!")
    print(f"  Successfully inserted: {added_count} new lab_test nodes.")
    print(f"  Skipped (duplicates): {skipped_count}")

if __name__ == '__main__':
    main()
