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
                usage = proc_result.get("usage", {})
                
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
        
        # Collect all sources
        all_sources = []
        for payer_sources in all_sources_by_payer.values():
            all_sources.extend(payer_sources)
        
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
