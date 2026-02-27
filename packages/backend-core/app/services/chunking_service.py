from typing import List, Optional, Callable
import re
from app.core.config import settings

class RecursiveCharacterTextSplitter:
    def __init__(
        self,
        chunk_size: int = 4000,
        chunk_overlap: int = 200,
        length_function: Callable[[str], int] = len,
        separators: Optional[List[str]] = None,
    ):
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._length_function = length_function
        self._separators = separators or ["\n\n", "\n", " ", ""]

    def split_text(self, text: str) -> List[str]:
        final_chunks = []
        
        # Split text using the first separator that works
        separator = self._separators[-1]
        for _s in self._separators:
            if _s == "":
                separator = _s
                break
            if _s in text:
                separator = _s
                break
                
        # Now split
        if separator:
            splits = text.split(separator)
        else:
            splits = list(text) # Split by char

        # Now merge
        _good_splits = []
        _separator = separator if separator else ""
        
        for s in splits:
            if self._length_function(s) < self._chunk_size:
                _good_splits.append(s)
            else:
                if _good_splits:
                    final_chunks.extend(self._merge_splits(_good_splits, _separator))
                    _good_splits = []
                # Recursively split long chunks
                if not self._separators: 
                    final_chunks.append(s[:self._chunk_size]) # fallback
                else:
                    # Find next separator index
                    try:
                        idx = self._separators.index(separator)
                        next_separators = self._separators[idx+1:]
                    except ValueError:
                        next_separators = []
                        
                    if next_separators:
                        sub_splitter = RecursiveCharacterTextSplitter(
                            chunk_size=self._chunk_size,
                            chunk_overlap=self._chunk_overlap,
                            length_function=self._length_function,
                            separators=next_separators
                        )
                        final_chunks.extend(sub_splitter.split_text(s))
                    else:
                        # logical end
                        final_chunks.append(s[:self._chunk_size])

        if _good_splits:
            final_chunks.extend(self._merge_splits(_good_splits, _separator))
            
        return final_chunks

    def _merge_splits(self, splits: List[str], separator: str) -> List[str]:
        separator_len = self._length_function(separator)
        docs = []
        current_doc: List[str] = []
        total = 0
        for d in splits:
            _len = self._length_function(d)
            if total + _len + (separator_len if current_doc else 0) > self._chunk_size:
                if total > self._chunk_size:
                    # Warning: chunk larger than size
                    pass
                if current_doc:
                    doc = separator.join(current_doc)
                    if doc:
                        docs.append(doc)
                    
                    # Handle overlap
                    while total > self._chunk_overlap or (total + _len + (separator_len if current_doc else 0) > self._chunk_size and total > 0):
                        total -= self._length_function(current_doc[0]) + (separator_len if len(current_doc) > 1 else 0)
                        current_doc.pop(0)

            current_doc.append(d)
            total += _len + (separator_len if len(current_doc) > 1 else 0)
            
        doc = separator.join(current_doc)
        if doc:
            docs.append(doc)
        return docs


class ChunkingService:
    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200):
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
            length_function=len,
        )

    def split_text(self, text: str) -> List[str]:
        if not text:
            return []
        return self.text_splitter.split_text(text)

chunking_service = ChunkingService(chunk_size=settings.chunk_size, chunk_overlap=settings.chunk_overlap)
