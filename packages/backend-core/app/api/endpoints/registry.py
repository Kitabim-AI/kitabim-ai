from fastapi import APIRouter, Depends, HTTPException
from app.services.ocr_registry_service import ocr_registry_service
from app.services.ocr_candidate_service import ocr_candidate_service
from app.db.mongodb import get_db
from datetime import datetime
import logging

router = APIRouter()
logger = logging.getLogger("app.api.registry")

@router.post("/rebuild")
async def rebuild_registry():
    """
    Triggers a full corpus scan to rebuild the vocabulary registry.
    This is a long-running operation.
    """
    # In a production environment, this should be a background task via ARQ
    # For now, we'll run it directly as a proof of concept
    return await ocr_registry_service.rebuild_registry()

@router.get("/stats")
async def get_registry_stats(db=Depends(get_db)):
    """
    Returns statistics about the vocabulary registry.
    """
    try:
        total_tokens = await db.ocr_vocabulary.count_documents({})
        verified_tokens = await db.ocr_vocabulary.count_documents({"status": "verified"})
        suspect_tokens = await db.ocr_vocabulary.count_documents({"status": "suspect"})
        correction_count = await db.ocr_vocabulary.count_documents({"status": "corrected"})
        
        return {
            "total_tokens": total_tokens,
            "verified_tokens": verified_tokens,
            "suspect_tokens": suspect_tokens,
            "corrected_tokens": correction_count,
            "health_score": round((verified_tokens / total_tokens * 100), 2) if total_tokens > 0 else 0
        }
    except Exception as e:
        logger.exception("Failed to get registry stats")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tokens")
async def list_tokens(
    status: str = "suspect", 
    limit: int = 100, 
    min_frequency: int = 1,
    db=Depends(get_db)
):
    """
    Lists tokens from the registry filtered by status.
    """
    cursor = db.ocr_vocabulary.find({
        "status": status,
        "frequency": {"$gte": min_frequency}
    }).sort("frequency", -1).limit(limit)
    
    tokens = await cursor.to_list(limit)
    # Convert ObjectId if any
    for t in tokens:
        if "_id" in t:
            t["_id"] = str(t["_id"])
    return tokens

@router.post("/generate-candidates")
async def generate_candidates(limit: int = 50):
    """
    Scans suspects and generates correction candidates.
    """
    return await ocr_candidate_service.identify_candidates(limit=limit)

@router.get("/candidates")
async def get_candidates(
    min_confidence: float = 0.7, 
    limit: int = 50, 
    db=Depends(get_db)
):
    """
    Returns identified suspects with their best correction candidates.
    """
    cursor = db.ocr_vocabulary.find({
        "status": "suspect",
        "candidates": {"$exists": True, "$ne": []}
    }).sort("candidates.0.confidence", -1).limit(limit)
    
    results = await cursor.to_list(limit)
    for r in results:
        if "_id" in r:
            r["_id"] = str(r["_id"])
            
        # Filter candidates by confidence if requested
        if min_confidence > 0:
            r["candidates"] = [c for c in r["candidates"] if c["confidence"] >= min_confidence]
            
    # Remove entries that have no candidates after filtering
    results = [r for r in results if r["candidates"]]
    
    return results

@router.get("/context")
async def get_token_context(token: str, limit: int = 5):
    """
    Returns real-world snippets of where a token appears in the corpus.
    """
    if not token:
        raise HTTPException(status_code=400, detail="Token is required")
    return await ocr_registry_service.get_token_context(token, limit=limit)

@router.post("/verify")
async def verify_token(token: str, db=Depends(get_db)):
    """
    Manually marks a suspect token as verified (correct).
    """
    if not token:
        raise HTTPException(status_code=400, detail="Token is required")
    
    result = await db.ocr_vocabulary.update_one(
        {"token": token},
        {"$set": {
            "status": "verified",
            "manualOverride": True,
            "verifiedAt": datetime.utcnow()
        }}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Token not found")
        
@router.post("/correct")
async def apply_correction(token: str, correction: str):
    """
    Applies a global correction for a token across the entire corpus.
    """
    if not token or not correction:
        raise HTTPException(status_code=400, detail="Token and correction are required")
        
    return await ocr_registry_service.apply_global_correction(token, correction)
