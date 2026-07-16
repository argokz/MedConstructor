import sys
import os
import re
import json
import time
import asyncio
import argparse
import psycopg2
from openai import AsyncOpenAI

# Ensure UTF-8 output
sys.stdout.reconfigure(encoding='utf-8')

# Add backend directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config import get_settings

def extract_raw_concepts_from_protocol(text_content):
    headings = []
    for match in re.finditer(r"(?m)^(#{1,6})\s+(.*)$", text_content):
        headings.append({
            "pos": match.start(),
            "level": len(match.group(1)),
            "title": match.group(2).strip(),
        })
    
    med_candidates = []
    diag_symptom_candidates = []
    
    for i in range(len(headings)):
        start = headings[i]["pos"]
        end = headings[i+1]["pos"] if i + 1 < len(headings) else len(text_content)
        section_title = headings[i]["title"]
        section_content = text_content[start:end]
        
        title_lower = section_title.lower()
        if "препараты" in title_lower or "действующие вещества" in title_lower:
            lines = section_content.split('\n')
            for line in lines:
                if '|' in line:
                    parts = [p.strip() for p in line.split('|')]
                    for part in parts:
                        if part and not re.match(r'^[\s\-:|]+$', part):
                            med_candidates.append(part)
        
        elif any(kw in title_lower for kw in ["диагностика", "диагностические", "клиническая картина", "симптомы", "жалобы"]):
            lines = section_content.split('\n')
            for line in lines:
                line_stripped = line.strip()
                if line_stripped.startswith(('·', '-', '*', '•')) or re.match(r'^\d+[\.\)]', line_stripped):
                    clean_line = re.sub(r'^[·\-*•\s\d\.\)]+', '', line_stripped).strip()
                    if clean_line:
                        diag_symptom_candidates.append(clean_line)
                        
    return med_candidates, diag_symptom_candidates

def clean_term(term):
    # Remove citations [1], [2,3], etc.
    term = re.sub(r'\[\d+(?:,\s*\d+)*\]', '', term)
    # Remove markdown formatting
    term = term.replace('**', '').replace('*', '').replace('_', '').replace('`', '')
    # Remove trailing/leading punctuation
    term = term.strip(' ;,.:()\-+*!?')
    # Normalize spaces
    term = re.sub(r'\s+', ' ', term)
    return term

def heuristic_filter(term, is_med=False):
    term = clean_term(term)
    if len(term) < 3:
        return False
    
    # Reject if it contains ANY digit
    if re.search(r'\d', term):
        return False
    
    # Reject if it contains math symbols
    if re.search(r'[<>=≤≥%±/\\|]', term):
        return False

    # Check if contains at least one Cyrillic character OR is a clean uppercase Latin acronym
    has_cyrillic = bool(re.search(r'[а-яА-ЯёЁ]', term))
    is_latin_acronym = bool(re.match(r'^[A-Z\s]{2,12}$', term))
    
    if not (has_cyrillic or is_latin_acronym):
        return False

    # Check word count and length
    words = term.split()
    if is_med:
        if len(words) > 3:
            return False
        if len(term) > 35:
            return False
    else:
        if len(words) > 3:
            return False
        if len(term) > 35:
            return False

    term_lower = term.lower()
    
    # Avoid units of measurement or measurement terms
    units = ["ммоль", "ммоль/л", "г/л", "пг/мл", "ед/л", "мкг", "мг", "сутки", "минуту", "часа", "часов", "дней", "года", "лет", "раза", "раз"]
    if any(u in term_lower for u in units):
        return False

    if is_med:
        if term_lower in ["название препарата", "действующее вещество", "торговое наименование", "дозировка", "кратность", "длительность", "примечание"]:
            return False
            
    junk_diagnostics = [
        "жалобы", "анамнез", "диагностика", "диагностические критерии", 
        "основные диагностические мероприятия", "дополнительные обследования", 
        "лабораторная диагностика", "инструментальная диагностика", 
        "сбор жалоб анамнеза заболевания и жизни", "физикальное обследование", 
        "осмотр", "консультация", "описание", "лечение", "показания",
        "мочи", "крови", "оак", "оам", "узи", "экг", "кт", "мрт", "результаты",
        "критерии", "диагноз", "стадия", "форма", "тип", "вид", "клиника",
        "сортировка", "лабораторное исследование", "сбор анамнеза", "исследование",
        "анализ", "показатели", "данные", "симптомы", "признаки", "факторы"
    ]
    if not is_med:
        if term_lower in junk_diagnostics:
            return False
        if any(term_lower == j for j in junk_diagnostics):
            return False
            
    return True


async def classify_batch(openai_client, model_name, batch):
    prompt = """You are a medical data extraction assistant. You are given a list of raw phrases extracted from clinical protocols.
For each raw phrase, you must clean it, translate/localize it, and classify it into one of these categories:
1. "symptom" - symptoms, complaints, syndromes, physical findings (e.g., "опоясывающая боль", "одышка", "лихорадка", "повышение артериального давления").
2. "medication" - specific drugs, active substances, generics, brand names (e.g., "Амоксициллин", "Альбумин человека", "Парацетамол").
3. "lab_test" - laboratory diagnostics, tests, indicators (e.g., "общий анализ крови", "альфа-амилаза сыворотки", "17-кетостероиды в моче").
4. "instrumental_test" - instrumental diagnostics, imaging, functional tests (e.g., "УЗИ органов брюшной полости", "ЭКГ", "КТ головного мозга", "рентгенография").
5. "other" - if the phrase is a general medical procedure, administrative task, doctor consultation, or does not represent a specific symptom/drug/test (e.g., "сбор анамнеза", "осмотр врача", "физикальное обследование", "госпитализация").

Guidelines:
- If a phrase represents a specific medication, clean up any generic/Latin names in parentheses (e.g., "Альбумин человека (Albumin human)" -> "Альбумин человека").
- Return the name in standard Russian (singular nominative case if applicable, standard capitalisation like first letter uppercase for proper terms, lowercase for generic symptoms).
- If the phrase is junk or generic, classify it as "other".

You must return a valid JSON array of objects. Each object must have:
- "raw": the exact raw phrase from the input.
- "name": the cleaned, standardized Russian name.
- "category": the chosen category ("symptom", "medication", "lab_test", "instrumental_test", "other").

Do not include any explanation or markdown formatting in your response. Just return the raw JSON array.

List of raw phrases to process:
""" + json.dumps(batch, ensure_ascii=False, indent=2)

    retries = 3
    for attempt in range(retries):
        try:
            response = await openai_client.chat.completions.create(
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
                await asyncio.sleep(2 ** attempt)
            else:
                print(f"  Failed to process batch after {retries} attempts.")
                return []

async def main():
    parser = argparse.ArgumentParser(description="Extract and classify medical concepts from clinical protocols.")
    parser.add_argument("--limit", type=int, default=None, help="Limit the number of protocols to parse (for testing)")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.openai_api_key:
        print("Error: OPENAI_API_KEY is not set in environment or config.")
        sys.exit(1)

    model_name = settings.openai_models.split(",")[0].strip()
    print(f"Using OpenAI Model: {model_name}")

    openai_client = AsyncOpenAI(api_key=settings.openai_api_key)

    # 1. Connect to Database
    conn = psycopg2.connect(get_settings().sync_database_url)
    cur = conn.cursor()

    # Query clinical protocols
    if args.limit:
        print(f"Fetching first {args.limit} clinical protocols...")
        cur.execute("SELECT id, title, text_content FROM clinical_protocols LIMIT %s", (args.limit,))
    else:
        print("Fetching all clinical protocols...")
        cur.execute("SELECT id, title, text_content FROM clinical_protocols")
    
    protocols = cur.fetchall()
    print(f"Loaded {len(protocols)} protocols.")

    # 2. Extract Candidates
    all_meds_raw = set()
    all_diags_raw = set()

    for pid, title, text in protocols:
        meds, diags = extract_raw_concepts_from_protocol(text)
        for m in meds:
            if heuristic_filter(m, is_med=True):
                all_meds_raw.add(clean_term(m))
        for d in diags:
            if heuristic_filter(d, is_med=False):
                all_diags_raw.add(clean_term(d))

    print(f"Raw candidates extracted:")
    print(f"  Unique Medications: {len(all_meds_raw)}")
    print(f"  Unique Diagnostic/Symptom Phrases: {len(all_diags_raw)}")

    # Merge candidates into a single set to process
    all_candidates = list(all_meds_raw.union(all_diags_raw))
    print(f"Total unique candidates to process: {len(all_candidates)}")

    # Load existing nodes from DB for duplicate checking
    cur.execute("SELECT name, category FROM medical_nodes")
    existing_nodes = {(row[0].lower(), row[1]) for row in cur.fetchall()}
    print(f"Loaded {len(existing_nodes)} existing nodes from DB to avoid duplicates.")

    # Batch processing
    batch_size = 200
    total_candidates = len(all_candidates)
    inserted_count = 0
    ignored_count = 0
    duplicate_count = 0

    for i in range(0, total_candidates, batch_size):
        batch = all_candidates[i:i+batch_size]
        print(f"Processing batch {i//batch_size + 1}/{(total_candidates + batch_size - 1)//batch_size} (Items {i+1} to {min(i+batch_size, total_candidates)} of {total_candidates})...")
        
        results = await classify_batch(openai_client, model_name, batch)
        if not results:
            print("  Warning: Empty response for batch.")
            continue

        batch_inserted = 0
        for item in results:
            raw = item.get("raw")
            name = item.get("name")
            category = item.get("category")

            if not name or not category or category == "other":
                ignored_count += 1
                continue

            # Validate category
            valid_categories = ["symptom", "medication", "lab_test", "instrumental_test"]
            if category not in valid_categories:
                # Fallback mapping
                if category == "disease":
                    pass # We do not add diseases from here
                else:
                    ignored_count += 1
                    continue

            name_clean = name.strip()
            name_lower = name_clean.lower()
            key = (name_lower, category)

            if key in existing_nodes:
                duplicate_count += 1
                continue

            # Insert node
            try:
                cur.execute(
                    """INSERT INTO medical_nodes (name, category, source)
                       VALUES (%s, %s, %s)""",
                    (name_clean, category, 'protocols')
                )
                existing_nodes.add(key)
                inserted_count += 1
                batch_inserted += 1
            except Exception as db_err:
                print(f"  Error inserting '{name_clean}' ({category}): {db_err}")
                conn.rollback()

        conn.commit()
        print(f"  Inserted {batch_inserted} nodes in this batch.")
        
        # Polite pause
        await asyncio.sleep(0.5)

    cur.close()
    conn.close()

    print("\nExtraction & Classification Completed!")
    print(f"  Total processed: {total_candidates}")
    print(f"  Successfully inserted: {inserted_count} new nodes")
    print(f"  Duplicates skipped: {duplicate_count}")
    print(f"  Ignored/Other: {ignored_count}")

if __name__ == '__main__':
    asyncio.run(main())
