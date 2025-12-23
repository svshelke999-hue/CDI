
#!/usr/bin/env python3
"""
CDI System Evaluation Script

This script evaluates the Multi-Payer CDI Compliance Checker system by:
1. Processing test charts and measuring performance metrics
2. Analyzing compliance detection accuracy
3. Evaluating cost-effectiveness and caching efficiency
4. Generating comprehensive evaluation reports
5. Comparing results across multiple payers
6. Assessing guideline retrieval quality

Usage:
    python evaluate_cdi.py                          # Run full evaluation
    python evaluate_cdi.py --charts-dir ./Charts    # Specify test charts directory
    python evaluate_cdi.py --output-dir ./eval      # Specify output directory
    python evaluate_cdi.py --quick                  # Quick evaluation (fewer metrics)
"""

import sys
import json
import os
import time
from pathlib import Path
from typing import Dict, List, Any, Tuple
from datetime import datetime
from dataclasses import dataclass, asdict
import argparse

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from multi_payer_cdi.core import MultiPayerCDI
from multi_payer_cdi.config import Config


@dataclass
class EvaluationMetrics:
    """Metrics for CDI system evaluation."""
    # Performance metrics
    total_charts_processed: int = 0
    successful_processing: int = 0
    failed_processing: int = 0
    avg_processing_time: float = 0.0
    min_processing_time: float = 0.0
    max_processing_time: float = 0.0
    
    # Extraction metrics
    charts_with_cpt: int = 0
    charts_without_cpt: int = 0
    total_cpt_codes_extracted: int = 0
    total_procedures_extracted: int = 0
    avg_cpt_per_chart: float = 0.0
    avg_procedures_per_chart: float = 0.0
    
    # Compliance metrics
    total_compliance_checks: int = 0
    sufficient_decisions: int = 0
    insufficient_decisions: int = 0
    compliance_rate: float = 0.0
    
    # Guideline retrieval metrics
    total_guidelines_retrieved: int = 0
    avg_guidelines_per_procedure: float = 0.0
    cpt_based_searches: int = 0
    procedure_based_searches: int = 0
    
    # Evidence metrics
    total_payer_guideline_refs: int = 0
    total_chart_refs: int = 0
    avg_evidence_per_procedure: float = 0.0
    
    # Cost metrics
    total_cost_usd: float = 0.0
    avg_cost_per_chart: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    
    # Cache metrics
    cache_hit_rate: float = 0.0
    prompt_cache_hit_rate: float = 0.0
    cache_savings_usd: float = 0.0
    prompt_cache_savings_usd: float = 0.0
    
    # Payer-specific metrics
    payer_metrics: Dict[str, Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.payer_metrics is None:
            self.payer_metrics = {}


@dataclass
class ChartEvaluation:
    """Evaluation results for a single chart."""
    file_name: str
    processing_time: float
    success: bool
    error_message: str = ""
    
    # Extraction results
    cpt_codes: List[str] = None
    procedures: List[str] = None
    has_cpt: bool = False
    
    # Compliance results
    payer_results: Dict[str, Any] = None
    
    # Cost and usage
    total_cost: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    
    # Guidelines and evidence
    guidelines_retrieved: int = 0
    payer_guideline_refs: int = 0
    chart_refs: int = 0
    
    def __post_init__(self):
        if self.cpt_codes is None:
            self.cpt_codes = []
        if self.procedures is None:
            self.procedures = []
        if self.payer_results is None:
            self.payer_results = {}


class CDIEvaluator:
    """Evaluates the CDI system performance and accuracy."""
    
    def __init__(self, output_dir: str = "./evaluation_results"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.cdi_system = None
        self.chart_evaluations: List[ChartEvaluation] = []
        self.start_time = None
        self.end_time = None
        
    def initialize_system(self) -> bool:
        """Initialize the CDI system."""
        try:
            print("=" * 80)
            print("Initializing CDI System for Evaluation")
            print("=" * 80)
            self.cdi_system = MultiPayerCDI()
            print("[OK] CDI system initialized successfully\n")
            return True
        except Exception as e:
            print(f"[ERROR] Failed to initialize CDI system: {e}")
            return False
    
    def evaluate_chart(self, chart_path: str) -> ChartEvaluation:
        """Evaluate a single chart."""
        file_name = os.path.basename(chart_path)
        print(f"\n{'='*80}")
        print(f"Evaluating: {file_name}")
        print(f"{'='*80}")
        
        start_time = time.time()
        
        try:
            # Process the chart
            result = self.cdi_system.process_file(chart_path)
            processing_time = time.time() - start_time
            
            # Extract evaluation data
            extraction_data = result.extraction_data or {}
            cpt_codes = extraction_data.get("cpt", [])
            procedures = extraction_data.get("procedure", [])
            has_cpt = extraction_data.get("has_cpt_codes", False)
            
            # Count guidelines and evidence
            guidelines_retrieved = 0
            payer_guideline_refs = 0
            chart_refs = 0
            
            for payer_key, payer_result in result.payer_results.items():
                if isinstance(payer_result, dict):
                    procedure_results = payer_result.get('procedure_results', [])
                    for proc_result in procedure_results:
                        if isinstance(proc_result, dict):
                            guideline_info = proc_result.get('guideline_availability', {})
                            guidelines_retrieved += guideline_info.get('search_hits', 0)
                            
                            sources = proc_result.get('sources', [])
                            for source in sources:
                                if isinstance(source, dict):
                                    payer_guideline_refs += len(source.get('payer_guideline_reference', []))
                            
                            chart_refs += len(proc_result.get('medical_chart_reference', []))
            
            evaluation = ChartEvaluation(
                file_name=file_name,
                processing_time=processing_time,
                success=True,
                cpt_codes=cpt_codes,
                procedures=procedures,
                has_cpt=has_cpt,
                payer_results=result.payer_results,
                total_cost=result.total_cost,
                input_tokens=result.total_usage.input_tokens if hasattr(result.total_usage, 'input_tokens') else 0,
                output_tokens=result.total_usage.output_tokens if hasattr(result.total_usage, 'output_tokens') else 0,
                guidelines_retrieved=guidelines_retrieved,
                payer_guideline_refs=payer_guideline_refs,
                chart_refs=chart_refs
            )
            
            print(f"[OK] Processing completed in {processing_time:.2f}s")
            print(f"     CPT Codes: {len(cpt_codes)}, Procedures: {len(procedures)}")
            print(f"     Guidelines Retrieved: {guidelines_retrieved}")
            print(f"     Cost: ${result.total_cost:.4f}")
            
            return evaluation
            
        except Exception as e:
            processing_time = time.time() - start_time
            print(f"[ERROR] Failed to process chart: {e}")
            
            return ChartEvaluation(
                file_name=file_name,
                processing_time=processing_time,
                success=False,
                error_message=str(e)
            )
    
    def evaluate_directory(self, charts_dir: str) -> List[ChartEvaluation]:
        """Evaluate all charts in a directory."""
        charts_path = Path(charts_dir)
        
        if not charts_path.exists():
            print(f"[ERROR] Charts directory not found: {charts_dir}")
            return []
        
        # Find all supported chart files
        chart_files = []
        for ext in ['.txt', '.pdf', '.doc', '.docx']:
            chart_files.extend(charts_path.glob(f"*{ext}"))
        
        if not chart_files:
            print(f"[WARNING] No chart files found in {charts_dir}")
            return []
        
        print(f"\nFound {len(chart_files)} chart file(s) to evaluate")
        
        evaluations = []
        for chart_file in chart_files:
            evaluation = self.evaluate_chart(str(chart_file))
            evaluations.append(evaluation)
            self.chart_evaluations.append(evaluation)
        
        return evaluations
    
    def calculate_metrics(self) -> EvaluationMetrics:
        """Calculate comprehensive evaluation metrics."""
        metrics = EvaluationMetrics()
        
        if not self.chart_evaluations:
            return metrics
        
        # Performance metrics
        metrics.total_charts_processed = len(self.chart_evaluations)
        metrics.successful_processing = sum(1 for e in self.chart_evaluations if e.success)
        metrics.failed_processing = metrics.total_charts_processed - metrics.successful_processing
        
        successful_evals = [e for e in self.chart_evaluations if e.success]
        
        if successful_evals:
            processing_times = [e.processing_time for e in successful_evals]
            metrics.avg_processing_time = sum(processing_times) / len(processing_times)
            metrics.min_processing_time = min(processing_times)
            metrics.max_processing_time = max(processing_times)
            
            # Extraction metrics
            metrics.charts_with_cpt = sum(1 for e in successful_evals if e.has_cpt)
            metrics.charts_without_cpt = len(successful_evals) - metrics.charts_with_cpt
            metrics.total_cpt_codes_extracted = sum(len(e.cpt_codes) for e in successful_evals)
            metrics.total_procedures_extracted = sum(len(e.procedures) for e in successful_evals)
            metrics.avg_cpt_per_chart = metrics.total_cpt_codes_extracted / len(successful_evals)
            metrics.avg_procedures_per_chart = metrics.total_procedures_extracted / len(successful_evals)
            
            # Compliance metrics
            total_sufficient = 0
            total_insufficient = 0
            payer_stats = {}
            
            for eval_result in successful_evals:
                for payer_key, payer_result in eval_result.payer_results.items():
                    if isinstance(payer_result, dict):
                        payer_name = payer_result.get('payer_name', payer_key)
                        
                        if payer_name not in payer_stats:
                            payer_stats[payer_name] = {
                                'total_procedures': 0,
                                'sufficient': 0,
                                'insufficient': 0,
                                'guidelines_retrieved': 0,
                                'total_cost': 0.0
                            }
                        
                        procedure_results = payer_result.get('procedure_results', [])
                        for proc_result in procedure_results:
                            if isinstance(proc_result, dict):
                                metrics.total_compliance_checks += 1
                                payer_stats[payer_name]['total_procedures'] += 1
                                
                                decision = proc_result.get('decision', '').lower()
                                if 'sufficient' in decision:
                                    total_sufficient += 1
                                    payer_stats[payer_name]['sufficient'] += 1
                                elif 'insufficient' in decision:
                                    total_insufficient += 1
                                    payer_stats[payer_name]['insufficient'] += 1
                                
                                guideline_info = proc_result.get('guideline_availability', {})
                                guidelines = guideline_info.get('search_hits', 0)
                                payer_stats[payer_name]['guidelines_retrieved'] += guidelines
            
            metrics.sufficient_decisions = total_sufficient
            metrics.insufficient_decisions = total_insufficient
            if metrics.total_compliance_checks > 0:
                metrics.compliance_rate = (total_sufficient / metrics.total_compliance_checks) * 100
            
            # Calculate payer-specific metrics
            for payer_name, stats in payer_stats.items():
                if stats['total_procedures'] > 0:
                    stats['compliance_rate'] = (stats['sufficient'] / stats['total_procedures']) * 100
                    stats['avg_guidelines_per_procedure'] = stats['guidelines_retrieved'] / stats['total_procedures']
                else:
                    stats['compliance_rate'] = 0.0
                    stats['avg_guidelines_per_procedure'] = 0.0
            
            metrics.payer_metrics = payer_stats
            
            # Guideline and evidence metrics
            metrics.total_guidelines_retrieved = sum(e.guidelines_retrieved for e in successful_evals)
            metrics.total_payer_guideline_refs = sum(e.payer_guideline_refs for e in successful_evals)
            metrics.total_chart_refs = sum(e.chart_refs for e in successful_evals)
            
            if metrics.total_compliance_checks > 0:
                metrics.avg_guidelines_per_procedure = metrics.total_guidelines_retrieved / metrics.total_compliance_checks
                metrics.avg_evidence_per_procedure = (metrics.total_payer_guideline_refs + metrics.total_chart_refs) / metrics.total_compliance_checks
            
            metrics.cpt_based_searches = metrics.charts_with_cpt
            metrics.procedure_based_searches = metrics.charts_without_cpt
            
            # Cost metrics
            metrics.total_cost_usd = sum(e.total_cost for e in successful_evals)
            metrics.avg_cost_per_chart = metrics.total_cost_usd / len(successful_evals)
            metrics.total_input_tokens = sum(e.input_tokens for e in successful_evals)
            metrics.total_output_tokens = sum(e.output_tokens for e in successful_evals)
            
            # Cache metrics (from CDI system)
            if self.cdi_system and hasattr(self.cdi_system, 'cache_manager'):
                cache_stats = self.cdi_system.cache_manager.stats
                total_hits = cache_stats.extraction_hits + cache_stats.compliance_hits
                total_requests = total_hits + cache_stats.extraction_misses + cache_stats.compliance_misses
                
                if total_requests > 0:
                    metrics.cache_hit_rate = (total_hits / total_requests) * 100
                
                metrics.cache_savings_usd = cache_stats.total_savings_usd
                
                # Prompt cache metrics
                total_prompt_calls = cache_stats.prompt_cache_writes + cache_stats.prompt_cache_reads
                if total_prompt_calls > 0:
                    metrics.prompt_cache_hit_rate = (cache_stats.prompt_cache_reads / total_prompt_calls) * 100
                
                metrics.prompt_cache_savings_usd = cache_stats.prompt_cache_savings_usd
        
        return metrics
    
    def generate_report(self, metrics: EvaluationMetrics) -> str:
        """Generate a comprehensive evaluation report."""
        report_lines = []
        
        report_lines.append("=" * 80)
        report_lines.append("CDI SYSTEM EVALUATION REPORT")
        report_lines.append("=" * 80)
        report_lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report_lines.append(f"Evaluation Duration: {(self.end_time - self.start_time):.2f} seconds")
        report_lines.append("")
        
        # Performance Summary
        report_lines.append("=" * 80)
        report_lines.append("PERFORMANCE SUMMARY")
        report_lines.append("=" * 80)
        report_lines.append(f"Total Charts Processed:     {metrics.total_charts_processed}")
        report_lines.append(f"Successful:                 {metrics.successful_processing} ({metrics.successful_processing/metrics.total_charts_processed*100:.1f}%)")
        report_lines.append(f"Failed:                     {metrics.failed_processing}")
        report_lines.append(f"Avg Processing Time:        {metrics.avg_processing_time:.2f}s")
        report_lines.append(f"Min Processing Time:        {metrics.min_processing_time:.2f}s")
        report_lines.append(f"Max Processing Time:        {metrics.max_processing_time:.2f}s")
        report_lines.append("")
        
        # Extraction Summary
        report_lines.append("=" * 80)
        report_lines.append("EXTRACTION SUMMARY")
        report_lines.append("=" * 80)
        report_lines.append(f"Charts with CPT Codes:      {metrics.charts_with_cpt}")
        report_lines.append(f"Charts without CPT Codes:   {metrics.charts_without_cpt}")
        report_lines.append(f"Total CPT Codes Extracted:  {metrics.total_cpt_codes_extracted}")
        report_lines.append(f"Total Procedures Extracted: {metrics.total_procedures_extracted}")
        report_lines.append(f"Avg CPT per Chart:          {metrics.avg_cpt_per_chart:.2f}")
        report_lines.append(f"Avg Procedures per Chart:   {metrics.avg_procedures_per_chart:.2f}")
        report_lines.append("")
        
        # Compliance Summary
        report_lines.append("=" * 80)
        report_lines.append("COMPLIANCE EVALUATION SUMMARY")
        report_lines.append("=" * 80)
        report_lines.append(f"Total Compliance Checks:    {metrics.total_compliance_checks}")
        report_lines.append(f"Sufficient Decisions:       {metrics.sufficient_decisions} ({metrics.compliance_rate:.1f}%)")
        report_lines.append(f"Insufficient Decisions:     {metrics.insufficient_decisions}")
        report_lines.append("")
        
        # Payer-Specific Metrics
        if metrics.payer_metrics:
            report_lines.append("=" * 80)
            report_lines.append("PAYER-SPECIFIC METRICS")
            report_lines.append("=" * 80)
            for payer_name, stats in metrics.payer_metrics.items():
                report_lines.append(f"\n{payer_name}:")
                report_lines.append(f"  Procedures Evaluated:       {stats['total_procedures']}")
                report_lines.append(f"  Sufficient:                 {stats['sufficient']} ({stats['compliance_rate']:.1f}%)")
                report_lines.append(f"  Insufficient:               {stats['insufficient']}")
                report_lines.append(f"  Guidelines Retrieved:       {stats['guidelines_retrieved']}")
                report_lines.append(f"  Avg Guidelines/Procedure:   {stats['avg_guidelines_per_procedure']:.2f}")
            report_lines.append("")
        
        # Guideline Retrieval Summary
        report_lines.append("=" * 80)
        report_lines.append("GUIDELINE RETRIEVAL SUMMARY")
        report_lines.append("=" * 80)
        report_lines.append(f"Total Guidelines Retrieved: {metrics.total_guidelines_retrieved}")
        report_lines.append(f"Avg Guidelines/Procedure:   {metrics.avg_guidelines_per_procedure:.2f}")
        report_lines.append(f"CPT-Based Searches:         {metrics.cpt_based_searches}")
        report_lines.append(f"Procedure-Based Searches:   {metrics.procedure_based_searches}")
        report_lines.append("")
        
        # Evidence Summary
        report_lines.append("=" * 80)
        report_lines.append("EVIDENCE EXTRACTION SUMMARY")
        report_lines.append("=" * 80)
        report_lines.append(f"Payer Guideline References: {metrics.total_payer_guideline_refs}")
        report_lines.append(f"Medical Chart References:   {metrics.total_chart_refs}")
        report_lines.append(f"Avg Evidence/Procedure:     {metrics.avg_evidence_per_procedure:.2f}")
        report_lines.append("")
        
        # Cost Summary
        report_lines.append("=" * 80)
        report_lines.append("COST ANALYSIS")
        report_lines.append("=" * 80)
        report_lines.append(f"Total Cost:                 ${metrics.total_cost_usd:.4f}")
        report_lines.append(f"Avg Cost per Chart:         ${metrics.avg_cost_per_chart:.4f}")
        report_lines.append(f"Total Input Tokens:         {metrics.total_input_tokens:,}")
        report_lines.append(f"Total Output Tokens:        {metrics.total_output_tokens:,}")
        report_lines.append("")
        
        # Cache Performance
        report_lines.append("=" * 80)
        report_lines.append("CACHE PERFORMANCE")
        report_lines.append("=" * 80)
        report_lines.append(f"File Cache Hit Rate:        {metrics.cache_hit_rate:.1f}%")
        report_lines.append(f"File Cache Savings:         ${metrics.cache_savings_usd:.4f}")
        report_lines.append(f"Prompt Cache Hit Rate:      {metrics.prompt_cache_hit_rate:.1f}%")
        report_lines.append(f"Prompt Cache Savings:       ${metrics.prompt_cache_savings_usd:.4f}")
        total_savings = metrics.cache_savings_usd + metrics.prompt_cache_savings_usd
        report_lines.append(f"Total Cache Savings:        ${total_savings:.4f}")
        report_lines.append("")
        
        # System Configuration
        report_lines.append("=" * 80)
        report_lines.append("SYSTEM CONFIGURATION")
        report_lines.append("=" * 80)
        report_lines.append(f"Data Source:                {Config.DATA_SOURCE}")
        report_lines.append(f"Claude Model:               {Config.CLAUDE_MODEL_ID}")
        report_lines.append(f"Cache Enabled:              {Config.ENABLE_CACHE}")
        report_lines.append(f"Prompt Caching Enabled:     {Config.ENABLE_PROMPT_CACHING}")
        report_lines.append("")
        
        report_lines.append("=" * 80)
        report_lines.append("END OF EVALUATION REPORT")
        report_lines.append("=" * 80)
        
        return "\n".join(report_lines)
    
    def save_results(self, metrics: EvaluationMetrics, report: str):
        """Save evaluation results to files."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save text report
        report_file = self.output_dir / f"evaluation_report_{timestamp}.txt"
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"\n[SAVED] Report: {report_file}")
        
        # Save JSON metrics
        metrics_file = self.output_dir / f"evaluation_metrics_{timestamp}.json"
        with open(metrics_file, 'w', encoding='utf-8') as f:
            json.dump(asdict(metrics), f, indent=2, default=str)
        print(f"[SAVED] Metrics: {metrics_file}")
        
        # Save detailed chart evaluations
        evaluations_file = self.output_dir / f"chart_evaluations_{timestamp}.json"
        evaluations_data = [asdict(e) for e in self.chart_evaluations]
        with open(evaluations_file, 'w', encoding='utf-8') as f:
            json.dump(evaluations_data, f, indent=2, default=str)
        print(f"[SAVED] Chart Evaluations: {evaluations_file}")
        
        # Save cache statistics
        if self.cdi_system:
            self.cdi_system.save_cache_stats()
            print(f"[SAVED] Cache Statistics")
    
    def run_evaluation(self, charts_dir: str) -> EvaluationMetrics:
        """Run complete evaluation."""
        self.start_time = time.time()
        
        print("\n" + "=" * 80)
        print("STARTING CDI SYSTEM EVALUATION")
        print("=" * 80)
        print(f"Charts Directory: {charts_dir}")
        print(f"Output Directory: {self.output_dir}")
        print("")
        
        # Initialize system
        if not self.initialize_system():
            return EvaluationMetrics()
        
        # Evaluate charts
        self.evaluate_directory(charts_dir)
        
        # Calculate metrics
        print("\n" + "=" * 80)
        print("CALCULATING METRICS")
        print("=" * 80)
        metrics = self.calculate_metrics()
        
        self.end_time = time.time()
        
        # Generate and save report
        print("\n" + "=" * 80)
        print("GENERATING REPORT")
        print("=" * 80)
        report = self.generate_report(metrics)
        self.save_results(metrics, report)
        
        # Print report to console
        print("\n" + report)
        
        # Print cache statistics
        if self.cdi_system:
            self.cdi_system.print_cache_stats()
        
        return metrics


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Evaluate the Multi-Payer CDI Compliance Checker system",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        '--charts-dir',
        type=str,
        default='./Charts',
        help='Directory containing test charts (default: ./Charts)'
    )
    
    parser.add_argument(
        '--output-dir',
        type=str,
        default='./evaluation_results',
        help='Directory for evaluation results (default: ./evaluation_results)'
    )
    
    parser.add_argument(
        '--quick',
        action='store_true',
        help='Run quick evaluation with fewer metrics'
    )
    
    args = parser.parse_args()
    
    try:
        # Create evaluator
        evaluator = CDIEvaluator(output_dir=args.output_dir)
        
        # Run evaluation
        metrics = evaluator.run_evaluation(args.charts_dir)
        
        # Print summary
        print("\n" + "=" * 80)
        print("EVALUATION COMPLETE")
        print("=" * 80)
        print(f"Charts Processed:    {metrics.total_charts_processed}")
        print(f"Success Rate:        {metrics.successful_processing/metrics.total_charts_processed*100:.1f}%")
        print(f"Compliance Rate:     {metrics.compliance_rate:.1f}%")
        print(f"Total Cost:          ${metrics.total_cost_usd:.4f}")
        print(f"Avg Cost per Chart:  ${metrics.avg_cost_per_chart:.4f}")
        print(f"Cache Savings:       ${metrics.cache_savings_usd + metrics.prompt_cache_savings_usd:.4f}")
        print("=" * 80)
        
    except KeyboardInterrupt:
        print("\n[INTERRUPTED] Evaluation interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Evaluation failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()