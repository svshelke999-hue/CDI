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

# Brand colors from medical website color palette
DARK_BLUE = "#122056"          # Page text color
ACCENT_BLUE = "#5B65DC"        # Accent color (buttons, links, active tabs)
LIGHT_BLUE = "#EEEFFD"         # Secondary buttons and ordered list elements
BG_LIGHT = "#FAFAFD"           # Page background color
WHITE = "#FFFFFF"              # Menu bar and tile color

# Custom CSS for brand styling with medical website color palette
st.markdown(f"""
<style>
    :root {{
        --dark-blue: {DARK_BLUE};
        --accent-blue: {ACCENT_BLUE};
        --light-blue: {LIGHT_BLUE};
        --bg-light: {BG_LIGHT};
        --white: {WHITE};
    }}

    /* Typography normalization */
    html, body, [class*="st-"], .stApp {{
        font-size: 16px;
    }}
    .stApp, .stApp * {{
        font-weight: 400;
    }}
    /* Standardize markdown heading sizes (Streamlit uses these heavily) */
    .stMarkdown h1 {{ font-size: 1.8rem; font-weight: 800; margin: 0.6rem 0; }}
    .stMarkdown h2 {{ font-size: 1.5rem; font-weight: 800; margin: 0.5rem 0; }}
    .stMarkdown h3 {{ font-size: 1.25rem; font-weight: 750; margin: 0.4rem 0; }}
    .stMarkdown h4 {{ font-size: 1.1rem; font-weight: 700; margin: 0.35rem 0; }}
    .stMarkdown p, .stMarkdown li {{ font-size: 1rem; }}
    /* Keep labels readable but not oversized */
    label, .stMarkdown label {{ font-size: 1rem; font-weight: 600; }}

    /* Page background */
    .stApp {{
        background-color: {BG_LIGHT};
    }}
    
    /* Main content area background */
    .main .block-container {{
        background-color: {BG_LIGHT};
    }}

    /* Header */
    .main-header {{
        font-size: 2.5rem;
        font-weight: 800;
        color: {DARK_BLUE};
        text-align: center;
        padding: 1rem 0;
    }}

    .sub-header {{
        font-size: 1.5rem;
        font-weight: 700;
        color: {DARK_BLUE};
        margin-top: 1rem;
    }}

    .payer-section {{
        background-color: {WHITE};
        padding: 1rem;
        border-radius: 0.5rem;
        border: 1px solid {LIGHT_BLUE};
        margin: 1rem 0;
    }}

    .metric-card {{
        background-color: {WHITE};
        padding: 1rem;
        border-radius: 0.5rem;
        border: 1px solid {LIGHT_BLUE};
        text-align: center;
        box-shadow: 0 1px 2px rgba(0,0,0,0.04);
    }}

    .decision-sufficient {{ color: #1b7f5a; font-weight: 700; }}
    .decision-insufficient {{ color: #b3261e; font-weight: 700; }}
    .decision-not-applicable {{ color: #b56b00; font-weight: 700; }}

    .requirement-met {{
        background-color: {LIGHT_BLUE};
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

    /* Primary Buttons - Dark Blue */
    .stButton>button {{
        background-color: {DARK_BLUE};
        color: {WHITE};
        border: 0;
        padding: 0.6rem 1rem;
        font-weight: 800;
        font-size: 1rem;
        border-radius: 8px;
    }}
    .stButton>button:hover {{
        background-color: {ACCENT_BLUE};
        filter: brightness(1.05);
    }}

    /* Secondary Buttons - Light Blue */
    .stButton>button[kind="secondary"] {{
        background-color: {LIGHT_BLUE};
        color: {DARK_BLUE};
        border: 1px solid {ACCENT_BLUE};
    }}

    /* Progress bar */
    .stProgress > div > div > div > div {{
        background-color: {ACCENT_BLUE};
    }}

    /* Tabs - bigger/bolder + clear selected state (used for payer tabs + Medical Chart) */
    .stTabs [data-baseweb="tab-list"] {{
        background-color: {WHITE};
        border-bottom: 2px solid {LIGHT_BLUE};
        padding: 0.25rem 0.25rem 0;
    }}
    
    .stTabs [data-baseweb="tab-list"] button {{
        color: {DARK_BLUE};
        font-size: 1.15rem;
        font-weight: 800;
        padding: 0.75rem 1.1rem;
        border-radius: 12px 12px 0 0;
        margin-right: 0.35rem;
    }}
    
    .stTabs [data-baseweb="tab-list"] button[aria-selected="true"] {{
        border-bottom: 3px solid {ACCENT_BLUE};
        background: {ACCENT_BLUE};
        color: {WHITE};
        font-weight: 900;
    }}

    /* Sidebar */
    section[data-testid="stSidebar"] {{
        background-color: {LIGHT_BLUE};
    }}
    
    section[data-testid="stSidebar"] [data-testid="stHeader"] {{
        color: {DARK_BLUE};
    }}

    /* Expanders and containers */
    .streamlit-expanderHeader {{
        background-color: {WHITE};
        color: {DARK_BLUE};
    }}

    /* Links */
    a {{
        color: {ACCENT_BLUE};
    }}
    a:hover {{
        color: {DARK_BLUE};
    }}

    /* Text areas and inputs */
    .stTextInput>div>div>input {{
        background-color: {WHITE};
        border-color: {LIGHT_BLUE};
    }}

    /* Select widgets (selectbox/multiselect) - slightly larger and clearer */
    [data-baseweb="select"] > div {{
        font-size: 1.05rem;
        font-weight: 600;
    }}
    /* Radio/checkbox text */
    [role="radiogroup"] label, [data-testid="stCheckbox"] label {{
        font-size: 1.05rem;
        font-weight: 600;
    }}

    /* Dataframes and tables */
    .dataframe {{
        background-color: {WHITE};
    }}
</style>
""", unsafe_allow_html=True)


def check_password():
    """Returns `True` if the user had the correct password."""
    
    def password_entered():
        """Checks whether a password entered by the user is correct."""
        # Get password from Streamlit Secrets or use default
        if hasattr(st, 'secrets') and 'APP_PASSWORD' in st.secrets:
            correct_password = st.secrets['APP_PASSWORD']
        else:
            # Fallback to environment variable or default (for local development)
            correct_password = os.getenv("APP_PASSWORD", "CDI2024Secure!")
        
        if st.session_state["password"] == correct_password:
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # Don't store password in session state
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        # First run, show input for password
        st.markdown("---")
        st.markdown("### 🔒 Access Restricted")
        st.markdown("This application requires authentication. Please enter the password to continue.")
        st.text_input(
            "Enter password", 
            type="password", 
            on_change=password_entered, 
            key="password",
            help="Contact the administrator for access credentials"
        )
        return False
    elif not st.session_state["password_correct"]:
        # Password not correct, show input + error
        st.markdown("---")
        st.markdown("### 🔒 Access Restricted")
        st.error("😕 Password incorrect. Please try again.")
        st.text_input(
            "Enter password", 
            type="password", 
            on_change=password_entered, 
            key="password",
            help="Contact the administrator for access credentials"
        )
        return False
    else:
        # Password correct
        return True


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
    if 'view_mode' not in st.session_state:
        st.session_state.view_mode = "📋 CDI Recommendations"


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


def display_available_payers():
    """Display available payers in sidebar with medical color palette styling."""
    # Apply light blue background to sidebar (from color palette)
    st.sidebar.markdown(
        f"""
        <style>
        section[data-testid="stSidebar"] {{
            background-color: {LIGHT_BLUE};
        }}
        </style>
        """,
        unsafe_allow_html=True
    )
    
    # Display Available Payers heading in dark blue
    st.sidebar.markdown(
        f'<h3 style="color: {DARK_BLUE}; font-weight: bold; margin-bottom: 1rem;">Available Payers</h3>',
        unsafe_allow_html=True
    )
    
    # Get payer names from Config
    if st.session_state.cdi_system:
        info = st.session_state.cdi_system.get_system_info()
        configured_payers = info.get('configured_payers', [])
        
        if configured_payers:
            for payer in configured_payers:
                payer_config = Config.PAYER_CONFIG.get(payer, {})
                payer_name = payer_config.get('name', payer)
                st.sidebar.markdown(f"• {payer_name}")
        else:
            # Fallback: show all payers from Config
            for payer_key, payer_config in Config.PAYER_CONFIG.items():
                payer_name = payer_config.get('name', payer_key)
                st.sidebar.markdown(f"• {payer_name}")


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
    st.markdown("#### 📋 Extraction Results")
    
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

    # 1) Prefer concise, model-generated summary recommendations (top 3–5)
    summary_recs = recommendations.get("summary_recommendations") or []
    summary_recs = [r for r in summary_recs if isinstance(r, str) and r.strip()]

    if summary_recs:
        unique = []
        seen = set()
        for r in summary_recs:
            r_clean = r.strip()
            if r_clean and r_clean not in seen:
                seen.add(r_clean)
                unique.append(r_clean)
        # Limit to 5 bullets for a focused view
        to_show = unique[:5]
        if to_show:
            st.markdown("**Improvement Recommendations:**")
            for r in to_show:
                st.markdown(f"- {r}")
            return

    # 2) Fallback: build up to 5 concise bullets from available fields (no category prefixes)
    all_recommendations = []

    def _extend_clean(items):
        for item in items or []:
            if isinstance(item, str):
                txt = item.strip()
                if txt:
                    all_recommendations.append(txt)

    # Prefer clinical documentation/action items first
    _extend_clean(recommendations.get("cdi_documentation_gaps"))
    _extend_clean(recommendations.get("completion_guidance"))
    _extend_clean(recommendations.get("next_steps"))
    _extend_clean(recommendations.get("documentation_gaps"))
    _extend_clean(recommendations.get("compliance_actions"))
    _extend_clean(recommendations.get("policy_needed"))

    # De-duplicate while preserving order and cap at 5
    if all_recommendations:
        seen = set()
        final_list = []
        for r in all_recommendations:
            if r not in seen:
                seen.add(r)
                final_list.append(r)
            if len(final_list) >= 5:
                break

        if final_list:
            st.markdown("**Improvement Recommendations:**")
            for r in final_list:
                st.markdown(f"- {r}")
            return

    # 3) If still nothing meaningful, show fallback message
    st.info("No specific recommendations available for this procedure")


def display_cms_guidelines(cms_sources, cms_guidelines_context, cms_has_guidelines, proc_result):
    """Display CMS general guidelines with evidence and compliance status."""
    
    # Always show the tab, even if no CMS guidelines were found
    # This helps users understand that CMS guidelines are being checked
    
    if not cms_sources and not cms_has_guidelines:
        st.info("ℹ️ No CMS general guidelines were retrieved for this procedure.")
        st.caption("CMS general guidelines are universal coding requirements that apply to all payers. They are checked before payer-specific guidelines.")
        st.markdown("---")
        st.markdown("### Why no CMS guidelines?")
        st.markdown("""
        Possible reasons:
        - No relevant CMS general guidelines matched the procedure/diagnosis
        - CMS guidelines database may need to be updated
        - The procedure may not have specific CMS general guideline requirements
        
        **Note:** Even if no CMS guidelines are shown, the evaluation still checks payer-specific guidelines.
        """)
        return
    
    # If we have context but no sources, still show something
    if cms_guidelines_context and not cms_sources:
        st.warning("⚠️ CMS guidelines context found but sources are missing. This may indicate a data structure issue.")
        st.markdown("### CMS Guidelines Context")
        st.text(cms_guidelines_context[:1000] + "..." if len(cms_guidelines_context) > 1000 else cms_guidelines_context)
        return
    
    st.markdown("### 📋 CMS General Guidelines Overview")
    st.success(f"✓ Found **{len(cms_sources)}** relevant CMS general guideline(s)")
    st.info("💡 **CMS general guidelines are universal requirements that apply to ALL payers. These must be satisfied before payer-specific guidelines are evaluated.**")
    
    # Display compliance status summary
    st.markdown("---")
    st.markdown("### ✅ CMS Compliance Status")
    
    # Analyze requirement checklist and decision to determine CMS compliance
    requirements = proc_result.get("requirement_checklist", [])
    decision = proc_result.get("decision", "").lower()
    primary_reasons = proc_result.get("primary_reasons", [])
    
    # Determine overall CMS compliance
    cms_compliance_status = "unknown"
    cms_compliance_reason = ""
    cms_specific_issues = []
    
    # Check if decision indicates CMS compliance
    if "sufficient" in decision:
        # Check if there are any unmet requirements that might be CMS-related
        unmet_cms_reqs = []
        for req in requirements:
            req_id = req.get("requirement_id", "").lower()
            status = req.get("status", "").lower()
            # Look for CMS-related requirements
            if status in ["unmet", "unclear"] and any(keyword in req_id for keyword in ["documentation", "coding", "diagnosis", "reporting", "accurate"]):
                unmet_cms_reqs.append(req)
        
        if unmet_cms_reqs:
            cms_compliance_status = "partially_met"
            cms_compliance_reason = "CMS guidelines mostly met, but some requirements need attention"
            for req in unmet_cms_reqs[:3]:  # Show first 3 issues
                missing = req.get("missing_to_meet", "")
                if missing:
                    cms_specific_issues.append(f"• {req.get('requirement_id', 'Unknown')}: {missing}")
        else:
            cms_compliance_status = "met"
            cms_compliance_reason = "✅ Procedure meets CMS general guidelines"
    elif "insufficient" in decision:
        cms_compliance_status = "not_met"
        cms_compliance_reason = "❌ Procedure does not meet CMS general guidelines"
        # Extract CMS-related issues from primary reasons
        for reason in primary_reasons:
            if any(keyword in reason.lower() for keyword in ["documentation", "coding", "diagnosis", "reporting", "accurate", "cms"]):
                cms_specific_issues.append(f"• {reason}")
    else:
        cms_compliance_status = "unclear"
        cms_compliance_reason = "⚠️ CMS compliance status unclear - review required"
    
    # Display compliance badge
    col1, col2 = st.columns([1, 3])
    with col1:
        if cms_compliance_status == "met":
            st.success("✅ **MET**")
        elif cms_compliance_status == "partially_met":
            st.warning("⚠️ **PARTIALLY MET**")
        elif cms_compliance_status == "not_met":
            st.error("❌ **NOT MET**")
        else:
            st.warning("⚠️ **UNCLEAR**")
    
    with col2:
        st.markdown(f"**Status:** {cms_compliance_reason}")
        if cms_specific_issues:
            st.markdown("**Issues identified:**")
            for issue in cms_specific_issues:
                st.markdown(issue)
    
    # Display each CMS guideline with evidence
    st.markdown("---")
    st.markdown("### 📄 CMS Guidelines Used")
    
    for idx, cms_source in enumerate(cms_sources, 1):
        full_source = cms_source.get("full_source", {})
        semantic_title = full_source.get("semantic_title", "CMS General Guideline")
        guideline_id = full_source.get("guideline_id", "")
        score = cms_source.get("score", 0.0)
        
        # Get content
        content = full_source.get("content", {})
        full_text = content.get("full_text", "")
        summary = content.get("summary", "")
        key_concepts = content.get("key_concepts", [])
        detailed_rules = content.get("detailed_rules", [])
        
        # Get metadata
        metadata = full_source.get("metadata", {})
        category = metadata.get("category", "")
        section_path = full_source.get("section_path", "")
        page_number = full_source.get("page_number", "")
        
        # Create expander for each guideline
        with st.expander(f"**Guideline {idx}:** {semantic_title} | Score: {score:.1f}", expanded=idx==1):
            # Header information
            col1, col2 = st.columns([2, 1])
            with col1:
                if guideline_id:
                    st.markdown(f"**Guideline ID:** `{guideline_id}`")
                if section_path:
                    st.markdown(f"**Section:** {section_path}")
                if page_number:
                    st.markdown(f"**Page:** {page_number}")
            with col2:
                st.metric("Relevance Score", f"{score:.1f}")
                if category:
                    st.caption(f"Category: {category}")
            
            # Display full text
            if full_text:
                st.markdown("---")
                st.markdown("#### 📝 Guideline Text")
                st.markdown(full_text)
            
            # Display summary
            if summary:
                st.markdown("---")
                st.markdown("#### 📋 Summary")
                st.info(summary)
            
            # Display key concepts
            if key_concepts:
                st.markdown("---")
                st.markdown("#### 🔑 Key Concepts")
                for concept in key_concepts:
                    st.markdown(f"• {concept}")
            
            # Display detailed rules
            if detailed_rules:
                st.markdown("---")
                st.markdown("#### 📜 Detailed Rules")
                for rule in detailed_rules:
                    rule_id = rule.get("rule_id", "")
                    rule_text = rule.get("rule_text", "")
                    explanation = rule.get("explanation", "")
                    importance = rule.get("importance", "")
                    
                    rule_container = st.container()
                    with rule_container:
                        if rule_id:
                            st.markdown(f"**{rule_id}**")
                        if rule_text:
                            st.markdown(f"• {rule_text}")
                        if explanation:
                            st.caption(f"  → {explanation}")
                        if importance:
                            importance_badge = "🔴 Critical" if importance == "critical" else "🟡 Important" if importance == "important" else "🔵 Standard"
                            st.caption(importance_badge)
            
            # Display evidence references
            st.markdown("---")
            st.markdown("#### 📍 Evidence References")
            
            # Extract evidence from the guideline content
            evidence_refs = []
            if full_text:
                import re
                # Look for evidence patterns like "(Evidence: pg no: X, LY)"
                pattern = r'\(Evidence:\s*pg\s+no:\s*(\d+),?\s*L(\d+(?:-L\d+)?)\)'
                matches = re.findall(pattern, full_text)
                for match in matches:
                    evidence_refs.append(f"Page {match[0]}, Line {match[1]}")
            
            if summary:
                matches = re.findall(pattern, summary)
                for match in matches:
                    evidence_refs.append(f"Page {match[0]}, Line {match[1]}")
            
            if evidence_refs:
                unique_evidence = sorted(set(evidence_refs))
                st.success(f"Found **{len(unique_evidence)}** evidence reference(s)")
                for ref in unique_evidence:
                    st.markdown(f"• {ref}")
            else:
                st.info("No specific page/line evidence references found in this guideline")
            
            # Display coding scenarios if available
            coding_scenarios = full_source.get("coding_scenarios", [])
            if coding_scenarios:
                st.markdown("---")
                st.markdown("#### 💡 Coding Scenarios")
                for scenario in coding_scenarios[:2]:  # Show first 2 scenarios
                    scenario_text = scenario.get("scenario", "")
                    if scenario_text:
                        with st.expander(f"Scenario: {scenario_text[:50]}...", expanded=False):
                            st.markdown(f"**Scenario:** {scenario_text}")
                            
                            correct_coding = scenario.get("correct_coding", {})
                            if correct_coding:
                                st.markdown("**Correct Coding:**")
                                primary_code = correct_coding.get("primary_code", "")
                                secondary_codes = correct_coding.get("secondary_codes", [])
                                if primary_code:
                                    st.markdown(f"• Primary: `{primary_code}`")
                                if secondary_codes:
                                    for code in secondary_codes:
                                        st.markdown(f"• Secondary: `{code}`")
    
    # Display how CMS guidelines relate to payer evaluation
    st.markdown("---")
    st.markdown("### 🔗 Relationship to Payer Evaluation")
    st.info("""
    **CMS General Guidelines are evaluated FIRST**, before any payer-specific guidelines.
    
    - If CMS guidelines are **NOT MET**, the procedure may be insufficient regardless of payer-specific compliance
    - If CMS guidelines are **MET**, the evaluation proceeds to payer-specific guidelines
    - Each payer may have additional requirements beyond CMS general guidelines
    """)
    
    # Show requirement checklist items that might relate to CMS
    if requirements:
        st.markdown("---")
        st.markdown("### 📋 Related Requirements")
        st.caption("The following requirements may be related to CMS general guidelines:")
        
        cms_related_reqs = []
        for req in requirements:
            req_id = req.get("requirement_id", "").lower()
            # Look for requirements that might be CMS-related
            if any(keyword in req_id for keyword in ["documentation", "coding", "diagnosis", "reporting", "accurate"]):
                cms_related_reqs.append(req)
        
        if cms_related_reqs:
            for req in cms_related_reqs[:5]:  # Show first 5
                req_id = req.get("requirement_id", "")
                status = req.get("status", "")
                missing = req.get("missing_to_meet", "")
                
                status_badge = "✅ Met" if status == "met" else "❌ Not Met" if status == "unmet" else "⚠️ Unclear"
                st.markdown(f"**{req_id}** - {status_badge}")
                if missing and status != "met":
                    st.caption(f"  Missing: {missing}")
        else:
            st.caption("No specific CMS-related requirements identified in the checklist")


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
        tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
            "📝 Requirements", 
            "📋 Chart Evidence",
            "⏰ Timing", 
            "⚠️ Contraindications", 
            "💊 Coding", 
            "📈 Recommendations",
            "📄 Guideline Evidence",
            "🏥 CMS Guidelines"
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
        
        with tab8:
            st.markdown("#### CMS General Guidelines")
            # Get CMS sources from the procedure result
            cms_sources = proc_result.get("cms_sources", [])
            cms_guidelines_context = proc_result.get("cms_guidelines_context", "")
            cms_has_guidelines = proc_result.get("cms_has_guidelines", False)
            
            # Debug: Show what we're getting
            if st.session_state.get("debug_mode", False):
                with st.expander("🔍 Debug Info", expanded=False):
                    st.write("CMS Sources:", len(cms_sources) if cms_sources else "None")
                    st.write("CMS Has Guidelines:", cms_has_guidelines)
                    st.write("CMS Context Length:", len(cms_guidelines_context) if cms_guidelines_context else 0)
                    st.write("Procedure Result Keys:", list(proc_result.keys())[:10])
            
            display_cms_guidelines(cms_sources, cms_guidelines_context, cms_has_guidelines, proc_result)


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
        st.markdown("### Compliance Impact")
        
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
    # Remove line numbers and all markers from comparison version (final human-readable chart)
    populated_clean = remove_line_numbers(final_chart)

    # Remove AI markers entirely (keep the actual chart text)
    populated_clean = re.sub(r'\[AI ADDED:\s*[^\]]+\]\s*', '', populated_clean)
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
    
    # Remove line numbers and all markers for clean medical chart format (download)
    chart_no_lines = remove_line_numbers(final_chart)
    chart_no_lines = re.sub(r'^L\d+\|', '', chart_no_lines, flags=re.MULTILINE)
    # Remove all marker types for clean medical chart format
    chart_no_lines = re.sub(r'\[AI ADDED:\s*[^\]]+\]\s*', '', chart_no_lines)
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
    st.markdown("###  Summary Metrics")
    
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
    
    st.markdown("---")
    
    # Important Information from Related Files
    multi_chart_info = getattr(result, "multi_chart_info", None)
    if multi_chart_info:
        other_charts_info = multi_chart_info.get("other_charts_info", {})
        
        if other_charts_info:
            st.markdown("### 📄 Important Information from Related Files")
        
            # Collect important information from all related charts
            important_info = []
            
            for chart_file, chart_info in other_charts_info.items():
                chart_title = chart_info.get("display_title") or chart_info.get("chart_type", "unknown").replace("_", " ").title()
                
                # Collect summary
                if chart_info.get("summary"):
                    important_info.append(f"{chart_title} Summary: {chart_info['summary']}")
                
                # Collect diagnosis
                diagnosis = chart_info.get("diagnosis", [])
                if diagnosis:
                    if isinstance(diagnosis, list):
                        diag_text = ", ".join(diagnosis[:3])  # First 3 diagnoses
                        if len(diagnosis) > 3:
                            diag_text += f" and {len(diagnosis) - 3} more"
                    else:
                        diag_text = str(diagnosis)
                    important_info.append(f"{chart_title} Diagnosis: {diag_text}")
        
                # Collect important tests/studies
                tests = chart_info.get("tests", [])
                reports = chart_info.get("reports", [])
                if tests or reports:
                    test_items = []
                    if tests:
                        if isinstance(tests, list):
                            test_items.extend(tests[:3])
                        else:
                            test_items.append(str(tests))
                    if reports:
                        if isinstance(reports, list):
                            test_items.extend([f"Report: {r}" for r in reports[:2]])
                        else:
                            test_items.append(f"Report: {reports}")
                    if test_items:
                        test_text = ", ".join(test_items)
                        important_info.append(f"{chart_title} Tests/Studies: {test_text}")
                
                # Collect medications
                medications = chart_info.get("medications", [])
                if medications:
                    if isinstance(medications, list):
                        med_text = ", ".join(medications[:5])  # First 5 medications
                        if len(medications) > 5:
                            med_text += f" and {len(medications) - 5} more"
                    else:
                        med_text = str(medications)
                    important_info.append(f"{chart_title} Medications: {med_text}")
                
                # Collect imaging studies
                imaging = chart_info.get("imaging", [])
                if imaging:
                    if isinstance(imaging, list):
                        img_text = ", ".join(imaging[:3])
                        if len(imaging) > 3:
                            img_text += f" and {len(imaging) - 3} more"
                    else:
                        img_text = str(imaging)
                    important_info.append(f"{chart_title} Imaging: {img_text}")
                
                # Collect conservative treatment info
                conservative_treatment = chart_info.get("conservative_treatment", {})
                if conservative_treatment and isinstance(conservative_treatment, dict):
                    treatment_items = []
                    for key, value in conservative_treatment.items():
                        if value:
                            treatment_items.append(f"{key.replace('_', ' ').title()}: {value}")
                    if treatment_items:
                        treatment_text = "; ".join(treatment_items[:3])
                        important_info.append(f"{chart_title} Conservative Treatment: {treatment_text}")
            
            # Display important information in the same format as Common Documentation Gaps
            if important_info:
                info_html = "<ul style='margin-top: 8px;'>"
                for info in important_info[:15]:  # Top 15 items
                    info_html += f"<li>{info}</li>"
                info_html += "</ul>"
                st.markdown(info_html, unsafe_allow_html=True)
            else:
                st.info("ℹ️ No additional information available from related files.")
            
            st.markdown("")
    
    # Standardized CDI Summary (simple, human-readable bullets)
    st.markdown("### 🧩 CDI Summary (Key Gaps)")

    # Get related charts information for gap filtering
    multi_chart_info = getattr(result, "multi_chart_info", None)
    other_charts_info = {}
    if multi_chart_info:
        other_charts_info = multi_chart_info.get("other_charts_info", {})

    policy_needed = set()
    cdi_gaps = set()
    
    # Helper function to check if gap information is already in related charts
    def is_gap_covered_in_related_charts(gap_text):
        """Check if the gap information is already documented in related charts."""
        if not other_charts_info or not gap_text:
            return False
        
        gap_lower = gap_text.lower()
        
        # Check each related chart for the information
        for chart_file, chart_info in other_charts_info.items():
            # Check conservative treatment
            if any(kw in gap_lower for kw in ["conservative", "treatment", "therapy", "pt", "physical therapy", "medication", "injection"]):
                conservative_treatment = chart_info.get("conservative_treatment", {})
                if conservative_treatment and isinstance(conservative_treatment, dict):
                    # Check if conservative treatment info exists
                    has_treatment = any(
                        value for key, value in conservative_treatment.items() 
                        if value and isinstance(value, (str, int, float)) and str(value).strip()
                    )
                    if has_treatment:
                        return True
            
            # Check duration/timeframe
            if any(kw in gap_lower for kw in ["duration", "weeks", "months", "timeframe", "period"]):
                # Check if duration is mentioned in summary or other fields
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
            if any(kw in gap_lower for kw in ["functional", "limitation", "adl", "activities of daily living", "activity"]):
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
            if any(kw in gap_lower for kw in ["imaging", "mri", "xray", "x-ray", "ct", "radiology", "finding"]):
                imaging = chart_info.get("imaging", [])
                if imaging:
                    return True
                tests = chart_info.get("tests", [])
                if tests:
                    tests_str = " ".join([str(t) for t in tests]).lower()
                    if any(kw in tests_str for kw in ["mri", "xray", "x-ray", "ct", "imaging"]):
                        return True
        
        return False

    # Helper function to check if text is policy-related (not a documentation gap)
    def is_policy_related(text):
        text_lower = text.lower()
        policy_keywords = [
            "policy", "guideline", "payer", "cigna", "anthem", "uhc", "unitedhealthcare",
            "aetna", "medicare", "medicaid", "policy_availability", "applicable policy",
            "request specific", "medical policy", "guideline needed", "applicable"
        ]
        return any(kw in text_lower for kw in policy_keywords)
    
    # Helper function to check if text is generic/unhelpful
    def is_generic_unhelpful(text):
        text_lower = text.lower()
        generic_phrases = [
            "unable to determine",
            "without applicable policy",
            "without specific policy",
            "policy not available",
            "guideline not found",
            "no policy found"
        ]
        return any(phrase in text_lower for phrase in generic_phrases)
    
    # Helper function to check if it's a clinical documentation gap (can be improved in chart)
    def is_clinical_gap(text):
        text_lower = text.lower()
        clinical_keywords = [
            "conservative", "treatment", "therapy", "pt", "physical therapy", "medication", "injection",
            "duration", "weeks", "months", "timeframe", "period",
            "physical examination", "exam", "range of motion", "rom", "strength", "test", "impingement",
            "functional", "limitation", "adl", "activities of daily living", "activity",
            "pain", "scale", "vas", "nrs", "score", "measurement",
            "imaging", "mri", "xray", "x-ray", "ct", "radiology", "finding",
            "documented", "documentation", "not documented", "missing", "lacks", "incomplete",
            "not specified", "not stated", "not provided", "not measured", "not recorded"
        ]
        return any(kw in text_lower for kw in clinical_keywords)
    
    # Clean up gap text to be more readable and user-friendly
    def _clean_gap_text(text):
        """Remove technical IDs, clean up language, make it readable for non-technical users."""
        if not text:
            return ""
        
        original_text = text
        
        # Remove requirement ID prefixes (format: "requirement_id: description")
        # Handle cases like "conservative_management: Documentation of..."
        if ":" in text:
            parts = text.split(":", 1)
            if len(parts) == 2:
                first_part = parts[0].strip()
                # Check if first part looks like a technical ID
                # Technical IDs typically have underscores, are short, or are all lowercase with underscores
                if ("_" in first_part and len(first_part) < 50) or \
                   (first_part.islower() and "_" in first_part) or \
                   (len(first_part) < 30 and not " " in first_part):
                    # Use only the description part
                    text = parts[1].strip()
        
        text = text.strip()
        if not text:
            return ""
        
        # Clean up common technical patterns and make more readable
        # Remove redundant "Documentation of" prefix
        if text.lower().startswith("documentation of "):
            text = text[17:].strip()
        
        # Remove redundant "Document" prefix
        if text.lower().startswith("document "):
            text = text[9:].strip()
        
        # Convert technical language to plain language
        # "Documentation of failure of provider-directed non-surgical management" 
        # -> "Failure of non-surgical treatment"
        text = text.replace("provider-directed non-surgical management", "non-surgical treatment")
        text = text.replace("non-surgical management", "non-surgical treatment")
        text = text.replace("conservative management", "conservative treatment")
        
        # Clean up "Insufficient documentation to meet..." type messages
        if "insufficient documentation" in text.lower() and "to meet" in text.lower():
            if "criteria for" in text.lower():
                parts = text.lower().split("criteria for")
                if len(parts) > 1:
                    procedure = parts[1].strip()
                    text = f"Documentation does not meet requirements for {procedure}"
            elif "interqual" in text.lower() or "criteria" in text.lower():
                # Simplify technical criteria references
                text = "Documentation does not meet all required criteria"
        
        # Make descriptions more natural
        # "Documentation of abnormal shoulder physical examination findings compared to non-involved side"
        # -> "Abnormal shoulder physical examination findings compared to non-involved side"
        # "Documentation of positive Neer Impingement Test"
        # -> "Positive Neer Impingement Test results"
        
        # Remove "Documentation of" if still present
        if text.lower().startswith("documentation of "):
            text = text[17:].strip()
        
        # Make "Document specific..." -> "Specific..."
        if text.lower().startswith("document specific"):
            text = text[15:].strip()
            if text:
                text = "Specific " + text
        
        # Make "Specify..." -> "Missing: ..." for clarity
        if text.lower().startswith("specify "):
            text = text[8:].strip()
            if text:
                text = f"Missing: {text}"
        
        # Clean up "Include..." -> "Missing: ..."
        if text.lower().startswith("include "):
            text = text[8:].strip()
            if text:
                text = f"Missing: {text}"
        
        # Make sure it starts with a capital letter
        if text and text[0].islower():
            text = text[0].upper() + text[1:]
        
        # Final cleanup - remove any remaining technical jargon
        text = text.replace("CP: Procedures", "procedure")
        text = text.replace("InterQual", "")
        text = text.strip()
        
        return text

    for payer_key, payer_result in payer_results.items():
        if isinstance(payer_result, dict):
            payer_name = payer_result.get("payer_name", payer_key)
            procedure_results = payer_result.get("procedure_results", [])
        else:
            payer_name = getattr(payer_result, "payer_name", payer_key)
            procedure_results = getattr(payer_result, "procedure_results", [])

        for proc_result in procedure_results:
            # Get procedure result as dict for easier access
            if not isinstance(proc_result, dict):
                proc_result = {
                    "improvement_recommendations": getattr(proc_result, "improvement_recommendations", {}),
                    "requirement_checklist": getattr(proc_result, "requirement_checklist", []),
                    "primary_reasons": getattr(proc_result, "primary_reasons", [])
                }
            
            improvement = proc_result.get("improvement_recommendations", {})
            if not isinstance(improvement, dict):
                improvement = {}

            # Extract policy needs (separate from documentation gaps)
            for s in improvement.get("policy_needed", []) or []:
                if isinstance(s, str) and s.strip():
                    policy_needed.add(s.strip())
            
            # Extract cdi_documentation_gaps - ONLY clinical documentation gaps
            for s in improvement.get("cdi_documentation_gaps", []) or []:
                if isinstance(s, str) and s.strip():
                    s_clean = s.strip()
                    # Only add if it's a clinical gap and not policy-related
                    if is_clinical_gap(s_clean) and not is_policy_related(s_clean) and not is_generic_unhelpful(s_clean):
                        cleaned = _clean_gap_text(s_clean)
                        if cleaned:
                            # Check if this gap is already covered in related charts
                            if not is_gap_covered_in_related_charts(cleaned):
                                cdi_gaps.add(cleaned)
                    elif is_policy_related(s_clean):
                        policy_needed.add(s_clean)
            
            # Also check documentation_gaps - ONLY clinical documentation gaps
            for s in improvement.get("documentation_gaps", []) or []:
                if isinstance(s, str) and s.strip():
                    s_clean = s.strip()
                    if is_clinical_gap(s_clean) and not is_policy_related(s_clean) and not is_generic_unhelpful(s_clean):
                        cleaned = _clean_gap_text(s_clean)
                        if cleaned:
                            # Check if this gap is already covered in related charts
                            if not is_gap_covered_in_related_charts(cleaned):
                                cdi_gaps.add(cleaned)
                    elif is_policy_related(s_clean):
                        policy_needed.add(s_clean)
            
            # Extract from requirement_checklist - focus ONLY on clinical documentation gaps
            requirement_checklist = proc_result.get("requirement_checklist", [])
            if isinstance(requirement_checklist, list):
                for req in requirement_checklist:
                    if isinstance(req, dict):
                        status = req.get("status", "").lower()
                        if status in ["unmet", "unclear", "insufficient", "not met", "partially met"]:
                            missing = req.get("missing_to_meet", "")
                            req_id = req.get("requirement_id", "").lower()
                            req_type = req.get("requirement_type", "").lower()
                            
                            # Skip ALL policy-related requirements
                            if "policy_availability" in req_id or "policy" in req_id or "policy" in req_type:
                                if missing and missing.strip():
                                    policy_needed.add(missing.strip())
                                continue
                            
                            # Only add if it's a clinical documentation gap
                            if missing and missing.strip():
                                missing_clean = missing.strip()
                                # Must be clinical gap, not policy-related, not generic
                                if is_clinical_gap(missing_clean) and not is_policy_related(missing_clean) and not is_generic_unhelpful(missing_clean):
                                    # Never include requirement ID - just use the missing description
                                    # Clean up the text to be more readable
                                    gap_text = _clean_gap_text(missing_clean)
                                    if gap_text:
                                        # Check if this gap is already covered in related charts
                                        if not is_gap_covered_in_related_charts(gap_text):
                                            cdi_gaps.add(gap_text)
            
            # Extract from primary_reasons - ONLY clinical documentation gaps
            primary_reasons = proc_result.get("primary_reasons", [])
            if isinstance(primary_reasons, list):
                for reason in primary_reasons:
                    if isinstance(reason, str) and reason.strip():
                        reason_clean = reason.strip()
                        # Only add if it's a clinical gap
                        if is_clinical_gap(reason_clean) and not is_policy_related(reason_clean) and not is_generic_unhelpful(reason_clean):
                            if any(keyword in reason_clean.lower() for keyword in [
                                "missing", "not documented", "lacks", "insufficient", "absent", 
                                "not found", "not specified", "not stated", "not provided",
                                "incomplete", "unclear", "not measured", "not recorded"
                            ]):
                                cleaned = _clean_gap_text(reason_clean)
                                if cleaned:
                                    # Check if this gap is already covered in related charts
                                    if not is_gap_covered_in_related_charts(cleaned):
                                        cdi_gaps.add(cleaned)

    def _render_bullets(items):
        if not items:
            return
        html = "<ul style='margin-top: 8px;'>"
        for it in items:
            html += f"<li>{it}</li>"
        html += "</ul>"
        st.markdown(html, unsafe_allow_html=True)

    # Helper function to check if two gaps are semantically similar (duplicates)
    def are_gaps_similar(gap1, gap2):
        """Check if two gaps are essentially saying the same thing."""
        g1_lower = gap1.lower().strip()
        g2_lower = gap2.lower().strip()
        
        # Exact match (after normalization)
        if g1_lower == g2_lower:
            return True
        
        # Check for very similar wording (one is subset of other)
        if g1_lower in g2_lower or g2_lower in g1_lower:
            # But not if one is much shorter (might be too generic)
            if abs(len(g1_lower) - len(g2_lower)) < 20:
                return True
        
        # Extract key concepts from each gap
        def extract_key_concepts(text):
            concepts = set()
            # Key terms to look for
            keywords = [
                "conservative", "treatment", "therapy", "duration", "weeks", "months", 
                "three", "3", "minimum", "required", "specified", "detailed", "documentation",
                "acute", "chronic", "tear", "within", "clarity", "unclear",
                "physical examination", "exam", "rom", "range of motion", "strength",
                "functional", "limitation", "pain", "scale", "vas", "imaging", "mri"
            ]
            text_lower = text.lower()
            for kw in keywords:
                if kw in text_lower:
                    concepts.add(kw)
            return concepts
        
        concepts1 = extract_key_concepts(gap1)
        concepts2 = extract_key_concepts(gap2)
        
        # If they share most key concepts, they're similar
        if len(concepts1) > 0 and len(concepts2) > 0:
            overlap = len(concepts1 & concepts2)
            total_unique = len(concepts1 | concepts2)
            similarity_ratio = overlap / total_unique if total_unique > 0 else 0
            # If 70% or more concepts overlap, consider them similar
            if similarity_ratio >= 0.7:
                return True
        
        return False
    
    # Simplify gaps - show specific clinical documentation gaps only, with deduplication
    def _format_clinical_gaps(raw_gaps: set) -> list:
        if not raw_gaps:
            return []
        
        # Clean and filter gaps
        filtered_gaps = []
        for gap in raw_gaps:
            # Clean up the gap text
            cleaned_gap = _clean_gap_text(gap)
            if not cleaned_gap:
                continue
            
            gap_lower = cleaned_gap.lower()
            # Skip if it's policy-related or generic
            if not is_policy_related(cleaned_gap) and not is_generic_unhelpful(cleaned_gap) and is_clinical_gap(cleaned_gap):
                filtered_gaps.append(cleaned_gap)
        
        if not filtered_gaps:
            return []
        
        # Remove exact duplicates first
        unique_gaps = list(set(filtered_gaps))
        
        # Deduplicate similar gaps - keep the most specific one
        deduplicated = []
        used_indices = set()
        
        for i, gap1 in enumerate(unique_gaps):
            if i in used_indices:
                continue
            
            # Find all similar gaps
            similar_group = [gap1]
            for j, gap2 in enumerate(unique_gaps[i+1:], start=i+1):
                if j in used_indices:
                    continue
                if are_gaps_similar(gap1, gap2):
                    similar_group.append(gap2)
                    used_indices.add(j)
            
            # From the similar group, pick the best one:
            # 1. Prefer longer (more specific)
            # 2. Prefer ones with numbers/specifics (e.g., "3 months" vs "duration")
            # 3. Prefer ones that are clearer (not "unclear" or "insufficient")
            best_gap = max(similar_group, key=lambda g: (
                len(g),  # Longer is better
                sum(1 for word in g.lower().split() if word.isdigit() or word in ['three', 'six', 'minimum', 'required']),  # Has specifics
                -1 if any(kw in g.lower() for kw in ['unclear', 'insufficient', 'not specified', 'missing']) else 1  # Prefer positive statements
            ))
            
            deduplicated.append(best_gap)
            used_indices.add(i)
        
        # Sort by specificity (longer = more specific) and limit to top 15
        final_gaps = sorted(deduplicated, key=lambda x: len(x), reverse=True)[:15]
        
        return final_gaps

    # 1) Policy / guideline needed
    st.markdown("#### 📚 Policy / Guideline Needed (if any)")
    if policy_needed:
        policy_list = sorted(list(set(policy_needed)))
        _render_bullets(policy_list)
    else:
        st.info("No policy gaps detected.")

    # 2) CDI documentation gaps – show ONLY clinical documentation gaps
    st.markdown("#### 📝 CDI Documentation Gaps (Top Priorities)")
    formatted_gaps = _format_clinical_gaps(cdi_gaps)
    if formatted_gaps:
        _render_bullets(formatted_gaps)
    else:
        # Fallback: Try to extract from requirement_checklist one more time
        all_requirement_gaps = []
        for payer_key, payer_result in payer_results.items():
            if isinstance(payer_result, dict):
                procedure_results = payer_result.get("procedure_results", [])
            else:
                procedure_results = getattr(payer_result, "procedure_results", [])
            
            for proc_result in procedure_results:
                if not isinstance(proc_result, dict):
                    proc_result = {
                        "requirement_checklist": getattr(proc_result, "requirement_checklist", []),
                    }
                
                requirement_checklist = proc_result.get("requirement_checklist", [])
                if isinstance(requirement_checklist, list):
                    for req in requirement_checklist:
                        if isinstance(req, dict):
                            status = req.get("status", "").lower()
                            req_id = req.get("requirement_id", "").lower()
                            
                            # Skip ALL policy-related requirements
                            if "policy_availability" in req_id or "policy" in req_id:
                                continue
                            
                            if status in ["unmet", "unclear", "insufficient", "not met", "partially met"]:
                                missing = req.get("missing_to_meet", "")
                                if missing and missing.strip():
                                    missing_clean = missing.strip()
                                    # Only add if it's a clinical gap
                                    if is_clinical_gap(missing_clean) and not is_policy_related(missing_clean) and not is_generic_unhelpful(missing_clean):
                                        # Clean up the text
                                        cleaned = _clean_gap_text(missing_clean)
                                        if cleaned:
                                            # Check if this gap is already covered in related charts
                                            if not is_gap_covered_in_related_charts(cleaned):
                                                all_requirement_gaps.append(cleaned)
        
        if all_requirement_gaps:
            unique_gaps = sorted(list(set(all_requirement_gaps)), key=lambda x: len(x), reverse=True)[:15]
            _render_bullets(unique_gaps)
        else:
            st.info("✅ No clinical documentation gaps identified. Documentation appears complete for the evaluated requirements.")
    
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
    
    # Completion Guidance - Generate dynamically based on actual gaps found
    st.markdown("#### ✍️ Completion Guidance")
    
    # Generate guidance based on what gaps are actually present
    guidance_items = []
    
    # Get the formatted gaps from CDI Summary (already deduplicated and cleaned)
    formatted_gaps = _format_clinical_gaps(cdi_gaps)
    all_gaps_text = " ".join([g.lower() for g in formatted_gaps]) if formatted_gaps else ""
    
    # Also check checklist items
    has_conservative = len(checklist_items["🏃‍♂️ Conservative Treatment"]) > 0
    has_imaging = len(checklist_items["🏥 Imaging"]) > 0
    has_clinical = len(checklist_items["📊 Clinical Assessments"]) > 0
    has_functional = len(checklist_items["🧠 Functional Limitations"]) > 0
    
    # Combine all gap text for analysis
    cdi_gaps_lower = all_gaps_text
    
    # Generate specific guidance based on gaps found
    if has_conservative or any(kw in cdi_gaps_lower for kw in ["conservative", "treatment", "therapy", "pt"]):
        # Check if duration is mentioned
        if any(kw in cdi_gaps_lower for kw in ["duration", "weeks", "months", "3 months", "six months"]):
            guidance_items.append("Document conservative treatment with specific duration (e.g., '6 weeks', '3 months'), start/end dates, treatment type, frequency, and patient response/outcome")
        else:
            guidance_items.append("Document conservative treatment attempts including type (PT, medications, injections), dates, duration, frequency, and patient response/outcome")
    
    if has_functional or any(kw in cdi_gaps_lower for kw in ["functional", "score", "ases", "constant", "vas", "limitation"]):
        # Check what specific scores are needed
        if "ases" in cdi_gaps_lower:
            guidance_items.append("Include ASES (American Shoulder and Elbow Surgeons) score with date of assessment")
        if "constant" in cdi_gaps_lower:
            guidance_items.append("Include Constant-Murley score with date of assessment")
        if "vas" in cdi_gaps_lower or "pain" in cdi_gaps_lower:
            guidance_items.append("Document pain assessment using VAS (Visual Analog Scale) or NRS (Numeric Rating Scale) with baseline and current measurements")
        if not any(kw in cdi_gaps_lower for kw in ["ases", "constant", "vas"]):
            guidance_items.append("Include specific functional scores (e.g., ASES, Constant, VAS) with dates of assessment")
    
    if has_imaging or any(kw in cdi_gaps_lower for kw in ["imaging", "mri", "xray", "x-ray", "ct", "radiology"]):
        guidance_items.append("Attach all relevant imaging reports (MRI, X-ray, CT) with radiologist interpretations and specific findings that support the diagnosis")
    
    if has_clinical or any(kw in cdi_gaps_lower for kw in ["physical examination", "exam", "rom", "range of motion", "strength", "test"]):
        # Check what specific exam findings are needed
        if "rom" in cdi_gaps_lower or "range of motion" in cdi_gaps_lower:
            guidance_items.append("Document range of motion measurements (degrees) for affected and unaffected sides with specific values")
        if "strength" in cdi_gaps_lower:
            guidance_items.append("Document strength testing results using standardized grading system (e.g., 0-5 scale) with side-to-side comparison")
        if "impingement" in cdi_gaps_lower or "neer" in cdi_gaps_lower or "hawkins" in cdi_gaps_lower:
            guidance_items.append("Document results of specific physical examination tests (e.g., Neer Impingement Test, Hawkins-Kennedy Test) with positive/negative findings")
        if not any(kw in cdi_gaps_lower for kw in ["rom", "strength", "impingement"]):
            guidance_items.append("Document clinical findings with objective measurements (range of motion, strength, special tests)")
    
    # Check for other specific gaps
    if any(kw in cdi_gaps_lower for kw in ["acute", "chronic", "tear"]):
        guidance_items.append("Clarify timeline of condition (acute vs chronic) with specific dates or duration since onset")
    
    if any(kw in cdi_gaps_lower for kw in ["duration", "symptom", "timeframe"]) and not has_conservative:
        guidance_items.append("Document duration of symptoms and functional limitations with specific timeframes (e.g., '6 weeks', '3 months')")
    
    # If no specific guidance was generated, provide general guidance based on what's in checklist
    if not guidance_items:
        if checklist_items["🏃‍♂️ Conservative Treatment"] or checklist_items["🏥 Imaging"] or checklist_items["📊 Clinical Assessments"] or checklist_items["🧠 Functional Limitations"]:
            guidance_items.append("Review the missing documentation items above and add the specific clinical information to the medical chart")
        else:
            guidance_items.append("No specific documentation gaps identified. Review the requirement checklist below for detailed requirements.")
    
    # Limit to top 6 most relevant guidance items
    guidance_items = guidance_items[:6]
    
    if guidance_items:
        guidance_html = "<ul style='margin-top: 8px;'>"
        for item in guidance_items:
            guidance_html += f"<li>{item}</li>"
        guidance_html += "</ul>"
        st.markdown(guidance_html, unsafe_allow_html=True)
    else:
        st.info("No specific completion guidance available. Review the missing documentation checklist above.")
    
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
    # File name line removed (looks noisy, especially with temp file names / multiple uploads)
    
    # Error handling
    if error:
        st.error(f"❌ Processing Error: {error}")
        return
    
    # Multi-chart information display
    multi_chart_info = getattr(result, "multi_chart_info", None)
    if multi_chart_info:
        st.markdown("### 📁 Multi-Chart Processing")
        st.info(f"Processed {multi_chart_info.get('total_charts', 0)} chart(s) as a complete inpatient record")
        
        # Display list of all identified chart names
        all_chart_names = multi_chart_info.get("all_chart_names", [])
        if all_chart_names:
            st.markdown("#### 📋 List of All Identified Charts")
            chart_details = multi_chart_info.get("chart_details", {})
            
            # Create a formatted numbered list of charts with their types
            chart_list_items = []
            for idx, chart_name in enumerate(all_chart_names, 1):
                chart_detail = chart_details.get(chart_name, {})
                chart_type_info = chart_detail if isinstance(chart_detail, dict) else {}
                display_title = chart_type_info.get("display_title") or chart_type_info.get("chart_type", "Unknown").replace("_", " ").title()
                chart_list_items.append(f"{idx}. **{display_title}** ({chart_name})")
            
            if chart_list_items:
                # Display as vertical list
                for item in chart_list_items:
                    st.markdown(item)
            else:
                # Fallback: just show names
                for idx, name in enumerate(all_chart_names, 1):
                    st.markdown(f"{idx}. **{name}**")
        
        # Display patient matching information in dropdown
        same_patient = multi_chart_info.get("same_patient", False)
        same_patient_reason = multi_chart_info.get("same_patient_reason", "")
        patient_name = multi_chart_info.get("patient_name")
        patient_id = multi_chart_info.get("patient_id")
        
        if same_patient:
            st.markdown("#### ✅ Patient Matching")
            st.success(f"**All charts are from the same patient**")
            with st.expander("📋 View Patient Details", expanded=False):
                if patient_name:
                    st.write(f"**Patient Name:** {patient_name}")
                if patient_id:
                    st.write(f"**Patient ID:** {patient_id}")
                if same_patient_reason:
                    st.caption(f"*{same_patient_reason}*")
        else:
            st.markdown("#### ⚠️ Unmatched Patient data/records")
            st.warning(f"**Charts may be from different patients**")
            with st.expander("📋 View Detailed Information", expanded=False):
                if same_patient_reason:
                    st.write(same_patient_reason)
                if patient_name:
                    st.write(f"**Patient Name Found:** {patient_name}")
                if patient_id:
                    st.write(f"**Patient ID Found:** {patient_id}")
        
        # Display duplicate information in dropdown
        duplicates = multi_chart_info.get("duplicates", [])
        duplicate_reason = multi_chart_info.get("duplicate_reason", "")
        if duplicates:
            st.markdown("#### ⚠️ Duplicate Charts")
            st.warning(f"**Duplicate charts detected: {', '.join(duplicates)}**")
            with st.expander("📋 View Duplicate Details", expanded=False):
                if duplicate_reason:
                    st.write(duplicate_reason)
                st.write(f"**Duplicate Files:** {', '.join(duplicates)}")
        else:
            st.markdown("#### ✅ Duplicate Check")
            st.success("**No duplicate charts detected**")
        
    
    # Patient overview
    if extraction_data:
        patient_name = extraction_data.get("patient_name", "Unknown") or "Unknown"
        patient_age = extraction_data.get("patient_age", "Unknown") or "Unknown"
        chart_specialty = extraction_data.get("chart_specialty", "Unknown") or "Unknown"
        
        st.markdown("### 🧑‍⚕️ Patient Overview")
        st.markdown(
            """
            <style>
              .patient-kpi {
                border: 1px solid rgba(49, 51, 63, 0.12);
                border-radius: 10px;
                padding: 12px 14px;
                background: rgba(250, 250, 250, 0.6);
              }
              .patient-kpi .label {
                font-size: 0.85rem;
                color: rgba(49, 51, 63, 0.75);
                margin-bottom: 4px;
                font-weight: 600;
              }
              .patient-kpi .value {
                font-size: 1.35rem; /* smaller, standard-ish size */
                line-height: 1.2;
                font-weight: 700;
                color: rgba(49, 51, 63, 0.95);
                word-break: break-word;
              }
            </style>
            """,
            unsafe_allow_html=True,
        )
        overview_col1, overview_col2, overview_col3 = st.columns(3)
        with overview_col1:
            st.markdown(
                f"""
                <div class="patient-kpi">
                  <div class="label">Patient Name</div>
                  <div class="value">{patient_name}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with overview_col2:
            st.markdown(
                f"""
                <div class="patient-kpi">
                  <div class="label">Patient Age</div>
                  <div class="value">{patient_age}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with overview_col3:
            st.markdown(
                f"""
                <div class="patient-kpi">
                  <div class="label">Chart Specialty</div>
                  <div class="value">{chart_specialty}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    
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
        st.markdown(
            """
            <style>
              .kpi-grid { margin-top: 0.25rem; }
              .kpi-card {
                border: 1px solid rgba(49, 51, 63, 0.12);
                border-radius: 10px;
                padding: 10px 12px;
                background: rgba(250, 250, 250, 0.6);
              }
              .kpi-card .label {
                font-size: 0.85rem;
                color: rgba(49, 51, 63, 0.75);
                margin-bottom: 2px;
                font-weight: 600;
              }
              .kpi-card .value {
                font-size: 1.15rem; /* consistent, not oversized like st.metric */
                line-height: 1.2;
                font-weight: 700;
                color: rgba(49, 51, 63, 0.95);
                word-break: break-word;
              }
              .small-section-title {
                font-size: 1.05rem;
                font-weight: 700;
                margin: 0.25rem 0 0.5rem 0;
              }
            </style>
            """,
            unsafe_allow_html=True,
        )

        overall_col1, overall_col2, overall_col3 = st.columns(3)
        with overall_col1:
            st.markdown(
                f"""
                <div class="kpi-card">
                  <div class="label">Overall Sufficient %</div>
                  <div class="value">{_format_pct(overall_summary.get("sufficient_percentage", 0.0))}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with overall_col2:
            st.markdown(
                f"""
                <div class="kpi-card">
                  <div class="label">Overall Insufficient %</div>
                  <div class="value">{_format_pct(overall_summary.get("insufficient_percentage", 0.0))}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with overall_col3:
            st.markdown(
                f"""
                <div class="kpi-card">
                  <div class="label">Procedures Evaluated</div>
                  <div class="value">{overall_summary.get("total_procedures", 0)}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        
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
    
    st.markdown("---")
    
    # View mode selector - Three buttons with different colors + persistent "active" highlight
    # We derive the active state from st.session_state.view_mode (more reliable than click events).
    current_view_mode = st.session_state.get("view_mode", "📋 CDI Recommendations")
    st.markdown(
        f"""
        <script>
        (function() {{
            const ACTIVE_VIEW_MODE = {json.dumps(current_view_mode)};
            const ACTIVE_OUTLINE = '0 0 0 4px rgba(91, 101, 220, 0.45), 0 10px 18px rgba(0,0,0,0.18)';

            function applyBaseStyle(button, bg, fg, hoverBg, baseShadow) {{
                button.style.cssText =
                    'background-color: ' + bg + ' !important;' +
                    'color: ' + fg + ' !important;' +
                    'border: 0 !important;' +
                    'padding: 1.05rem 1.6rem !important;' +
                    'font-weight: 950 !important;' +
                    'font-size: 18px !important;' +
                    'border-radius: 12px !important;' +
                    'width: 100% !important;' +
                    'box-shadow: ' + baseShadow + ' !important;' +
                    'text-transform: uppercase !important;' +
                    'letter-spacing: 0.7px !important;' +
                    'transition: all 0.2s ease !important;';

                // Ensure we don't stack listeners on rerenders
                if (!button.dataset.vmStyled) {{
                    button.addEventListener('mouseenter', function() {{
                        this.style.backgroundColor = hoverBg;
                        this.style.transform = 'translateY(-2px)';
                    }});
                    button.addEventListener('mouseleave', function() {{
                        this.style.backgroundColor = bg;
                        this.style.transform = 'translateY(0)';
                    }});
                    button.dataset.vmStyled = '1';
                }}
            }}

            function setActive(button, isActive) {{
                if (isActive) {{
                    button.style.filter = 'none';
                    button.style.opacity = '1';
                    button.style.boxShadow = ACTIVE_OUTLINE;
                    button.style.transform = 'translateY(-1px)';
                }} else {{
                    button.style.opacity = '0.75';
                    button.style.filter = 'saturate(0.9)';
                }}
            }}

            function styleViewModeButtons() {{
                const buttons = document.querySelectorAll('button');
                buttons.forEach(function(button) {{
                    const text = (button.textContent || '').trim();
                    if (text === 'CDI Recommendations') {{
                        applyBaseStyle(
                            button,
                            '#DC3545',
                            'white',
                            '#C82333',
                            '0 4px 8px rgba(220, 53, 69, 0.30)'
                        );
                        setActive(button, ACTIVE_VIEW_MODE.includes('CDI Recommendations'));
                    }} else if (text === 'Cross-Payer Dashboard') {{
                        applyBaseStyle(
                            button,
                            '#28A745',
                            'white',
                            '#218838',
                            '0 4px 8px rgba(40, 167, 69, 0.30)'
                        );
                        setActive(button, ACTIVE_VIEW_MODE.includes('Cross-Payer Dashboard'));
                    }} else if (text === 'Medical Chart Improvement') {{
                        applyBaseStyle(
                            button,
                            '#FFC107',
                            '#000000',
                            '#E0A800',
                            '0 4px 8px rgba(255, 193, 7, 0.30)'
                        );
                        setActive(button, ACTIVE_VIEW_MODE.includes('Medical Chart Improvement'));
                    }}
                }});
            }}

            styleViewModeButtons();
            setTimeout(styleViewModeButtons, 100);
            setTimeout(styleViewModeButtons, 500);

            const observer = new MutationObserver(styleViewModeButtons);
            observer.observe(document.body, {{ childList: true, subtree: true }});
        }})();
        </script>
        """,
        unsafe_allow_html=True,
    )
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        button_cdi = st.button("CDI Recommendations", key="btn_cdi", use_container_width=True)
        if button_cdi:
            st.session_state.view_mode = "📋 CDI Recommendations"
            st.rerun()
    
    with col2:
        button_dashboard = st.button("Cross-Payer Dashboard", key="btn_dashboard", use_container_width=True)
        if button_dashboard:
            st.session_state.view_mode = "📊 Cross-Payer Dashboard"
            st.rerun()
    
    with col3:
        button_improvement = st.button("Medical Chart Improvement", key="btn_improvement", use_container_width=True)
        if button_improvement:
            st.session_state.view_mode = "✨ Medical Chart Improvement"
            st.rerun()
    
    # Get current view mode from session state
    view_mode = st.session_state.view_mode
    
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

        # Other Chart Findings - Display before Overall Metrics
        multi_chart_info = getattr(result, "multi_chart_info", None)
        if multi_chart_info:
            other_charts_info = multi_chart_info.get("other_charts_info", {})
            operative_chart_name = multi_chart_info.get("operative_chart", "N/A")
            
            if other_charts_info:
                st.markdown("---")
                st.markdown("### 📋 Related Given Charts")
                st.info(f"ℹ️ **CDI Evaluation:** Used operative chart (**{operative_chart_name}**) for compliance evaluation. Information from related charts below was cross-referenced to avoid false gap identification.")
                
                for chart_file, chart_info in other_charts_info.items():
                    # Use display_title if available, otherwise fallback to formatted chart_type
                    chart_title = chart_info.get("display_title") or chart_info.get("chart_type", "unknown").replace("_", " ").title()
                    chart_file_path = chart_info.get("file_path", chart_file)
                    file_display_name = os.path.basename(chart_file_path)
                    
                    # Display chart title as attractive heading in bold accent blue
                    st.markdown(f'<h4 style="color: {ACCENT_BLUE}; font-weight: bold; margin-top: 1rem; margin-bottom: 0.5rem;">📄 {chart_title}</h4>', unsafe_allow_html=True)
                    
                    # Dropdown/expander for detail information
                    with st.expander("View Details", expanded=False):
                        # Show file name in details
                        st.write(f"**File Name:** {file_display_name}")
                        st.write(f"**Chart Type:** {chart_title}")
                        if chart_info.get("chart_type_confidence"):
                            st.write(f"**Confidence:** {chart_info.get('chart_type_confidence', 'unknown').title()}")
                        st.markdown("---")
                        
                        # Summary Section
                        if chart_info.get("summary"):
                            st.markdown("**📝 Summary:**")
                            st.write(chart_info["summary"])
                            st.markdown("")
                        
                        # Diagnosis Section
                        diagnosis = chart_info.get("diagnosis", [])
                        
                        if diagnosis:
                            st.markdown("**🏥 Diagnosis:**")
                            if isinstance(diagnosis, list):
                                for diag in diagnosis:
                                    st.markdown(f"• {diag}")
                            else:
                                st.markdown(f"• {diagnosis}")
                            st.markdown("")
                        
                        # Important Tests Section
                        tests = chart_info.get("tests", [])
                        reports = chart_info.get("reports", [])
                        if tests or reports:
                            st.markdown("**🧪 Important Tests & Studies:**")
                            if tests:
                                if isinstance(tests, list):
                                    for test in tests:
                                        st.markdown(f"• {test}")
                                else:
                                    st.markdown(f"• {tests}")
                            if reports:
                                st.markdown("**Test Reports:**")
                                if isinstance(reports, list):
                                    for report in reports[:10]:  # Limit to first 10 reports
                                        st.markdown(f"• {report}")
                                    if len(reports) > 10:
                                        st.caption(f"... and {len(reports) - 10} more reports")
                                else:
                                    st.markdown(f"• {reports}")
                            st.markdown("")
                        
                        # Medications Section
                        medications = chart_info.get("medications", [])
                        if medications:
                            st.markdown("**💊 Medications:**")
                            if isinstance(medications, list):
                                for med in medications:
                                    st.markdown(f"• {med}")
                            else:
                                st.markdown(f"• {medications}")
                            st.markdown("")
                        
                        # Conservative Treatment Section
                        conservative_treatment = chart_info.get("conservative_treatment", {})
                        if conservative_treatment:
                            st.markdown("**🏃 Conservative Treatment:**")
                            if isinstance(conservative_treatment, dict):
                                for key, value in conservative_treatment.items():
                                    if value:
                                        st.markdown(f"• **{key.replace('_', ' ').title()}:** {value}")
                            else:
                                st.markdown(f"• {conservative_treatment}")
                            st.markdown("")
                        
                        # Physical Examination Section
                        physical_exam = chart_info.get("physical_exam", {})
                        if physical_exam:
                            st.markdown("**🔍 Physical Examination:**")
                            if isinstance(physical_exam, dict):
                                for key, value in physical_exam.items():
                                    if value:
                                        st.markdown(f"• **{key.replace('_', ' ').title()}:** {value}")
                            else:
                                st.markdown(f"• {physical_exam}")
                            st.markdown("")

                        # Functional Limitations Section
                        functional_limitations = chart_info.get("functional_limitations", {})
                        if functional_limitations:
                            st.markdown("**⚠️ Functional Limitations:**")
                            if isinstance(functional_limitations, dict):
                                for key, value in functional_limitations.items():
                                    if value:
                                        st.markdown(f"• **{key.replace('_', ' ').title()}:** {value}")
                            else:
                                st.markdown(f"• {functional_limitations}")
                            st.markdown("")
                        
                        # Risk Assessment Section
                        risk_assessment = chart_info.get("risk_assessment", "")
                        if risk_assessment:
                            st.markdown("**⚡ Risk Assessment:**")
                            st.markdown(f"• {risk_assessment}")
                            st.markdown("")
                        
                        # Allergies Section
                        allergies = chart_info.get("allergies", [])
                        if allergies:
                            st.markdown("**🚫 Allergies:**")
                            if isinstance(allergies, list):
                                for allergy in allergies:
                                    st.markdown(f"• {allergy}")
                            else:
                                st.markdown(f"• {allergies}")
                            st.markdown("")
                        
                        # Imaging Section
                        imaging = chart_info.get("imaging", [])
                        if imaging:
                            st.markdown("**📸 Imaging Studies:**")
                            if isinstance(imaging, list):
                                for img in imaging:
                                    st.markdown(f"• {img}")
                            else:
                                st.markdown(f"• {imaging}")
                            st.markdown("")

        # Overall Metrics + Execution Times (moved here after "Related Given Charts")
        st.markdown("---")
        st.markdown('<div class="small-section-title">📈 Overall Metrics</div>', unsafe_allow_html=True)

        total_tokens = total_usage.input_tokens + total_usage.output_tokens
        payers_processed = len([p for p in payer_results.values() if not p.get("error")])
        total_time = sum(execution_times.values()) if execution_times else 0

        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.markdown(
                f"""
                <div class="kpi-card">
                  <div class="label">Total Tokens</div>
                  <div class="value">{total_tokens:,}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with m2:
            st.markdown(
                f"""
                <div class="kpi-card">
                  <div class="label">Total Cost</div>
                  <div class="value">${total_cost:.6f}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with m3:
            st.markdown(
                f"""
                <div class="kpi-card">
                  <div class="label">Payers Processed</div>
                  <div class="value">{payers_processed}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with m4:
            st.markdown(
                f"""
                <div class="kpi-card">
                  <div class="label">Total Time</div>
                  <div class="value">{total_time:.2f}s</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        if execution_times:
            st.markdown("---")
            st.markdown('<div class="small-section-title">⏱️ Execution Times</div>', unsafe_allow_html=True)

            cols = st.columns(len(execution_times))
            for col, (payer_key, exec_time) in zip(cols, execution_times.items()):
                payer_name = Config.PAYER_CONFIG[payer_key]["name"]
                with col:
                    st.markdown(
                        f"""
                        <div class="kpi-card">
                          <div class="label">{payer_name}</div>
                          <div class="value">{exec_time:.2f}s</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
    
    else:  # Cross-Payer Dashboard
        display_cross_payer_dashboard(result)


def main():
    """Main Streamlit application."""
    # Initialize session state
    initialize_session_state()
    
    # Check password before showing any app content
    if not check_password():
        st.stop()  # Stop execution if password is incorrect
    
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
    display_available_payers()
    
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
    
    # Single uploader; branch flow based on count (1 => single chart, >1 => multichart)
    uploaded_files = st.file_uploader(
        "Choose medical chart file(s) (PDF, TXT, or DOCX)",
        type=["pdf", "txt", "docx"],
        accept_multiple_files=True,
        help="Upload 1 file for single-chart analysis, or multiple related charts for complete-record (multichart) analysis.",
    )

    if uploaded_files and len(uploaded_files) > 0:
        is_multi = len(uploaded_files) > 1
        button_label = " Process All Charts" if is_multi else " Process Chart"

        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button(button_label, type="primary", width="stretch"):
                if not is_multi:
                    uploaded_file = uploaded_files[0]
                    with tempfile.NamedTemporaryFile(
                        delete=False, suffix=Path(uploaded_file.name).suffix
                    ) as tmp_file:
                        tmp_file.write(uploaded_file.getvalue())
                        tmp_file_path = tmp_file.name

                    try:
                        with st.spinner("🔄 Processing medical chart... This may take a minute."):
                            progress_bar = st.progress(0)
                            progress_bar.progress(10)

                            result = st.session_state.cdi_system.process_file(tmp_file_path)

                            progress_bar.progress(100)
                            st.session_state.processing_result = result
                            st.session_state.file_processed = True
                            # Clear previous chart improvement results when processing new file
                            st.session_state.improved_chart_result = None
                            st.session_state.original_chart_text = None
                            st.session_state.user_input_fields = {}

                        st.markdown(
                            '<div style="background-color: #10b981; color: white; padding: 12px 20px; border-radius: 8px; font-weight: bold; font-size: 16px; text-align: center; margin: 10px 0;">Processing Done</div>',
                            unsafe_allow_html=True,
                        )
                    except Exception as e:
                        st.error(f"❌ Error processing file: {e}")
                    finally:
                        try:
                            os.unlink(tmp_file_path)
                        except Exception:
                            pass
                else:
                    temp_files = []
                    try:
                        for uploaded_file in uploaded_files:
                            tmp_file = tempfile.NamedTemporaryFile(
                                delete=False, suffix=Path(uploaded_file.name).suffix
                            )
                            tmp_file.write(uploaded_file.getvalue())
                            tmp_file.close()
                            temp_files.append(tmp_file.name)

                        with st.spinner(
                            "🔄 Processing multiple charts as complete record... This may take several minutes."
                        ):
                            progress_bar = st.progress(0)
                            progress_bar.progress(10)

                            result = st.session_state.cdi_system.process_multiple_charts(
                                temp_files
                            )

                            progress_bar.progress(100)
                            st.session_state.processing_result = result
                            st.session_state.file_processed = True
                            # Clear previous chart improvement results when processing new file
                            st.session_state.improved_chart_result = None
                            st.session_state.original_chart_text = None
                            st.session_state.user_input_fields = {}

                        st.markdown(
                            '<div style="background-color: #10b981; color: white; padding: 12px 20px; border-radius: 8px; font-weight: bold; font-size: 16px; text-align: center; margin: 10px 0;">Processing Done</div>',
                            unsafe_allow_html=True,
                        )
                    except Exception as e:
                        st.error(f"❌ Error processing files: {e}")
                    finally:
                        for tmp_path in temp_files:
                            try:
                                os.unlink(tmp_path)
                            except Exception:
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
            label=" Download Results (JSON)",
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
