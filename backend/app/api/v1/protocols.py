from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, distinct
from typing import List, Optional

from app.api.deps import get_db
from app.models import ClinicalProtocol
from app.schemas import ProtocolListResponse, ClinicalProtocolDetail

router = APIRouter(prefix="/protocols", tags=["protocols"])

@router.get("/sections", response_model=List[str])
async def get_sections(db: AsyncSession = Depends(get_db)):
    """
    Get a list of all unique medical sections from the protocols.
    """
    # Use unnest to get distinct elements from the array
    query = select(func.unnest(ClinicalProtocol.medical_sections).label("section")).distinct().order_by("section")
    result = await db.execute(query)
    sections = [row[0] for row in result.all() if row[0]]
    return sections

@router.get("", response_model=ProtocolListResponse)
async def list_protocols(
    section: Optional[str] = None,
    q: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=5000),
    db: AsyncSession = Depends(get_db)
):
    """
    List protocols with optional filtering by section and search query.
    """
    query = select(ClinicalProtocol)
    
    if section:
        query = query.where(ClinicalProtocol.medical_sections.any(section))
        
    if q:
        query = query.where(ClinicalProtocol.title.ilike(f"%{q}%"))
        
    # Count total items
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    
    # Get paginated items
    query = query.order_by(ClinicalProtocol.id).offset(skip).limit(limit)
    result = await db.execute(query)
    items = result.scalars().all()
    
    return ProtocolListResponse(items=items, total=total)

@router.get("/{protocol_id}", response_model=ClinicalProtocolDetail)
async def get_protocol(protocol_id: int, db: AsyncSession = Depends(get_db)):
    """
    Get protocol detail by ID.
    """
    protocol = await db.get(ClinicalProtocol, protocol_id)
    if not protocol:
        raise HTTPException(status_code=404, detail="Protocol not found")
    return protocol
