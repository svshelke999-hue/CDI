#!/usr/bin/env python3
"""
Main entry point for the Multi-Payer CDI Compliance Checker.

Enhanced Clinical Documentation Improvement (CDI) system with multi-payer support,
RAG integration, and comprehensive prompt caching.
"""

import sys
import json
import os
from pathlib import Path

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from multi_payer_cdi.core import MultiPayerCDI
from multi_payer_cdi.config import Config


def print_banner():
    """Print application banner."""
    print("Enhanced Multi-Payer CDI Compliance Checker with Prompt Caching")
    print("=" * 80)


def print_evidence_summary(result):
    """Print evidence summary from processing results."""
    if not result or not hasattr(result, 'payer_results'):
        return
    
    print("\nEvidence Summary:")
    print("=" * 80)
    
    total_guideline_refs = 0
    total_chart_refs = 0
    total_guidelines_found = 0
    
    for payer_key, payer_result in result.payer_results.items():
        if isinstance(payer_result, dict):
            payer_name = payer_result.get('payer_name', 'Unknown')
            procedure_results = payer_result.get('procedure_results', [])
            
            # Collect payer guideline evidence
            payer_guideline_evidence = []
            # Collect medical chart evidence
            payer_chart_evidence = []
            # Count total guidelines
            guidelines_count = 0
            # Collect CPT-specific guidelines and procedure guidelines separately
            all_cpt_guidelines = []
            all_procedure_guidelines = []
            
            for proc_result in procedure_results:
                if isinstance(proc_result, dict):
                    # Check if CPT-based search was used
                    guideline_info = proc_result.get('guideline_availability', {})
                    is_cpt_based = "CPT" in guideline_info.get('message', '') or "codes:" in guideline_info.get('message', '')
                    
                    # Count guidelines
                    guidelines_count += guideline_info.get('search_hits', 0)
                    
                    # Collect CPT-specific guidelines
                    cpt_guidelines = proc_result.get('cpt_specific_guidelines', [])
                    if cpt_guidelines and is_cpt_based and not all_cpt_guidelines:
                        all_cpt_guidelines = cpt_guidelines  # Collect once (same for all CPT procedures)
                    
                    # Collect procedure-based guidelines
                    procedure_guidelines = proc_result.get('procedure_guidelines', [])
                    if procedure_guidelines:
                        all_procedure_guidelines.extend(procedure_guidelines)  # Collect for each non-CPT procedure
                    
                    # Payer guideline references
                    sources = proc_result.get('sources', [])
                    for source in sources:
                        if isinstance(source, dict):
                            guideline_refs = source.get('payer_guideline_reference', [])
                            payer_guideline_evidence.extend(guideline_refs)
                    
                    # Medical chart references
                    chart_refs = proc_result.get('medical_chart_reference', [])
                    if chart_refs:
                        payer_chart_evidence.extend(chart_refs)
            
            # Remove duplicates
            unique_guideline_evidence = sorted(set(payer_guideline_evidence))
            unique_chart_evidence = sorted(set(payer_chart_evidence))
            
            if unique_guideline_evidence or unique_chart_evidence or guidelines_count > 0:
                print(f"\n{payer_name}:")
                
                # Display guideline count
                if guidelines_count > 0:
                    print(f"   Guidelines Retrieved: {guidelines_count} guideline(s)")
                
                # Display CPT-specific guidelines (if any)
                if all_cpt_guidelines:
                    print(f"\n   🎯 CPT-SPECIFIC GUIDELINES:")
                    print("   " + "="*70)
                    for idx, guideline in enumerate(all_cpt_guidelines, 1):
                        procedure_name = guideline.get('procedure_name', 'Unknown')
                        cpt_codes = guideline.get('cpt_codes', [])
                        guideline_text = guideline.get('guideline_text', 'No content')
                        evidence_summary = guideline.get('evidence_summary', 'No references')
                        
                        print(f"\n   Guideline {idx}:")
                        print(f"   CPT Code(s): {', '.join(cpt_codes)}")
                        print(f"   Procedure: {procedure_name}")
                        print(f"   Evidence: {evidence_summary}")
                        print(f"\n   {guideline_text}")
                        print("   " + "-"*70)
                
                # Display procedure-based guidelines (if any)
                if all_procedure_guidelines:
                    print(f"\n   📋 PROCEDURE-BASED GUIDELINES (No CPT codes):")
                    print("   " + "="*70)
                    for idx, guideline in enumerate(all_procedure_guidelines, 1):
                        procedure_name = guideline.get('procedure_name', 'Unknown')
                        guideline_text = guideline.get('guideline_text', 'No content')
                        evidence_summary = guideline.get('evidence_summary', 'No references')
                        
                        print(f"\n   Guideline {idx}:")
                        print(f"   Procedure: {procedure_name}")
                        print(f"   Evidence: {evidence_summary}")
                        print(f"\n   {guideline_text}")
                        print("   " + "-"*70)
                
                # Display medical chart evidence
                if unique_chart_evidence:
                    print(f"   Medical Chart Evidence:")
                    print(f"      Found {len(unique_chart_evidence)} line reference(s) from medical chart")
                    chart_display = ", ".join(unique_chart_evidence[:15])  # Show first 15
                    print(f"      {chart_display}")
                    if len(unique_chart_evidence) > 15:
                        print(f"      ... and {len(unique_chart_evidence) - 15} more")
                    total_chart_refs += len(unique_chart_evidence)
                
                # Display payer guideline evidence (PDF references)
                if unique_guideline_evidence:
                    print(f"   Payer Guideline Evidence (PDF References):")
                    print(f"      Found {len(unique_guideline_evidence)} reference(s) from guideline documents")
                    for evidence_ref in unique_guideline_evidence[:5]:  # Show first 5
                        print(f"      - {evidence_ref}")
                    if len(unique_guideline_evidence) > 5:
                        print(f"      ... and {len(unique_guideline_evidence) - 5} more")
                    total_guideline_refs += len(unique_guideline_evidence)
                
                total_guidelines_found += guidelines_count
    
    # Print totals
    print("\nTotal Evidence Summary:")
    if total_guidelines_found > 0:
        print(f"   Total Guidelines Retrieved: {total_guidelines_found}")
    if total_chart_refs > 0:
        print(f"   Medical Chart References: {total_chart_refs}")
    if total_guideline_refs > 0:
        print(f"   Payer Guideline References (PDF): {total_guideline_refs}")
    if total_chart_refs == 0 and total_guideline_refs == 0 and total_guidelines_found == 0:
        print("   No evidence references found")
    
    print("=" * 80)


def print_configuration():
    """Print current configuration."""
    print("Configured Payers:")
    for payer_key, config in Config.PAYER_CONFIG.items():
        json_path = config.get('json_data_path', 'N/A')
        if Config.DATA_SOURCE == "json":
            print(f"  • {config['name']}: JSON path configured")
        else:
            print(f"  • {config['name']}: {config['os_index']} (filters: {', '.join(config['filter_terms'])})")
    
    print(f"Cache enabled: {Config.ENABLE_CACHE}")
    print(f"Cache directory: {Config.CACHE_DIR}")
    print(f"Cache TTL: {Config.CACHE_TTL_HOURS} hours")
    print(f"Data source: {Config.DATA_SOURCE}")
    
    if Config.DATA_SOURCE == "opensearch":
        print(f"OpenSearch host: {Config.OS_HOST}")
        print(f"OpenSearch index: {Config.OS_INDEX}")
    elif Config.DATA_SOURCE == "json":
        print(f"JSON guideline paths:")
        for payer, path in Config.JSON_GUIDELINE_PATHS.items():
            exists = "[OK]" if __import__('os').path.exists(path) else "[MISSING]"
            print(f"  {exists} {payer}: {path}")
    
    print(f"Claude model: {Config.CLAUDE_MODEL_ID}")
    print()


def process_single_file(cdi_system: MultiPayerCDI, file_path: str):
    """Process a single file."""
    print(f"Processing single file: {os.path.basename(file_path)}")
    
    try:
        result = cdi_system.process_file(file_path)
        
        # Check if CPT codes were detected
        extraction_data = result.extraction_data
        cpt_codes = extraction_data.get("cpt", []) if extraction_data else []
        has_cpt = extraction_data.get("has_cpt_codes", False) if extraction_data else False
        procedures = extraction_data.get("procedure", []) if extraction_data else []
        
        # Print CPT detection status
        print("\n" + "="*80)
        if has_cpt and cpt_codes:
            num_cpt = len(cpt_codes)
            num_proc = len(procedures)
            
            print("🎯 CPT CODES DETECTED - Hybrid Processing")
            print(f"   CPT Codes: {', '.join(cpt_codes)}")
            
            if num_proc > num_cpt:
                # Mixed case: some procedures with CPT, some without
                print(f"\n   CPT-Associated Procedures ({num_cpt}): {', '.join(procedures[:num_cpt])}")
                print(f"   → Search Method: Direct CPT lookup")
                
                print(f"\n   Additional Procedures ({num_proc - num_cpt}): {', '.join(procedures[num_cpt:])}")
                print(f"   → Search Method: Procedure-based RAG search")
            else:
                # All procedures have CPT codes
                print(f"   Search Method: Direct CPT lookup for all procedures")
                print(f"   Result: ALL guidelines containing these CPT codes were retrieved")
        else:
            print("ℹ️  No CPT Codes Detected - Procedure-Based RAG Search Used")
            print("   Search Method: Semantic RAG search for procedure descriptions")
        print("="*80)
        
        # Print results with evidence information
        print("\nProcessing Results:")
        print(json.dumps(result.__dict__, indent=2, ensure_ascii=False, default=str))
        
        # Print evidence summary
        print_evidence_summary(result)
        
        # Print cache statistics
        cdi_system.print_cache_stats()
        
        # Save cache statistics
        cdi_system.save_cache_stats()
        
    except Exception as e:
        print(f"[ERROR] Error processing file: {e}")
        print(json.dumps({"error": str(e)}, indent=2))


def process_directory(cdi_system: MultiPayerCDI, input_dir: str):
    """Process all files in a directory."""
    print(f"Processing directory: {input_dir}")
    
    try:
        results = cdi_system.process_directory(input_dir)
        
        # Print results
        print(f"\nProcessing complete. Results for {len(results)} files:")
        print(json.dumps(results, indent=2, ensure_ascii=False, default=str))
        
        # Print evidence summary for each file
        for file_name, file_result in results.items():
            if isinstance(file_result, dict) and 'payer_results' in file_result:
                # Create a mock object with payer_results attribute
                class MockResult:
                    def __init__(self, payer_results):
                        self.payer_results = payer_results
                print(f"\nEvidence for {file_name}:")
                print_evidence_summary(MockResult(file_result['payer_results']))
        
        # Print cache statistics
        cdi_system.print_cache_stats()
        
        # Save cache statistics
        cdi_system.save_cache_stats()
        
    except Exception as e:
        print(f"[ERROR] Error processing directory: {e}")
        print(json.dumps({"error": str(e)}, indent=2))


def show_system_info():
    """Show system information and configuration."""
    try:
        cdi_system = MultiPayerCDI()
        info = cdi_system.get_system_info()
        
        print("System Information:")
        print(json.dumps(info, indent=2))
        
    except Exception as e:
        print(f"[ERROR] Error getting system info: {e}")


def main():
    """Main entry point."""
    print_banner()
    
    # Get command line arguments (excluding flags)
    args = [arg for arg in sys.argv[1:] if not arg.startswith("-")]
    
    # Check for help flag
    if "--help" in sys.argv or "-h" in sys.argv:
        print("""
Usage: python main.py [options] [file_or_directory]

Options:
  --help, -h          Show this help message
  --info              Show system information and configuration
  --single-file       Process as single file (default for single argument)
  --directory         Process as directory (default for no arguments)

Examples:
  python main.py                                    # Process default directory
  python main.py /path/to/file.pdf                  # Process single file
  python main.py /path/to/directory                 # Process directory
  python main.py --info                             # Show system info

Environment Variables:
  AWS_REGION                    AWS region for Bedrock (default: us-east-1)
  CLAUDE_MODEL_ID              Claude model ID
  OS_HOST                      OpenSearch host (default: http://localhost:9200)
  OS_INDEX                     OpenSearch index (default: rag-chunks)
  CACHE_DIR                    Cache directory
  CACHE_TTL_HOURS              Cache TTL in hours (default: 24)
  ENABLE_CACHE                 Enable caching (default: true)
  CHART_INPUT_DIR              Default input directory for charts
        """)
        return
    
    # Check for info flag
    if "--info" in sys.argv:
        show_system_info()
        return
    
    # Print configuration
    print_configuration()
    
    try:
        # Initialize the CDI system
        cdi_system = MultiPayerCDI()
        
        if len(args) == 0:
            # No arguments - process default directory
            input_dir = Config.CHART_INPUT_DIR
            process_directory(cdi_system, input_dir)
            
        elif len(args) == 1:
            # Single argument - determine if it's file or directory
            path = args[0]
            
            if os.path.isfile(path):
                # It's a file
                process_single_file(cdi_system, path)
            elif os.path.isdir(path):
                # It's a directory
                process_directory(cdi_system, path)
            else:
                print(f"[ERROR] Path does not exist: {path}")
                return
                
        else:
            # Multiple arguments - process each as a file
            for path in args:
                if os.path.isfile(path):
                    process_single_file(cdi_system, path)
                else:
                    print(f"[WARNING] Skipping non-file path: {path}")
    
    except KeyboardInterrupt:
        print("\n[INTERRUPTED] Processing interrupted by user")
    except Exception as e:
        print(f"[FATAL ERROR] Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
