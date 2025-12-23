# OCR Support for Scanned PDF Processing

## Overview

This document describes the OCR (Optical Character Recognition) implementation added to the CDI system to handle scanned/image-based PDFs that cannot be processed using standard text extraction methods.

**Status:** ✅ Implemented  
**Date:** December 2024  
**Version:** 1.0

---

## Problem Statement

Previously, the system could only extract text from PDFs that contained selectable text. Scanned PDFs (image-based documents) would fail with errors like:
- "PDF text extraction failed or returned minimal content"
- "Extracted 0 characters"
- Unable to detect procedures or patient information

## Solution

Implemented automatic OCR fallback mechanism that:
1. First attempts standard text extraction (pdfplumber/PyPDF2)
2. If text extraction fails, automatically attempts OCR
3. Supports two OCR engines: Tesseract OCR and EasyOCR
4. Provides detailed logging and error messages

---

## Architecture

### Extraction Flow

```
PDF Upload
    ↓
[Method 1] pdfplumber text extraction
    ↓ (if fails)
[Method 2] PyPDF2 text extraction
    ↓ (if fails)
[Method 3] Tesseract OCR (if available)
    ↓ (if fails)
[Method 4] EasyOCR (if available)
    ↓ (if all fail)
Error message with solutions
```

### Components

#### 1. File Processor (`src/multi_payer_cdi/file_processor.py`)

**Key Functions:**
- `read_chart()` - Main entry point for PDF processing
- Automatic OCR detection and execution
- Multi-method fallback chain

**OCR Libraries:**
- `pytesseract` - Python wrapper for Tesseract OCR
- `pdf2image` - Converts PDF pages to images
- `easyocr` - Self-contained OCR solution

---

## Installation Guide

### Option 1: EasyOCR (Recommended - Easiest Setup)

**Pros:**
- ✅ Self-contained, no external dependencies
- ✅ Works immediately after pip install
- ✅ No system-level installation required

**Cons:**
- ⚠️ Slower on first use (downloads models ~500MB)
- ⚠️ Larger memory footprint

**Installation:**
```bash
pip install easyocr
```

**Usage:**
- Automatically used when text extraction fails
- No additional configuration needed

---

### Option 2: Tesseract OCR

**Pros:**
- ✅ Fast and accurate
- ✅ Industry standard
- ✅ Good for production environments

**Cons:**
- ⚠️ Requires separate Tesseract OCR engine installation
- ⚠️ Platform-specific installation steps

**Installation Steps:**

1. **Install Python packages:**
   ```bash
   pip install pytesseract pdf2image
   ```

2. **Install Tesseract OCR Engine:**

   **Windows:**
   - Download installer from: https://github.com/UB-Mannheim/tesseract/wiki
   - Run installer and note installation path (usually `C:\Program Files\Tesseract-OCR`)
   - Add to PATH or set environment variable:
     ```bash
     setx TESSDATA_PREFIX "C:\Program Files\Tesseract-OCR\tessdata"
     ```

   **Mac:**
   ```bash
   brew install tesseract
   ```

   **Linux (Ubuntu/Debian):**
   ```bash
   sudo apt-get update
   sudo apt-get install tesseract-ocr
   ```

3. **Install Poppler (required for pdf2image):**

   **Windows:**
   - Download from: https://github.com/oschwartz10612/poppler-windows/releases
   - Extract and add `bin` folder to PATH

   **Mac:**
   ```bash
   brew install poppler
   ```

   **Linux:**
   ```bash
   sudo apt-get install poppler-utils
   ```

---

## Configuration

### Environment Variables

No additional environment variables required. OCR is automatically enabled when libraries are installed.

### Code Configuration

OCR settings are in `src/multi_payer_cdi/file_processor.py`:

```python
# OCR DPI setting (higher = better quality, slower processing)
dpi=300  # Default: 300 DPI

# EasyOCR GPU support (if CUDA available)
gpu=False  # Set to True if you have CUDA GPU
```

---

## Usage

### Automatic Mode (Default)

OCR runs automatically when text extraction fails. No code changes needed.

**Example Flow:**
1. User uploads scanned PDF
2. System attempts text extraction → fails
3. System automatically tries OCR
4. Text extracted successfully
5. Processing continues normally

### Console Output

**Successful OCR:**
```
[PDF] Analyzing PDF: 5 page(s), encrypted: False
[PDF] Page 1: No text extracted (might be image-based)
[PDF] Text extraction failed. Attempting OCR for scanned/image-based PDF...
[OCR] Using Tesseract OCR to extract text from images...
[OCR] Converted 5 page(s) to images at 300 DPI
[OCR] Page 1: Extracted 1234 characters using Tesseract
[OCR] Page 2: Extracted 987 characters using Tesseract
[OCR] Successfully extracted 5678 characters using Tesseract OCR from 5 page(s)
[PDF] Successfully extracted: 890 words, 234 lines, 5678 characters
```

**OCR Not Available:**
```
[PDF] Text extraction failed. Attempting OCR for scanned/image-based PDF...
[ERROR] PDF text extraction failed or returned minimal content.
OCR not available.
SOLUTIONS:
- Install OCR support: pip install easyocr
- OR: pip install pytesseract pdf2image
```

---

## Performance Considerations

### Processing Time

| Method | Speed | Accuracy | Setup Complexity |
|--------|-------|----------|------------------|
| Text Extraction | ⚡ Fast (< 1s) | ✅ Perfect | ✅ Easy |
| Tesseract OCR | 🐢 Slow (5-30s) | ✅ Good | ⚠️ Medium |
| EasyOCR | 🐢 Slow (10-60s) | ✅ Good | ✅ Easy |

**Notes:**
- First EasyOCR run is slower (downloads models)
- Subsequent runs are faster (models cached)
- Processing time scales with PDF page count
- Higher DPI = better accuracy but slower processing

### Memory Usage

- **EasyOCR:** ~2-3 GB RAM (first load), ~1 GB (subsequent)
- **Tesseract:** ~500 MB RAM
- **pdf2image:** ~100-500 MB per page (temporary)

### Recommendations

- **Development:** Use EasyOCR (easier setup)
- **Production:** Use Tesseract OCR (faster, more stable)
- **Large PDFs:** Consider processing pages in batches

---

## Error Handling

### Common Issues and Solutions

#### Issue 1: "TesseractNotFoundError"

**Cause:** Tesseract OCR engine not installed or not in PATH

**Solution:**
- Install Tesseract OCR (see Installation Guide)
- Add to system PATH
- Or use EasyOCR instead

#### Issue 2: "pdf2image conversion failed"

**Cause:** Poppler not installed or not in PATH

**Solution:**
- Install Poppler (see Installation Guide)
- Add to system PATH
- Or use EasyOCR with pdfplumber fallback

#### Issue 3: "EasyOCR initialization failed"

**Cause:** Network issues or insufficient disk space

**Solution:**
- Check internet connection (first run downloads models)
- Ensure ~2 GB free disk space
- Check firewall/proxy settings

#### Issue 4: "OCR extracted minimal text"

**Cause:** Poor image quality or blank pages

**Solution:**
- Improve PDF image quality
- Ensure PDF contains readable text/images
- Try different DPI settings (200-400)

---

## Testing

### Test Cases

1. **Scanned PDF (Image-based)**
   - ✅ Should automatically use OCR
   - ✅ Should extract text successfully
   - ✅ Should process normally after extraction

2. **Text-based PDF**
   - ✅ Should use standard text extraction
   - ✅ Should NOT use OCR (faster)
   - ✅ Should process normally

3. **Mixed PDF (Text + Images)**
   - ✅ Should extract text where available
   - ✅ Should use OCR for image-only pages
   - ✅ Should combine results

4. **No OCR Available**
   - ✅ Should show helpful error message
   - ✅ Should suggest installation steps
   - ✅ Should not crash

### Test Files

Create test PDFs:
- Scanned document (image-based)
- Text-based PDF
- Mixed content PDF
- Poor quality scanned PDF

---

## Code Changes Summary

### Files Modified

1. **`src/multi_payer_cdi/file_processor.py`**
   - Added OCR library imports
   - Added OCR fallback logic
   - Enhanced error messages
   - Added image conversion support

2. **`requirements.txt`**
   - Added `pytesseract>=0.3.10`
   - Added `pdf2image>=1.16.0`
   - Added `easyocr>=1.7.0`

### Key Functions

```python
# OCR detection
HAS_TESSERACT = True/False  # Auto-detected
HAS_EASYOCR = True/False    # Auto-detected

# OCR execution (automatic)
- Tesseract OCR processing
- EasyOCR processing
- Image conversion (pdf2image/pdfplumber)
```

---

## Future Enhancements

### Potential Improvements

1. **Multi-language Support**
   - Currently: English only
   - Future: Support for Spanish, French, etc.

2. **GPU Acceleration**
   - EasyOCR GPU support (CUDA)
   - Faster processing for large documents

3. **Batch Processing**
   - Process multiple PDFs in parallel
   - Queue system for large volumes

4. **Quality Assessment**
   - Detect image quality before OCR
   - Suggest DPI adjustments
   - Pre-processing (deskew, denoise)

5. **OCR Caching**
   - Cache OCR results for repeated documents
   - Reduce processing time

---

## Troubleshooting

### Debug Mode

Enable detailed logging:
```python
# In file_processor.py, OCR section already includes detailed logging
# Check console output for:
- [OCR] messages
- [PDF] messages
- Error tracebacks
```

### Common Log Messages

| Message | Meaning | Action |
|---------|---------|--------|
| `[OCR] Using Tesseract OCR...` | OCR starting | Wait for completion |
| `[OCR] Page X: Extracted Y characters` | Success | None needed |
| `[OCR] Page X: Minimal text extracted` | Low quality | Check PDF quality |
| `[OCR] Tesseract OCR failed` | Error occurred | Check error details |
| `OCR not available` | Not installed | Install OCR library |

---

## Support and Contact

### Questions or Issues?

1. Check this documentation
2. Review console logs for error details
3. Verify OCR library installation
4. Test with sample PDFs

### Related Documentation

- [PDF Processing Guide](./README.md)
- [Installation Guide](./ANACONDA_SETUP.md)
- [API Documentation](./API_ACCESS_GUIDE.md)

---

## Changelog

### Version 1.0 (December 2024)

- ✅ Initial OCR implementation
- ✅ Tesseract OCR support
- ✅ EasyOCR support
- ✅ Automatic fallback mechanism
- ✅ Enhanced error messages
- ✅ Detailed logging

---

## Appendix

### OCR Library Links

- **Tesseract OCR:** https://github.com/tesseract-ocr/tesseract
- **EasyOCR:** https://github.com/JaidedAI/EasyOCR
- **pytesseract:** https://github.com/madmaze/pytesseract
- **pdf2image:** https://github.com/Belval/pdf2image

### System Requirements

**Minimum:**
- Python 3.8+
- 2 GB RAM
- 2 GB disk space (for EasyOCR models)

**Recommended:**
- Python 3.10+
- 4 GB RAM
- 5 GB disk space
- GPU (optional, for EasyOCR acceleration)

---

**Document Version:** 1.0  
**Last Updated:** December 2024  
**Author:** CDI Development Team

