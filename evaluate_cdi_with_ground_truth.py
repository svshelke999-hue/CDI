#!/usr/bin/env python3
"""
CDI System Evaluation Script with Ground Truth Comparison

This script evaluates the Multi-Payer CDI Compliance Checker system by:
1. Processing synthetic medical charts through the CDI system
2. Comparing CDI recommendations against ground truth improvement notes
3. Using LLM to assess quality, coverage, and accuracy of recommendations
4. Generating comprehensive evaluation reports with metrics

Usage:
    python evaluate_cdi_with_ground_truth.py                          # Run full evaluation
    python evaluate_cdi_with_ground_truth.py --process-charts          # Process charts first
    python evaluate_cdi_with_ground_truth.py --charts-dir ./Synthetic_data medical chart
    python evaluate_cdi_with_ground_truth.py --output-dir ./evaluation_results
"""

import sys
import json
import os
import time
import re
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional
from datetime import datetime
from dataclasses import dataclass, asdict
import argparse

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from multi_payer_cdi.core import MultiPayerCDI
from multi_payer_cdi.config import Config
from multi_payer_cdi.bedrock_client import BedrockClient


@dataclass
class ImprovementNote:
    """Structure for improvement notes."""
    chart_name: str
    primary_focus: List[str]
    recommended_improvements: List[str]
    coding_impact: List[str]


@dataclass
class CDIRecommendation:
    """Structure for CDI recommendations extracted from results."""
    payer: str
    procedure: str
    decision: str
    primary_reasons: List[str]
    missing_requirements: List[str]
    suggestions: List[str]
    requirement_checklist: List[Dict[str, Any]]


@dataclass
class LLMEvaluationResult:
    """Results from LLM evaluation."""
    coverage_score: float  # 0-100: How many expected improvements were addressed
    quality_score: float  # 0-100: How well recommendations match expected improvements
    completeness_score: float  # 0-100: Are all key areas covered
    accuracy_score: float  # 0-100: Are recommendations medically appropriate
    detailed_analysis: str
    matched_improvements: List[str]
    missed_improvements: List[str]
    extra_recommendations: List[str]
    strengths: List[str]
    weaknesses: List[str]


@dataclass
class ChartEvaluationResult:
    """Evaluation results for a single chart."""
    chart_name: str
    chart_path: str
    improvement_note_path: str
    processing_success: bool
    processing_time: float
    error_message: str = ""
    
    # CDI Results
    cdi_recommendations: List[CDIRecommendation] = None
    extraction_data: Dict[str, Any] = None
    
    # Ground Truth
    improvement_note: ImprovementNote = None
    
    # LLM Evaluation
    llm_evaluation: LLMEvaluationResult = None
    
    # Overall scores
    overall_score: float = 0.0
    
    def __post_init__(self):
        if self.cdi_recommendations is None:
            self.cdi_recommendations = []


@dataclass
class EvaluationMetrics:
    """Overall evaluation metrics."""
    total_charts: int = 0
    successful_processing: int = 0
    failed_processing: int = 0
    
    # Average scores
    avg_coverage_score: float = 0.0
    avg_quality_score: float = 0.0
    avg_completeness_score: float = 0.0
    avg_accuracy_score: float = 0.0
    avg_overall_score: float = 0.0
    
    # Coverage metrics
    total_expected_improvements: int = 0
    total_matched_improvements: int = 0
    total_missed_improvements: int = 0
    total_extra_recommendations: int = 0
    improvement_coverage_rate: float = 0.0
    
    # Processing metrics
    avg_processing_time: float = 0.0
    total_processing_time: float = 0.0
    
    # Cost metrics
    total_cost_usd: float = 0.0
    total_evaluation_cost_usd: float = 0.0
    
    # Payer-specific metrics
    payer_performance: Dict[str, Dict[str, float]] = None
    
    def __post_init__(self):
        if self.payer_performance is None:
            self.payer_performance = {}


class CDIGroundTruthEvaluator:
    """Evaluates CDI system against ground truth improvement notes."""
    
    def __init__(self, output_dir: str = "./evaluation_results", existing_outputs_dir: Optional[str] = None):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.existing_outputs_dir = existing_outputs_dir
        self.cdi_system = None
        self.chart_evaluations: List[ChartEvaluationResult] = []
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
            import traceback
            traceback.print_exc()
            return False
    
    def load_improvement_note(self, note_path: str) -> Optional[ImprovementNote]:
        """Load and parse improvement note file."""
        try:
            with open(note_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Parse the improvement note
            chart_name = ""
            primary_focus = []
            recommended_improvements = []
            coding_impact = []
            
            lines = content.split('\n')
            current_section = None
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                if line.startswith("CHART:"):
                    chart_name = line.replace("CHART:", "").strip()
                elif line == "PRIMARY CDI FOCUS:":
                    current_section = "primary_focus"
                elif line == "RECOMMENDED IMPROVEMENTS:":
                    current_section = "recommendations"
                elif line == "CODING IMPACT:":
                    current_section = "coding_impact"
                elif line.startswith("-"):
                    if current_section == "primary_focus":
                        primary_focus.append(line[1:].strip())
                elif line and line[0].isdigit() and '.' in line:
                    if current_section == "recommendations":
                        # Extract text after number and period
                        improvement_text = line.split('.', 1)[1].strip() if '.' in line else line
                        recommended_improvements.append(improvement_text)
                elif current_section == "coding_impact" and line.startswith("-"):
                    coding_impact.append(line[1:].strip())
            
            return ImprovementNote(
                chart_name=chart_name,
                primary_focus=primary_focus,
                recommended_improvements=recommended_improvements,
                coding_impact=coding_impact
            )
        except Exception as e:
            print(f"[ERROR] Failed to load improvement note {note_path}: {e}")
            return None
    
    def extract_cdi_recommendations(self, processing_result) -> List[CDIRecommendation]:
        """Extract CDI recommendations from processing result."""
        recommendations = []
        
        if not hasattr(processing_result, 'payer_results'):
            return recommendations
        
        for payer_key, payer_result in processing_result.payer_results.items():
            if not isinstance(payer_result, dict):
                continue
            
            payer_name = payer_result.get('payer_name', payer_key)
            procedure_results = payer_result.get('procedure_results', [])
            
            for proc_result in procedure_results:
                if not isinstance(proc_result, dict):
                    continue
                
                procedure = proc_result.get('procedure_evaluated', 'Unknown')
                decision = proc_result.get('decision', 'Unknown')
                primary_reasons = proc_result.get('primary_reasons', [])
                
                # Extract missing requirements and suggestions
                missing_requirements = []
                suggestions = []
                requirement_checklist = proc_result.get('requirement_checklist', [])
                
                for req in requirement_checklist:
                    if isinstance(req, dict):
                        status = req.get('status', '').lower()
                        if status in ['not met', 'partially met', 'missing']:
                            req_id = req.get('requirement_id', '')
                            missing_to_meet = req.get('missing_to_meet', '')
                            suggestion = req.get('suggestion', '')
                            
                            if missing_to_meet:
                                missing_requirements.append(f"{req_id}: {missing_to_meet}")
                            if suggestion:
                                suggestions.append(suggestion)
                
                recommendation = CDIRecommendation(
                    payer=payer_name,
                    procedure=procedure,
                    decision=decision,
                    primary_reasons=primary_reasons,
                    missing_requirements=missing_requirements,
                    suggestions=suggestions,
                    requirement_checklist=requirement_checklist
                )
                recommendations.append(recommendation)
        
        return recommendations
    
    def evaluate_with_llm(
        self, 
        improvement_note: ImprovementNote,
        cdi_recommendations: List[CDIRecommendation],
        original_chart: str
    ) -> LLMEvaluationResult:
        """Use LLM to evaluate CDI recommendations against ground truth."""
        
        # Build prompt for LLM evaluation
        recommendations_text = self._format_recommendations(cdi_recommendations)
        improvements_text = "\n".join([
            f"{i+1}. {imp}" for i, imp in enumerate(improvement_note.recommended_improvements)
        ])
        primary_focus_text = "\n".join([
            f"- {focus}" for focus in improvement_note.primary_focus
        ])
        
        evaluation_prompt = f"""You are an expert Clinical Documentation Improvement (CDI) evaluator. Your task is to evaluate how well CDI system recommendations match the expected improvements for a medical chart.

ORIGINAL CHART:
{original_chart[:2000]}...

EXPECTED IMPROVEMENTS (Ground Truth):
Primary CDI Focus:
{primary_focus_text}

Recommended Improvements:
{improvements_text}

CDI SYSTEM RECOMMENDATIONS:
{recommendations_text}

EVALUATION TASK:
Evaluate the CDI system recommendations against the expected improvements. Consider:

1. COVERAGE (0-100): How many of the expected improvements were addressed by the CDI recommendations?
   - Count how many expected improvements have corresponding recommendations
   - Calculate: (matched improvements / total expected improvements) * 100

2. QUALITY (0-100): How well do the CDI recommendations match the expected improvements in terms of:
   - Specificity and detail level
   - Medical accuracy
   - Actionability
   - Alignment with CDI best practices

3. COMPLETENESS (0-100): Are all key areas from the primary CDI focus covered?
   - Check if all primary focus areas are addressed
   - Assess if recommendations cover the full scope needed

4. ACCURACY (0-100): Are the recommendations medically appropriate and clinically sound?
   - Medical correctness
   - Clinical relevance
   - Appropriate level of detail

Provide your evaluation in the following JSON format:
{{
    "coverage_score": <0-100>,
    "quality_score": <0-100>,
    "completeness_score": <0-100>,
    "accuracy_score": <0-100>,
    "detailed_analysis": "<comprehensive analysis text>",
    "matched_improvements": ["<list of expected improvements that were matched>"],
    "missed_improvements": ["<list of expected improvements that were missed>"],
    "extra_recommendations": ["<list of recommendations not in expected improvements>"],
    "strengths": ["<list of strengths>"],
    "weaknesses": ["<list of weaknesses>"]
}}

Be thorough and specific in your analysis. Focus on actionable insights."""
        
        try:
            print(f"    [LLM] Evaluating recommendations with Claude...")
            response, usage_info = BedrockClient.call_claude(
                evaluation_prompt,
                max_tokens=4000,
                temperature=0.1,
                system_prompt="You are an expert CDI evaluator. Provide detailed, accurate evaluations in JSON format."
            )
            
            # Parse JSON response
            # Try to extract JSON from response
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                eval_data = json.loads(json_str)
            else:
                # Fallback: try to parse entire response
                eval_data = json.loads(response)
            
            # Calculate cost
            cost = (
                (usage_info.get("input_tokens", 0) / 1000 * Config.INPUT_COST_PER_1K) +
                (usage_info.get("output_tokens", 0) / 1000 * Config.OUTPUT_COST_PER_1K)
            )
            
            result = LLMEvaluationResult(
                coverage_score=float(eval_data.get("coverage_score", 0)),
                quality_score=float(eval_data.get("quality_score", 0)),
                completeness_score=float(eval_data.get("completeness_score", 0)),
                accuracy_score=float(eval_data.get("accuracy_score", 0)),
                detailed_analysis=eval_data.get("detailed_analysis", ""),
                matched_improvements=eval_data.get("matched_improvements", []),
                missed_improvements=eval_data.get("missed_improvements", []),
                extra_recommendations=eval_data.get("extra_recommendations", []),
                strengths=eval_data.get("strengths", []),
                weaknesses=eval_data.get("weaknesses", [])
            )
            
            return result, cost
            
        except Exception as e:
            print(f"    [ERROR] LLM evaluation failed: {e}")
            import traceback
            traceback.print_exc()
            
            # Return default result
            return LLMEvaluationResult(
                coverage_score=0.0,
                quality_score=0.0,
                completeness_score=0.0,
                accuracy_score=0.0,
                detailed_analysis=f"Evaluation failed: {str(e)}",
                matched_improvements=[],
                missed_improvements=improvement_note.recommended_improvements,
                extra_recommendations=[],
                strengths=[],
                weaknesses=[f"Evaluation error: {str(e)}"]
            ), 0.0
    
    def _format_recommendations(self, recommendations: List[CDIRecommendation]) -> str:
        """Format CDI recommendations for LLM prompt."""
        if not recommendations:
            return "No recommendations provided."
        
        formatted = []
        for i, rec in enumerate(recommendations, 1):
            formatted.append(f"\n{i}. PAYER: {rec.payer}")
            formatted.append(f"   PROCEDURE: {rec.procedure}")
            formatted.append(f"   DECISION: {rec.decision}")
            if rec.primary_reasons:
                formatted.append(f"   PRIMARY REASONS:")
                for reason in rec.primary_reasons:
                    formatted.append(f"     - {reason}")
            if rec.missing_requirements:
                formatted.append(f"   MISSING REQUIREMENTS:")
                for req in rec.missing_requirements:
                    formatted.append(f"     - {req}")
            if rec.suggestions:
                formatted.append(f"   SUGGESTIONS:")
                for sug in rec.suggestions:
                    formatted.append(f"     - {sug}")
        
        return "\n".join(formatted)
    
    def find_matching_chart_and_note(self, charts_dir: str, notes_dir: str) -> List[Tuple[str, str]]:
        """Find matching chart and improvement note files."""
        charts_path = Path(charts_dir)
        notes_path = Path(notes_dir)
        
        if not charts_path.exists():
            print(f"[ERROR] Charts directory not found: {charts_dir}")
            return []
        
        if not notes_path.exists():
            print(f"[ERROR] Improvement notes directory not found: {notes_dir}")
            return []
        
        # Find all chart files
        chart_files = list(charts_path.glob("*.txt"))
        
        matches = []
        for chart_file in chart_files:
            # Extract chart number/name
            chart_name = chart_file.stem
            # Look for matching improvement note
            # Pattern: chart_XX_*.txt -> chart_XX_*_improvement.txt
            note_pattern = chart_name.replace(".txt", "") + "_improvement.txt"
            note_file = notes_path / note_pattern
            
            if note_file.exists():
                matches.append((str(chart_file), str(note_file)))
            else:
                print(f"[WARNING] No matching improvement note for {chart_file.name}")
        
        return matches
    
    def process_chart(self, chart_path: str, process_if_needed: bool = True) -> Optional[Any]:
        """Process chart through CDI system or load existing result."""
        chart_name = Path(chart_path).stem
        
        # Check for existing output files
        # Use provided directory or fall back to Config.OUTPUT_DIR
        if self.existing_outputs_dir:
            output_dir = Path(self.existing_outputs_dir)
        else:
            output_dir = Path(Config.OUTPUT_DIR)
        
        if output_dir.exists():
            # Look for most recent output file for this chart
            pattern = f"*{chart_name}*.json"
            output_files = sorted(output_dir.glob(pattern), key=os.path.getmtime, reverse=True)
            
            if output_files and not process_if_needed:
                print(f"    [INFO] Loading existing result: {output_files[0].name}")
                try:
                    with open(output_files[0], 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    # Convert to ProcessingResult-like object
                    class MockResult:
                        def __init__(self, data):
                            self.file_name = data.get('file_name', '')
                            self.extraction_data = data.get('extraction_data', {})
                            self.payer_results = data.get('payer_results', {})
                            self.total_cost = data.get('total_cost', 0.0)
                            self.total_usage = type('obj', (object,), {
                                'input_tokens': data.get('total_usage', {}).get('input_tokens', 0),
                                'output_tokens': data.get('total_usage', {}).get('output_tokens', 0)
                            })()
                    return MockResult(data)
                except Exception as e:
                    print(f"    [WARNING] Failed to load existing result: {e}")
        
        # Process chart through CDI system
        if not self.cdi_system:
            if not self.initialize_system():
                return None
        
        print(f"    [INFO] Processing chart through CDI system...")
        try:
            result = self.cdi_system.process_file(chart_path)
            return result
        except Exception as e:
            print(f"    [ERROR] Failed to process chart: {e}")
            return None
    
    def evaluate_chart(
        self, 
        chart_path: str, 
        improvement_note_path: str,
        process_chart: bool = True
    ) -> ChartEvaluationResult:
        """Evaluate a single chart against its improvement note."""
        chart_name = Path(chart_path).stem
        print(f"\n{'='*80}")
        print(f"Evaluating: {chart_name}")
        print(f"{'='*80}")
        
        start_time = time.time()
        
        # Load improvement note
        improvement_note = self.load_improvement_note(improvement_note_path)
        if not improvement_note:
            return ChartEvaluationResult(
                chart_name=chart_name,
                chart_path=chart_path,
                improvement_note_path=improvement_note_path,
                processing_success=False,
                processing_time=time.time() - start_time,
                error_message="Failed to load improvement note"
            )
        
        # Process chart
        processing_result = self.process_chart(chart_path, process_if_needed=process_chart)
        processing_time = time.time() - start_time
        
        if not processing_result:
            return ChartEvaluationResult(
                chart_name=chart_name,
                chart_path=chart_path,
                improvement_note_path=improvement_note_path,
                processing_success=False,
                processing_time=processing_time,
                error_message="Failed to process chart",
                improvement_note=improvement_note
            )
        
        # Extract CDI recommendations
        cdi_recommendations = self.extract_cdi_recommendations(processing_result)
        
        # Load original chart text
        try:
            with open(chart_path, 'r', encoding='utf-8') as f:
                original_chart = f.read()
        except Exception as e:
            print(f"    [WARNING] Failed to load original chart: {e}")
            original_chart = ""
        
        # Evaluate with LLM
        llm_evaluation, eval_cost = self.evaluate_with_llm(
            improvement_note,
            cdi_recommendations,
            original_chart
        )
        
        # Calculate overall score (weighted average)
        overall_score = (
            llm_evaluation.coverage_score * 0.3 +
            llm_evaluation.quality_score * 0.3 +
            llm_evaluation.completeness_score * 0.2 +
            llm_evaluation.accuracy_score * 0.2
        )
        
        # Get processing cost
        processing_cost = getattr(processing_result, 'total_cost', 0.0) if processing_result else 0.0
        
        result = ChartEvaluationResult(
            chart_name=chart_name,
            chart_path=chart_path,
            improvement_note_path=improvement_note_path,
            processing_success=True,
            processing_time=processing_time,
            cdi_recommendations=cdi_recommendations,
            extraction_data=processing_result.extraction_data if hasattr(processing_result, 'extraction_data') else {},
            improvement_note=improvement_note,
            llm_evaluation=llm_evaluation,
            overall_score=overall_score
        )
        
        # Store evaluation cost for metrics calculation
        result._eval_cost = eval_cost
        result._processing_cost = processing_cost
        
        print(f"    [OK] Evaluation completed")
        print(f"         Coverage: {llm_evaluation.coverage_score:.1f}%")
        print(f"         Quality: {llm_evaluation.quality_score:.1f}%")
        print(f"         Completeness: {llm_evaluation.completeness_score:.1f}%")
        print(f"         Accuracy: {llm_evaluation.accuracy_score:.1f}%")
        print(f"         Overall: {overall_score:.1f}%")
        
        return result
    
    def evaluate_all_charts(
        self, 
        charts_dir: str, 
        notes_dir: str,
        process_charts: bool = True
    ) -> List[ChartEvaluationResult]:
        """Evaluate all charts against their improvement notes."""
        matches = self.find_matching_chart_and_note(charts_dir, notes_dir)
        
        if not matches:
            print("[ERROR] No matching chart/note pairs found")
            return []
        
        print(f"\nFound {len(matches)} chart/note pair(s) to evaluate")
        
        results = []
        for chart_path, note_path in matches:
            result = self.evaluate_chart(chart_path, note_path, process_chart=process_charts)
            results.append(result)
            self.chart_evaluations.append(result)
        
        return results
    
    def calculate_metrics(self) -> EvaluationMetrics:
        """Calculate comprehensive evaluation metrics."""
        metrics = EvaluationMetrics()
        
        if not self.chart_evaluations:
            return metrics
        
        successful_evals = [e for e in self.chart_evaluations if e.processing_success and e.llm_evaluation]
        
        metrics.total_charts = len(self.chart_evaluations)
        metrics.successful_processing = len(successful_evals)
        metrics.failed_processing = metrics.total_charts - metrics.successful_processing
        
        if successful_evals:
            # Average scores
            metrics.avg_coverage_score = sum(e.llm_evaluation.coverage_score for e in successful_evals) / len(successful_evals)
            metrics.avg_quality_score = sum(e.llm_evaluation.quality_score for e in successful_evals) / len(successful_evals)
            metrics.avg_completeness_score = sum(e.llm_evaluation.completeness_score for e in successful_evals) / len(successful_evals)
            metrics.avg_accuracy_score = sum(e.llm_evaluation.accuracy_score for e in successful_evals) / len(successful_evals)
            metrics.avg_overall_score = sum(e.overall_score for e in successful_evals) / len(successful_evals)
            
            # Coverage metrics
            for eval_result in successful_evals:
                if eval_result.improvement_note:
                    metrics.total_expected_improvements += len(eval_result.improvement_note.recommended_improvements)
                    metrics.total_matched_improvements += len(eval_result.llm_evaluation.matched_improvements)
                    metrics.total_missed_improvements += len(eval_result.llm_evaluation.missed_improvements)
                    metrics.total_extra_recommendations += len(eval_result.llm_evaluation.extra_recommendations)
            
            if metrics.total_expected_improvements > 0:
                metrics.improvement_coverage_rate = (metrics.total_matched_improvements / metrics.total_expected_improvements) * 100
            
            # Processing metrics
            processing_times = [e.processing_time for e in successful_evals]
            metrics.avg_processing_time = sum(processing_times) / len(processing_times)
            metrics.total_processing_time = sum(processing_times)
            
            # Cost metrics
            metrics.total_cost_usd = sum(getattr(e, '_processing_cost', 0.0) for e in successful_evals)
            metrics.total_evaluation_cost_usd = sum(getattr(e, '_eval_cost', 0.0) for e in successful_evals)
            
            # Payer-specific metrics
            payer_scores = {}
            for eval_result in successful_evals:
                for rec in eval_result.cdi_recommendations:
                    payer = rec.payer
                    if payer not in payer_scores:
                        payer_scores[payer] = {
                            'count': 0,
                            'coverage_sum': 0.0,
                            'quality_sum': 0.0,
                            'completeness_sum': 0.0,
                            'accuracy_sum': 0.0
                        }
                    payer_scores[payer]['count'] += 1
                    payer_scores[payer]['coverage_sum'] += eval_result.llm_evaluation.coverage_score
                    payer_scores[payer]['quality_sum'] += eval_result.llm_evaluation.quality_score
                    payer_scores[payer]['completeness_sum'] += eval_result.llm_evaluation.completeness_score
                    payer_scores[payer]['accuracy_sum'] += eval_result.llm_evaluation.accuracy_score
            
            for payer, scores in payer_scores.items():
                count = scores['count']
                metrics.payer_performance[payer] = {
                    'avg_coverage': scores['coverage_sum'] / count if count > 0 else 0.0,
                    'avg_quality': scores['quality_sum'] / count if count > 0 else 0.0,
                    'avg_completeness': scores['completeness_sum'] / count if count > 0 else 0.0,
                    'avg_accuracy': scores['accuracy_sum'] / count if count > 0 else 0.0,
                    'charts_evaluated': count
                }
        
        return metrics
    
    def generate_report(self, metrics: EvaluationMetrics) -> str:
        """Generate comprehensive evaluation report."""
        report_lines = []
        
        report_lines.append("=" * 80)
        report_lines.append("CDI SYSTEM EVALUATION REPORT (Ground Truth Comparison)")
        report_lines.append("=" * 80)
        report_lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        if self.start_time and self.end_time:
            report_lines.append(f"Evaluation Duration: {(self.end_time - self.start_time):.2f} seconds")
        report_lines.append("")
        
        # Summary
        report_lines.append("=" * 80)
        report_lines.append("EXECUTIVE SUMMARY")
        report_lines.append("=" * 80)
        report_lines.append(f"Total Charts Evaluated:     {metrics.total_charts}")
        report_lines.append(f"Successful Evaluations:     {metrics.successful_processing} ({metrics.successful_processing/metrics.total_charts*100:.1f}%)")
        report_lines.append(f"Failed Evaluations:         {metrics.failed_processing}")
        report_lines.append(f"Overall Score:              {metrics.avg_overall_score:.1f}%")
        report_lines.append("")
        
        # Score Breakdown
        report_lines.append("=" * 80)
        report_lines.append("SCORE BREAKDOWN")
        report_lines.append("=" * 80)
        report_lines.append(f"Average Coverage Score:     {metrics.avg_coverage_score:.1f}%")
        report_lines.append(f"Average Quality Score:       {metrics.avg_quality_score:.1f}%")
        report_lines.append(f"Average Completeness Score: {metrics.avg_completeness_score:.1f}%")
        report_lines.append(f"Average Accuracy Score:     {metrics.avg_accuracy_score:.1f}%")
        report_lines.append("")
        
        # Coverage Metrics
        report_lines.append("=" * 80)
        report_lines.append("IMPROVEMENT COVERAGE")
        report_lines.append("=" * 80)
        report_lines.append(f"Total Expected Improvements: {metrics.total_expected_improvements}")
        report_lines.append(f"Matched Improvements:       {metrics.total_matched_improvements}")
        report_lines.append(f"Missed Improvements:        {metrics.total_missed_improvements}")
        report_lines.append(f"Extra Recommendations:      {metrics.total_extra_recommendations}")
        report_lines.append(f"Coverage Rate:              {metrics.improvement_coverage_rate:.1f}%")
        report_lines.append("")
        
        # Payer Performance
        if metrics.payer_performance:
            report_lines.append("=" * 80)
            report_lines.append("PAYER-SPECIFIC PERFORMANCE")
            report_lines.append("=" * 80)
            for payer, perf in metrics.payer_performance.items():
                report_lines.append(f"\n{payer}:")
                report_lines.append(f"  Charts Evaluated:        {perf['charts_evaluated']}")
                report_lines.append(f"  Avg Coverage:            {perf['avg_coverage']:.1f}%")
                report_lines.append(f"  Avg Quality:             {perf['avg_quality']:.1f}%")
                report_lines.append(f"  Avg Completeness:        {perf['avg_completeness']:.1f}%")
                report_lines.append(f"  Avg Accuracy:            {perf['avg_accuracy']:.1f}%")
            report_lines.append("")
        
        # Processing Metrics
        report_lines.append("=" * 80)
        report_lines.append("PROCESSING METRICS")
        report_lines.append("=" * 80)
        report_lines.append(f"Average Processing Time:     {metrics.avg_processing_time:.2f}s")
        report_lines.append(f"Total Processing Time:       {metrics.total_processing_time:.2f}s")
        report_lines.append("")
        
        # Cost Metrics
        report_lines.append("=" * 80)
        report_lines.append("COST ANALYSIS")
        report_lines.append("=" * 80)
        report_lines.append(f"Total CDI Processing Cost:   ${metrics.total_cost_usd:.4f}")
        report_lines.append(f"Total Evaluation Cost:       ${metrics.total_evaluation_cost_usd:.4f}")
        report_lines.append(f"Total Cost:                  ${metrics.total_cost_usd + metrics.total_evaluation_cost_usd:.4f}")
        report_lines.append("")
        
        # Detailed Chart Results
        report_lines.append("=" * 80)
        report_lines.append("DETAILED CHART RESULTS")
        report_lines.append("=" * 80)
        for eval_result in self.chart_evaluations:
            if eval_result.processing_success and eval_result.llm_evaluation:
                report_lines.append(f"\n{eval_result.chart_name}:")
                report_lines.append(f"  Overall Score:           {eval_result.overall_score:.1f}%")
                report_lines.append(f"  Coverage:                {eval_result.llm_evaluation.coverage_score:.1f}%")
                report_lines.append(f"  Quality:                 {eval_result.llm_evaluation.quality_score:.1f}%")
                report_lines.append(f"  Completeness:            {eval_result.llm_evaluation.completeness_score:.1f}%")
                report_lines.append(f"  Accuracy:                {eval_result.llm_evaluation.accuracy_score:.1f}%")
                report_lines.append(f"  Matched:                 {len(eval_result.llm_evaluation.matched_improvements)}")
                report_lines.append(f"  Missed:                  {len(eval_result.llm_evaluation.missed_improvements)}")
                report_lines.append(f"  Extra:                   {len(eval_result.llm_evaluation.extra_recommendations)}")
                
                if eval_result.llm_evaluation.strengths:
                    report_lines.append(f"  Strengths:")
                    for strength in eval_result.llm_evaluation.strengths:
                        report_lines.append(f"    - {strength}")
                
                if eval_result.llm_evaluation.weaknesses:
                    report_lines.append(f"  Weaknesses:")
                    for weakness in eval_result.llm_evaluation.weaknesses:
                        report_lines.append(f"    - {weakness}")
        
        report_lines.append("")
        report_lines.append("=" * 80)
        report_lines.append("END OF EVALUATION REPORT")
        report_lines.append("=" * 80)
        
        return "\n".join(report_lines)
    
    def save_results(self, metrics: EvaluationMetrics, report: str):
        """Save evaluation results to files."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save text report
        report_file = self.output_dir / f"ground_truth_evaluation_report_{timestamp}.txt"
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"\n[SAVED] Report: {report_file}")
        
        # Save JSON metrics
        metrics_file = self.output_dir / f"ground_truth_metrics_{timestamp}.json"
        with open(metrics_file, 'w', encoding='utf-8') as f:
            json.dump(asdict(metrics), f, indent=2, default=str)
        print(f"[SAVED] Metrics: {metrics_file}")
        
        # Save detailed chart evaluations
        evaluations_file = self.output_dir / f"ground_truth_chart_evaluations_{timestamp}.json"
        evaluations_data = []
        for eval_result in self.chart_evaluations:
            eval_dict = {
                'chart_name': eval_result.chart_name,
                'processing_success': eval_result.processing_success,
                'overall_score': eval_result.overall_score,
                'processing_time': eval_result.processing_time,
                'llm_evaluation': asdict(eval_result.llm_evaluation) if eval_result.llm_evaluation else None,
                'improvement_note': asdict(eval_result.improvement_note) if eval_result.improvement_note else None,
                'cdi_recommendations': [
                    {
                        'payer': rec.payer,
                        'procedure': rec.procedure,
                        'decision': rec.decision,
                        'primary_reasons': rec.primary_reasons,
                        'missing_requirements': rec.missing_requirements,
                        'suggestions': rec.suggestions
                    }
                    for rec in eval_result.cdi_recommendations
                ] if eval_result.cdi_recommendations else []
            }
            evaluations_data.append(eval_dict)
        
        with open(evaluations_file, 'w', encoding='utf-8') as f:
            json.dump(evaluations_data, f, indent=2, default=str)
        print(f"[SAVED] Chart Evaluations: {evaluations_file}")
    
    def run_evaluation(
        self, 
        charts_dir: str, 
        notes_dir: str,
        process_charts: bool = True
    ) -> EvaluationMetrics:
        """Run complete evaluation."""
        self.start_time = time.time()
        
        print("\n" + "=" * 80)
        print("STARTING CDI SYSTEM EVALUATION (Ground Truth Comparison)")
        print("=" * 80)
        print(f"Charts Directory: {charts_dir}")
        print(f"Improvement Notes Directory: {notes_dir}")
        print(f"Output Directory: {self.output_dir}")
        if self.existing_outputs_dir:
            print(f"Existing Outputs Directory: {self.existing_outputs_dir}")
        else:
            print(f"Existing Outputs Directory: {Config.OUTPUT_DIR} (from config)")
        print(f"Process Charts: {process_charts}")
        print("")
        
        # Initialize system
        if process_charts and not self.initialize_system():
            return EvaluationMetrics()
        
        # Evaluate all charts
        self.evaluate_all_charts(charts_dir, notes_dir, process_charts=process_charts)
        
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
        
        return metrics


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Evaluate CDI system against ground truth improvement notes",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        '--charts-dir',
        type=str,
        default='./Synthetic_data medical chart',
        help='Directory containing synthetic medical charts (default: ./Synthetic_data medical chart)'
    )
    
    parser.add_argument(
        '--notes-dir',
        type=str,
        default='./Charts/CDI_Improvement_Notes',
        help='Directory containing improvement notes (default: ./Charts/CDI_Improvement_Notes)'
    )
    
    parser.add_argument(
        '--output-dir',
        type=str,
        default='./evaluation_results',
        help='Directory for evaluation results (default: ./evaluation_results)'
    )
    
    parser.add_argument(
        '--existing-outputs-dir',
        type=str,
        default=None,
        help='Directory containing existing CDI output JSON files (default: uses OUTPUT_DIR from config or environment variable)'
    )
    
    parser.add_argument(
        '--process-charts',
        action='store_true',
        help='Process charts through CDI system (default: use existing outputs if available)'
    )
    
    parser.add_argument(
        '--no-process',
        action='store_true',
        help='Skip processing, only use existing outputs'
    )
    
    args = parser.parse_args()
    
    # Determine if charts should be processed
    process_charts = args.process_charts
    if args.no_process:
        process_charts = False
    
    try:
        # Create evaluator
        evaluator = CDIGroundTruthEvaluator(
            output_dir=args.output_dir,
            existing_outputs_dir=args.existing_outputs_dir
        )
        
        # Run evaluation
        metrics = evaluator.run_evaluation(
            args.charts_dir,
            args.notes_dir,
            process_charts=process_charts
        )
        
        # Print summary
        print("\n" + "=" * 80)
        print("EVALUATION COMPLETE")
        print("=" * 80)
        print(f"Charts Evaluated:        {metrics.total_charts}")
        print(f"Success Rate:            {metrics.successful_processing/metrics.total_charts*100:.1f}%")
        print(f"Overall Score:           {metrics.avg_overall_score:.1f}%")
        print(f"Coverage Rate:           {metrics.improvement_coverage_rate:.1f}%")
        print(f"Average Coverage:        {metrics.avg_coverage_score:.1f}%")
        print(f"Average Quality:         {metrics.avg_quality_score:.1f}%")
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

