#!/usr/bin/env python3
"""
Multi-File Comparison Dashboard for Multi-Payer CDI Compliance Checker.

Batch processing and comparative analysis across multiple medical charts.
"""

import sys
import json
import os
from pathlib import Path
import tempfile
import streamlit as st
from datetime import datetime
import pandas as pd
from typing import List, Dict, Any
import concurrent.futures

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from multi_payer_cdi.core import MultiPayerCDI
from multi_payer_cdi.config import Config
from multi_payer_cdi.file_processor import FileProcessor


# Page configuration
st.set_page_config(
    page_title="Multi-File CDI Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1E88E5;
        text-align: center;
        padding: 1rem 0;
    }
    .metric-card {
        background-color: #ffffff;
        padding: 1.5rem;
        border-radius: 0.5rem;
        border: 2px solid #e0e0e0;
        text-align: center;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .comparison-table {
        font-size: 0.9rem;
    }
    .success-rate-high {
        background-color: #c8e6c9;
        padding: 0.25rem 0.5rem;
        border-radius: 0.25rem;
        font-weight: bold;
    }
    .success-rate-medium {
        background-color: #fff9c4;
        padding: 0.25rem 0.5rem;
        border-radius: 0.25rem;
        font-weight: bold;
    }
    .success-rate-low {
        background-color: #ffcdd2;
        padding: 0.25rem 0.5rem;
        border-radius: 0.25rem;
        font-weight: bold;
    }
    .file-card {
        background-color: #f8f9fa;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 0.5rem 0;
        border-left: 4px solid #1E88E5;
    }
</style>
""", unsafe_allow_html=True)


def initialize_session_state():
    """Initialize session state variables."""
    if 'cdi_system' not in st.session_state:
        st.session_state.cdi_system = None
    if 'batch_results' not in st.session_state:
        st.session_state.batch_results = []
    if 'processing_complete' not in st.session_state:
        st.session_state.processing_complete = False
    if 'current_tab' not in st.session_state:
        st.session_state.current_tab = "upload"


def initialize_cdi_system():
    """Initialize the CDI system."""
    try:
        if st.session_state.cdi_system is None:
            with st.spinner("🔄 Initializing Multi-Payer CDI system..."):
                st.session_state.cdi_system = MultiPayerCDI()
        return True
    except Exception as e:
        st.error(f"❌ Failed to initialize CDI system: {e}")
        return False


def process_single_file_for_batch(cdi_system: MultiPayerCDI, file_path: str, file_name: str) -> Dict[str, Any]:
    """Process a single file and return results."""
    try:
        result = cdi_system.process_file(file_path)
        return {
            "file_name": file_name,
            "status": "success",
            "result": result
        }
    except Exception as e:
        return {
            "file_name": file_name,
            "status": "error",
            "error": str(e)
        }


def process_batch_files(uploaded_files):
    """Process multiple files in parallel."""
    results = []
    temp_files = []
    
    try:
        # Save uploaded files to temp location
        for uploaded_file in uploaded_files:
            tmp_file = tempfile.NamedTemporaryFile(
                delete=False, 
                suffix=Path(uploaded_file.name).suffix
            )
            tmp_file.write(uploaded_file.getvalue())
            tmp_file.close()
            temp_files.append((tmp_file.name, uploaded_file.name))
        
        # Create progress tracking
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # Process files
        total_files = len(temp_files)
        for idx, (tmp_path, original_name) in enumerate(temp_files):
            status_text.text(f"Processing {original_name}... ({idx + 1}/{total_files})")
            
            result = process_single_file_for_batch(
                st.session_state.cdi_system, 
                tmp_path, 
                original_name
            )
            results.append(result)
            
            progress_bar.progress((idx + 1) / total_files)
        
        status_text.text("✅ All files processed!")
        
    finally:
        # Cleanup temp files
        for tmp_path, _ in temp_files:
            try:
                os.unlink(tmp_path)
            except:
                pass
    
    return results


def calculate_aggregate_metrics(batch_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Calculate aggregate metrics from batch results."""
    metrics = {
        "total_files": len(batch_results),
        "successful_files": 0,
        "failed_files": 0,
        "total_cost": 0.0,
        "total_tokens": 0,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_procedures": 0,
        "avg_processing_time": 0.0,
        "payer_stats": {},
        "procedure_compliance": {
            "sufficient": 0,
            "insufficient": 0,
            "not_applicable": 0
        }
    }
    
    processing_times = []
    
    for item in batch_results:
        if item["status"] == "success":
            metrics["successful_files"] += 1
            result = item["result"]
            
            # Token and cost metrics
            metrics["total_cost"] += result.total_cost
            metrics["total_input_tokens"] += result.total_usage.input_tokens
            metrics["total_output_tokens"] += result.total_usage.output_tokens
            metrics["total_tokens"] += (result.total_usage.input_tokens + result.total_usage.output_tokens)
            
            # Processing time
            if result.execution_times:
                processing_times.append(sum(result.execution_times.values()))
            
            # Payer-specific stats
            for payer_key, payer_result in result.payer_results.items():
                if payer_key not in metrics["payer_stats"]:
                    metrics["payer_stats"][payer_key] = {
                        "name": payer_result.get("payer_name", payer_key),
                        "total_procedures": 0,
                        "sufficient": 0,
                        "insufficient": 0,
                        "total_cost": 0.0
                    }
                
                payer_metrics = metrics["payer_stats"][payer_key]
                
                # Process procedure results
                for proc_result in payer_result.get("procedure_results", []):
                    metrics["total_procedures"] += 1
                    payer_metrics["total_procedures"] += 1
                    
                    decision = proc_result.get("decision", "").lower()
                    # Only count Sufficient/Insufficient, exclude "Not Applicable" or "No Guidelines"
                    if "sufficient" in decision and "insufficient" not in decision:
                        metrics["procedure_compliance"]["sufficient"] += 1
                        payer_metrics["sufficient"] += 1
                    elif "insufficient" in decision:
                        metrics["procedure_compliance"]["insufficient"] += 1
                        payer_metrics["insufficient"] += 1
                    # Skip "Not Applicable" and "No Guidelines Available" cases
                
                # Payer cost
                usage = payer_result.get("usage", {})
                if hasattr(usage, "total_cost"):
                    payer_metrics["total_cost"] += usage.total_cost
                elif isinstance(usage, dict):
                    payer_metrics["total_cost"] += usage.get("total_cost", 0.0)
        else:
            metrics["failed_files"] += 1
    
    # Calculate averages
    if processing_times:
        metrics["avg_processing_time"] = sum(processing_times) / len(processing_times)
    
    return metrics


def display_overview_metrics(metrics: Dict[str, Any]):
    """Display aggregate metrics overview."""
    st.markdown("### 📊 Batch Processing Overview")
    
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric("Total Files", metrics["total_files"])
        st.metric("✅ Success", metrics["successful_files"])
    
    with col2:
        st.metric("Total Procedures", metrics["total_procedures"])
        st.metric("❌ Failed", metrics["failed_files"])
    
    with col3:
        st.metric("Total Tokens", f"{metrics['total_tokens']:,}")
        st.metric("Input", f"{metrics['total_input_tokens']:,}")
    
    with col4:
        st.metric("Total Cost", f"${metrics['total_cost']:.6f}")
        avg_cost = metrics['total_cost'] / metrics['total_files'] if metrics['total_files'] > 0 else 0
        st.metric("Avg/File", f"${avg_cost:.6f}")
    
    with col5:
        st.metric("Avg Time", f"{metrics['avg_processing_time']:.2f}s")
        st.metric("Output", f"{metrics['total_output_tokens']:,}")


def display_compliance_summary(metrics: Dict[str, Any]):
    """Display compliance summary with charts."""
    st.markdown("### 🎯 Compliance Summary")
    
    compliance = metrics["procedure_compliance"]
    total = sum(compliance.values())
    
    if total > 0:
        col1, col2 = st.columns(2)
        
        with col1:
            # Compliance breakdown
            st.markdown("#### Decision Distribution")
            
            sufficient_pct = (compliance["sufficient"] / total) * 100
            insufficient_pct = (compliance["insufficient"] / total) * 100
            
            df_compliance = pd.DataFrame({
                "Decision": ["Sufficient", "Insufficient"],
                "Count": [compliance["sufficient"], compliance["insufficient"]],
                "Percentage": [sufficient_pct, insufficient_pct]
            })
            
            st.dataframe(df_compliance, use_container_width=True)
        
        with col2:
            # Visual bars
            st.markdown("#### Compliance Rate")
            
            st.markdown(f"""
            <div style='margin: 1rem 0;'>
                <div style='background-color: #c8e6c9; padding: 0.5rem; border-radius: 0.25rem; margin: 0.5rem 0;'>
                    ✅ Sufficient: {compliance["sufficient"]} ({sufficient_pct:.1f}%)
                </div>
                <div style='background-color: #ffcdd2; padding: 0.5rem; border-radius: 0.25rem; margin: 0.5rem 0;'>
                    ❌ Insufficient: {compliance["insufficient"]} ({insufficient_pct:.1f}%)
                </div>
                <div style='background-color: #fff9c4; padding: 0.5rem; border-radius: 0.25rem; margin: 0.5rem 0;'>
                </div>
            </div>
            """, unsafe_allow_html=True)


def display_payer_comparison(metrics: Dict[str, Any]):
    """Display payer-by-payer comparison."""
    st.markdown("### 🏥 Payer Comparison")
    
    if not metrics["payer_stats"]:
        st.info("No payer data available")
        return
    
    # Create comparison table
    payer_data = []
    for payer_key, stats in metrics["payer_stats"].items():
        total_decisions = stats["sufficient"] + stats["insufficient"]
        compliance_rate = (stats["sufficient"] / total_decisions * 100) if total_decisions > 0 else 0
        
        payer_data.append({
            "Payer": stats["name"],
            "Procedures": stats["total_procedures"],
            "✅ Sufficient": stats["sufficient"],
            "❌ Insufficient": stats["insufficient"],
            "Compliance %": f"{compliance_rate:.1f}%",
            "Total Cost": f"${stats['total_cost']:.6f}"
        })
    
    df_payers = pd.DataFrame(payer_data)
    st.dataframe(df_payers, use_container_width=True)
    
    # Detailed payer tabs
    st.markdown("#### Detailed Payer Analysis")
    payer_tabs = st.tabs([stats["name"] for stats in metrics["payer_stats"].values()])
    
    for tab, (payer_key, stats) in zip(payer_tabs, metrics["payer_stats"].items()):
        with tab:
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Total Procedures", stats["total_procedures"])
            with col2:
                st.metric("Sufficient", stats["sufficient"])
            with col3:
                st.metric("Insufficient", stats["insufficient"])
            with col4:
                st.metric("Cost", f"${stats['total_cost']:.6f}")
            
            # Compliance rate for this payer
            total = stats["sufficient"] + stats["insufficient"]
            if total > 0:
                rate = (stats["sufficient"] / total) * 100
                
                if rate >= 70:
                    color = "#c8e6c9"
                    status = "Good"
                elif rate >= 40:
                    color = "#fff9c4"
                    status = "Fair"
                else:
                    color = "#ffcdd2"
                    status = "Needs Improvement"
                
                st.markdown(f"""
                <div style='background-color: {color}; padding: 1rem; border-radius: 0.5rem; margin: 1rem 0;'>
                    <strong>Compliance Rate:</strong> {rate:.1f}% ({status})
                </div>
                """, unsafe_allow_html=True)


def display_file_by_file_results(batch_results: List[Dict[str, Any]]):
    """Display detailed results for each file."""
    st.markdown("### 📄 File-by-File Results")
    
    for idx, item in enumerate(batch_results, 1):
        file_name = item["file_name"]
        status = item["status"]
        
        with st.expander(f"📋 File {idx}: {file_name}", expanded=False):
            if status == "error":
                st.error(f"❌ Error: {item.get('error', 'Unknown error')}")
                continue
            
            result = item["result"]
            
            # File metrics
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                total_tokens = result.total_usage.input_tokens + result.total_usage.output_tokens
                st.metric("Tokens", f"{total_tokens:,}")
            
            with col2:
                st.metric("Cost", f"${result.total_cost:.6f}")
            
            with col3:
                procedures_count = len(result.extraction_data.get("procedure", []))
                st.metric("Procedures", procedures_count)
            
            with col4:
                total_time = sum(result.execution_times.values()) if result.execution_times else 0
                st.metric("Time", f"{total_time:.2f}s")
            
            # Extraction data
            st.markdown("**Extraction:**")
            extraction = result.extraction_data
            st.markdown(f"- **CPT Codes:** {', '.join(extraction.get('cpt', [])) or 'None'}")
            st.markdown(f"- **Procedures:** {', '.join(extraction.get('procedure', [])) or 'None'}")
            
            # Payer results summary
            st.markdown("**Payer Results:**")
            for payer_key, payer_result in result.payer_results.items():
                payer_name = payer_result.get("payer_name", payer_key)
                proc_results = payer_result.get("procedure_results", [])
                
                sufficient = sum(1 for p in proc_results if "sufficient" in p.get("decision", "").lower())
                insufficient = sum(1 for p in proc_results if "insufficient" in p.get("decision", "").lower())
                
                st.markdown(f"- **{payer_name}:** {sufficient} Sufficient, {insufficient} Insufficient")
            
            # PDF Evidence Summary
            st.markdown("**📄 Evidence References:**")
            evidence_count = 0
            payer_refs_count = 0
            all_payer_refs = []
            
            for payer_key, payer_result in result.payer_results.items():
                proc_results = payer_result.get("procedure_results", [])
                for proc in proc_results:
                    sources = proc.get("sources", [])
                    for source in sources:
                        if source.get("pdf_evidence"):
                            evidence_count += 1
                        inline_evidence = source.get("inline_evidence", [])
                        if inline_evidence:
                            all_payer_refs.extend(inline_evidence)
            
            payer_refs_count = len(set(all_payer_refs))
            
            if evidence_count > 0 or payer_refs_count > 0:
                summary_parts = []
                if payer_refs_count > 0:
                    summary_parts.append(f"{payer_refs_count} payer reference(s)")
                if evidence_count > 0:
                    summary_parts.append(f"{evidence_count} PDF evidence item(s)")
                st.info(f"✅ {' and '.join(summary_parts)} found")
                
                # Show sample payer references
                if all_payer_refs:
                    unique_refs = sorted(set(all_payer_refs))[:3]
                    st.caption(f"Sample references: {', '.join(unique_refs)}")
            else:
                st.info("No evidence references available")


def export_to_csv(batch_results: List[Dict[str, Any]]) -> str:
    """Export batch results to CSV format with PDF evidence."""
    rows = []
    
    for item in batch_results:
        if item["status"] != "success":
            continue
        
        result = item["result"]
        file_name = item["file_name"]
        
        for payer_key, payer_result in result.payer_results.items():
            payer_name = payer_result.get("payer_name", payer_key)
            
            for proc_result in payer_result.get("procedure_results", []):
                # Collect PDF evidence and payer references
                pdf_references = []
                payer_references = []
                sources = proc_result.get("sources", [])
                for source in sources:
                    # PDF evidence
                    pdf_evidence = source.get("pdf_evidence", {})
                    if pdf_evidence:
                        pdf_file = pdf_evidence.get("pdf_file", "")
                        page = pdf_evidence.get("page", "")
                        if pdf_file:
                            ref = pdf_file
                            if page:
                                ref += f" (Page {page})"
                            pdf_references.append(ref)
                    
                    # Payer inline references
                    inline_evidence = source.get("inline_evidence", [])
                    if inline_evidence:
                        payer_references.extend(inline_evidence)
                
                # Get unique payer references
                unique_payer_refs = sorted(set(payer_references))
                
                # Parse page numbers from references
                import re
                page_numbers = set()
                line_numbers = []
                for ref in unique_payer_refs:
                    match = re.search(r'pg\s+no:\s*(\d+).*?L(\d+(?:-L\d+)?)', ref)
                    if match:
                        page_numbers.add(match.group(1))
                        line_numbers.append(match.group(2))
                
                rows.append({
                    "File": file_name,
                    "Payer": payer_name,
                    "Procedure": proc_result.get("procedure_evaluated", ""),
                    "Decision": proc_result.get("decision", ""),
                    "Policy": proc_result.get("policy_name", ""),
                    "Primary Reasons": "; ".join(proc_result.get("primary_reasons", [])),
                    "Evidence References": ", ".join(unique_payer_refs) if unique_payer_refs else "None",
                    "Reference Count": len(unique_payer_refs),
                    "Guideline Pages": ", ".join(sorted(page_numbers)) if page_numbers else "N/A",
                    "Guideline Lines": ", ".join(line_numbers) if line_numbers else "N/A",
                    "PDF Evidence": "; ".join(pdf_references) if pdf_references else "None",
                    "PDF Count": len(pdf_references)
                })
    
    df = pd.DataFrame(rows)
    return df.to_csv(index=False)


def export_to_json(batch_results: List[Dict[str, Any]]) -> str:
    """Export batch results to JSON format."""
    export_data = []
    
    for item in batch_results:
        if item["status"] == "success":
            export_data.append({
                "file_name": item["file_name"],
                "result": item["result"].__dict__ if hasattr(item["result"], "__dict__") else item["result"]
            })
        else:
            export_data.append({
                "file_name": item["file_name"],
                "error": item.get("error", "Unknown error")
            })
    
    return json.dumps(export_data, indent=2, default=str, ensure_ascii=False)


def display_sidebar():
    """Display sidebar information."""
    st.sidebar.markdown("### 📊 Dashboard Info")
    
    if st.session_state.cdi_system:
        info = st.session_state.cdi_system.get_system_info()
        
        st.sidebar.markdown(f"**Version:** {info['version']}")
        st.sidebar.markdown(f"**Cache:** {'✅' if info['cache_enabled'] else '❌'}")
        st.sidebar.markdown(f"**OpenSearch:** {'✅' if info['opensearch_connected'] else '❌'}")
        
        st.sidebar.markdown("**Configured Payers:**")
        for payer in info['configured_payers']:
            payer_config = Config.PAYER_CONFIG[payer]
            st.sidebar.markdown(f"- {payer_config['name']}")
        
        # Cache stats
        st.sidebar.markdown("---")
        st.sidebar.markdown("### 💾 Cache Stats")
        cache_stats = st.session_state.cdi_system.cache_manager.cache_stats
        st.sidebar.metric("Hit Rate", f"{cache_stats.get_hit_rate():.1f}%")
        st.sidebar.metric("Total Savings", f"${cache_stats.total_savings_usd:.6f}")


def main():
    """Main dashboard application."""
    # Initialize
    initialize_session_state()
    
    # Header
    st.markdown('<div class="main-header">📊 Multi-File CDI Comparison Dashboard</div>', 
               unsafe_allow_html=True)
    st.markdown("Batch processing and comparative analysis across multiple medical charts")
    
    # Initialize system
    if not initialize_cdi_system():
        st.stop()
    
    # Sidebar
    display_sidebar()
    
    # Main content
    st.markdown("---")
    
    # Tab navigation
    tab1, tab2, tab3 = st.tabs(["📁 Upload & Process", "📊 Analytics", "📥 Export"])
    
    with tab1:
        st.markdown("### 📁 Batch File Upload")
        
        uploaded_files = st.file_uploader(
            "Upload multiple medical chart files (PDF or TXT)",
            type=["pdf", "txt"],
            accept_multiple_files=True,
            help="Select multiple files to process in batch"
        )
        
        if uploaded_files:
            st.info(f"📋 {len(uploaded_files)} file(s) selected")
            
            # Display selected files
            with st.expander("View selected files", expanded=False):
                for idx, f in enumerate(uploaded_files, 1):
                    st.markdown(f"{idx}. {f.name} ({f.size / 1024:.1f} KB)")
            
            col1, col2, col3 = st.columns([1, 2, 1])
            
            with col2:
                if st.button("🚀 Process All Files", type="primary", use_container_width=True):
                    with st.spinner("Processing files... This may take several minutes."):
                        batch_results = process_batch_files(uploaded_files)
                        st.session_state.batch_results = batch_results
                        st.session_state.processing_complete = True
                    
                    st.success(f"✅ Processed {len(batch_results)} files successfully!")
                    st.balloons()
    
    with tab2:
        if st.session_state.processing_complete and st.session_state.batch_results:
            # Calculate metrics
            metrics = calculate_aggregate_metrics(st.session_state.batch_results)
            
            # Display analytics
            display_overview_metrics(metrics)
            st.markdown("---")
            
            display_compliance_summary(metrics)
            st.markdown("---")
            
            display_payer_comparison(metrics)
            st.markdown("---")
            
            display_file_by_file_results(st.session_state.batch_results)
            
        else:
            st.info("👆 Upload and process files in the 'Upload & Process' tab to see analytics")
    
    with tab3:
        if st.session_state.processing_complete and st.session_state.batch_results:
            st.markdown("### 📥 Export Results")
            
            col1, col2 = st.columns(2)
            
            with col1:
                # CSV Export
                csv_data = export_to_csv(st.session_state.batch_results)
                st.download_button(
                    label="📊 Download as CSV",
                    data=csv_data,
                    file_name=f"cdi_batch_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
            
            with col2:
                # JSON Export
                json_data = export_to_json(st.session_state.batch_results)
                st.download_button(
                    label="📄 Download as JSON",
                    data=json_data,
                    file_name=f"cdi_batch_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    mime="application/json",
                    use_container_width=True
                )
            
            st.markdown("---")
            st.info("💡 CSV format is ideal for Excel analysis. JSON format preserves complete data structure.")
            
        else:
            st.info("👆 Process files first to enable export functionality")
    
    # Footer
    st.markdown("---")
    st.markdown(
        "<div style='text-align: center; color: #666;'>"
        "Multi-File CDI Comparison Dashboard v1.0.0 | "
        f"Powered by AWS Bedrock & OpenSearch"
        "</div>",
        unsafe_allow_html=True
    )


if __name__ == "__main__":
    main()

