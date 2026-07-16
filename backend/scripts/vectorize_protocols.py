"""
Векторизация клинических протоколов через OpenAI text-embedding-3-small.
Использует семантический чанкинг по заголовкам Markdown для лучшего RAG.
"""
import os
import sys
import time
import psycopg2
import re
from openai import OpenAI

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_text_splitters import RecursiveCharacterTextSplitter
from dotenv import load_dotenv
from app.config import get_settings
load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
EMBEDDING_MODEL = "text-embedding-3-small"
EMBED_BATCH_SIZE = 100

fallback_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1500,
    chunk_overlap=200,
    length_function=len,
)

def semantic_chunking(text_content: str, max_chunk_len: int = 1500) -> list[str]:
    """
    Разбивает Markdown-текст на логические секции по заголовкам (#, ##, ###).
    Добавляет название секции в начало каждого чанка, чтобы эмбеддинг понимал контекст.
    Если секция слишком большая, разбивает её fallback_splitter'ом.
    """
    chunks = []
    # Ищем заголовки Markdown и сплитим по ним
    parts = re.split(r'(?m)^(#{1,6})\s+(.*)$', text_content)
    
    # Если текст не начинается с заголовка, первая часть - введение
    current_section = "Общая информация"
    current_text = parts[0].strip()
    
    if current_text:
        for sub_chunk in fallback_splitter.split_text(current_text):
            chunks.append(f"[Секция: {current_section}]\n{sub_chunk}")
            
    for i in range(1, len(parts), 3):
        header_level = parts[i]
        header_text = parts[i+1].strip()
        section_content = parts[i+2].strip() if i+2 < len(parts) else ""
        
        current_section = header_text
        
        if not section_content:
            continue
            
        for sub_chunk in fallback_splitter.split_text(section_content):
            chunks.append(f"[Секция: {current_section}]\n{sub_chunk}")
            
    return chunks

def get_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """Get embeddings from OpenAI in a single batch call."""
    for attempt in range(3):
        try:
            response = client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=texts
            )
            return [item.embedding for item in response.data]
        except Exception as e:
            err = str(e)
            if "rate" in err.lower() or "429" in err:
                wait = 20 * (attempt + 1)
                print(f"    Rate limit, waiting {wait}s...")
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("Failed after 3 retries")


def main():
    conn = psycopg2.connect(get_settings().sync_database_url)
    cur = conn.cursor()

    cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
    conn.commit()

    # Clear chunks for protocols containing images so they get re-vectorized with new OCR text
    if "--clear" in sys.argv:
        print("Clearing stale chunks for protocols with images...")
        cur.execute("""
            DELETE FROM protocol_chunks 
            WHERE protocol_id IN (
                SELECT id FROM clinical_protocols WHERE text_content LIKE '%![%'
            )
        """)
        conn.commit()
        print("Stale chunks deleted successfully!")
    else:
        print("Resuming vectorization (re-indexing skipped). Pass --clear to force full re-vectorization.")

    cur.execute("""
        SELECT id, title, text_content
        FROM clinical_protocols
        WHERE id NOT IN (SELECT DISTINCT protocol_id FROM protocol_chunks)
        ORDER BY id
    """)
    protocols = cur.fetchall()
    total = len(protocols)
    print(f"Protocols to vectorize: {total}")
    print(f"Model: {EMBEDDING_MODEL} (1536 dims)")

    api_calls = 0
    t_start = time.time()

    for idx, (pid, title, text_content) in enumerate(protocols):
        chunks = semantic_chunking(text_content)
        n_chunks = len(chunks)

        saved = 0
        for batch_start in range(0, n_chunks, EMBED_BATCH_SIZE):
            batch_texts = chunks[batch_start:batch_start + EMBED_BATCH_SIZE]

            try:
                embeddings = get_embeddings_batch(batch_texts)
                api_calls += 1
            except Exception as e:
                print(f"    FAILED batch at chunk {batch_start}: {e}")
                continue

            for j, (chunk_text, embedding) in enumerate(zip(batch_texts, embeddings)):
                chunk_idx = batch_start + j
                vec_str = "[" + ",".join(str(v) for v in embedding) + "]"
                cur.execute(
                    """INSERT INTO protocol_chunks (protocol_id, chunk_index, text_content, embedding)
                       VALUES (%s, %s, %s, %s::vector)""",
                    (pid, chunk_idx, chunk_text, vec_str)
                )
                saved += 1

        conn.commit()
        elapsed = time.time() - t_start
        rate = (idx + 1) / elapsed * 60 if elapsed > 0 else 0
        if (idx + 1) % 50 == 0 or idx == 0:
            print(f"  [{idx+1}/{total}] #{pid} {saved}/{n_chunks} chunks | calls: {api_calls} | {rate:.0f} prot/min")

    cur.close()
    conn.close()
    print(f"\nDone! {total} protocols, {api_calls} API calls, {time.time() - t_start:.0f}s")


if __name__ == "__main__":
    main()
