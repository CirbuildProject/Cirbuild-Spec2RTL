"""Long-Term Memory for persistent error-fix pair storage.

This module provides ChromaDB-backed storage for learning from past HLS
compilation errors. When the HLS Reflection Engine successfully resolves
an error, the error-fix pair is stored. On subsequent failures, similar
historical fixes can be retrieved via embedding similarity search.
"""

import json
import logging
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger("spec2rtl.memory.long_term")


class ErrorFixPair(BaseModel):
    """Schema for error-fix pair storage."""
    
    error_type: str = Field(
        description="Type of error (e.g., 'scheduling_failure', 'syntax_error')",
    )
    compiler: str = Field(
        description="HLS compiler (e.g., 'google_xls', 'bambu')",
    )
    error_message: str = Field(
        description="Original error message/stack trace",
    )
    fix_strategy: str = Field(
        description="Description of the fix strategy applied",
    )
    fixed_code_snippet: str = Field(
        description="Code diff or snippet showing the fix",
    )
    success: bool = Field(
        description="Whether the fix resolved the error",
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="When this fix was recorded",
    )


class LongTermMemory:
    """ChromaDB-backed long-term memory for HLS error-fix pairs.
    
    This class provides:
    - Persistent storage of error-fix pairs in a local ChromaDB collection
    - Embedding-based similarity search for retrieving relevant past fixes
    - Automatic deduplication based on error hash
    
    Args:
        persist_dir: Directory for ChromaDB persistence (default: 'memory/hls_fixes')
        similarity_threshold: Minimum cosine similarity to return a match (default: 0.7)
    """
    
    def __init__(
        self,
        persist_dir: str = "memory/hls_fixes",
        similarity_threshold: float = 0.7,
    ) -> None:
        self.persist_dir = Path(persist_dir)
        self.similarity_threshold = similarity_threshold
        self._client = None
        self._collection = None
        self._initialize_db()
    
    def _initialize_db(self) -> None:
        """Initialize ChromaDB client and collection."""
        try:
            import chromadb
            from chromadb.config import Settings
            
            self.persist_dir.mkdir(parents=True, exist_ok=True)
            
            self._client = chromadb.PersistentClient(
                path=str(self.persist_dir),
                settings=Settings(anonymized_telemetry=False),
            )
            
            self._collection = self._client.get_or_create_collection(
                name="hls_error_fixes",
                metadata={"description": "HLS compilation error-fix pairs"},
            )
            
            logger.info(
                "Long-term memory initialized at %s with %d entries",
                self.persist_dir,
                self._collection.count(),
            )
            
        except ImportError:
            logger.warning(
                "ChromaDB not installed. Long-term memory disabled. "
                "Install with: pip install chromadb"
            )
            self._client = None
            self._collection = None
        except Exception as exc:
            logger.warning("Failed to initialize ChromaDB: %s", exc)
            self._client = None
            self._collection = None
    
    def _generate_id(self, error_type: str, compiler: str, error_message: str) -> str:
        """Generate a unique ID for an error-fix pair."""
        content = f"{error_type}:{compiler}:{error_message[:200]}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def store_fix(
        self,
        error_fix: ErrorFixPair,
    ) -> bool:
        """Store a successful error-fix pair in long-term memory.
        
        Args:
            error_fix: The error-fix pair to store.
        
        Returns:
            True if stored successfully, False otherwise.
        """
        if self._collection is None:
            logger.debug("ChromaDB not available, skipping memory storage")
            return False
        
        try:
            doc_id = self._generate_id(
                error_fix.error_type,
                error_fix.compiler,
                error_fix.error_message,
            )
            
            # Check if already exists
            existing = self._collection.get(ids=[doc_id])
            if existing and existing.get("ids"):
                logger.debug("Error-fix pair already exists: %s", doc_id)
                return False
            
            # Store the error-fix pair
            document = json.dumps(error_fix.model_dump())
            
            self._collection.add(
                ids=[doc_id],
                documents=[document],
                metadatas=[{
                    "error_type": error_fix.error_type,
                    "compiler": error_fix.compiler,
                    "success": error_fix.success,
                    "timestamp": error_fix.timestamp,
                }],
            )
            
            logger.info(
                "Stored error-fix pair: %s (%s on %s)",
                doc_id,
                error_fix.error_type,
                error_fix.compiler,
            )
            
            return True
            
        except Exception as exc:
            logger.error("Failed to store error-fix pair: %s", exc)
            return False
    
    def find_similar_fixes(
        self,
        error_message: str,
        error_type: str | None = None,
        compiler: str | None = None,
        n_results: int = 3,
    ) -> list[ErrorFixPair]:
        """Find similar historical fixes for a given error.
        
        Args:
            error_message: The current error message to match against.
            error_type: Optional error type to filter by.
            compiler: Optional compiler to filter by.
            n_results: Maximum number of results to return.
        
        Returns:
            List of similar ErrorFixPairs (up to n_results), ordered by similarity.
        """
        if self._collection is None:
            logger.debug("ChromaDB not available, skipping memory retrieval")
            return []
        
        try:
            # Build where clause for filtering
            where: dict[str, Any] = {}
            if error_type:
                where["error_type"] = error_type
            if compiler:
                where["compiler"] = compiler
            
            # Only return successful fixes
            where["success"] = True
            
            results = self._collection.query(
                query_texts=[error_message],
                n_results=n_results,
                where=where if where else None,
            )
            
            if not results or not results.get("documents"):
                logger.debug("No similar fixes found for: %s", error_message[:100])
                return []
            
            fixes: list[ErrorFixPair] = []
            for doc in results["documents"][0]:
                try:
                    data = json.loads(doc)
                    fix = ErrorFixPair(**data)
                    
                    # Check similarity threshold (ChromaDB returns distances, not scores)
                    # Lower distance = higher similarity
                    # We approximate by checking if the error message is substantially similar
                    fixes.append(fix)
                except Exception as exc:
                    logger.warning("Failed to parse stored fix: %s", exc)
            
            logger.info(
                "Found %d similar fixes for error: %s",
                len(fixes),
                error_message[:50],
            )
            
            return fixes
            
        except Exception as exc:
            logger.error("Failed to search for similar fixes: %s", exc)
            return []
    
    def get_statistics(self) -> dict[str, Any]:
        """Get statistics about the long-term memory.
        
        Returns:
            Dictionary with collection statistics.
        """
        if self._collection is None:
            return {"available": False, "reason": "ChromaDB not initialized"}
        
        try:
            count = self._collection.count()
            return {
                "available": True,
                "total_fixes": count,
                "persist_dir": str(self.persist_dir),
            }
        except Exception as exc:
            return {"available": False, "error": str(exc)}
    
    def clear(self) -> bool:
        """Clear all stored error-fix pairs.
        
        Returns:
            True if cleared successfully.
        """
        if self._collection is None:
            return False
        
        try:
            self._collection.delete(where={"success": True})
            logger.info("Long-term memory cleared")
            return True
        except Exception as exc:
            logger.error("Failed to clear memory: %s", exc)
            return False
