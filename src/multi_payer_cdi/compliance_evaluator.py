"""
Compliance evaluation logic for multi-payer CDI processing.
"""

import json
from typing import Dict, Any, List, Tuple, Optional

from .bedrock_client import BedrockClient
from .opensearch_client import OpenSearchClient
from .cache_manager import CacheManager
from .file_processor import FileProcessor
from .models import ComplianceResult, ProcedureResult, UsageInfo, ExtractionData
from .config import Config
from .json_loader import JSONGuidelineLoader
from .logger import CDILogger
from .utils import smart_truncate_by_words


class ComplianceEvaluator:
    """Handles compliance evaluation for multiple payers."""
    
    def __init__(self, cache_manager: CacheManager):
        self.cache_manager = cache_manager
        self.json_loader = None
        self.base_system_prompt = self._load_system_prompt()
        
        # Initialize JSON loader if using JSON data source
        if Config.DATA_SOURCE == "json":
            print("[INFO] Initializing JSON guideline loader...")
            self.json_loader = JSONGuidelineLoader()
            print(f"[OK] JSON loader initialized with {len(self.json_loader.guidelines_cache)} payer(s)")
    
    def _load_system_prompt(self) -> str:
        """Load the comprehensive compliance system prompt."""
        import os
        prompt_path = os.path.join(os.path.dirname(__file__), "..", "..", "prompts", "compliance_system_prompt.txt")
        prompt_path = os.path.normpath(prompt_path)
        try:
            with open(prompt_path, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            print(f"[WARNING] Compliance system prompt not found at {prompt_path}, using fallback")
            # Fallback minimal prompt if file not found
            return "You are a clinical documentation specialist evaluating medical charts against payer guidelines. Assess whether documented evidence meets guideline requirements. Return valid JSON as requested."
    
    def call_claude_with_cache(
        self, 
        prompt: str, 
        max_tokens: int = 800, 
        temperature: float = 0.0, 
        system_prompt: Optional[str] = None, 
        cache_type: str = "general"
    ) -> Tuple[str, Dict[str, Any]]:
        """Call Claude with caching support."""
        cache_key = self.cache_manager.get_cache_key(prompt, system_prompt, max_tokens, temperature)
        
        # Try to load from cache first
        cached_result = self.cache_manager.load_from_cache(cache_key)
        if cached_result:
            response, usage_info = cached_result
            print(f"[CACHE] Cache HIT for {cache_type} prompt")
            self.cache_manager.update_cache_stats(cache_type, True)
            return response, usage_info
        
        # Cache miss - call Claude
        print(f"[CACHE] Cache MISS for {cache_type} prompt - calling Claude")
        response, usage_info = BedrockClient.call_claude(prompt, max_tokens, temperature, system_prompt)
        
        # Log LLM call
        cost = (usage_info.get("input_tokens", 0) / 1000 * Config.INPUT_COST_PER_1K) + \
               (usage_info.get("output_tokens", 0) / 1000 * Config.OUTPUT_COST_PER_1K)
        CDILogger.log_llm_call(
            model=usage_info.get("model_id", "unknown"),
            prompt_tokens=usage_info.get("input_tokens", 0),
            completion_tokens=usage_info.get("output_tokens", 0),
            cost=cost,
            cache_hit=False,
            purpose=cache_type
        )
        
        # Save to cache
        self.cache_manager.save_to_cache(cache_key, response, usage_info)
        self.cache_manager.update_cache_stats(cache_type, False)
        
        return response, usage_info
    
    def run_extraction(self, chart_text: str) -> Tuple[str, Dict[str, Any]]:
        """Run extraction with caching and CPT detection."""
        extraction_prompt = """
You are a medical coding and CDI specialist.

TASK:
Analyze the following operative report/medical chart and return a JSON object with the EXACT keys below. You MUST extract patient information FIRST before procedures.

REQUIRED JSON STRUCTURE (ALL fields are required - extract ALL of them):
You MUST return a JSON object with these EXACT keys:
- "patient_name": STRING - Extract the patient's full name from the chart
- "patient_age": STRING - Extract age with units (e.g., "52-year-old", "67 years old", "6 months")
- "chart_specialty": STRING - Determine specialty category (e.g., "Orthopedic Surgery", "Oncology")
- "cpt": ARRAY of strings - CPT codes if mentioned, empty array [] if none
- "procedure": ARRAY of strings - Surgical/medical procedures performed
- "summary": STRING - 2-4 sentence clinical summary highlighting documentation critical for CDI

EXAMPLE JSON OUTPUT:
{{
  "patient_name": "Sarah Johnson",
  "patient_age": "52-year-old",
  "chart_specialty": "Orthopedic Surgery",
  "cpt": [],
  "procedure": ["Arthroscopic rotator cuff repair, right shoulder", "Arthroscopic labral repair, right shoulder"],
  "summary": "52-year-old female with rotator cuff tear and labral pathology..."
}}

CRITICAL: EXTRACT PATIENT INFORMATION FIRST - BEFORE ANYTHING ELSE

1. PATIENT NAME EXTRACTION - READ CAREFULLY:
   Search the ENTIRE chart from beginning to end for patient name. Common locations:
   - Lines starting with "Patient Name:" followed by a name
   - Lines with "Name:" label followed by a name  
   - "PATIENT:" header followed by a name
   - "Patient:" label followed by a name
   - Header section typically contains: "Patient Name: [NAME]" or "Name: [NAME]"
   
   EXAMPLES:
   - If chart contains: "Patient Name: Sarah Johnson" → Extract "Sarah Johnson" (NOT "Unknown")
   - If chart contains: "Name: John Doe" → Extract "John Doe" (NOT "Unknown")
   - If chart contains: "Patient: Michael Smith" → Extract "Michael Smith" (NOT "Unknown")
   
   CRITICAL: 
   - The patient name is ALWAYS in the chart header if the chart is complete
   - Look for "Patient Name:" at the top of the chart - this is the PRIMARY source
   - Extract the COMPLETE name as written (e.g., "Sarah Johnson", "John Doe")
   - Do NOT use "Unknown" if you see ANY name pattern in the chart
   - Names are typically on line 2-5 of the chart header

2. PATIENT AGE EXTRACTION - READ CAREFULLY:
   Search the ENTIRE chart for age information:
   - Look for phrases like "52-year-old", "67 years old", "45-year-old female", "6 months old"
   - Check HPI/Indications sections which often state: "The patient is a 52-year-old..."
   - Look for DOB (Date of Birth) with encounter date - calculate age if both present
   
   EXAMPLES:
   - If chart contains: "The patient is a 52-year-old female" → Extract "52-year-old" (NOT "Unknown")
   - If chart contains: "INDICATIONS: The patient is a 52-year-old female" → Extract "52-year-old" (NOT "Unknown")
   - If chart contains: "52-year-old female with..." → Extract "52-year-old" (NOT "Unknown")
   - If chart contains: "Patient age: 45 years" → Extract "45 years old" (NOT "Unknown")
   - If chart contains: "67 yo male" → Extract "67 years old" (NOT "Unknown")
   
   CRITICAL:
   - Age is ALWAYS stated in the chart if it's a complete operative report
   - Look in INDICATIONS, HPI, or first few sentences of clinical sections
   - Extract the age WITH units/format as written (e.g., "52-year-old", "67 years old")
   - Do NOT use "Unknown" if you see ANY age pattern in the chart
   - Age typically appears with gender (e.g., "52-year-old female", "67-year-old male")

3. CHART SPECIALTY EXTRACTION - USE MEDICAL KNOWLEDGE:
   Determine the specialty by analyzing the procedures and diagnoses:
   
   EXAMPLES:
   - Procedures: rotator cuff, knee arthroscopy, hip replacement, shoulder surgery → "Orthopedic Surgery"
   - Procedures: arthroscopy, ACL, labrum, meniscus → "Orthopedic Surgery"
   - Diagnoses: cancer, tumor, chemotherapy → "Oncology"
   - Procedures: cardiac catheterization, stent, echo → "Cardiology"
   - Procedures: brain surgery, stroke, seizure → "Neurology"
   - Procedures: appendectomy, cholecystectomy, hernia → "General Surgery"
   
   IMPORTANT:
   - Analyze ALL procedures and diagnoses to determine specialty
   - Use your medical knowledge to categorize appropriately
   - Default to "Orthopedic Surgery" for musculoskeletal procedures
   - Only use "Unknown" if truly ambiguous (rare)

4. PROCEDURE AND CPT EXTRACTION:

PROCEDURE EXTRACTION - FOLLOW THESE STEPS EXACTLY:

STEP 1: Locate the Procedure Section
- Find the section labeled "Procedure", "Procedures", "Operative Procedures", "Operations", or similar.
- Extract all procedures mentioned in this section (usually near the top of the report).

STEP 2: Identify Each Listed Procedure
- Read each procedure line carefully.
- Each numbered or bulleted item typically represents one or more procedures.
- Look for separators like commas, semicolons, or the word "and".

STEP 3: Apply Splitting Rules CONSISTENTLY
Split procedures ONLY when they involve different:
- Laterality (left vs right): "Right knee arthroscopy and left knee arthroscopy" → 2 procedures
- Spinal/anatomical levels: "L3-4 and L4-5 discectomy" → 2 procedures  
- Different anatomical sites: "Hip replacement and knee replacement" → 2 procedures

Do NOT split when:
- It's a single procedure with multiple steps: "Incision and drainage" → 1 procedure
- It's a single procedure with a modifier: "Open reduction and internal fixation" → 1 procedure
- It describes one procedure: "Lysis of adhesions and exploration" → 1 procedure

STEP 4: Format Each Procedure
- Keep each procedure complete and self-contained.
- Include laterality (left/right) with each split procedure.
- Include anatomical level with each split procedure.
- Use exact medical terminology from the report.

EXAMPLE:
Input: "Right L3-4 and left L2-3 laminotomy and microdiscectomy"
Output (2 procedures):
1. "Right L3-4 laminotomy and microdiscectomy"
2. "Left L2-3 laminotomy and microdiscectomy"

STEP 5: Validate Before Returning
- Count your procedures.
- Verify each procedure is independently codable.
- Ensure no procedures were missed from the procedure section.
- Ensure no duplicate procedures.

CRITICAL FINAL INSTRUCTIONS:
Return ONLY valid JSON with these EXACT keys: patient_name, patient_age, chart_specialty, cpt, procedure, summary.

EXTRACTION ORDER - FOLLOW THIS EXACTLY:
1. FIRST: Search the chart header/top for patient_name (look for "Patient Name:", "Name:", "Patient:")
2. SECOND: Search the chart for patient_age (look for "X-year-old", "X years old", age in HPI/Indications)
3. THIRD: Determine chart_specialty by analyzing procedures (rotator cuff/shoulder/knee/hip → "Orthopedic Surgery")
4. FOURTH: Extract procedures from the Procedure section
5. FIFTH: Look for CPT codes (often listed separately)
6. LAST: Create summary

VALIDATION CHECKLIST - Before returning JSON:
✓ Did you search the ENTIRE chart for patient name? (Check header, first line, HPI)
✓ Did you search for age patterns like "52-year-old" or "67 years old"?
✓ Did you analyze procedures to determine specialty? (rotator cuff → Orthopedic Surgery)
✓ Are ALL 6 fields present in your JSON? (patient_name, patient_age, chart_specialty, cpt, procedure, summary)
✓ Did you use "Unknown" ONLY if information is truly absent?

IMPORTANT:
- Do NOT default to "Unknown" if the information exists in the chart
- Extract actual values - the LLM can see the chart text clearly
- Patient name is usually at the top of the chart in a header
- Patient age is usually in HPI/Indications section (e.g., "The patient is a 52-year-old...")
- Specialty can be inferred from procedure types (use medical knowledge)

OPERATIVE REPORT:
<<<
{chart}
>>>
""".format(chart=smart_truncate_by_words(
            chart_text.strip(),
            max_words=Config.MAX_CHART_WORDS,
            context_words=Config.PROCEDURE_CONTEXT_WORDS,
            prioritize_sections=True
        ))
        
        response, usage_info = self.call_claude_with_cache(
            extraction_prompt, 
            max_tokens=1500,  # Increased to accommodate patient info fields
            temperature=0.0, 
            system_prompt=None, 
            cache_type="extraction"
        )
        
        # Parse and validate extraction response
        try:
            # Extract JSON from response (handles markdown code fences)
            json_str = self._extract_first_json_object(response)
            if json_str:
                parsed_response = json.loads(json_str)
                if isinstance(parsed_response, dict):
                    # Ensure all required fields are present with defaults
                    parsed_response.setdefault("patient_name", "Unknown")
                    parsed_response.setdefault("patient_age", "Unknown")
                    parsed_response.setdefault("chart_specialty", "Unknown")
                    parsed_response.setdefault("cpt", [])
                    parsed_response.setdefault("procedure", [])
                    parsed_response.setdefault("summary", "")
                    
                    # Log extracted patient information
                    patient_name = parsed_response.get("patient_name", "Unknown")
                    patient_age = parsed_response.get("patient_age", "Unknown")
                    chart_specialty = parsed_response.get("chart_specialty", "Unknown")
                    print(f"[EXTRACTION] Patient Name: {patient_name}")
                    print(f"[EXTRACTION] Patient Age: {patient_age}")
                    print(f"[EXTRACTION] Chart Specialty: {chart_specialty}")
                    
                    cpt_codes = parsed_response.get("cpt", [])
                    if cpt_codes and len(cpt_codes) > 0:
                        print(f"[INFO] CPT codes detected: {cpt_codes}")
                        parsed_response["has_cpt_codes"] = True
                    
                    # Update response with clean JSON
                    response = json.dumps(parsed_response)
                else:
                    print(f"[WARNING] Extraction response is not a dictionary")
            else:
                print(f"[WARNING] No JSON object found in extraction response")
        except Exception as e:
            print(f"[WARNING] Error parsing extraction response: {e}")
            print(f"[DEBUG] Response preview: {response[:500] if response else 'No response'}")
        
        return response, usage_info
    
    def _extract_first_json_object(self, text: str) -> Optional[str]:
        """Extract first JSON object from text with enhanced parsing."""
        if text is None:
            return None
        stripped = text.strip()
        if stripped.startswith("```"):
            parts = stripped.split("\n", 1)
            stripped = parts[1] if len(parts) > 1 else stripped
            if stripped.endswith("```"):
                stripped = stripped[:-3]
        start = stripped.find("{")
        if start == -1:
            return None
        depth = 0
        in_string = False
        escape = False
        for i in range(start, len(stripped)):
            ch = stripped[i]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue
            else:
                if ch == '"':
                    in_string = True
                    continue
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        return stripped[start : i + 1]
        return None
    
    def evaluate_procedure_for_all_payers(
        self,
        proc_name: str,
        chart_text: str,
        extraction_data: Optional[Dict[str, Any]] = None,
        proc_index: int = 0,
        total_procedures: int = 1
    ) -> Dict[str, Any]:
        """
        Evaluate a single procedure against all payers in a single LLM call.
        
        Args:
            proc_name: Name of the procedure to evaluate
            chart_text: Medical chart text with line numbers
            extraction_data: Extraction data containing CPT codes if available
            proc_index: Index of this procedure (for logging)
            total_procedures: Total number of procedures (for logging)
            
        Returns:
            Dictionary mapping payer_key to ProcedureResult for this procedure
        """
        print(f"[PROC {proc_index+1}/{total_procedures}] Evaluating '{proc_name}' for all payers in single LLM call...")
        
        try:
            chart_snippet = (chart_text or "")[:4000]
            all_payer_results = {}
            all_sources_by_payer = {}
            total_input_tokens = 0
            total_output_tokens = 0
            model_id = "unknown"
            
            # Check if we have CPT codes from extraction and if this procedure should use them
            has_cpt_codes = False
            cpt_codes = []
            procedures_list = extraction_data.get("procedure", []) if extraction_data else []
            
            if extraction_data and extraction_data.get("has_cpt_codes", False):
                all_cpt_codes = extraction_data.get("cpt", [])
                # Simple heuristic: if this procedure is in the first N procedures where N = number of CPT codes
                # then use CPT-based search for it
                if proc_index < len(all_cpt_codes):
                    has_cpt_codes = True
                    # Use the CPT code at the same index as the procedure
                    cpt_codes = [all_cpt_codes[proc_index]] if proc_index < len(all_cpt_codes) else all_cpt_codes
                    print(f"[INFO] Procedure '{proc_name}' will use CPT-based search with codes: {cpt_codes}")
                else:
                    print(f"[INFO] Procedure '{proc_name}' will use procedure-based RAG search (no CPT code match)")
            
            # Collect guidelines for all payers
            payer_guidelines = {}
            payer_sources = {}
            payer_contexts = {}
            
            sorted_payers = Config.get_sorted_payers()
            
            for payer_key, payer_config in sorted_payers:
                payer_name = payer_config['name']
                os_index = payer_config['os_index']
                payer_filter_terms = payer_config.get("filter_terms", [])
                
                print(f"  [{payer_name}] Retrieving guidelines for '{proc_name}'...")
                
                try:
                    if has_cpt_codes and cpt_codes:
                        # CPT-based search
                        if Config.DATA_SOURCE == "json" and self.json_loader:
                            hits = self.json_loader.search_by_cpt_codes(payer_key, cpt_codes, Config.TOP_K)
                            ctx, srcs, has_guidelines = self.json_loader.build_context_for_procedure(
                                proc_name, hits, Config.MAX_CONTEXT_CHARS // len(sorted_payers), payer_key
                            )
                        else:
                            hits = OpenSearchClient.search_by_cpt_codes(
                                os_index, cpt_codes, payer_filter_terms, Config.TOP_K
                            )
                            ctx, srcs, has_guidelines = OpenSearchClient.build_context_for_procedure(
                                proc_name, hits, Config.MAX_CONTEXT_CHARS // len(sorted_payers), payer_key
                            )
                    else:
                        # Procedure-based RAG search
                        q = f"{proc_name}\n\nChart evidence:\n{chart_snippet}"
                        if Config.DATA_SOURCE == "json" and self.json_loader:
                            hits = self.json_loader.search_guidelines(payer_key, q, Config.TOP_K)
                            ctx, srcs, has_guidelines = self.json_loader.build_context_for_procedure(
                                proc_name, hits, Config.MAX_CONTEXT_CHARS // len(sorted_payers), payer_key
                            )
                        else:
                            hits = OpenSearchClient.search_payer_specific(
                                os_index, q, payer_filter_terms, Config.TOP_K
                            )
                            if not hits:
                                hits = OpenSearchClient.search_general(os_index, q, Config.TOP_K)
                            ctx, srcs, has_guidelines = OpenSearchClient.build_context_for_procedure(
                                proc_name, hits, Config.MAX_CONTEXT_CHARS // len(sorted_payers), payer_key
                            )
                    
                    payer_guidelines[payer_key] = {
                        "context": ctx,
                        "has_guidelines": has_guidelines,
                        "hits": hits,
                        "payer_name": payer_name,
                        "is_cpt_based": has_cpt_codes and cpt_codes
                    }
                    payer_sources[payer_key] = srcs
                    payer_contexts[payer_key] = ctx
                    
                    print(f"  [{payer_name}] Found {len(hits)} guideline(s)")
                    
                except Exception as e:
                    print(f"  [ERROR] {payer_name}: Failed to retrieve guidelines: {e}")
                    payer_guidelines[payer_key] = {
                        "context": "",
                        "has_guidelines": False,
                        "hits": [],
                        "payer_name": payer_name,
                        "is_cpt_based": False,
                        "error": str(e)
                    }
                    payer_sources[payer_key] = []
                    payer_contexts[payer_key] = ""
            
            # Create multi-payer prompt
            system_prompt = f"{self.base_system_prompt}\n\nMULTI-PAYER TASK:\nYou will evaluate this procedure against guidelines from multiple payers. Return a JSON object with results for EACH payer separately."
            
            user_prompt = self._create_multi_payer_prompt(
                proc_name, chart_text, payer_guidelines, cpt_codes if has_cpt_codes else None
            )
            
            # Make single LLM call for all payers
            print(f"  [LLM] Making single LLM call for all {len(sorted_payers)} payers...")
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    raw, usage_info = self.call_claude_with_cache(
                        user_prompt,
                        max_tokens=4000,  # Increased for multi-payer response
                        temperature=0.0,
                        system_prompt=system_prompt,
                        cache_type="compliance"
                    )
                    break
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise e
                    print(f"  [WARNING] LLM call failed (attempt {attempt + 1}), retrying...")
                    continue
            
            total_input_tokens += usage_info.get("input_tokens", 0)
            total_output_tokens += usage_info.get("output_tokens", 0)
            model_id = usage_info.get("model_id", "unknown")
            
            # Parse multi-payer response
            parsed_results = self._parse_multi_payer_response(raw, proc_name, sorted_payers)
            
            # Process results for each payer
            for payer_key, payer_config in sorted_payers:
                payer_name = payer_config['name']
                
                if payer_key in parsed_results:
                    # Parse the payer-specific result
                    parsed = parsed_results[payer_key]
                    parsed["_original_procedure_name"] = proc_name
                    
                    # Extract chart references
                    chart_references = self._extract_chart_references(parsed)
                    parsed["medical_chart_reference"] = chart_references
                    
                    # Add guideline availability info
                    guideline_info = payer_guidelines.get(payer_key, {})
                    hits = guideline_info.get("hits", [])
                    parsed["guideline_availability"] = {
                        "status": "available" if guideline_info.get("has_guidelines") else "not_found",
                        "search_hits": len(hits),
                        "max_score": max([float(h.get("_score", 0.0)) for h in hits], default=0.0),
                        "message": f"Found {len(hits)} guideline(s) for {payer_name}"
                    }
                    
                    # Add sources
                    parsed["sources"] = payer_sources.get(payer_key, [])
                    
                    # Add guideline source tracking
                    parsed["guideline_source"] = "payer"
                    
                    all_payer_results[payer_key] = parsed
                    print(f"  [OK] {payer_name}: Successfully evaluated")
                else:
                    # Fallback to error result
                    error_result = self._create_error_result(proc_name, payer_name, "No result in LLM response")
                    error_result["_original_procedure_name"] = proc_name
                    all_payer_results[payer_key] = error_result
                    print(f"  [WARNING] {payer_name}: No result found, using error fallback")
            
            return {
                "payer_results": all_payer_results,
                "sources_by_payer": payer_sources,
                "usage": {"input_tokens": total_input_tokens, "output_tokens": total_output_tokens, "model_id": model_id}
            }
            
        except Exception as e:
            print(f"[ERROR] Failed to evaluate procedure '{proc_name}' for all payers: {e}")
            # Return error results for all payers
            error_results = {}
            for payer_key, payer_config in Config.get_sorted_payers():
                error_result = self._create_error_result(proc_name, payer_config['name'], str(e))
                error_result["_original_procedure_name"] = proc_name
                error_results[payer_key] = error_result
            
            return {
                "payer_results": error_results,
                "sources_by_payer": {},
                "usage": {"input_tokens": 0, "output_tokens": 0, "model_id": "unknown"}
            }
    
    def evaluate_payer_compliance(
        self, 
        payer_key: str, 
        payer_config: Dict[str, Any], 
        procedures_list: List[str], 
        chart_text: str, 
        extraction_data: Optional[Dict[str, Any]] = None
    ) -> Tuple[str, ComplianceResult]:
        """Evaluate compliance for a specific payer with enhanced error handling and caching."""
        payer_name = payer_config['name']
        os_index = payer_config['os_index']
        
        print(f"[STARTING] Starting {payer_name} evaluation...")
        
        try:
            chart_snippet = (chart_text or "")[:4000]
            all_sources = []
            all_procedure_results = []
            total_input_tokens = 0
            total_output_tokens = 0
            model_id = "unknown"
            
            # Check if we have CPT codes from extraction
            has_cpt_codes = False
            cpt_codes = []
            if extraction_data and extraction_data.get("has_cpt_codes", False):
                has_cpt_codes = True
                cpt_codes = extraction_data.get("cpt", [])
                print(f"[INFO] {payer_name}: CPT codes detected: {cpt_codes}")
            
            # Separate procedures into CPT-associated and non-CPT procedures
            # This allows us to handle mixed cases properly
            cpt_associated_procedures = []
            non_cpt_procedures = []
            
            if has_cpt_codes and cpt_codes:
                # Try to match procedures with CPT codes (basic matching)
                # For now, if CPT codes exist, we'll process some procedures with CPT and others without
                # User can specify mapping, or we use smart matching
                
                # Simple heuristic: if chart has CPT codes, assume first N procedures match
                # where N = number of CPT codes
                num_cpt = len(cpt_codes)
                cpt_associated_procedures = procedures_list[:num_cpt] if num_cpt <= len(procedures_list) else procedures_list
                non_cpt_procedures = procedures_list[num_cpt:] if num_cpt < len(procedures_list) else []
                
                if cpt_associated_procedures:
                    print(f"[INFO] {payer_name}: CPT-associated procedures: {cpt_associated_procedures}")
                if non_cpt_procedures:
                    print(f"[INFO] {payer_name}: Non-CPT procedures (will use RAG): {non_cpt_procedures}")
            else:
                # No CPT codes, all procedures use RAG search
                non_cpt_procedures = procedures_list
            
            # Process CPT-associated procedures with CPT-based flow
            if has_cpt_codes and cpt_codes and cpt_associated_procedures:
                # CPT-BASED FLOW: Direct lookup by CPT codes
                print(f"[INFO] {payer_name}: Using DIRECT CPT lookup (no RAG search) for codes: {cpt_codes}")
                
                # Get guidelines directly for CPT codes
                if Config.DATA_SOURCE == "json" and self.json_loader:
                    print(f"    [INFO] {payer_name}: Direct CPT lookup in JSON guidelines...")
                    hits = self.json_loader.search_by_cpt_codes(payer_key, cpt_codes, Config.TOP_K)
                else:
                    # Use OpenSearch with CPT-specific search
                    payer_filter_terms = payer_config.get("filter_terms", [])
                    print(f"    [INFO] {payer_name}: Direct CPT lookup in OpenSearch...")
                    hits = OpenSearchClient.search_by_cpt_codes(
                        os_index, cpt_codes, payer_filter_terms, Config.TOP_K
                    )
                
                # Process CPT-associated procedures with the CPT guidelines
                for proc_idx, proc_name in enumerate(cpt_associated_procedures, 1):
                    print(f"   {payer_name} [CPT {proc_idx}/{len(cpt_associated_procedures)}]: Evaluating {proc_name} with CPT guidelines")
                    
                    try:
                        # Build context from CPT-specific hits
                        if Config.DATA_SOURCE == "json" and self.json_loader:
                            ctx, srcs, has_guidelines = self.json_loader.build_context_for_procedure(
                                proc_name, hits, Config.MAX_CONTEXT_CHARS // len(procedures_list), payer_key
                            )
                        else:
                            ctx, srcs, has_guidelines = OpenSearchClient.build_context_for_procedure(
                                proc_name, hits, Config.MAX_CONTEXT_CHARS // len(procedures_list), payer_key
                            )
                        all_sources.extend(srcs)
                        
                        # Handle case where no relevant guidelines were found
                        if not has_guidelines or not hits:
                            print(f"    [WARNING] {payer_name}: No CPT guidelines found for {proc_name}, using general guidelines")
                            general_result = self._create_general_guidelines_result(proc_name, payer_name, hits)
                            # Add original procedure name for proper matching
                            general_result["_original_procedure_name"] = proc_name
                            all_procedure_results.append(general_result)
                            continue
                        
                        # Create CPT-based compliance evaluation prompt
                        # Use comprehensive system prompt with payer-specific instructions
                        system_prompt = f"{self.base_system_prompt}\n\nSPECIFIC TASK FOR {payer_name.upper()}:\nUse only the CPT-specific guideline context provided below. Assess compliance strictly against the provided {payer_name} context."
                        
                        user_prompt = self._create_cpt_based_prompt(
                            payer_name, proc_name, cpt_codes, chart_text, ctx
                        )
                        
                        # Call Claude with caching and retry logic
                        max_retries = 3
                        for attempt in range(max_retries):
                            try:
                                raw, usage_info = self.call_claude_with_cache(
                                    user_prompt, 
                                    max_tokens=1200, 
                                    temperature=0.0, 
                                    system_prompt=system_prompt,
                                    cache_type="compliance"
                                )
                                break
                            except Exception as e:
                                if attempt == max_retries - 1:
                                    raise e
                                print(f"    [WARNING] {payer_name}: Claude call failed (attempt {attempt + 1}), retrying...")
                                continue
                        
                        total_input_tokens += usage_info.get("input_tokens", 0)
                        total_output_tokens += usage_info.get("output_tokens", 0)
                        model_id = usage_info.get("model_id", "unknown")
                        
                        # Parse JSON response with enhanced error handling
                        parsed = self._parse_compliance_response(raw, proc_name, payer_name)
                        
                        # Store original procedure name for dashboard matching
                        parsed["_original_procedure_name"] = proc_name
                        
                        # Extract medical chart references from the compliance response
                        chart_references = self._extract_chart_references(parsed)
                        
                        # Build list of CPT-specific guidelines with actual requirements
                        cpt_guidelines_list = []
                        for idx, src in enumerate(srcs, 1):
                            # Get the full source data
                            full_source = src.get("full_source", {})
                            
                            # Extract CPT codes from source - only from matching procedure
                            source_cpt_codes = []
                            
                            # Check if this is a nested structure with procedures array
                            if "procedures" in full_source and isinstance(full_source["procedures"], list):
                                # Nested structure - extract CPT codes only from matching procedure
                                for proc_item in full_source["procedures"]:
                                    if isinstance(proc_item, dict):
                                        # Get codes from this specific procedure
                                        proc_codes = []
                                        if "codes" in proc_item:
                                            for c in proc_item["codes"]:
                                                if isinstance(c, dict):
                                                    proc_codes.append(c.get("code", ""))
                                        
                                        # Only use codes if this procedure matches our input CPT codes
                                        if proc_codes and any(pc in cpt_codes for pc in proc_codes):
                                            source_cpt_codes = proc_codes
                                            break
                            else:
                                # Flat structure - extract from top level
                                # Check top-level codes field
                                if "codes" in full_source and isinstance(full_source["codes"], list):
                                    for code_item in full_source["codes"]:
                                        if isinstance(code_item, dict):
                                            source_cpt_codes.append(code_item.get("code", ""))
                                
                                # Check cpt_codes field
                                if "cpt_codes" in full_source:
                                    cpt_field = full_source["cpt_codes"]
                                    if isinstance(cpt_field, list):
                                        source_cpt_codes.extend([str(c) for c in cpt_field])
                                    elif isinstance(cpt_field, str):
                                        source_cpt_codes.append(str(cpt_field))
                            
                            # If no source codes found, or too many, just use the input CPT codes
                            if not source_cpt_codes or len(source_cpt_codes) > 10:
                                source_cpt_codes = cpt_codes
                            
                            # Extract procedure name (try multiple locations)
                            procedure_name = None
                            
                            # Try top level first
                            if "procedure" in full_source:
                                procedure_name = full_source["procedure"]
                            elif "section_title" in full_source:
                                procedure_name = full_source["section_title"]
                            elif "procedure_id" in full_source:
                                procedure_name = full_source["procedure_id"]
                            
                            # Try within procedures array (for nested structures)
                            if not procedure_name or procedure_name == "Unknown Procedure":
                                if "procedures" in full_source and isinstance(full_source["procedures"], list):
                                    if full_source["procedures"]:
                                        first_proc = full_source["procedures"][0]
                                        if isinstance(first_proc, dict):
                                            procedure_name = (first_proc.get("section_title") or 
                                                           first_proc.get("procedure_id") or
                                                           first_proc.get("names", [""])[0] if "names" in first_proc else None)
                            
                            # Fallback to the procedure we're evaluating
                            if not procedure_name:
                                procedure_name = proc_name
                            
                            # Build meaningful guideline text
                            guideline_parts = []
                            
                            # Check if this is a nested structure with procedures array
                            if "procedures" in full_source and isinstance(full_source["procedures"], list):
                                # Nested structure - extract from first matching procedure
                                for proc_item in full_source["procedures"]:
                                    if isinstance(proc_item, dict):
                                        # Try to match by CPT code or use first one
                                        proc_codes = []
                                        if "codes" in proc_item:
                                            for c in proc_item["codes"]:
                                                if isinstance(c, dict):
                                                    proc_codes.append(c.get("code", ""))
                                        
                                        # Use this procedure if it matches our CPT codes or use first one
                                        if not proc_codes or any(pc in cpt_codes for pc in proc_codes):
                                            # Extract from this procedure
                                            if "description" in proc_item and proc_item["description"]:
                                                guideline_parts.append(f"Description: {proc_item['description']}")
                                            
                                            if "general_requirements" in proc_item:
                                                gen_req = proc_item["general_requirements"]
                                                if isinstance(gen_req, dict) and "documentation" in gen_req:
                                                    doc_list = gen_req["documentation"]
                                                    if isinstance(doc_list, list) and doc_list:
                                                        guideline_parts.append("\nDocumentation Requirements:")
                                                        for req in doc_list:
                                                            guideline_parts.append(f"  • {req}")
                                            
                                            if "exclusions" in proc_item and isinstance(proc_item["exclusions"], list):
                                                if proc_item["exclusions"]:
                                                    guideline_parts.append("\nExclusions:")
                                                    for excl in proc_item["exclusions"]:
                                                        guideline_parts.append(f"  • {excl}")
                                            
                                            if "notes" in proc_item and proc_item["notes"]:
                                                guideline_parts.append(f"\nNotes: {proc_item['notes']}")
                                            
                                            # If we found content, break after first matching procedure
                                            if guideline_parts:
                                                break
                            else:
                                # Flat structure - extract directly
                                if "description" in full_source and full_source["description"]:
                                    guideline_parts.append(f"Description: {full_source['description']}")
                                
                                if "general_requirements" in full_source:
                                    gen_req = full_source["general_requirements"]
                                    if isinstance(gen_req, dict) and "documentation" in gen_req:
                                        doc_list = gen_req["documentation"]
                                        if isinstance(doc_list, list) and doc_list:
                                            guideline_parts.append("\nDocumentation Requirements:")
                                            for req in doc_list:
                                                guideline_parts.append(f"  • {req}")
                                
                                if "exclusions" in full_source and isinstance(full_source["exclusions"], list):
                                    if full_source["exclusions"]:
                                        guideline_parts.append("\nExclusions:")
                                        for excl in full_source["exclusions"]:
                                            guideline_parts.append(f"  • {excl}")
                                
                                if "notes" in full_source and full_source["notes"]:
                                    guideline_parts.append(f"\nNotes: {full_source['notes']}")
                            
                            # Fallback to text field if no structured data found
                            if not guideline_parts and "text" in full_source:
                                guideline_parts.append(full_source["text"][:1000])
                            
                            # Combine all parts
                            if guideline_parts:
                                guideline_content = "\n".join(guideline_parts)
                            else:
                                # Final fallback
                                guideline_content = src.get("description", "No guideline content available")[:1000]
                            
                            # Get guideline ID
                            guideline_id = src.get("record_id", f"Guideline_{idx}")
                            
                            # Get evidence count
                            evidence_refs = src.get("payer_guideline_reference", [])
                            evidence_count = len(evidence_refs) if evidence_refs else 0
                            evidence_summary = f"{evidence_count} PDF reference(s)" if evidence_count > 0 else "No PDF references"
                            
                            cpt_guidelines_list.append({
                                "guideline_id": guideline_id,
                                "procedure_name": procedure_name,
                                "cpt_codes": source_cpt_codes if source_cpt_codes else cpt_codes,
                                "guideline_text": guideline_content,
                                "evidence_count": evidence_count,
                                "evidence_summary": evidence_summary,
                                "score": src.get("score", 0.0)
                            })
                        
                        # Add guideline source tracking
                        parsed["guideline_source"] = "payer"
                        
                        # Add guideline availability info
                        parsed["guideline_availability"] = {
                            "status": "available",
                            "search_hits": len(hits),
                            "max_score": max([float(h.get("_score", 0.0)) for h in hits], default=0.0),
                            "message": f"Found {len(hits)} CPT-specific {payer_name} guidelines for codes: {', '.join(cpt_codes)}"
                        }
                        
                        # Add CPT-specific guidelines list
                        parsed["cpt_specific_guidelines"] = cpt_guidelines_list
                        
                        # Add medical chart references
                        parsed["medical_chart_reference"] = chart_references
                        
                        # Add sources with PDF evidence to this procedure result
                        parsed["sources"] = srcs
                        
                        all_procedure_results.append(parsed)
                        print(f"    [OK] {payer_name}: Completed {proc_name} with CPT guidelines")
                        
                    except Exception as proc_error:
                        # Per-procedure error isolation
                        print(f"    [ERROR] {payer_name}: Error processing {proc_name}: {proc_error}")
                        error_result = self._create_error_result(proc_name, payer_name, str(proc_error))
                        # Add original procedure name for proper matching
                        error_result["_original_procedure_name"] = proc_name
                        all_procedure_results.append(error_result)
            
            # Process non-CPT procedures with PROCEDURE-BASED FLOW (RAG search)
            if non_cpt_procedures:
                # PROCEDURE-BASED FLOW: Use RAG search for procedures without CPT codes
                print(f"[INFO] {payer_name}: Using RAG search for {len(non_cpt_procedures)} additional procedure(s) without CPT codes")
                
                for proc_idx, proc_name in enumerate(non_cpt_procedures, 1):
                    print(f"   {payer_name} [PROC {proc_idx}/{len(non_cpt_procedures)}]: Evaluating {proc_name} with RAG search")
                    
                    try:
                        # Procedure-based RAG search
                        q = f"{proc_name}\n\nChart evidence:\n{chart_snippet}"
                        print(f"    [INFO] {payer_name}: RAG searching for procedure: {proc_name}")
                        
                        # Use JSON loader or OpenSearch based on configuration
                        if Config.DATA_SOURCE == "json" and self.json_loader:
                            print(f"    [INFO] {payer_name}: Searching JSON guidelines...")
                            hits = self.json_loader.search_guidelines(payer_key, q, Config.TOP_K)
                            ctx, srcs, has_guidelines = self.json_loader.build_context_for_procedure(
                                    proc_name, hits, Config.MAX_CONTEXT_CHARS // len(non_cpt_procedures), payer_key
                            )
                        else:
                            # Use OpenSearch
                            payer_filter_terms = payer_config.get("filter_terms", [])
                            hits = OpenSearchClient.search_payer_specific(
                                os_index, q, payer_filter_terms, Config.TOP_K
                            )
                            
                            # Fallback to general search if no payer-specific results
                            if not hits:
                                print(f"    [INFO] {payer_name}: No payer-specific guidelines found, trying general search...")
                                hits = OpenSearchClient.search_general(os_index, q, Config.TOP_K)
                            
                            ctx, srcs, has_guidelines = OpenSearchClient.build_context_for_procedure(
                                    proc_name, hits, Config.MAX_CONTEXT_CHARS // len(non_cpt_procedures), payer_key
                            )
                        all_sources.extend(srcs)
                        
                        # Handle case where no relevant guidelines were found - use general guidelines fallback
                        if not has_guidelines or not hits:
                            print(f"    [WARNING] {payer_name}: No specific guidelines found for {proc_name}, using general guidelines fallback")
                            # Create a result using general guidelines (default to Sufficient)
                            general_result = self._create_general_guidelines_result(proc_name, payer_name, hits)
                            # Add original procedure name for proper matching
                            general_result["_original_procedure_name"] = proc_name
                            all_procedure_results.append(general_result)
                            continue
                        
                        # Create compliance evaluation prompt
                        # Use comprehensive system prompt with payer-specific instructions  
                        system_prompt = f"{self.base_system_prompt}\n\nSPECIFIC TASK FOR {payer_name.upper()}:\nUse only the RAG-retrieved guideline context provided below. Assess compliance strictly against the provided {payer_name} context."
                        
                        # Chart text is already numbered from the beginning
                        # Create user prompt for procedure-based evaluation
                        user_prompt = self._create_procedure_based_prompt(
                            payer_name, proc_name, chart_text, ctx
                        )
                        
                        # Call Claude with caching and retry logic
                        max_retries = 3
                        for attempt in range(max_retries):
                            try:
                                raw, usage_info = self.call_claude_with_cache(
                                    user_prompt, 
                                    max_tokens=1200, 
                                    temperature=0.0, 
                                    system_prompt=system_prompt,
                                    cache_type="compliance"
                                )
                                break
                            except Exception as e:
                                if attempt == max_retries - 1:
                                    raise e
                                print(f"    [WARNING] {payer_name}: Claude call failed (attempt {attempt + 1}), retrying...")
                                continue
                        
                        total_input_tokens += usage_info.get("input_tokens", 0)
                        total_output_tokens += usage_info.get("output_tokens", 0)
                        model_id = usage_info.get("model_id", "unknown")
                        
                        # Parse JSON response with enhanced error handling
                        parsed = self._parse_compliance_response(raw, proc_name, payer_name)
                        
                        # Store original procedure name for dashboard matching
                        parsed["_original_procedure_name"] = proc_name
                        
                        # Extract medical chart references from the compliance response
                        chart_references = self._extract_chart_references(parsed)
                        
                        # Build procedure-based guidelines list (similar to CPT list but from procedure search)
                        procedure_guidelines_list = []
                        for idx, src in enumerate(srcs, 1):
                            full_source = src.get("full_source", {})
                            guideline_id = src.get("record_id", f"Guideline_{idx}")
                            
                            # Extract procedure name (handle nested structures)
                            procedure_name_from_guideline = None
                            if "procedure" in full_source:
                                procedure_name_from_guideline = full_source["procedure"]
                            elif "section_title" in full_source:
                                procedure_name_from_guideline = full_source["section_title"]
                            elif "procedure_id" in full_source:
                                procedure_name_from_guideline = full_source["procedure_id"]
                            elif "procedures" in full_source and isinstance(full_source["procedures"], list):
                                if full_source["procedures"]:
                                    first_proc = full_source["procedures"][0]
                                    if isinstance(first_proc, dict):
                                        procedure_name_from_guideline = (first_proc.get("section_title") or 
                                                                       first_proc.get("procedure_id") or
                                                                       first_proc.get("names", [""])[0] if "names" in first_proc else None)
                            
                            if not procedure_name_from_guideline:
                                procedure_name_from_guideline = proc_name
                            
                            evidence_refs = src.get("payer_guideline_reference", [])
                            evidence_count = len(evidence_refs) if evidence_refs else 0
                            evidence_summary = f"{evidence_count} PDF reference(s)" if evidence_count > 0 else "No PDF references"
                            
                            # Extract structured content (same logic as CPT)
                            guideline_parts = []
                            
                            # Check if nested structure
                            if "procedures" in full_source and isinstance(full_source["procedures"], list):
                                for proc_item in full_source["procedures"]:
                                    if isinstance(proc_item, dict):
                                        if "description" in proc_item and proc_item["description"]:
                                            guideline_parts.append(f"Description: {proc_item['description']}")
                                        if "general_requirements" in proc_item:
                                            gen_req = proc_item["general_requirements"]
                                            if isinstance(gen_req, dict) and "documentation" in gen_req:
                                                doc_list = gen_req["documentation"]
                                                if isinstance(doc_list, list) and doc_list:
                                                    guideline_parts.append("\nDocumentation Requirements:")
                                                    for req in doc_list:
                                                        guideline_parts.append(f"  • {req}")
                                        if "exclusions" in proc_item and isinstance(proc_item["exclusions"], list):
                                            if proc_item["exclusions"]:
                                                guideline_parts.append("\nExclusions:")
                                                for excl in proc_item["exclusions"]:
                                                    guideline_parts.append(f"  • {excl}")
                                        if "notes" in proc_item and proc_item["notes"]:
                                            guideline_parts.append(f"\nNotes: {proc_item['notes']}")
                                        if guideline_parts:
                                            break
                            else:
                                # Flat structure
                                if "description" in full_source and full_source["description"]:
                                    guideline_parts.append(f"Description: {full_source['description']}")
                                if "general_requirements" in full_source:
                                    gen_req = full_source["general_requirements"]
                                    if isinstance(gen_req, dict) and "documentation" in gen_req:
                                        doc_list = gen_req["documentation"]
                                        if isinstance(doc_list, list) and doc_list:
                                            guideline_parts.append("\nDocumentation Requirements:")
                                            for req in doc_list:
                                                guideline_parts.append(f"  • {req}")
                                if "exclusions" in full_source and isinstance(full_source["exclusions"], list):
                                    if full_source["exclusions"]:
                                        guideline_parts.append("\nExclusions:")
                                        for excl in full_source["exclusions"]:
                                            guideline_parts.append(f"  • {excl}")
                                if "notes" in full_source and full_source["notes"]:
                                    guideline_parts.append(f"\nNotes: {full_source['notes']}")
                            
                            if not guideline_parts and "text" in full_source:
                                guideline_parts.append(full_source["text"][:1000])
                            
                            guideline_content = "\n".join(guideline_parts) if guideline_parts else src.get("description", "No content")[:1000]
                            
                            procedure_guidelines_list.append({
                                "guideline_id": guideline_id,
                                "procedure_name": procedure_name_from_guideline,
                                "guideline_text": guideline_content,
                                "evidence_count": evidence_count,
                                "evidence_summary": evidence_summary,
                                "score": src.get("score", 0.0)
                            })
                        
                        # Add guideline source tracking
                        parsed["guideline_source"] = "payer"
                        
                        # Add guideline availability info
                        parsed["guideline_availability"] = {
                            "status": "available",
                            "search_hits": len(hits),
                            "max_score": max([float(h.get("_score", 0.0)) for h in hits], default=0.0),
                            "message": f"Found {len(hits)} relevant {payer_name} guideline chunks for '{proc_name}'"
                        }
                        
                        # Add procedure-based guidelines list
                        parsed["procedure_guidelines"] = procedure_guidelines_list
                        
                        # Add medical chart references
                        parsed["medical_chart_reference"] = chart_references
                        
                        # Add sources with PDF evidence to this procedure result
                        parsed["sources"] = srcs
                        
                        all_procedure_results.append(parsed)
                        print(f"    [OK] {payer_name}: Completed {proc_name}")
                        
                    except Exception as proc_error:
                        # Per-procedure error isolation
                        print(f"    [ERROR] {payer_name}: Error processing {proc_name}: {proc_error}")
                        error_result = self._create_error_result(proc_name, payer_name, str(proc_error))
                        # Add original procedure name for proper matching
                        error_result["_original_procedure_name"] = proc_name
                        all_procedure_results.append(error_result)
            
            usage_info = UsageInfo(
                input_tokens=total_input_tokens,
                output_tokens=total_output_tokens,
                model_id=model_id
            )
            usage_info.calculate_costs(Config.INPUT_COST_PER_1K, Config.OUTPUT_COST_PER_1K)
            
            payer_result = ComplianceResult(
                payer_name=payer_name,
                procedures_evaluated=len(procedures_list),
                procedure_results=all_procedure_results,
                usage=usage_info,
                sources=all_sources
            )
            
            print(f"[OK] {payer_name} evaluation completed successfully")
            return payer_key, payer_result
            
        except Exception as e:
            # Catch-all for payer-level errors
            print(f"[ERROR] {payer_name} evaluation failed: {e}")
            error_result = ComplianceResult(
                payer_name=payer_name,
                procedures_evaluated=0,
                procedure_results=[],
                usage=UsageInfo(),
                sources=[],
                error=str(e)
            )
            return payer_key, error_result
    
    def _create_general_guidelines_result(self, proc_name: str, payer_name: str, general_hits: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create result using general guidelines when payer-specific guidelines are not found."""
        return {
            "procedure_evaluated": proc_name,
            "variant_or_subprocedure": proc_name,
            "policy_name": f"{payer_name} - General Medical Necessity Guidelines",
            "decision": "Sufficient",  # Default to Sufficient when using general guidelines
            "guideline_source": "general",  # Track that general guidelines were used
            "primary_reasons": [
                f"Evaluated using general medical necessity guidelines",
                f"No {payer_name}-specific policy found for {proc_name}"
            ],
            "requirement_checklist": [],
            "timing_validation": {
                "conservative_duration_weeks": "unknown",
                "pt_sessions_completed": "unknown",
                "follow_up_interval": "unknown"
            },
            "contraindications_exclusions": {
                "active_infection": "unclear",
                "severe_arthritis": "unclear",
                "other_contraindications": []
            },
            "coding_implications": {
                "eligible_codes_if_sufficient": [],
                "notes": f"Evaluated using general medical necessity guidelines - {payer_name}-specific policy not available"
            },
            "improvement_recommendations": {
                "documentation_gaps": [f"No {payer_name}-specific guidelines available for {proc_name}"],
                "compliance_actions": [
                    f"Submit to {payer_name} using general medical necessity criteria",
                    f"Consider requesting specific {payer_name} policy for {proc_name}"
                ],
                "priority": "medium"
            },
            "guideline_availability": {
                "status": "general_fallback",
                "search_hits": len(general_hits),
                "max_score": max([float(h.get("_score", 0.0)) for h in general_hits], default=0.0),
                "message": f"Using general medical necessity guidelines - no {payer_name}-specific policy found"
            }
        }
    
    def _create_error_result(self, proc_name: str, payer_name: str, error_msg: str) -> Dict[str, Any]:
        """Create error result for failed procedure evaluation."""
        return {
            "procedure_evaluated": proc_name,
            "variant_or_subprocedure": "Error",
            "policy_name": f"{payer_name} - Error",
            "decision": "Insufficient",  # Default to Insufficient on errors
            "guideline_source": "error",  # Track error state
            "primary_reasons": [f"Error processing procedure: {error_msg}"],
            "requirement_checklist": [],
            "timing_validation": {},
            "contraindications_exclusions": {},
            "coding_implications": {"eligible_codes_if_sufficient": [], "notes": f"{payer_name} - Processing error"},
            "improvement_recommendations": {
                "documentation_gaps": ["Processing error occurred"],
                "compliance_actions": ["Review error and retry processing"],
                "priority": "high"
            }
        }
    
    def _create_cpt_based_prompt(
        self, 
        payer_name: str, 
        proc_name: str, 
        cpt_codes: List[str], 
        numbered_chart: str, 
        ctx: str
    ) -> str:
        """Create CPT-based compliance evaluation prompt."""
        return (
            "Return STRICT JSON ONLY. Do not include any commentary, prefixes, suffixes, or code fences.\n"
            "Schema:\n"
            "{\n"
            '  "procedure_evaluated": "STRING (main procedure category)",\n'
            '  "variant_or_subprocedure": "STRING (specific variant performed)",\n'
            f'  "policy_name": "STRING ({payer_name} policy being evaluated)",\n'
            '  "decision": "Sufficient | Insufficient",\n'
            '  "primary_reasons": ["STRING (reason 1)", "STRING (reason 2)", ...],\n'
            '  "requirement_checklist": [\n'
            '    {\n'
            '      "requirement_id": "STRING (e.g., imaging, conservative_mgmt, etc.)",\n'
            '      "type": "single | multiple",\n'
            '      "status": "met | unmet | unclear",\n'
            '      "evidence": [\n'
            '        {\n'
            '          "line_reference": "STRING (e.g., L012, L013-L015)"\n'
            '        }\n'
            '      ],\n'
            '      "missing_to_meet": "STRING (what is missing if unmet)",\n'
            '      "suggestion": "STRING (specific actionable improvement recommendation based on missing information)"\n'
            '    }\n'
            '  ],\n'
            '  "timing_validation": {\n'
            '    "conservative_duration_weeks": "INT or unknown",\n'
            '    "pt_sessions_completed": "INT or unknown",\n'
            '    "follow_up_interval": "STRING or unknown"\n'
            '  },\n'
            '  "contraindications_exclusions": {\n'
            '    "active_infection": "present | absent | unclear",\n'
            '    "severe_arthritis": "present | absent | unclear",\n'
            '    "other_contraindications": ["STRING", ...]\n'
            '  },\n'
            '  "coding_implications": {\n'
            '    "eligible_codes_if_sufficient": ["STRING (CPT codes)", ...],\n'
            f'    "notes": "STRING ({payer_name} coding context)"\n'
            '  },\n'
            '  "improvement_recommendations": {\n'
            '    "documentation_gaps": ["STRING (specific gaps identified)", ...],\n'
            f'    "compliance_actions": ["STRING (actionable steps to improve {payer_name} compliance)", ...],\n'
            '    "priority": "high | medium | low (based on compliance impact)"\n'
            '  }\n'
            "}\n\n"
            "CRITICAL INSTRUCTIONS FOR CPT-BASED EVALUATION:\n"
            f"- You are evaluating CPT code(s): {', '.join(cpt_codes)}\n"
            f"- ALL {payer_name} guidelines provided below are specifically for these CPT codes\n"
            f"- Review EVERY guideline section provided - they ALL contain requirements for the CPT codes\n"
            f"- Extract requirements from ALL guidelines, not just the first one\n"
            f"- The guidelines below represent the COMPLETE {payer_name} policy for these CPT codes\n\n"
            "Rules:\n"
            f"- Use ONLY the CPT-specific {payer_name} guidelines provided below; do not use external knowledge\n"
            f"- ALL guidelines below are relevant to CPT codes {', '.join(cpt_codes)}\n"
            "- decision='Sufficient' only if ALL required elements across ALL guidelines are evidenced in the medical chart\n"
            "- decision='Insufficient' if ANY required element from ANY guideline is missing/contradicted\n"
            "- decision='Insufficient' if the procedure doesn't match the policy scope\n"
            f"- primary_reasons should list the main issues preventing {payer_name} compliance\n"
            f"- requirement_checklist should include requirements from ALL provided guidelines\n"
            "- Include line numbers (L###) from the medical chart in the evidence field where relevant\n"
            f"- policy_name should clearly identify the {payer_name} CPT policy being evaluated\n"
            "- For suggestions, provide specific actionable recommendations based on what information is missing\n"
            f"- improvement_recommendations should identify gaps and actionable steps for {payer_name} compliance\n\n"
            f"Medical chart with line numbers:\n{numbered_chart}\n\n"
            f"=== ALL {payer_name} GUIDELINES FOR CPT CODES {', '.join(cpt_codes)} ===\n"
            f"The following guidelines represent the complete {payer_name} policy for procedure '{proc_name}' with CPT codes {', '.join(cpt_codes)}.\n"
            f"Review ALL guideline sections below:\n\n{ctx}\n\n"
            f"=== END OF {payer_name} GUIDELINES ===\n"
        )
    
    def _create_procedure_based_prompt(
        self, 
        payer_name: str, 
        proc_name: str, 
        numbered_chart: str, 
        ctx: str
    ) -> str:
        """Create procedure-based compliance evaluation prompt."""
        return (
            "Return STRICT JSON ONLY. Do not include any commentary, prefixes, suffixes, or code fences.\n"
            "Schema:\n"
            "{\n"
            '  "procedure_evaluated": "STRING (main procedure category)",\n'
            '  "variant_or_subprocedure": "STRING (specific variant performed)",\n'
            f'  "policy_name": "STRING ({payer_name} policy being evaluated)",\n'
            '  "decision": "Sufficient | Insufficient",\n'
            '  "primary_reasons": ["STRING (reason 1)", "STRING (reason 2)", ...],\n'
            '  "requirement_checklist": [\n'
            '    {\n'
            '      "requirement_id": "STRING (e.g., imaging, conservative_mgmt, etc.)",\n'
            '      "type": "single | multiple",\n'
            '      "status": "met | unmet | unclear",\n'
            '      "evidence": [\n'
            '        {\n'
            '          "line_reference": "STRING (e.g., L012, L013-L015)"\n'
            '        }\n'
            '      ],\n'
            '      "missing_to_meet": "STRING (what is missing if unmet)",\n'
            '      "suggestion": "STRING (specific actionable improvement recommendation based on missing information)"\n'
            '    }\n'
            '  ],\n'
            '  "timing_validation": {\n'
            '    "conservative_duration_weeks": "INT or unknown",\n'
            '    "pt_sessions_completed": "INT or unknown",\n'
            '    "follow_up_interval": "STRING or unknown"\n'
            '  },\n'
            '  "contraindications_exclusions": {\n'
            '    "active_infection": "present | absent | unclear",\n'
            '    "severe_arthritis": "present | absent | unclear",\n'
            '    "other_contraindications": ["STRING", ...]\n'
            '  },\n'
            '  "coding_implications": {\n'
            '    "eligible_codes_if_sufficient": ["STRING (CPT codes)", ...],\n'
            f'    "notes": "STRING ({payer_name} coding context)"\n'
            '  },\n'
            '  "improvement_recommendations": {\n'
            '    "documentation_gaps": ["STRING (specific gaps identified)", ...],\n'
            f'    "compliance_actions": ["STRING (actionable steps to improve {payer_name} compliance)", ...],\n'
            '    "priority": "high | medium | low (based on compliance impact)"\n'
            '  }\n'
            "}\n\n"
            "Rules:\n"
            f"- Use ONLY the RAG-retrieved {payer_name} guidelines given for this procedure; do not use external knowledge.\n"
            "- decision='Sufficient' only if ALL required elements in those chunks are evidenced in the medical chart.\n"
            "- decision='Insufficient' if ANY required element is missing/contradicted.\n"
            "- decision='Insufficient' if the procedure doesn't match the policy scope.\n"
            f"- primary_reasons should list the main issues preventing {payer_name} compliance.\n"
            f"- requirement_checklist should map to specific {payer_name} policy requirements.\n"
            "- Include line numbers (L###) from the medical chart in the evidence field of requirement_checklist where relevant.\n"
            f"- policy_name should clearly identify which {payer_name} policy is being evaluated.\n"
            "- For suggestions, provide specific actionable recommendations based on what information is missing.\n"
            f"- improvement_recommendations should identify specific gaps and actionable steps for {payer_name} compliance.\n\n"
            f"Medical chart with line numbers:\n{numbered_chart}\n\n"
            f"{payer_name} guideline context for procedure '{proc_name}':\n{ctx}\n"
        )
    
    def _parse_compliance_response(self, raw: str, proc_name: str, payer_name: str) -> Dict[str, Any]:
        """Parse compliance response with error handling."""
        try:
            parsed = json.loads(raw)
            if not isinstance(parsed, dict) or "procedure_evaluated" not in parsed:
                raise ValueError("Unexpected schema")
        except Exception:
            recovered = self._extract_first_json_object(raw)
            try:
                if recovered:
                    parsed = json.loads(recovered)
                else:
                    raise ValueError("No JSON object found")
                if not isinstance(parsed, dict) or "procedure_evaluated" not in parsed:
                    raise ValueError("Unexpected schema after recovery")
            except Exception:
                # Fallback to structured error result
                parsed = {
                    "procedure_evaluated": proc_name,
                    "variant_or_subprocedure": "Unknown",
                    "policy_name": f"{payer_name} - Unknown Policy",
                    "decision": "Sufficient",
                    "primary_reasons": [f"Unparseable model output: {raw[:200]}..."],
                    "requirement_checklist": [],
                    "timing_validation": {},
                    "contraindications_exclusions": {},
                    "coding_implications": {"eligible_codes_if_sufficient": [], "notes": f"{payer_name} - Error in processing"},
                    "improvement_recommendations": {
                        "documentation_gaps": ["Unable to process due to model output error"],
                        "compliance_actions": ["Review and reprocess with corrected data"],
                        "priority": "high"
                    }
                }
        return parsed
    
    def _extract_chart_references(self, parsed_response: Dict[str, Any]) -> List[str]:
        """Extract all medical chart line references (L###) from the compliance response."""
        import re
        chart_refs = []
        
        def extract_from_value(value):
            """Recursively extract line references from any value."""
            if isinstance(value, str):
                # Pattern to match line references like L001, L123, L001-L003, etc.
                pattern = r'L\d{3,}(?:-L\d{3,})?'
                matches = re.findall(pattern, value)
                chart_refs.extend(matches)
            elif isinstance(value, dict):
                for v in value.values():
                    extract_from_value(v)
            elif isinstance(value, list):
                for item in value:
                    extract_from_value(item)
        
        extract_from_value(parsed_response)
        # Remove duplicates while preserving order
        seen = set()
        unique_refs = []
        for ref in chart_refs:
            if ref not in seen:
                seen.add(ref)
                unique_refs.append(ref)
        
        return unique_refs
    
    def _create_multi_payer_prompt(
        self,
        proc_name: str,
        numbered_chart: str,
        payer_guidelines: Dict[str, Dict[str, Any]],
        cpt_codes: Optional[List[str]] = None
    ) -> str:
        """Create a prompt that evaluates one procedure against all payers."""
        sorted_payers = Config.get_sorted_payers()
        payer_names = [payer_config['name'] for _, payer_config in sorted_payers]
        
        # Build the JSON schema showing all payers
        schema_lines = [
            "Return STRICT JSON ONLY. Do not include any commentary, prefixes, suffixes, or code fences.\n",
            "Schema:\n",
            "{\n",
            f'  "{sorted_payers[0][0]}": {{\n',  # First payer key
            '    "procedure_evaluated": "STRING (main procedure category)",\n',
            '    "variant_or_subprocedure": "STRING (specific variant performed)",\n',
            f'    "policy_name": "STRING ({sorted_payers[0][1]["name"]} policy being evaluated)",\n',
            '    "decision": "Sufficient | Insufficient",\n',
            '    "primary_reasons": ["STRING (reason 1)", "STRING (reason 2)", ...],\n',
            '    "requirement_checklist": [\n',
            '      {\n',
            '        "requirement_id": "STRING (e.g., imaging, conservative_mgmt, etc.)",\n',
            '        "type": "single | multiple",\n',
            '        "status": "met | unmet | unclear",\n',
            '        "evidence": [{"line_reference": "STRING (e.g., L012, L013-L015)"}],\n',
            '        "missing_to_meet": "STRING (what is missing if unmet)",\n',
            '        "suggestion": "STRING (specific actionable improvement recommendation)"\n',
            '      }\n',
            '    ],\n',
            '    "timing_validation": {"conservative_duration_weeks": "INT or unknown", "pt_sessions_completed": "INT or unknown", "follow_up_interval": "STRING or unknown"},\n',
            '    "contraindications_exclusions": {"active_infection": "present | absent | unclear", "severe_arthritis": "present | absent | unclear", "other_contraindications": []},\n',
            '    "coding_implications": {"eligible_codes_if_sufficient": ["STRING (CPT codes)", ...], "notes": "STRING"},\n',
            '    "improvement_recommendations": {"documentation_gaps": ["STRING", ...], "compliance_actions": ["STRING", ...], "priority": "high | medium | low"}\n',
            '  },\n'
        ]
        
        # Add remaining payers
        for payer_key, payer_config in sorted_payers[1:]:
            schema_lines.append(f'  "{payer_key}": {{\n')
            schema_lines.append('    "procedure_evaluated": "STRING",\n')
            schema_lines.append('    "variant_or_subprocedure": "STRING",\n')
            schema_lines.append(f'    "policy_name": "STRING ({payer_config["name"]} policy)",\n')
            schema_lines.append('    "decision": "Sufficient | Insufficient",\n')
            schema_lines.append('    "primary_reasons": ["STRING", ...],\n')
            schema_lines.append('    "requirement_checklist": [...],\n')
            schema_lines.append('    "timing_validation": {...},\n')
            schema_lines.append('    "contraindications_exclusions": {...},\n')
            schema_lines.append('    "coding_implications": {...},\n')
            schema_lines.append('    "improvement_recommendations": {...}\n')
            schema_lines.append('  },\n')
        
        schema_lines.append('}\n\n')
        
        # Build guidelines sections for each payer
        guidelines_sections = []
        for payer_key, payer_config in sorted_payers:
            payer_name = payer_config['name']
            guideline_info = payer_guidelines.get(payer_key, {})
            ctx = guideline_info.get("context", "")
            is_cpt_based = guideline_info.get("is_cpt_based", False)
            
            if is_cpt_based and cpt_codes:
                guidelines_sections.append(
                    f"=== {payer_name.upper()} GUIDELINES FOR CPT CODES {', '.join(cpt_codes)} ===\n"
                    f"The following guidelines represent the {payer_name} policy for procedure '{proc_name}' with CPT codes {', '.join(cpt_codes)}.\n"
                    f"Review ALL guideline sections below:\n\n{ctx}\n\n"
                    f"=== END OF {payer_name.upper()} GUIDELINES ===\n\n"
                )
            else:
                guidelines_sections.append(
                    f"=== {payer_name.upper()} GUIDELINES FOR PROCEDURE '{proc_name}' ===\n"
                    f"The following guidelines represent the {payer_name} policy for procedure '{proc_name}'.\n"
                    f"Review ALL guideline sections below:\n\n{ctx}\n\n"
                    f"=== END OF {payer_name.upper()} GUIDELINES ===\n\n"
                )
        
        guidelines_text = "\n".join(guidelines_sections)
        
        # Build instructions
        instructions = [
            "CRITICAL INSTRUCTIONS FOR MULTI-PAYER EVALUATION:\n",
            f"- You are evaluating procedure '{proc_name}' against guidelines from {len(sorted_payers)} payers: {', '.join(payer_names)}\n",
            "- You MUST return a JSON object with keys for EACH payer (cigna, uhc, anthem)\n",
            "- Each payer key should contain the full compliance evaluation result for that payer\n",
            "- Evaluate each payer INDEPENDENTLY using ONLY that payer's guidelines\n",
            "- Do NOT mix requirements between payers\n",
            "- Each payer may have different requirements and decisions\n\n"
        ]
        
        if cpt_codes:
            instructions.append(
                f"- CPT codes being evaluated: {', '.join(cpt_codes)}\n"
                "- Some payers may use CPT-based guidelines, others may use procedure-based guidelines\n"
                "- Use the appropriate guideline type for each payer as provided\n\n"
            )
        
        instructions.extend([
            "Rules for each payer evaluation:\n",
            "- decision='Sufficient' only if ALL required elements from that payer's guidelines are evidenced in the medical chart\n",
            "- decision='Insufficient' if ANY required element from that payer's guidelines is missing/contradicted\n",
            "- primary_reasons should list the main issues preventing compliance with that specific payer\n",
            "- requirement_checklist should include requirements from ALL provided guidelines for that payer\n",
            "- Include line numbers (L###) from the medical chart in the evidence field where relevant\n",
            "- policy_name should clearly identify which policy is being evaluated for that payer\n",
            "- improvement_recommendations should identify gaps and actionable steps for that specific payer's compliance\n\n",
            f"Medical chart with line numbers:\n{numbered_chart}\n\n",
            guidelines_text
        ])
        
        return "".join(schema_lines) + "".join(instructions)
    
    def _parse_multi_payer_response(self, raw: str, proc_name: str, sorted_payers: List[Tuple[str, Dict[str, Any]]]) -> Dict[str, Dict[str, Any]]:
        """Parse multi-payer response containing results for all payers."""
        parsed_results = {}
        
        try:
            # Try to parse JSON directly
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                raise ValueError("Response is not a JSON object")
            
            # Extract results for each payer
            for payer_key, payer_config in sorted_payers:
                payer_name = payer_config['name']
                
                if payer_key in parsed:
                    payer_result = parsed[payer_key]
                    if isinstance(payer_result, dict) and "procedure_evaluated" in payer_result:
                        parsed_results[payer_key] = payer_result
                    else:
                        # Invalid structure, create error result
                        parsed_results[payer_key] = self._create_error_result(
                            proc_name, payer_name, "Invalid response structure"
                        )
                else:
                    # Missing payer, create error result
                    parsed_results[payer_key] = self._create_error_result(
                        proc_name, payer_name, f"Missing '{payer_key}' in response"
                    )
            
        except json.JSONDecodeError:
            # Try to extract JSON object
            recovered = self._extract_first_json_object(raw)
            if recovered:
                try:
                    parsed = json.loads(recovered)
                    if isinstance(parsed, dict):
                        # Extract results for each payer
                        for payer_key, payer_config in sorted_payers:
                            payer_name = payer_config['name']
                            
                            if payer_key in parsed:
                                payer_result = parsed[payer_key]
                                if isinstance(payer_result, dict) and "procedure_evaluated" in payer_result:
                                    parsed_results[payer_key] = payer_result
                                else:
                                    parsed_results[payer_key] = self._create_error_result(
                                        proc_name, payer_name, "Invalid response structure"
                                    )
                            else:
                                parsed_results[payer_key] = self._create_error_result(
                                    proc_name, payer_name, f"Missing '{payer_key}' in response"
                                )
                    else:
                        raise ValueError("Recovered JSON is not an object")
                except Exception as e:
                    # Fallback to error results for all payers
                    for payer_key, payer_config in sorted_payers:
                        parsed_results[payer_key] = self._create_error_result(
                            proc_name, payer_config['name'], f"Failed to parse response: {str(e)}"
                        )
            else:
                # Cannot extract JSON, create error results for all payers
                for payer_key, payer_config in sorted_payers:
                    parsed_results[payer_key] = self._create_error_result(
                        proc_name, payer_config['name'], "No JSON object found in response"
                    )
        
        except Exception as e:
            # Fallback to error results for all payers
            for payer_key, payer_config in sorted_payers:
                parsed_results[payer_key] = self._create_error_result(
                    proc_name, payer_config['name'], f"Failed to parse response: {str(e)}"
                )
        
        return parsed_results
