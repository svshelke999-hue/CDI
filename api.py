"""
FastAPI application for Multi-Payer CDI Compliance Checker.
Provides REST API endpoints for React frontend integration.
"""

import os
import sys
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from multi_payer_cdi.core import MultiPayerCDI
from multi_payer_cdi.models import ProcessingResult

app = FastAPI(title="CDI Compliance API", version="1.0.0")

# Configure CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your React app's URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize CDI system (singleton)
cdi_system: Optional[MultiPayerCDI] = None


def get_cdi_system() -> MultiPayerCDI:
    """Get or initialize the CDI system."""
    global cdi_system
    if cdi_system is None:
        cdi_system = MultiPayerCDI()
    return cdi_system


def convert_to_serializable(obj):
    """Convert dataclass objects and other non-serializable types to dictionaries."""
    if hasattr(obj, '__dict__'):
        # It's a dataclass or object with __dict__
        result = {}
        for key, value in obj.__dict__.items():
            result[key] = convert_to_serializable(value)
        return result
    elif isinstance(obj, dict):
        return {k: convert_to_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [convert_to_serializable(item) for item in obj]
    elif isinstance(obj, (int, float, str, bool, type(None))):
        return obj
    else:
        # Fallback: try to convert to string or dict
        try:
            return str(obj)
        except:
            return {}


def transform_result_to_react_format(result: ProcessingResult, filename: str) -> dict:
    """
    Transform ProcessingResult to the format expected by React UI.
    
    React expects:
    - filename or lambda_response.file_name
    - lambda_response.extraction_data.procedure or lambda_response.procedures
    - lambda_response.extraction_data.summary
    - lambda_response.extraction_data.cpt or lambda_response.cpt_codes
    - lambda_response.result_summary.payer_results with payer decisions
    """
    extraction_data = result.extraction_data or {}
    payer_results = result.payer_results or {}
    
    # Extract procedures and CPT codes - ensure they're lists
    procedures = extraction_data.get("procedure", []) or extraction_data.get("procedures", [])
    if not isinstance(procedures, list):
        procedures = [procedures] if procedures else []
    
    cpt_codes = extraction_data.get("cpt", []) or extraction_data.get("cpt_codes", [])
    if not isinstance(cpt_codes, list):
        cpt_codes = [cpt_codes] if cpt_codes else []
    
    summary = extraction_data.get("summary", "") or ""
    
    # Transform payer results to match React expectations
    # React expects: result_summary.payer_results[key].procedure_results[0].decision
    transformed_payer_results = {}
    for payer_key, payer_result in payer_results.items():
        if isinstance(payer_result, dict):
            payer_name = payer_result.get("payer_name", payer_key)
            procedure_results = payer_result.get("procedure_results", [])
            
            # Ensure procedure_results is a list of dicts with decision field
            if not isinstance(procedure_results, list):
                procedure_results = []
            
            # Make sure each procedure_result has a decision field
            normalized_procedure_results = []
            for proc_result in procedure_results:
                if isinstance(proc_result, dict):
                    # Ensure decision field exists
                    proc_result = proc_result.copy()
                    if "decision" not in proc_result:
                        proc_result["decision"] = "-"
                    normalized_procedure_results.append(proc_result)
            
            transformed_payer_results[payer_key] = {
                "payer_name": payer_name,
                "procedure_results": normalized_procedure_results,
            }
    
    # Build the response structure matching React expectations exactly
    response = {
        "filename": filename,
        "lambda_response": {
            "file_name": filename,
            "extraction_data": {
                "procedure": procedures,
                "procedures": procedures,  # Both for compatibility
                "summary": summary,
                "cpt": cpt_codes,
                "cpt_codes": cpt_codes,  # Both for compatibility
                "patient_name": extraction_data.get("patient_name", "Unknown"),
                "patient_age": extraction_data.get("patient_age", "Unknown"),
                "chart_specialty": extraction_data.get("chart_specialty", "Unknown"),
            },
            "result_summary": {
                "payer_results": transformed_payer_results
            },
            "payer_results": transformed_payer_results,  # Also at top level for compatibility
        },
        # Include full result for advanced use cases (convert to serializable)
        "full_result": convert_to_serializable({
            "file_name": result.file_name,
            "extraction_data": extraction_data,
            "payer_results": payer_results,
            "payer_summary": result.payer_summary if hasattr(result, 'payer_summary') else {},
            "total_cost": float(result.total_cost) if result.total_cost else 0.0,
            "execution_times": {str(k): float(v) for k, v in (result.execution_times or {}).items()},
        })
    }
    
    return response


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "message": "CDI Compliance API is running"}


@app.get("/health")
async def health():
    """Health check endpoint."""
    try:
        system = get_cdi_system()
        return {"status": "healthy", "system_initialized": True}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


@app.post("/process-pdf")
async def process_pdf(file: UploadFile = File(...)):
    """
    Process a PDF, DOCX, or TXT file and return CDI compliance results.
    
    Accepts:
    - PDF files (.pdf)
    - DOCX files (.docx)
    - TXT files (.txt)
    
    Returns:
    - JSON response with extraction data, payer results, and compliance decisions
    """
    # Validate file type
    filename = file.filename or "unknown"
    ext = Path(filename).suffix.lower()
    
    if ext not in [".pdf", ".docx", ".doc", ".txt"]:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format: {ext}. Please upload PDF, DOCX, or TXT file."
        )
    
    # Save uploaded file to temporary location
    temp_file = None
    try:
        # Create temporary file
        suffix = Path(filename).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await file.read()
            tmp.write(content)
            temp_file = tmp.name
        
        # Process file using CDI system
        system = get_cdi_system()
        result = system.process_file(temp_file)
        
        # Check for errors
        if result.error:
            raise HTTPException(
                status_code=500,
                detail=f"Processing error: {result.error}"
            )
        
        # Transform result to React-expected format
        response_data = transform_result_to_react_format(result, filename)
        
        return JSONResponse(content=response_data)
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Error processing file {filename}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error processing file: {str(e)}"
        )
    finally:
        # Clean up temporary file
        if temp_file and os.path.exists(temp_file):
            try:
                os.unlink(temp_file)
            except Exception as e:
                print(f"[WARNING] Failed to delete temp file {temp_file}: {e}")


@app.get("/test")
async def test_with_sample_chart():
    """
    Test endpoint that processes a sample chart and returns both input and output.
    Useful for verifying the API is working correctly.
    """
    try:
        system = get_cdi_system()
        
        # Use sample chart from Charts directory
        sample_chart_path = Path(__file__).parent / "Charts" / "sample_chart_mixed.txt"
        
        if not sample_chart_path.exists():
            # Try alternative path
            sample_chart_path = Path(__file__).parent / "Charts" / "sample_chart_procedure_only.txt"
        
        if not sample_chart_path.exists():
            raise HTTPException(
                status_code=404,
                detail="Sample chart file not found. Please ensure Charts/sample_chart_mixed.txt exists."
            )
        
        # Read the input chart
        with open(sample_chart_path, "r", encoding="utf-8", errors="ignore") as f:
            input_chart = f.read()
        
        # Process the chart
        result = system.process_file(str(sample_chart_path))
        
        # Check for errors
        if result.error:
            raise HTTPException(
                status_code=500,
                detail=f"Processing error: {result.error}"
            )
        
        # Transform result to React-expected format
        response_data = transform_result_to_react_format(result, sample_chart_path.name)
        
        # Convert UsageInfo to dict for JSON serialization
        def convert_usage_info(usage_info):
            if hasattr(usage_info, '__dict__'):
                return usage_info.__dict__
            elif isinstance(usage_info, dict):
                return usage_info
            return {
                "input_tokens": getattr(usage_info, 'input_tokens', 0),
                "output_tokens": getattr(usage_info, 'output_tokens', 0),
                "total_cost": getattr(usage_info, 'total_cost', 0.0)
            }
        
        # Convert execution_times to ensure it's serializable
        execution_times = result.execution_times
        if execution_times:
            execution_times = {str(k): float(v) for k, v in execution_times.items()}
        
        # Add input chart to response for testing
        test_response = {
            "test_status": "success",
            "input": {
                "file_name": sample_chart_path.name,
                "chart_text": input_chart,
                "chart_length": len(input_chart),
                "chart_lines": len(input_chart.split('\n'))
            },
            "output": response_data,
            "processing_info": {
                "file_name": result.file_name,
                "total_cost": float(result.total_cost) if result.total_cost else 0.0,
                "execution_times": execution_times or {},
                "payers_processed": len(result.payer_results) if result.payer_results else 0,
                "extraction_data_keys": list(result.extraction_data.keys()) if result.extraction_data else [],
                "total_usage": convert_usage_info(result.total_usage) if result.total_usage else {}
            }
        }
        
        return JSONResponse(content=test_response)
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Error in test endpoint: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error processing test chart: {str(e)}"
        )


@app.get("/system-info")
async def system_info():
    """Get system configuration and status information."""
    try:
        system = get_cdi_system()
        info = system.get_system_info()
        return info
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting system info: {str(e)}")


if __name__ == "__main__":
    # Run the API server
    # host="0.0.0.0" allows access from any network interface
    # Access via: http://localhost:8001 or http://127.0.0.1:8001 (local)
    # Or use your machine's IP: http://10.50.20.175:8001 (network access)
    uvicorn.run(
        "api:app",
        host="0.0.0.0",  # Bind to all interfaces (allows network access)
        port=8001,
        reload=True,
        log_level="info"
    )

