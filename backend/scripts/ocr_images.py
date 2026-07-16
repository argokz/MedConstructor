import asyncio
import os
import sys
import re
import httpx
import base64
from io import BytesIO
from PIL import Image
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from openai import AsyncOpenAI

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.models import ClinicalProtocol
from app.config import get_settings

settings = get_settings()

client = AsyncOpenAI(api_key=settings.openai_api_key)

async def fetch_image(http_client, url):
    try:
        r = await http_client.get(url, timeout=20.0)
        r.raise_for_status()
        return r.content
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return None

async def ocr_image(image_bytes):
    try:
        # Load image with PIL to verify and compress if needed
        image = Image.open(BytesIO(image_bytes))
        if image.mode != 'RGB':
            image = image.convert('RGB')
            
        # Convert back to jpeg bytes to pass as base64
        buffered = BytesIO()
        image.save(buffered, format="JPEG")
        img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
        
        prompt = "Внимательно изучи это изображение. Если это таблица, переведи её в строгую Markdown-таблицу. Если это текст, просто распознай его. Выведи ТОЛЬКО результат в формате Markdown без лишних слов."
        
        response = await client.chat.completions.create(
            model=settings.openai_models.split(",")[0].strip(),
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{img_str}"
                            }
                        }
                    ]
                }
            ],
            max_completion_tokens=1500
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error in OCR: {e}")
        return None

async def process_protocol(session, protocol, http_client):
    matches = list(re.finditer(r'!\[.*?\]\((.*?)\)', protocol.text_content))
    if not matches:
        return False
        
    updated = False
    new_text = protocol.text_content
    
    # Process from bottom to top so indices don't shift
    for match in reversed(matches):
        full_match = match.group(0)
        url_raw = match.group(1)
        url = url_raw.split(" ")[0].strip()
        
        # Ignore empty urls, small icons, gifs, logos
        if not url or "ajax-loader" in url or "logo" in url or url.endswith(".gif") or url.endswith(".svg"):
            continue
            
        print(f"  Found image: {url}")
        
        # Skip if already OCR'd right below it (making sure not to look past a subsequent image)
        lookahead = new_text[match.end():match.end()+200]
        ocr_idx = lookahead.find("Распознанный текст")
        next_img_idx = lookahead.find("![")
        if ocr_idx != -1 and (next_img_idx == -1 or ocr_idx < next_img_idx):
            print("  Already OCR'd, skipping.")
            continue
            
        img_bytes = await fetch_image(http_client, url)
        if img_bytes:
            print("  Running OCR via OpenAI...")
            ocr_text = await ocr_image(img_bytes)
            
            if ocr_text:
                print("  Success OCR.")
                insertion = f"\n\n<details><summary>Распознанный текст (для ИИ)</summary>\n\n{ocr_text}\n\n</details>\n\n"
                new_text = new_text[:match.end()] + insertion + new_text[match.end():]
                updated = True
                
    if updated:
        protocol.text_content = new_text
        return True
    return False

async def main():
    engine = create_async_engine(settings.database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        query = select(ClinicalProtocol).where(ClinicalProtocol.text_content.like('%![%](%')).order_by(ClinicalProtocol.id)
        if len(sys.argv) > 1 and sys.argv[1] == '--test':
            query = query.limit(2)
            
        result = await session.execute(query)
        protocols = result.scalars().all()
        
        print(f"Found {len(protocols)} protocols with images.")
        
        async with httpx.AsyncClient() as http_client:
            for p in protocols:
                try:
                    print(f"Processing ID: {p.id} | {p.title}".encode('cp1251', errors='replace').decode('cp1251'))
                except:
                    pass
                changed = await process_protocol(session, p, http_client)
                if changed:
                    await session.commit()
                    print(f"  [Saved ID {p.id}]")

if __name__ == "__main__":
    asyncio.run(main())
