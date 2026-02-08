import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from app.db.mongodb import db_manager
from app.services.ocr_registry_service import ocr_registry_service

logger = logging.getLogger("app.services.ocr_candidate")

class OcrCandidateService:
    def __init__(self):
        # Thresholds for candidate generation
        self.min_verified_frequency = 8
        self.min_verified_book_span = 1
        self.max_suspect_frequency = 5
        self.max_suspect_book_span = 1

    def levenshtein_distance(self, s1: str, s2: str) -> int:
        """Standard Levenshtein distance implementation."""
        if len(s1) < len(s2):
            return self.levenshtein_distance(s2, s1)
        if len(s2) == 0:
            return len(s1)
        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
        return previous_row[-1]

    async def identify_candidates(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Scans suspects and identifies correction candidates using fuzzy matching.
        """
        db = db_manager.db
        if db is None:
            raise RuntimeError("Database not connected")

        # 1. Fetch potential suspects
        suspects_cursor = db.ocr_vocabulary.find({
            "status": "suspect",
            "frequency": {"$lte": self.max_suspect_frequency},
            "bookSpan": {"$lte": self.max_suspect_book_span},
            "manualOverride": {"$ne": True}
        }).sort("frequency", -1).limit(limit)

        suspects = await suspects_cursor.to_list(limit)
        if not suspects:
            return []

        # 2. Fetch verified words for comparison
        # We fetch words that are broadly accepted as "correct"
        verified_cursor = db.ocr_vocabulary.find({
            "status": "verified",
            "frequency": {"$gte": self.min_verified_frequency},
            "bookSpan": {"$gte": self.min_verified_book_span}
        }).sort("frequency", -1)
        
        verified_words = await verified_cursor.to_list(20000)
        verified_stems = {v["token"] for v in verified_words}

        results = []
        for suspect in suspects:
            token = suspect["token"]
            
            # Skip if purely numeric (Feedback: reduces false positives in registry)
            if token.isdigit() or re.match(r'^\d+$', token):
                continue
                
            # Skip if it's a valid agglutination (Feedback A)
            if ocr_registry_service.is_valid_agglutination(token, verified_stems):
                await db.ocr_vocabulary.update_one(
                    {"token": token},
                    {"$set": {"status": "verified", "flags": ["agglutination"]}}
                )
                continue

            candidates = []
            for verified in verified_words:
                v_token = verified["token"]
                
                # Length filter for performance
                if abs(len(token) - len(v_token)) > 1:
                    continue
                
                # Fuzzy match
                dist = self.levenshtein_distance(token, v_token)
                if dist <= 1: # Start with edit distance 1 for high precision
                    confidence = self.calculate_confidence(suspect, verified, dist)
                    candidates.append({
                        "token": v_token,
                        "frequency": verified["frequency"],
                        "bookSpan": verified["bookSpan"],
                        "confidence": confidence,
                        "distance": dist
                    })

            if candidates:
                # Sort by confidence descending
                candidates.sort(key=lambda x: x["confidence"], reverse=True)
                
                # Update the suspect entry in DB
                await db.ocr_vocabulary.update_one(
                    {"token": token},
                    {"$set": {
                        "candidates": candidates,
                        "lastSeenAt": datetime.utcnow()
                    }}
                )
                
                # Prepare result for return
                clean_suspect = {
                    "token": suspect["token"],
                    "frequency": suspect["frequency"],
                    "bookSpan": suspect["bookSpan"],
                    "candidates": candidates[:5] # Top 5 only
                }
                results.append(clean_suspect)

        return results

    def calculate_confidence(self, suspect: Dict, verified: Dict, distance: int) -> float:
        """
        Weights multiple signals to determine confidence in a correction.
        """
        # Signal 1: Frequency Ratio (log scale or saturated)
        # If verified is 100x more common, it's a strong signal
        freq_ratio = min(verified["frequency"] / max(suspect["frequency"], 1), 50) / 50
        
        # Signal 2: Spread (more books = more trust)
        spread_score = min(verified["bookSpan"], 10) / 10
        
        # Signal 3: OCR Confusion Bonus
        # Specific Uyghur/Arabic character visual confusions
        ocr_bonus = 0.0
        s_text = suspect["token"]
        v_text = verified["token"]
        
        confusion_pairs = [
            ('ۆ', 'ۇ'), ('ۇ', 'ۆ'),
            ('ې', 'ە'), ('ە', 'ې'),
            ('ى', 'ي'), ('ي', 'ى'),
            ('ئا', 'ا'), ('ا', 'ئا')
        ]
        
        for c1, c2 in confusion_pairs:
            if c1 in s_text and c2 in v_text:
                ocr_bonus = 0.5
                break

        # Weighted calculation
        # distance=1 -> 1.0, distance=2 -> 0.5 (if we enabled it)
        dist_factor = 1.0 if distance == 1 else 0.4
        
        score = (
            freq_ratio * 0.3 + 
            spread_score * 0.3 + 
            dist_factor * 0.2 + 
            ocr_bonus * 0.2
        )
        
        return round(score, 3)

ocr_candidate_service = OcrCandidateService()
