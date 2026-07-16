import asyncio
import json
import os
import sys
from typing import Dict, Any, List

import psycopg2
from dotenv import load_dotenv

# Add parent directory to path so we can import app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.llm_router import llm_router
from app.schemas import NodeType, EdgeType

load_dotenv()

# Database connection details
DB_URL = os.getenv("DATABASE_URL")
if not DB_URL:
    print("Error: DATABASE_URL not set in .env")
    sys.exit(1)

# Parsing database url to standard psycopg2 connection parameters
# Example: postgresql+asyncpg://postgres:change-me@127.0.0.1:5440/medical_constructor
cleaned_url = DB_URL.replace("postgresql+asyncpg://", "postgresql://")

# Optional external dataset path. The default location is inside backend/benchmarks;
# override with MEDCONSTRUCTOR_DATASET_JSONL when importing a one-off dataset.
DATA_FILE = os.getenv(
    "MEDCONSTRUCTOR_DATASET_JSONL",
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "benchmarks",
        "medconstructor_dataset.jsonl",
    ),
)

# Let's write the translation prompt
TRANSLATE_PROMPT = """
Вы — опытный профессор медицины и эксперт-переводчик. 
Вам предоставлен клинический случай в виде JSON с описанием на английском языке:
{case_json}

Ваша задача — перевести данный случай на русский язык и адаптировать его под формат нашей системы клинического конструктора.
Вы должны перевести:
1. `question` -> `case_description` (клиническая виньетка: жалобы, анамнез, объективно, результаты обследований. Удалите любые инструкции вида "Put your final answer in boxed").
2. `answer` -> `expected_diagnosis` (название диагноза на русском языке).
3. `content` -> `expected_treatment` (описание решения, обоснование и план лечения на русском языке).
4. `answer` -> `title` (краткое и понятное название клинического случая на русском языке, максимум 5 слов).
5. `graph` -> `graph_data` (полный граф рассуждений, представленный в виде схемы с узлами и ребрами в соответствии со следующими строгими правилами):

Вы должны сгенерировать JSON объект `graph_data` со следующей структурой:
{{
  "nodes": [
    {{
      "id": "node_1",
      "type": "default",
      "position": {{"x": 100.0, "y": 150.0}},
      "data": {{
        "label": "Метка узла на русском языке (например, 'Боль в эпигастрии', 'Желчнокаменная болезнь', 'Компьютерная томография')",
        "category": "NodeType"
      }}
    }}
  ],
  "edges": [
    {{
      "id": "edge_1",
      "source": "node_1",
      "target": "node_2",
      "label": "EdgeType"
    }}
  ]
}}

ПРАВИЛА ДЛЯ УЗЛОВ (`nodes`):
1. Категория узла (`category`) должна СТРОГО соответствовать одному из значений перечисления NodeType:
   - PATIENT_PROFILE (профиль пациента: возраст, пол, вредные привычки и т.д.)
   - SYMPTOM (симптомы, жалобы)
   - EXAM (объективный осмотр, признаки)
   - LAB_TEST (лабораторные анализы)
   - INSTRUMENTAL_TEST (инструментальные методы диагностики: УЗИ, КТ, МРТ, Рентген)
   - DIAGNOSIS (диагноз)
   - MEDICATION (лекарственная терапия)
   - SURGERY (хирургическое вмешательство)

2. Расположите узлы логически на сетке с помощью `position`:
   - Начните с PATIENT_PROFILE и SYMPTOM слева (например, x = 100, 200).
   - EXAM, LAB_TEST, INSTRUMENTAL_TEST посередине (x = 400, 600).
   - DIAGNOSIS правее (x = 800).
   - MEDICATION и SURGERY в самом конце справа (x = 1000, 1200).
   - Разносите узлы по высоте `y` (например, с шагом 150), чтобы они не перекрывали друг друга.

ПРАВИЛА ДЛЯ СВЯЗЕЙ (`edges`):
1. Тип связи (`label`) должен СТРОГО соответствовать одному из значений перечисления EdgeType:
   - DETERMINES (узел определяет/указывает на другой узел)
   - REQUIRES_CONFIRMATION (диагноз или тест требует подтверждения другим методом)
   - EXCLUDES (исключает диагноз/лечение)
   - INDICATED_FOR (показано при — связь СТРОГО от DIAGNOSIS к MEDICATION или SURGERY)
   - CONTRAINDICATED_DUE_TO (противопоказано из-за — связь СТРОГО от MEDICATION/SURGERY к PATIENT_PROFILE/DIAGNOSIS/SYMPTOM)

2. Убедитесь, что ВСЕ связи валидны согласно Pydantic валидаторам:
   - Любая связь `INDICATED_FOR` должна вести ТОЛЬКО от узла с категорией DIAGNOSIS к узлам с категорией MEDICATION или SURGERY.
   - Связь `CONTRAINDICATED_DUE_TO` должна идти только от MEDICATION/SURGERY к PATIENT_PROFILE/DIAGNOSIS/SYMPTOM.
   - Убедитесь, что все `source` и `target` соответствуют реальным `id` из списка узлов.
   - Сделайте граф связным и логически полным, переведя оригинальные triplets в этот формат.

ОТВЕТ ДОЛЖЕН БЫТЬ СТРОГО В ФОРМАТЕ JSON:
{{
  "title": "...",
  "case_description": "...",
  "expected_diagnosis": "...",
  "expected_treatment": "...",
  "graph_data": {{
    "nodes": [...],
    "edges": [...]
  }}
}}
"""

async def translate_case(case: Dict[str, Any], index: int) -> Dict[str, Any]:
    print(f"[{index}] Translating case {case.get('index', 'unknown')} ({case.get('answer', 'unknown')})...")
    case_json_str = json.dumps({
        "question": case.get("question"),
        "answer": case.get("answer"),
        "content": case.get("content"),
        "graph": case.get("graph")
    }, ensure_ascii=False)
    
    prompt = TRANSLATE_PROMPT.format(case_json=case_json_str)
    
    # Try calling LLM Router (which will attempt gpt-5-nano or gemini)
    try:
        response_text = await llm_router.chat_completion(prompt)
        
        # Clean response string if LLM returned markdown blocks
        clean_text = response_text.strip()
        if clean_text.startswith("```json"):
            clean_text = clean_text[7:]
        if clean_text.endswith("```"):
            clean_text = clean_text[:-3]
        clean_text = clean_text.strip()
        
        translated_data = json.loads(clean_text)
        return translated_data
    except Exception as e:
        print(f"Error during translation of case {index}: {e}")
        return None

async def find_closest_protocol_id(conn, translated_diagnosis: str) -> int:
    try:
        # Use our embedding service to embed the translated diagnosis
        embedding = await llm_router.get_embedding(translated_diagnosis)
        embedding_str = "[" + ",".join(map(str, embedding)) + "]"
        
        cur = conn.cursor()
        
        # Query protocol_chunks via pgvector Cosine/L2 distance to find closest match
        # '<=>' represents cosine distance, '<->' represents L2 distance. We use cosine distance.
        cur.execute("""
            SELECT protocol_id, 1 - (embedding <=> %s::vector) as similarity
            FROM protocol_chunks
            ORDER BY embedding <=> %s::vector
            LIMIT 1
        """, (embedding_str, embedding_str))
        
        res = cur.fetchone()
        if res:
            protocol_id, similarity = res
            print(f"  Matched to protocol #{protocol_id} with similarity {similarity:.4f}")
            return protocol_id
    except Exception as e:
        print(f"  Error matching protocol by embedding: {e}")
        
    # Fallback to direct keyword search or first protocol
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM clinical_protocols LIMIT 1")
        res = cur.fetchone()
        if res:
            return res[0]
    except Exception as e:
        print(f"  Failed fallback search: {e}")
    return 1

async def main():
    if not os.path.exists(DATA_FILE):
        print(f"Error: Data file not found at {DATA_FILE}")
        return
        
    print(f"Reading examples from {DATA_FILE}...")
    cases = []
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                cases.append(json.loads(line))
                
    print(f"Loaded {len(cases)} cases.")
    
    # Establish connection to DB using psycopg2
    try:
        conn = psycopg2.connect(cleaned_url)
        conn.autocommit = False
        print("Connected to PostgreSQL successfully.")
    except Exception as e:
        print(f"Failed to connect to database: {e}")
        return
        
    # Ensure a default Discipline exists in DB
    discipline_id = 1
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM disciplines WHERE id = 1")
        if not cur.fetchone():
            cur.execute("INSERT INTO disciplines (id, name, code) VALUES (1, 'Клиническая медицина', 'MED-BASE')")
            conn.commit()
            print("Default discipline created.")
    except Exception as e:
        conn.rollback()
        print(f"Error checking/creating discipline: {e}")
        
    success_count = 0
    for idx, case in enumerate(cases):
        translated = await translate_case(case, idx + 1)
        if not translated:
            print(f"Skipping case {idx+1} due to translation failure.")
            continue
            
        try:
            # 1. Match to closest clinical protocol
            protocol_id = await find_closest_protocol_id(conn, translated["expected_diagnosis"])
            
            # 2. Insert into reference_graphs
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO reference_graphs (title, description, graph_data, discipline_id, created_at, updated_at)
                VALUES (%s, %s, %s, %s, NOW(), NOW())
                RETURNING id
            """, (
                translated["title"],
                translated["case_description"],
                json.dumps(translated["graph_data"], ensure_ascii=False),
                discipline_id
            ))
            ref_graph_id = cur.fetchone()[0]
            
            # 3. Insert into assignments
            cur.execute("""
                INSERT INTO assignments (title, description, discipline_id, reference_graph_id, created_at)
                VALUES (%s, %s, %s, %s, NOW())
            """, (
                translated["title"],
                translated["case_description"],
                discipline_id,
                ref_graph_id
            ))
            
            # 4. Insert into student_tasks (RAG Task)
            cur.execute("""
                INSERT INTO student_tasks (protocol_id, case_description, expected_diagnosis, expected_treatment, created_at)
                VALUES (%s, %s, %s, %s, NOW())
            """, (
                protocol_id,
                translated["case_description"],
                translated["expected_diagnosis"],
                translated["expected_treatment"]
            ))
            
            conn.commit()
            print(f"  Successfully seeded ReferenceGraph #{ref_graph_id} and Assignment!")
            success_count += 1
            
        except Exception as e:
            conn.rollback()
            print(f"  Failed to insert case #{idx+1} into DB: {e}")
            
    conn.close()
    print(f"\nCompleted seeding. Successfully imported {success_count} / {len(cases)} cases.")

if __name__ == "__main__":
    asyncio.run(main())
