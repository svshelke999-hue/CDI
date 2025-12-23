# CDI System Evaluation Guide

## Overview

The `evaluate_cdi_with_ground_truth.py` script evaluates the CDI system's performance by comparing its recommendations against ground truth improvement notes. It uses LLM (Claude) to assess the quality, coverage, completeness, and accuracy of CDI recommendations.

## Features

- **Ground Truth Comparison**: Compares CDI recommendations against expert-created improvement notes
- **LLM-Powered Evaluation**: Uses Claude to assess recommendation quality across multiple dimensions
- **Comprehensive Metrics**: 
  - Coverage Score: How many expected improvements were addressed
  - Quality Score: How well recommendations match expected improvements
  - Completeness Score: Are all key areas covered
  - Accuracy Score: Medical appropriateness of recommendations
- **Payer-Specific Analysis**: Performance breakdown by payer (Cigna, UHC, Anthem)
- **Detailed Reports**: Text and JSON reports with actionable insights

## Prerequisites

1. Synthetic medical charts in `Synthetic_data medical chart/` directory
2. Corresponding improvement notes in `Charts/CDI_Improvement_Notes/` directory
3. AWS credentials configured for Bedrock access
4. CDI system dependencies installed

## Usage

### Basic Evaluation (Use Existing Outputs)

If you've already processed charts through `main.py`, you can evaluate using existing outputs:

```bash
python evaluate_cdi_with_ground_truth.py
```

This will:
- Look for existing CDI output files in `outputs/` directory
- Compare them against improvement notes
- Generate evaluation report

### Process Charts First, Then Evaluate

To process charts through the CDI system first, then evaluate:

```bash
python evaluate_cdi_with_ground_truth.py --process-charts
```

### Custom Directories

```bash
python evaluate_cdi_with_ground_truth.py \
    --charts-dir "./Synthetic_data medical chart" \
    --notes-dir "./Charts/CDI_Improvement_Notes" \
    --output-dir "./evaluation_results"
```

### Skip Processing (Use Existing Outputs Only)

```bash
python evaluate_cdi_with_ground_truth.py --no-process
```

## Command Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--charts-dir` | Directory containing synthetic medical charts | `./Synthetic_data medical chart` |
| `--notes-dir` | Directory containing improvement notes | `./Charts/CDI_Improvement_Notes` |
| `--output-dir` | Directory for evaluation results | `./evaluation_results` |
| `--process-charts` | Process charts through CDI system first | Use existing outputs if available |
| `--no-process` | Skip processing, only use existing outputs | Process if needed |

## File Naming Convention

The script automatically matches charts with improvement notes based on naming:

- Chart: `chart_01_rotator_cuff_labrum.txt`
- Improvement Note: `chart_01_rotator_cuff_labrum_improvement.txt`

## Evaluation Metrics

### Coverage Score (0-100%)
Measures how many of the expected improvements from the ground truth were addressed by the CDI recommendations.

**Calculation**: (Matched improvements / Total expected improvements) × 100

### Quality Score (0-100%)
Assesses how well the CDI recommendations match the expected improvements in terms of:
- Specificity and detail level
- Medical accuracy
- Actionability
- Alignment with CDI best practices

### Completeness Score (0-100%)
Evaluates whether all key areas from the primary CDI focus are covered by the recommendations.

### Accuracy Score (0-100%)
Measures the medical appropriateness and clinical soundness of recommendations:
- Medical correctness
- Clinical relevance
- Appropriate level of detail

### Overall Score
Weighted average of all scores:
- Coverage: 30%
- Quality: 30%
- Completeness: 20%
- Accuracy: 20%

## Output Files

The evaluation generates several output files in the `evaluation_results/` directory:

1. **`ground_truth_evaluation_report_YYYYMMDD_HHMMSS.txt`**
   - Human-readable text report with detailed analysis
   - Executive summary
   - Score breakdowns
   - Payer-specific performance
   - Detailed chart-by-chart results

2. **`ground_truth_metrics_YYYYMMDD_HHMMSS.json`**
   - Machine-readable metrics in JSON format
   - Aggregate statistics
   - Payer performance data

3. **`ground_truth_chart_evaluations_YYYYMMDD_HHMMSS.json`**
   - Detailed evaluation results for each chart
   - LLM evaluation details
   - Matched/missed improvements
   - Strengths and weaknesses

## Example Workflow

### Step 1: Process All Charts

```bash
# Process all synthetic charts through CDI system
python main.py "./Synthetic_data medical chart"
```

This will create output JSON files in the `outputs/` directory.

### Step 2: Evaluate Results

```bash
# Evaluate against ground truth improvement notes
python evaluate_cdi_with_ground_truth.py --no-process
```

### Step 3: Review Results

Check the evaluation report in `evaluation_results/`:

```bash
# View the latest report
cat evaluation_results/ground_truth_evaluation_report_*.txt | tail -100
```

## Understanding the Results

### Good Performance Indicators
- **Coverage Score > 80%**: Most expected improvements are addressed
- **Quality Score > 75%**: Recommendations are specific and actionable
- **Completeness Score > 80%**: All key focus areas are covered
- **Accuracy Score > 85%**: Recommendations are medically sound

### Areas for Improvement
- **Low Coverage**: CDI system is missing important improvement areas
- **Low Quality**: Recommendations lack specificity or detail
- **Low Completeness**: Key focus areas are not addressed
- **Low Accuracy**: Recommendations may be medically inappropriate

## Troubleshooting

### No Matching Chart/Note Pairs Found
- Ensure chart files are named correctly (e.g., `chart_01_*.txt`)
- Ensure improvement notes follow naming convention (e.g., `chart_01_*_improvement.txt`)
- Check that both directories exist and contain files

### LLM Evaluation Errors
- Verify AWS credentials are configured
- Check that Claude model ID is correct in config
- Ensure sufficient AWS Bedrock quota

### Processing Failures
- Check that CDI system is properly configured
- Verify input chart files are readable
- Check logs for detailed error messages

## Cost Considerations

The evaluation script uses LLM calls for each chart evaluation. Estimated costs:
- **Per Chart Evaluation**: ~$0.01-0.03 (depending on chart size)
- **10 Charts**: ~$0.10-0.30 total

To reduce costs:
- Use `--no-process` to skip reprocessing charts
- Reuse existing evaluation results when possible

## Integration with CI/CD

You can integrate this evaluation into automated testing:

```bash
#!/bin/bash
# Run evaluation and check if overall score meets threshold
python evaluate_cdi_with_ground_truth.py --no-process

# Extract overall score from JSON
OVERALL_SCORE=$(jq '.avg_overall_score' evaluation_results/ground_truth_metrics_*.json)

# Fail if score below threshold
if (( $(echo "$OVERALL_SCORE < 75" | bc -l) )); then
    echo "Evaluation failed: Overall score $OVERALL_SCORE% is below 75% threshold"
    exit 1
fi
```

## Best Practices

1. **Regular Evaluation**: Run evaluation after major system changes
2. **Baseline Establishment**: Create baseline metrics for comparison
3. **Payer-Specific Analysis**: Review payer-specific performance separately
4. **Iterative Improvement**: Use evaluation results to refine CDI prompts and logic
5. **Documentation**: Keep improvement notes updated as requirements change

## Support

For issues or questions:
1. Check the evaluation report for detailed error messages
2. Review logs in `logs/` directory
3. Verify file naming conventions match expected patterns
4. Ensure all dependencies are installed correctly

