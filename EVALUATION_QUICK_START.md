# CDI Evaluation Quick Start

## Quick Commands

### 1. Process Charts First (if needed)
```bash
python main.py "./Synthetic_data medical chart"
```

### 2. Run Evaluation
```bash
# Use existing outputs (recommended)
python evaluate_cdi_with_ground_truth.py

# Or process charts first, then evaluate
python evaluate_cdi_with_ground_truth.py --process-charts
```

## What It Does

1. **Matches Charts with Improvement Notes**
   - Finds all charts in `Synthetic_data medical chart/`
   - Matches with corresponding notes in `Charts/CDI_Improvement_Notes/`
   - Pattern: `chart_01_*.txt` → `chart_01_*_improvement.txt`

2. **Processes Charts (if needed)**
   - Runs charts through CDI system
   - Extracts recommendations from all payers
   - Saves results to `outputs/` directory

3. **Evaluates with LLM**
   - Compares CDI recommendations vs. expected improvements
   - Scores: Coverage, Quality, Completeness, Accuracy
   - Identifies matched/missed improvements

4. **Generates Reports**
   - Text report: `evaluation_results/ground_truth_evaluation_report_*.txt`
   - JSON metrics: `evaluation_results/ground_truth_metrics_*.json`
   - Detailed results: `evaluation_results/ground_truth_chart_evaluations_*.json`

## Evaluation Metrics Explained

| Metric | What It Measures | Good Score |
|--------|------------------|------------|
| **Coverage** | % of expected improvements addressed | > 80% |
| **Quality** | How well recommendations match expectations | > 75% |
| **Completeness** | All key focus areas covered | > 80% |
| **Accuracy** | Medical appropriateness | > 85% |
| **Overall** | Weighted average of all scores | > 80% |

## Example Output

```
EXECUTIVE SUMMARY
================
Total Charts Evaluated:     10
Successful Evaluations:     10 (100.0%)
Overall Score:              82.5%

SCORE BREAKDOWN
===============
Average Coverage Score:     85.0%
Average Quality Score:      80.0%
Average Completeness Score: 82.0%
Average Accuracy Score:     83.0%

IMPROVEMENT COVERAGE
====================
Total Expected Improvements: 60
Matched Improvements:        51
Missed Improvements:          9
Coverage Rate:               85.0%
```

## Troubleshooting

**No matching files found?**
- Check file naming: `chart_XX_*.txt` and `chart_XX_*_improvement.txt`
- Verify directories exist

**LLM evaluation errors?**
- Check AWS credentials
- Verify Claude model access

**Processing failures?**
- Check CDI system configuration
- Review logs in `logs/` directory

## Next Steps

1. Review the evaluation report
2. Identify areas for improvement
3. Update CDI prompts/logic based on findings
4. Re-run evaluation to measure improvements

