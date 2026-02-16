# Multi-Chart Implementation - Detailed Documentation

## Overview
This document provides a comprehensive explanation of the multi-chart functionality implementation. The system was upgraded from single-file processing to support processing multiple related medical charts as a complete inpatient record.

---

## Table of Contents
1. [Multi-Chart Initial Extraction](#1-multi-chart-initial-extraction)
2. [Prompt Side Updates in Main Model](#2-prompt-side-updates-in-main-model)
3. [Flow and Processing Logic](#3-flow-and-processing-logic)
4. [Streamlit UI Updates](#4-streamlit-ui-updates)
5. [Code-Level Changes Summary](#5-code-level-changes-summary)

---

## 1. Multi-Chart Initial Extraction

### 1.1 Chart Type Identification

**Purpose:** Before extraction, the system identifies what type of medical document each file represents.

**Location:** `src/multi_payer_cdi/chart_type_identifier.py`

**Key Implementation:**

```python
class ChartTypeIdentifier:
    """Identifies chart types from medical documents."""
    
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
    
    def identify_chart_type(self, file_path: str, text_sample: str) -> Dict[str, Any]:
        """
        Identify chart type from first 200 words of text using LLM.
        """
        # Creates a detailed prompt asking LLM to classify document type
        # Returns: chart_type, confidence, reason, display_title
```

**How It Works:**
1. Takes first 200 words from each chart file
2. Sends to LLM with a classification prompt
3. LLM analyzes headers, structure, terminology
4. Returns chart type with confidence score

**Example Prompt Structure:**
```
You are a medical document classification specialist.

TASK:
Analyze the following text sample and identify its SPECIFIC chart type.

CHART TYPE OPTIONS:
- operative_note: Surgical operative reports, procedure notes
- pre_operative_note: Pre-operative assessments, pre-surgical evaluations
- post_operative_note: Post-operative notes, recovery documentation
- progress_note: Daily progress notes, clinical progress notes
- nursing_note: Nursing documentation, nursing assessments
... (and more)

CRITICAL RULES:
- If you see "procedure performed" → operative_note
- If you see "pre-operative" → pre_operative_note
- If you see test values with units → laboratory_report
- BE SPECIFIC: Don't default to "other" unless absolutely necessary

TEXT SAMPLE:
{first_200_words}

Return JSON:
{
  "chart_type": "one of the chart type options",
  "confidence": "high | medium | low",
  "reason": "brief explanation"
}
```

### 1.2 Per-Chart Extraction

**Purpose:** Extract information from each chart individually using chart-type-specific prompts.

**Location:** `src/multi_payer_cdi/compliance_evaluator.py` - `run_extraction()` method

**Key Implementation:**

```python
def run_extraction(self, chart_text: str, chart_type: str = "operative_note") -> Tuple[str, Dict[str, Any]]:
    """
    Run extraction with chart-type-specific prompts.
    
    Args:
        chart_text: Medical chart text
        chart_type: Type of chart (operative_note, pre_operative_note, etc.)
    """
    # Select appropriate extraction prompt based on chart type
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
    
    # Call LLM with chart-type-specific prompt
    response, usage_info = self.call_claude_with_cache(
        extraction_prompt, 
        max_tokens=1500,
        temperature=0.0, 
        system_prompt=None, 
        cache_type=f"extraction_{chart_type}"  # Cache by chart type
    )
    
    return response, usage_info
```

**Chart-Type-Specific Extraction Prompts:**

#### A. Operative Note Extraction Prompt
**Location:** `_get_operative_extraction_prompt()`

**Extracts:**
- Patient name, age, specialty
- CPT codes
- Procedures performed
- Clinical summary

**Key Fields:**
```json
{
  "patient_name": "STRING",
  "patient_age": "STRING",
  "chart_specialty": "STRING",
  "cpt": ["ARRAY"],
  "procedure": ["ARRAY"],
  "summary": "STRING"
}
```

#### B. Pre-Operative Note Extraction Prompt
**Location:** `_get_pre_operative_extraction_prompt()`

**Extracts:**
- Patient information
- Planned procedures
- Pre-operative tests (labs, imaging, EKG)
- Diagnoses and indications
- Medications and allergies
- Risk assessment

**Key Fields:**
```json
{
  "patient_name": "STRING",
  "patient_age": "STRING",
  "chart_specialty": "STRING",
  "cpt": ["ARRAY"],
  "procedure": ["ARRAY"],  // Planned procedures
  "summary": "STRING",
  "diagnosis": ["ARRAY"],
  "tests": ["ARRAY"],  // Pre-op tests
  "reports": ["ARRAY"],  // Referenced reports
  "medications": ["ARRAY"],
  "allergies": ["ARRAY"],
  "risk_assessment": "STRING"
}
```

#### C. Post-Operative Note Extraction Prompt
**Location:** `_get_post_operative_extraction_prompt()`

**Extracts:**
- Procedures performed
- Post-operative complications
- Vital signs
- Pain management
- Discharge planning

**Key Fields:**
```json
{
  "patient_name": "STRING",
  "patient_age": "STRING",
  "chart_specialty": "STRING",
  "cpt": ["ARRAY"],
  "procedure": ["ARRAY"],
  "summary": "STRING",
  "post_op_complications": ["ARRAY"],
  "vital_signs": "STRING",
  "pain_management": "STRING",
  "discharge_planning": "STRING"
}
```

#### D. Progress Note / Nursing Note Extraction Prompt
**Location:** `_get_progress_note_extraction_prompt()`

**Extracts:**
- Current condition
- Vital signs
- Medications
- Assessments
- Interventions

**Key Fields:**
```json
{
  "patient_name": "STRING",
  "patient_age": "STRING",
  "chart_specialty": "STRING",
  "cpt": ["ARRAY"],
  "procedure": ["ARRAY"],
  "summary": "STRING",
  "current_condition": "STRING",
  "vital_signs": "STRING",
  "medications": ["ARRAY"],
  "assessments": ["ARRAY"],
  "interventions": ["ARRAY"]
}
```

#### E. Report Extraction Prompt (Lab/Imaging/Pathology)
**Location:** `_get_report_extraction_prompt()`

**Extracts:**
- Test/study name
- Results and findings
- Impression/conclusion
- Recommendations

**Key Fields:**
```json
{
  "patient_name": "STRING",
  "patient_age": "STRING",
  "chart_specialty": "STRING",
  "cpt": ["ARRAY"],
  "procedure": ["ARRAY"],
  "summary": "STRING",
  "test_name": "STRING",
  "results": ["ARRAY"],
  "impression": "STRING",
  "recommendations": ["ARRAY"]
}
```

### 1.3 Extraction Flow in Multi-Chart Processing

**Location:** `src/multi_payer_cdi/core.py` - `process_multiple_charts()` method

**Step-by-Step Process:**

```python
def process_multiple_charts(self, file_paths: List[str]) -> ProcessingResult:
    """
    Process multiple related medical charts as a complete inpatient record.
    """
    # Step 1: Read all files and get first 100 words for each
    chart_data = []
    for file_path in file_paths:
        original_text = FileProcessor.read_chart(file_path)
        words = original_text.split()[:100]
        sample_text = " ".join(words)
        
        chart_data.append({
            "file_path": file_path,
            "file_name": os.path.basename(file_path),
            "original_text": original_text,
            "sample_text": sample_text
        })
    
    # Step 2: Identify chart type for each file
    for chart in chart_data:
        chart_type_info = self.chart_type_identifier.identify_chart_type(
            chart["file_path"],
            chart["sample_text"]
        )
        chart["chart_type"] = chart_type_info.get("chart_type", "other")
        chart["chart_type_confidence"] = chart_type_info.get("confidence", "low")
        chart["display_title"] = chart_type_info.get("display_title", "Medical Document")
    
    # Step 3: Extract information from each chart separately
    all_extraction_data = {}
    combined_extraction = {
        "patient_name": "Unknown",
        "patient_age": "Unknown",
        "chart_specialty": "Unknown",
        "cpt": [],
        "procedure": [],
        "summary": "",
        "multi_chart_data": {}
    }
    
    # Identify operative chart (for procedures)
    operative_chart_file = None
    for chart in chart_data:
        if chart.get("chart_type") == "operative_note":
            operative_chart_file = chart["file_name"]
            break
    
    # Extract from each chart
    for chart in chart_data:
        file_name = chart["file_name"]
        chart_type = chart["chart_type"]
        chart_text = chart["original_text"]
        numbered_chart_text = FileProcessor.add_line_numbers(chart_text)
        
        # Run extraction with chart type
        llm_output, extraction_usage = self.compliance_evaluator.run_extraction(
            numbered_chart_text,
            chart_type=chart_type  # Pass chart type for specific prompt
        )
        
        # Parse extraction data
        extraction_data = safe_json_loads(llm_output, {})
        
        # Store per-chart extraction
        all_extraction_data[file_name] = {
            "chart_type": chart_type,
            "display_title": chart.get("display_title"),
            "extraction_data": extraction_data
        }
        
        # Combine key information
        # CRITICAL: Only use procedures from operative chart
        if file_name == operative_chart_file:
            procedures = extraction_data.get("procedure", [])
            if procedures:
                combined_extraction["procedure"] = procedures
        
        # Store chart-specific data
        combined_extraction["multi_chart_data"][file_name] = {
            "chart_type": chart_type,
            "extracted_info": extraction_data
        }
```

**Key Points:**
1. **Per-Chart Extraction:** Each chart is extracted separately using its identified chart type
2. **Operative Chart Priority:** Only procedures from the operative chart are used for CDI evaluation
3. **Combined Extraction:** Patient info, diagnoses, and other data are combined from all charts
4. **Chart-Specific Data:** Each chart's extraction data is stored separately for reference

---

## 2. Prompt Side Updates in Main Model

### 2.1 Chart-Type-Specific Extraction Prompts

**What Changed:**
- **Before:** Single extraction prompt for all charts (assumed operative notes)
- **After:** Multiple specialized prompts based on chart type

**Implementation Details:**

#### A. Operative Note Prompt (Existing - Enhanced)
**Location:** `src/multi_payer_cdi/compliance_evaluator.py:152`

**Key Features:**
- Extracts procedures, CPT codes, patient info
- Focuses on surgical procedures and findings
- Used for the main operative report

**Prompt Structure:**
```
You are a medical coding and CDI specialist.

TASK:
Analyze the following operative report/medical chart and return a JSON object.

REQUIRED JSON STRUCTURE:
{
  "patient_name": STRING,
  "patient_age": STRING,
  "chart_specialty": STRING,
  "cpt": ARRAY,
  "procedure": ARRAY,  // Surgical procedures
  "summary": STRING
}

EXTRACTION ORDER:
1. FIRST: Search for patient_name
2. SECOND: Search for patient_age
3. THIRD: Determine chart_specialty
4. FOURTH: Extract procedures from Procedure section
5. FIFTH: Look for CPT codes
6. LAST: Create summary

OPERATIVE REPORT:
<<<
{chart_text}
>>>
```

#### B. Pre-Operative Note Prompt (NEW)
**Location:** `src/multi_payer_cdi/compliance_evaluator.py:316`

**Key Features:**
- Extracts planned procedures (may not be performed yet)
- Extracts pre-operative tests and assessments
- Extracts indications, medications, allergies
- Extracts risk assessments

**Prompt Structure:**
```
You are a medical coding and CDI specialist.

TASK:
Analyze the following PRE-OPERATIVE note and extract important information.

REQUIRED JSON STRUCTURE:
{
  "patient_name": STRING,
  "patient_age": STRING,
  "chart_specialty": STRING,
  "cpt": ARRAY,
  "procedure": ARRAY,  // Planned procedures
  "summary": STRING,
  "diagnosis": ARRAY,  // Indications for surgery
  "tests": ARRAY,  // Pre-op tests (labs, imaging, EKG)
  "reports": ARRAY,  // Referenced reports
  "medications": ARRAY,
  "allergies": ARRAY,
  "risk_assessment": STRING
}

EXTRACTION FOCUS:
- Extract ALL planned procedures
- Extract ALL pre-operative tests
- Extract ALL diagnoses and indications
- Extract ALL reports referenced
- Extract medications and allergies
- Extract risk assessments

PRE-OPERATIVE NOTE:
<<<
{chart_text}
>>>
```

#### C. Post-Operative Note Prompt (NEW)
**Location:** `src/multi_payer_cdi/compliance_evaluator.py:359`

**Key Features:**
- Extracts procedures that were performed
- Extracts post-operative complications
- Extracts recovery status and vital signs
- Extracts pain management and discharge planning

**Prompt Structure:**
```
You are a medical coding and CDI specialist.

TASK:
Analyze the following POST-OPERATIVE note and extract important information.

REQUIRED JSON STRUCTURE:
{
  "patient_name": STRING,
  "patient_age": STRING,
  "chart_specialty": STRING,
  "cpt": ARRAY,
  "procedure": ARRAY,  // Procedures performed
  "summary": STRING,
  "post_op_complications": ARRAY,
  "vital_signs": STRING,
  "pain_management": STRING,
  "discharge_planning": STRING
}

EXTRACTION FOCUS:
- Extract procedures that were performed
- Extract post-operative complications
- Extract vital signs and recovery status
- Extract pain management information
- Extract discharge planning notes

POST-OPERATIVE NOTE:
<<<
{chart_text}
>>>
```

#### D. Progress Note / Nursing Note Prompt (NEW)
**Location:** `src/multi_payer_cdi/compliance_evaluator.py:399`

**Key Features:**
- Extracts current patient condition
- Extracts vital signs and medications
- Extracts assessments and interventions
- May extract procedures mentioned

**Prompt Structure:**
```
You are a medical coding and CDI specialist.

TASK:
Analyze the following PROGRESS NOTE or NURSING NOTE and extract information.

REQUIRED JSON STRUCTURE:
{
  "patient_name": STRING,
  "patient_age": STRING,
  "chart_specialty": STRING,
  "cpt": ARRAY,
  "procedure": ARRAY,  // Procedures mentioned
  "summary": STRING,
  "current_condition": STRING,
  "vital_signs": STRING,
  "medications": ARRAY,
  "assessments": ARRAY,
  "interventions": ARRAY
}

EXTRACTION FOCUS:
- Extract current patient condition
- Extract vital signs
- Extract medications
- Extract assessments and interventions
- Extract any procedures mentioned

PROGRESS/NURSING NOTE:
<<<
{chart_text}
>>>
```

#### E. Report Extraction Prompt (NEW)
**Location:** `src/multi_payer_cdi/compliance_evaluator.py:440`

**Key Features:**
- Extracts test/study name
- Extracts results and findings
- Extracts impression/conclusion
- Extracts recommendations

**Prompt Structure:**
```
You are a medical coding and CDI specialist.

TASK:
Analyze the following {REPORT_TYPE} REPORT and extract information.

REQUIRED JSON STRUCTURE:
{
  "patient_name": STRING,
  "patient_age": STRING,
  "chart_specialty": STRING,
  "cpt": ARRAY,
  "procedure": ARRAY,  // Tests/procedures performed
  "summary": STRING,
  "test_name": STRING,
  "results": ARRAY,
  "impression": STRING,
  "recommendations": ARRAY
}

EXTRACTION FOCUS:
- Extract test/study name
- Extract ALL results and findings
- Extract impression/conclusion
- Extract recommendations
- Extract any procedures or tests mentioned

{REPORT_TYPE} REPORT:
<<<
{chart_text}
>>>
```

### 2.2 Prompt Selection Logic

**Location:** `src/multi_payer_cdi/compliance_evaluator.py:87`

**Code:**
```python
def run_extraction(self, chart_text: str, chart_type: str = "operative_note") -> Tuple[str, Dict[str, Any]]:
    """
    Run extraction with chart-type-specific prompts.
    """
    # Select appropriate extraction prompt based on chart type
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
    
    # Call LLM with chart-type-specific prompt and cache by chart type
    response, usage_info = self.call_claude_with_cache(
        extraction_prompt, 
        max_tokens=1500,
        temperature=0.0, 
        system_prompt=None, 
        cache_type=f"extraction_{chart_type}"  # Cache key includes chart type
    )
    
    return response, usage_info
```

**Key Points:**
1. **Dynamic Prompt Selection:** Prompt is selected based on identified chart type
2. **Chart-Type-Specific Caching:** Cache key includes chart type for better cache hits
3. **Fallback to General:** Unknown chart types use general extraction prompt
4. **Consistent Output Format:** All prompts return similar JSON structure for compatibility

### 2.3 Chart Type Identification Prompt

**Location:** `src/multi_payer_cdi/chart_type_identifier.py:82`

**Purpose:** Classify medical documents into specific chart types before extraction.

**Prompt Structure:**
```
You are a medical document classification specialist.

TASK:
Analyze the following text sample (first 200 words) and identify its SPECIFIC chart type.

CHART TYPE OPTIONS:

OPERATIVE/SURGICAL DOCUMENTS:
- operative_note: Surgical operative reports, procedure notes
  Key indicators: "procedure performed", "operative report", "surgical technique"

PRE/POST-OPERATIVE DOCUMENTS:
- pre_operative_note: Pre-operative assessments, pre-surgical evaluations
  Key indicators: "pre-operative", "pre-op", "surgical clearance"
  
- post_operative_note: Post-operative notes, post-surgical follow-ups
  Key indicators: "post-operative", "post-op", "recovery documentation"

CLINICAL NOTES:
- progress_note: Daily progress notes, clinical progress notes
  Key indicators: "progress note", "daily note", "follow-up visit"
  
- consultation_note: Consultation reports, specialist consultations
  Key indicators: "consultation", "referral", "specialist opinion"
  
- nursing_note: Nursing documentation, nursing assessments
  Key indicators: "nursing assessment", "nurse's note"

HOSPITAL DOCUMENTS:
- discharge_summary: Discharge summaries, discharge notes
  Key indicators: "discharge summary", "discharge planning"
  
- admission_note: Admission notes, admission assessments
  Key indicators: "admission note", "admitting"

TEST/REPORT DOCUMENTS:
- laboratory_report: Lab results, lab reports, blood work
  Key indicators: "laboratory", "lab results", test values with units
  
- imaging_report: Imaging study reports (MRI, CT, X-ray)
  Key indicators: "MRI report", "CT scan report", imaging findings
  
- pathology_report: Pathology reports, biopsy reports
  Key indicators: "pathology report", "biopsy report", tissue analysis

CRITICAL RULES:
- If you see "procedure performed" → operative_note
- If you see "pre-operative" → pre_operative_note
- If you see test values with units → laboratory_report
- If you see "MRI findings" → imaging_report
- BE SPECIFIC: Don't default to "other" unless absolutely necessary

TEXT SAMPLE:
{first_200_words}

Return JSON:
{
  "chart_type": "one of the chart type options",
  "confidence": "high | medium | low",
  "reason": "brief explanation"
}
```

---

## 3. Flow and Processing Logic

### 3.1 Complete Multi-Chart Processing Flow

**Location:** `src/multi_payer_cdi/core.py:530` - `process_multiple_charts()` method

**High-Level Flow Diagram:**

```
1. Input Stage
   ↓
2. Chart Type Identification Stage
   ↓
3. Per-Chart Extraction Stage
   ↓
4. Chart Combination Stage
   ↓
5. Compliance Evaluation Stage
   ↓
6. Chart Improvement Stage
   ↓
7. Output Generation Stage
```

### 3.2 Detailed Step-by-Step Flow

#### Step 1: Input Stage
**Code:**
```python
# Read all files and get first 100 words for each
chart_data = []
for file_path in file_paths:
    if not FileProcessor.validate_file(file_path):
        print(f"[WARNING] Skipping invalid file: {file_path}")
        continue
    
    original_text = FileProcessor.read_chart(file_path)
    words = original_text.split()[:100]
    sample_text = " ".join(words)
    
    chart_data.append({
        "file_path": file_path,
        "file_name": os.path.basename(file_path),
        "original_text": original_text,
        "sample_text": sample_text
    })
```

**What Happens:**
- Validates each file
- Reads full content
- Extracts first 100 words for chart type identification
- Stores in `chart_data` list

#### Step 2: Chart Type Identification Stage
**Code:**
```python
# Identify chart type for each file
print(f"[IDENTIFY] Identifying chart types...")
for chart in chart_data:
    chart_type_info = self.chart_type_identifier.identify_chart_type(
        chart["file_path"],
        chart["sample_text"]
    )
    chart["chart_type"] = chart_type_info.get("chart_type", "other")
    chart["chart_type_confidence"] = chart_type_info.get("confidence", "low")
    chart["chart_type_reason"] = chart_type_info.get("reason", "")
    chart["display_title"] = chart_type_info.get("display_title", "Medical Document")
    print(f"[IDENTIFY] {chart['file_name']}: {chart['display_title']} ({chart['chart_type']})")
```

**What Happens:**
- For each chart, sends first 200 words to LLM
- LLM classifies chart type (operative_note, pre_operative_note, etc.)
- Stores chart type, confidence, and display title
- Identifies operative chart for procedure extraction

#### Step 3: Per-Chart Extraction Stage
**Code:**
```python
# Extract information from each chart separately
all_extraction_data = {}
combined_extraction = {
    "patient_name": "Unknown",
    "patient_age": "Unknown",
    "chart_specialty": "Unknown",
    "cpt": [],
    "procedure": [],
    "summary": "",
    "multi_chart_data": {}
}

# Identify operative chart (for procedures)
operative_chart_file = None
for chart in chart_data:
    if chart.get("chart_type") == "operative_note":
        operative_chart_file = chart["file_name"]
        break

# Extract from each chart
for chart in chart_data:
    file_name = chart["file_name"]
    chart_type = chart["chart_type"]
    chart_text = chart["original_text"]
    numbered_chart_text = FileProcessor.add_line_numbers(chart_text)
    
    # Run extraction with chart type
    llm_output, extraction_usage = self.compliance_evaluator.run_extraction(
        numbered_chart_text,
        chart_type=chart_type  # Pass chart type for specific prompt
    )
    
    # Parse extraction data
    extraction_data = safe_json_loads(llm_output, {})
    
    # Store per-chart extraction
    all_extraction_data[file_name] = {
        "chart_type": chart_type,
        "display_title": chart.get("display_title"),
        "extraction_data": extraction_data
    }
    
    # CRITICAL: Only use procedures from operative chart
    if file_name == operative_chart_file:
        procedures = extraction_data.get("procedure", [])
        if procedures:
            combined_extraction["procedure"] = procedures
    
    # Combine patient info (prefer non-"Unknown" values)
    if extraction_data.get("patient_name") and extraction_data.get("patient_name") != "Unknown":
        if combined_extraction["patient_name"] == "Unknown":
            combined_extraction["patient_name"] = extraction_data.get("patient_name")
    
    # Store chart-specific data
    combined_extraction["multi_chart_data"][file_name] = {
        "chart_type": chart_type,
        "extracted_info": extraction_data
    }
```

**What Happens:**
- Each chart is extracted separately using its chart type
- Operative chart is identified for procedure extraction
- Procedures are ONLY taken from operative chart (prevents mixing patients)
- Patient info is combined from all charts (prefer non-"Unknown" values)
- Each chart's extraction data is stored separately

**Key Logic:**
- **Procedure Extraction:** Only from operative chart
- **Patient Info:** Combined from all charts (best value wins)
- **Chart-Specific Data:** Stored separately for reference

#### Step 4: Chart Combination Stage
**Code:**
```python
# Combine all charts with markers for compliance evaluation
print(f"[COMBINE] Combining charts for compliance evaluation...")
combined_chart_text = ""
for chart in chart_data:
    file_name = chart["file_name"]
    chart_type = chart["chart_type"]
    chart_text = chart["original_text"]
    
    combined_chart_text += f"\n\n=== CHART: {file_name} (Type: {chart_type}) ===\n"
    combined_chart_text += chart_text
    combined_chart_text += f"\n=== END CHART: {file_name} ===\n"

numbered_combined_chart = FileProcessor.add_line_numbers(combined_chart_text)
```

**What Happens:**
- All charts are combined into single text
- Each chart is marked with file name and chart type
- Line numbers are added to combined chart
- Combined chart is used for compliance evaluation

**Format:**
```
=== CHART: pre_op_eval.pdf (Type: pre_operative_note) ===
[Pre-operative note content]
=== END CHART: pre_op_eval.pdf ===

=== CHART: operative_note.pdf (Type: operative_note) ===
[Operative note content]
=== END CHART: operative_note.pdf ===

=== CHART: progress_note_day1.pdf (Type: progress_note) ===
[Progress note content]
=== END CHART: progress_note_day1.pdf ===
```

#### Step 5: Compliance Evaluation Stage
**Code:**
```python
# Run compliance evaluation using combined chart and combined extraction
print(f"[COMPLIANCE] Running compliance evaluation with combined charts...")
combined_extraction_json = json.dumps(combined_extraction)
mapping_result = self.map_guidelines_for_case_text_multi_payer(
    combined_extraction_json,
    numbered_combined_chart
)
```

**What Happens:**
- Combined extraction (with procedures from operative chart) is converted to JSON
- Combined chart (all charts with markers) is used for evaluation
- Compliance evaluation runs as normal (one LLM call per procedure for all payers)
- Evidence extraction can reference any chart in the combined text

**Key Points:**
- Procedures come from operative chart only
- Evidence can come from any chart (pre-op, operative, post-op, progress notes)
- Compliance evaluation considers documentation across all charts

#### Step 6: Chart Improvement Stage
**Code:**
```python
# Generate improved chart
print("[CHART IMPROVEMENT] Generating AI-improved chart...")
improved_chart_data = self.chart_improver.improve_medical_chart(
    original_chart=combined_chart_text,  # Combined chart
    processing_result=result
)
```

**What Happens:**
- Chart improvement uses combined chart
- Improvements are mapped to appropriate chart types
- Recommendations specify which chart type needs improvement

#### Step 7: Output Generation Stage
**Code:**
```python
# Add multi-chart metadata
result.multi_chart_info = {
    "total_charts": len(chart_data),
    "chart_details": all_extraction_data,
    "combined_extraction": combined_extraction,
    "operative_chart": operative_chart_name,
    "other_charts_info": other_charts_info
}
```

**What Happens:**
- Multi-chart metadata is added to result
- Chart details (type, extraction data) are stored
- Operative chart is identified
- Other charts info (non-operative) is stored separately

**Output Structure:**
```python
ProcessingResult(
    file_name=", ".join([os.path.basename(fp) for fp in file_paths]),
    extraction_data=combined_extraction,  # Combined from all charts
    payer_results=mapping_result["result"]["payer_results"],
    numbered_medical_chart=numbered_combined_chart,  # Combined with markers
    original_chart=combined_chart_text,  # Combined without line numbers
    multi_chart_info={  # NEW: Multi-chart metadata
        "total_charts": 3,
        "chart_details": {...},
        "operative_chart": "operative_note.pdf",
        "other_charts_info": {...}
    }
)
```

### 3.3 Key Processing Logic Decisions

#### Decision 1: Procedure Extraction
**Rule:** Only extract procedures from operative chart

**Why:**
- Prevents mixing procedures from different patients
- Ensures procedures are actually performed (not just planned)
- Maintains data integrity

**Code:**
```python
# CRITICAL: Only use procedures from the operative chart for CDI evaluation
if file_name == operative_chart_file:
    procedures = extraction_data.get("procedure", [])
    if procedures:
        combined_extraction["procedure"] = procedures
else:
    # This is NOT the operative chart - don't add its procedures
    procedures = extraction_data.get("procedure", [])
    if procedures:
        print(f"[INFO] Found {len(procedures)} procedure(s) in non-operative chart {file_name}, but NOT using for CDI evaluation")
```

#### Decision 2: Patient Info Combination
**Rule:** Combine patient info from all charts, prefer non-"Unknown" values

**Why:**
- Patient info may be incomplete in one chart but present in another
- Ensures best available patient information is used

**Code:**
```python
# Use the most complete patient info (prefer non-"Unknown" values)
if extraction_data.get("patient_name") and extraction_data.get("patient_name") != "Unknown":
    if combined_extraction["patient_name"] == "Unknown":
        combined_extraction["patient_name"] = extraction_data.get("patient_name")

if extraction_data.get("patient_age") and extraction_data.get("patient_age") != "Unknown":
    if combined_extraction["patient_age"] == "Unknown":
        combined_extraction["patient_age"] = extraction_data.get("patient_age")
```

#### Decision 3: Chart Combination Format
**Rule:** Combine charts with clear markers showing file name and chart type

**Why:**
- Preserves chart boundaries for evidence extraction
- Allows evidence to reference specific charts
- Maintains context for compliance evaluation

**Code:**
```python
combined_chart_text += f"\n\n=== CHART: {file_name} (Type: {chart_type}) ===\n"
combined_chart_text += chart_text
combined_chart_text += f"\n=== END CHART: {file_name} ===\n"
```

#### Decision 4: Chart Type Identification
**Rule:** Identify chart type before extraction to use appropriate prompt

**Why:**
- Different chart types have different information structures
- Chart-type-specific prompts extract more relevant information
- Improves extraction accuracy

**Code:**
```python
# Step 2: Identify chart type
chart_type_info = self.chart_type_identifier.identify_chart_type(
    chart["file_path"],
    chart["sample_text"]
)
chart["chart_type"] = chart_type_info.get("chart_type", "other")

# Step 3: Extract with chart type
llm_output, extraction_usage = self.compliance_evaluator.run_extraction(
    numbered_chart_text,
    chart_type=chart_type  # Use identified chart type
)
```

### 3.4 Error Handling

**Location:** `src/multi_payer_cdi/core.py:889`

**Code:**
```python
except Exception as e:
    execution_time = time.time() - start_time
    print(f"[ERROR] Error processing multiple charts: {e}")
    self.logger.error(f"Multi-chart processing failed: {e}")
    
    # Log failed processing
    CDILogger.log_processing_result(
        file_name=", ".join([os.path.basename(fp) for fp in file_paths]) if file_paths else "unknown",
        payers_processed=0,
        procedures_evaluated=0,
        total_cost=0.0,
        execution_time=execution_time,
        success=False,
        error=str(e)
    )
    
    return ProcessingResult(
        file_name=", ".join([os.path.basename(fp) for fp in file_paths]) if file_paths else "unknown",
        extraction_data={},
        payer_results={},
        total_usage=UsageInfo(),
        total_cost=0.0,
        execution_times={},
        sources=[],
        numbered_medical_chart=None,
        original_chart=None,
        improved_chart_by_ai=None,
        enhanced_by_ai=None,
        error=str(e)
    )
```

**Error Handling Points:**
1. **Invalid Files:** Skipped with warning
2. **Chart Type Identification Failure:** Defaults to "other"
3. **Extraction Failure:** Continues with other charts
4. **No Operative Chart:** Uses first chart as fallback
5. **No Procedures Found:** Returns skeleton result
6. **Compliance Evaluation Failure:** Returns error result

---

## 4. Streamlit UI Updates

### 4.1 Multi-File Upload Support

**Location:** `streamlit_app.py:2938`

**Code:**
```python
# Multi-file upload
uploaded_files = st.file_uploader(
    "Upload medical chart file(s)",
    type=["pdf", "txt"],
    accept_multiple_files=True,  # NEW: Allow multiple files
    help="Upload one or more medical chart files. For multi-chart processing, upload all related charts together."
)

if uploaded_files:
    if len(uploaded_files) == 1:
        # Single file processing (existing flow)
        result = st.session_state.cdi_system.process_file(temp_file)
    else:
        # Multi-file processing (NEW)
        st.info(f"📋 {len(uploaded_files)} file(s) selected for multi-chart processing")
        temp_files = []
        for uploaded_file in uploaded_files:
            tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=Path(uploaded_file.name).suffix)
            tmp_file.write(uploaded_file.getvalue())
            tmp_file.close()
            temp_files.append(tmp_file.name)
        
        result = st.session_state.cdi_system.process_multiple_charts(temp_files)
```

**What Changed:**
- `accept_multiple_files=True` enables multi-file upload
- Detects single vs. multiple files
- Routes to appropriate processing method

### 4.2 Multi-Chart Information Display

**Location:** `streamlit_app.py:2365`

**Code:**
```python
# Multi-chart information display
multi_chart_info = getattr(result, "multi_chart_info", None)
if multi_chart_info:
    st.markdown("### 📁 Multi-Chart Processing")
    st.info(f"Processed {multi_chart_info.get('total_charts', 0)} chart(s) as a complete inpatient record")
    
    # Display chart details
    chart_details = multi_chart_info.get("chart_details", {})
    for file_name, details in chart_details.items():
        chart_type = details.get("chart_type", "unknown")
        display_title = details.get("display_title", "Medical Document")
        st.markdown(f"**{display_title}:** {file_name}")
    
    # Display operative chart
    operative_chart = multi_chart_info.get("operative_chart", "N/A")
    st.markdown(f"**Operative Chart:** {operative_chart}")
    
    # Display other charts info
    other_charts_info = multi_chart_info.get("other_charts_info", {})
    if other_charts_info:
        st.markdown("### 📄 Additional Charts")
        for file_name, info in other_charts_info.items():
            display_title = info.get("display_title", "Medical Document")
            st.markdown(f"**{display_title}:** {file_name}")
            # Display extracted information from non-operative charts
            extraction_data = info.get("extraction_data", {})
            if extraction_data.get("summary"):
                st.markdown(f"*Summary:* {extraction_data['summary'][:200]}...")
```

**What Changed:**
- Displays total number of charts processed
- Shows chart type for each chart
- Identifies operative chart
- Displays information from non-operative charts

### 4.3 Enhanced Extraction Display

**Location:** `streamlit_app.py:1945`

**Code:**
```python
# Display multi-chart extraction data
multi_chart_info = getattr(result, "multi_chart_info", None)
if multi_chart_info:
    other_charts_info = multi_chart_info.get("other_charts_info", {})
    
    # Display extraction from operative chart
    st.markdown("### 📋 Extraction from Operative Chart")
    # ... display operative chart extraction ...
    
    # Display extraction from other charts
    if other_charts_info:
        st.markdown("### 📄 Extraction from Additional Charts")
        for file_name, info in other_charts_info.items():
            display_title = info.get("display_title", "Medical Document")
            extraction_data = info.get("extraction_data", {})
            
            with st.expander(f"{display_title}: {file_name}"):
                # Display chart-specific extraction
                if extraction_data.get("diagnosis"):
                    st.markdown(f"**Diagnoses:** {', '.join(extraction_data['diagnosis'])}")
                if extraction_data.get("tests"):
                    st.markdown(f"**Tests:** {', '.join(extraction_data['tests'])}")
                if extraction_data.get("summary"):
                    st.markdown(f"**Summary:** {extraction_data['summary']}")
```

**What Changed:**
- Separates extraction display by chart type
- Shows operative chart extraction prominently
- Shows additional charts in expandable sections
- Displays chart-specific extracted information

---

## 5. Code-Level Changes Summary

### 5.1 New Files Created

1. **`src/multi_payer_cdi/chart_type_identifier.py`**
   - Chart type identification using LLM
   - Chart type to display title mapping
   - Classification prompt and logic

### 5.2 Modified Files

1. **`src/multi_payer_cdi/core.py`**
   - Added `process_multiple_charts()` method
   - Modified `__init__()` to initialize `ChartTypeIdentifier`
   - Enhanced error handling for multi-chart processing

2. **`src/multi_payer_cdi/compliance_evaluator.py`**
   - Modified `run_extraction()` to accept `chart_type` parameter
   - Added chart-type-specific extraction prompts:
     - `_get_pre_operative_extraction_prompt()`
     - `_get_post_operative_extraction_prompt()`
     - `_get_progress_note_extraction_prompt()`
     - `_get_report_extraction_prompt()`
     - `_get_general_extraction_prompt()`
   - Updated cache key to include chart type

3. **`src/multi_payer_cdi/models.py`**
   - Added `multi_chart_info` field to `ProcessingResult` model

4. **`streamlit_app.py`**
   - Added multi-file upload support
   - Added multi-chart information display
   - Enhanced extraction display for multi-chart results

### 5.3 Key Code Changes

#### Change 1: Chart Type Identification
**Before:**
```python
# No chart type identification - assumed all charts are operative notes
```

**After:**
```python
# Identify chart type before extraction
chart_type_info = self.chart_type_identifier.identify_chart_type(
    chart["file_path"],
    chart["sample_text"]
)
chart["chart_type"] = chart_type_info.get("chart_type", "other")
```

#### Change 2: Chart-Type-Specific Extraction
**Before:**
```python
def run_extraction(self, chart_text: str) -> Tuple[str, Dict[str, Any]]:
    extraction_prompt = self._get_operative_extraction_prompt(chart_text)
    # Always uses operative note prompt
```

**After:**
```python
def run_extraction(self, chart_text: str, chart_type: str = "operative_note") -> Tuple[str, Dict[str, Any]]:
    # Select prompt based on chart type
    if chart_type == "operative_note":
        extraction_prompt = self._get_operative_extraction_prompt(chart_text)
    elif chart_type == "pre_operative_note":
        extraction_prompt = self._get_pre_operative_extraction_prompt(chart_text)
    # ... more chart types
```

#### Change 3: Multi-Chart Processing
**Before:**
```python
def process_file(self, file_path: str) -> ProcessingResult:
    # Process single file only
```

**After:**
```python
def process_file(self, file_path: str) -> ProcessingResult:
    # Process single file (backward compatible)

def process_multiple_charts(self, file_paths: List[str]) -> ProcessingResult:
    # NEW: Process multiple charts as complete record
    # 1. Identify chart types
    # 2. Extract from each chart
    # 3. Combine charts
    # 4. Run compliance evaluation
    # 5. Generate improvements
```

#### Change 4: ProcessingResult Model
**Before:**
```python
class ProcessingResult:
    # ... existing fields ...
    # No multi-chart support
```

**After:**
```python
class ProcessingResult:
    # ... existing fields ...
    multi_chart_info: Optional[Dict[str, Any]] = None  # NEW: Multi-chart metadata
```

### 5.4 Backward Compatibility

**Key Point:** Single-file processing still works exactly as before.

**Code:**
```python
# Single file processing (unchanged)
result = cdi_system.process_file("single_chart.pdf")

# Multi-chart processing (new)
result = cdi_system.process_multiple_charts(["pre_op.pdf", "operative.pdf", "post_op.pdf"])
```

**Why:**
- `process_file()` method unchanged
- `run_extraction()` defaults to `chart_type="operative_note"`
- Existing workflows continue to work

---

## Summary

### What Was Added:
1. **Chart Type Identification:** LLM-based classification of medical documents
2. **Chart-Type-Specific Extraction:** Specialized prompts for different chart types
3. **Multi-Chart Processing:** Complete workflow for processing multiple charts together
4. **Chart Combination:** Smart combination of charts with markers
5. **Multi-Chart Metadata:** Storage of chart details and extraction data
6. **UI Updates:** Multi-file upload and enhanced display in Streamlit

### Key Benefits:
1. **Better Extraction:** Chart-type-specific prompts extract more relevant information
2. **Complete Records:** Process entire inpatient records, not just operative notes
3. **Cross-Chart Evidence:** Evidence can come from any chart in the record
4. **Backward Compatible:** Single-file processing still works
5. **Flexible:** Supports various chart types (pre-op, post-op, progress notes, reports, etc.)

### Processing Flow:
1. **Input** → Multiple files
2. **Identify** → Chart types for each file
3. **Extract** → From each chart using chart-type-specific prompts
4. **Combine** → Charts with markers
5. **Evaluate** → Compliance using combined chart
6. **Improve** → Generate improvements
7. **Output** → Comprehensive results with multi-chart metadata

---

## End of Document

