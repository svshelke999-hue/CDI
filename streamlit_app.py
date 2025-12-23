#!/usr/bin/env python3
"""
Streamlit UI for Multi-Payer CDI Compliance Checker.

Enhanced Clinical Documentation Improvement (CDI) system with multi-payer support,
RAG integration, and comprehensive prompt caching.
"""

import sys
import json
import os
from pathlib import Path
import tempfile
import streamlit as st
from datetime import datetime

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from multi_payer_cdi.core import MultiPayerCDI
from multi_payer_cdi.config import Config
from multi_payer_cdi.file_processor import FileProcessor
from multi_payer_cdi.chart_improver import ChartImprover
from multi_payer_cdi.cache_manager import CacheManager

# Brand assets (optional local files). If present, they'll be used.
_project_dir = Path(__file__).parent
# Prefer a user-provided 'logo' directory as the assets folder; fallback to 'assets'.
ASSETS_DIR = (_project_dir / "logo") if (_project_dir / "logo").exists() else (_project_dir / "assets")

# Candidate paths for logos/icons (try in order)
ASCENT_LOGO_CANDIDATES = [
    ASSETS_DIR / "ascent.png",
    ASSETS_DIR / "ascent_logo.png",
    _project_dir / "logo" / "ascent.png",
    _project_dir / "assets" / "ascent.png",
    _project_dir / "ascent.png",
    _project_dir / "ascent_logo.png",
]
CHART_ICON_CANDIDATES = [
    ASSETS_DIR / "images_logo.png",
    ASSETS_DIR / "medical_chart_icon.png",
    _project_dir / "logo" / "images_logo.png",
    _project_dir / "assets" / "images_logo.png",
    _project_dir / "images_logo.png",
    _project_dir / "medical_chart_icon.png",
]

def _first_existing(paths):
    for p in paths:
        if p.exists():
            return p
    return None

ASCENT_LOGO_FILE = _first_existing(ASCENT_LOGO_CANDIDATES)
CHART_ICON_FILE = _first_existing(CHART_ICON_CANDIDATES)

# Page configuration (use logo if available)
_page_icon = str(ASCENT_LOGO_FILE) if ASCENT_LOGO_FILE else "🏥"
st.set_page_config(
    page_title="Multi-Payer CDI Compliance Checker",
    page_icon=_page_icon,
    layout="wide",
    initial_sidebar_state="expanded"
)

# Brand colors (light purple and light peacock green)
PRIMARY_PURPLE = "#8B5CF6"     # light purple
ACCENT_TEAL = "#14B8A6"        # light peacock/teal
TEXT_DARK = "#2b2b2b"

# Custom CSS for brand styling
st.markdown(f"""
<style>
    :root {{
        --primary: {PRIMARY_PURPLE};
        --accent: {ACCENT_TEAL};
        --text-dark: {TEXT_DARK};
    }}

    /* Header */
    .main-header {{
        font-size: 2.5rem;
        font-weight: 800;
        color: var(--primary);
        text-align: center;
        padding: 1rem 0;
    }}

    .sub-header {{
        font-size: 1.5rem;
        font-weight: 700;
        color: var(--text-dark);
        margin-top: 1rem;
    }}

    .payer-section {{
        background-color: #f7f7ff; /* subtle purple tint */
        padding: 1rem;
        border-radius: 0.5rem;
        border: 1px solid #ecebff;
        margin: 1rem 0;
    }}

    .metric-card {{
        background-color: #ffffff;
        padding: 1rem;
        border-radius: 0.5rem;
        border: 1px solid #ebecef;
        text-align: center;
        box-shadow: 0 1px 2px rgba(0,0,0,0.04);
    }}

    .decision-sufficient {{ color: #1b7f5a; font-weight: 700; }}
    .decision-insufficient {{ color: #b3261e; font-weight: 700; }}
    .decision-not-applicable {{ color: #b56b00; font-weight: 700; }}

    .requirement-met {{
        background-color: #e6fff7; /* teal tint */
        padding: 0.5rem; border-radius: 0.25rem; margin: 0.25rem 0;
    }}
    .requirement-unmet {{
        background-color: #fff0f0;
        padding: 0.5rem; border-radius: 0.25rem; margin: 0.25rem 0;
    }}
    .requirement-unclear {{
        background-color: #fff7e6;
        padding: 0.5rem; border-radius: 0.25rem; margin: 0.25rem 0;
    }}

    /* Buttons */
    .stButton>button {{
        background: linear-gradient(90deg, var(--primary), var(--accent));
        color: #ffffff; border: 0; padding: 0.6rem 1rem; font-weight: 700;
        border-radius: 8px;
    }}
    .stButton>button:hover {{
        filter: brightness(1.05);
    }}

    /* Progress bar */
    .stProgress > div > div > div > div {{ background-color: var(--accent); }}

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] button[aria-selected="true"] {{
        border-bottom: 3px solid var(--primary);
    }}

    /* Sidebar accents */
    section[data-testid="stSidebar"] [data-testid="stHeader"] {{
        color: var(--primary);
    }}
</style>
""", unsafe_allow_html=True)


def initialize_session_state():
    """Initialize session state variables."""
    if 'cdi_system' not in st.session_state:
        st.session_state.cdi_system = None
    if 'processing_result' not in st.session_state:
        st.session_state.processing_result = None
    if 'file_processed' not in st.session_state:
        st.session_state.file_processed = False
    if 'chart_improver' not in st.session_state:
        st.session_state.chart_improver = None
    if 'improved_chart_result' not in st.session_state:
        st.session_state.improved_chart_result = None
    if 'original_chart_text' not in st.session_state:
        st.session_state.original_chart_text = None
    if 'user_input_fields' not in st.session_state:
        st.session_state.user_input_fields = {}


def initialize_cdi_system():
    """Initialize the CDI system."""
    try:
        with st.spinner("🔄 Initializing Multi-Payer CDI system..."):
            if st.session_state.cdi_system is None:
                st.session_state.cdi_system = MultiPayerCDI()
        return True
    except Exception as e:
        st.error(f"❌ Failed to initialize CDI system: {e}")
        st.error("Please check your configuration and ensure OpenSearch is running.")
        return False


def display_system_info():
    """Display system configuration in sidebar."""
    st.sidebar.markdown("### 🔧 System Configuration")
    
    if st.session_state.cdi_system:
        info = st.session_state.cdi_system.get_system_info()
        
        st.sidebar.markdown(f"**Version:** {info['version']}")
        st.sidebar.markdown(f"**Cache Enabled:** {'✅' if info['cache_enabled'] else '❌'}")
        
        # Display data source info
        data_source = info.get('data_source', 'unknown')
        st.sidebar.markdown(f"**Data Source:** {data_source.upper()}")
        
        # Show connection status based on data source
        if data_source == 'opensearch':
            opensearch_connected = info.get('opensearch_connected', False)
            st.sidebar.markdown(f"**OpenSearch:** {'✅ Connected' if opensearch_connected else '❌ Disconnected'}")
        elif data_source == 'json':
            json_available = info.get('json_files_available', {})
            available_count = sum(1 for v in json_available.values() if v)
            total_count = len(json_available)
            st.sidebar.markdown(f"**JSON Files:** ✅ {available_count}/{total_count} Available")
        
        st.sidebar.markdown(f"**Model:** {info['claude_model'].split('.')[-1]}")
        
        st.sidebar.markdown("**Configured Payers:**")
        for payer in info['configured_payers']:
            payer_config = Config.PAYER_CONFIG[payer]
            st.sidebar.markdown(f"- {payer_config['name']}")


def display_cache_stats():
    """Display cache statistics."""
    if st.session_state.cdi_system:
        st.sidebar.markdown("---")
        st.sidebar.markdown("### 💾 Cache Statistics")
        
        cache_stats = st.session_state.cdi_system.cache_manager.cache_stats
        
        col1, col2 = st.sidebar.columns(2)
        with col1:
            st.metric("Extraction Hits", cache_stats.extraction_hits)
            st.metric("Compliance Hits", cache_stats.compliance_hits)
        with col2:
            st.metric("Extraction Misses", cache_stats.extraction_misses)
            st.metric("Compliance Misses", cache_stats.compliance_misses)
        
        st.sidebar.metric("Hit Rate", f"{cache_stats.get_hit_rate():.1f}%")
        st.sidebar.metric("Total Savings", f"${cache_stats.total_savings_usd:.6f}")


def get_decision_class(decision):
    """Get CSS class for decision styling."""
    decision_lower = decision.lower()
    if "sufficient" in decision_lower:
        return "decision-sufficient"
    elif "insufficient" in decision_lower:
        return "decision-insufficient"
    else:
        return "decision-not-applicable"


def display_extraction_data(extraction_data):
    """Display extraction data in a formatted way."""
    st.markdown("### 📋 Extraction Results")
    
    # Check if CPT codes are present
    cpt_codes = extraction_data.get("cpt", [])
    has_cpt = extraction_data.get("has_cpt_codes", False) or (cpt_codes and len(cpt_codes) > 0)
    
    # Show CPT detection status prominently
    if has_cpt:
        procedures = extraction_data.get("procedure", [])
        num_cpt = len(cpt_codes)
        num_proc = len(procedures)
        
        st.success(f"🎯 **CPT CODES DETECTED** - Hybrid Processing")
        
        # Show CPT codes FIRST and prominently
        st.markdown("#### CPT Codes Found:")
        for code in cpt_codes:
            st.code(code, language=None)
        
        st.markdown("---")
        
        # Show procedures with indication of which use CPT vs RAG
        if procedures:
            if num_proc > num_cpt:
                # Mixed case
                st.markdown(f"**CPT-Associated Procedures ({num_cpt}):**")
                st.info("✓ Will use Direct CPT lookup")
                for proc in procedures[:num_cpt]:
                    st.markdown(f"• {proc}")
                
                st.markdown(f"**Additional Procedures ({num_proc - num_cpt}):**")
                st.info("ℹ️ Will use Procedure-based RAG search")
                for proc in procedures[num_cpt:]:
                    st.markdown(f"• {proc}")
            else:
                # All procedures have CPT codes
                st.markdown("**Associated Procedures:**")
                st.info("✓ All procedures will use Direct CPT lookup")
                for proc in procedures:
                    st.markdown(f"• {proc}")
    else:
        st.info("ℹ️ No CPT codes detected - Using procedure-based RAG search")
        
        st.markdown("---")
        
        # Show procedures when no CPT codes
        procedures = extraction_data.get("procedure", [])
        if procedures:
            st.markdown("**Procedures:**")
            for proc in procedures:
                st.markdown(f"• {proc}")
        else:
            st.info("No procedures detected")
    
    # Summary at the end
    st.markdown("---")
    st.markdown("**Clinical Summary:**")
    summary = extraction_data.get("summary", "No summary available")
    st.info(summary)


def display_medical_chart(numbered_chart):
    """Display the numbered medical chart."""
    if not numbered_chart:
        st.info("No medical chart available")
        return
    
    st.markdown("### 📄 Numbered Medical Chart")
    st.info("The medical chart with line numbers. Use these line numbers to cross-reference evidence in the compliance results.")
    
    # Display in a scrollable text area
    st.text_area(
        "Medical Chart with Line Numbers",
        numbered_chart,
        height=600,
        label_visibility="collapsed"
    )
    
    # Add download button for the chart
    st.download_button(
        label="📥 Download Numbered Chart",
        data=numbered_chart,
        file_name=f"numbered_chart_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
        mime="text/plain",
        width="stretch"
    )


def display_requirement_checklist(requirements, payer_key="unknown", proc_idx=0):
    """Display requirement checklist with color coding."""
    if not requirements:
        st.info("No requirements checklist available")
        return
    
    for req in requirements:
        status = req.get("status", "unclear")
        req_id = req.get("requirement_id", "Unknown")
        req_type = req.get("type", "single")
        missing = req.get("missing_to_meet", "N/A")
        suggestion = req.get("suggestion", "N/A")
        
        # Determine CSS class based on status
        if status == "met":
            css_class = "requirement-met"
            icon = "✅"
        elif status == "unmet":
            css_class = "requirement-unmet"
            icon = "❌"
        else:
            css_class = "requirement-unclear"
            icon = "❔"
        
        with st.container():
            st.markdown(f"""
            <div class="{css_class}">
                <strong>{icon} {req_id}</strong> ({req_type})<br>
                <strong>Status:</strong> {status.upper()}<br>
                <strong>Missing:</strong> {missing}<br>
                <strong>Suggestion:</strong> {suggestion}
            </div>
            """, unsafe_allow_html=True)


def display_timing_validation(timing):
    """Display timing validation information."""
    if not timing:
        st.info("No timing validation available")
        return
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        duration = timing.get("conservative_duration_weeks", "unknown")
        display_value = "Not Given" if duration == "unknown" else duration
        st.metric("Conservative Duration (weeks)", display_value)
    
    with col2:
        sessions = timing.get("pt_sessions_completed", "unknown")
        display_value = "Not Given" if sessions == "unknown" else sessions
        st.metric("PT Sessions Completed", display_value)
    
    with col3:
        interval = timing.get("follow_up_interval", "unknown")
        display_value = "Not Given" if interval == "unknown" else interval
        st.metric("Follow-up Interval", display_value)


def display_contraindications(contraindications):
    """Display contraindications and exclusions."""
    if not contraindications:
        st.info("No contraindications information available")
        return
    
    col1, col2 = st.columns(2)
    
    with col1:
        active_infection = contraindications.get("active_infection", "unclear")
        display_infection = "Not Documented" if active_infection == "unclear" else active_infection.title()
        infection_icon = "🔴" if active_infection == "present" else "🟢" if active_infection == "absent" else "🟡"
        st.markdown(f"{infection_icon} **Active Infection:** {display_infection}")
    
    with col2:
        severe_arthritis = contraindications.get("severe_arthritis", "unclear")
        display_arthritis = "Not Documented" if severe_arthritis == "unclear" else severe_arthritis.title()
        arthritis_icon = "🔴" if severe_arthritis == "present" else "🟢" if severe_arthritis == "absent" else "🟡"
        st.markdown(f"{arthritis_icon} **Severe Arthritis:** {display_arthritis}")
    
    other_contraindications = contraindications.get("other_contraindications", [])
    if other_contraindications:
        st.markdown("**Other Contraindications:**")
        for contra in other_contraindications:
            st.markdown(f"- {contra}")


def display_coding_implications(coding):
    """Display coding implications."""
    if not coding:
        st.info("No coding implications available")
        return
    
    eligible_codes = coding.get("eligible_codes_if_sufficient", [])
    notes = coding.get("notes", "")
    
    if eligible_codes:
        st.markdown("**Eligible CPT Codes:**")
        for code in eligible_codes:
            st.code(code, language=None)
    else:
        st.info("No eligible codes specified")
    
    if notes:
        st.markdown("**Notes:**")
        st.info(notes)


def display_improvement_recommendations(recommendations):
    """Display improvement recommendations."""
    if not recommendations:
        st.info("No improvement recommendations available")
        return
    
    priority = recommendations.get("priority", "medium")
    priority_colors = {
        "high": "🔴",
        "medium": "🟡",
        "low": "🟢"
    }
    priority_icon = priority_colors.get(priority.lower(), "⚪")
    
    st.markdown(f"**Priority:** {priority_icon} {priority.upper()}")
    
    doc_gaps = recommendations.get("documentation_gaps", [])
    if doc_gaps:
        st.markdown("**Documentation Gaps:**")
        for gap in doc_gaps:
            st.markdown(f"- {gap}")
    
    compliance_actions = recommendations.get("compliance_actions", [])
    if compliance_actions:
        st.markdown("**Compliance Actions:**")
        for action in compliance_actions:
            st.markdown(f"- {action}")


def display_payer_guideline_evidence(sources):
    """Display payer guideline evidence from sources."""
    if not sources:
        st.info("No evidence references available")
        return
    
    # Collect all payer references
    all_payer_refs = []
    for source in sources:
        payer_refs = source.get("payer_guideline_reference", [])
        all_payer_refs.extend(payer_refs)
    
    # Display payer references prominently at the top
    if all_payer_refs:
        unique_refs = sorted(set(all_payer_refs))
        st.markdown("### 📍 Payer Guideline References")
        st.success(f"Found **{len(unique_refs)}** evidence reference(s) in guideline documents")
        st.info("These references show the exact page and line numbers in the payer's guideline documents where requirements are documented:")
        
        # Parse and display references in a structured way
        parsed_refs = []
        for ref in unique_refs:
            # Extract page and line numbers
            import re
            match = re.search(r'pg\s+no:\s*(\d+).*?L(\d+(?:-L\d+)?)', ref)
            if match:
                page = match.group(1)
                lines = match.group(2)
                parsed_refs.append({
                    "page": page,
                    "lines": lines,
                    "full_ref": ref
                })
        
        # Display in a table if we have structured data
        if parsed_refs:
            import pandas as pd
            df = pd.DataFrame(parsed_refs)
            df.columns = ["Page Number", "Line Numbers", "Full Reference"]
            st.dataframe(df, width="stretch", hide_index=True)
        else:
            # Fallback to simple list
            refs_text = "\n".join([f"• {ref}" for ref in unique_refs])
            st.code(refs_text, language=None)
        
        st.markdown("---")
        st.caption("💡 Use these page and line numbers to verify requirements in the payer's guideline PDF")
    else:
        st.warning("⚠️ No inline evidence references found in the retrieved guidelines")
    
    # Display guideline source files
    st.markdown("### 📄 Guideline Source Files")
    
    # Group sources by file
    sources_by_file = {}
    for source in sources:
        file_name = source.get('file', 'Unknown')
        if file_name not in sources_by_file:
            sources_by_file[file_name] = []
        sources_by_file[file_name].append(source)
    
    for file_name, file_sources in sources_by_file.items():
        with st.expander(f"📁 {file_name} ({len(file_sources)} guideline(s))", expanded=False):
            # Collect all references from this file
            file_refs = []
            for source in file_sources:
                payer_refs = source.get("payer_guideline_reference", [])
                file_refs.extend(payer_refs)
            
            unique_file_refs = sorted(set(file_refs))
            if unique_file_refs:
                st.markdown("**Evidence References from this file:**")
                for ref in unique_file_refs:
                    st.markdown(f"- `{ref}`")
            
            # Show guideline details
            for idx, source in enumerate(file_sources, 1):
                st.caption(f"Guideline {idx}: {source.get('record_id', 'N/A')}")
                description = source.get("description", "")
                if description and len(description) > 0:
                    with st.expander(f"View guideline {idx} content preview"):
                        st.text(description[:500] + "..." if len(description) > 500 else description)


def display_procedure_result(proc_result, proc_idx, payer_key="unknown"):
    """Display a single procedure result with all details."""
    # Get original procedure name for display
    original_proc_name = proc_result.get("_original_procedure_name", "")
    procedure_name = proc_result.get("procedure_evaluated", "Unknown Procedure")
    # Prefer original name if available
    display_name = original_proc_name if original_proc_name else procedure_name
    
    variant = proc_result.get("variant_or_subprocedure", "")
    policy_name = proc_result.get("policy_name", "Unknown Policy")
    decision = proc_result.get("decision", "Unknown")
    primary_reasons = proc_result.get("primary_reasons", [])
    
    # Determine search method used
    cpt_guidelines = proc_result.get("cpt_specific_guidelines", [])
    procedure_guidelines = proc_result.get("procedure_guidelines", [])
    search_method = ""
    if cpt_guidelines:
        search_method = " [CPT Lookup]"
    elif procedure_guidelines:
        search_method = " [RAG Search]"
    
    # Create expander for procedure - use display name
    with st.expander(f"📋 Procedure {proc_idx}: {display_name}{search_method}", expanded=False):
        # Show mapping if Claude returned different name
        if original_proc_name and original_proc_name != procedure_name:
            st.info(f"📌 Input: **{original_proc_name}** → Evaluated as: **{procedure_name}**")
        
        # Basic information
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown(f"**Variant/Subprocedure:** {variant}")
            st.markdown(f"**Policy:** {policy_name}")
            
            # Show guideline source
            guideline_source = proc_result.get("guideline_source", "unknown")
            if guideline_source == "payer":
                st.markdown("**Guideline Type:** 🎯 Payer-Specific")
            elif guideline_source == "general":
                st.markdown("**Guideline Type:** 📋 General Medical Necessity")
            elif guideline_source == "error":
                st.markdown("**Guideline Type:** ⚠️ Error")
        
        with col2:
            # Replace "Not Applicable" with "No Payer Guidelines"
            display_decision = decision
            if 'not applicable' in decision.lower():
                display_decision = "No Payer Guidelines"
            elif 'no guidelines available' in decision.lower():
                display_decision = "No Payer Guidelines"
            
            decision_class = get_decision_class(decision)
            st.markdown(f"**Decision:** <span class='{decision_class}'>{display_decision}</span>", 
                       unsafe_allow_html=True)
        
        # Primary reasons
        if primary_reasons:
            st.markdown("**Primary Reasons:**")
            for reason in primary_reasons:
                st.markdown(f"- {reason}")
        
        # Display medical chart evidence line numbers at procedure level
        st.markdown("---")
        medical_chart_refs = proc_result.get("medical_chart_reference", [])
        if medical_chart_refs:
            st.markdown("**📋 Medical Chart Evidence Line Numbers:**")
            st.success(f"Found {len(medical_chart_refs)} line reference(s) from medical chart where evidence was found")
            
            # Display line numbers in a more visible format
            col1, col2 = st.columns([3, 1])
            with col1:
                refs_display = ", ".join([f"`{ref}`" for ref in medical_chart_refs])
                st.markdown(refs_display)
            with col2:
                st.metric("Total Lines", len(medical_chart_refs))
            
            st.info("💡 Use these line numbers to find corresponding evidence in the Medical Chart tab")
        else:
            st.warning("⚠️ No medical chart line references found for this procedure")
        
        # Display BOTH CPT-specific AND procedure-based guidelines (for mixed cases)
        cpt_guidelines = proc_result.get("cpt_specific_guidelines", [])
        procedure_guidelines = proc_result.get("procedure_guidelines", [])
        
        # Display CPT-specific guidelines first
        if cpt_guidelines:
            st.markdown("---")
            st.markdown("### 🎯 CPT-Specific Guidelines")
            st.success(f"✓ Found {len(cpt_guidelines)} guideline(s) containing the specified CPT codes")
            
            for idx, guideline in enumerate(cpt_guidelines, 1):
                procedure_name = guideline.get("procedure_name", "Unknown Procedure")
                cpt_codes = guideline.get("cpt_codes", [])
                guideline_text = guideline.get("guideline_text", "No content available")
                evidence_summary = guideline.get("evidence_summary", "No references")
                evidence_count = guideline.get("evidence_count", 0)
                
                # Display guideline with CPT codes
                cpt_display = ", ".join(cpt_codes) if cpt_codes else "Unknown"
                with st.expander(f"**Guideline {idx}** | CPT: {cpt_display} | {procedure_name}", expanded=idx==1):
                    # Header info
                    col1, col2 = st.columns([2, 1])
                    with col1:
                        st.markdown(f"**CPT Code(s):** `{cpt_display}`")
                        st.markdown(f"**Procedure:** {procedure_name}")
                    with col2:
                        st.markdown(f"**Evidence:** {evidence_summary}")
                    
                    # Add dropdown for evidence references if count > 0
                    if evidence_count > 0:
                        # Get the actual evidence references from sources
                        evidence_refs = []
                        for source in proc_result.get("sources", []):
                            refs = source.get("payer_guideline_reference", [])
                            evidence_refs.extend(refs)
                        
                        unique_evidence = sorted(set(evidence_refs))
                        
                        if unique_evidence:
                            with st.expander(f"📍 View all {len(unique_evidence)} PDF evidence references", expanded=False):
                                st.caption("Page and line numbers from the payer's guideline PDF:")
                                # Display in columns for better readability
                                refs_per_col = 20
                                num_cols = min(3, (len(unique_evidence) + refs_per_col - 1) // refs_per_col)
                                cols = st.columns(num_cols)
                                
                                for i, ref in enumerate(unique_evidence):
                                    col_idx = i % num_cols
                                    cols[col_idx].markdown(f"• `{ref}`")
                    
                    st.markdown("---")
                    
                    # Guideline content with proper formatting
                    st.markdown("#### 📋 Medical Necessity Requirements")
                    
                    # Display the guideline text with proper formatting
                    lines = guideline_text.split('\n')
                    for line in lines:
                        if line.startswith('Description:'):
                            st.markdown(f"**{line}**")
                        elif line.startswith('Documentation Requirements:') or line.startswith('Exclusions:') or line.startswith('Notes:'):
                            st.markdown(f"**{line}**")
                        elif line.strip().startswith('•'):
                            st.markdown(line)
                        elif line.strip():
                            st.markdown(line)
                    
                    if evidence_count > 0:
                        st.caption(f"💡 Supported by {evidence_count} reference(s) in payer's guideline PDF")
        
        # Display procedure-based guidelines (for procedures without CPT codes)
        if procedure_guidelines:
            st.markdown("---")
            st.markdown("### 📋 Procedure-Based Guidelines (No CPT Codes)")
            st.info(f"ℹ️ Found {len(procedure_guidelines)} guideline(s) for procedures without CPT codes")
            
            for idx, guideline in enumerate(procedure_guidelines, 1):
                procedure_name = guideline.get("procedure_name", "Unknown Procedure")
                guideline_text = guideline.get("guideline_text", "No content available")
                evidence_summary = guideline.get("evidence_summary", "No references")
                evidence_count = guideline.get("evidence_count", 0)
                
                # Display guideline with procedure name only
                header = f"**Guideline {idx}** | {procedure_name}"
                
                with st.expander(header, expanded=False):
                    # Header info
                    col1, col2 = st.columns([2, 1])
                    with col1:
                        st.markdown(f"**Procedure:** {procedure_name}")
                    with col2:
                        st.markdown(f"**Evidence:** {evidence_summary}")
                    
                    # Add dropdown for evidence references if count > 0
                    if evidence_count > 0:
                        # Get the actual evidence references from sources
                        evidence_refs = []
                        for source in proc_result.get("sources", []):
                            refs = source.get("payer_guideline_reference", [])
                            evidence_refs.extend(refs)
                        
                        unique_evidence = sorted(set(evidence_refs))
                        
                        if unique_evidence:
                            with st.expander(f"📍 View all {len(unique_evidence)} PDF evidence references", expanded=False):
                                st.caption("Page and line numbers from the payer's guideline PDF:")
                                # Display in columns for better readability
                                refs_per_col = 20
                                num_cols = min(3, (len(unique_evidence) + refs_per_col - 1) // refs_per_col)
                                cols = st.columns(num_cols)
                                
                                for i, ref in enumerate(unique_evidence):
                                    col_idx = i % num_cols
                                    cols[col_idx].markdown(f"• `{ref}`")
                    
                    st.markdown("---")
                    
                    # Guideline content with proper formatting
                    st.markdown("#### 📋 Medical Necessity Requirements")
                    
                    # Display the guideline text with proper formatting
                    lines = guideline_text.split('\n')
                    for line in lines:
                        if line.startswith('Description:'):
                            st.markdown(f"**{line}**")
                        elif line.startswith('Documentation Requirements:') or line.startswith('Exclusions:') or line.startswith('Notes:'):
                            st.markdown(f"**{line}**")
                        elif line.strip().startswith('•'):
                            st.markdown(line)
                        elif line.strip():
                            st.markdown(line)
                    
                    if evidence_count > 0:
                        st.caption(f"💡 Supported by {evidence_count} reference(s) in payer's guideline PDF")
        
        # Display payer guideline references
        sources = proc_result.get("sources", [])
        all_payer_refs = []
        for source in sources:
            payer_refs = source.get("payer_guideline_reference", [])
            all_payer_refs.extend(payer_refs)
        
        if all_payer_refs:
            unique_refs = sorted(set(all_payer_refs))
            st.markdown("**📍 Payer Guideline References:**")
            refs_display = ", ".join([f"`{ref}`" for ref in unique_refs[:3]])  # Show first 3
            if len(unique_refs) > 3:
                refs_display += f" and {len(unique_refs) - 3} more"
            st.markdown(refs_display)
            st.caption(f"Total {len(unique_refs)} reference(s) from payer guideline documents")
        
        # Detailed sections in tabs
        tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
            "📝 Requirements", 
            "📋 Chart Evidence",
            "⏰ Timing", 
            "⚠️ Contraindications", 
            "💊 Coding", 
            "📈 Recommendations",
            "📄 Guideline Evidence"
        ])
        
        with tab1:
            st.markdown("#### Requirement Checklist")
            requirements = proc_result.get("requirement_checklist", [])
            display_requirement_checklist(requirements, payer_key, proc_idx)
        
        with tab2:
            st.markdown("#### Medical Chart Evidence Line Numbers")
            medical_chart_refs = proc_result.get("medical_chart_reference", [])
            if medical_chart_refs:
                st.info("These line numbers indicate where evidence was found in the medical chart. Use the Medical Chart tab to view the corresponding lines.")
                
                # Display as a formatted list
                st.markdown("**Line Numbers:**")
                # Group by ranges if applicable
                refs_text = "\n".join([f"• {ref}" for ref in medical_chart_refs])
                st.code(refs_text, language=None)
                
                st.metric("Total Evidence Lines", len(medical_chart_refs))
                
                st.caption("💡 Tip: Go to the Medical Chart tab and search for these line numbers (e.g., L012, L023)")
            else:
                st.warning("No medical chart line references found for this procedure")
        
        with tab3:
            st.markdown("#### Timing Validation")
            timing = proc_result.get("timing_validation", {})
            display_timing_validation(timing)
        
        with tab4:
            st.markdown("#### Contraindications & Exclusions")
            contraindications = proc_result.get("contraindications_exclusions", {})
            display_contraindications(contraindications)
        
        with tab5:
            st.markdown("#### Coding Implications")
            coding = proc_result.get("coding_implications", {})
            display_coding_implications(coding)
        
        with tab6:
            st.markdown("#### Improvement Recommendations")
            recommendations = proc_result.get("improvement_recommendations", {})
            display_improvement_recommendations(recommendations)
        
        with tab7:
            st.markdown("#### Payer Guideline Evidence")
            st.markdown("Evidence sources from payer guideline documents:")
            # Get sources from the procedure result if available
            sources = proc_result.get("sources", [])
            display_payer_guideline_evidence(sources)


def display_payer_results(payer_key, payer_result):
    """Display results for a specific payer."""
    payer_name = payer_result.get("payer_name", "Unknown Payer")
    procedures_evaluated = payer_result.get("procedures_evaluated", 0)
    procedure_results = payer_result.get("procedure_results", [])
    usage = payer_result.get("usage", {})
    error = payer_result.get("error")
    
    # Payer header
    st.markdown(f"### 🏥 {payer_name}")
    
    # Error handling
    if error:
        st.error(f"❌ Error: {error}")
        return
    
    # Metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Procedures Evaluated", procedures_evaluated)
    
    with col2:
        # Handle both UsageInfo object and dict
        if hasattr(usage, "input_tokens"):
            input_tokens = usage.input_tokens
        else:
            input_tokens = usage.get("input_tokens", 0) if usage else 0
        st.metric("Input Tokens", f"{input_tokens:,}")
    
    with col3:
        # Handle both UsageInfo object and dict
        if hasattr(usage, "output_tokens"):
            output_tokens = usage.output_tokens
        else:
            output_tokens = usage.get("output_tokens", 0) if usage else 0
        st.metric("Output Tokens", f"{output_tokens:,}")
    
    with col4:
        # Handle both UsageInfo object and dict
        if hasattr(usage, "total_cost"):
            total_cost = usage.total_cost
        else:
            total_cost = usage.get("total_cost", 0.0) if usage else 0.0
        st.metric("Cost", f"${total_cost:.6f}")
    
    st.markdown("---")
    
    # Evidence Summary for this payer
    all_payer_refs = []
    all_chart_refs = []
    
    for proc_result in procedure_results:
        # Collect payer guideline references
        sources = proc_result.get("sources", [])
        for source in sources:
            payer_refs = source.get("payer_guideline_reference", [])
            all_payer_refs.extend(payer_refs)
        
        # Collect medical chart references
        chart_refs = proc_result.get("medical_chart_reference", [])
        all_chart_refs.extend(chart_refs)
    
    unique_payer_refs = list(set(all_payer_refs))
    unique_chart_refs = list(set(all_chart_refs))
    
    # Display evidence summary
    if unique_payer_refs or unique_chart_refs:
        summary_parts = []
        if unique_payer_refs:
            summary_parts.append(f"📍 {len(unique_payer_refs)} payer guideline reference(s)")
        if unique_chart_refs:
            summary_parts.append(f"📋 {len(unique_chart_refs)} medical chart line reference(s)")
        
        st.info(" | ".join(summary_parts))
        
        # Show sample references
        if unique_chart_refs:
            st.caption(f"Chart references: {', '.join(sorted(unique_chart_refs)[:5])}")
        if unique_payer_refs:
            st.caption(f"Guideline references: {', '.join(sorted(unique_payer_refs)[:3])}")
    
    st.markdown("---")
    
    # Display each procedure result
    if procedure_results:
        for idx, proc_result in enumerate(procedure_results, 1):
            display_procedure_result(proc_result, idx, payer_key)
    else:
        st.info("No procedure results available")


def display_payer_results_simple(payer_results):
    """Display payer results in exact tabular format as shown in image."""
    for payer_key, payer_result in payer_results.items():
        # Extract payer name
        if isinstance(payer_result, dict):
            payer_name = payer_result.get('payer_name', payer_key)
            procedure_results = payer_result.get('procedure_results', [])
        else:
            payer_name = getattr(payer_result, 'payer_name', payer_key)
            procedure_results = getattr(payer_result, 'procedure_results', [])
        
        st.markdown(f"#### {payer_name} Results")
        
        # Count decisions and get cost
        sufficient_count = 0
        insufficient_count = 0
        payer_cost = 0
        
        for proc_result in procedure_results:
            if isinstance(proc_result, dict):
                decision = proc_result.get('decision', '').lower()
            else:
                decision = getattr(proc_result, 'decision', '').lower()
            
            if 'sufficient' in decision:
                sufficient_count += 1
            elif 'insufficient' in decision:
                insufficient_count += 1
        
        # Get cost
        if isinstance(payer_result, dict):
            usage = payer_result.get('usage', {})
            if usage and isinstance(usage, dict):
                payer_cost = usage.get('cost', 0)
            else:
                payer_cost = getattr(usage, 'cost', 0) if usage else 0
        else:
            if hasattr(payer_result, 'usage') and payer_result.usage:
                payer_cost = getattr(payer_result.usage, 'cost', 0)
            else:
                payer_cost = 0
        
        # Summary pills (exact format from image)
        pills_html = f"""
        <div style='margin-bottom: 16px;'>
            <span style='padding: 4px 12px; border: 1px solid #ddd; border-radius: 999px; display: inline-block; font-size: 0.9rem; margin-right: 8px;'>✅ Sufficient: {sufficient_count}</span>
            <span style='padding: 4px 12px; border: 1px solid #ddd; border-radius: 999px; display: inline-block; font-size: 0.9rem; margin-right: 8px;'>❌ Insufficient: {insufficient_count}</span>
            <span style='padding: 4px 12px; border: 1px solid #ddd; border-radius: 999px; display: inline-block; font-size: 0.9rem;'>💰 Payer Cost: ${payer_cost:.6f}</span>
        </div>
        """
        st.markdown(pills_html, unsafe_allow_html=True)
        
        # Display each procedure in tabular format
        for proc_result in procedure_results:
            if isinstance(proc_result, dict):
                proc_name = proc_result.get('procedure_evaluated', 'Unknown')
                decision = proc_result.get('decision', 'Unknown')
                reasons = proc_result.get('primary_reasons', [])
                req_checklist = proc_result.get('requirement_checklist', [])
                chart_refs = proc_result.get('medical_chart_reference', [])
                improvement = proc_result.get('improvement_recommendations', {})
                suggestions = improvement.get('compliance_actions', []) if improvement else []
            else:
                proc_name = getattr(proc_result, 'procedure_evaluated', 'Unknown')
                decision = getattr(proc_result, 'decision', 'Unknown')
                reasons = getattr(proc_result, 'primary_reasons', [])
                req_checklist = getattr(proc_result, 'requirement_checklist', [])
                chart_refs = getattr(proc_result, 'medical_chart_reference', [])
                improvement = getattr(proc_result, 'improvement_recommendations', {})
                suggestions = improvement.get('compliance_actions', []) if improvement else []
            
            # Get guideline source
            if isinstance(proc_result, dict):
                guideline_source = proc_result.get('guideline_source', 'unknown')
            else:
                guideline_source = getattr(proc_result, 'guideline_source', 'unknown')
            
            # Guideline source badge
            if guideline_source == 'payer':
                guideline_badge = "<span style='background: #dbeafe; color: #1e3a8a; padding: 2px 6px; border-radius: 4px; font-size: 0.75rem; margin-left: 8px;'>🎯 Payer</span>"
            elif guideline_source == 'general':
                guideline_badge = "<span style='background: #fef3c7; color: #92400e; padding: 2px 6px; border-radius: 4px; font-size: 0.75rem; margin-left: 8px;'>📋 General</span>"
            else:
                guideline_badge = ""
            
            # Decision badge - Replace "Not Applicable" with "No Payer Guidelines"
            display_decision = decision
            if 'not applicable' in decision.lower():
                display_decision = "No Payer Guidelines"
            elif 'no guidelines available' in decision.lower():
                display_decision = "No Payer Guidelines"
            
            if 'sufficient' in decision.lower() and 'insufficient' not in decision.lower():
                badge_html = f"<span style='background: #ecfdf5; color: #065f46; padding: 4px 8px; border-radius: 6px; border: 1px solid #a7f3d0; font-size: 0.85rem; font-weight: 600;'>{display_decision}</span>"
            elif 'insufficient' in decision.lower():
                badge_html = f"<span style='background: #fff7ed; color: #7c2d12; padding: 4px 8px; border-radius: 6px; border: 1px solid #fed7aa; font-size: 0.85rem; font-weight: 600;'>{display_decision}</span>"
            else:
                badge_html = f"<span style='background: #f1f5f9; color: #334155; padding: 4px 8px; border-radius: 6px; border: 1px solid #cbd5e1; font-size: 0.85rem; font-weight: 600;'>{display_decision}</span>"
            
            st.markdown(f"**📋 {proc_name}** {badge_html}{guideline_badge}", unsafe_allow_html=True)
            
            # Primary Reasons
            reasons_html = "<ul style='margin: 4px 0;'>" + "".join([f"<li>{r}</li>" for r in reasons]) + "</ul>" if reasons else "None"
            
            # Payer Requirements Matched
            requirements_html = "<ul style='margin: 4px 0;'>"
            for req in req_checklist:
                if isinstance(req, dict):
                    req_id = req.get('requirement_id', 'Unknown').replace('_', ' ').title()
                    status = req.get('status', 'unclear')
                else:
                    req_id = getattr(req, 'requirement_id', 'Unknown').replace('_', ' ').title()
                    status = getattr(req, 'status', 'unclear')
                
                req_badge = f"<span style='background: #f1f5f9; color: #334155; padding: 2px 6px; border-radius: 6px; border: 1px solid #cbd5e1; font-size: 0.75rem; margin-right: 4px;'>{req_id}</span>"
                requirements_html += f"<li>{req_badge} {req_id}</li>"
            requirements_html += "</ul>" if req_checklist else "No specific requirements listed"
            
            # Evidence Extracts
            evidence_html = "<ul style='margin: 4px 0;'>"
            for ref in chart_refs[:3]:  # Show top 3
                evidence_html += f"<li><code style='background: #f1f5f9; padding: 2px 6px; border-radius: 4px; font-size: 0.85rem;'>{ref}</code> Evidence from chart</li>"
            evidence_html += "</ul>" if chart_refs else "No line references extracted"
            
            # Suggestions
            suggestions_html = "<ul style='margin: 4px 0;'>" + "".join([f"<li>{s}</li>" for s in suggestions[:3]]) + "</ul>" if suggestions else "None"
            
            # Display as HTML table (exact format from image)
            table_html = f"""
            <table style='width: 100%; border-collapse: collapse; margin-bottom: 16px; font-size: 0.9rem;'>
                <tbody>
                    <tr>
                        <th style='border: 1px solid #eee; padding: 8px; text-align: left; background: #fafafa; width: 200px;'>Primary Reasons</th>
                        <td style='border: 1px solid #eee; padding: 8px;'>{reasons_html}</td>
                    </tr>
                    <tr>
                        <th style='border: 1px solid #eee; padding: 8px; text-align: left; background: #fafafa;'>Payer Requirements Matched</th>
                        <td style='border: 1px solid #eee; padding: 8px;'>{requirements_html}</td>
                    </tr>
                    <tr>
                        <th style='border: 1px solid #eee; padding: 8px; text-align: left; background: #fafafa;'>Evidence Extracts</th>
                        <td style='border: 1px solid #eee; padding: 8px;'>{evidence_html}</td>
                    </tr>
                    <tr>
                        <th style='border: 1px solid #eee; padding: 8px; text-align: left; background: #fafafa;'>Suggestions</th>
                        <td style='border: 1px solid #eee; padding: 8px;'>{suggestions_html}</td>
                    </tr>
                </tbody>
            </table>
            """
            
            st.markdown(table_html, unsafe_allow_html=True)
        
        st.markdown("---")


def generate_html_fallback(result):
    """Generate HTML fallback report when payer results fail."""
    st.markdown("### 📄 HTML Report Generated")
    
    # Create a simple HTML report
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Multi-Payer CDI Analysis Report</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; }}
            .header {{ background: #f0f0f0; padding: 20px; border-radius: 5px; }}
            .section {{ margin: 20px 0; }}
            .procedure {{ border: 1px solid #ddd; padding: 15px; margin: 10px 0; border-radius: 5px; }}
            .sufficient {{ color: green; font-weight: bold; }}
            .insufficient {{ color: red; font-weight: bold; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🏥 Multi-Payer CDI Analysis Report</h1>
            <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} • 
            <p>Chart ID: {os.path.basename(result.file_name).split('.')[0]} • 
            <p>Total Cost: ${result.total_cost:.6f}
        </div>
        
        <div class="section">
            <h2>📋 Payer Results</h2>
            <p>Note: Detailed payer analysis is not available in the current data format.</p>
            <p>This is a fallback HTML report generated due to data structure issues.</p>
        </div>
        
        <div class="section">
            <h2>📊 Summary</h2>
            <p>Total Cost: ${result.total_cost:.6f}</p>
            <p>Procedures Detected: {len(result.extraction_data.get('procedure', [])) if result.extraction_data else 0}</p>
        </div>
    </body>
    </html>
    """
    
    # Save HTML file
    html_filename = f"cdi_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    html_path = os.path.join("outputs", html_filename)
    
    os.makedirs("outputs", exist_ok=True)
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    st.success(f"HTML report generated: {html_path}")
    
    # Provide download link
    with open(html_path, 'r', encoding='utf-8') as f:
        html_data = f.read()
    
    st.download_button(
        label="📥 Download HTML Report",
        data=html_data,
        file_name=html_filename,
        mime="text/html"
    )


def get_procedure_display_name(proc_result):
    """Get the best display name for a procedure result."""
    if isinstance(proc_result, dict):
        # Prefer original procedure name, fall back to procedure_evaluated
        original = proc_result.get('_original_procedure_name', '')
        evaluated = proc_result.get('procedure_evaluated', '')
        return original if original else evaluated
    else:
        original = getattr(proc_result, '_original_procedure_name', '')
        evaluated = getattr(proc_result, 'procedure_evaluated', '')
        return original if original else evaluated


def populate_chart_with_user_inputs(chart_text, user_input_required, user_inputs):
    """
    Replace [NEEDS PHYSICIAN INPUT: ...] markers in the chart with actual user input.
    
    Args:
        chart_text: The improved chart text with markers
        user_input_required: List of fields requiring input
        user_inputs: Dictionary of user-provided values
        
    Returns:
        Chart text with user inputs populated
    """
    import re
    populated_chart = chart_text
    
    print(f"[DEBUG] populate_chart_with_user_inputs called")
    print(f"[DEBUG] Chart length: {len(chart_text)}")
    print(f"[DEBUG] User inputs: {list(user_inputs.keys())}")
    print(f"[DEBUG] Fields required: {len(user_input_required)}")
    
    # Find all markers in the chart
    marker_pattern = re.compile(r'\[NEEDS PHYSICIAN INPUT:[^\]]+\]')
    all_markers = marker_pattern.findall(populated_chart)
    print(f"[DEBUG] Found {len(all_markers)} markers in chart")
    for i, marker in enumerate(all_markers):
        print(f"[DEBUG] Marker {i+1}: {marker}")
    
    # Create a mapping of field info to user input
    for idx, field in enumerate(user_input_required, 1):
        field_key = f"input_{idx}"
        
        if field_key not in user_inputs or not user_inputs[field_key]:
            print(f"[DEBUG] Field {field_key} not found or empty")
            continue
            
        section = field.get("section", "")
        field_name = field.get("field", "")
        suggestion = field.get("suggestion", "")
        user_value = user_inputs[field_key]
        
        print(f"[DEBUG] Processing field {idx}: {field_name}")
        print(f"[DEBUG] Section: {section}")
        print(f"[DEBUG] User value length: {len(user_value)}")
        
        # Strategy 1: Try to match by section AND field name
        if section and field_name:
            # Look for section heading followed by [NEEDS PHYSICIAN INPUT: ...] containing field name
            pattern = re.compile(
                rf'({re.escape(section)}[^\[]*)\[NEEDS PHYSICIAN INPUT:[^\]]*?{re.escape(field_name)}[^\]]*?\]',
                re.IGNORECASE | re.DOTALL
            )
            match = pattern.search(populated_chart)
            if match:
                # Replace the marker with user value, preserving the section heading
                replacement = match.group(1) + user_value
                populated_chart = populated_chart[:match.start()] + replacement + populated_chart[match.end():]
                continue
        
        # Strategy 2: Try to match by suggestion text (more specific)
        if suggestion:
            # Extract first few words from suggestion for matching
            suggestion_keywords = ' '.join(suggestion.split()[:5])
            pattern = re.compile(
                rf'\[NEEDS PHYSICIAN INPUT:[^\]]*?{re.escape(suggestion_keywords)}[^\]]*?\]',
                re.IGNORECASE
            )
            if pattern.search(populated_chart):
                populated_chart = pattern.sub(user_value, populated_chart, count=1)
                continue
        
        # Strategy 3: Try to match by field name anywhere
        if field_name:
            pattern = re.compile(
                rf'\[NEEDS PHYSICIAN INPUT:[^\]]*?{re.escape(field_name)}[^\]]*?\]',
                re.IGNORECASE
            )
            if pattern.search(populated_chart):
                populated_chart = pattern.sub(user_value, populated_chart, count=1)
                continue
        
        # Strategy 4: If section is known, replace first [NEEDS PHYSICIAN INPUT: ...] in that section
        if section:
            # Find the section in the text
            section_match = re.search(rf'{re.escape(section)}.*?$', populated_chart, re.MULTILINE | re.IGNORECASE)
            if section_match:
                # Look for next [NEEDS PHYSICIAN INPUT: ...] after this section
                after_section = populated_chart[section_match.start():]
                marker_pattern = re.compile(r'\[NEEDS PHYSICIAN INPUT:[^\]]+\]')
                marker_match = marker_pattern.search(after_section)
                if marker_match:
                    # Calculate position in original text
                    marker_pos = section_match.start() + marker_match.start()
                    marker_end = section_match.start() + marker_match.end()
                    populated_chart = populated_chart[:marker_pos] + user_value + populated_chart[marker_end:]
                    continue
    
    # Strategy 5: Last resort - sequential replacement
    # Replace markers in document order with user inputs in field order
    # This handles cases where marker text doesn't match field metadata
    marker_pattern = re.compile(r'\[NEEDS PHYSICIAN INPUT:[^\]]+\]')
    
    for idx, field in enumerate(user_input_required, 1):
        field_key = f"input_{idx}"
        if field_key in user_inputs and user_inputs[field_key]:
            user_value = user_inputs[field_key]
            print(f"[DEBUG] Sequential replacement for field {field_key}")
            # Only replace if value not already in chart
            if user_value not in populated_chart:
                # Find first remaining marker and replace it
                match = marker_pattern.search(populated_chart)
                if match:
                    print(f"[DEBUG] Found marker to replace: {match.group()}")
                    populated_chart = populated_chart[:match.start()] + user_value + populated_chart[match.end():]
                    print(f"[DEBUG] Successfully replaced marker")
                else:
                    print(f"[DEBUG] No more markers found to replace")
        else:
            print(f"[DEBUG] User value already in chart, skipping")
    
    print(f"[DEBUG] Final chart length: {len(populated_chart)}")
    return populated_chart


def remove_line_numbers(text):
    """
    Remove line numbers from text.
    Handles formats like 'L001|content' or '   1|content'
    
    Args:
        text: Text potentially containing line numbers
        
    Returns:
        Text without line numbers
    """
    import re
    lines = text.split('\n')
    cleaned_lines = []
    
    for line in lines:
        # Remove line number prefixes like "L001|" or "   1|" or "L001:"
        cleaned_line = re.sub(r'^\s*L?\d+[|:]?\s*', '', line)
        cleaned_lines.append(cleaned_line)
    
    return '\n'.join(cleaned_lines)


def add_line_numbers(text):
    """
    Add line numbers to text in format L001:, L002:, etc.
    
    Args:
        text: Input text
        
    Returns:
        Text with line numbers prefixed
    """
    lines = text.split('\n')
    numbered_lines = []
    for i, line in enumerate(lines, 1):
        numbered_lines.append(f"L{i:03d}: {line}")
    return '\n'.join(numbered_lines)


def display_improved_medical_chart(original_chart, improved_data):
    """Display improved medical chart with editable fields and recommendations."""
    st.markdown("### 📝 Improved Medical Chart")
    
    if not improved_data or not improved_data.get("success", False):
        error_msg = improved_data.get("error", "Unknown error") if improved_data else "No data available"
        st.error(f"❌ Chart improvement failed: {error_msg}")
        return
    
    improved_chart = improved_data.get("improved_chart", "")
    improvements = improved_data.get("improvements", [])
    user_input_required = improved_data.get("user_input_required", [])
    recommendations = improved_data.get("recommendations", [])
    compliance_impact = improved_data.get("compliance_impact", {})
    cost = improved_data.get("cost", 0.0)
    
    # Show cost and token usage
    col1, col2, col3 = st.columns(3)
    with col1:
        input_tokens = improved_data.get("usage", {}).get("input_tokens", 0)
        st.metric("Input Tokens", f"{input_tokens:,}")
    with col2:
        output_tokens = improved_data.get("usage", {}).get("output_tokens", 0)
        st.metric("Output Tokens", f"{output_tokens:,}")
    with col3:
        st.metric("Improvement Cost", f"${cost:.6f}")
    
    st.markdown("---")
    
    # Compliance Impact Summary
    if compliance_impact:
        st.markdown("### 📊 Compliance Impact")
        
        before_text = compliance_impact.get("before", "N/A")
        after_text = compliance_impact.get("after", "N/A")
        
        # Split long text into bullet points if it contains periods
        def format_as_points(text):
            if not text or text == "N/A":
                return ["N/A"]
            # Split by periods and filter out empty strings
            points = [p.strip() for p in text.split('.') if p.strip()]
            # If it's already well-formatted or single sentence, return as-is
            if len(points) <= 1:
                return [text]
            return points
        
        before_points = format_as_points(before_text)
        after_points = format_as_points(after_text)
        
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**📋 Before Improvement:**")
            st.markdown('<div style="background-color: #FFF3CD; padding: 15px; border-radius: 5px; border-left: 4px solid #FFC107;">', unsafe_allow_html=True)
            for point in before_points:
                st.markdown(f"• {point}")
            st.markdown('</div>', unsafe_allow_html=True)
        
        with col2:
            st.markdown("**✅ After Improvement:**")
            st.markdown('<div style="background-color: #D4EDDA; padding: 15px; border-radius: 5px; border-left: 4px solid #28A745;">', unsafe_allow_html=True)
            for point in after_points:
                st.markdown(f"• {point}")
            st.markdown('</div>', unsafe_allow_html=True)
        
        key_changes = compliance_impact.get("key_changes", [])
        if key_changes:
            st.markdown("---")
            st.markdown("**🔑 Key Changes:**")
            st.markdown('<div style="background-color: #E7F3FF; padding: 15px; border-radius: 5px; border-left: 4px solid #0066CC;">', unsafe_allow_html=True)
            for change in key_changes:
                st.markdown(f"✓ {change}")
            st.markdown('</div>', unsafe_allow_html=True)
        
        st.markdown("---")
    
    # Remove line numbers from improved chart before processing
    import re
    clean_improved_chart = remove_line_numbers(improved_chart)
    clean_improved_chart = re.sub(r'^L\d+\|', '', clean_improved_chart, flags=re.MULTILINE)
    
    # Populate chart with user inputs
    populated_chart = populate_chart_with_user_inputs(
        clean_improved_chart, 
        user_input_required, 
        st.session_state.user_input_fields
    )
    
    # Update populated chart with latest inputs
    populated_chart = populate_chart_with_user_inputs(
        clean_improved_chart, 
        user_input_required, 
        st.session_state.user_input_fields
    )
    
    # ===== SEQUENTIAL LAYOUT - All sections scrollable =====
    
    # 1. List of AI Improvements Made
    st.markdown("---")
    st.markdown("## ✨ AI Improvements Made")
    
    if improvements:
        # Group improvements by section
        improvements_by_section = {}
        for imp in improvements:
            section = imp.get("section", "General")
            if section not in improvements_by_section:
                improvements_by_section[section] = []
            improvements_by_section[section].append(imp)
        
        # Display as a clean list
        for section, section_improvements in improvements_by_section.items():
            st.markdown(f"**• {section}** ({len(section_improvements)} improvement{'s' if len(section_improvements) > 1 else ''})")
        
        st.success(f"✅ {len(improvements)} total improvement(s) were made by AI to your medical chart.")
    else:
        st.info("No specific improvements were made to the structure or clarity.")
    
    # 3. After Improvement Chart with Placeholders (Editable)
    st.markdown("---")
    st.markdown("## 📄 Improved Medical Chart")
    
    # Check if there are still unfilled inputs
    unfilled_count = sum(1 for field in user_input_required 
                        if f"input_{user_input_required.index(field) + 1}" not in st.session_state.user_input_fields 
                        or not st.session_state.user_input_fields.get(f"input_{user_input_required.index(field) + 1}"))
    
    if unfilled_count > 0:
        st.info(f"🔍 **Note:** {unfilled_count} field(s) still need input above. They are marked as [NEEDS PHYSICIAN INPUT: ...]")
    else:
        st.success("✅ All required fields have been filled with your input!")
    
    # Create highlighted version with purple for [ADDED:] and light red for [NEEDS PHYSICIAN INPUT:]
    import html
    
    # Keep the chart as-is with markers for highlighting (non-editable display)
    # Add line numbers to the display chart for reference
    display_chart = add_line_numbers(populated_chart)
    
    # Create highlighted version for non-editable display
    def highlight_added(match):
        content = match.group(1)
        return f'<span style="background-color: #E6D5F5; color: #6B46C1; padding: 2px 4px; border-radius: 3px; font-weight: bold;">{html.escape(content)}</span>'
    
    def highlight_physician_input(match):
        content = match.group(1)
        return f'<span style="background-color: #FFE6E6; color: #C53030; padding: 2px 4px; border-radius: 3px; font-weight: bold;">{html.escape(content)}</span>'
    
    display_chart_html = html.escape(display_chart)
    display_chart_html = re.sub(r'\[ADDED:\s*([^\]]+)\]', highlight_added, display_chart_html)
    display_chart_html = re.sub(r'\[NEEDS PHYSICIAN INPUT:\s*([^\]]+)\]', highlight_physician_input, display_chart_html)
    display_chart_html = display_chart_html.replace('\n', '<br>')
    
    # Display chart with highlights
    st.info("📋 **View Only:** Purple highlights = AI additions, Light Red highlights = Fields needing physician input")
    st.markdown(
        f'<div style="background-color: #f8f9fa; padding: 20px; border-radius: 5px; border: 1px solid #dee2e6; max-height: 600px; overflow-y: auto; font-family: monospace; white-space: pre-wrap; font-size: 13px;">{display_chart_html}</div>',
        unsafe_allow_html=True
    )
    
    # Editable version with more visible placeholders
    st.markdown("---")
    st.markdown("#### ✏️ Editable Chart:")
    
    # Create editable version with more visible placeholders
    # Add line numbers to editable version
    editable_chart = add_line_numbers(populated_chart)
    
    # Make placeholders more visible by adding warning markers
    editable_chart_with_placeholders = re.sub(
        r'\[NEEDS PHYSICIAN INPUT:\s*([^\]]+)\]',
        r'[⚠️ PHYSICIAN INPUT REQUIRED: \1]',
        editable_chart
    )
    
    # Also mark ADDED sections for visibility in editable version
    editable_chart_with_placeholders = re.sub(
        r'\[ADDED:\s*([^\]]+)\]',
        r'[➕ ADDED BY AI: \1]',
        editable_chart_with_placeholders
    )
    
    edited_chart = st.text_area(
        "Make changes to the improved chart below (placeholders marked with ⚠️):",
        editable_chart_with_placeholders,
        height=400,
        help="Edit the improved chart directly. ⚠️ marks areas needing physician input, ➕ marks AI additions.",
        key="improved_chart_editor"
    )
    
    # Store edited chart for download
    final_chart = edited_chart
    
    # 5. Comparison Section
    st.markdown("---")
    st.markdown("## 🔄 Comparison: Original vs Improved")
    
    # Remove line numbers for cleaner comparison
    original_clean = remove_line_numbers(original_chart)
    # Remove line numbers and all ADDED markers from comparison version
    populated_clean = remove_line_numbers(final_chart)
    
    # Remove all ADDED markers from comparison (keep content, remove markers)
    populated_clean = re.sub(r'\[ADDED:\s*([^\]]+)\]', r'\1', populated_clean)
    populated_clean = re.sub(r'\[➕ ADDED BY AI:\s*([^\]]+)\]', r'\1', populated_clean)
    # Remove PHYSICIAN INPUT markers (already filled in, so just remove the markers)
    populated_clean = re.sub(r'\[NEEDS PHYSICIAN INPUT:[^\]]+\]', '', populated_clean)
    populated_clean = re.sub(r'\[⚠️ PHYSICIAN INPUT REQUIRED:[^\]]+\]', '', populated_clean)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**Original Chart:**")
        st.text_area(
            "Original",
            original_clean,
            height=500,
            label_visibility="collapsed",
            key="compare_original"
        )
        st.metric("Length", f"{len(original_clean)} characters")
    
    with col2:
        st.markdown("**Improved Chart (with your inputs):**")
        st.text_area(
            "Improved",
            populated_clean,
            height=500,
            label_visibility="collapsed",
            key="compare_improved"
        )
        st.metric("Length", f"{len(populated_clean)} characters")
        
        # Calculate improvement percentage
        if len(populated_clean) > len(original_clean):
            improvement_pct = ((len(populated_clean) - len(original_clean)) / len(original_clean)) * 100
            st.metric("Added Content", f"+{improvement_pct:.1f}%")
    
    # 6. Download Section
    st.markdown("---")
    st.markdown("## 💾 Download Improved Chart")
    
    # Remove line numbers and all markers for clean medical chart format
    chart_no_lines = remove_line_numbers(final_chart)
    chart_no_lines = re.sub(r'^L\d+\|', '', chart_no_lines, flags=re.MULTILINE)
    # Remove all marker types for clean medical chart format
    chart_no_lines = re.sub(r'\[ADDED:\s*([^\]]+)\]', r'\1', chart_no_lines)
    chart_no_lines = re.sub(r'\[➕ ADDED BY AI:\s*([^\]]+)\]', r'\1', chart_no_lines)
    chart_no_lines = re.sub(r'\[NEEDS PHYSICIAN INPUT:[^\]]+\]', '', chart_no_lines)
    chart_no_lines = re.sub(r'\[⚠️ PHYSICIAN INPUT REQUIRED:[^\]]+\]', '', chart_no_lines)
    
    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            label="📥 Download Improved Chart",
            data=chart_no_lines,
            file_name=f"improved_chart_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            mime="text/plain",
            width='stretch'
        )
    with col2:
        # Remove line numbers from original too
        original_no_lines = remove_line_numbers(original_chart)
        original_no_lines = re.sub(r'^L\d+\|', '', original_no_lines, flags=re.MULTILINE)
        st.download_button(
            label="📥 Download Clean Original Chart",
            data=original_no_lines,
            file_name=f"clean_original_chart_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            mime="text/plain",
            width='stretch'
        )


def display_cross_payer_dashboard(result):
    """Display comprehensive cross-payer analysis dashboard."""
    extraction_data = result.extraction_data
    payer_results = result.payer_results
    total_cost = result.total_cost
    
    # Header with metadata
    st.markdown("## 🏥 Multi-Payer CDI Analysis Report")
    
    # Metadata row
    st.markdown(
        f"<div style='color: #666; font-size: 0.9rem; margin-bottom: 16px;'>"
        f"Generated: {datetime.now().strftime('%Y-%m-%dT%H:%M:%S')} • "
        f"Chart ID: {os.path.basename(result.file_name).split('.')[0]} • "
        f"Total Cost: ${total_cost:.6f}"
        f"</div>",
        unsafe_allow_html=True
    )
    
    # Dashboard note
    st.info("📊 **Dashboard Focus:** This dashboard shows Sufficient/Insufficient decisions only. When payer-specific guidelines are not available, the system uses general medical necessity guidelines to provide a decision.")
    
    st.markdown("---")
    
    # Extract procedures
    procedures = extraction_data.get("procedure", []) if extraction_data else []
    cpt_codes = extraction_data.get("cpt", []) if extraction_data else []
    
    # Summary metrics
    st.markdown("### 📊 Summary Metrics")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Procedures Detected", len(procedures))
    
    with col2:
        total_analyses = sum(len(pr.procedure_results) for pr in payer_results.values() if hasattr(pr, 'procedure_results'))
        st.metric("Total Analyses", total_analyses)
    
    with col3:
        # Calculate average sufficiency - only count Sufficient/Insufficient decisions
        all_decisions = []
        for pr in payer_results.values():
            if hasattr(pr, 'procedure_results'):
                for proc_result in pr.procedure_results:
                    decision = proc_result.get('decision', '')
                    # Only count Sufficient/Insufficient, skip "Not Applicable" or "No Guidelines"
                    if 'sufficient' in decision.lower() and 'insufficient' not in decision.lower():
                        all_decisions.append(1)
                    elif 'insufficient' in decision.lower():
                        all_decisions.append(0)
        
        avg_sufficiency = (sum(all_decisions) / len(all_decisions) * 100) if all_decisions else 0
        st.metric("Avg. Sufficiency", f"{avg_sufficiency:.1f}%")
    
    with col4:
        st.metric("Total Cost", f"${total_cost:.3f}")
    
    st.markdown("---")
    
    # Cross-Payer Consensus Analysis - MOVED TO TOP
    st.markdown("### 🔄 Cross-Payer Consensus Analysis 🔗")
    
    # Build consensus data per procedure
    consensus_data = {}
    payer_summary = {}  # For payer-wise comparison table
    
    for proc in procedures:
        consensus_data[proc] = {
            'decisions': {},
            'conflicts': [],
            'all_sufficient': True,
            'all_insufficient': True,
            'payer_costs': {}
        }
        
        for payer_key, payer_result in payer_results.items():
            if isinstance(payer_result, dict):
                payer_name = payer_result.get('payer_name', payer_key)
                procedure_results = payer_result.get('procedure_results', [])
                usage = payer_result.get('usage', {})
                if isinstance(usage, dict):
                    payer_cost = usage.get('cost', 0)
                else:
                    payer_cost = getattr(usage, 'cost', 0) if usage else 0
            else:
                if not hasattr(payer_result, 'payer_name'):
                    continue
                payer_name = payer_result.payer_name
                procedure_results = getattr(payer_result, 'procedure_results', [])
                if hasattr(payer_result, 'usage') and payer_result.usage:
                    payer_cost = getattr(payer_result.usage, 'cost', 0)
                else:
                    payer_cost = 0
            
            # Initialize payer summary if not exists
            if payer_name not in payer_summary:
                payer_summary[payer_name] = {
                    'sufficient': 0,
                    'insufficient': 0,
                    'total_cost': 0
                }
            
            # Find matching procedure result
            for proc_result in procedure_results:
                if isinstance(proc_result, dict):
                    # Use original procedure name for matching if available
                    original_proc_name = proc_result.get('_original_procedure_name', '')
                    proc_name = proc_result.get('procedure_evaluated', '')
                    decision = proc_result.get('decision', 'Unknown')
                else:
                    original_proc_name = getattr(proc_result, '_original_procedure_name', '')
                    proc_name = getattr(proc_result, 'procedure_evaluated', '')
                    decision = getattr(proc_result, 'decision', 'Unknown')
                
                # Use original procedure name for matching if available, otherwise use procedure_evaluated
                match_name = original_proc_name if original_proc_name else proc_name
                
                # Improved matching logic: extract key terms from both procedure names
                proc_lower = proc.lower()
                match_name_lower = match_name.lower()
                
                # Extract key medical terms (ignore common words like "right", "left", etc.)
                def extract_key_terms(text):
                    common_words = ['right', 'left', 'bilateral', 'shoulder', 'knee', 'hip', 'elbow', 'ankle', 'wrist']
                    words = text.lower().split()
                    # Keep procedure-specific terms
                    key_terms = [w for w in words if len(w) > 4 and w not in common_words]
                    return set(key_terms)
                
                # Check if they share significant key terms or one contains the other
                exact_match = proc_lower == match_name_lower
                substring_match = match_name_lower in proc_lower or proc_lower in match_name_lower
                key_terms_extracted = extract_key_terms(proc)
                key_terms_evaluated = extract_key_terms(match_name)
                key_terms_overlap = len(key_terms_extracted & key_terms_evaluated) > 0
                
                if exact_match or (substring_match and len(match_name.split()) > 1) or (key_terms_overlap and len(key_terms_extracted & key_terms_evaluated) >= 2):
                    # Always add to consensus (system uses general guidelines as fallback)
                    consensus_data[proc]['decisions'][payer_name] = decision
                    consensus_data[proc]['payer_costs'][payer_name] = payer_cost
                    
                    # Update payer summary - only count Sufficient/Insufficient decisions
                    # Skip "Not Applicable" or "No Guidelines" as system uses general guidelines fallback
                    if 'sufficient' in decision.lower() and 'insufficient' not in decision.lower():
                        payer_summary[payer_name]['sufficient'] += 1
                        consensus_data[proc]['all_insufficient'] = False
                    elif 'insufficient' in decision.lower():
                        payer_summary[payer_name]['insufficient'] += 1
                        consensus_data[proc]['all_sufficient'] = False
                    # Decisions without payer-specific guidelines use general guidelines
                    # and will result in either Sufficient or Insufficient
                    
                    payer_summary[payer_name]['total_cost'] += payer_cost
                    break
    
    # Detect conflicts
    for proc, data in consensus_data.items():
        decisions_list = list(data['decisions'].values())
        if len(set([d.lower() for d in decisions_list])) > 1:
            # There are conflicts
            payer_names = list(data['decisions'].keys())
            for i in range(len(payer_names)):
                for j in range(i+1, len(payer_names)):
                    if data['decisions'][payer_names[i]].lower() != data['decisions'][payer_names[j]].lower():
                        data['conflicts'].append(
                            f"{payer_names[i]} vs {payer_names[j]}: {data['decisions'][payer_names[i]]} vs {data['decisions'][payer_names[j]]}"
                        )
    
    # Display consensus table
    if consensus_data:
        st.markdown("#### 📊 Consensus by Procedure")
        
        # Build table data
        table_data = []
        for proc_num, (proc, data) in enumerate(consensus_data.items(), 1):
            # Count payers for this procedure
            payer_count = len(data['decisions'])
            
            # Skip if no decisions recorded
            if payer_count == 0:
                continue
            
            # Agreement level
            if data['all_sufficient']:
                agreement = f"✅ Full Agreement - All Sufficient ({payer_count} payers)"
                agreement_color = "#ecfdf5"
            elif data['all_insufficient']:
                agreement = f"❌ Full Agreement - All Insufficient ({payer_count} payers)"
                agreement_color = "#fff7ed"
            else:
                agreement = f"⚠️ Partial Agreement - Mixed ({payer_count} payers)"
                agreement_color = "#f1f5f9"
            
            # Payer Decisions - format as list with emojis
            decisions_list = []
            for payer_name, decision in data['decisions'].items():
                # Since we use general guidelines as fallback, we only show Sufficient/Insufficient
                if 'sufficient' in decision.lower() and 'insufficient' not in decision.lower():
                    display_decision = decision
                    emoji = "✅"
                elif 'insufficient' in decision.lower():
                    display_decision = decision
                    emoji = "❌"
                else:
                    # Handle any remaining cases - should be Sufficient or Insufficient
                    display_decision = decision
                    emoji = "✅" if 'sufficient' in decision.lower() else "❌"
                decisions_list.append(f"{emoji} {payer_name}: {display_decision}")
            decisions_text = "<br>".join(decisions_list)
            
            # Conflicts - Only show real conflicts between Sufficient/Insufficient
            if data['conflicts']:
                conflicts_list = []
                for conflict in data['conflicts']:
                    # Only include real conflicts (Sufficient vs Insufficient)
                    # Skip conflicts involving "No Guidelines" since we have fallback
                    if 'not applicable' in conflict.lower() or 'no guidelines' in conflict.lower():
                        continue
                    conflicts_list.append(f"⚠️ {conflict}")
                conflicts_text = "<br>".join(conflicts_list) if conflicts_list else "✅ No conflicts"
            else:
                conflicts_text = "✅ No conflicts"
            
            # Recommendation
            if data['all_sufficient']:
                recommendation = "✅ Documentation meets all payer requirements. Proceed with confidence."
            elif data['all_insufficient']:
                recommendation = "❌ Documentation insufficient across all payers. Address all identified gaps before submission."
            else:
                recommendation = "⚠️ Mixed results. Review payer-specific requirements and resolve conflicts to maximize approval."
            
            table_data.append({
                'procedure': f"{proc_num}. {proc}",
                'agreement': agreement,
                'decisions': decisions_text,
                'conflicts': conflicts_text,
                'recommendation': recommendation
            })
        
        # Display as single HTML table
        if table_data:
            # Build HTML as a single string
            table_html = '<style>.consensus-table { width: 100%; border-collapse: collapse; margin-bottom: 20px; font-size: 14px; } .consensus-table th { background: #f8fafc; border: 1px solid #e2e8f0; padding: 12px; text-align: left; font-weight: 600; color: #334155; } .consensus-table td { border: 1px solid #e2e8f0; padding: 12px; vertical-align: top; } .consensus-table tr:hover { background-color: #f8fafc; } .procedure-col { width: 20%; font-weight: 500; } .agreement-col { width: 15%; } .decisions-col { width: 25%; } .conflicts-col { width: 20%; font-size: 13px; } .recommendation-col { width: 20%; }</style>'
            
            table_html += '<table class="consensus-table"><thead><tr><th class="procedure-col">Procedure</th><th class="agreement-col">Agreement Level</th><th class="decisions-col">Payer Decisions</th><th class="conflicts-col">Conflicts</th><th class="recommendation-col">Consensus Recommendation</th></tr></thead><tbody>'
            
            for row in table_data:
                table_html += f'<tr><td class="procedure-col"><strong>{row["procedure"]}</strong></td><td class="agreement-col">{row["agreement"]}</td><td class="decisions-col">{row["decisions"]}</td><td class="conflicts-col">{row["conflicts"]}</td><td class="recommendation-col">{row["recommendation"]}</td></tr>'
            
            table_html += '</tbody></table>'
            
            st.markdown(table_html, unsafe_allow_html=True)
        
        # Add consensus summary statistics
        if consensus_data:
            st.markdown("#### 📈 Consensus Summary")
            
            # Calculate summary stats
            total_procedures_analyzed = len(consensus_data)
            full_agreement_count = sum(1 for data in consensus_data.values() if data['all_sufficient'] or data['all_insufficient'])
            partial_agreement_count = total_procedures_analyzed - full_agreement_count
            total_conflicts = sum(len(data['conflicts']) for data in consensus_data.values())
            
            # Display stats in columns
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Procedures Analyzed", total_procedures_analyzed)
            
            with col2:
                st.metric("Full Agreement", full_agreement_count)
            
            with col3:
                st.metric("Partial Agreement", partial_agreement_count)
            
            with col4:
                st.metric("Total Conflicts", total_conflicts)
    
    # Payer-wise Comparison Table
    if payer_summary:
        st.markdown("#### Payer-wise Comparison")
        
        # Create comparison table data
        comparison_data = []
        for payer_name, stats in payer_summary.items():
            comparison_data.append({
                'Payer': payer_name,
                'Sufficient': stats['sufficient'],
                'Insufficient': stats['insufficient'],
                'Total Cost': f"${stats['total_cost']:.6f}"
            })
        
        # Display as Streamlit native table
        import pandas as pd
        df = pd.DataFrame(comparison_data)
        
        # Style the dataframe
        def highlight_sufficient(val):
            if isinstance(val, (int, float)) and val > 0:
                return 'background-color: #ecfdf5; color: #065f46; font-weight: bold;'
            return ''
        
        def highlight_insufficient(val):
            if isinstance(val, (int, float)) and val > 0:
                return 'background-color: #fff7ed; color: #7c2d12; font-weight: bold;'
            return ''
        
        
        def highlight_cost(val):
            if isinstance(val, str) and '$' in val:
                return 'font-weight: bold;'
            return ''
        
        # Apply styling
        styled_df = df.style.applymap(highlight_sufficient, subset=['Sufficient'])\
                           .applymap(highlight_insufficient, subset=['Insufficient'])\
                           .applymap(highlight_cost, subset=['Total Cost'])
        
        st.dataframe(
            styled_df,
            width='stretch',
            hide_index=True,
            column_config={
                "Payer": st.column_config.TextColumn("Payer", width="medium"),
                "Sufficient": st.column_config.NumberColumn("Sufficient", width="small"),
                "Insufficient": st.column_config.NumberColumn("Insufficient", width="small"),
                "Total Cost": st.column_config.TextColumn("Total Cost", width="small")
            }
        )
    
    st.markdown("---")
    
    # Common Documentation Gaps & Actionable Recommendations
    st.markdown("### 📝 Common Documentation Gaps")
    
    # Extract common gaps from all sources
    all_gaps = set()
    
    # Get gaps from payer results
    for payer_key, payer_result in payer_results.items():
        if isinstance(payer_result, dict):
            procedure_results = payer_result.get('procedure_results', [])
        else:
            procedure_results = getattr(payer_result, 'procedure_results', [])
        
        for proc_result in procedure_results:
            if isinstance(proc_result, dict):
                reasons = proc_result.get('primary_reasons', [])
                req_checklist = proc_result.get('requirement_checklist', [])
            else:
                reasons = getattr(proc_result, 'primary_reasons', [])
                req_checklist = getattr(proc_result, 'requirement_checklist', [])
            
            # Extract gaps from reasons
            for reason in reasons:
                if any(keyword in reason.lower() for keyword in ['missing', 'absent', 'not found', 'lacks', 'incomplete', 'no ', 'not ']):
                    all_gaps.add(reason)
            
            # Extract gaps from unmet requirements
            for req in req_checklist:
                if isinstance(req, dict):
                    status = req.get('status', '')
                    gap_text = req.get('missing_to_meet', '')
                else:
                    status = getattr(req, 'status', '')
                    gap_text = getattr(req, 'missing_to_meet', '')
                
                if status == 'unmet' and gap_text:
                    all_gaps.add(gap_text)
    
    # Display gaps as bullets
    if all_gaps:
        gap_html = "<ul style='margin-top: 8px;'>"
        for gap in sorted(all_gaps)[:10]:  # Top 10
            gap_html += f"<li>{gap}</li>"
        gap_html += "</ul>"
        st.markdown(gap_html, unsafe_allow_html=True)
    else:
        st.success("✅ No common documentation gaps identified across payers!")
    
    st.markdown("")
    
    # Actionable Recommendations
    st.markdown("### ✅ Actionable Recommendations")
    
    # Extract recommendations from all sources
    all_recommendations = set()
    
    # Get recommendations from payer results
    for payer_key, payer_result in payer_results.items():
        if isinstance(payer_result, dict):
            procedure_results = payer_result.get('procedure_results', [])
        else:
            procedure_results = getattr(payer_result, 'procedure_results', [])
        
        for proc_result in procedure_results:
            if isinstance(proc_result, dict):
                improvement = proc_result.get('improvement_recommendations', {})
                actions = improvement.get('compliance_actions', []) if improvement else []
            else:
                improvement = getattr(proc_result, 'improvement_recommendations', {})
                actions = improvement.get('compliance_actions', []) if improvement else []
            
            for action in actions:
                if action and action.strip():
                    all_recommendations.add(action.strip())
    
    if all_recommendations:
        rec_html = "<ol style='margin-top: 8px;'>"
        for rec in sorted(all_recommendations)[:10]:  # Top 10
            rec_html += f"<li>{rec}</li>"
        rec_html += "</ol>"
        st.markdown(rec_html, unsafe_allow_html=True)
    else:
        st.info("No specific recommendations available")
    
    st.markdown("---")
    
    # Missing Documentation Checklist
    st.markdown("### 📋 Missing Documentation (Aggregated)")
    
    checklist_items = {
        "🏥 Imaging": [],
        "🏃‍♂️ Conservative Treatment": [],
        "📊 Clinical Assessments": [],
        "🧠 Functional Limitations": []
    }
    
    for payer_key, payer_result in payer_results.items():
        if not hasattr(payer_result, 'procedure_results'):
            continue
        
        for proc_result in payer_result.procedure_results:
            gaps = proc_result.get('improvement_recommendations', {}).get('documentation_gaps', [])
            for gap in gaps:
                gap_lower = gap.lower()
                if 'mri' in gap_lower or 'imaging' in gap_lower or 'xray' in gap_lower or 'ct' in gap_lower or 'radiology' in gap_lower:
                    checklist_items["🏥 Imaging"].append(gap)
                elif 'pt' in gap_lower or 'therapy' in gap_lower or 'conservative' in gap_lower or 'treatment' in gap_lower:
                    checklist_items["🏃‍♂️ Conservative Treatment"].append(gap)
                elif 'rom' in gap_lower or 'strength' in gap_lower or 'exam' in gap_lower or 'assessment' in gap_lower:
                    checklist_items["📊 Clinical Assessments"].append(gap)
                elif 'score' in gap_lower or 'functional' in gap_lower or 'ases' in gap_lower or 'vas' in gap_lower or 'limitation' in gap_lower:
                    checklist_items["🧠 Functional Limitations"].append(gap)
    
    # Display in 2-column grid
    col1, col2 = st.columns(2)
    
    categories = list(checklist_items.items())
    
    with col1:
        for category, items in categories[:2]:  # First 2 categories
            if items:
                st.markdown(f"**{category}**")
                unique_items = list(set(items))[:3]  # Top 3 unique items
                checklist_html = "<ul style='font-family: monospace; font-size: 0.9rem;'>"
                for item in unique_items:
                    checklist_html += f"<li>[ ] {item}</li>"
                checklist_html += "</ul>"
                st.markdown(checklist_html, unsafe_allow_html=True)
    
    with col2:
        for category, items in categories[2:]:  # Last 2 categories
            if items:
                st.markdown(f"**{category}**")
                unique_items = list(set(items))[:3]  # Top 3 unique items
                checklist_html = "<ul style='font-family: monospace; font-size: 0.9rem;'>"
                for item in unique_items:
                    checklist_html += f"<li>[ ] {item}</li>"
                checklist_html += "</ul>"
                st.markdown(checklist_html, unsafe_allow_html=True)
    
    # Completion Guidance
    st.markdown("#### ✍️ Completion Guidance")
    guidance_items = [
        "Summarize conservative measures with dates and documented outcomes",
        "Include specific functional scores (ASES, Constant, VAS) with dates",
        "Attach all relevant imaging reports with radiologist interpretations",
        "Document clinical findings with objective measurements (ROM, strength)"
    ]
    
    guidance_html = "<ul style='margin-top: 8px;'>"
    for item in guidance_items:
        guidance_html += f"<li>{item}</li>"
    guidance_html += "</ul>"
    st.markdown(guidance_html, unsafe_allow_html=True)
    
    st.markdown("---")
    
    # Coding Implications
    st.markdown("### 💼 Coding Implications")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### CPT")
        
        # Build CPT table using Streamlit's native table
        if cpt_codes:
            cpt_data = []
            for idx, cpt in enumerate(cpt_codes):
                # Try to get laterality from procedures
                modifier = ""
                if idx < len(procedures):
                    proc_lower = procedures[idx].lower()
                    if "right" in proc_lower:
                        modifier = "RT"
                    elif "left" in proc_lower:
                        modifier = "LT"
                
                rationale = procedures[idx] if idx < len(procedures) else "Procedure from extraction"
                
                cpt_data.append({
                    "Code": cpt,
                    "Modifier": modifier if modifier else "-",
                    "Rationale": rationale
                })
            
            if cpt_data:
                import pandas as pd
                df = pd.DataFrame(cpt_data)
                st.dataframe(
                    df,
                    width='stretch',
                    hide_index=True,
                    column_config={
                        "Code": st.column_config.TextColumn("Code", width="small"),
                        "Modifier": st.column_config.TextColumn("Modifier", width="small"),
                        "Rationale": st.column_config.TextColumn("Rationale", width="large")
                    }
                )
        else:
            st.info("No CPT codes detected")
    
    with col2:
        st.markdown("#### ICD-10")
        
        # Extract ICD codes from coding implications
        icd_data = []
        for payer_key, payer_result in payer_results.items():
            if not hasattr(payer_result, 'procedure_results'):
                continue
            
            for proc_result in payer_result.procedure_results:
                coding = proc_result.get('coding_implications', {})
                notes = coding.get('notes', '')
                
                # Try to extract ICD-10 pattern codes (e.g., M75.100, S43.011A)
                import re
                icd_pattern = r'\b[A-Z]\d{2}\.\d{1,3}[A-Z]?\b'
                found_codes = re.findall(icd_pattern, notes)
                
                for code in found_codes[:3]:  # Limit to 3 per payer
                    if code not in [d['code'] for d in icd_data]:
                        # Get context around the code
                        code_context = notes[max(0, notes.find(code)-50):notes.find(code)+100]
                        icd_data.append({
                            'code': code,
                            'rationale': code_context if len(code_context) > 10 else notes[:100]
                        })
        
        # Build ICD table using Streamlit's native table
        if icd_data:
            icd_df_data = []
            for item in icd_data[:5]:  # Top 5
                icd_df_data.append({
                    "Code": item['code'],
                    "Rationale": item['rationale'][:150] + "..." if len(item['rationale']) > 150 else item['rationale']
                })
            
            if icd_df_data:
                import pandas as pd
                icd_df = pd.DataFrame(icd_df_data)
                st.dataframe(
                    icd_df,
                    width='stretch',
                    hide_index=True,
                    column_config={
                        "Code": st.column_config.TextColumn("Code", width="small"),
                        "Rationale": st.column_config.TextColumn("Rationale", width="large")
                    }
                )
            else:
                st.info("Review procedure documentation for appropriate diagnosis codes")
        else:
            st.info("Review procedure documentation for appropriate diagnosis codes")
    
    st.markdown("---")
    
    # Detected Procedures section
    st.markdown("### 🔍 Detected Procedures")
    
    if procedures:
        proc_data = []
        for idx, proc in enumerate(procedures):
            cpt = cpt_codes[idx] if idx < len(cpt_codes) else "N/A"
            proc_data.append({
                "Procedure": proc,
                "CPT": cpt,
                "Source": "Extraction"
            })
        
        import pandas as pd
        df = pd.DataFrame(proc_data)
        st.dataframe(df, width='stretch', hide_index=True)
    else:
        st.info("No procedures detected")
    
    st.markdown("---")
    
    # Individual Payer Results - Detailed Section
    st.markdown("### 📋 Detailed Payer Results")
    
    if not payer_results:
        st.warning("No payer results available")
        # Generate HTML fallback
        generate_html_fallback(result)
        return
    
    # Try to display payer results, if fails, show HTML fallback
    try:
        display_payer_results_simple(payer_results)
    except Exception as e:
        st.error(f"Error displaying payer results: {e}")
        st.info("Generating HTML fallback report...")
        generate_html_fallback(result)
    
    st.markdown("---")
    st.markdown(
        "<div style='text-align: center; color: #666; font-size: 0.9rem;'>"
        "Generated from multi-payer CDI results. This document may contain AI-assisted summaries; "
        "verify against source chart and payer policies before submission."
        "</div>",
        unsafe_allow_html=True
    )


def display_processing_results(result):
    """Display complete processing results."""
    if not result:
        return
    
    file_name = result.file_name
    extraction_data = result.extraction_data
    payer_results = result.payer_results
    total_usage = result.total_usage
    total_cost = result.total_cost
    execution_times = result.execution_times
    numbered_chart = result.numbered_medical_chart
    error = result.error
    
    # Header
    st.markdown('<div class="main-header">📊 Processing Results</div>', unsafe_allow_html=True)
    st.markdown(f"**File:** {os.path.basename(file_name)}")
    
    # Error handling
    if error:
        st.error(f"❌ Processing Error: {error}")
        return
    
    # Patient overview
    if extraction_data:
        patient_name = extraction_data.get("patient_name", "Unknown") or "Unknown"
        patient_age = extraction_data.get("patient_age", "Unknown") or "Unknown"
        chart_specialty = extraction_data.get("chart_specialty", "Unknown") or "Unknown"
        
        st.markdown("### 🧑‍⚕️ Patient Overview")
        overview_col1, overview_col2, overview_col3 = st.columns(3)
        with overview_col1:
            st.metric("Patient Name", patient_name)
        with overview_col2:
            st.metric("Patient Age", patient_age)
        with overview_col3:
            st.metric("Chart Specialty", chart_specialty)
    
    # Payer summary - calculate if not present
    payer_summary = getattr(result, "payer_summary", None)
    
    # Helper function to calculate payer summary
    def calculate_payer_summary_fallback(prs):
        if not prs:
            return {"per_payer": {}, "overall": {"total_procedures": 0, "sufficient_count": 0, "insufficient_count": 0, "other_count": 0, "sufficient_percentage": 0.0, "insufficient_percentage": 0.0, "other_percentage": 0.0}}
        
        per_payer = {}
        overall_total = 0
        overall_sufficient = 0
        overall_insufficient = 0
        overall_other = 0
        
        for payer_key, payer_data in prs.items():
            if isinstance(payer_data, dict):
                payer_name = payer_data.get("payer_name", payer_key)
                procedure_results = payer_data.get("procedure_results", [])
            else:
                payer_name = getattr(payer_data, "payer_name", payer_key)
                procedure_results = getattr(payer_data, "procedure_results", [])
            
            total = len(procedure_results) if procedure_results else 0
            sufficient_count = 0
            insufficient_count = 0
            
            for proc_result in procedure_results or []:
                if isinstance(proc_result, dict):
                    decision = proc_result.get("decision", "")
                else:
                    decision = getattr(proc_result, "decision", "")
                decision_lower = decision.lower() if isinstance(decision, str) else ""
                
                if "insufficient" in decision_lower:
                    insufficient_count += 1
                elif "sufficient" in decision_lower and "insufficient" not in decision_lower:
                    sufficient_count += 1
            
            other_count = max(total - sufficient_count - insufficient_count, 0)
            overall_total += total
            overall_sufficient += sufficient_count
            overall_insufficient += insufficient_count
            overall_other += other_count
            
            per_payer[payer_key] = {
                "payer_key": payer_key,
                "payer_name": payer_name,
                "total_procedures": total,
                "sufficient_count": sufficient_count,
                "insufficient_count": insufficient_count,
                "other_count": other_count,
                "sufficient_percentage": round((sufficient_count / total * 100) if total else 0.0, 2),
                "insufficient_percentage": round((insufficient_count / total * 100) if total else 0.0, 2),
                "other_percentage": round((other_count / total * 100) if total else 0.0, 2)
            }
        
        overall_summary = {
            "total_procedures": overall_total,
            "sufficient_count": overall_sufficient,
            "insufficient_count": overall_insufficient,
            "other_count": overall_other,
            "sufficient_percentage": round((overall_sufficient / overall_total * 100) if overall_total else 0.0, 2),
            "insufficient_percentage": round((overall_insufficient / overall_total * 100) if overall_total else 0.0, 2),
            "other_percentage": round((overall_other / overall_total * 100) if overall_total else 0.0, 2)
        }
        
        return {"per_payer": per_payer, "overall": overall_summary}
    
    # Use existing payer_summary or calculate if missing
    if not payer_summary or not isinstance(payer_summary, dict) or not payer_summary:
        payer_summary = calculate_payer_summary_fallback(payer_results)
    else:
        # Ensure payer_summary has expected structure
        if not payer_summary.get("per_payer"):
            payer_summary["per_payer"] = {}
        if not payer_summary.get("overall"):
            payer_summary["overall"] = {}
    
    per_payer_summary = payer_summary.get("per_payer", {}) if isinstance(payer_summary, dict) else {}
    overall_summary = payer_summary.get("overall", {}) if isinstance(payer_summary, dict) else {}
    
    # Always display payer summary if we have payer results
    if payer_results:
        def _format_pct(value):
            try:
                return f"{float(value):.2f}%"
            except (TypeError, ValueError):
                return "0.00%"
        
        st.markdown("### 📊 Payer Sufficiency Summary")
        overall_col1, overall_col2, overall_col3 = st.columns(3)
        with overall_col1:
            st.metric("Overall Sufficient %", _format_pct(overall_summary.get("sufficient_percentage", 0.0)))
        with overall_col2:
            st.metric("Overall Insufficient %", _format_pct(overall_summary.get("insufficient_percentage", 0.0)))
        with overall_col3:
            st.metric("Procedures Evaluated", overall_summary.get("total_procedures", 0))
        
        summary_rows = []
        for payer_key, summary in per_payer_summary.items():
            payer_name = summary.get("payer_name", payer_key)
            summary_rows.append({
                "Payer": payer_name,
                "Total Procedures": summary.get("total_procedures", 0),
                "Sufficient %": _format_pct(summary.get("sufficient_percentage", 0.0)),
                "Insufficient %": _format_pct(summary.get("insufficient_percentage", 0.0)),
                "Other %": _format_pct(summary.get("other_percentage", 0.0)),
                "Sufficient Count": summary.get("sufficient_count", 0),
                "Insufficient Count": summary.get("insufficient_count", 0),
                "Other Count": summary.get("other_count", 0)
            })
        
        if summary_rows:
            import pandas as pd
            summary_df = pd.DataFrame(summary_rows)
            st.dataframe(summary_df, width='stretch', hide_index=True)
        
        with st.expander("View Raw Summary JSON", expanded=False):
            st.json(payer_summary)
    
    st.markdown("---")
    
    # Overall metrics
    st.markdown("### 📈 Overall Metrics")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        total_tokens = total_usage.input_tokens + total_usage.output_tokens
        st.metric("Total Tokens", f"{total_tokens:,}")
    
    with col2:
        st.metric("Total Cost", f"${total_cost:.6f}")
    
    with col3:
        payers_processed = len([p for p in payer_results.values() if not p.get("error")])
        st.metric("Payers Processed", payers_processed)
    
    with col4:
        total_time = sum(execution_times.values()) if execution_times else 0
        st.metric("Total Time", f"{total_time:.2f}s")
    
    st.markdown("---")
    
    # View mode selector
    view_mode = st.radio(
        "Select View Mode:",
        ["📋 CDI Recommendations", "📊 Cross-Payer Dashboard", "✨ Medical Chart Improvement"],
        horizontal=True,
        help="Choose between CDI recommendations, cross-payer analysis, or chart improvement"
    )
    
    st.markdown("---")
    
    if view_mode == "✨ Medical Chart Improvement":
        # Chart Improvement View
        st.markdown("## ✨ Medical Chart Improvement")
        st.info("🎯 **Goal:** Transform your medical chart based on CDI recommendations to improve clinical documentation quality and medical necessity support.")
        
        # Check if chart improver is initialized
        if st.session_state.chart_improver is None:
            st.session_state.chart_improver = ChartImprover(st.session_state.cdi_system.cache_manager)
        
        # Check if we have original chart
        if not st.session_state.original_chart_text:
            # Try to get original chart from processing result
            if numbered_chart:
                # Remove line numbers to get original chart
                lines = numbered_chart.split('\n')
                original_lines = []
                for line in lines:
                    # Remove line number prefix (format: "L001|")
                    if '|' in line:
                        original_lines.append(line.split('|', 1)[1] if len(line.split('|', 1)) > 1 else line)
                    else:
                        original_lines.append(line)
                st.session_state.original_chart_text = '\n'.join(original_lines)
        
        # Generate improvement button
        if st.session_state.improved_chart_result is None:
            col1, col2, col3 = st.columns([1, 2, 1])
            
            with col2:
                if st.button("🚀 Generate Improved Medical Chart", type="primary"):
                    if not st.session_state.original_chart_text:
                        st.error("❌ Original chart not available. Please process a chart first.")
                    else:
                        with st.spinner("🔄 Analyzing recommendations and improving chart... This may take a minute."):
                            progress_bar = st.progress(0)
                            progress_bar.progress(20)
                            
                            # Generate improved chart
                            improved_result = st.session_state.chart_improver.improve_medical_chart(
                                st.session_state.original_chart_text,
                                result
                            )
                            
                            progress_bar.progress(100)
                            st.session_state.improved_chart_result = improved_result
                            st.rerun()
        
        # Display improved chart if available
        if st.session_state.improved_chart_result:
            display_improved_medical_chart(
                st.session_state.original_chart_text,
                st.session_state.improved_chart_result
            )
            
            # Add reset button
            st.markdown("---")
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                if st.button("🔄 Regenerate Improvement"):
                    st.session_state.improved_chart_result = None
                    st.session_state.user_input_fields = {}  # Clear user inputs
                    st.rerun()
        else:
            st.markdown("### 📝 How Chart Improvement Works")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.markdown("#### 1️⃣ Analysis")
                st.info("AI analyzes all CDI recommendations from multiple payers to identify documentation requirements")
            
            with col2:
                st.markdown("#### 2️⃣ Enhancement")
                st.info("Improves chart structure, clarity, and completeness while preserving medical accuracy")
            
            with col3:
                st.markdown("#### 3️⃣ Guidance")
                st.info("Identifies fields requiring physician input with specific suggestions")
            
            st.markdown("---")
            
            st.markdown("### ✅ What Gets Improved")
            
            improvements_list = """
            - **Documentation Structure:** Organizes information into clear sections (Chief Complaint, HPI, Exam, etc.)
            - **Missing Requirements:** Highlights what needs to be documented (conservative treatment duration, imaging dates, etc.)
            - **Clinical Specificity:** Makes vague statements more specific and measurable
            - **Terminology:** Uses proper medical terminology where appropriate
            - **Medical Necessity:** Ensures clinical criteria supporting medical necessity are clearly documented
            """
            st.markdown(improvements_list)
            
            st.markdown("### ⚠️ Important Notes")
            
            st.warning("""
            **The AI will NOT:**
            - Fabricate clinical data or patient information
            - Create false test results or findings
            - Make up patient history or symptoms
            
            **The AI will:**
            - Reorganize existing information for clarity
            - Suggest areas where more documentation is needed
            - Mark fields that require physician input
            - Provide guidance on what should be documented
            """)
    
    elif view_mode == "📋 CDI Recommendations":
        # Extraction results
        if extraction_data:
            display_extraction_data(extraction_data)
            st.markdown("---")
        
        # Main tabs: Payer Results + Medical Chart (Medical Chart at the end)
        all_tabs = [Config.PAYER_CONFIG[key]["name"] for key in payer_results.keys()] + ["📄 Medical Chart"]
        tabs = st.tabs(all_tabs)
        
        # Payer results tabs (all except last)
        if payer_results:
            for tab, (payer_key, payer_result) in zip(tabs[:-1], payer_results.items()):
                with tab:
                    display_payer_results(payer_key, payer_result)
        
        # Last tab: Medical Chart
        with tabs[-1]:
            display_medical_chart(numbered_chart)
        
        # Execution times
        if execution_times:
            st.markdown("---")
            st.markdown("### ⏱️ Execution Times")
            
            cols = st.columns(len(execution_times))
            for col, (payer_key, exec_time) in zip(cols, execution_times.items()):
                payer_name = Config.PAYER_CONFIG[payer_key]["name"]
                col.metric(payer_name, f"{exec_time:.2f}s")
    
    else:  # Cross-Payer Dashboard
        display_cross_payer_dashboard(result)


def main():
    """Main Streamlit application."""
    # Initialize session state
    initialize_session_state()
    
    # Header with optional logo
    header_cols = st.columns([0.08, 0.92])
    with header_cols[0]:
        if ASCENT_LOGO_FILE:
            st.image(str(ASCENT_LOGO_FILE), width=56)
        else:
            st.markdown("<div style='font-size:2.4rem'>🟣</div>", unsafe_allow_html=True)
    with header_cols[1]:
        st.markdown('<div class="main-header">Clinical Documentation Improvement</div>', 
                    unsafe_allow_html=True)
    
    # Initialize system
    if not initialize_cdi_system():
        st.stop()
    
    # Sidebar
    display_system_info()
    display_cache_stats()
    
    # Main content area
    st.markdown("---")
    
    # File upload section with medical chart icon
    if CHART_ICON_FILE:
        icon_col, text_col = st.columns([0.08, 0.92])
        with icon_col:
            st.image(str(CHART_ICON_FILE))
        with text_col:
            st.markdown("### Upload Medical Chart")
    else:
        st.markdown("### 🩺 Upload Medical Chart")

    # If either image missing, guide user once (non-intrusive info box)
    missing_notes = []
    if not ASCENT_LOGO_FILE:
        missing_notes.append("Place `ascent.png` or `ascent_logo.png` in `logo/` (or `assets/`).")
    if not CHART_ICON_FILE:
        missing_notes.append("Place `images_logo.png` or `medical_chart_icon.png` in `logo/` (or `assets/`).")
    if missing_notes:
        st.info(" ".join(missing_notes))
    
    uploaded_file = st.file_uploader(
        "Choose a medical chart file (PDF or TXT)",
        type=["pdf", "txt"],
        help="Upload a medical chart file for CDI compliance evaluation"
    )
    
    # Process button
    if uploaded_file is not None:
        col1, col2, col3 = st.columns([1, 2, 1])
        
        with col2:
            if st.button("🚀 Process Chart", type="primary", width='stretch'):
                # Save uploaded file to temporary location
                with tempfile.NamedTemporaryFile(delete=False, suffix=Path(uploaded_file.name).suffix) as tmp_file:
                    tmp_file.write(uploaded_file.getvalue())
                    tmp_file_path = tmp_file.name
                
                try:
                    # Process the file
                    with st.spinner("🔄 Processing medical chart... This may take a minute."):
                        progress_bar = st.progress(0)
                        progress_bar.progress(10)
                        
                        result = st.session_state.cdi_system.process_file(tmp_file_path)
                        
                        progress_bar.progress(100)
                        st.session_state.processing_result = result
                        st.session_state.file_processed = True
                    
                    st.success("✅ Processing completed successfully!")
                    
                    # Clean up temporary file
                    try:
                        os.unlink(tmp_file_path)
                    except:
                        pass
                    
                except Exception as e:
                    st.error(f"❌ Error processing file: {e}")
                    # Clean up temporary file
                    try:
                        os.unlink(tmp_file_path)
                    except:
                        pass
    
    # Display results if available
    if st.session_state.file_processed and st.session_state.processing_result:
        st.markdown("---")
        display_processing_results(st.session_state.processing_result)
        
        # Download results as JSON
        st.markdown("---")
        st.markdown("### 💾 Export Results")
        
        result_dict = st.session_state.processing_result.__dict__
        result_json = json.dumps(result_dict, indent=2, default=str, ensure_ascii=False)
        
        st.download_button(
            label="📥 Download Results (JSON)",
            data=result_json,
            file_name=f"cdi_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json",
            width="stretch"
        )
    
    # Footer
    st.markdown("---")
    st.markdown(
        "<div style='text-align: center; color: #666;'>"
        "Multi-Payer CDI Compliance Checker v1.0.0 | "
        "Powered by AWS Bedrock & OpenSearch"
        "</div>",
        unsafe_allow_html=True
    )


if __name__ == "__main__":
    main()
