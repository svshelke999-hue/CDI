"""
File processing utilities for reading medical charts.
"""

import os
from pathlib import Path
from typing import Optional

try:
    from PyPDF2 import PdfReader
except ImportError:
    PdfReader = None

# Try to import pdfplumber as a better alternative for PDF extraction
try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False
    pdfplumber = None
    # Print warning only once at module load
    import sys
    if not hasattr(sys, '_pdfplumber_warned'):
        print("[INFO] pdfplumber not installed. For better PDF extraction, install: pip install pdfplumber")
        print("[INFO] Falling back to PyPDF2 (may have issues with complex PDFs)")
        sys._pdfplumber_warned = True

try:
    from docx import Document
except ImportError:
    Document = None

# Try to import OCR libraries for scanned PDFs
try:
    import pytesseract
    from pdf2image import convert_from_path
    HAS_TESSERACT = True
except ImportError:
    HAS_TESSERACT = False
    pytesseract = None
    convert_from_path = None

# Try EasyOCR as alternative (doesn't require external Tesseract installation)
try:
    import easyocr
    HAS_EASYOCR = True
except ImportError:
    HAS_EASYOCR = False
    easyocr = None

# Print OCR availability once at module load
import sys
if not hasattr(sys, '_ocr_warned'):
    if not HAS_TESSERACT and not HAS_EASYOCR:
        print("[INFO] OCR libraries not installed. For scanned PDF support, install:")
        print("[INFO]   Option 1: pip install pytesseract pdf2image (requires Tesseract OCR)")
        print("[INFO]   Option 2: pip install easyocr (self-contained, no external dependencies)")
    elif HAS_TESSERACT:
        print("[INFO] Tesseract OCR available for scanned PDF processing")
    elif HAS_EASYOCR:
        print("[INFO] EasyOCR available for scanned PDF processing")
    sys._ocr_warned = True


class FileProcessor:
    """Handles reading and processing of medical chart files."""
    
    @staticmethod
    def read_chart(file_path: str) -> str:
        """
        Read chart text from .txt, .pdf, or .docx file.
        
        Args:
            file_path: Path to the medical chart file
            
        Returns:
            Extracted text content
            
        Raises:
            ValueError: If file format is unsupported
        """
        ext = Path(file_path).suffix.lower()
        
        if ext == ".txt":
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        elif ext == ".pdf":
            # Try multiple PDF extraction methods for better compatibility
            extracted_text = None
            extraction_method = None
            pdf_info = {}
            
            # Method 1: Try pdfplumber with multiple strategies
            if HAS_PDFPLUMBER:
                try:
                    with pdfplumber.open(file_path) as pdf:
                        # Get PDF metadata
                        pdf_info['total_pages'] = len(pdf.pages)
                        pdf_info['is_encrypted'] = pdf.metadata.get('encrypted', False) if pdf.metadata else False
                        
                        print(f"[PDF] Analyzing PDF: {pdf_info['total_pages']} page(s), encrypted: {pdf_info['is_encrypted']}")
                        
                        text_parts = []
                        for page_num, page in enumerate(pdf.pages, 1):
                            # Try standard extraction first
                            page_text = page.extract_text()
                            
                            # If standard extraction fails, try with layout preservation
                            if not page_text or len(page_text.strip()) < 10:
                                try:
                                    # Try extracting with layout
                                    page_text = page.extract_text(layout=True)
                                except:
                                    pass
                            
                            # If still no text, try extracting tables and text separately
                            if not page_text or len(page_text.strip()) < 10:
                                try:
                                    # Extract tables
                                    tables = page.extract_tables()
                                    if tables:
                                        table_texts = []
                                        for table in tables:
                                            for row in table:
                                                if row:
                                                    table_texts.append(" | ".join(str(cell) if cell else "" for cell in row))
                                        if table_texts:
                                            page_text = "\n".join(table_texts)
                                except:
                                    pass
                            
                            if page_text and len(page_text.strip()) > 0:
                                text_parts.append(page_text)
                                print(f"[PDF] Page {page_num}: Extracted {len(page_text)} characters")
                            else:
                                print(f"[PDF] Page {page_num}: No text extracted (might be image-based)")
                        
                        if text_parts:
                            extracted_text = "\n".join(text_parts)
                            extraction_method = "pdfplumber"
                            print(f"[PDF] Extracted {len(extracted_text)} characters using pdfplumber from {len(text_parts)} page(s)")
                except Exception as e:
                    print(f"[PDF] pdfplumber extraction failed: {e}")
                    import traceback
                    print(f"[PDF] Traceback: {traceback.format_exc()}")
            
            # Method 2: Fallback to PyPDF2
            if not extracted_text and PdfReader:
                try:
                    reader = PdfReader(file_path)
                    pdf_info['total_pages'] = len(reader.pages)
                    pdf_info['is_encrypted'] = reader.is_encrypted
                    
                    print(f"[PDF] Trying PyPDF2: {pdf_info['total_pages']} page(s), encrypted: {pdf_info['is_encrypted']}")
                    
                    if reader.is_encrypted:
                        print(f"[PDF] WARNING: PDF is password-protected. Text extraction may fail.")
                    
                    text_parts = []
                    for page_num, page in enumerate(reader.pages, 1):
                        try:
                            page_text = page.extract_text()
                            if page_text:
                                text_parts.append(page_text)
                                print(f"[PDF] Page {page_num}: Extracted {len(page_text)} characters using PyPDF2")
                            else:
                                print(f"[PDF] Page {page_num}: No text extracted using PyPDF2")
                        except Exception as e:
                            print(f"[PDF] Page {page_num} extraction error: {e}")
                    
                    if text_parts:
                        extracted_text = "\n".join(text_parts)
                        extraction_method = "PyPDF2"
                        print(f"[PDF] Extracted {len(extracted_text)} characters using PyPDF2 from {len(text_parts)} page(s)")
                except Exception as e:
                    print(f"[PDF] PyPDF2 extraction failed: {e}")
                    import traceback
                    print(f"[PDF] Traceback: {traceback.format_exc()}")
            
            # Method 3: Try OCR if text extraction failed (for scanned/image-based PDFs)
            if not extracted_text or len(extracted_text.strip()) < 10:
                print(f"[PDF] Text extraction failed. Attempting OCR for scanned/image-based PDF...")
                
                # Try Tesseract OCR first (if available)
                if HAS_TESSERACT:
                    try:
                        print(f"[OCR] Using Tesseract OCR to extract text from images...")
                        # Convert PDF pages to images
                        images = convert_from_path(file_path, dpi=300)
                        print(f"[OCR] Converted {len(images)} page(s) to images at 300 DPI")
                        
                        ocr_text_parts = []
                        for page_num, image in enumerate(images, 1):
                            try:
                                # Perform OCR on the image
                                page_text = pytesseract.image_to_string(image, lang='eng')
                                if page_text and len(page_text.strip()) > 10:
                                    ocr_text_parts.append(page_text)
                                    print(f"[OCR] Page {page_num}: Extracted {len(page_text)} characters using Tesseract")
                                else:
                                    print(f"[OCR] Page {page_num}: Minimal text extracted (might be blank or low quality)")
                            except Exception as e:
                                print(f"[OCR] Page {page_num} OCR error: {e}")
                        
                        if ocr_text_parts:
                            extracted_text = "\n".join(ocr_text_parts)
                            extraction_method = "Tesseract OCR"
                            print(f"[OCR] Successfully extracted {len(extracted_text)} characters using Tesseract OCR from {len(ocr_text_parts)} page(s)")
                    except Exception as e:
                        print(f"[OCR] Tesseract OCR failed: {e}")
                        import traceback
                        print(f"[OCR] Traceback: {traceback.format_exc()}")
                
                # Try EasyOCR as fallback (if Tesseract failed or not available)
                if (not extracted_text or len(extracted_text.strip()) < 10) and HAS_EASYOCR:
                    try:
                        print(f"[OCR] Trying EasyOCR as alternative OCR method...")
                        # Initialize EasyOCR reader (English only for now) - cache it to avoid re-initialization
                        if not hasattr(FileProcessor, '_easyocr_reader'):
                            print(f"[OCR] Initializing EasyOCR reader (this may take a moment on first use)...")
                            FileProcessor._easyocr_reader = easyocr.Reader(['en'], gpu=False)  # Set gpu=True if you have CUDA
                        reader = FileProcessor._easyocr_reader
                        
                        # Convert PDF pages to images
                        images = []
                        if HAS_TESSERACT:
                            try:
                                images = convert_from_path(file_path, dpi=300)
                            except Exception as e:
                                print(f"[OCR] pdf2image conversion failed: {e}")
                        
                        # If pdf2image not available or failed, try alternative methods
                        if not images and HAS_PDFPLUMBER:
                            try:
                                # Use pdfplumber's image conversion
                                with pdfplumber.open(file_path) as pdf:
                                    for page in pdf.pages:
                                        try:
                                            img = page.to_image(resolution=300)
                                            # Convert PIL image to numpy array for EasyOCR
                                            import numpy as np
                                            from PIL import Image
                                            if hasattr(img, 'original'):
                                                pil_img = img.original
                                            else:
                                                pil_img = img
                                            # Convert PIL to numpy array
                                            img_array = np.array(pil_img)
                                            images.append(img_array)
                                        except Exception as e:
                                            print(f"[OCR] Page image conversion error: {e}")
                            except Exception as e:
                                print(f"[OCR] pdfplumber image conversion failed: {e}")
                        
                        if not images:
                            print(f"[OCR] Could not convert PDF to images. Install pdf2image: pip install pdf2image")
                        else:
                            print(f"[OCR] Converted {len(images)} page(s) to images for EasyOCR")
                            
                            ocr_text_parts = []
                            for page_num, image in enumerate(images, 1):
                                try:
                                    # Perform OCR using EasyOCR
                                    # EasyOCR accepts numpy arrays or PIL images
                                    results = reader.readtext(image)
                                    page_text = "\n".join([result[1] for result in results])  # Extract text from results
                                    
                                    if page_text and len(page_text.strip()) > 10:
                                        ocr_text_parts.append(page_text)
                                        print(f"[OCR] Page {page_num}: Extracted {len(page_text)} characters using EasyOCR")
                                    else:
                                        print(f"[OCR] Page {page_num}: Minimal text extracted using EasyOCR")
                                except Exception as e:
                                    print(f"[OCR] Page {page_num} EasyOCR error: {e}")
                            
                            if ocr_text_parts:
                                extracted_text = "\n".join(ocr_text_parts)
                                extraction_method = "EasyOCR"
                                print(f"[OCR] Successfully extracted {len(extracted_text)} characters using EasyOCR from {len(ocr_text_parts)} page(s)")
                    except Exception as e:
                        print(f"[OCR] EasyOCR failed: {e}")
                        import traceback
                        print(f"[OCR] Traceback: {traceback.format_exc()}")
            
            # Validate extraction
            if not extracted_text or len(extracted_text.strip()) < 10:
                # Provide detailed error message
                error_details = []
                error_details.append(f"Extracted {len(extracted_text) if extracted_text else 0} characters")
                error_details.append(f"PDF has {pdf_info.get('total_pages', 'unknown')} page(s)")
                if pdf_info.get('is_encrypted'):
                    error_details.append("PDF is password-protected")
                
                # Check if OCR was attempted
                ocr_attempted = HAS_TESSERACT or HAS_EASYOCR
                ocr_status = "OCR attempted but failed" if ocr_attempted else "OCR not available"
                
                error_msg = (
                    f"PDF text extraction failed or returned minimal content. "
                    f"{' | '.join(error_details)}. {ocr_status}.\n\n"
                    f"This PDF might be:\n"
                    f"1. A scanned/image-based PDF with poor quality images\n"
                    f"2. Password-protected - Remove password protection first\n"
                    f"3. Corrupted or has unsupported structure\n"
                    f"4. Contains only images that OCR cannot process\n\n"
                    f"SOLUTIONS:\n"
                )
                
                if not ocr_attempted:
                    error_msg += (
                        f"- Install OCR support: pip install pytesseract pdf2image (requires Tesseract OCR)\n"
                        f"  OR: pip install easyocr (self-contained, no external dependencies)\n"
                    )
                
                error_msg += (
                    f"- Convert PDF to .txt format using a PDF viewer (File > Save As > Text)\n"
                    f"- Use online OCR tools (Google Drive, Adobe Acrobat Online)\n"
                    f"- Try opening the PDF in a PDF editor and re-saving it\n"
                    f"- Improve image quality if it's a scanned document"
                )
                print(f"[ERROR] {error_msg}")
                raise ValueError(error_msg)
            
            # Clean up extracted text
            extracted_text = extracted_text.strip()
            
            # Log extraction stats
            word_count = len(extracted_text.split())
            line_count = len(extracted_text.split('\n'))
            print(f"[PDF] Successfully extracted using {extraction_method}: {word_count:,} words, {line_count:,} lines, {len(extracted_text):,} characters")
            
            return extracted_text
        elif ext in [".docx", ".doc"]:
            if Document is None:
                raise ImportError("Please install python-docx: pip install python-docx")
            doc = Document(file_path)
            text = []
            for paragraph in doc.paragraphs:
                text.append(paragraph.text)
            return "\n".join(text)
        else:
            raise ValueError("Unsupported file format. Use .txt, .pdf, or .docx")
    
    @staticmethod
    def add_line_numbers(text: str) -> str:
        """
        Add line numbers to text for better reference in compliance evaluation.
        
        Args:
            text: Input text
            
        Returns:
            Text with line numbers prefixed (L001:, L002:, etc.)
        """
        lines = text.split('\n')
        numbered_lines = []
        for i, line in enumerate(lines, 1):
            numbered_lines.append(f"L{i:03d}: {line}")
        return '\n'.join(numbered_lines)
    
    @staticmethod
    def remove_line_numbers(text: str) -> str:
        """
        Remove line numbers from text (e.g., L001:, L002:, etc.).
        
        Args:
            text: Input text that may contain line numbers
            
        Returns:
            Text with line numbers removed
        """
        import re
        # Pattern to match line numbers like L001:, L002:, etc. at the start of lines
        pattern = r'^L\d{3}:\s*'
        lines = text.split('\n')
        cleaned_lines = []
        for line in lines:
            cleaned_line = re.sub(pattern, '', line)
            cleaned_lines.append(cleaned_line)
        return '\n'.join(cleaned_lines)
    
    @staticmethod
    def get_files_to_process(input_dir: str) -> list:
        """
        Get list of files to process from input directory.
        
        Args:
            input_dir: Directory containing medical chart files
            
        Returns:
            List of file paths to process
        """
        files_to_process = []
        
        if not os.path.exists(input_dir):
            print(f"⚠️ Input directory does not exist: {input_dir}")
            return files_to_process
        
        for file in os.listdir(input_dir):
            if file.endswith((".txt", ".pdf", ".docx", ".doc")):
                files_to_process.append(os.path.join(input_dir, file))
        
        return files_to_process
    
    @staticmethod
    def validate_file(file_path: str) -> bool:
        """
        Validate that file exists and is readable.
        
        Args:
            file_path: Path to file to validate
            
        Returns:
            True if file is valid, False otherwise
        """
        if not os.path.exists(file_path):
            print(f"❌ File does not exist: {file_path}")
            return False
        
        if not os.access(file_path, os.R_OK):
            print(f"❌ File is not readable: {file_path}")
            return False
        
        ext = Path(file_path).suffix.lower()
        if ext not in [".txt", ".pdf", ".docx", ".doc"]:
            print(f"❌ Unsupported file format: {ext}")
            return False
        
        return True
