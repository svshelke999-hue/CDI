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
        """Extract all recommendations from all payers."""
        all_recommendations = []
        
        for payer_key, payer_result in processing_result.payer_results.items():
            payer_name = payer_result.get("payer_name", payer_key)
            
            for proc_result in payer_result.get("procedure_results", []):
                procedure_name = proc_result.get("procedure_evaluated", "Unknown")
                decision = proc_result.get("decision", "Unknown")
                
                # Extract improvement recommendations
                improvement_recs = proc_result.get("improvement_recommendations", {})
                doc_gaps = improvement_recs.get("documentation_gaps", [])
                compliance_actions = improvement_recs.get("compliance_actions", [])
                priority = improvement_recs.get("priority", "medium")
                
                # Extract requirement checklist
                requirements = proc_result.get("requirement_checklist", [])
                unmet_requirements = [
                    req for req in requirements 
                    if req.get("status") in ["unmet", "unclear"]
                ]
                
                # Extract primary reasons
                primary_reasons = proc_result.get("primary_reasons", [])
                
                all_recommendations.append({
                    "payer": payer_name,
                    "procedure": procedure_name,
                    "decision": decision,
                    "documentation_gaps": doc_gaps,
                    "compliance_actions": compliance_actions,
                    "priority": priority,
                    "unmet_requirements": unmet_requirements,
                    "primary_reasons": primary_reasons
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
 {recommendations_summary}
 
 ## YOUR TASK:
 
 CRITICAL: Generate VALID JSON ONLY. When including medical chart text or descriptions:
 - Properly escape all quotes with backslash: " becomes \\"
 - Replace newlines with \\n
 - Escape backslashes: \\ becomes \\\\
 - Keep strings on single lines when possible
 
 Generate a JSON response with the following structure:

```json
{{
  "improved_chart": "STRING - The improved medical chart with clear markers to identify content sources. CRITICAL REQUIREMENTS: 1) Use [AI ADDED: description] markers to identify ALL content that you (the AI) are adding or improving that was not in the original chart. 2) Use [NEEDS PHYSICIAN INPUT: description] placeholders for information that ONLY the treating physician can provide (e.g., specific test results, examination findings, patient-reported symptoms). 3) NEVER include insurance company names (Anthem, Cigna, UnitedHealthcare, etc.) in this text. 4) Do NOT add line numbers (L001:, L002:, etc.) to the chart text. The chart should clearly distinguish between AI-generated improvements and areas requiring physician input.",
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
3. **MARK PHYSICIAN INPUT NEEDED**: Use [NEEDS PHYSICIAN INPUT: description] ONLY for information that ONLY the treating physician can provide (e.g., specific physical examination findings, test results, patient-reported symptoms, dates of treatments, medication dosages, etc.)
4. **ADD STRUCTURE**: Improve formatting, add section headers, organize information clearly - but mark these improvements with [AI ADDED: ...]
5. **CLARIFY EXISTING INFO**: Rewrite ambiguous statements to be more specific - mark clarifications with [AI ADDED: clarification]
6. **NO LINE NUMBERS**: Do NOT add line numbers (L001:, L002:, etc.) to the chart text. The chart should be clean text with only the two marker types above.
7. **PRESERVE ACCURACY**: Keep all original clinical information intact - do not change facts, only improve presentation and add missing structure
8. **IMPROVE TERMINOLOGY**: Use proper medical terminology where appropriate - mark terminology improvements with [AI ADDED: terminology improvement]
9. **ADD CONTEXT**: Where the chart references something vaguely, make it more specific if context allows - mark these with [AI ADDED: context added]
10. **NEVER MENTION PAYER NAMES IN CHART**: The improved_chart text must NEVER contain insurance company names (Anthem, Cigna, UnitedHealthcare, etc.). Document clinical criteria and medical necessity without referencing specific payers. Payer names are ONLY allowed in the JSON metadata fields (payers_affected, payers_requiring, payers) for tracking purposes, NOT in the actual medical chart text.
11. **FOCUS ON CLINICAL REQUIREMENTS**: Instead of "Document Anthem policy criteria", request clinical information like "Document specific conservative treatment duration, modalities used, and outcomes" or "Specify clinical examination findings supporting medical necessity"
12. **REQUIRED MARKERS**: You MUST use markers. Every AI improvement should be marked with [AI ADDED: ...] and every area needing physician input should be marked with [NEEDS PHYSICIAN INPUT: ...]. This is critical for transparency.

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

