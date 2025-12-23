"""
OpenSearch client for RAG (Retrieval-Augmented Generation) operations.
"""

import os
import json
import threading
from typing import List, Dict, Any, Tuple

from opensearchpy import OpenSearch

from .config import Config


class OpenSearchClient:
    """Thread-safe OpenSearch client for RAG operations."""
    
    # Thread-local storage for client instances
    _thread_local = threading.local()
    
    @classmethod
    def get_client(cls) -> OpenSearch:
        """Get thread-local OpenSearch client."""
        if not hasattr(cls._thread_local, 'os_client'):
            cls._thread_local.os_client = OpenSearch(
                hosts=[Config.OS_HOST],
                http_auth=(Config.OS_USER, Config.OS_PASS) if Config.OS_USER and Config.OS_PASS else None,
                use_ssl=Config.OS_HOST.startswith("https"),
                verify_certs=Config.OS_SSL_VERIFY,
                ssl_show_warn=False,
            )
        return cls._thread_local.os_client
    
    @classmethod
    def ping(cls) -> bool:
        """Test OpenSearch connection."""
        try:
            client = cls.get_client()
            return client.ping()
        except Exception:
            return False
    
    @classmethod
    def search_by_cpt_codes(
        cls,
        index: str,
        cpt_codes: List[str],
        payer_filter_terms: List[str],
        top_k: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Direct search for ALL guidelines containing the CPT codes.
        
        Args:
            index: OpenSearch index name
            cpt_codes: List of CPT codes to search for
            payer_filter_terms: Terms to filter for payer-specific content
            top_k: Maximum number of results to return (default 50 to get all matches)
            
        Returns:
            List of ALL search hits matching the CPT codes
        """
        try:
            client = cls.get_client()
            
            # Normalize CPT codes for matching
            normalized_cpt_codes = []
            for code in cpt_codes:
                cleaned = str(code).strip().replace("-", "").replace(" ", "")
                normalized_cpt_codes.append(cleaned)
            
            print(f"[INFO] Searching OpenSearch for CPT codes: {cpt_codes}")
            
            # Build comprehensive query for CPT code matching
            should_clauses = []
            for original_code, normalized_code in zip(cpt_codes, normalized_cpt_codes):
                # Search in multiple fields with different variations
                # Wildcard search for flexible matching
                should_clauses.append({"wildcard": {"text": {"value": f"*{normalized_code}*", "boost": 5.0}}})
                should_clauses.append({"wildcard": {"text": {"value": f"*{original_code}*", "boost": 5.0}}})
                
                # Match phrase for exact matches
                should_clauses.append({"match_phrase": {"text": {"query": original_code, "boost": 10.0}}})
                should_clauses.append({"match_phrase": {"text": {"query": normalized_code, "boost": 10.0}}})
                
                # Match in dedicated CPT fields
                should_clauses.append({"match": {"cpt_codes": {"query": original_code, "boost": 15.0}}})
                should_clauses.append({"match": {"code": {"query": original_code, "boost": 15.0}}})
                should_clauses.append({"match": {"cpt_codes": {"query": normalized_code, "boost": 15.0}}})
                should_clauses.append({"match": {"code": {"query": normalized_code, "boost": 15.0}}})
            
            body = {
                "size": 100,  # Get more results to capture all matches
                "query": {
                    "bool": {
                        "should": should_clauses,
                        "minimum_should_match": 1
                    }
                },
                "_source": True,  # Get all fields
            }
            
            res = client.search(index=index, body=body)
            hits = res.get("hits", {}).get("hits", [])
            
            print(f"[INFO] OpenSearch returned {len(hits)} total hits")
            
            # Filter for payer-specific hits (prioritize but don't exclude general hits)
            payer_hits = []
            general_hits = []
            
            for hit in hits:
                source = hit.get("_source", {})
                file_path = str(source.get("file", "")).lower()
                text_content = str(source.get("text", "")).lower()
                record_id = str(source.get("record_id", "")).lower()
                
                # Check if any CPT code is actually in this hit
                hit_str = json.dumps(source, default=str).upper()
                has_cpt_match = any(norm_code in hit_str for norm_code in normalized_cpt_codes)
                
                if not has_cpt_match:
                    continue  # Skip if CPT code not found in content
                
                is_payer_specific = (
                    any(term.lower() in file_path for term in payer_filter_terms) or
                    any(term.lower() in text_content for term in payer_filter_terms) or
                    any(term.lower() in record_id for term in payer_filter_terms)
                )
                
                if is_payer_specific:
                    payer_hits.append(hit)
                else:
                    general_hits.append(hit)
            
            # Prioritize payer-specific hits, then general hits
            combined_hits = payer_hits + general_hits
            result_hits = combined_hits[:top_k]
            
            print(f"[INFO] Direct CPT lookup found {len(combined_hits)} total guidelines")
            print(f"[INFO] Returning top {len(result_hits)} guidelines (Payer-specific: {len(payer_hits)}, General: {len(general_hits)})")
            
            return result_hits
            
        except Exception as e:
            print(f"[WARNING] OpenSearch error for CPT code search: {e}")
            return []
    
    @classmethod
    def search_payer_specific(
        cls, 
        index: str, 
        query: str, 
        payer_filter_terms: List[str], 
        top_k: int
    ) -> List[Dict[str, Any]]:
        """
        Enhanced payer-specific search with better filtering.
        
        Args:
            index: OpenSearch index name
            query: Search query text
            payer_filter_terms: Terms to bias search toward payer-specific content
            top_k: Number of results to return
            
        Returns:
            List of search hits
        """
        try:
            client = cls.get_client()
            
            body = {
                "size": top_k * 3,  # Get more results for better filtering
                "query": {
                    "bool": {
                        "must": [
                            {"match": {"text": {"query": query, "boost": 1.0}}}
                        ],
                        "should": [
                            {"match": {"file": {"query": " ".join(payer_filter_terms), "boost": 3.0}}},
                            {"match": {"text": {"query": " ".join(payer_filter_terms), "boost": 2.0}}},
                            {"match": {"record_id": {"query": " ".join(payer_filter_terms), "boost": 2.5}}}
                        ],
                        "minimum_should_match": 0
                    }
                },
                "_source": ["text", "file", "record_id", "chunk_index", "text_preview"],
            }
            
            res = client.search(index=index, body=body)
            hits = res.get("hits", {}).get("hits", [])
            
            # Enhanced filtering logic
            payer_hits = []
            general_hits = []
            
            for hit in hits:
                file_path = hit.get("_source", {}).get("file", "").lower()
                text_content = hit.get("_source", {}).get("text", "").lower()
                record_id = hit.get("_source", {}).get("record_id", "").lower()
                
                # Check multiple fields for payer-specific terms
                is_payer_specific = (
                    any(term.lower() in file_path for term in payer_filter_terms) or
                    any(term.lower() in text_content for term in payer_filter_terms) or
                    any(term.lower() in record_id for term in payer_filter_terms)
                )
                
                if is_payer_specific:
                    payer_hits.append(hit)
                else:
                    general_hits.append(hit)
            
            # Return payer-specific hits first, then general hits
            combined_hits = payer_hits + general_hits
            return combined_hits[:top_k]
            
        except Exception as e:
            print(f"⚠️ OpenSearch error for payer-specific search: {e}")
            return []
    
    @classmethod
    def search_general(cls, index: str, query: str, top_k: int) -> List[Dict[str, Any]]:
        """
        Fallback general search.
        
        Args:
            index: OpenSearch index name
            query: Search query text
            top_k: Number of results to return
            
        Returns:
            List of search hits
        """
        try:
            client = cls.get_client()
            
            body = {
                "size": top_k,
                "query": {"match": {"text": {"query": query}}},
                "_source": ["text", "file", "record_id", "chunk_index", "text_preview"],
            }
            
            res = client.search(index=index, body=body)
            return res.get("hits", {}).get("hits", [])
            
        except Exception as e:
            print(f"⚠️ OpenSearch error for general search: {e}")
            return []
    
    @classmethod
    def _extract_inline_evidence(cls, text: str) -> List[str]:
        """Extract inline evidence references like '(Evidence: pg no: 2, L73)' from text."""
        import re
        # Pattern to match evidence references in format: (Evidence: pg no: X, LY) or (Evidence: pg no: X, LY-LZ)
        pattern = r'\(Evidence:\s*pg\s+no:\s*\d+,?\s*L\d+(?:-L\d+)?\)'
        matches = re.findall(pattern, text)
        return matches
    
    @classmethod
    def _collect_all_evidence_from_source(cls, source: Dict[str, Any]) -> List[str]:
        """Collect all inline evidence references from an OpenSearch source."""
        all_evidence = []
        
        def extract_from_value(value):
            """Recursively extract evidence from any value."""
            if isinstance(value, str):
                evidence_refs = cls._extract_inline_evidence(value)
                all_evidence.extend(evidence_refs)
            elif isinstance(value, dict):
                for v in value.values():
                    extract_from_value(v)
            elif isinstance(value, list):
                for item in value:
                    extract_from_value(item)
        
        extract_from_value(source)
        return list(set(all_evidence))  # Remove duplicates
    
    @classmethod
    def build_context_for_procedure(
        cls, 
        proc_name: str, 
        hits: List[Dict[str, Any]], 
        max_chars: int, 
        payer: str
    ) -> Tuple[str, List[Dict[str, Any]], bool]:
        """
        Build context with enhanced source tracking and evidence extraction.
        
        Args:
            proc_name: Procedure name
            hits: Search hits from OpenSearch
            max_chars: Maximum characters for context
            payer: Payer name
            
        Returns:
            Tuple of (context_text, sources, has_relevant_guidelines)
        """
        lines = []
        sources = []
        used = 0
        has_relevant_guidelines = False
        
        for rank, h in enumerate(hits, start=1):
            score = float(h.get("_score", 0.0))
            s = h.get("_source", {})
            file_name = os.path.basename(s.get("file", ""))
            record_id = s.get("record_id", "")
            part = s.get("chunk_index", 0)
            text = s.get("text", "")
            
            # Extract inline evidence references from the text
            inline_evidence = cls._collect_all_evidence_from_source(s)
            
            # Add evidence info to header if available
            evidence_summary = ""
            if inline_evidence:
                evidence_summary = f" | Evidence: {len(inline_evidence)} ref(s)"
            
            header = f"[{payer.upper()} | {proc_name} | Chunk {rank} | score={score:.3f} | file={file_name} | id={record_id} | part={part}{evidence_summary}]"
            block = f"{header}\n{text}\n"
            
            if score >= Config.MIN_RELEVANCE_SCORE:
                has_relevant_guidelines = True
            
            if used + len(block) > max_chars and lines:
                break
                
            lines.append(block)
            used += len(block)
            
            sources.append({
                "header": header,
                "file": s.get("file", ""),
                "record_id": record_id,
                "chunk_index": part,
                "payer": payer,
                "score": score,
                "description": s.get("text_preview", text[:1500]) or text[:1500],  # Increased from 600 to 1500
                "full_source": s,  # Include full source for detailed extraction
                "payer_guideline_reference": inline_evidence
            })
        
        return "\n\n".join(lines), sources, has_relevant_guidelines
