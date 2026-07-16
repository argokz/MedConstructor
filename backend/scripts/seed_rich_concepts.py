import asyncio
import re
import sys
import os
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import engine
from app.models import ClinicalProtocol, MedicalNode
from app.services.llm_router import llm_router

# Curated high-quality dictionaries for matching
SYMPTOMS_DICT = [
    "боль в животе", "тошнота", "рвота", "лихорадка", "одышка", "кашель", "слабость", "головная боль",
    "диарея", "запор", "желтуха", "зуд кожи", "отеки", "головокружение", "потеря сознания", "судороги",
    "цианоз", "тахикардия", "брадикардия", "артериальная гипертензия", "артериальная гипотензия",
    "анорексия", "дисфагия", "метеоризм", "изжога", "отрыжка", "гематурия", "дизурия", "олигурия",
    "анурия", "полиурия", "кровотечение", "кашель с мокротой", "кровохарканье", "хрипы в легких",
    "боль в грудной клетке", "удушье", "сонливость", "бессонница", "тремор", "парез", "паралич",
    "снижение зрения", "шум в ушах", "боль в суставах", "сыпь", "гиперемия", "бледность кожи",
    "потливость", "озноб", "сухость во рту", "чувство жажды", "онемение конечностей",
    "опоясывающая боль", "тупая боль", "острая боль", "схваткообразная боль", "жжение за грудиной",
    "увеличение лимфоузлов", "боль в горле", "заложенность носа", "чихание", "рвота с кровью",
    "дегтеобразный стул (мелена)", "чувство тяжести в правом подреберье", "мышечная слабость",
    "снижение массы тела", "увеличение живота в объеме"
]

MEDICATIONS_DICT = [
    "Аспирин", "Парацетамол", "Ибупрофен", "Амоксициллин", "Цефтриаксон", "Метронидазол", "Омепразол",
    "Гепарин", "Варфарин", "Клопидогрел", "Аторвастатин", "Лозартан", "Эналаприл", "Каптоприл",
    "Амлодипин", "Бисопролол", "Метопролол", "Амиодарон", "Фуросемид", "Спиронолактон", "Диклофенак",
    "Нимесулид", "Кетопрофен", "Дексаметазон", "Преднизолон", "Спирамицин", "Азитромицин",
    "Ципрофлоксацин", "Левофлоксацин", "Цефазолин", "Амикацин", "Ванкомицин", "Линезолид",
    "Меропенем", "Имипенем", "Флуконазол", "Ацикловир", "Инсулин", "Метформин", "Гликлазид",
    "Ситаглиптин", "Сальбутамол", "Будесонид", "Ипратропия бромид", "Аминофиллин", "Эпинефрин",
    "Атропин", "Димедрол", "Хлоропирамин", "Клемастин", "Дезлоратадин", "Ранитидин", "Фамотидин",
    "Пантопразол", "Эзомепразол", "Висмута трикалия дицитрат", "Кларитромицин", "Альбумин",
    "Декстран", "Натрия хлорид", "Глюкоза", "Калия хлорид", "Магния сульфат", "Кальция глюконат",
    "Морфин", "Фентанил", "Трамадол", "Промедол", "Кетамин", "Пропофол", "Тиопентал натрия",
    "Диазепам", "Мидазолам", "Аминазин", "Галоперидол", "Амитриптилин", "Флуоксетин", "Сертралин",
    "Вальпроевая кислота", "Карбамазепин", "Леветирацетам", "Фенобарбитал", "Леводопа",
    "Пирацетам", "Винпоцетин", "Пентоксифиллин", "Нифедипин", "Верапамил", "Дилтиазем",
    "Нитроглицерин", "Изосорбида динитрат", "Спираприл", "Периндоприл", "Рамиприл", "Лизиноприл",
    "Валсартан", "Кандесартан", "Ирбесартан", "Гидрохлоротиазид", "Торасемид", "Ацетилсалициловая кислота",
    "Ривароксабан", "Апиксабан", "Дабигатран", "Эноксапарин натрия", "Надропарин кальция",
    "Фондапаринукс", "Стрептокиназа", "Альтеплаза", "Тенектеплаза", "Викасол", "Аминокапроновая кислота",
    "Транексамовая кислота", "Фитоменадион", "Сорбифер", "Феррум Лек", "Фолиевая кислота",
    "Цианокобаламин", "Лидокаин", "Прокаин", "Бупивакаин", "Артикаин", "Унитол", "Налоксон",
    "Флумазенил", "Уголь активированный", "Смекта", "Лоперамид", "Мебеверин", "Дротаверин",
    "Папаверин", "Платифиллин", "Метоклопрамид", "Домперидон", "Ондансетрон", "Урсодезоксихолевая кислота",
    "Эссенциале", "Панкреатин", "Сенна", "Лактулоза", "Бисакодил"
]

def clean_disease_name(raw: str) -> str:
    # Remove code blocks like "(M88)" or "(O88.3)"
    name = re.sub(r"\([A-Z][0-9][0-9a-zA-Z.]*\)", "", raw)
    # Remove metadata lines and years
    name = re.sub(r"-\s*\d{4}.*$", "", name)
    name = re.sub(r"\d{4}\s*год.*$", "", name)
    name = name.strip()
    return name

async def main():
    SessionLocal = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    
    async with SessionLocal() as session:
        # 1. Fetch all existing node names to avoid duplicates
        existing_res = await session.execute(select(MedicalNode.name))
        existing_names = {r[0].lower().strip() for r in existing_res.all()}
        
        print(f"Loaded {len(existing_names)} existing concepts in database.")
        
        # 2. Get all protocols and extract diseases
        print("Extracting diseases from protocol titles and MKB classifications...")
        protocols_res = await session.execute(select(ClinicalProtocol))
        protocols = list(protocols_res.scalars().all())
        
        to_add = []
        diseases_found = set()
        
        for p in protocols:
            # Protocol title
            title_clean = clean_disease_name(p.title)
            if title_clean and len(title_clean) > 3:
                diseases_found.add(title_clean)
                
            # MKB categories
            if p.mkb_categories:
                for cat in p.mkb_categories:
                    cat_clean = clean_disease_name(cat)
                    if cat_clean and len(cat_clean) > 3:
                        diseases_found.add(cat_clean)
                        
        print(f"Found {len(diseases_found)} unique candidate diseases.")
        
        # Filter duplicates
        new_diseases = [d for d in diseases_found if d.lower().strip() not in existing_names]
        print(f"Identified {len(new_diseases)} new diseases to seed.")
        
        # 3. Match symptoms and medications in text content
        print("Scanning protocol text contents for common symptoms and medications...")
        
        symptoms_found = set()
        medications_found = set()
        
        # Compile case-insensitive search regexes
        symptom_regexes = {s: re.compile(rf"\b{re.escape(s[:6])}\w*", re.IGNORECASE) for s in SYMPTOMS_DICT}
        med_regexes = {m: re.compile(rf"\b{re.escape(m[:6])}\w*", re.IGNORECASE) for m in MEDICATIONS_DICT}
        
        for p in protocols:
            text = p.text_content or ""
            if not text:
                continue
            
            # Check symptoms
            for s, r in symptom_regexes.items():
                if s.lower().strip() not in existing_names and r.search(text):
                    symptoms_found.add(s)
            
            # Check meds
            for m, r in med_regexes.items():
                if m.lower().strip() not in existing_names and r.search(text):
                    medications_found.add(m)
                    
        print(f"Found {len(symptoms_found)} matched symptoms and {len(medications_found)} matched medications in protocols.")
        
        # Add to seed list
        for d in new_diseases[:300]: # limit batch size for quick seeding
            to_add.append(MedicalNode(name=d, category="disease", source="clinical_protocols"))
            
        for s in symptoms_found:
            to_add.append(MedicalNode(name=s, category="symptom", source="clinical_protocols"))
            
        for m in medications_found:
            to_add.append(MedicalNode(name=m, category="medication", source="clinical_protocols"))
            
        if not to_add:
            print("No new concepts to add.")
            return
            
        print(f"Adding {len(to_add)} concepts to database (without vectorizing first, to run quickly)...")
        session.add_all(to_add)
        await session.commit()
        print("Successfully seeded rich concepts from clinical protocols!")

if __name__ == '__main__':
    asyncio.run(main())
