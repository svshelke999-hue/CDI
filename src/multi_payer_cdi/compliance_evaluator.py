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
    
    def run_extraction(self, chart_text: str, chart_type: str = "operative_note") -> Tuple[str, Dict[str, Any]]:
        """
        Run extraction with caching and CPT detection.
        
        Args:
            chart_text: Medical chart text
            chart_type: Type of chart (operative_note, pre_operative_note, etc.)
        """
        # Use chart-type-specific extraction
        if chart_type == "operative_note":
            extraction_prompt = self._get_operative_extraction_prompt(chart_text)
        elif chart_type == "pre_operative_note":
            extraction_prompt = self._get_pre_operative_extraction_prompt(chart_text)
        elif chart_type == "post_operative_note":
            extraction_prompt = self._get_post_operative_extraction_prompt(chart_text)
        elif chart_type in ["progress_note", "nursing_note"]:
            extraction_prompt = self._get_progress_note_extraction_prompt(chart_text)
        elif chart_type in ["laboratory_report", "imaging_report", "pathology_report", "radiology_report"]:
            extraction_prompt = self._get_report_extraction_prompt(chart_text, chart_type)
        else:
            extraction_prompt = self._get_general_extraction_prompt(chart_text, chart_type)
        
        response, usage_info = self.call_claude_with_cache(
            extraction_prompt, 
            max_tokens=1500,
            temperature=0.0, 
            system_prompt=None, 
            cache_type=f"extraction_{chart_type}"
        )
        
        # Parse and validate extraction response
        try:
            json_str = self._extract_first_json_object(response)
            if json_str:
                parsed_response = json.loads(json_str)
                if isinstance(parsed_response, dict):
                    parsed_response.setdefault("patient_name", "Unknown")
                    parsed_response.setdefault("patient_age", "Unknown")
                    parsed_response.setdefault("chart_specialty", "Unknown")
                    parsed_response.setdefault("cpt", [])
                    parsed_response.setdefault("procedure", [])
                    parsed_response.setdefault("summary", "")
                    parsed_response["chart_type"] = chart_type
                    
                    print(f"[EXTRACTION] Chart Type: {chart_type}")
                    print(f"[EXTRACTION] Patient Name: {parsed_response.get('patient_name', 'Unknown')}")
                    print(f"[EXTRACTION] Patient Age: {parsed_response.get('patient_age', 'Unknown')}")
                    print(f"[EXTRACTION] Chart Specialty: {parsed_response.get('chart_specialty', 'Unknown')}")
                    
                    cpt_codes = parsed_response.get("cpt", [])
                    if cpt_codes and len(cpt_codes) > 0:
                        print(f"[INFO] CPT codes detected: {cpt_codes}")
                        parsed_response["has_cpt_codes"] = True
                    
                    response = json.dumps(parsed_response)
                else:
                    print(f"[WARNING] Extraction response is not a dictionary")
            else:
                print(f"[WARNING] No JSON object found in extraction response")
        except Exception as e:
            print(f"[WARNING] Error parsing extraction response: {e}")
            print(f"[DEBUG] Response preview: {response[:500] if response else 'No response'}")
        
        return response, usage_info
    
    def _get_operative_extraction_prompt(self, chart_text: str) -> str:
        """Get extraction prompt for operative notes (existing prompt)."""
        return """
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
    
    def _get_pre_operative_extraction_prompt(self, chart_text: str) -> str:
        """Get extraction prompt for pre-operative notes."""
        return """
You are a medical coding and CDI specialist.

TASK:
Analyze the following PRE-OPERATIVE note and extract important information for CDI compliance evaluation.

REQUIRED JSON STRUCTURE:
{{
  "patient_name": STRING - Extract patient's full name,
  "patient_age": STRING - Extract age with units,
  "chart_specialty": STRING - Determine specialty,
  "cpt": ARRAY - CPT codes if mentioned, empty array [] if none,
  "procedure": ARRAY - Planned procedures mentioned (may be empty if not yet performed),
  "summary": STRING - Clinical summary,
  "diagnosis": ARRAY - Diagnoses, conditions, indications for surgery,
  "tests": ARRAY - Pre-operative tests performed (labs, imaging, EKG, etc.),
  "reports": ARRAY - Pre-operative reports referenced (imaging reports, lab results, etc.),
  "medications": ARRAY - Current medications,
  "allergies": ARRAY - Known allergies,
  "risk_assessment": STRING - Risk assessment or ASA classification if mentioned
}}

EXTRACTION FOCUS:
- Extract ALL planned procedures (even if not yet performed)
- Extract ALL pre-operative tests (labs, imaging, EKG, cardiac clearance, etc.)
- Extract ALL diagnoses and indications
- Extract ALL reports referenced (imaging, lab, consultation reports)
- Extract medications and allergies
- Extract risk assessments

PRE-OPERATIVE NOTE:
<<<
{chart}
>>>
""".format(chart=smart_truncate_by_words(
            chart_text.strip(),
            max_words=Config.MAX_CHART_WORDS,
            context_words=Config.PROCEDURE_CONTEXT_WORDS,
            prioritize_sections=True
        ))
    
    def _get_post_operative_extraction_prompt(self, chart_text: str) -> str:
        """Get extraction prompt for post-operative notes."""
        return """
You are a medical coding and CDI specialist.

TASK:
Analyze the following POST-OPERATIVE note and extract important information for CDI compliance evaluation.

REQUIRED JSON STRUCTURE:
{{
  "patient_name": STRING - Extract patient's full name,
  "patient_age": STRING - Extract age with units,
  "chart_specialty": STRING - Determine specialty,
  "cpt": ARRAY - CPT codes if mentioned, empty array [] if none,
  "procedure": ARRAY - Procedures performed (from the surgery),
  "summary": STRING - Clinical summary,
  "post_op_complications": ARRAY - Any post-operative complications,
  "vital_signs": STRING - Post-operative vital signs if documented,
  "pain_management": STRING - Pain management approach,
  "discharge_planning": STRING - Discharge planning notes
}}

EXTRACTION FOCUS:
- Extract procedures that were performed
- Extract post-operative complications
- Extract vital signs and recovery status
- Extract pain management information
- Extract discharge planning notes

POST-OPERATIVE NOTE:
<<<
{chart}
>>>
""".format(chart=smart_truncate_by_words(
            chart_text.strip(),
            max_words=Config.MAX_CHART_WORDS,
            context_words=Config.PROCEDURE_CONTEXT_WORDS,
            prioritize_sections=True
        ))
    
    def _get_progress_note_extraction_prompt(self, chart_text: str) -> str:
        """Get extraction prompt for progress notes and nursing notes."""
        return """
You are a medical coding and CDI specialist.

TASK:
Analyze the following PROGRESS NOTE or NURSING NOTE and extract important information for CDI compliance evaluation.

REQUIRED JSON STRUCTURE:
{{
  "patient_name": STRING - Extract patient's full name,
  "patient_age": STRING - Extract age with units,
  "chart_specialty": STRING - Determine specialty,
  "cpt": ARRAY - CPT codes if mentioned, empty array [] if none,
  "procedure": ARRAY - Procedures mentioned (may be empty),
  "summary": STRING - Clinical summary,
  "current_condition": STRING - Current patient condition,
  "vital_signs": STRING - Vital signs documented,
  "medications": ARRAY - Current medications,
  "assessments": ARRAY - Clinical assessments made,
  "interventions": ARRAY - Interventions performed
}}

EXTRACTION FOCUS:
- Extract current patient condition
- Extract vital signs
- Extract medications
- Extract assessments and interventions
- Extract any procedures mentioned

PROGRESS/NURSING NOTE:
<<<
{chart}
>>>
""".format(chart=smart_truncate_by_words(
            chart_text.strip(),
            max_words=Config.MAX_CHART_WORDS,
            context_words=Config.PROCEDURE_CONTEXT_WORDS,
            prioritize_sections=True
        ))
    
    def _get_report_extraction_prompt(self, chart_text: str, chart_type: str) -> str:
        """Get extraction prompt for lab/imaging/pathology reports."""
        report_type_map = {
            "laboratory_report": "LABORATORY",
            "imaging_report": "IMAGING",
            "pathology_report": "PATHOLOGY",
            "radiology_report": "RADIOLOGY"
        }
        report_type = report_type_map.get(chart_type, "REPORT")
        
        return """
You are a medical coding and CDI specialist.

TASK:
Analyze the following {report_type} REPORT and extract important information for CDI compliance evaluation.

REQUIRED JSON STRUCTURE:
{{
  "patient_name": STRING - Extract patient's full name,
  "patient_age": STRING - Extract age with units,
  "chart_specialty": STRING - Determine specialty,
  "cpt": ARRAY - CPT codes if mentioned, empty array [] if none,
  "procedure": ARRAY - Procedures/tests performed (may be empty),
  "summary": STRING - Report summary/findings,
  "test_name": STRING - Name of test/study,
  "results": ARRAY - Key results/findings,
  "impression": STRING - Impression/conclusion if present,
  "recommendations": ARRAY - Recommendations if present
}}

EXTRACTION FOCUS:
- Extract test/study name
- Extract ALL results and findings
- Extract impression/conclusion
- Extract recommendations
- Extract any procedures or tests mentioned

{report_type} REPORT:
<<<
{chart}
>>>
""".format(report_type=report_type, chart=smart_truncate_by_words(
            chart_text.strip(),
            max_words=Config.MAX_CHART_WORDS,
            context_words=Config.PROCEDURE_CONTEXT_WORDS,
            prioritize_sections=True
        ))
    
    def _get_general_extraction_prompt(self, chart_text: str, chart_type: str) -> str:
        """Get extraction prompt for other chart types."""
        return """
You are a medical coding and CDI specialist.

TASK:
Analyze the following medical document (Chart Type: {chart_type}) and extract important information for CDI compliance evaluation.

REQUIRED JSON STRUCTURE:
{{
  "patient_name": STRING - Extract patient's full name,
  "patient_age": STRING - Extract age with units,
  "chart_specialty": STRING - Determine specialty,
  "cpt": ARRAY - CPT codes if mentioned, empty array [] if none,
  "procedure": ARRAY - Procedures mentioned,
  "summary": STRING - Clinical summary,
  "diagnosis": ARRAY - Diagnoses mentioned,
  "key_information": ARRAY - Any other key information relevant for CDI
}}

EXTRACTION FOCUS:
- Extract patient information
- Extract procedures
- Extract diagnoses
- Extract any other key information relevant for CDI compliance

MEDICAL DOCUMENT:
<<<
{chart}
>>>
""".format(chart_type=chart_type, chart=smart_truncate_by_words(
            chart_text.strip(),
            max_words=Config.MAX_CHART_WORDS,
            context_words=Config.PROCEDURE_CONTEXT_WORDS,
            prioritize_sections=True
        ))
    
    def _extract_first_json_object(self, text: str) -> Optional[str]:
        """Extract first JSON object from text with enhanced parsing."""
        if text is None:
            return None
        stripped = text.strip()
        
        # Remove markdown code fences
        if stripped.startswith("```"):
            parts = stripped.split("\n", 1)
            if len(parts) > 1:
                stripped = parts[1]
            else:
                stripped = stripped[3:]
            if stripped.endswith("```"):
                stripped = stripped[:-3]
            stripped = stripped.strip()
        
        # Try to find JSON object start
        start = stripped.find("{")
        if start == -1:
            return None
        
        # Try multiple strategies to extract valid JSON
        strategies = [
            # Strategy 1: Extract from first { to last }
            lambda: self._extract_json_by_depth(stripped, start),
            # Strategy 2: Try to find complete JSON by matching braces more carefully
            lambda: self._extract_json_careful(stripped, start),
            # Strategy 3: Try to extract JSON from code blocks
            lambda: self._extract_json_from_code_blocks(text)
        ]
        
        for strategy in strategies:
            try:
                result = strategy()
                if result:
                    # Validate it's parseable JSON
                    json.loads(result)
                    return result
            except:
                continue
        
        return None
    
    def _extract_json_by_depth(self, text: str, start: int) -> Optional[str]:
        """Extract JSON by tracking brace depth."""
        depth = 0
        in_string = False
        escape = False
        for i in range(start, len(text)):
            ch = text[i]
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
                        return text[start : i + 1]
        return None
    
    def _extract_json_careful(self, text: str, start: int) -> Optional[str]:
        """More careful JSON extraction handling edge cases."""
        import re
        # Try to find the complete JSON object
        # Look for balanced braces
        brace_count = 0
        in_string = False
        escape_next = False
        end_pos = start
        
        for i in range(start, len(text)):
            char = text[i]
            
            if escape_next:
                escape_next = False
                continue
            
            if char == '\\' and in_string:
                escape_next = True
                continue
            
            if char == '"' and not escape_next:
                in_string = not in_string
                continue
            
            if not in_string:
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end_pos = i + 1
                        break
        
        if brace_count == 0 and end_pos > start:
            return text[start:end_pos]
        return None
    
    def _extract_json_from_code_blocks(self, text: str) -> Optional[str]:
        """Extract JSON from markdown code blocks."""
        import re
        # Look for JSON code blocks
        json_pattern = r'```(?:json)?\s*(\{.*?\})\s*```'
        matches = re.findall(json_pattern, text, re.DOTALL)
        if matches:
            return matches[0]
        return None
    
    def evaluate_procedure_for_all_payers(
        self,
        proc_name: str,
        chart_text: str,
        extraction_data: Optional[Dict[str, Any]] = None,
        proc_index: int = 0,
        total_procedures: int = 1,
        other_charts_info: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Evaluate a single procedure against all payers in a single LLM call.
        
        Args:
            proc_name: Name of the procedure to evaluate
            chart_text: Medical chart text with line numbers (operative chart only for multi-chart)
            extraction_data: Extraction data containing CPT codes if available
            proc_index: Index of this procedure (for logging)
            total_procedures: Total number of procedures (for logging)
            other_charts_info: Optional dict with extracted information from other charts for cross-referencing
            
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
            
            # STEP 1: Check CMS General Guidelines FIRST (before payer-specific guidelines)
            print(f"  [CMS_GENERAL] Checking CMS general guidelines for '{proc_name}'...")
            cms_guidelines_context = ""
            cms_sources = []
            cms_has_guidelines = False
            
            try:
                if Config.DATA_SOURCE == "json" and self.json_loader:
                    # Smart CMS search: Use only procedure name, not full chart text
                    # This avoids false matches from unrelated chart content
                    cms_query = proc_name
                    
                    if has_cpt_codes and cpt_codes:
                        # Search with both procedure name and CPT codes
                        cms_hits = self.json_loader.search_cms_general_guidelines(
                            cms_query, cpt_codes, top_k=10, min_relevance_score=15.0
                        )
                    else:
                        # Search with procedure name only
                        cms_hits = self.json_loader.search_cms_general_guidelines(
                            cms_query, None, top_k=10, min_relevance_score=15.0
                        )
                    
                    # LLM-based relevance filtering for top results
                    if cms_hits:
                        cms_hits = self._filter_cms_guidelines_by_relevance(
                            proc_name, cms_hits, extraction_data
                        )
                    
                    # Build CMS context
                    cms_ctx, cms_srcs, cms_has_guidelines = self.json_loader.build_cms_context_for_procedure(
                        proc_name, cms_hits, Config.MAX_CONTEXT_CHARS // 4  # Allocate 25% of context to CMS
                    )
                    cms_guidelines_context = cms_ctx
                    cms_sources = cms_srcs
                    
                    print(f"  [CMS_GENERAL] Found {len(cms_hits)} relevant CMS general guideline(s) after filtering")
                else:
                    print(f"  [WARNING] CMS general guidelines only supported with JSON data source")
            except Exception as e:
                print(f"  [ERROR] Failed to retrieve CMS general guidelines: {e}")
            
            # STEP 2: Collect guidelines for all payers
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
                proc_name, chart_text, payer_guidelines, cpt_codes if has_cpt_codes else None, other_charts_info, cms_guidelines_context
            )
            
            # Make single LLM call for all payers
            print(f"  [LLM] Making single LLM call for all {len(sorted_payers)} payers...")
            
            # Check prompt length (rough estimate: 1 token ≈ 4 characters)
            prompt_length = len(user_prompt)
            estimated_tokens = prompt_length / 4
            print(f"  [DEBUG] Prompt length: {prompt_length:,} chars (~{estimated_tokens:,.0f} tokens)")
            
            # Warn if prompt is very long (Claude 3.7 Sonnet has ~200k context window, but we want to leave room for response)
            if estimated_tokens > 150000:
                print(f"  [WARNING] Prompt is very long ({estimated_tokens:,.0f} tokens). Response may be truncated.")
            
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    # Increase max_tokens for multi-payer responses (need more tokens for JSON output)
                    max_output_tokens = 8000 if other_charts_info else 4000
                    print(f"  [DEBUG] Using max_output_tokens: {max_output_tokens}")
                    raw, usage_info = self.call_claude_with_cache(
                        user_prompt,
                        max_tokens=max_output_tokens,  # Increased for multi-payer response with cross-referencing
                        temperature=0.0,
                        system_prompt=system_prompt,
                        cache_type="compliance"
                    )
                    print(f"  [DEBUG] Response length: {len(raw)} chars, Input tokens: {usage_info.get('input_tokens', 'N/A')}, Output tokens: {usage_info.get('output_tokens', 'N/A')}")
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
                    
                    # Add CMS sources to each payer's procedure result (CMS guidelines are universal)
                    parsed["cms_sources"] = cms_sources
                    parsed["cms_guidelines_context"] = cms_guidelines_context
                    parsed["cms_has_guidelines"] = cms_has_guidelines
                    
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
                "cms_sources": cms_sources,  # Add CMS sources
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
                "cms_sources": [],  # Add CMS sources even on error
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
                # Simplified, UI-friendly bullets (non payer-specific display)
                "policy_needed": [
                    f"Add the payer policy/guideline for: {proc_name}"
                ],
                "cdi_documentation_gaps": [],
                "completion_guidance": [],
                "next_steps": [
                    f"Load the missing policy into the guideline store/index, then re-run evaluation for: {proc_name}"
                ],
            },
            "guideline_availability": {
                "status": "general_fallback",
                "search_hits": len(general_hits),
                "max_score": max([float(h.get("_score", 0.0)) for h in general_hits], default=0.0),
                "message": f"Using general medical necessity guidelines - no {payer_name}-specific policy found"
            }
        }
    
    def _filter_cms_guidelines_by_relevance(
        self,
        proc_name: str,
        cms_hits: List[Dict[str, Any]],
        extraction_data: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Use LLM to filter CMS guidelines and keep only truly relevant ones.
        
        Args:
            proc_name: Procedure name being evaluated
            cms_hits: List of CMS guideline hits from search
            extraction_data: Optional extraction data with diagnosis, etc.
            
        Returns:
            Filtered list of relevant CMS guidelines
        """
        if not cms_hits or len(cms_hits) == 0:
            return []
        
        # If we have many results, only check top 10 for relevance
        hits_to_check = cms_hits[:10]
        
        # Build context about the procedure
        procedure_context = f"Procedure: {proc_name}"
        
        # Determine procedure type (treatment vs diagnosis coding)
        proc_lower = proc_name.lower()
        is_treatment_procedure = any(term in proc_lower for term in [
            'therapy', 'treatment', 'application', 'placement', 'insertion', 'removal',
            'repair', 'revision', 'replacement', 'aspiration', 'drainage', 'injection',
            'surgery', 'procedure', 'operation', 'excision', 'resection'
        ])
        
        procedure_type_note = ""
        if is_treatment_procedure:
            procedure_type_note = "\nNOTE: This is a TREATMENT PROCEDURE (not a diagnosis). Guidelines about diagnosis coding/staging are NOT relevant unless they specifically relate to documenting the procedure itself."
        
        if extraction_data:
            diagnoses = extraction_data.get("diagnosis", [])
            if diagnoses:
                procedure_context += f"\nRelated Diagnoses: {', '.join(diagnoses[:3])}"
        
        # Build list of guideline titles with summaries to check
        guideline_list = []
        for idx, hit in enumerate(hits_to_check, 1):
            source = hit.get("_source", {})
            title = source.get("semantic_title", "Unknown")
            guideline_id = source.get("guideline_id", "")
            score = hit.get("_score", 0.0)
            summary = source.get("content", {}).get("summary", "")
            # Get first 150 chars of summary for context
            summary_preview = summary[:150] + "..." if len(summary) > 150 else summary
            guideline_list.append(f"{idx}. {title} (ID: {guideline_id}, Score: {score:.1f})\n   Summary: {summary_preview}")
        
        # Create LLM prompt to determine relevance
        relevance_prompt = f"""You are a medical coding expert evaluating CMS general guidelines for relevance to a specific procedure.

{procedure_context}{procedure_type_note}

Below are CMS general guidelines that were retrieved by a search algorithm. Your task is to identify which guidelines are ACTUALLY RELEVANT to this procedure.

CMS Guidelines Retrieved:
{chr(10).join(guideline_list)}

CRITICAL DISTINCTIONS:
1. TREATMENT PROCEDURES (like "{proc_name}") need guidelines about:
   - Procedure documentation requirements
   - Coding the procedure itself
   - General coding principles that apply to procedures
   - Laterality coding (if procedure specifies left/right)
   - NOT diagnosis coding/staging guidelines (unless they relate to documenting the procedure indication)

2. DIAGNOSIS CODING GUIDELINES are relevant ONLY if:
   - They relate to documenting the indication/reason for the procedure
   - They are general principles that apply to all procedures
   - They are NOT relevant if they're about coding/staging a condition that the procedure treats

3. AVOID FALSE MATCHES:
   - "Negative Pressure Wound Therapy" ≠ "Pressure Ulcer" coding guidelines
   - "Joint Aspiration" ≠ "Coma" coding guidelines
   - Treatment procedures ≠ Diagnosis staging guidelines
   - Word similarity ≠ Semantic relevance

INSTRUCTIONS:
1. Review each guideline title and summary
2. Determine if it is TRULY RELEVANT to the procedure "{proc_name}"
3. A guideline is RELEVANT if it:
   - Directly relates to coding/documentation for this type of procedure
   - Covers coding rules that would apply to this procedure
   - Contains general coding principles applicable to procedures (e.g., laterality)
   - Addresses documentation requirements for procedures
4. A guideline is NOT RELEVANT if it:
   - Is about diagnosis coding/staging for conditions the procedure treats (unless it relates to documenting the indication)
   - Is about completely unrelated medical conditions
   - Only matches because of word similarity, not semantic relevance
   - Covers coding rules that don't apply to this procedure type

Be STRICT - only include guidelines that are genuinely relevant. When in doubt, exclude it.

Return ONLY a JSON array of the guideline numbers (1, 2, 3, etc.) that are RELEVANT.
Example: {{"relevant_guidelines": [1, 3]}} means only guidelines 1 and 3 are relevant.

Return format (JSON only, no other text):
{{"relevant_guidelines": [1, 2, 3]}}"""

        try:
            # Call LLM to determine relevance
            response, _ = self.call_claude_with_cache(
                relevance_prompt,
                max_tokens=500,
                temperature=0.0,
                system_prompt="You are a medical coding expert. Return only valid JSON.",
                cache_type="cms_relevance"
            )
            
            # Parse response
            import json
            parsed = json.loads(response)
            relevant_indices = parsed.get("relevant_guidelines", [])
            
            # Filter hits based on LLM response (indices are 1-based)
            filtered_hits = []
            for idx, hit in enumerate(hits_to_check, 1):
                if idx in relevant_indices:
                    filtered_hits.append(hit)
            
            # If LLM filtered everything out, keep at least the top result if score is high
            if not filtered_hits and hits_to_check:
                top_hit = hits_to_check[0]
                if top_hit.get("_score", 0) >= 30.0:  # Keep if high confidence
                    print(f"  [CMS_GENERAL] LLM filtered all results, keeping top result with high score")
                    filtered_hits = [top_hit]
            
            # Add remaining hits (beyond top 10) if we have space
            if len(filtered_hits) < 5 and len(cms_hits) > 10:
                # Add next few high-scoring hits
                for hit in cms_hits[10:15]:
                    if hit.get("_score", 0) >= 25.0:  # Only high-scoring ones
                        filtered_hits.append(hit)
                        if len(filtered_hits) >= 5:
                            break
            
            print(f"  [CMS_GENERAL] LLM relevance check: {len(hits_to_check)} checked, {len(filtered_hits)} relevant")
            return filtered_hits
            
        except Exception as e:
            print(f"  [WARNING] LLM relevance filtering failed: {e}, using original results")
            # Fallback: return top results with high scores only
            return [h for h in hits_to_check if h.get("_score", 0) >= 20.0]
    
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
            '    "policy_needed": ["STRING (if any policy/guideline is missing or ambiguous; keep short)", ...],\n'
            '    "cdi_documentation_gaps": ["STRING (specific missing documentation item; include what exactly is missing + any numbers/dates/measurements needed)", ...],\n'
            '    "completion_guidance": ["STRING (how to document it; where to add it in note; be concise)", ...],\n'
            '    "next_steps": ["STRING (operational next action; concise, no repeated phrasing)", ...],\n'
            '    "summary_recommendations": ["STRING (top 3–5 MOST IMPORTANT, concise, non-duplicated, procedure-specific clinical documentation improvements the provider should make; no category labels like \\"CDI gap\\" or \\"Next step\\")", ...]\n'
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
            f"- improvement_recommendations MUST be BULLET STRINGS ONLY (policy_needed, cdi_documentation_gaps, completion_guidance, next_steps, summary_recommendations).\n"
            "- Do NOT mention payer names in these bullets.\n"
            "- Do NOT use repetitive starter words like 'Appropriate' or 'Request'.\n\n"
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
            '    "policy_needed": ["STRING (if any policy/guideline is missing or ambiguous; keep short)", ...],\n'
            '    "cdi_documentation_gaps": ["STRING (specific missing documentation item; include what exactly is missing + any numbers/dates/measurements needed)", ...],\n'
            '    "completion_guidance": ["STRING (how to document it; where to add it in note; be concise)", ...],\n'
            '    "next_steps": ["STRING (operational next action; concise, no repeated phrasing)", ...],\n'
            '    "summary_recommendations": ["STRING (top 3–5 MOST IMPORTANT, concise, non-duplicated, procedure-specific clinical documentation improvements the provider should make; no category labels like \\"CDI gap\\" or \\"Next step\\")", ...]\n'
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
            f"- improvement_recommendations MUST be BULLET STRINGS ONLY (policy_needed, cdi_documentation_gaps, completion_guidance, next_steps, summary_recommendations).\n"
            "- Do NOT mention payer names in these bullets.\n"
            "- Do NOT use repetitive starter words like 'Appropriate' or 'Request'.\n\n"
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
        cpt_codes: Optional[List[str]] = None,
        other_charts_info: Optional[Dict[str, Any]] = None,
        cms_guidelines_context: str = ""
    ) -> str:
        """Create a prompt that evaluates one procedure against all payers."""
        sorted_payers = Config.get_sorted_payers()
        payer_names = [payer_config['name'] for _, payer_config in sorted_payers]
        
        # Build the JSON schema showing all payers
        schema_lines = [
            "╔══════════════════════════════════════════════════════════════════════════════╗\n",
            "║ CRITICAL: RETURN ONLY VALID JSON - NO TEXT BEFORE OR AFTER                    ║\n",
            "║ Start your response with { and end with } - nothing else                      ║\n",
            "║ Do NOT include: markdown code fences (```), explanations, or any other text  ║\n",
            "╚══════════════════════════════════════════════════════════════════════════════╝\n\n",
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
            '    "improvement_recommendations": {\n',
            '      "policy_needed": ["STRING", ...],\n',
            '      "cdi_documentation_gaps": ["STRING", ...],\n',
            '      "completion_guidance": ["STRING", ...],\n',
            '      "next_steps": ["STRING", ...]\n',
            '    }\n',
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
        
        # Build CMS general guidelines section FIRST (before payer-specific guidelines)
        cms_section = ""
        if cms_guidelines_context:
            cms_section = (
                "=" * 80 + "\n"
                "CMS GENERAL GUIDELINES (CHECK THESE FIRST)\n"
                "=" * 80 + "\n"
                "\n"
                "IMPORTANT: Before evaluating payer-specific guidelines, ensure compliance\n"
                "with CMS general coding guidelines. These are universal requirements that\n"
                "apply to all payers and must be satisfied regardless of payer-specific policies.\n"
                "\n"
                f"{cms_guidelines_context}\n"
                "\n"
                "=" * 80 + "\n"
                "\n"
            )
        
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
            "- EVALUATION ORDER: FIRST check compliance with CMS general guidelines, THEN check payer-specific guidelines\n",
            "- CMS general guidelines are universal requirements that apply to ALL payers\n",
            "- If CMS general guidelines are not met, the procedure may be insufficient regardless of payer-specific compliance\n",
            "- You MUST return a JSON object with keys for EACH payer (cigna, uhc, anthem)\n",
            "- Each payer key should contain the full compliance evaluation result for that payer\n",
            "- Evaluate each payer INDEPENDENTLY using ONLY that payer's guidelines\n",
            "- Do NOT mix requirements between payers\n",
            "- Each payer may have different requirements and decisions\n",
            "- improvement_recommendations MUST be BULLET STRINGS ONLY (policy_needed, cdi_documentation_gaps, completion_guidance, next_steps).\n",
            "- Do NOT mention payer names in these bullets.\n",
            "- Do NOT generate repetitive phrases like 'Appropriate ... guidelines' or 'Request ... guidelines'.\n\n"
        ]
        
        if cpt_codes:
            instructions.append(
                f"- CPT codes being evaluated: {', '.join(cpt_codes)}\n"
                "- Some payers may use CPT-based guidelines, others may use procedure-based guidelines\n"
                "- Use the appropriate guideline type for each payer as provided\n\n"
            )
        
        # Add cross-reference information from other charts if available
        cross_reference_section = ""
        if other_charts_info:
            cross_reference_section = "\n=== INFORMATION FROM RELATED CHARTS (for cross-referencing) ===\n"
            cross_reference_section += "The following information has been extracted from other related charts (pre-operative, post-operative, etc.).\n"
            cross_reference_section += "When evaluating compliance and generating recommendations, you MUST:\n"
            cross_reference_section += "1. Check if required information exists in these other charts\n"
            cross_reference_section += "2. If information exists in other charts, DO NOT flag it as a gap in improvement_recommendations\n"
            cross_reference_section += "3. Only flag gaps if the information is truly missing from ALL charts (operative + other charts)\n"
            cross_reference_section += "4. In your evaluation, you can reference that information exists in other charts\n\n"
            
            for chart_file, chart_info in other_charts_info.items():
                chart_type = chart_info.get("chart_type", "unknown")
                cross_reference_section += f"--- {chart_file} (Type: {chart_type}) ---\n"
                
                # Add summary (most important - contains key clinical info)
                if chart_info.get("summary"):
                    summary_text = chart_info['summary']
                    cross_reference_section += f"Summary: {summary_text}\n"
                    # Quick inference notes
                    summary_lower = summary_text.lower()
                    notes = []
                    if any(word in summary_lower for word in ["conservative", "management", "therapy", "physical therapy", "pt"]):
                        notes.append("conservative management mentioned")
                    if any(word in summary_lower for word in ["pain", "symptom", "limited range"]):
                        notes.append("symptoms documented")
                    if any(word in summary_lower for word in ["failed", "tried", "attempted"]):
                        notes.append("treatment attempted")
                    if notes:
                        cross_reference_section += f"→ Info present: {', '.join(notes)}\n"
                    cross_reference_section += "\n"
                
                # Add diagnosis (concise)
                if chart_info.get("diagnosis"):
                    diagnosis_list = chart_info['diagnosis']
                    if isinstance(diagnosis_list, list):
                        cross_reference_section += f"Diagnosis: {', '.join(diagnosis_list[:5])}\n"  # Limit to 5
                    else:
                        cross_reference_section += f"Diagnosis: {diagnosis_list}\n"
                
                # Add tests (concise)
                if chart_info.get("tests"):
                    tests_list = chart_info['tests']
                    if isinstance(tests_list, list):
                        cross_reference_section += f"Tests: {', '.join(tests_list[:8])}\n"  # Limit to 8
                    else:
                        cross_reference_section += f"Tests: {tests_list}\n"
                
                # Add reports (key findings only)
                if chart_info.get("reports"):
                    reports = chart_info['reports']
                    if isinstance(reports, list):
                        # Show first 3 most relevant reports
                        for report in reports[:3]:
                            cross_reference_section += f"Report: {report[:200]}\n"  # Truncate long reports
                    else:
                        cross_reference_section += f"Reports: {str(reports)[:300]}\n"
                
                # Add medications (concise)
                if chart_info.get("medications"):
                    meds_list = chart_info['medications']
                    if isinstance(meds_list, list):
                        cross_reference_section += f"Medications: {', '.join(meds_list)}\n"
                    else:
                        cross_reference_section += f"Medications: {meds_list}\n"
                
                # Add conservative treatment (if exists)
                if chart_info.get("conservative_treatment"):
                    conservative = chart_info['conservative_treatment']
                    if isinstance(conservative, dict):
                        # Show key fields only
                        key_fields = {k: v for k, v in list(conservative.items())[:3]}
                        cross_reference_section += f"Conservative Treatment: {json.dumps(key_fields)}\n"
                    else:
                        cross_reference_section += f"Conservative Treatment: {str(conservative)[:200]}\n"
                
                # Add physical exam (if exists, concise)
                if chart_info.get("physical_exam"):
                    physical_exam = chart_info['physical_exam']
                    if isinstance(physical_exam, dict):
                        key_fields = {k: v for k, v in list(physical_exam.items())[:3]}
                        cross_reference_section += f"Physical Exam: {json.dumps(key_fields)}\n"
                    else:
                        cross_reference_section += f"Physical Exam: {str(physical_exam)[:200]}\n"
                
                # Add functional limitations (if exists, concise)
                if chart_info.get("functional_limitations"):
                    func_lim = chart_info['functional_limitations']
                    if isinstance(func_lim, dict):
                        key_fields = {k: v for k, v in list(func_lim.items())[:3]}
                        cross_reference_section += f"Functional Limitations: {json.dumps(key_fields)}\n"
                    else:
                        cross_reference_section += f"Functional Limitations: {str(func_lim)[:200]}\n"
                
                cross_reference_section += "\n"
            
            cross_reference_section += "=== END OF RELATED CHARTS INFORMATION ===\n\n"
        
        # Enhanced instructions with explicit cross-referencing rules
        cross_ref_instructions = ""
        if other_charts_info:
            cross_ref_instructions = """
╔══════════════════════════════════════════════════════════════════════════════╗
║ CRITICAL: CROSS-REFERENCE CHECKING RULES FOR RECOMMENDATIONS                 ║
╚══════════════════════════════════════════════════════════════════════════════╝

BEFORE flagging ANY gap in improvement_recommendations.documentation_gaps or 
improvement_recommendations.compliance_actions, you MUST perform this 3-step check:

STEP 1: Check operative chart for the information
STEP 2: If NOT in operative chart, check ALL related charts below
STEP 3: If information exists in ANY related chart → DO NOT flag as gap

╔══════════════════════════════════════════════════════════════════════════════╗
║ EXAMPLES OF SMART CROSS-REFERENCING (CRITICAL TO FOLLOW)                     ║
╚══════════════════════════════════════════════════════════════════════════════╝

Example 1 - Conservative Management:
  ❌ WRONG: Flag "duration of conservative management not specified" as gap
  ✅ CORRECT: If related chart says "failed conservative management including 
              physical therapy, NSAIDs, and corticosteroid injections" → 
              DO NOT flag duration gap (it implies management was tried)
              Set status to "unclear" or "met", NOT "unmet"

Example 2 - Imaging:
  ❌ WRONG: Flag "advanced imaging not documented" as gap
  ✅ CORRECT: If related chart has "MRI Right Shoulder report showing 
              full-thickness rotator cuff tear" → DO NOT flag imaging gap
              Set status to "met"

Example 3 - Medications:
  ❌ WRONG: Flag "NSAIDs not documented" as gap
  ✅ CORRECT: If related chart lists "Ibuprofen 600mg TID" → DO NOT flag 
              medication gap (Ibuprofen IS an NSAID)

Example 4 - Symptoms:
  ❌ WRONG: Flag "function-limiting pain not documented" as gap
  ✅ CORRECT: If related chart mentions "right shoulder pain and limited 
              range of motion" → DO NOT flag symptom gap
              Set status to "met" or "unclear"

Example 5 - Tests:
  ❌ WRONG: Flag "impingement tests not documented" as gap
  ✅ CORRECT: If related chart has test results or mentions tests performed →
              DO NOT flag test gaps

╔══════════════════════════════════════════════════════════════════════════════╗
║ INTELLIGENT INFERENCE RULES                                                  ║
╚══════════════════════════════════════════════════════════════════════════════╝

- "Failed conservative management" = management was tried → don't flag as completely missing
- Test reports exist = tests were performed → don't flag test gaps
- Medications listed = medication management was tried → don't flag medication gaps
- Summary mentions symptoms = symptoms documented → don't flag symptom gaps
- Diagnosis listed = condition documented → don't flag diagnosis gaps
- Reports mention findings = findings documented → don't flag finding gaps

╔══════════════════════════════════════════════════════════════════════════════╗
║ WHEN INFORMATION EXISTS IN RELATED CHARTS:                                   ║
╚══════════════════════════════════════════════════════════════════════════════╝

1. Set requirement_checklist status to "met" or "unclear" (NEVER "unmet")
2. In evidence field, add: "Information available in related chart: [chart name]"
3. DO NOT include in improvement_recommendations.documentation_gaps
4. DO NOT include in improvement_recommendations.compliance_actions
5. DO NOT include in primary_reasons as a missing element
6. You CAN mention in primary_reasons: "Some details may be in related charts"

ONLY flag gaps if information is COMPLETELY ABSENT from BOTH operative AND all related charts.

"""
        
        instructions.extend([
            "Rules for each payer evaluation:\n",
            "- decision='Sufficient' only if ALL required elements from that payer's guidelines are evidenced in the medical chart OR in related charts\n",
            "- decision='Insufficient' if ANY required element from that payer's guidelines is missing/contradicted in BOTH the operative chart AND related charts\n",
            "- primary_reasons should list the main issues preventing compliance with that specific payer\n",
            "- requirement_checklist should include requirements from ALL provided guidelines for that payer\n",
            "- Include line numbers (L###) from the medical chart in the evidence field where relevant\n",
            "- policy_name should clearly identify which policy is being evaluated for that payer\n",
            "- improvement_recommendations should identify gaps ONLY if information is missing from BOTH the operative chart AND related charts\n",
            "- If information exists in related charts, mention it in evidence but DO NOT flag it as a gap\n",
            cross_ref_instructions,
            cross_reference_section,
            f"OPERATIVE CHART (primary chart for CDI evaluation) with line numbers:\n{numbered_chart}\n\n",
            "FINAL REMINDER: Before adding ANY item to improvement_recommendations.documentation_gaps or compliance_actions, verify it is NOT mentioned in the related charts section above. If it exists in related charts (even implicitly), DO NOT flag it as a gap.\n\n",
            cms_section,  # Add CMS general guidelines section FIRST
            guidelines_text,  # Then payer-specific guidelines
            "\n\n╔══════════════════════════════════════════════════════════════════════════════╗\n",
            "║ FINAL INSTRUCTION: Return ONLY the JSON object - start with {{ and end with }} ║\n",
            "║ NO markdown, NO code fences, NO explanations - JUST the JSON object          ║\n",
            "╚══════════════════════════════════════════════════════════════════════════════╝\n"
        ])
        
        return "".join(schema_lines) + "".join(instructions)
    
    def _parse_multi_payer_response(self, raw: str, proc_name: str, sorted_payers: List[Tuple[str, Dict[str, Any]]]) -> Dict[str, Dict[str, Any]]:
        """Parse multi-payer response containing results for all payers."""
        parsed_results = {}

        def _normalize_payer_key(k: Any) -> str:
            try:
                return str(k).strip().lower().replace(" ", "").replace("-", "").replace("_", "")
            except Exception:
                return ""

        def _unwrap_container(obj: Any) -> Any:
            """Handle common wrapper shapes like {'payer_results': {...}}."""
            if not isinstance(obj, dict):
                return obj
            for container_key in ("payer_results", "payers", "results", "evaluations"):
                if container_key in obj and isinstance(obj[container_key], dict):
                    return obj[container_key]
            return obj

        expected_norm_keys = set()
        for payer_key, payer_config in sorted_payers:
            expected_norm_keys.add(_normalize_payer_key(payer_key))
            expected_norm_keys.add(_normalize_payer_key(payer_config.get("name", "")))

        def _coverage_score(obj: Any) -> int:
            """How many expected payer keys this candidate contains (case/format insensitive)."""
            if not isinstance(obj, dict):
                return 0
            keys = set(_normalize_payer_key(k) for k in obj.keys())
            # Count payer_key matches (not payer_name variants) more strongly by using expected_norm_keys.
            return len(keys.intersection(expected_norm_keys))

        def _extract_best_json_candidate(text: str) -> Optional[Dict[str, Any]]:
            """
            When the LLM response is malformed, we may recover multiple JSON objects.
            Choose the candidate that covers the most payer keys (and is longest as tie-breaker).
            """
            import re

            candidates: List[str] = []
            first = self._extract_first_json_object(text)
            if first:
                candidates.append(first)

            # Grab JSON-like objects; we'll parse and score them.
            json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
            matches = re.findall(json_pattern, text, re.DOTALL)
            # Prefer longer candidates first (often the full multi-payer object)
            candidates.extend(sorted(matches, key=len, reverse=True))

            best_obj: Optional[Dict[str, Any]] = None
            best_score = -1
            best_len = -1

            seen = set()
            for cand in candidates:
                if cand in seen:
                    continue
                seen.add(cand)
                try:
                    fixed = self._fix_json_common_issues(cand)
                    obj = _unwrap_container(json.loads(fixed))
                    if not isinstance(obj, dict):
                        continue
                    score = _coverage_score(obj)
                    if score > best_score or (score == best_score and len(cand) > best_len):
                        best_obj = obj
                        best_score = score
                        best_len = len(cand)
                    # Early exit if we likely have full coverage
                    if best_score >= 3:  # current project has 3 payers; safe heuristic
                        break
                except Exception:
                    continue

            return best_obj
        
        try:
            # Try to parse JSON directly
            parsed = _unwrap_container(json.loads(raw))
            if not isinstance(parsed, dict):
                raise ValueError("Response is not a JSON object")

            # Build a normalized lookup to tolerate casing/format differences (e.g., "Cigna" vs "cigna")
            normalized_map = {_normalize_payer_key(k): k for k in parsed.keys()}
            
            # Extract results for each payer
            for payer_key, payer_config in sorted_payers:
                payer_name = payer_config['name']

                # Try exact key first, then common variants
                candidate_keys = [payer_key]
                norm = _normalize_payer_key(payer_key)
                if norm in normalized_map:
                    candidate_keys.append(normalized_map[norm])
                name_norm = _normalize_payer_key(payer_name)
                if name_norm in normalized_map:
                    candidate_keys.append(normalized_map[name_norm])
                # Deduplicate while preserving order
                seen = set()
                candidate_keys = [k for k in candidate_keys if not (k in seen or seen.add(k))]

                found_key = next((k for k in candidate_keys if k in parsed), None)

                if found_key is not None:
                    payer_result = parsed[found_key]
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
            
        except json.JSONDecodeError as json_err:
            # Log the error for debugging
            print(f"[WARNING] JSON decode error: {json_err}")
            print(f"[DEBUG] Response length: {len(raw)} characters")
            print(f"[DEBUG] Response preview (first 1000 chars): {raw[:1000]}")
            print(f"[DEBUG] Response preview (last 1000 chars): {raw[-1000:]}")
            
            best_obj = _extract_best_json_candidate(raw)

            if best_obj:
                try:
                    parsed = best_obj
                    if isinstance(parsed, dict):
                        normalized_map = {_normalize_payer_key(k): k for k in parsed.keys()}
                        # Extract results for each payer
                        for payer_key, payer_config in sorted_payers:
                            payer_name = payer_config['name']

                            candidate_keys = [payer_key]
                            norm = _normalize_payer_key(payer_key)
                            if norm in normalized_map:
                                candidate_keys.append(normalized_map[norm])
                            name_norm = _normalize_payer_key(payer_name)
                            if name_norm in normalized_map:
                                candidate_keys.append(normalized_map[name_norm])
                            seen = set()
                            candidate_keys = [k for k in candidate_keys if not (k in seen or seen.add(k))]

                            found_key = next((k for k in candidate_keys if k in parsed), None)

                            if found_key is not None:
                                payer_result = parsed[found_key]
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
                    # Log the recovery attempt error
                    print(f"[WARNING] Failed to parse recovered JSON: {e}")
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
    
    def _fix_json_common_issues(self, json_str: str) -> str:
        """Fix common JSON issues that cause parsing errors."""
        import re
        fixed = json_str
        
        # Fix trailing commas before closing braces/brackets
        fixed = re.sub(r',(\s*[}\]])', r'\1', fixed)
        
        # Remove control characters except newline, tab, carriage return
        fixed = ''.join(char for char in fixed if ord(char) >= 32 or char in '\n\r\t')
        
        return fixed
