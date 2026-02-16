"""
Test script for multi-chart processing functionality.
"""

import sys
from pathlib import Path

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from multi_payer_cdi.core import MultiPayerCDI

def test_multi_chart_processing():
    """Test processing multiple charts together."""
    print("=" * 60)
    print("Testing Multi-Chart Processing")
    print("=" * 60)
    
    # Initialize CDI system
    print("\n[1/4] Initializing CDI system...")
    cdi_system = MultiPayerCDI()
    print("[OK] CDI system initialized")
    
    # Define test chart files
    test_files = [
        "test_charts/pre_operative_note.txt",
        "test_charts/operative_note.txt"
    ]
    
    # Check if files exist
    print("\n[2/4] Checking test files...")
    for file_path in test_files:
        if Path(file_path).exists():
            print(f"[OK] Found: {file_path}")
        else:
            print(f"[ERROR] Missing: {file_path}")
            return
    
    # Process multiple charts
    print("\n[3/4] Processing multiple charts...")
    try:
        result = cdi_system.process_multiple_charts(test_files)
        print("[OK] Multi-chart processing completed")
        
        # Display results
        print("\n[4/4] Results Summary:")
        print(f"  - File Name: {result.file_name}")
        print(f"  - Total Cost: ${result.total_cost:.6f}")
        print(f"  - Payer Results: {len(result.payer_results)} payer(s)")
        
        # Display multi-chart info
        if hasattr(result, 'multi_chart_info') and result.multi_chart_info:
            multi_info = result.multi_chart_info
            print(f"\n  Multi-Chart Information:")
            print(f"    - Total Charts: {multi_info.get('total_charts', 0)}")
            
            chart_details = multi_info.get('chart_details', {})
            print(f"    - Chart Details:")
            for file_name, details in chart_details.items():
                chart_type = details.get('chart_type', 'unknown')
                confidence = details.get('chart_type_confidence', 'unknown')
                print(f"      • {file_name}: {chart_type} (confidence: {confidence})")
        
        # Display extraction data
        extraction = result.extraction_data
        print(f"\n  Combined Extraction:")
        print(f"    - Patient Name: {extraction.get('patient_name', 'Unknown')}")
        print(f"    - Patient Age: {extraction.get('patient_age', 'Unknown')}")
        print(f"    - Chart Specialty: {extraction.get('chart_specialty', 'Unknown')}")
        print(f"    - Procedures: {extraction.get('procedure', [])}")
        print(f"    - CPT Codes: {extraction.get('cpt', [])}")
        
        print("\n" + "=" * 60)
        print("[OK] Test completed successfully!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n[ERROR] Error during processing: {e}")
        import traceback
        traceback.print_exc()
        return

if __name__ == "__main__":
    test_multi_chart_processing()

