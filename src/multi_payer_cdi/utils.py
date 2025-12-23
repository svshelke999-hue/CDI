"""
Utility functions for the Multi-Payer CDI Compliance Checker.
"""

import json
from typing import Dict, Any, List


def extract_first_json_object(text: str) -> str | None:
    """
    Extract first JSON object from text with enhanced parsing.
    
    Args:
        text: Input text that may contain JSON
        
    Returns:
        First JSON object found as string, or None if not found
    """
    if text is None:
        return None
    stripped = text.strip()
    if stripped.startswith("```"):
        parts = stripped.split("\n", 1)
        stripped = parts[1] if len(parts) > 1 else stripped
        if stripped.endswith("```"):
            stripped = stripped[:-3]
    start = stripped.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(stripped)):
        ch = stripped[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        else:
            if ch == '"':
                in_string = True
                continue
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    return stripped[start : i + 1]
    return None


def safe_json_loads(json_str: str, default: Any = None) -> Any:
    """
    Safely parse JSON string with fallback.
    
    Args:
        json_str: JSON string to parse
        default: Default value if parsing fails
        
    Returns:
        Parsed JSON object or default value
    """
    try:
        return json.loads(json_str)
    except (json.JSONDecodeError, TypeError):
        return default


def validate_json_schema(data: Dict[str, Any], required_keys: List[str]) -> bool:
    """
    Validate that data contains required keys.
    
    Args:
        data: Dictionary to validate
        required_keys: List of required keys
        
    Returns:
        True if all required keys are present, False otherwise
    """
    return all(key in data for key in required_keys)


def format_cost(cost: float, currency: str = "$") -> str:
    """
    Format cost value for display.
    
    Args:
        cost: Cost value
        currency: Currency symbol
        
    Returns:
        Formatted cost string
    """
    return f"{currency}{cost:.6f}"


def format_tokens(tokens: int) -> str:
    """
    Format token count for display.
    
    Args:
        tokens: Number of tokens
        
    Returns:
        Formatted token string with commas
    """
    return f"{tokens:,}"


def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """
    Truncate text to specified length.
    
    Args:
        text: Input text
        max_length: Maximum length
        suffix: Suffix to add when truncating
        
    Returns:
        Truncated text
    """
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename for safe file operations.
    
    Args:
        filename: Input filename
        
    Returns:
        Sanitized filename
    """
    import re
    # Remove or replace unsafe characters
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', filename)
    # Remove leading/trailing whitespace and dots
    sanitized = sanitized.strip('. ')
    # Limit length
    if len(sanitized) > 200:
        sanitized = sanitized[:200]
    return sanitized


def get_file_extension(filename: str) -> str:
    """
    Get file extension from filename.
    
    Args:
        filename: Input filename
        
    Returns:
        File extension (including dot)
    """
    import os
    _, ext = os.path.splitext(filename)
    return ext.lower()


def is_supported_file_type(filename: str) -> bool:
    """
    Check if file type is supported.
    
    Args:
        filename: Input filename
        
    Returns:
        True if file type is supported, False otherwise
    """
    supported_extensions = ['.txt', '.pdf']
    ext = get_file_extension(filename)
    return ext in supported_extensions


def merge_dicts(*dicts: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge multiple dictionaries.
    
    Args:
        *dicts: Dictionaries to merge
        
    Returns:
        Merged dictionary
    """
    result = {}
    for d in dicts:
        result.update(d)
    return result


def deep_merge_dicts(dict1: Dict[str, Any], dict2: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deep merge two dictionaries.
    
    Args:
        dict1: First dictionary
        dict2: Second dictionary
        
    Returns:
        Deep merged dictionary
    """
    result = dict1.copy()
    
    for key, value in dict2.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge_dicts(result[key], value)
        else:
            result[key] = value
    
    return result


def calculate_percentage(part: int, total: int) -> float:
    """
    Calculate percentage with safe division.
    
    Args:
        part: Part value
        total: Total value
        
    Returns:
        Percentage (0-100)
    """
    if total == 0:
        return 0.0
    return (part / total) * 100


def format_duration(seconds: float) -> str:
    """
    Format duration in seconds to human readable format.
    
    Args:
        seconds: Duration in seconds
        
    Returns:
        Formatted duration string
    """
    if seconds < 60:
        return f"{seconds:.2f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.2f}m"
    else:
        hours = seconds / 3600
        return f"{hours:.2f}h"


def print_separator(char: str = "=", length: int = 80) -> None:
    """
    Print a separator line.
    
    Args:
        char: Character to use for separator
        length: Length of separator line
    """
    print(char * length)


def print_section_header(title: str, char: str = "=", length: int = 80) -> None:
    """
    Print a section header.
    
    Args:
        title: Section title
        char: Character to use for border
        length: Length of border line
    """
    print_separator(char, length)
    print(f" {title}")
    print_separator(char, length)


def smart_truncate_by_words(
    text: str, 
    max_words: int, 
    context_words: int = 2000,
    prioritize_sections: bool = True
) -> str:
    """
    Intelligently truncate text by word count, prioritizing important sections.
    
    This function is designed for medical chart processing where procedure sections
    are critical. It will:
    1. Try to find and include procedure sections
    2. Include context before/after procedure sections
    3. Fall back to beginning of text if procedure section not found
    
    Args:
        text: Input text to truncate
        max_words: Maximum number of words to keep
        context_words: Number of words to include before procedure section
        prioritize_sections: If True, prioritize finding procedure sections
        
    Returns:
        Truncated text (by word count)
    """
    if not text:
        return text
    
    # Count words in full text
    words = text.split()
    total_words = len(words)
    
    # If text is within limit, return as-is
    if total_words <= max_words:
        return text
    
    # If not prioritizing sections, just take first max_words
    if not prioritize_sections:
        truncated_words = words[:max_words]
        return " ".join(truncated_words)
    
    # Try to find procedure section
    procedure_keywords = [
        "PROCEDURE", "Procedures", "OPERATIVE PROCEDURE", "Operations",
        "PROCEDURES PERFORMED", "Surgical Procedure", "Operation"
    ]
    
    text_upper = text.upper()
    procedure_start_idx = -1
    found_keyword = None
    
    # Find the earliest procedure section
    for keyword in procedure_keywords:
        idx = text_upper.find(keyword)
        if idx != -1:
            if procedure_start_idx == -1 or idx < procedure_start_idx:
                procedure_start_idx = idx
                found_keyword = keyword
    
    if procedure_start_idx != -1:
        # Found procedure section - include context before it
        # Count words up to procedure section
        text_before_procedure = text[:procedure_start_idx]
        words_before = text_before_procedure.split()
        words_before_count = len(words_before)
        
        # Calculate how many words we can include from procedure section onwards
        words_available_for_procedure = max_words - min(context_words, words_before_count)
        
        if words_available_for_procedure > 0:
            # Include context before procedure (up to context_words)
            start_word_idx = max(0, words_before_count - context_words)
            
            # Include procedure section and beyond
            text_from_procedure = text[procedure_start_idx:]
            words_from_procedure = text_from_procedure.split()
            words_to_take = min(words_available_for_procedure, len(words_from_procedure))
            
            # Combine: context before + procedure section
            if start_word_idx > 0:
                truncated_words = words[start_word_idx:start_word_idx + context_words] + words_from_procedure[:words_to_take]
            else:
                truncated_words = words[:words_before_count] + words_from_procedure[:words_to_take]
            
            result = " ".join(truncated_words)
            print(f"[TRUNCATION] Chart truncated from {total_words:,} to {len(truncated_words):,} words "
                  f"(found '{found_keyword}' section, included {context_words} words context)")
            return result
    
    # Fallback: procedure section not found, take first max_words
    truncated_words = words[:max_words]
    print(f"[TRUNCATION] Chart truncated from {total_words:,} to {max_words:,} words "
          f"(procedure section not found, using first {max_words:,} words)")
    return " ".join(truncated_words)