import logging
import unicodedata
import re
import asyncio
from datetime import datetime
from typing import List, Dict, Any, Optional

from app.db.mongodb import db_manager
from app.models.schemas import OcrVocabulary, RawVariant
from app.utils.markdown import strip_markdown
from app.utils.observability import log_json

logger = logging.getLogger("app.services.ocr_registry")

class OcrRegistryService:
    def __init__(self):
        self.uyghur_suffixes = [
            # Case and Plural
            'لار', 'لەر', 'نى', 'نىڭ', 'دا', 'دە', 'دىن', 'تىن', 
            'غا', 'گە', 'قا', 'كە',
            # Possessive
            'ىم', 'ىڭ', 'ى', 'سى', 'ىمىز', 'ىڭىز', 'ىڭلار', 'لارى', 'لىرى',
            # Derivational / Ordinal
            'چى', 'چە', 'لىق', 'لىك', 'سىز', 'لۇق', 'لۈك', 'داش', 'نچى', 'ىنچى',
            # Tense / Aspect
            'غان', 'گەن', 'قان', 'كەن', 'ىپ', 'ۇپ', 'ۈپ', 'مەك', 'ماق', 'ىدۇ', 'ەيدۇ'
        ]
        self.common_fragments = [
            'نچى', 'ىنچى', 'لار', 'لەر', 'نى', 'نىڭ', 'دا', 'دە', 'دىن', 'تىن',
            'لىق', 'لىك', 'چى', 'چە', 'سىز', 'لۇق', 'لۈك'
        ]

    def normalize_token(self, token: str) -> str:
        """
        Applies Unicode NFKC normalization and cleans the token.
        Preserves Uyghur/Arabic characters and word characters.
        """
        if not token:
            return ""
        
        # 1. NFKC Normalization (Feedback B)
        normalized = unicodedata.normalize('NFKC', token)
        
        # 2. Remove non-word characters (punctuation, etc.)
        # \w in Python 3 with Unicode matches letters and numbers across scripts
        normalized = re.sub(r'[^\w]', '', normalized)
        
        # 3. Basic case folding (though not applicable to Arabic script, good for mixed text)
        return normalized.strip()

    async def rebuild_registry(self) -> Dict[str, Any]:
        """
        Performs a full corpus scan using high-speed MongoDB aggregation. (Feedback C)
        """
        db = db_manager.db
        if db is None:
            raise RuntimeError("Database not connected")

        logger.info("Starting full corpus vocabulary aggregation...")
        start_time = datetime.utcnow()

        # Step 1: Aggregate raw tokens across all pages
        # We split by whitespace and other common delimiters
        pipeline = [
            # Only process pages with text
            {"$match": {"text": {"$exists": True, "$ne": ""}}},
            
            # Split content into words (Handles newlines and punctuation)
            {"$project": {
                "bookId": 1,
                "text_clean": {
                    "$trim": {
                        "input": {
                            "$replaceAll": {
                                "input": {
                                    "$replaceAll": {
                                        "input": {
                                            "$replaceAll": {
                                                "input": "$text",
                                                "find": "\n",
                                                "replacement": " "
                                            }
                                        },
                                        "find": ".",
                                        "replacement": " "
                                    }
                                },
                                "find": ",",
                                "replacement": " "
                            }
                        }
                    }
                }
            }},
            {"$project": {
                "bookId": 1,
                "words": {"$split": ["$text_clean", " "]}
            }},
            
            # Deconstruct the words array
            {"$unwind": "$words"},
            
            # Basic cleanup in DB to reduce Python overhead
            {"$project": {
                "bookId": 1,
                "word": {"$trim": {"input": "$words"}}
            }},
            
            # Group by raw word and book
            {"$group": {
                "_id": {"word": "$word", "bookId": "$bookId"},
                "count": {"$sum": 1}
            }},
            
            # Final grouping to get global stats
            {"$group": {
                "_id": "$_id.word",
                "frequency": {"$sum": "$count"},
                "bookIds": {"$addToSet": "$_id.bookId"},
                "rawVariants": {"$push": {"token": "$_id.word", "count": "$count"}}
            }},
            
            # Output to temporary collection
            {"$out": "temp_raw_vocabulary"}
        ]

        try:
            await db.pages.aggregate(pipeline).to_list(None)
            
            # Step 2: Process raw tokens with NFKC and merge
            # This handles the "Kitabim Consensus" by merging variants
            logger.info("Raw aggregation complete. Normalizing and merging tokens...")
            
            cursor = db.temp_raw_vocabulary.find()
            batch = []
            processed_count = 0
            
            async for raw in cursor:
                raw_word = raw["_id"]
                if not raw_word or len(raw_word) < 2:
                    continue
                
                normalized = self.normalize_token(raw_word)
                if not normalized or len(normalized) < 2:
                    continue
                
                # Use a bulk operation to merge variants
                # If the token is already verified or ignored, we don't want to downgrade it
                from pymongo import UpdateOne
                
                # Determine status based on book spread OR frequency (Feedback: reduce false suspects)
                is_verified = len(raw["bookIds"]) > 1 or raw["frequency"] >= 8
                
                if normalized in self.common_fragments:
                    new_status = "verified" # Trust common fragments even if split
                elif is_verified:
                    new_status = "verified"
                else: 
                    new_status = "suspect"
                
                batch.append(UpdateOne(
                    {"token": normalized},
                    [
                        {
                            "$set": {
                                "frequency": {"$add": [{"$ifNull": ["$frequency", 0]}, raw["frequency"]]},
                                "bookIds": {"$setUnion": [{"$ifNull": ["$bookIds", []]}, raw["bookIds"]]},
                                "lastSeenAt": datetime.utcnow(),
                                # Preserve raw variants
                                "rawVariants": {"$concatArrays": [{"$ifNull": ["$rawVariants", []]}, raw["rawVariants"]]},
                                # Only update status if manualOverride is not set
                                "status": {
                                    "$cond": {
                                        "if": {"$eq": ["$manualOverride", True]},
                                        "then": "$status",
                                        "else": {
                                            "$cond": {
                                                "if": {
                                                    "$or": [
                                                        {"$eq": ["$status", "verified"]},
                                                        {"$eq": [new_status, "verified"]}
                                                    ]
                                                },
                                                "then": "verified",
                                                "else": "suspect"
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    ],
                    upsert=True
                ))
                
                if len(batch) >= 500:
                    await db.ocr_vocabulary.bulk_write(batch, ordered=False)
                    processed_count += len(batch)
                    logger.info(f"Processed {processed_count} tokens...")
                    batch = []

            if batch:
                await db.ocr_vocabulary.bulk_write(batch, ordered=False)
                processed_count += len(batch)

            # Calculate bookSpan (Feeedback A)
            await db.ocr_vocabulary.update_many(
                {},
                [{"$set": {"bookSpan": {"$size": "$bookIds"}}}]
            )

            # Cleanup
            await db.temp_raw_vocabulary.drop()
            
            duration = (datetime.utcnow() - start_time).total_seconds()
            logger.info(f"Registry rebuild complete in {duration}s. Processed {processed_count} tokens.")

            return {
                "status": "success",
                "duration_seconds": duration,
                "tokens_processed": processed_count
            }

        except Exception as e:
            logger.exception("Failed to rebuild registry")
            return {"status": "error", "message": str(e)}

    def is_valid_agglutination(self, token: str, verified_stems: set) -> bool:
        """
        Linguistic heuristic for Uyghur suffixes.
        Includes basic support for vowel narrowing (e.g., mektep -> mektipi).
        """
        for suffix in self.uyghur_suffixes:
            if token.endswith(suffix):
                stem = token[:-len(suffix)]
                
                # Exact match
                if stem in verified_stems:
                    return True
                
                # Handle vowel narrowing (e.g. e/a -> i)
                # If stem ends in 'i', it might be a narrowed 'e' or 'a'
                if stem.endswith('ى'):
                    # Try replacing last 'i' (\u0649) with 'e' (\u06ە) or 'a' (\u0627)
                    if (stem[:-1] + 'ە') in verified_stems or (stem[:-1] + 'ا') in verified_stems:
                        return True
        return False

    async def get_token_context(self, token: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Retrieves real-world snippets of where a token appears in the corpus. (Feedback D)
        """
        db = db_manager.db
        
        # 1. Locate the token in the registry to find book context and raw variants
        vocab = await db.ocr_vocabulary.find_one({"token": token})
        
        # Build a list of search strings: the token itself and all its raw variants
        search_variants = {token}
        if vocab and vocab.get("rawVariants"):
            for v in vocab["rawVariants"]:
                if v.get("token"):
                    search_variants.add(v["token"])
        
        # Create a regex to find any of these variants in the text
        # Sorted by length descending to match longest possible variant first
        sorted_variants = sorted(list(search_variants), key=len, reverse=True)
        search_pattern = "|".join([re.escape(v) for v in sorted_variants])
        
        query = {"text": {"$regex": search_pattern}}
        if vocab and vocab.get("bookIds"):
            query["bookId"] = {"$in": vocab["bookIds"]}

        # 2. Find pages containing any of these variants
        cursor = db.pages.find(query).limit(limit)
        pages = await cursor.to_list(limit)

        # 3. Enhance with book titles and volumes
        from bson import ObjectId
        
        book_ids = list(set(p["bookId"] for p in pages))
        
        # We search by both 'id' field (common linkage) and '_id' (just in case)
        query_ids = []
        for bid in book_ids:
            try:
                if isinstance(bid, str) and len(bid) == 24: # Likely ObjectId string
                    query_ids.append(ObjectId(bid))
            except:
                pass
        
        # Build map with priority for 'id' matching as it's the primary linkage in this app
        books_map = {}
        
        # Query by 'id' field
        async for b in db.books.find({"id": {"$in": book_ids}}):
            books_map[str(b.get("id"))] = {
                "title": b.get("title", "Unknown Book"),
                "volume": b.get("volume")
            }
            
        # Also query by '_id' if we have potential ObjectIds
        if query_ids:
            async for b in db.books.find({"_id": {"$in": query_ids}}):
                books_map[str(b.get("_id"))] = {
                    "title": b.get("title", "Unknown Book"),
                    "volume": b.get("volume")
                }

        results = []
        re_pattern = re.compile(search_pattern)
        
        for page in pages:
            text = page.get("text", "")
            # Use regex search to find the actual variant and its position
            match = re_pattern.search(text)
            if match:
                idx = match.start()
                matched_text = match.group()
                
                # Find the boundaries of the paragraph (separated by double newline or start/end of text)
                p_start = text.rfind("\n\n", 0, idx)
                p_start = p_start + 2 if p_start != -1 else 0
                
                p_end = text.find("\n\n", idx)
                p_end = p_end if p_end != -1 else len(text)
                
                snippet = text[p_start:p_end].strip()
                
                bid_str = str(page["bookId"])
                book_info = books_map.get(bid_str, {})
                
                results.append({
                    "bookTitle": book_info.get("title", "Unknown"),
                    "bookId": bid_str,
                    "volume": book_info.get("volume"),
                    "pageNumber": page.get("pageNumber"),
                    "snippet": snippet,
                    "matchedToken": matched_text # Crucial for accurate UI highlighting
                })
        
        return results

    async def apply_global_correction(self, target: str, replacement: str) -> Dict[str, Any]:
        """
        Performs a full corpus search and replace for a specific string. (Feedback: handles split suffixes)
        """
        db = db_manager.db
        if db is None:
            raise RuntimeError("Database not connected")
            
        logger.info(f"Applying global correction: '{target}' -> '{replacement}'")
        
        # 1. Update pages
        # We find pages containing the target string
        cursor = db.pages.find({"text": {"$regex": re.escape(target)}})
        pages_to_update = await cursor.to_list(None)
        
        updated_count = 0
        from pymongo import UpdateOne
        batch = []
        
        for page in pages_to_update:
            old_text = page.get("text", "")
            new_text = old_text.replace(target, replacement)
            
            if old_text != new_text:
                batch.append(UpdateOne(
                    {"_id": page["_id"]},
                    {
                        "$set": {
                            "text": new_text, 
                            "lastUpdated": datetime.utcnow()
                        }, 
                        "$unset": {"embedding": ""} # Invalidate RAG embedding
                    }
                ))
                updated_count += 1
            
            if len(batch) >= 500:
                await db.pages.bulk_write(batch, ordered=False)
                batch = []
        
        if batch:
            await db.pages.bulk_write(batch, ordered=False)

        # 2. Record in history
        await db.ocr_correction_history.insert_one({
            "type": "global_replace",
            "target": target,
            "replacement": replacement,
            "pagesAffected": updated_count,
            "appliedAt": datetime.utcnow()
        })
        
        # 3. Mark token as corrected in registry if it exists
        await db.ocr_vocabulary.update_one(
            {"token": target},
            {"$set": {"status": "corrected", "lastCorrection": replacement, "correctedAt": datetime.utcnow()}}
        )
        
        return {
            "status": "success",
            "pages_updated": updated_count,
            "target": target,
            "replacement": replacement
        }

ocr_registry_service = OcrRegistryService()
