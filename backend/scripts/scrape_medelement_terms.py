import sys
import os
import time
import re
import json
import httpx
from bs4 import BeautifulSoup
import psycopg2
from openai import OpenAI

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
    # e.g., /term/ana/45381392620505 -> 45381392620505
    # e.g., /term/1010 -> 1010
    match = re.search(r'/term/(?:.*/)?(\d+)', href)
    if match:
        return match.group(1)
    return href.strip('/').split('/')[-1]

def classify_batch(openai_client, model_name, batch):
    prompt = """You are a medical data classification assistant. You are given a list of medical terms with their descriptions.
For each term, you must clean it and classify it into one of these categories:
1. "symptom" - symptoms, complaints, physical findings, syndromes (e.g., "опоясывающая боль", "одышка", "лихорадка", "крепитация").
2. "medication" - drugs, active substances, generics, brand names (e.g., "Амоксициллин", "эритропоэтины").
3. "disease" - diseases, diagnoses, pathology names (e.g., "эрозивный эзофагит", "эшерихиоз", "язвенный колит").
4. "lab_test" - laboratory diagnostics, tests, indicators (e.g., "общий анализ крови", "антинуклеарные антитела").
5. "instrumental_test" - instrumental diagnostics, imaging, functional tests (e.g., "УЗИ органов брюшной полости", "ЭКГ", "КТ головного мозга").
6. "other" - general medical terms, clinical procedures, anatomy terms, abbreviations or general medical jargon that doesn't fit the above categories.

Guidelines:
- Clean the name: return the name in standard Russian (singular nominative case where appropriate, keep uppercase for standard acronyms/abbreviations like CPAP or ANA, lowercase for general symptoms/diseases unless proper names).
- Return a valid JSON array of objects. Each object must have:
  - "raw": the exact raw name from the input.
  - "name": the cleaned, standardized Russian name.
  - "category": the chosen category ("symptom", "medication", "disease", "lab_test", "instrumental_test", "other").

Do not include any explanation or markdown formatting in your response. Just return the raw JSON array.

List of terms to process:
""" + json.dumps(batch, ensure_ascii=False, indent=2)

    retries = 3
    for attempt in range(retries):
        try:
            response = openai_client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}]
            )
            content = response.choices[0].message.content.strip()
            
            # Clean markdown formatting if present
            if content.startswith("```"):
                content = re.sub(r"^```(?:json)?\n", "", content)
                content = re.sub(r"\n```$", "", content)
            
            return json.loads(content)
        except Exception as e:
            print(f"  Attempt {attempt + 1} failed: {e}")
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            else:
                print(f"  Failed to process batch after {retries} attempts.")
                return []

def main():
    settings = get_settings()
    if not settings.openai_api_key:
        print("Error: OPENAI_API_KEY is not set in environment or config.")
        sys.exit(1)

    model_name = settings.openai_models.split(",")[0].strip()
    print(f"Using OpenAI Model: {model_name}")

    openai_client = OpenAI(api_key=settings.openai_api_key)

    conn = psycopg2.connect(get_settings().sync_database_url)
    cur = conn.cursor()

    # Load existing node names from DB (lowercased)
    cur.execute("SELECT LOWER(name) FROM medical_nodes")
    existing_names = {row[0] for row in cur.fetchall()}
    print(f"Loaded {len(existing_names)} existing medical nodes from database.")

    scraped_terms = []
    total_pages = 175 # skip from 0 to 1740 (175 pages)

    print("\n--- Phase 1: Crawling terms from MedElement ---")
    with httpx.Client(timeout=30.0, headers=HEADERS) as client:
        for page_idx in range(total_pages):
            skip = page_idx * 10
            url = f"{BASE_URL}?searched_data=terms&q=&mq=&tq=&terms_filter_type=list&skip={skip}"
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
            
            articles = soup.find_all("article")
            found_on_page = 0
            for article in articles:
                link = article.find("a", class_="results-item__title-link")
                if not link or not link.get("href") or "/term/" not in link["href"]:
                    continue
                
                raw_name = clean_name(link.text)
                if not raw_name:
                    continue
                
                # Check description
                desc_divs = article.find_all("div", class_="results-item__value")
                description = ""
                for div in desc_divs:
                    if "Упоминаний в статьях" in div.text:
                        continue
                    description = div.text.strip()
                    break
                
                ext_id = extract_external_id(link["href"])
                
                # Deduplicate before classification to save API tokens
                if raw_name.lower() in existing_names:
                    continue
                
                scraped_terms.append({
                    "raw_name": raw_name,
                    "description": description,
                    "external_id": ext_id
                })
                found_on_page += 1
            
            print(f"  Found {found_on_page} unique new terms on page.")
            time.sleep(0.3)

    print(f"\nCrawling finished. Found {len(scraped_terms)} unique terms not present in the DB.")
    if not scraped_terms:
        print("No new terms to process. Exiting.")
        cur.close()
        conn.close()
        return

    print("\n--- Phase 2: Classifying and seeding terms using LLM ---")
    batch_size = 50
    total_candidates = len(scraped_terms)
    inserted_count = 0
    ignored_count = 0

    for i in range(0, total_candidates, batch_size):
        batch = scraped_terms[i:i+batch_size]
        print(f"Classifying batch {i//batch_size + 1}/{(total_candidates + batch_size - 1)//batch_size} (Items {i+1} to {min(i+batch_size, total_candidates)})...")
        
        # Prepare input for LLM
        llm_input = []
        for item in batch:
            llm_input.append({
                "name": item["raw_name"],
                "description": item["description"]
            })
            
        results = classify_batch(openai_client, model_name, llm_input)
        if not results:
            print("  Warning: Empty response for batch. Skipping inserts for this batch.")
            continue

        # Map results back to external_id
        results_by_raw = {res["raw"].lower(): res for res in results if "raw" in res}
        
        batch_inserted = 0
        for item in batch:
            raw_key = item["raw_name"].lower()
            res_item = results_by_raw.get(raw_key)
            if not res_item:
                # Fallback to defaults if model output missed this key
                cleaned_name = item["raw_name"]
                category = "other"
            else:
                cleaned_name = res_item.get("name", item["raw_name"])
                category = res_item.get("category", "other")

            # Check if cleaned name exists in DB to be absolutely sure
            if cleaned_name.lower() in existing_names:
                continue

            try:
                cur.execute(
                    """INSERT INTO medical_nodes (name, category, external_id, source)
                       VALUES (%s, %s, %s, %s)""",
                    (cleaned_name, category, item["external_id"], 'medelement_terms')
                )
                existing_names.add(cleaned_name.lower())
                inserted_count += 1
                batch_inserted += 1
            except Exception as db_err:
                print(f"  Database error inserting '{cleaned_name}': {db_err}")
                conn.rollback()

        conn.commit()
        print(f"  Seeded {batch_inserted} new nodes from this batch.")
        time.sleep(0.5)

    cur.close()
    conn.close()

    print("\n--- Seeding Completed! ---")
    print(f"Successfully inserted: {inserted_count} terms into medical_nodes.")

if __name__ == '__main__':
    main()
