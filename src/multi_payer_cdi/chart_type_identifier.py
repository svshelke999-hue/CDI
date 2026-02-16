"""
Chart type identification module for multi-chart processing.
"""

from typing import Dict, Any, Optional, List
from .bedrock_client import BedrockClient
from .cache_manager import CacheManager
from .config import Config
from .logger import CDILogger


class ChartTypeIdentifier:
    """Identifies chart types from medical documents."""
    
    # Chart type categories
    CHART_TYPES = [
        "operative_note",
        "pre_operative_note",
        "post_operative_note",
        "progress_note",
        "nursing_note",
        "discharge_summary",
        "consultation_note",
        "laboratory_report",
        "imaging_report",
        "pathology_report",
        "radiology_report",
        "anesthesia_note",
        "emergency_note",
        "admission_note",
        "billing_note",
        "other"
    ]
    
    # Mapping from chart_type to human-readable display title
    CHART_TYPE_DISPLAY_TITLES = {
        "operative_note": "Operative Report",
        "pre_operative_note": "Pre-Operative Note",
        "post_operative_note": "Post-Operative Note",
        "progress_note": "Progress Note",
        "nursing_note": "Nursing Note",
        "discharge_summary": "Discharge Summary",
        "consultation_note": "Consultation Note",
        "laboratory_report": "Laboratory Report",
        "imaging_report": "Imaging Report",
        "pathology_report": "Pathology Report",
        "radiology_report": "Radiology Report",
        "anesthesia_note": "Anesthesia Note",
        "emergency_note": "Emergency Department Note",
        "admission_note": "Admission Note",
        "billing_note": "Billing Document",
        "other": "Medical Document"
    }
    
    def __init__(self, cache_manager: CacheManager):
        self.cache_manager = cache_manager
    
    def identify_chart_type(self, file_path: str, text_sample: str) -> Dict[str, Any]:
        """
        Identify chart type from first 100 words of text.
        
        Args:
            file_path: Path to the file (for logging)
            text_sample: First 100 words of the document
            
        Returns:
            Dictionary with chart_type and confidence
        """
        # Get first 100 words for chart type identification
        words = text_sample.split()[:100]
        sample_text = " ".join(words)
        
        if len(sample_text.strip()) < 10:
            return {
                "chart_type": "other",
                "confidence": "low",
                "reason": "Insufficient text sample",
                "display_title": "Medical Document"
            }
        
        # Create identification prompt with enhanced detection
        identification_prompt = f"""You are a medical document classification specialist with expertise in identifying different types of medical documents.

TASK:
Analyze the following text sample (first 100 words) from a medical document and identify its SPECIFIC chart type. Be very specific and accurate.

CRITICAL: You MUST identify the chart type. Do NOT default to "other" unless the document is truly ambiguous. Most medical documents have clear indicators of their type.

IMPORTANT: Read the entire text sample carefully. Look for:
1. Document headers (e.g., "OPERATIVE REPORT", "LAB RESULTS", "IMAGING REPORT")
2. Key phrases and terminology specific to document types
3. Document structure and format
4. Type of information presented (procedures, test results, assessments, etc.)

CHART TYPE OPTIONS (choose the MOST SPECIFIC match):

OPERATIVE/SURGICAL DOCUMENTS:
- operative_note: Surgical operative reports, procedure notes, surgery documentation
  Key indicators: "procedure performed", "operative report", "surgical technique", "incision", "findings", procedure steps, surgical instruments
  Examples: "OPERATIVE REPORT", "SURGICAL PROCEDURE", procedure details with steps

PRE/POST-OPERATIVE DOCUMENTS:
- pre_operative_note: Pre-operative assessments, pre-surgical evaluations, surgical clearance
  Key indicators: "pre-operative", "pre-op", "surgical clearance", "pre-operative assessment", planned procedures, anesthesia clearance
  Examples: "PRE-OPERATIVE NOTE", "PRE-OP ASSESSMENT", pre-surgery evaluation
  
- post_operative_note: Post-operative notes, post-surgical follow-ups, recovery documentation
  Key indicators: "post-operative", "post-op", "post-operative care", recovery status, post-surgery follow-up
  Examples: "POST-OPERATIVE NOTE", recovery documentation

CLINICAL NOTES:
- progress_note: Daily progress notes, clinical progress notes, visit notes
  Key indicators: "progress note", "daily note", "follow-up visit", clinical updates, day-to-day progress
  Examples: "PROGRESS NOTE", daily clinical updates
  
- consultation_note: Consultation reports, specialist consultations, referral notes
  Key indicators: "consultation", "referral", "specialist opinion", second opinion, consultant report
  Examples: "CONSULTATION NOTE", specialist referral
  
- nursing_note: Nursing documentation, nursing assessments, nurse notes
  Key indicators: "nursing assessment", "nurse's note", nursing documentation, nurse charting
  Examples: "NURSING NOTE", nursing assessment

HOSPITAL DOCUMENTS:
- discharge_summary: Discharge summaries, discharge notes, hospital discharge documents
  Key indicators: "discharge summary", "discharge planning", "hospital discharge", discharge instructions
  Examples: "DISCHARGE SUMMARY", discharge planning
  
- admission_note: Admission notes, admission assessments, hospital admission
  Key indicators: "admission note", "admitting", "hospital admission", admission assessment
  Examples: "ADMISSION NOTE", admission assessment
  
- emergency_note: Emergency department notes, ER notes, emergency room documentation
  Key indicators: "emergency", "ER note", "ED note", "emergency department", triage note
  Examples: "EMERGENCY NOTE", ER documentation

TEST/REPORT DOCUMENTS:
- laboratory_report: Lab results, lab reports, blood work, test results
  Key indicators: "laboratory", "lab results", "lab report", test values (glucose, hemoglobin, etc.), chemistry panel, CBC, CMP
  Examples: "LABORATORY RESULTS", "BLOOD WORK", test values with units
  
- imaging_report: Imaging study reports (MRI, CT, X-ray, ultrasound with findings)
  Key indicators: "MRI report", "CT scan report", "ultrasound report", "X-ray report", imaging findings, "impression", "findings"
  Examples: "MRI REPORT", "CT SCAN", imaging interpretation with findings
  
- radiology_report: Radiology reports, radiology interpretations
  Key indicators: "radiology report", "radiologist", imaging interpretation, diagnostic imaging report
  Examples: "RADIOLOGY REPORT", radiologist interpretation
  
- pathology_report: Pathology reports, biopsy reports, tissue analysis
  Key indicators: "pathology report", "biopsy report", tissue analysis, histopathology, specimen analysis, microscopic findings
  Examples: "PATHOLOGY REPORT", "BIOPSY REPORT", tissue analysis

ANESTHESIA:
- anesthesia_note: Anesthesia records, anesthesia notes, anesthesia documentation
  Key indicators: "anesthesia record", "anesthetic", anesthetic agents, intubation, monitoring during surgery
  Examples: "ANESTHESIA RECORD", anesthetic documentation

FINANCIAL/ADMINISTRATIVE:
- billing_note: Billing documents, charge sheets, financial documents
  Key indicators: "billing", "charges", "CPT codes", "ICD codes", billing codes, financial information, fee schedule
  Examples: "BILLING DOCUMENT", charge sheet with CPT codes

OTHER (use ONLY if none of the above match):
- other: Generic medical document that doesn't clearly fit any category above
  Use this ONLY as a last resort when the document type is truly ambiguous

IDENTIFICATION PROCESS:
1. FIRST: Look for explicit headers (OPERATIVE REPORT, LAB RESULTS, etc.) - these are the strongest indicators
2. SECOND: Analyze the content type (procedures vs test results vs assessments)
3. THIRD: Check for specific terminology and phrases unique to each document type
4. FOURTH: Consider document structure and format
5. LAST: If truly unclear, use "other" but try to be as specific as possible

CRITICAL RULES:
- If you see "procedure performed", "surgical technique", or procedure steps → operative_note
- If you see test values with units (e.g., "glucose 95 mg/dL") → laboratory_report
- If you see "MRI findings", "CT findings", or imaging impressions → imaging_report or radiology_report
- If you see "pre-operative" or "pre-op" → pre_operative_note
- If you see "post-operative" or "post-op" → post_operative_note
- If you see "discharge planning" or "discharge summary" → discharge_summary
- If you see CPT codes with charges → billing_note
- BE SPECIFIC: Don't default to "other" unless absolutely necessary

TEXT SAMPLE:
{sample_text}

Return ONLY a JSON object with these exact keys:
{{
  "chart_type": "one of the chart type options above",
  "confidence": "high | medium | low",
  "reason": "brief explanation of why this chart type was identified"
}}

CRITICAL IDENTIFICATION RULES:
- Return ONLY valid JSON, no other text
- Use the exact chart_type values listed above
- Be SPECIFIC: Don't default to "other" unless absolutely necessary
- Look for explicit headers FIRST - these are the strongest indicators
- If you see "procedure performed" or surgical steps → operative_note
- If you see test values with units (e.g., "glucose 95 mg/dL") → laboratory_report
- If you see "MRI findings" or "CT findings" → imaging_report or radiology_report
- If you see "pre-operative" or "pre-op" → pre_operative_note
- If you see "post-operative" or "post-op" → post_operative_note
- If you see "discharge summary" → discharge_summary
- If you see CPT codes with charges → billing_note
- BE CONFIDENT: If you see clear indicators, use "high" confidence
- Only use "other" with "low" confidence if truly ambiguous
- In your reason, mention specific keywords or headers found that led to this identification
"""
        
        try:
            # Check cache
            cache_key = self.cache_manager.get_cache_key(
                identification_prompt, None, 200, 0.0
            )
            cached_result = self.cache_manager.load_from_cache(cache_key)
            
            if cached_result:
                response, usage_info = cached_result
                print(f"[CACHE] Chart type identification cache HIT for {file_path}")
            else:
                print(f"[IDENTIFY] Identifying chart type for {file_path}...")
                response, usage_info = BedrockClient.call_claude(
                    identification_prompt,
                    max_tokens=200,
                    temperature=0.0,
                    system_prompt=None
                )
                
                # Log and cache
                cost = (usage_info.get("input_tokens", 0) / 1000 * Config.INPUT_COST_PER_1K) + \
                       (usage_info.get("output_tokens", 0) / 1000 * Config.OUTPUT_COST_PER_1K)
                CDILogger.log_llm_call(
                    model=usage_info.get("model_id", "unknown"),
                    prompt_tokens=usage_info.get("input_tokens", 0),
                    completion_tokens=usage_info.get("output_tokens", 0),
                    cost=cost,
                    cache_hit=False,
                    purpose="chart_type_identification"
                )
                self.cache_manager.save_to_cache(cache_key, response, usage_info)
            
            # Parse response
            import json
            import re
            
            # Extract JSON from response
            json_match = re.search(r'\{[^{}]*"chart_type"[^{}]*\}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                # Try to find JSON object
                start = response.find('{')
                end = response.rfind('}') + 1
                if start >= 0 and end > start:
                    json_str = response[start:end]
                else:
                    raise ValueError("No JSON found in response")
            
            result = json.loads(json_str)
            
            # Validate chart type
            chart_type = result.get("chart_type", "other")
            if chart_type not in self.CHART_TYPES:
                chart_type = "other"
                result["chart_type"] = chart_type
                result["confidence"] = "low"
                result["reason"] = f"Invalid chart type returned, defaulting to 'other'"
            
            # Always add display title (ensure it's present)
            if "display_title" not in result:
                result["display_title"] = self.CHART_TYPE_DISPLAY_TITLES.get(chart_type, "Medical Document")
            else:
                # Validate display_title exists in our mapping, otherwise use mapped value
                if result["display_title"] not in self.CHART_TYPE_DISPLAY_TITLES.values():
                    result["display_title"] = self.CHART_TYPE_DISPLAY_TITLES.get(chart_type, "Medical Document")
            
            result["file_path"] = file_path
            print(f"[IDENTIFY] Chart type identified: {chart_type} → {result['display_title']} (confidence: {result.get('confidence', 'unknown')})")
            
            return result
            
        except Exception as e:
            print(f"[WARNING] Chart type identification failed for {file_path}: {e}")
            return {
                "chart_type": "other",
                "confidence": "low",
                "reason": f"Identification error: {str(e)}",
                "display_title": "Medical Document",
                "file_path": file_path
            }
    
    def identify_multiple_charts(
        self, 
        charts_data: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Identify chart types for multiple charts together, checking for same patient and duplicates.
        
        Args:
            charts_data: List of dictionaries, each containing:
                - "file_path": str - Path to the file
                - "file_name": str - Name of the file
                - "sample_text": str - First 100 words of the document
                
        Returns:
            Dictionary with:
                - "chart_results": List of chart identification results
                - "same_patient": bool - Whether all charts are from the same patient
                - "patient_name": str - Patient name if identified
                - "patient_id": str - Patient ID if identified
                - "duplicates": List of duplicate chart file names
                - "all_chart_names": List of all identified chart names
        """
        if not charts_data:
            return {
                "chart_results": [],
                "same_patient": False,
                "patient_name": None,
                "patient_id": None,
                "duplicates": [],
                "all_chart_names": []
            }
        
        # Prepare chart samples for prompt
        chart_samples = []
        for idx, chart in enumerate(charts_data):
            file_name = chart.get("file_name", f"chart_{idx+1}")
            sample_text = chart.get("sample_text", "")
            chart_samples.append({
                "file_name": file_name,
                "sample_text": sample_text[:500]  # Limit to 500 chars per chart for prompt
            })
        
        # Create comprehensive prompt for multi-chart identification
        charts_text = ""
        for idx, chart_sample in enumerate(chart_samples):
            charts_text += f"\n\n--- CHART {idx+1}: {chart_sample['file_name']} ---\n"
            charts_text += chart_sample['sample_text']
            charts_text += f"\n--- END CHART {idx+1} ---\n"
        
        identification_prompt = f"""You are a medical document classification specialist with expertise in identifying different types of medical documents and verifying patient information across multiple charts.

TASK:
Analyze the following multiple medical document samples (first 100 words from each) and perform THREE critical checks:

1. IDENTIFY CHART TYPE for each document
2. VERIFY if all charts are from the SAME PATIENT (by Name or Patient ID)
3. CHECK for DUPLICATE charts (same chart type and same content)

CHART TYPE OPTIONS:
- operative_note: Surgical operative reports, procedure notes
- pre_operative_note: Pre-operative assessments, pre-surgical evaluations
- post_operative_note: Post-operative notes, post-surgical follow-ups
- progress_note: Daily progress notes, clinical progress notes
- nursing_note: Nursing documentation, nursing assessments
- discharge_summary: Discharge summaries, discharge notes
- consultation_note: Consultation reports, specialist consultations
- laboratory_report: Lab results, lab reports, blood work
- imaging_report: Imaging study reports (MRI, CT, X-ray, ultrasound)
- pathology_report: Pathology reports, biopsy reports, tissue analysis
- radiology_report: Radiology reports, radiology interpretations
- anesthesia_note: Anesthesia records, anesthesia notes
- emergency_note: Emergency department notes, ER notes
- admission_note: Admission notes, admission assessments
- billing_note: Billing documents, charge sheets
- other: Generic medical document

PATIENT IDENTIFICATION:
Look for patient identifiers in each chart:
- Patient Name: Look for "Patient Name:", "Name:", "Patient:", "PATIENT:" followed by a name
- Patient ID: Look for "Patient ID:", "MRN:", "Medical Record Number:", "ID:", "Account Number:", "Case Number:"
- Date of Birth: Look for "DOB:", "Date of Birth:", "Birth Date:"
- Age: Look for age information like "52-year-old", "67 years old"

SAME PATIENT CHECK:
Compare patient identifiers across ALL charts:
- If patient names match (exact or very similar), they are from the same patient
- If patient IDs match (exact match), they are from the same patient
- If both name and ID are present and match, confirm same patient
- If names are similar but IDs differ, note the discrepancy
- If no identifiers found, mark as "unknown"

DUPLICATE CHECK:
Check if any charts are duplicates:
- Same chart type AND same or very similar content
- Same file name or very similar file names
- Same procedures, same dates, same findings
- If duplicates found, list which charts are duplicates

CHART SAMPLES:
{charts_text}

Return ONLY a JSON object with these exact keys:
{{
  "charts": [
    {{
      "file_name": "exact file name from input",
      "chart_type": "one of the chart type options",
      "confidence": "high | medium | low",
      "reason": "brief explanation",
      "patient_name": "extracted patient name or null",
      "patient_id": "extracted patient ID or null"
    }}
  ],
  "same_patient": true or false,
  "same_patient_reason": "explanation of why charts are/are not from same patient",
  "patient_name": "common patient name if all charts are from same patient, or null",
  "patient_id": "common patient ID if all charts are from same patient, or null",
  "duplicates": ["list of file names that are duplicates"],
  "duplicate_reason": "explanation of why charts are duplicates"
}}

CRITICAL RULES:
- Return ONLY valid JSON, no other text
- For each chart, identify its type based on content (headers, terminology, structure)
- Extract patient name and ID from each chart if present
- Compare patient identifiers across all charts to determine if same patient
- Check for duplicate charts (same type + similar content)
- Be accurate: if patient info doesn't match, set same_patient to false
- If no patient identifiers found, set same_patient to false and patient_name/patient_id to null
- List all duplicate chart file names in the duplicates array
"""
        
        try:
            # Check cache
            cache_key = self.cache_manager.get_cache_key(
                identification_prompt, None, 2000, 0.0
            )
            cached_result = self.cache_manager.load_from_cache(cache_key)
            
            if cached_result:
                response, usage_info = cached_result
                print(f"[CACHE] Multi-chart identification cache HIT")
            else:
                print(f"[IDENTIFY] Identifying {len(charts_data)} chart(s) together...")
                response, usage_info = BedrockClient.call_claude(
                    identification_prompt,
                    max_tokens=2000,
                    temperature=0.0,
                    system_prompt=None
                )
                
                # Log and cache
                cost = (usage_info.get("input_tokens", 0) / 1000 * Config.INPUT_COST_PER_1K) + \
                       (usage_info.get("output_tokens", 0) / 1000 * Config.OUTPUT_COST_PER_1K)
                CDILogger.log_llm_call(
                    model=usage_info.get("model_id", "unknown"),
                    prompt_tokens=usage_info.get("input_tokens", 0),
                    completion_tokens=usage_info.get("output_tokens", 0),
                    cost=cost,
                    cache_hit=False,
                    purpose="multi_chart_type_identification"
                )
                self.cache_manager.save_to_cache(cache_key, response, usage_info)
            
            # Parse response
            import json
            import re
            
            # Extract JSON from response
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                # Try to find JSON object
                start = response.find('{')
                end = response.rfind('}') + 1
                if start >= 0 and end > start:
                    json_str = response[start:end]
                else:
                    raise ValueError("No JSON found in response")
            
            result = json.loads(json_str)
            
            # Validate and process results
            chart_results = []
            all_chart_names = []
            
            charts_list = result.get("charts", [])
            for chart_info in charts_list:
                chart_type = chart_info.get("chart_type", "other")
                if chart_type not in self.CHART_TYPES:
                    chart_type = "other"
                    chart_info["chart_type"] = chart_type
                    chart_info["confidence"] = "low"
                
                # Add display title
                chart_info["display_title"] = self.CHART_TYPE_DISPLAY_TITLES.get(
                    chart_type, "Medical Document"
                )
                
                chart_results.append(chart_info)
                all_chart_names.append(chart_info.get("file_name", "Unknown"))
            
            # Build final result
            final_result = {
                "chart_results": chart_results,
                "same_patient": result.get("same_patient", False),
                "same_patient_reason": result.get("same_patient_reason", ""),
                "patient_name": result.get("patient_name"),
                "patient_id": result.get("patient_id"),
                "duplicates": result.get("duplicates", []),
                "duplicate_reason": result.get("duplicate_reason", ""),
                "all_chart_names": all_chart_names
            }
            
            print(f"[IDENTIFY] Multi-chart identification completed:")
            print(f"  - Same Patient: {final_result['same_patient']}")
            print(f"  - Patient Name: {final_result.get('patient_name', 'Not found')}")
            print(f"  - Patient ID: {final_result.get('patient_id', 'Not found')}")
            print(f"  - Duplicates: {len(final_result['duplicates'])}")
            print(f"  - Chart Names: {', '.join(all_chart_names)}")
            
            return final_result
            
        except Exception as e:
            print(f"[WARNING] Multi-chart identification failed: {e}")
            import traceback
            traceback.print_exc()
            
            # Fallback: identify charts individually
            print(f"[FALLBACK] Identifying charts individually...")
            chart_results = []
            all_chart_names = []
            patient_names = []
            patient_ids = []
            
            for chart in charts_data:
                try:
                    chart_result = self.identify_chart_type(
                        chart.get("file_path", ""),
                        chart.get("sample_text", "")
                    )
                    chart_result["file_name"] = chart.get("file_name", "Unknown")
                    chart_results.append(chart_result)
                    all_chart_names.append(chart.get("file_name", "Unknown"))
                except Exception as e2:
                    print(f"[ERROR] Failed to identify chart {chart.get('file_name', 'Unknown')}: {e2}")
            
            return {
                "chart_results": chart_results,
                "same_patient": False,
                "same_patient_reason": f"Fallback mode: {str(e)}",
                "patient_name": None,
                "patient_id": None,
                "duplicates": [],
                "duplicate_reason": "Could not check duplicates in fallback mode",
                "all_chart_names": all_chart_names
            }
    
    @classmethod
    def get_display_title(cls, chart_type: str) -> str:
        """Get human-readable display title for a chart type."""
        return cls.CHART_TYPE_DISPLAY_TITLES.get(chart_type, "Medical Document")

