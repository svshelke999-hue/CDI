"""
Medical Chart Improvement module for Multi-Payer CDI Compliance Checker.
This module analyzes CDI recommendations and generates improved medical charts.
"""

import json
from typing import Dict, Any, List, Tuple, Optional
from .bedrock_client import BedrockClient
from .cache_manager import CacheManager
from .config import Config
from .logger import CDILogger
from .models import ProcessingResult


class ChartImprover:
    """Handles medical chart improvement based on CDI recommendations."""
    
    def __init__(self, cache_manager: CacheManager):
        self.cache_manager = cache_manager
    
    def call_claude_with_cache(
        self, 
        prompt: str, 
        max_tokens: int = 3000, 
        temperature: float = 0.1, 
        system_prompt: Optional[str] = None
    ) -> Tuple[str, Dict[str, Any]]:
        """Call Claude with caching support for chart improvement."""
        cache_key = self.cache_manager.get_cache_key(prompt, system_prompt, max_tokens, temperature)
        
        # Try to load from cache first
        cached_result = self.cache_manager.load_from_cache(cache_key)
        if cached_result:
            response, usage_info = cached_result
            print(f"[CACHE] Cache HIT for chart_improvement prompt")
            self.cache_manager.update_cache_stats("chart_improvement", True)
            return response, usage_info
        
        # Cache miss - call Claude
        print(f"[CACHE] Cache MISS for chart_improvement prompt - calling Claude")
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
            purpose="chart_improvement"
        )
        
        # Save to cache
        self.cache_manager.save_to_cache(cache_key, response, usage_info)
        self.cache_manager.update_cache_stats("chart_improvement", False)
        
        return response, usage_info
    
    def improve_medical_chart(
        self, 
        original_chart: str, 
        processing_result: ProcessingResult
    ) -> Dict[str, Any]:
        """
        Generate an improved medical chart based on CDI recommendations.
        
        Args:
            original_chart: Original medical chart text
            processing_result: ProcessingResult with compliance evaluation
            
        Returns:
            Dictionary containing improved chart and metadata
        """
        print("[CHART IMPROVEMENT] Starting medical chart improvement process...")
        
        # Extract all recommendations from all payers
        all_recommendations = self._extract_all_recommendations(processing_result)
        
        # Create comprehensive improvement prompt
        system_prompt = """You are an expert medical documentation specialist and clinical documentation improvement (CDI) professional.

Your task is to improve medical charts to meet payer compliance requirements while maintaining medical accuracy and completeness.

Key principles:
1. Never fabricate clinical information
2. MANDATORY: Use [AI ADDED: description] markers for ALL content you add or improve that was not in the original chart
3. MANDATORY: Use [NEEDS PHYSICIAN INPUT: description] placeholders for information that ONLY the treating physician can provide
4. Suggest specific improvements based on actual CDI recommendations
5. Maintain proper medical documentation format and terminology
6. Ensure transparency by clearly distinguishing AI-generated content from areas requiring physician input"""
        
        user_prompt = self._create_improvement_prompt(original_chart, all_recommendations, processing_result)
        
        # Call Claude to generate improved chart
        try:
            response, usage_info = self.call_claude_with_cache(
                user_prompt,
                max_tokens=8000,
                temperature=0.1,
                system_prompt=system_prompt
            )
            
            # Parse the response
            improved_data = self._parse_improvement_response(response)
            
            # Post-process: Ensure [NEEDS PHYSICIAN INPUT: ...] markers are embedded in chart text
            improved_data = self._ensure_physician_input_markers(improved_data)
            
            # Add metadata
            improved_data["usage"] = usage_info
            improved_data["cost"] = (
                usage_info.get("input_tokens", 0) / 1000 * Config.INPUT_COST_PER_1K +
                usage_info.get("output_tokens", 0) / 1000 * Config.OUTPUT_COST_PER_1K
            )
            improved_data["original_chart_length"] = len(original_chart)
            improved_data["improved_chart_length"] = len(improved_data.get("improved_chart", ""))
            
            print(f"[CHART IMPROVEMENT] Completed successfully")
            print(f"[CHART IMPROVEMENT] Cost: ${improved_data['cost']:.4f}")
            
            return improved_data
            
        except Exception as e:
            print(f"[ERROR] Chart improvement failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "improved_chart": original_chart,
                "improvements": [],
                "user_input_required": [],
                "recommendations": []
            }
    
    def _extract_all_recommendations(self, processing_result: ProcessingResult) -> List[Dict[str, Any]]:
        """Extract all recommendations from all payers, filtering out gaps already in related charts."""
        all_recommendations = []
        
        # Get related charts information for filtering
        multi_chart_info = getattr(processing_result, "multi_chart_info", None)
        other_charts_info = {}
        if multi_chart_info:
            other_charts_info = multi_chart_info.get("other_charts_info", {})
        
        def is_gap_covered_in_related_charts(gap_text):
            """Check if the gap information is already documented in related charts."""
            if not other_charts_info or not gap_text:
                return False
            
            gap_lower = str(gap_text).lower()
            
            # Check each related chart for the information
            for chart_file, chart_info in other_charts_info.items():
                # Check conservative treatment
                if any(kw in gap_lower for kw in ["conservative", "treatment", "therapy", "pt", "physical therapy", "medication", "injection"]):
                    conservative_treatment = chart_info.get("conservative_treatment", {})
                    if conservative_treatment and isinstance(conservative_treatment, dict):
                        has_treatment = any(
                            value for key, value in conservative_treatment.items() 
                            if value and isinstance(value, (str, int, float)) and str(value).strip()
                        )
                        if has_treatment:
                            return True
                
                # Check duration/timeframe
                if any(kw in gap_lower for kw in ["duration", "weeks", "months", "timeframe", "period"]):
                    summary = chart_info.get("summary", "")
                    if summary and isinstance(summary, str):
                        if any(kw in summary.lower() for kw in ["week", "month", "duration", "timeframe"]):
                            return True
                
                # Check physical examination
                if any(kw in gap_lower for kw in ["physical examination", "exam", "range of motion", "rom", "strength", "test", "impingement"]):
                    summary = chart_info.get("summary", "")
                    if summary and isinstance(summary, str):
                        if any(kw in summary.lower() for kw in ["exam", "examination", "rom", "range of motion", "strength", "impingement", "neer", "hawkins"]):
                            return True
                
                # Check functional limitations
                if any(kw in gap_lower for kw in ["functional", "limitation", "adl", "activities of daily living"]):
                    summary = chart_info.get("summary", "")
                    if summary and isinstance(summary, str):
                        if any(kw in summary.lower() for kw in ["functional", "limitation", "adl", "activity", "daily living"]):
                            return True
                
                # Check pain assessment
                if any(kw in gap_lower for kw in ["pain", "scale", "vas", "nrs", "score"]):
                    summary = chart_info.get("summary", "")
                    if summary and isinstance(summary, str):
                        if any(kw in summary.lower() for kw in ["pain", "vas", "nrs", "scale", "score"]):
                            return True
                
                # Check imaging
                if any(kw in gap_lower for kw in ["imaging", "mri", "xray", "x-ray", "ct", "radiology"]):
                    imaging = chart_info.get("imaging", [])
                    if imaging:
                        return True
                    tests = chart_info.get("tests", [])
                    if tests:
                        tests_str = " ".join([str(t) for t in tests]).lower()
                        if any(kw in tests_str for kw in ["mri", "xray", "x-ray", "ct", "imaging"]):
                            return True
            
            return False
        
        for payer_key, payer_result in processing_result.payer_results.items():
            payer_name = payer_result.get("payer_name", payer_key)
            
            for proc_result in payer_result.get("procedure_results", []):
                procedure_name = proc_result.get("procedure_evaluated", "Unknown")
                decision = proc_result.get("decision", "Unknown")
                
                # Extract improvement recommendations
                improvement_recs = proc_result.get("improvement_recommendations", {})
                doc_gaps = improvement_recs.get("documentation_gaps", [])
                # Filter out gaps already covered in related charts
                filtered_doc_gaps = [
                    gap for gap in doc_gaps 
                    if not is_gap_covered_in_related_charts(gap)
                ]
                
                compliance_actions = improvement_recs.get("compliance_actions", [])
                priority = improvement_recs.get("priority", "medium")
                
                # Extract requirement checklist
                requirements = proc_result.get("requirement_checklist", [])
                unmet_requirements = [
                    req for req in requirements 
                    if req.get("status") in ["unmet", "unclear"]
                ]
                # Filter unmet requirements that are already in related charts
                filtered_unmet_requirements = []
                for req in unmet_requirements:
                    missing = req.get("missing_to_meet", "")
                    if missing and not is_gap_covered_in_related_charts(missing):
                        filtered_unmet_requirements.append(req)
                
                # Extract primary reasons
                primary_reasons = proc_result.get("primary_reasons", [])
                # Filter primary reasons that are already in related charts
                filtered_primary_reasons = [
                    reason for reason in primary_reasons 
                    if not is_gap_covered_in_related_charts(reason)
                ]
                
                all_recommendations.append({
                    "payer": payer_name,
                    "procedure": procedure_name,
                    "decision": decision,
                    "documentation_gaps": filtered_doc_gaps,
                    "compliance_actions": compliance_actions,
                    "priority": priority,
                    "unmet_requirements": filtered_unmet_requirements,
                    "primary_reasons": filtered_primary_reasons
                })
        
        return all_recommendations
    
    def _create_improvement_prompt(
        self, 
        original_chart: str, 
        all_recommendations: List[Dict[str, Any]],
        processing_result: ProcessingResult
    ) -> str:
        """Create the prompt for chart improvement."""
        
        # Summarize recommendations
        recommendations_summary = self._summarize_recommendations(all_recommendations)
        
        # Get related charts information to avoid duplicating information
        related_charts_section = ""
        multi_chart_info = getattr(processing_result, "multi_chart_info", None)
        if multi_chart_info:
            other_charts_info = multi_chart_info.get("other_charts_info", {})
            if other_charts_info:
                related_charts_section = "\n\n## RELATED MEDICAL CHARTS (Information Already Available):\n\n"
                related_charts_section += "IMPORTANT: The following information is already documented in related medical charts for this patient. "
                related_charts_section += "DO NOT add [NEEDS PHYSICIAN INPUT: ...] markers or request this information in the improved chart, "
                related_charts_section += "as it is already available in other records:\n\n"
                
                for chart_file, chart_info in other_charts_info.items():
                    chart_title = chart_info.get("display_title") or chart_info.get("chart_type", "unknown").replace("_", " ").title()
                    related_charts_section += f"### {chart_title}:\n"
                    
                    if chart_info.get("summary"):
                        related_charts_section += f"Summary: {chart_info['summary']}\n"
                    
                    conservative_treatment = chart_info.get("conservative_treatment", {})
                    if conservative_treatment and isinstance(conservative_treatment, dict):
                        treatment_items = []
                        for key, value in conservative_treatment.items():
                            if value:
                                treatment_items.append(f"{key.replace('_', ' ').title()}: {value}")
                        if treatment_items:
                            related_charts_section += f"Conservative Treatment: {'; '.join(treatment_items)}\n"
                    
                    imaging = chart_info.get("imaging", [])
                    if imaging:
                        if isinstance(imaging, list):
                            related_charts_section += f"Imaging: {', '.join(imaging[:5])}\n"
                        else:
                            related_charts_section += f"Imaging: {imaging}\n"
                    
                    tests = chart_info.get("tests", [])
                    if tests:
                        if isinstance(tests, list):
                            related_charts_section += f"Tests/Studies: {', '.join(tests[:5])}\n"
                        else:
                            related_charts_section += f"Tests/Studies: {tests}\n"
                    
                    related_charts_section += "\n"
                
                related_charts_section += "CRITICAL: Before adding any [NEEDS PHYSICIAN INPUT: ...] marker for conservative treatment, duration, imaging, tests, or physical examination findings, check if that information is already listed above in the related charts. If it is available in related charts, DO NOT request it again.\n"
        
        prompt = f"""# MEDICAL CHART IMPROVEMENT TASK
 
 You are reviewing a medical chart and will improve it based on CDI compliance recommendations from multiple payers.
 
 ## ORIGINAL MEDICAL CHART:
 ```
 {original_chart[:8000]}
 ```
 
## CDI COMPLIANCE ANALYSIS SUMMARY:

### Procedures Evaluated:
{self._format_procedures(processing_result)}

### RECOMMENDATIONS FROM ALL PAYERS:
{recommendations_summary}{related_charts_section}
 
 ## YOUR TASK:
 
 CRITICAL: Generate VALID JSON ONLY. When including medical chart text or descriptions:
 - Properly escape all quotes with backslash: " becomes \\"
 - Replace newlines with \\n
 - Escape backslashes: \\ becomes \\\\
 - Keep strings on single lines when possible
 
 Generate a JSON response with the following structure:

```json
{{
  "improved_chart": "STRING - The improved medical chart with clear markers to identify content sources. CRITICAL REQUIREMENTS: 1) Use [AI ADDED: description] markers to identify ALL content that you (the AI) are adding or improving that was not in the original chart. 2) MANDATORY: Use [NEEDS PHYSICIAN INPUT: description] placeholders DIRECTLY IN THE CHART TEXT wherever information is missing or incomplete that ONLY the treating physician can provide. These markers MUST appear in the actual chart text, not just in the user_input_required array. For example, if physical examination findings are incomplete, add [NEEDS PHYSICIAN INPUT: specific range of motion measurements, strength testing results] right in that section. 3) NEVER include insurance company names (Anthem, Cigna, UnitedHealthcare, etc.) in this text. 4) Do NOT add line numbers (L001:, L002:, etc.) to the chart text. The chart should clearly distinguish between AI-generated improvements and areas requiring physician input.",
  "improvements": [
    {{
      "section": "STRING - Which section was improved (e.g., 'History', 'Physical Exam', 'Assessment')",
      "original": "STRING - Original text or indication it was missing",
      "improved": "STRING - Improved/added text (NEVER mention payer names in this text)",
      "reason": "STRING - Clinical rationale for improvement (reference which requirements this helps meet)",
      "payers_affected": ["STRING - List of payers this improvement helps (metadata only, not in chart text)"]
    }}
  ],
  "user_input_required": [
    {{
      "section": "STRING - Section name",
      "field": "STRING - Specific CLINICAL information needed (e.g., 'Conservative treatment duration', 'Physical examination findings', 'Pain severity measurement' - NEVER ask for payer policy information)",
      "reason": "STRING - Clinical reason why this information is needed for medical necessity documentation",
      "suggestion": "STRING - Guidance on what clinical details should be documented",
      "payers_requiring": ["STRING - Which payers require this (metadata only)"],
      "priority": "high | medium | low"
    }}
  ],
  "recommendations": [
    {{
      "category": "STRING - Category (e.g., 'Imaging', 'Conservative Treatment', 'Clinical Findings')",
      "recommendation": "STRING - Specific actionable recommendation",
      "payers": ["STRING - Payers requiring this"],
      "priority": "high | medium | low"
    }}
  ],
  "compliance_impact": {{
    "before": "STRING - Summary of compliance issues before improvement",
    "after": "STRING - Expected compliance status after improvements and physician input",
    "key_changes": ["STRING - List of most important changes made"]
  }},
  "success": true
}}
```

## GUIDELINES FOR IMPROVEMENT:

1. **DO NOT FABRICATE CLINICAL DATA**: Never invent patient symptoms, test results, or clinical findings
2. **MARK AI-GENERATED CONTENT**: Use [AI ADDED: description] markers to identify ALL content you are adding or improving that was not explicitly in the original chart. This includes: new sections, improved formatting, clarified terminology, added structure, enhanced descriptions, etc.
3. **MARK PHYSICIAN INPUT NEEDED - MANDATORY**: You MUST embed [NEEDS PHYSICIAN INPUT: description] markers DIRECTLY IN THE CHART TEXT wherever information is missing, incomplete, or needs physician verification. These markers should appear in the actual improved_chart text at the exact location where the information is needed. For example: "Range of motion: [NEEDS PHYSICIAN INPUT: forward flexion degrees, abduction degrees, internal/external rotation degrees]" or "Physical therapy: [NEEDS PHYSICIAN INPUT: specific duration in weeks] weeks, [NEEDS PHYSICIAN INPUT: frequency per week] sessions per week". DO NOT just list these in the user_input_required array - they MUST appear in the chart text itself.
4. **ADD STRUCTURE**: Improve formatting, add section headers, organize information clearly - but mark these improvements with [AI ADDED: ...]
5. **CLARIFY EXISTING INFO**: Rewrite ambiguous statements to be more specific - mark clarifications with [AI ADDED: clarification]
6. **NO LINE NUMBERS**: Do NOT add line numbers (L001:, L002:, etc.) to the chart text. The chart should be clean text with only the two marker types above.
7. **PRESERVE ACCURACY**: Keep all original clinical information intact - do not change facts, only improve presentation and add missing structure
8. **IMPROVE TERMINOLOGY**: Use proper medical terminology where appropriate - mark terminology improvements with [AI ADDED: terminology improvement]
9. **ADD CONTEXT**: Where the chart references something vaguely, make it more specific if context allows - mark these with [AI ADDED: context added]
10. **NEVER MENTION PAYER NAMES IN CHART**: The improved_chart text must NEVER contain insurance company names (Anthem, Cigna, UnitedHealthcare, etc.). Document clinical criteria and medical necessity without referencing specific payers. Payer names are ONLY allowed in the JSON metadata fields (payers_affected, payers_requiring, payers) for tracking purposes, NOT in the actual medical chart text.
11. **FOCUS ON CLINICAL REQUIREMENTS**: Instead of "Document Anthem policy criteria", request clinical information like "Document specific conservative treatment duration, modalities used, and outcomes" or "Specify clinical examination findings supporting medical necessity"
12. **REQUIRED MARKERS - MANDATORY**: You MUST use markers. Every AI improvement should be marked with [AI ADDED: ...] and every area needing physician input should be marked with [NEEDS PHYSICIAN INPUT: ...] DIRECTLY IN THE CHART TEXT. If you identify missing information in the user_input_required array, you MUST also add corresponding [NEEDS PHYSICIAN INPUT: ...] markers in the improved_chart text at the appropriate locations. This is critical for transparency and allows physicians to see exactly where their input is needed.

## EXAMPLES OF GOOD IMPROVEMENTS:

**Example 1 - Adding Structure (AI Improvement):**
Original: "Patient has knee pain"
Improved: "[AI ADDED: Section header added] Chief Complaint: Patient presents with knee pain [NEEDS PHYSICIAN INPUT: Duration, severity, onset, aggravating/relieving factors]"

**Example 2 - Clarifying Existing Info (AI Improvement + Physician Input):**
Original: "Conservative treatment tried"
Improved: "[AI ADDED: Clarified wording] Conservative treatment attempted [NEEDS PHYSICIAN INPUT: Please specify: type of treatment, duration (weeks/months), frequency, patient response/outcome]"

**Example 3 - Organizing Information (AI Improvement):**
Original: Medical information scattered throughout
Improved: "[AI ADDED: Organized into structured sections] 
- Chief Complaint
- History of Present Illness
- Past Medical History
- Physical Examination
- Imaging/Diagnostic Studies
- Assessment and Plan"

**Example 4 - WRONG (contains payer name):**
BAD: "ANTHEM POLICY COMPLIANCE: Patient meets Anthem criteria including 6 weeks conservative management..."

**Example 5 - CORRECT (AI improvement marked + physician input marked):**
GOOD: "[AI ADDED: Medical necessity documentation section] MEDICAL NECESSITY DOCUMENTATION: Patient has completed [NEEDS PHYSICIAN INPUT: specific duration] of conservative management including [NEEDS PHYSICIAN INPUT: treatment modalities]. [AI ADDED: Clinical criteria summary] Clinical criteria met include documented pain >=4/10 VAS, weakness on examination, and imaging-confirmed pathology requiring surgical intervention."

**Example 6 - WRONG (asking for payer policy):**
BAD: "[NEEDS PHYSICIAN INPUT: Anthem policy requirements for rotator cuff repair]"

**Example 7 - CORRECT (asking for clinical details):**
GOOD: "[NEEDS PHYSICIAN INPUT: Specific examination findings including range of motion measurements, strength testing results, and positive provocative tests supporting surgical indication]"

**Example 8 - AI Adding Missing Information:**
Original: "Physical therapy completed"
Improved: "[AI ADDED: Enhanced with structured format] Physical therapy: [NEEDS PHYSICIAN INPUT: duration in weeks] weeks, [NEEDS PHYSICIAN INPUT: frequency per week] sessions per week, [NEEDS PHYSICIAN INPUT: patient response/outcome]"

**Example 9 - AI Improving Terminology:**
Original: "Knee hurts"
Improved: "[AI ADDED: Improved medical terminology] Patient reports [NEEDS PHYSICIAN INPUT: specific location and characteristics] of knee pain"

Return ONLY valid JSON, no other text."""
        
        return prompt
    
    def _summarize_recommendations(self, all_recommendations: List[Dict[str, Any]]) -> str:
        """Summarize all recommendations into readable format."""
        if not all_recommendations:
            return "No specific recommendations available."
        
        summary_parts = []
        
        for i, rec in enumerate(all_recommendations, 1):
            summary_parts.append(f"\n### Recommendation {i}: {rec['payer']} - {rec['procedure']}")
            summary_parts.append(f"Decision: {rec['decision']}")
            
            if rec.get("documentation_gaps"):
                summary_parts.append("\n**Documentation Gaps:**")
                for gap in rec["documentation_gaps"]:
                    summary_parts.append(f"  - {gap}")
            
            if rec.get("compliance_actions"):
                summary_parts.append("\n**Required Actions:**")
                for action in rec["compliance_actions"]:
                    summary_parts.append(f"  - {action}")
            
            if rec.get("unmet_requirements"):
                summary_parts.append("\n**Unmet Requirements:**")
                for req in rec["unmet_requirements"]:
                    req_id = req.get("requirement_id", "Unknown")
                    missing = req.get("missing_to_meet", "Not specified")
                    suggestion = req.get("suggestion", "")
                    summary_parts.append(f"  - {req_id}: {missing}")
                    if suggestion:
                        summary_parts.append(f"    Suggestion: {suggestion}")
            
            summary_parts.append(f"\nPriority: {rec.get('priority', 'medium').upper()}")
            summary_parts.append("---")
        
        return "\n".join(summary_parts)
    
    def _format_procedures(self, processing_result: ProcessingResult) -> str:
        """Format procedures list."""
        procedures = processing_result.extraction_data.get("procedure", [])
        if not procedures:
            return "No procedures detected"
        
        return "\n".join([f"  {i+1}. {proc}" for i, proc in enumerate(procedures)])
    
    def _ensure_physician_input_markers(self, improved_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Post-process improved chart to ensure [NEEDS PHYSICIAN INPUT: ...] markers 
        are embedded in the chart text based on user_input_required array.
        """
        improved_chart = improved_data.get("improved_chart", "")
        user_input_required = improved_data.get("user_input_required", [])
        
        if not user_input_required or not improved_chart:
            return improved_data
        
        # Check if chart already has physician input markers
        existing_markers = improved_chart.count("[NEEDS PHYSICIAN INPUT:")
        if existing_markers >= len(user_input_required):
            print(f"[CHART IMPROVEMENT] Physician input markers already present ({existing_markers} found)")
            return improved_data
        
        # If markers are missing, add them based on user_input_required
        print(f"[CHART IMPROVEMENT] Adding physician input markers to chart text ({len(user_input_required)} required)...")
        
        import re
        chart_lines = improved_chart.split('\n')
        modified_chart_lines = chart_lines.copy()
        markers_added = 0
        
        # For each required input, try to find the appropriate section and add marker
        for input_req in user_input_required:
            section = input_req.get("section", "")
            field = input_req.get("field", "")
            suggestion = input_req.get("suggestion", "")
            
            # Create marker text
            marker_text = f"[NEEDS PHYSICIAN INPUT: {suggestion if suggestion else field}]"
            
            # Skip if marker already exists
            if marker_text in improved_chart:
                continue
            
            # Try to find the section in the chart (case-insensitive)
            section_found = False
            section_line_idx = -1
            
            # Normalize section name for matching
            section_normalized = section.lower().strip()
            
            for i, line in enumerate(modified_chart_lines):
                line_lower = line.lower().strip()
                # Check if line contains section name (as header)
                if (section_normalized in line_lower and 
                    (line_lower.startswith(section_normalized) or 
                     ':' in line or 
                     line_lower == section_normalized or
                     line_lower.replace(' ', '').replace('-', '') == section_normalized.replace(' ', '').replace('-', ''))):
                    section_found = True
                    section_line_idx = i
                    break
            
            if section_found and section_line_idx >= 0:
                # Found the section, add marker after section header or in relevant location
                insert_idx = section_line_idx + 1
                
                # Look for relevant content in the next few lines
                for j in range(section_line_idx + 1, min(section_line_idx + 15, len(modified_chart_lines))):
                    next_line = modified_chart_lines[j].lower()
                    field_lower = field.lower()
                    
                    # Check if this line relates to the field
                    field_keywords = [w for w in field_lower.split() if len(w) > 4]
                    if field_keywords and any(kw in next_line for kw in field_keywords[:2]):
                        # Found relevant line, add marker inline or after
                        if ":" in modified_chart_lines[j] and not marker_text in modified_chart_lines[j]:
                            # Add marker after colon if present
                            modified_chart_lines[j] = modified_chart_lines[j].rstrip() + f" {marker_text}"
                            markers_added += 1
                            break
                        elif j + 1 < len(modified_chart_lines):
                            # Add as new line after this one
                            modified_chart_lines.insert(j + 1, marker_text)
                            markers_added += 1
                            break
                else:
                    # No relevant line found, add marker after section header
                    if insert_idx < len(modified_chart_lines):
                        modified_chart_lines.insert(insert_idx, marker_text)
                        markers_added += 1
            else:
                # Section not found, try to add at end of chart or find similar section
                # Look for partial matches
                for i, line in enumerate(modified_chart_lines):
                    line_lower = line.lower()
                    # Check for partial section match
                    section_words = [w for w in section_normalized.split() if len(w) > 4]
                    if section_words and any(w in line_lower for w in section_words):
                        # Found similar section, add marker
                        if i + 1 < len(modified_chart_lines):
                            modified_chart_lines.insert(i + 1, marker_text)
                            markers_added += 1
                            break
        
        if markers_added > 0:
            improved_data["improved_chart"] = '\n'.join(modified_chart_lines)
            print(f"[CHART IMPROVEMENT] Added {markers_added} physician input marker(s) to chart text")
        else:
            print("[CHART IMPROVEMENT] No markers added (may already be present or sections not found)")
        
        return improved_data
    
    def _parse_improvement_response(self, response: str) -> Dict[str, Any]:
        """Parse the improvement response from Claude with robust error handling."""
        import re
        from json import JSONDecoder, JSONDecodeError, loads
        
        try:
            # Try to extract JSON from the response
            if "```json" in response:
                json_start = response.find("```json") + 7
                json_end = response.find("```", json_start)
                json_str = response[json_start:json_end].strip()
            elif "```" in response:
                json_start = response.find("```") + 3
                json_end = response.find("```", json_start)
                json_str = response[json_start:json_end].strip()
            else:
                json_str = response.strip()
            
            # First attempt: Direct JSON parsing
            try:
                parsed = loads(json_str)
            except JSONDecodeError as e:
                print(f"[WARNING] Initial JSON parse failed at position {e.pos}: {e.msg}")
                
                # Attempt to fix JSON by finding complete object
                brace_count = 0
                start_idx = json_str.find('{')
                if start_idx == -1:
                    raise ValueError("No JSON object found in response")
                
                end_idx = -1
                in_string = False
                escape_next = False
                
                for i in range(start_idx, len(json_str)):
                    char = json_str[i]
                    
                    # Track string context to avoid counting braces in strings
                    if escape_next:
                        escape_next = False
                        continue
                    
                    if char == '\\':
                        escape_next = True
                        continue
                    
                    if char == '"':
                        in_string = not in_string
                        continue
                    
                    if not in_string:
                        if char == '{':
                            brace_count += 1
                        elif char == '}':
                            brace_count -= 1
                            if brace_count == 0:
                                end_idx = i + 1
                                break
                
                if end_idx > start_idx:
                    json_str = json_str[start_idx:end_idx]
                    
                    # Try parsing the extracted JSON
                    try:
                        # Use JSONDecoder with strict=False to be more lenient
                        decoder = JSONDecoder(strict=False)
                        parsed = decoder.decode(json_str)
                    except Exception as decode_error:
                        print(f"[WARNING] Lenient parsing also failed: {decode_error}")
                        # Last resort: try to manually fix common issues
                        # Remove control characters that break JSON
                        json_str = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', json_str)
                        parsed = loads(json_str)
                else:
                    raise ValueError(f"Could not find complete JSON object")
            
            # Validate structure
            if not isinstance(parsed, dict):
                raise ValueError("Response is not a dictionary")
            
            # Ensure required fields
            parsed.setdefault("success", True)
            parsed.setdefault("improved_chart", "")
            parsed.setdefault("improvements", [])
            parsed.setdefault("user_input_required", [])
            parsed.setdefault("recommendations", [])
            parsed.setdefault("compliance_impact", {})
            
            print(f"[OK] Successfully parsed improvement response")
            return parsed
            
        except Exception as e:
            print(f"[ERROR] Failed to parse improvement response after all attempts: {e}")
            print(f"[DEBUG] Response length: {len(response)} characters")
            print(f"[DEBUG] First 300 chars: {response[:300]}")
            
            return {
                "success": False,
                "error": f"Failed to parse response: {str(e)}",
                "improved_chart": "",
                "improvements": [],
                "user_input_required": [],
                "recommendations": [],
                "compliance_impact": {},
                "raw_response_preview": response[:500]  # Include snippet for debugging
            }

