import sys
import os
import psycopg2
import time

# Ensure UTF-8 output
sys.stdout.reconfigure(encoding='utf-8')

# Add backend directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config import get_settings
from app.services.text_embeddings import encode_texts_sync

def main():
    settings = get_settings()
    if not settings.openai_api_key:
        print("Error: OPENAI_API_KEY is not set in environment or config.")
        sys.exit(1)

    print(f"Using Embedding Model: {settings.embedding_model_name}")
    print(f"Dimension: {settings.embedding_vector_dim}")

    conn = psycopg2.connect(settings.sync_database_url)
    cur = conn.cursor()

    # Find nodes without embeddings
    cur.execute("SELECT id, name, category FROM medical_nodes WHERE embedding IS NULL ORDER BY id")
    nodes = cur.fetchall()
    total = len(nodes)
    print(f"Found {total} medical nodes with NULL embedding.")

    if total == 0:
        print("Nothing to vectorize. Exiting.")
        cur.close()
        conn.close()
        return

    batch_size = 100
    t_start = time.time()

    for i in range(0, total, batch_size):
        batch = nodes[i:i+batch_size]
        batch_ids = [node[0] for node in batch]
        batch_names = [node[1] for node in batch]

        print(f"Vectorizing batch {i//batch_size + 1}/{(total + batch_size - 1)//batch_size} ({len(batch)} nodes)...")
        
        try:
            embeddings = encode_texts_sync(settings, batch_names)
        except Exception as e:
            print(f"  Error generating embeddings: {e}")
            continue

        if len(embeddings) != len(batch):
            print(f"  Warning: Embedding size mismatch! Got {len(embeddings)} vectors for {len(batch)} nodes. Skipping this batch.")
            continue

        for node_id, name, embedding in zip(batch_ids, batch_names, embeddings):
            # Check for NaN or empty embedding
            if not embedding:
                continue
            
            # Format vector as string for pgvector cast
            vec_str = "[" + ",".join(str(v) for v in embedding) + "]"
            
            try:
                cur.execute(
                    "UPDATE medical_nodes SET embedding = %s::vector WHERE id = %s",
                    (vec_str, node_id)
                )
            except Exception as db_err:
                print(f"  Error updating node id {node_id} ({name}): {db_err}")
                conn.rollback()
                break
        else:
            # Commit after a successful batch update
            conn.commit()

        elapsed = time.time() - t_start
        rate = (i + len(batch)) / elapsed if elapsed > 0 else 0
        print(f"  Done. Vectorized {i + len(batch)}/{total} nodes ({rate:.1f} nodes/sec).")

    cur.close()
    conn.close()
    print(f"\nVectorization complete! Total time: {time.time() - t_start:.1f} seconds.")

if __name__ == '__main__':
    main()
