"""
Quick verification script to check if CMS sources are being added to procedure results.
Run this after processing a file to verify CMS data is present.
"""

import json
import sys

def verify_cms_in_result(result_file_path):
    """Verify CMS sources are in the result file."""
    try:
        with open(result_file_path, 'r', encoding='utf-8') as f:
            result = json.load(f)
        
        payer_results = result.get("result", {}).get("payer_results", {})
        
        print("=" * 80)
        print("CMS GUIDELINES VERIFICATION")
        print("=" * 80)
        
        found_cms = False
        for payer_key, payer_result in payer_results.items():
            procedure_results = payer_result.get("procedure_results", [])
            
            for idx, proc_result in enumerate(procedure_results, 1):
                proc_name = proc_result.get("procedure_evaluated", "Unknown")
                cms_sources = proc_result.get("cms_sources", [])
                cms_has_guidelines = proc_result.get("cms_has_guidelines", False)
                cms_context = proc_result.get("cms_guidelines_context", "")
                
                print(f"\n[{payer_key}] Procedure {idx}: {proc_name}")
                print(f"  CMS Sources: {len(cms_sources) if cms_sources else 0}")
                print(f"  CMS Has Guidelines: {cms_has_guidelines}")
                print(f"  CMS Context Length: {len(cms_context)}")
                
                if cms_sources or cms_has_guidelines:
                    found_cms = True
                    print(f"  ✅ CMS data found!")
                    if cms_sources:
                        print(f"  First source keys: {list(cms_sources[0].keys()) if cms_sources else 'N/A'}")
                else:
                    print(f"  ⚠️ No CMS data found")
        
        print("\n" + "=" * 80)
        if found_cms:
            print("✅ VERIFICATION PASSED: CMS data is present in results")
        else:
            print("⚠️ VERIFICATION WARNING: No CMS data found in results")
            print("   This could mean:")
            print("   1. No CMS guidelines matched the procedures")
            print("   2. CMS guidelines database is not loaded")
            print("   3. Results were generated before CMS integration")
        print("=" * 80)
        
    except FileNotFoundError:
        print(f"❌ ERROR: Result file not found: {result_file_path}")
        print("   Please process a file first to generate results")
    except Exception as e:
        print(f"❌ ERROR: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        result_file = sys.argv[1]
    else:
        # Try to find a recent result file
        import os
        import glob
        output_dir = "outputs"
        if os.path.exists(output_dir):
            result_files = glob.glob(os.path.join(output_dir, "*.json"))
            if result_files:
                # Get most recent
                result_file = max(result_files, key=os.path.getmtime)
                print(f"Using most recent result file: {result_file}\n")
            else:
                print("❌ No result files found in outputs/ directory")
                print("   Please process a file first, or provide a result file path")
                sys.exit(1)
        else:
            print("❌ Outputs directory not found")
            sys.exit(1)
    
    verify_cms_in_result(result_file)

