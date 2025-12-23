# Testing the CDI API

## Quick Test Endpoint

I've added a `/test` endpoint that automatically processes a sample chart and shows both **input** and **output**.

### Access the Test Endpoint

**In your browser:**
```
http://localhost:8001/test
```

This will:
1. ✅ Load a sample chart from `Charts/sample_chart_mixed.txt`
2. ✅ Process it through the CDI system
3. ✅ Return both the **input chart text** and **processed output**

### Response Structure

The test endpoint returns:
```json
{
  "test_status": "success",
  "input": {
    "file_name": "sample_chart_mixed.txt",
    "chart_text": "...full chart text...",
    "chart_length": 1234,
    "chart_lines": 110
  },
  "output": {
    "filename": "sample_chart_mixed.txt",
    "lambda_response": {
      "extraction_data": {
        "procedure": [...],
        "cpt": [...],
        "summary": "..."
      },
      "result_summary": {
        "payer_results": {...}
      }
    }
  },
  "processing_info": {
    "total_cost": 0.001234,
    "payers_processed": 3,
    ...
  }
}
```

## Testing with Your Own File

### Option 1: Using the API Documentation (Swagger UI)

1. Go to: **http://localhost:8001/docs**
2. Find the `/process-pdf` endpoint
3. Click "Try it out"
4. Click "Choose File" and select your PDF/DOCX/TXT file
5. Click "Execute"
6. See the response with both input (file name) and output (processed results)

### Option 2: Using curl (Command Line)

```bash
curl -X POST "http://localhost:8001/process-pdf" \
  -H "accept: application/json" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@Charts/sample_chart_mixed.txt"
```

### Option 3: Using Python

```python
import requests

# Test with sample chart
with open("Charts/sample_chart_mixed.txt", "rb") as f:
    files = {"file": f}
    response = requests.post("http://localhost:8001/process-pdf", files=files)
    result = response.json()
    
    print("Input file:", result.get("filename"))
    print("Procedures:", result["lambda_response"]["extraction_data"]["procedure"])
    print("CPT Codes:", result["lambda_response"]["extraction_data"]["cpt"])
    print("Payer Results:", result["lambda_response"]["result_summary"]["payer_results"])
```

## Test Checklist

- [ ] Server is running (check terminal)
- [ ] Health check works: http://localhost:8001/
- [ ] Test endpoint works: http://localhost:8001/test
- [ ] API docs accessible: http://localhost:8001/docs
- [ ] Can upload and process a file via `/process-pdf`
- [ ] Response includes both input info and processed output

## Expected Test Results

When you access `/test`, you should see:

**Input:**
- Sample chart with multiple procedures
- CPT codes: 27447, 29826
- Procedures: Total knee arthroplasty, Subacromial decompression, etc.

**Output:**
- Extracted procedures list
- Extracted CPT codes
- Summary of the chart
- Payer-specific compliance results
- Decision for each payer (Sufficient/Insufficient)

## Troubleshooting

### Test endpoint returns 404
- Make sure `Charts/sample_chart_mixed.txt` exists
- Check the file path is correct

### Test endpoint returns 500 error
- Check terminal for error messages
- Verify all dependencies are installed
- Check environment variables are set (AWS credentials, etc.)

### No output in response
- Check that the CDI system initialized correctly
- Verify OpenSearch/JSON data sources are configured
- Check logs in the terminal

