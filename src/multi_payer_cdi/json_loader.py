"""
JSON guideline data loader for local file-based knowledge retrieval.
"""

import os
import json
import glob
from typing import List, Dict, Any, Tuple

from .config import Config


class JSONGuidelineLoader:
    """Loads and searches payer guideline data from local JSON files."""
    
    def __init__(self):
        """Initialize the JSON guideline loader."""
        self.guidelines_cache = {}
        self._load_all_guidelines()
    
    def _load_all_guidelines(self):
        """Load all JSON guideline files into memory."""
        for payer_key, json_path in Config.JSON_GUIDELINE_PATHS.items():
            if os.path.exists(json_path):
                self.guidelines_cache[payer_key] = self._load_payer_guidelines(json_path)
                print(f"[OK] Loaded {len(self.guidelines_cache[payer_key])} guidelines for {payer_key}")
            else:
                print(f"[WARNING] JSON guideline path not found for {payer_key}: {json_path}")
                self.guidelines_cache[payer_key] = []
    
    def _load_payer_guidelines(self, directory_path: str) -> List[Dict[str, Any]]:
        """Load all JSON files from a payer's directory."""
        guidelines = []
        
        if os.path.isfile(directory_path):
            # Single JSON file
            try:
                with open(directory_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        guidelines.extend(data)
                    else:
                        guidelines.append(data)
            except Exception as e:
                print(f"[WARNING] Error loading JSON file {directory_path}: {e}")
        
        elif os.path.isdir(directory_path):
            # Directory of JSON files
            json_files = glob.glob(os.path.join(directory_path, "*.json"))
            for json_file in json_files:
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        if isinstance(data, list):
                            guidelines.extend(data)
                        else:
                            guidelines.append(data)
                except Exception as e:
                    print(f"[WARNING] Error loading JSON file {json_file}: {e}")
        
        return guidelines
    
    def search_by_cpt_codes(
        self,
        payer_key: str,
        cpt_codes: List[str],
        top_k: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Direct search for guidelines by CPT codes - returns ALL guidelines containing any of the CPT codes.
        
        Args:
            payer_key: Payer identifier (cigna, uhc, anthem)
            cpt_codes: List of CPT codes to search for
            top_k: Maximum number of results to return (default 50 to get all matches)
            
        Returns:
            List of ALL guideline documents matching the CPT codes
        """
        payer_guidelines = self.guidelines_cache.get(payer_key, [])
        
        if not payer_guidelines:
            print(f"[WARNING] No guidelines loaded for {payer_key}")
            return []
        
        matched_guidelines = []
        
        # Normalize CPT codes for matching (remove spaces, hyphens, make uppercase)
        normalized_cpt_codes = []
        for code in cpt_codes:
            cleaned = str(code).strip().replace("-", "").replace(" ", "").upper()
            normalized_cpt_codes.append(cleaned)
        
        print(f"[INFO] Searching for CPT codes: {cpt_codes} (normalized: {normalized_cpt_codes})")
        
        for idx, guideline in enumerate(payer_guidelines):
            matched = False
            matched_codes = []
            score = 0
            
            # Convert entire guideline to string for comprehensive search
            guideline_str = json.dumps(guideline, default=str).upper()
            
            # Check each CPT code
            for original_code, normalized_code in zip(cpt_codes, normalized_cpt_codes):
                # Check if CPT code appears anywhere in the guideline
                if normalized_code in guideline_str:
                    matched = True
                    matched_codes.append(original_code)
                    score += 100.0  # High score for direct match
                    
                    # Extra score if in dedicated CPT fields
                    if "cpt_codes" in guideline:
                        cpt_field_str = str(guideline.get("cpt_codes", "")).upper()
                        if normalized_code in cpt_field_str:
                            score += 50.0
                    
                    if "codes" in guideline:
                        codes_str = json.dumps(guideline.get("codes", []), default=str).upper()
                        if normalized_code in codes_str:
                            score += 50.0
            
            # If any CPT code matched, add this guideline
            if matched:
                matched_guidelines.append({
                    "_score": score,
                    "_source": guideline,
                    "_index": payer_key,
                    "_id": f"{payer_key}_{idx}",
                    "matched_cpt_codes": matched_codes
                })
                print(f"  [MATCH] Found guideline {idx} with CPT codes: {matched_codes} (score: {score})")
        
        # Sort by score descending (guidelines with more CPT matches come first)
        matched_guidelines.sort(key=lambda x: x["_score"], reverse=True)
        
        result_count = min(len(matched_guidelines), top_k)
        print(f"[INFO] Direct CPT lookup found {len(matched_guidelines)} total guidelines for {payer_key}")
        print(f"[INFO] Returning top {result_count} guidelines")
        
        return matched_guidelines[:top_k]
    
    def search_guidelines(
        self, 
        payer_key: str, 
        query: str, 
        top_k: int = 6
    ) -> List[Dict[str, Any]]:
        """
        Search for relevant guidelines for a payer based on query.
        
        Args:
            payer_key: Payer identifier (cigna, uhc, anthem)
            query: Search query (procedure name, CPT code, etc.)
            top_k: Number of results to return
            
        Returns:
            List of relevant guideline documents with scores
        """
        payer_guidelines = self.guidelines_cache.get(payer_key, [])
        
        if not payer_guidelines:
            return []
        
        # Simple keyword-based search with scoring
        scored_guidelines = []
        query_lower = query.lower()
        query_terms = set(query_lower.split())
        
        for idx, guideline in enumerate(payer_guidelines):
            score = self._calculate_relevance_score(guideline, query_lower, query_terms)
            
            if score > 0:
                scored_guidelines.append({
                    "_score": score,
                    "_source": guideline,
                    "_index": payer_key,
                    "_id": f"{payer_key}_{idx}"
                })
        
        # Sort by score descending
        scored_guidelines.sort(key=lambda x: x["_score"], reverse=True)
        
        return scored_guidelines[:top_k]
    
    def _calculate_relevance_score(
        self, 
        guideline: Dict[str, Any], 
        query_lower: str, 
        query_terms: set
    ) -> float:
        """Calculate relevance score for a guideline based on query."""
        score = 0.0
        
        # Convert guideline to searchable text
        searchable_fields = [
            guideline.get("procedure", ""),
            guideline.get("text", ""),
            guideline.get("content", ""),
            guideline.get("policy_name", ""),
            guideline.get("description", ""),
            " ".join(guideline.get("cpt_codes", [])) if isinstance(guideline.get("cpt_codes"), list) else "",
        ]
        
        # Add nested fields if present
        if "evidence" in guideline:
            if isinstance(guideline["evidence"], dict):
                searchable_fields.append(str(guideline["evidence"]))
            elif isinstance(guideline["evidence"], list):
                searchable_fields.extend([str(e) for e in guideline["evidence"]])
        
        searchable_text = " ".join(str(field) for field in searchable_fields).lower()
        
        # Exact phrase match (high score)
        if query_lower in searchable_text:
            score += 10.0
        
        # Term matching (moderate score)
        text_terms = set(searchable_text.split())
        matching_terms = query_terms.intersection(text_terms)
        score += len(matching_terms) * 2.0
        
        # CPT code matching (high priority)
        cpt_codes = guideline.get("cpt_codes", [])
        if isinstance(cpt_codes, list):
            for cpt in cpt_codes:
                if str(cpt) in query_lower:
                    score += 15.0
        
        # Procedure name matching
        procedure = str(guideline.get("procedure", "")).lower()
        if procedure and procedure in query_lower:
            score += 12.0
        
        return score
    
    def build_context_for_procedure(
        self, 
        proc_name: str, 
        hits: List[Dict[str, Any]], 
        max_chars: int, 
        payer_key: str
    ) -> Tuple[str, List[Dict[str, Any]], bool]:
        """
        Build context from JSON guideline hits with PDF evidence.
        
        Args:
            proc_name: Procedure name
            hits: Search results
            max_chars: Maximum characters for context
            payer_key: Payer identifier
            
        Returns:
            Tuple of (context_text, sources, has_relevant_guidelines)
        """
        lines = []
        sources = []
        used = 0
        has_relevant_guidelines = False
        
        for rank, h in enumerate(hits, start=1):
            score = float(h.get("_score", 0.0))
            source = h.get("_source", {})
            
            # Build header
            procedure = source.get("procedure", proc_name)
            file_name = f"{payer_key}_guideline_{rank}.json"
            record_id = h.get("_id", f"{payer_key}_{rank}")
            
            # Extract PDF evidence if available
            evidence = source.get("evidence", {})
            pdf_reference = ""
            if evidence:
                if isinstance(evidence, dict):
                    pdf_file = evidence.get("pdf_file") or evidence.get("file") or evidence.get("source_file")
                    page_num = evidence.get("page") or evidence.get("page_number") or evidence.get("page_num")
                    if pdf_file:
                        pdf_reference = f" | PDF: {pdf_file}"
                        if page_num:
                            pdf_reference += f" (Page {page_num})"
                elif isinstance(evidence, str):
                    pdf_reference = f" | Evidence: {evidence[:100]}"
            
            header = f"[{payer_key.upper()} | {procedure} | Chunk {rank} | score={score:.3f} | file={file_name} | id={record_id}{pdf_reference}]"
            
            # Get text content - include all fields that might have evidence
            text_parts = []
            
            # Get main text
            main_text = (
                source.get("text") or 
                source.get("content") or 
                source.get("description") or 
                ""
            )
            if main_text:
                text_parts.append(main_text)
            
            # Include category, section_title, names with evidence
            if source.get("category"):
                text_parts.append(f"Category: {source.get('category')}")
            if source.get("section_title"):
                text_parts.append(f"Section: {source.get('section_title')}")
            if source.get("names"):
                names = source.get("names")
                if isinstance(names, list):
                    text_parts.append(f"Names: {', '.join(names)}")
            
            # Include requirements that have evidence
            if source.get("general_requirements"):
                gen_req = source.get("general_requirements")
                if isinstance(gen_req, dict):
                    if gen_req.get("documentation"):
                        text_parts.append("Documentation Requirements:")
                        for req in gen_req.get("documentation", []):
                            text_parts.append(f"  - {req}")
            
            # Include codes with evidence
            if source.get("codes"):
                codes = source.get("codes", [])
                if isinstance(codes, list):
                    text_parts.append("Codes:")
                    for code in codes:
                        if isinstance(code, dict):
                            code_desc = f"  {code.get('code', '')}: {code.get('description', '')}"
                            text_parts.append(code_desc)
            
            # Include notes
            if source.get("notes"):
                text_parts.append(f"Notes: {source.get('notes')}")
            
            text = "\n".join(text_parts)
            
            # Add evidence to text if available
            if evidence and isinstance(evidence, dict):
                evidence_text = evidence.get("text") or evidence.get("evidence_text") or evidence.get("excerpt")
                if evidence_text:
                    text += f"\n\n[PDF Evidence]: {evidence_text}"
            
            block = f"{header}\n{text}\n"
            
            if score >= Config.MIN_RELEVANCE_SCORE:
                has_relevant_guidelines = True
            
            if used + len(block) > max_chars and lines:
                break
            
            lines.append(block)
            used += len(block)
            
            # Collect all inline evidence references from this source
            inline_evidence = self._collect_all_evidence_from_source(source)
            
            sources.append({
                "header": header,
                "file": file_name,
                "record_id": record_id,
                "chunk_index": rank,
                "payer": payer_key,
                "score": score,
                "description": str(source)[:1500],  # Increased from 600 to 1500 for more content
                "full_source": source,  # Include full source for detailed extraction
                "payer_guideline_reference": inline_evidence
            })
        
        return "\n\n".join(lines), sources, has_relevant_guidelines
    
    def _extract_evidence_details(self, evidence: Any) -> Dict[str, Any]:
        """Extract structured evidence details from various formats."""
        if not evidence:
            return {}
        
        evidence_details = {}
        
        if isinstance(evidence, dict):
            evidence_details = {
                "pdf_file": evidence.get("pdf_file") or evidence.get("file") or evidence.get("source_file") or "",
                "page": evidence.get("page") or evidence.get("page_number") or evidence.get("page_num") or "",
                "text": evidence.get("text") or evidence.get("evidence_text") or evidence.get("excerpt") or "",
                "location": evidence.get("location") or evidence.get("section") or "",
                "reference": evidence.get("reference") or evidence.get("citation") or ""
            }
            # Remove empty values
            evidence_details = {k: v for k, v in evidence_details.items() if v}
        
        elif isinstance(evidence, list) and evidence:
            # Take first evidence if list
            evidence_details = self._extract_evidence_details(evidence[0])
        
        elif isinstance(evidence, str):
            evidence_details = {"text": evidence}
        
        return evidence_details
    
    def _extract_inline_evidence(self, text: str) -> List[str]:
        """Extract inline evidence references like '(Evidence: pg no: 2, L73)' from text."""
        import re
        # Pattern to match evidence references in format: (Evidence: pg no: X, LY)
        pattern = r'\(Evidence:\s*pg\s+no:\s*\d+,?\s*L\d+(?:-L\d+)?\)'
        matches = re.findall(pattern, text)
        return matches
    
    def _collect_all_evidence_from_source(self, source: Dict[str, Any]) -> List[str]:
        """Collect all inline evidence references from a JSON source."""
        all_evidence = []
        
        def extract_from_value(value):
            """Recursively extract evidence from any value."""
            if isinstance(value, str):
                evidence_refs = self._extract_inline_evidence(value)
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
    def is_available(cls) -> bool:
        """Check if JSON guidelines are available."""
        for payer_key, json_path in Config.JSON_GUIDELINE_PATHS.items():
            if os.path.exists(json_path):
                return True
        return False

