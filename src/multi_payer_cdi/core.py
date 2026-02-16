"""
Core orchestrator for the Multi-Payer CDI Compliance Checker.
"""

import os
import json
import time
import re
import concurrent.futures
from typing import Dict, Any, List, Tuple

from .config import Config
from .models import ProcessingResult, UsageInfo, ComplianceResult, ExtractionData
from .cache_manager import CacheManager
from .compliance_evaluator import ComplianceEvaluator
from .file_processor import FileProcessor
from .opensearch_client import OpenSearchClient
from .utils import safe_json_loads
from .logger import CDILogger, get_logger
from .chart_improver import ChartImprover
from .chart_type_identifier import ChartTypeIdentifier


class MultiPayerCDI:
    """Main orchestrator for multi-payer CDI compliance checking."""
    
    def __init__(self):
        # Ensure directories exist
        os.makedirs(Config.OUTPUT_DIR, exist_ok=True)
        os.makedirs(Config.LOG_DIR, exist_ok=True)
        
        # Initialize logger
        self.logger = get_logger("cdi_system")
        self.logger.info("Initializing Multi-Payer CDI system...")
        
        self.cache_manager = CacheManager()
        self.compliance_evaluator = ComplianceEvaluator(self.cache_manager)
        self.chart_improver = ChartImprover(self.cache_manager)
        self.chart_type_identifier = ChartTypeIdentifier(self.cache_manager)
        
        # Initialize cache and cleanup
        self.cache_manager.cleanup_old_cache()
        
        # Validate configuration
        if not Config.validate_config():
            raise ValueError("Invalid configuration. Please check environment variables.")
        
        # Test OpenSearch connection (only if using OpenSearch data source)
        if Config.DATA_SOURCE == "opensearch":
            if not OpenSearchClient.ping():
                raise ConnectionError("OpenSearch connection failed. Please check configuration.")
            print("[OK] OpenSearch connected")
        elif Config.DATA_SOURCE == "json":
            print(f"[OK] Using JSON guideline data from local files")
            # Verify at least one JSON path exists
            json_available = any(
                __import__('os').path.exists(path) 
                for path in Config.JSON_GUIDELINE_PATHS.values()
            )
            if not json_available:
                raise FileNotFoundError(
                    "No JSON guideline files found. Please check JSON_GUIDELINE_PATHS in config."
                )
        
        print("[OK] Multi-Payer CDI system initialized successfully")
    
    def process_file(self, file_path: str) -> ProcessingResult:
        """
        Process a single medical chart file.
        
        Args:
            file_path: Path to the medical chart file
            
        Returns:
            ProcessingResult with compliance evaluation for all payers
        """
        start_time = time.time()
        print(f"[PROCESSING] Processing {file_path}...")
        self.logger.info(f"Processing file: {file_path}")
        
        try:
            # Read and validate file
            if not FileProcessor.validate_file(file_path):
                raise ValueError(f"Invalid file: {file_path}")
            
            # Read chart and add line numbers immediately
            original_chart_text = FileProcessor.read_chart(file_path)
            numbered_chart_text = FileProcessor.add_line_numbers(original_chart_text)
            print(f"[INFO] Medical chart loaded with {len(original_chart_text.split(chr(10)))} lines")
            
            # Run extraction using the numbered chart
            llm_output, extraction_usage = self.compliance_evaluator.run_extraction(numbered_chart_text)
            print(f"[EXTRACTION] Extraction completed. Raw output: {llm_output}")
            
            # Parse extraction data
            extraction_data = safe_json_loads(llm_output, {})
            if not isinstance(extraction_data, dict):
                extraction_data = {}
            extraction_data.setdefault("patient_name", "Unknown")
            extraction_data.setdefault("patient_age", "Unknown")
            extraction_data.setdefault("chart_specialty", "Unknown")
            extraction_data.setdefault("cpt", [])
            extraction_data.setdefault("procedure", [])
            extraction_data.setdefault("summary", "")
            
            # Run multi-payer compliance evaluation using the numbered chart
            mapping_result = self.map_guidelines_for_case_text_multi_payer(llm_output, numbered_chart_text)
            
            # Create processing result
            total_usage = UsageInfo(
                input_tokens=extraction_usage.get("input_tokens", 0) + mapping_result["usage"]["input_tokens"],
                output_tokens=extraction_usage.get("output_tokens", 0) + mapping_result["usage"]["output_tokens"]
            )
            total_usage.calculate_costs(Config.INPUT_COST_PER_1K, Config.OUTPUT_COST_PER_1K)
            
            # Ensure original_chart is stored without line numbers
            original_chart_clean = FileProcessor.remove_line_numbers(original_chart_text)
            
            result = ProcessingResult(
                file_name=file_path,
                extraction_data=extraction_data,
                payer_results=mapping_result["result"]["payer_results"],
                total_usage=total_usage,
                total_cost=mapping_result["cost"]["total_cost_usd"],
                execution_times=mapping_result["meta"]["execution_times"],
                sources=mapping_result["sources"],
                numbered_medical_chart=numbered_chart_text,
                original_chart=original_chart_clean
            )
            result.payer_summary = self._calculate_payer_summary(result.payer_results)
            
            # Generate improved chart using AI
            print("[CHART IMPROVEMENT] Generating AI-improved chart...")
            try:
                improved_chart_data = self.chart_improver.improve_medical_chart(
                    original_chart=original_chart_text,
                    processing_result=result
                )
                
                # Extract just the improved chart text (end-to-end chart, without line numbers)
                improved_chart_text = improved_chart_data.get("improved_chart", original_chart_text)
                # Preserve [AI ADDED: ...] and [NEEDS PHYSICIAN INPUT: ...] markers
                # Only remove old-style [ADDED: ...] markers (without "AI" prefix) if they exist
                # This allows backward compatibility while preserving new marker format
                improved_chart_text = re.sub(r'\[ADDED\s*:\s*([^\]]+)\]\s*', r'\1', improved_chart_text, flags=re.IGNORECASE)
                # Ensure no line numbers in improved chart (strip if any exist)
                improved_chart_text = FileProcessor.remove_line_numbers(improved_chart_text)
                result.improved_chart_by_ai = improved_chart_text
                
                # Store enhancement details separately
                result.enhanced_by_ai = {
                    "improvements": improved_chart_data.get("improvements", []),
                    "user_input_required": improved_chart_data.get("user_input_required", []),
                    "recommendations": improved_chart_data.get("recommendations", []),
                    "compliance_impact": improved_chart_data.get("compliance_impact", {}),
                    "success": improved_chart_data.get("success", True)
                }
                
                # Update total cost to include chart improvement cost
                improvement_cost = improved_chart_data.get("cost", 0.0)
                result.total_cost += improvement_cost
                
                # Update total usage to include chart improvement tokens
                improvement_usage = improved_chart_data.get("usage", {})
                if improvement_usage:
                    result.total_usage.input_tokens += improvement_usage.get("input_tokens", 0)
                    result.total_usage.output_tokens += improvement_usage.get("output_tokens", 0)
                    result.total_usage.calculate_costs(Config.INPUT_COST_PER_1K, Config.OUTPUT_COST_PER_1K)
                
                print(f"[CHART IMPROVEMENT] AI chart improvement completed successfully")
            except Exception as e:
                print(f"[WARNING] Chart improvement failed: {e}")
                self.logger.warning(f"Chart improvement failed for {file_path}: {e}")
                # If improvement fails, use original chart as fallback
                result.improved_chart_by_ai = original_chart_text
                result.enhanced_by_ai = {
                    "improvements": [],
                    "user_input_required": [],
                    "recommendations": [],
                    "compliance_impact": {},
                    "success": False,
                    "error": str(e)
                }
            
            # Calculate execution time
            execution_time = time.time() - start_time
            
            # Save outputs to outputs directory
            # 1. Save JSON output (without medical chart to keep file size smaller)
            result_dict = result.__dict__.copy()
            numbered_chart = result_dict.pop('numbered_medical_chart', None)
            json_output_path = CDILogger.save_output(file_path, result_dict, "json")
            
            # 2. Save numbered medical chart as separate text file
            if numbered_chart:
                chart_output_path = CDILogger.save_numbered_chart(file_path, numbered_chart)
                print(f"[SAVED] Numbered medical chart saved to: {chart_output_path}")
            
            # Log processing result
            CDILogger.log_processing_result(
                file_name=file_path,
                payers_processed=len(result.payer_results),
                procedures_evaluated=mapping_result["result"]["procedures_evaluated"],
                total_cost=result.total_cost,
                execution_time=execution_time,
                success=True
            )
            
            print(f"[OK] Processing completed for {file_path}")
            self.logger.info(f"Processing completed successfully. Output: {json_output_path}")
            return result
            
        except Exception as e:
            execution_time = time.time() - start_time
            print(f"[ERROR] Error processing {file_path}: {e}")
            self.logger.error(f"Processing failed for {file_path}: {e}")
            
            # Log failed processing
            CDILogger.log_processing_result(
                file_name=file_path,
                payers_processed=0,
                procedures_evaluated=0,
                total_cost=0.0,
                execution_time=execution_time,
                success=False,
                error=str(e)
            )
            
            return ProcessingResult(
                file_name=file_path,
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
    
    def map_guidelines_for_case_text_multi_payer(self, llm_output: str, chart_text: str) -> Dict[str, Any]:
        """
        Enhanced multi-payer processing with better parallel execution and caching.
        
        Args:
            llm_output: JSON output from extraction phase
            chart_text: Original medical chart text
            
        Returns:
            Dictionary containing compliance results for all payers
        """
        # Parse procedures from extraction
        procedures_list = []
        extraction_data = {}
        
        try:
            ext = safe_json_loads(llm_output, {})
            if isinstance(ext, dict):
                raw_procs = ext.get("procedure") or ext.get("procedures") or []
                if isinstance(raw_procs, list):
                    procedures_list = [str(p) for p in raw_procs if p]
                extraction_data = ext
        except Exception:
            procedures_list = []
        
        if not procedures_list:
            # Return skeleton result if no procedures found
            return {
                "result": {
                    "procedures_evaluated": 0,
                    "payer_results": {
                        payer_key: ComplianceResult(
                            payer_name=config["name"],
                            procedures_evaluated=0,
                            procedure_results=[],
                            usage=UsageInfo(),
                            sources=[]
                        ).__dict__
                        for payer_key, config in Config.PAYER_CONFIG.items()
                    }
                },
                "usage": {"input_tokens": 0, "output_tokens": 0},
                "cost": {"total_cost_usd": 0.0},
                "meta": {"model_id": "none", "execution_times": {}},
                "sources": []
            }
        
        print(f"[PROCESSING] Processing {len(procedures_list)} procedures - evaluating each procedure for all {len(Config.PAYER_CONFIG)} payers in single LLM call...")
        
        # OPTIMIZED: Iterate by procedure first, evaluate all payers in single LLM call per procedure
        # Initialize payer results structure
        payer_results = {}
        total_input_tokens = 0
        total_output_tokens = 0
        all_sources_by_payer = {}
        all_cms_sources = []  # Track CMS general guideline sources
        execution_times = {}
        
        # Initialize payer results structure
        sorted_payers = Config.get_sorted_payers()
        for payer_key, payer_config in sorted_payers:
            payer_results[payer_key] = {
                "payer_name": payer_config['name'],
                "procedures_evaluated": len(procedures_list),
                "procedure_results": [],
                "usage": {"input_tokens": 0, "output_tokens": 0},
                "sources": []
            }
            all_sources_by_payer[payer_key] = []
        
        # Process each procedure sequentially (each procedure makes one LLM call for all payers)
        for proc_idx, proc_name in enumerate(procedures_list):
            start_time = time.time()
            
            try:
                # Evaluate this procedure for all payers in a single LLM call
                proc_result = self.compliance_evaluator.evaluate_procedure_for_all_payers(
                    proc_name=proc_name,
                    chart_text=chart_text,
                    extraction_data=extraction_data,
                    proc_index=proc_idx,
                    total_procedures=len(procedures_list)
                )
                
                # Distribute results to payer results structure
                procedure_results_by_payer = proc_result.get("payer_results", {})
                sources_by_payer = proc_result.get("sources_by_payer", {})
                cms_sources = proc_result.get("cms_sources", [])  # Get CMS sources
                usage = proc_result.get("usage", {})
                
                # Accumulate CMS sources
                if cms_sources:
                    all_cms_sources.extend(cms_sources)
                
                # Add procedure results to each payer
                for payer_key, proc_result_data in procedure_results_by_payer.items():
                    if payer_key in payer_results:
                        payer_results[payer_key]["procedure_results"].append(proc_result_data)
                        # Accumulate sources
                        if payer_key in sources_by_payer:
                            payer_sources = sources_by_payer[payer_key]
                            all_sources_by_payer[payer_key].extend(payer_sources)
                            payer_results[payer_key]["sources"].extend(payer_sources)
                
                # Accumulate usage
                total_input_tokens += usage.get("input_tokens", 0)
                total_output_tokens += usage.get("output_tokens", 0)
                
                # Track execution time for this procedure
                execution_time = time.time() - start_time
                # Store procedure execution time for logging
                execution_times[f"procedure_{proc_idx+1}"] = execution_time
                
                print(f"[OK] Procedure '{proc_name}' evaluated for all payers in {execution_time:.2f}s")
                
            except Exception as proc_exc:
                # Handle procedure-level errors
                execution_time = time.time() - start_time
                print(f"[ERROR] Failed to evaluate procedure '{proc_name}': {proc_exc}")
                
                # Add error results for all payers for this procedure
                for payer_key, payer_config in sorted_payers:
                    if payer_key in payer_results:
                        error_result = {
                            "procedure_evaluated": proc_name,
                            "variant_or_subprocedure": "Error",
                            "policy_name": f"{payer_config['name']} - Error",
                            "decision": "Insufficient",
                            "primary_reasons": [f"Error processing procedure: {str(proc_exc)}"],
                            "requirement_checklist": [],
                            "timing_validation": {},
                            "contraindications_exclusions": {},
                            "coding_implications": {"eligible_codes_if_sufficient": [], "notes": f"{payer_config['name']} - Processing error"},
                            "improvement_recommendations": {
                                "documentation_gaps": ["Processing error occurred"],
                                "compliance_actions": ["Review error and retry processing"],
                                "priority": "high"
                            },
                            "_original_procedure_name": proc_name
                        }
                        payer_results[payer_key]["procedure_results"].append(error_result)
        
        # Convert to ComplianceResult format for compatibility
        # Note: Usage is tracked per procedure evaluation (one LLM call per procedure for all payers)
        # We divide the total usage by number of procedures to estimate per-payer usage
        final_payer_results = {}
        for payer_key, result_data in payer_results.items():
            payer_config = Config.PAYER_CONFIG[payer_key]
            # Estimate per-payer usage: divide total by number of procedures
            # This is an approximation since we make one call per procedure for all payers
            estimated_input_tokens = total_input_tokens // len(procedures_list) if procedures_list else 0
            estimated_output_tokens = total_output_tokens // len(procedures_list) if procedures_list else 0
            usage_info = UsageInfo(
                input_tokens=estimated_input_tokens,
                output_tokens=estimated_output_tokens
            )
            usage_info.calculate_costs(Config.INPUT_COST_PER_1K, Config.OUTPUT_COST_PER_1K)
            
            final_result = ComplianceResult(
                payer_name=result_data["payer_name"],
                procedures_evaluated=result_data["procedures_evaluated"],
                procedure_results=result_data["procedure_results"],
                usage=usage_info,
                sources=result_data["sources"]
            )
            final_payer_results[payer_key] = final_result.__dict__
        
        # Collect all sources (payer-specific + CMS general)
        all_sources = []
        for payer_sources in all_sources_by_payer.values():
            all_sources.extend(payer_sources)
        # Add CMS general guideline sources
        all_sources.extend(all_cms_sources)
        
        # Calculate total cost
        total_cost = (total_input_tokens / 1000 * Config.INPUT_COST_PER_1K) + \
                    (total_output_tokens / 1000 * Config.OUTPUT_COST_PER_1K)
        
        # Calculate total execution time (sum of all procedure times)
        total_execution_time = sum(execution_times.values()) if execution_times else 0
        
        # Create payer-based execution times for compatibility with Streamlit app
        # Since all payers are evaluated together in each procedure call, 
        # we assign the total execution time equally to each payer for display
        payer_execution_times = {}
        for payer_key, payer_config in sorted_payers:
            # Each payer gets the total time since they're all processed together
            payer_execution_times[payer_key] = total_execution_time
        
        # Print execution summary
        print(f"\n[SUMMARY] Execution Summary:")
        for proc_key, time_taken in execution_times.items():
            print(f"  • {proc_key}: {time_taken:.2f}s")
        print(f"  • Total execution time: {total_execution_time:.2f}s")
        print(f"  • Total LLM calls: {len(procedures_list)} (one per procedure for all payers)")
        print(f"  • Total cost: ${total_cost:.6f}")
        print(f"  • Total tokens: {total_input_tokens + total_output_tokens:,}")
        
        return {
            "result": {
                "procedures_evaluated": len(procedures_list),
                "payer_results": final_payer_results
            },
            "usage": {
                "input_tokens": total_input_tokens,
                "output_tokens": total_output_tokens
            },
            "cost": {
                "total_cost_usd": round(total_cost, 6)
            },
            "meta": {
                "model_id": "multi-payer-optimized-single-call",
                "execution_times": payer_execution_times  # Use payer-based format for compatibility
            },
            "sources": all_sources
        }
    
    def _calculate_payer_summary(self, payer_results: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate per-payer and overall sufficiency/insufficiency percentages."""
        if not payer_results:
            return {"per_payer": {}, "overall": {
                "total_procedures": 0,
                "sufficient_count": 0,
                "insufficient_count": 0,
                "other_count": 0,
                "sufficient_percentage": 0.0,
                "insufficient_percentage": 0.0,
                "other_percentage": 0.0
            }}
        
        per_payer: Dict[str, Any] = {}
        overall_total = 0
        overall_sufficient = 0
        overall_insufficient = 0
        overall_other = 0
        
        for payer_key, payer_data in payer_results.items():
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
                elif "sufficient" in decision_lower:
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
        
        return {
            "per_payer": per_payer,
            "overall": overall_summary
        }
    
    def process_multiple_charts(self, file_paths: List[str]) -> ProcessingResult:
        """
        Process multiple related medical charts as a complete inpatient record.
        
        Args:
            file_paths: List of paths to medical chart files (can be from a folder)
            
        Returns:
            ProcessingResult with combined compliance evaluation
        """
        start_time = time.time()
        print(f"[PROCESSING] Processing {len(file_paths)} chart(s) as complete record...")
        self.logger.info(f"Processing {len(file_paths)} charts as complete record")
        
        try:
            # Step 1: Read all files and get first 100 words for each
            chart_data = []
            for file_path in file_paths:
                if not FileProcessor.validate_file(file_path):
                    print(f"[WARNING] Skipping invalid file: {file_path}")
                    continue
                
                original_text = FileProcessor.read_chart(file_path)
                # Get first 100 words for chart type identification
                words = original_text.split()[:100]
                sample_text = " ".join(words)
                
                chart_data.append({
                    "file_path": file_path,
                    "file_name": os.path.basename(file_path),
                    "original_text": original_text,
                    "sample_text": sample_text
                })
            
            if not chart_data:
                raise ValueError("No valid charts found to process")
            
            print(f"[INFO] Successfully loaded {len(chart_data)} chart(s)")
            
            # Step 2: Identify chart types together with patient matching and duplicate detection
            print(f"[IDENTIFY] Identifying chart types together (with patient matching and duplicate check)...")
            multi_chart_result = self.chart_type_identifier.identify_multiple_charts(chart_data)
            
            # Map results back to chart_data
            chart_results_map = {r.get("file_name"): r for r in multi_chart_result.get("chart_results", [])}
            
            for chart in chart_data:
                file_name = chart["file_name"]
                chart_result = chart_results_map.get(file_name, {})
                
                chart["chart_type"] = chart_result.get("chart_type", "other")
                chart["chart_type_confidence"] = chart_result.get("confidence", "low")
                chart["chart_type_reason"] = chart_result.get("reason", "")
                chart["display_title"] = chart_result.get("display_title", ChartTypeIdentifier.get_display_title(chart["chart_type"]))
                chart["patient_name"] = chart_result.get("patient_name")
                chart["patient_id"] = chart_result.get("patient_id")
                
                print(f"[IDENTIFY] {file_name}: {chart['display_title']} ({chart['chart_type']}) (confidence: {chart['chart_type_confidence']})")
            
            # Store multi-chart identification results
            same_patient = multi_chart_result.get("same_patient", False)
            same_patient_reason = multi_chart_result.get("same_patient_reason", "")
            patient_name = multi_chart_result.get("patient_name")
            patient_id = multi_chart_result.get("patient_id")
            duplicates = multi_chart_result.get("duplicates", [])
            all_chart_names = multi_chart_result.get("all_chart_names", [])
            
            print(f"[IDENTIFY] Patient Check: Same Patient = {same_patient}")
            if patient_name:
                print(f"[IDENTIFY] Patient Name: {patient_name}")
            if patient_id:
                print(f"[IDENTIFY] Patient ID: {patient_id}")
            if duplicates:
                print(f"[IDENTIFY] Duplicates found: {duplicates}")
            print(f"[IDENTIFY] All Chart Names: {', '.join(all_chart_names)}")
            
            # Step 3: Extract information from each chart separately
            print(f"[EXTRACTION] Extracting information from each chart...")
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
            
            total_extraction_usage = {"input_tokens": 0, "output_tokens": 0}
            
            # First, identify the operative chart
            operative_chart_file = None
            for chart in chart_data:
                if chart.get("chart_type") == "operative_note":
                    operative_chart_file = chart["file_name"]
                    print(f"[IDENTIFY] Found operative chart: {operative_chart_file}")
                    break
            
            # If no operative chart found, use the first chart as fallback
            if operative_chart_file is None:
                operative_chart_file = chart_data[0]["file_name"] if chart_data else None
                print(f"[WARNING] No operative chart found, using first chart as fallback: {operative_chart_file}")
            
            for chart in chart_data:
                file_name = chart["file_name"]
                chart_type = chart["chart_type"]
                chart_text = chart["original_text"]
                numbered_chart_text = FileProcessor.add_line_numbers(chart_text)
                
                print(f"[EXTRACTION] Extracting from {file_name} (type: {chart_type})...")
                
                # Run extraction with chart type
                llm_output, extraction_usage = self.compliance_evaluator.run_extraction(
                    numbered_chart_text,
                    chart_type=chart_type
                )
                
                total_extraction_usage["input_tokens"] += extraction_usage.get("input_tokens", 0)
                total_extraction_usage["output_tokens"] += extraction_usage.get("output_tokens", 0)
                
                # Parse extraction data
                extraction_data = safe_json_loads(llm_output, {})
                if not isinstance(extraction_data, dict):
                    extraction_data = {}
                
                # Store extraction data per chart with display_title
                chart_display_title = chart.get("display_title") or ChartTypeIdentifier.get_display_title(chart_type)
                all_extraction_data[file_name] = {
                    "chart_type": chart_type,
                    "display_title": chart_display_title,
                    "chart_type_confidence": chart.get("chart_type_confidence", "low"),
                    "extraction_data": extraction_data,
                    "file_path": chart["file_path"]
                }
                
                # Combine key information (procedures, CPT codes, etc.)
                # Use the most complete patient info (prefer non-"Unknown" values)
                if extraction_data.get("patient_name") and extraction_data.get("patient_name") != "Unknown":
                    if combined_extraction["patient_name"] == "Unknown":
                        combined_extraction["patient_name"] = extraction_data.get("patient_name")
                
                if extraction_data.get("patient_age") and extraction_data.get("patient_age") != "Unknown":
                    if combined_extraction["patient_age"] == "Unknown":
                        combined_extraction["patient_age"] = extraction_data.get("patient_age")
                
                if extraction_data.get("chart_specialty") and extraction_data.get("chart_specialty") != "Unknown":
                    if combined_extraction["chart_specialty"] == "Unknown":
                        combined_extraction["chart_specialty"] = extraction_data.get("chart_specialty")
                
                # CRITICAL: Only use procedures from the operative chart for CDI evaluation
                # This prevents combining procedures from different charts/patients
                if file_name == operative_chart_file:
                    # This is the operative chart - use its procedures for CDI
                    procedures = extraction_data.get("procedure", []) or extraction_data.get("procedures", [])
                    if not isinstance(procedures, list):
                        procedures = []
                    
                    # Also check for procedures in chart-specific fields (e.g., from pre-op notes)
                    if chart_type == "pre_operative_note":
                        # Pre-op notes might have planned procedures
                        planned_procs = extraction_data.get("planned_procedures", [])
                        if isinstance(planned_procs, list):
                            procedures.extend(planned_procs)
                    
                    if procedures:
                        print(f"[COMBINE] Found {len(procedures)} procedure(s) in OPERATIVE chart {file_name}: {procedures}")
                        # Clear and set procedures from operative chart only
                        combined_extraction["procedure"] = []
                        for proc in procedures:
                            if proc and str(proc).strip() and proc not in combined_extraction["procedure"]:
                                combined_extraction["procedure"].append(str(proc).strip())
                    else:
                        print(f"[WARNING] No procedures found in operative chart {file_name} (type: {chart_type})")
                    
                    # Use CPT codes from operative chart (but also collect from others for reference)
                    cpt_codes = extraction_data.get("cpt", [])
                    if isinstance(cpt_codes, list) and cpt_codes:
                        # Clear and set CPT codes from operative chart
                        combined_extraction["cpt"] = []
                        for cpt in cpt_codes:
                            if cpt and cpt not in combined_extraction["cpt"]:
                                combined_extraction["cpt"].append(cpt)
                else:
                    # This is NOT the operative chart - don't add its procedures to combined list
                    # But still collect other information for cross-referencing
                    procedures = extraction_data.get("procedure", []) or extraction_data.get("procedures", [])
                    if procedures:
                        print(f"[INFO] Found {len(procedures)} procedure(s) in non-operative chart {file_name}, but NOT using for CDI evaluation (only operative chart procedures are used)")
                
                # Store chart-specific data
                combined_extraction["multi_chart_data"][file_name] = {
                    "chart_type": chart_type,
                    "chart_type_confidence": chart.get("chart_type_confidence", "low"),
                    "extracted_info": extraction_data
                }
                
                print(f"[EXTRACTION] Completed extraction from {file_name}")
            
            # Step 4: Combine all charts with markers for compliance evaluation
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
            
            # Step 5: Run compliance evaluation using combined chart and combined extraction
            print(f"[COMPLIANCE] Running compliance evaluation with combined charts...")
            print(f"[COMPLIANCE] Combined procedures: {combined_extraction.get('procedure', [])}")
            print(f"[COMPLIANCE] Combined CPT codes: {combined_extraction.get('cpt', [])}")
            
            if not combined_extraction.get("procedure"):
                print(f"[WARNING] No procedures found in any chart! This may cause compliance evaluation to fail.")
                print(f"[DEBUG] Extraction data summary:")
                for file_name, details in all_extraction_data.items():
                    ext_data = details.get("extraction_data", {})
                    print(f"  - {file_name}: procedures={ext_data.get('procedure', [])}")
            
            combined_extraction_json = json.dumps(combined_extraction)
            mapping_result = self.map_guidelines_for_case_text_multi_payer(
                combined_extraction_json,
                numbered_combined_chart
            )
            
            # Step 6: Create processing result
            total_usage = UsageInfo(
                input_tokens=total_extraction_usage.get("input_tokens", 0) + mapping_result["usage"]["input_tokens"],
                output_tokens=total_extraction_usage.get("output_tokens", 0) + mapping_result["usage"]["output_tokens"]
            )
            total_usage.calculate_costs(Config.INPUT_COST_PER_1K, Config.OUTPUT_COST_PER_1K)
            
            # Store original charts (without line numbers)
            original_charts = {}
            for chart in chart_data:
                original_charts[chart["file_name"]] = chart["original_text"]
            
            result = ProcessingResult(
                file_name=", ".join([os.path.basename(fp) for fp in file_paths]),
                extraction_data=combined_extraction,
                payer_results=mapping_result["result"]["payer_results"],
                total_usage=total_usage,
                total_cost=mapping_result["cost"]["total_cost_usd"],
                execution_times=mapping_result["meta"]["execution_times"],
                sources=mapping_result["sources"],
                numbered_medical_chart=numbered_combined_chart,
                original_chart=combined_chart_text
            )
            
            # Identify operative chart and create other_charts_info
            operative_chart = None
            operative_chart_name = None
            other_charts_info = {}
            
            for chart in chart_data:
                file_name = chart["file_name"]
                chart_type = chart["chart_type"]
                extraction_info = all_extraction_data.get(file_name, {}).get("extraction_data", {})
                
                if chart_type == "operative_note":
                    operative_chart = chart
                    operative_chart_name = file_name
                    print(f"[IDENTIFY] Found operative chart: {file_name}")
                else:
                    # Store extracted information from non-operative charts
                    chart_display_title = chart.get("display_title") or ChartTypeIdentifier.get_display_title(chart_type)
                    other_charts_info[file_name] = {
                        "chart_type": chart_type,
                        "display_title": chart_display_title,
                        "extraction_data": extraction_info,
                        "summary": extraction_info.get("summary", ""),
                        "diagnosis": extraction_info.get("diagnosis", []),
                        "tests": extraction_info.get("tests", []),
                        "reports": extraction_info.get("reports", []),
                        "medications": extraction_info.get("medications", []),
                        "allergies": extraction_info.get("allergies", []),
                        "risk_assessment": extraction_info.get("risk_assessment", ""),
                        "history": extraction_info.get("history", {}),
                        "physical_exam": extraction_info.get("physical_exam", {}),
                        "imaging": extraction_info.get("imaging", []),
                        "conservative_treatment": extraction_info.get("conservative_treatment", {}),
                        "functional_limitations": extraction_info.get("functional_limitations", {})
                    }
                    print(f"[INFO] Stored information from {chart_display_title} ({chart_type}): {file_name}")
            
            if operative_chart is None:
                print(f"[WARNING] No operative chart found, using first chart as fallback")
                operative_chart_name = chart_data[0]["file_name"] if chart_data else "N/A"
            
            # Add multi-chart metadata with patient matching and duplicate info
            result.multi_chart_info = {
                "total_charts": len(chart_data),
                "chart_details": all_extraction_data,
                "combined_extraction": combined_extraction,
                "operative_chart": operative_chart_name,
                "other_charts_info": other_charts_info,
                "same_patient": same_patient,
                "same_patient_reason": same_patient_reason,
                "patient_name": patient_name,
                "patient_id": patient_id,
                "duplicates": duplicates,
                "duplicate_reason": multi_chart_result.get("duplicate_reason", ""),
                "all_chart_names": all_chart_names
            }
            
            result.payer_summary = self._calculate_payer_summary(result.payer_results)
            
            # Generate improved chart
            print("[CHART IMPROVEMENT] Generating AI-improved chart...")
            try:
                improved_chart_data = self.chart_improver.improve_medical_chart(
                    original_chart=combined_chart_text,
                    processing_result=result
                )
                
                improved_chart_text = improved_chart_data.get("improved_chart", combined_chart_text)
                improved_chart_text = re.sub(r'\[ADDED\s*:\s*([^\]]+)\]\s*', r'\1', improved_chart_text, flags=re.IGNORECASE)
                improved_chart_text = FileProcessor.remove_line_numbers(improved_chart_text)
                result.improved_chart_by_ai = improved_chart_text
                
                result.enhanced_by_ai = {
                    "improvements": improved_chart_data.get("improvements", []),
                    "user_input_required": improved_chart_data.get("user_input_required", []),
                    "recommendations": improved_chart_data.get("recommendations", []),
                    "compliance_impact": improved_chart_data.get("compliance_impact", {}),
                    "success": improved_chart_data.get("success", True)
                }
                
                improvement_cost = improved_chart_data.get("cost", 0.0)
                result.total_cost += improvement_cost
                
                improvement_usage = improved_chart_data.get("usage", {})
                if improvement_usage:
                    result.total_usage.input_tokens += improvement_usage.get("input_tokens", 0)
                    result.total_usage.output_tokens += improvement_usage.get("output_tokens", 0)
                    result.total_usage.calculate_costs(Config.INPUT_COST_PER_1K, Config.OUTPUT_COST_PER_1K)
                
                print(f"[CHART IMPROVEMENT] AI chart improvement completed successfully")
            except Exception as e:
                print(f"[WARNING] Chart improvement failed: {e}")
                self.logger.warning(f"Chart improvement failed: {e}")
                result.improved_chart_by_ai = combined_chart_text
                result.enhanced_by_ai = {
                    "improvements": [],
                    "user_input_required": [],
                    "recommendations": [],
                    "compliance_impact": {},
                    "success": False,
                    "error": str(e)
                }
            
            # Calculate execution time
            execution_time = time.time() - start_time
            
            # Save outputs
            result_dict = result.__dict__.copy()
            numbered_chart = result_dict.pop('numbered_medical_chart', None)
            json_output_path = CDILogger.save_output(
                f"multi_chart_{int(time.time())}",
                result_dict,
                "json"
            )
            
            if numbered_chart:
                chart_output_path = CDILogger.save_numbered_chart(
                    f"multi_chart_{int(time.time())}",
                    numbered_chart
                )
                print(f"[SAVED] Numbered medical chart saved to: {chart_output_path}")
            
            # Log processing result
            CDILogger.log_processing_result(
                file_name=", ".join([os.path.basename(fp) for fp in file_paths]),
                payers_processed=len(result.payer_results),
                procedures_evaluated=mapping_result["result"]["procedures_evaluated"],
                total_cost=result.total_cost,
                execution_time=execution_time,
                success=True
            )
            
            print(f"[OK] Multi-chart processing completed successfully")
            self.logger.info(f"Multi-chart processing completed. Output: {json_output_path}")
            return result
            
        except Exception as e:
            execution_time = time.time() - start_time
            print(f"[ERROR] Error processing multiple charts: {e}")
            self.logger.error(f"Multi-chart processing failed: {e}")
            
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
    
    def process_directory(self, input_dir: str) -> Dict[str, Any]:
        """
        Process all files in a directory.
        
        Args:
            input_dir: Directory containing medical chart files
            
        Returns:
            Dictionary with results for all processed files
        """
        files_to_process = FileProcessor.get_files_to_process(input_dir)
        
        if not files_to_process:
            print(f"[WARNING] No supported files found in {input_dir}")
            return {}
        
        print(f"[INFO] Found {len(files_to_process)} files to process")
        
        results = {}
        for file_path in files_to_process:
            file_name = file_path.split('/')[-1]  # Get just the filename
            print(f"\n[PROCESSING] Processing {file_name}...")
            
            try:
                result = self.process_file(file_path)
                results[file_name] = result.__dict__
                print(f"[OK] {file_name} completed successfully")
            except Exception as e:
                print(f"[ERROR] {file_name} failed: {e}")
                results[file_name] = {"error": str(e)}
        
        return results
    
    def print_cache_stats(self):
        """Print cache statistics."""
        self.cache_manager.print_cache_stats()
    
    def save_cache_stats(self):
        """Save cache statistics to file."""
        self.cache_manager.save_cache_stats()
    
    def cleanup_cache(self):
        """Clean up old cache files."""
        self.cache_manager.cleanup_old_cache()
    
    def get_system_info(self) -> Dict[str, Any]:
        """Get system configuration and status information."""
        info = {
            "version": "1.0.0",
            "configured_payers": list(Config.PAYER_CONFIG.keys()),
            "cache_enabled": Config.ENABLE_CACHE,
            "cache_directory": Config.CACHE_DIR,
            "data_source": Config.DATA_SOURCE,
            "claude_model": Config.CLAUDE_MODEL_ID,
            "aws_region": Config.AWS_REGION,
        }
        
        # Add data source specific info
        if Config.DATA_SOURCE == "opensearch":
            info["opensearch_host"] = Config.OS_HOST
            info["opensearch_index"] = Config.OS_INDEX
            info["opensearch_connected"] = OpenSearchClient.ping()
        elif Config.DATA_SOURCE == "json":
            info["json_guideline_paths"] = Config.JSON_GUIDELINE_PATHS
            info["json_files_available"] = {
                payer: __import__('os').path.exists(path)
                for payer, path in Config.JSON_GUIDELINE_PATHS.items()
            }
        
        return info
