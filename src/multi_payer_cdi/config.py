"""
Configuration management for Multi-Payer CDI Compliance Checker.
"""

import os
from typing import Dict, Any


class Config:
    """Configuration class for the Multi-Payer CDI system."""
    
    # AWS Bedrock Configuration
    AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
    # CRITICAL: Use cross-region inference profile (with "us." prefix) for prompt caching!
    CLAUDE_MODEL_ID = os.getenv("CLAUDE_MODEL_ID", "us.anthropic.claude-3-7-sonnet-20250219-v1:0")
    CLAUDE_INFERENCE_PROFILE_ARN = os.getenv("CLAUDE_INFERENCE_PROFILE_ARN", "")
    CLAUDE_FALLBACK_MODEL_ID = os.getenv("CLAUDE_FALLBACK_MODEL_ID", "anthropic.claude-3-5-sonnet-20240620-v1:0")
    
    # Prompt Caching Configuration (Anthropic's server-side caching)
    # CRITICAL: Must use cross-region inference profile for prompt caching to work
    # Example: "us.anthropic.claude-3-5-haiku-20241022-v1:0" (note the "us." prefix)
    ENABLE_PROMPT_CACHING = os.getenv("ENABLE_PROMPT_CACHING", "true").lower() in ("1", "true", "yes")
    
    # Minimum token requirements for caching by model:
    # - Claude 3.5 Haiku: 2,048 tokens
    # - Claude 3.7 Sonnet: 1,024 tokens  
    # - Claude 3.5 Sonnet v2: 1,024 tokens
    MIN_CACHE_TOKENS = int(os.getenv("MIN_CACHE_TOKENS", "1024"))
    
    # Prompt caching cost multipliers (relative to base input cost)
    CACHE_WRITE_MULTIPLIER = 1.25  # Cache creation costs 25% more
    CACHE_READ_MULTIPLIER = 0.10   # Cache reads cost 90% less!
    
    # Cache Configuration
    CACHE_DIR = os.getenv("CACHE_DIR", os.path.join(os.getcwd(), "cache"))
    CACHE_TTL_HOURS = int(os.getenv("CACHE_TTL_HOURS", "24"))
    ENABLE_CACHE = os.getenv("ENABLE_CACHE", "true").lower() in ("1", "true", "yes")
    
    # Output and Logging Configuration
    OUTPUT_DIR = os.getenv("OUTPUT_DIR", os.path.join(os.getcwd(), "outputs"))
    LOG_DIR = os.getenv("LOG_DIR", os.path.join(os.getcwd(), "logs"))
    DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() in ("1", "true", "yes")
    
    # OpenSearch Configuration
    OS_HOST = os.getenv("OS_HOST", "http://localhost:9200")
    OS_USER = os.getenv("OS_USER")
    OS_PASS = os.getenv("OS_PASS")
    OS_SSL_VERIFY = os.getenv("OS_SSL_VERIFY", "false").lower() in ("1", "true", "yes")
    OS_INDEX = os.getenv("OS_INDEX", "rag-chunks")
    
    # Processing Configuration
    TOP_K = int(os.getenv("TOP_K", "6"))
    MAX_CONTEXT_CHARS = int(os.getenv("MAX_CONTEXT_CHARS", "12000"))
    MIN_RELEVANCE_SCORE = float(os.getenv("MIN_RELEVANCE_SCORE", "10.0"))
    
    # Chart Text Truncation Configuration
    # Word-based limit for chart extraction (more accurate than character limit)
    # Claude 3.7 Sonnet supports ~200k tokens ≈ ~150k words
    # Default: 100k words (safe limit with room for prompt overhead)
    MAX_CHART_WORDS = int(os.getenv("MAX_CHART_WORDS", "100000"))
    # Context words to include before/after procedure section when truncating
    PROCEDURE_CONTEXT_WORDS = int(os.getenv("PROCEDURE_CONTEXT_WORDS", "2000"))
    
    # Input/Output Configuration
    CHART_INPUT_DIR = os.getenv("CHART_INPUT_DIR", os.path.join(os.getcwd(), "data"))
    
    # JSON Guideline Data Paths (can be overridden with environment variables)
    JSON_GUIDELINE_PATHS = {
        "anthem": os.getenv(
            "ANTHEM_JSON_PATH",
            r"C:\Users\svshelke\OneDrive\CDI\Final_refact_CDI_copy - Copy - Backup - 10_19_amrishdemo\src\multi_payer_cdi\JSON_Data\extracted_procedures_single_call_Anthem_with_evidence_v2"
        ),
        "uhc": os.getenv(
            "UHC_JSON_PATH",
            r"C:\Users\svshelke\OneDrive\CDI\Final_refact_CDI_copy - Copy - Backup - 10_19_amrishdemo\src\multi_payer_cdi\JSON_Data\extracted_procedures_single_call_UHC_with_evidence_v2"
        ),
        "cigna": os.getenv(
            "CIGNA_JSON_PATH",
            r"C:\Users\svshelke\OneDrive\CDI\Final_refact_CDI_copy - Copy - Backup - 10_19_amrishdemo\src\multi_payer_cdi\JSON_Data\extracted_procedures_single_call_cigna_with_evidence_v2"
        )
    }
    
    # Data Source Configuration: 'opensearch' or 'json'
    DATA_SOURCE = os.getenv("DATA_SOURCE", "json")
    
    # Multi-payer Configuration
    PAYER_CONFIG = {
        "cigna": {
            "name": "Cigna",
            "os_index": OS_INDEX,
            "json_data_path": JSON_GUIDELINE_PATHS["cigna"],
            "filter_terms": ["cigna", "cigna_procedures"],
            "priority": 1
        },
        "uhc": {
            "name": "UnitedHealthcare", 
            "os_index": OS_INDEX,
            "json_data_path": JSON_GUIDELINE_PATHS["uhc"],
            "filter_terms": ["uhc", "uhc_procedures", "united", "unitedhealth"],
            "priority": 2
        },
        "anthem": {
            "name": "Anthem",
            "os_index": OS_INDEX,
            "json_data_path": JSON_GUIDELINE_PATHS["anthem"],
            "filter_terms": ["anthem", "anthem_procedures"],
            "priority": 3
        }
    }
    
    # Cost Configuration (per 1K tokens)
    INPUT_COST_PER_1K = 0.003
    OUTPUT_COST_PER_1K = 0.015
    
    # Prompt Caching Pricing (per 1K tokens)
    # These are calculated from base input cost with multipliers above
    CACHE_WRITE_COST_PER_1K = INPUT_COST_PER_1K * CACHE_WRITE_MULTIPLIER  # $0.00375
    CACHE_READ_COST_PER_1K = INPUT_COST_PER_1K * CACHE_READ_MULTIPLIER    # $0.0003
    
    @classmethod
    def get_payer_config(cls, payer_key: str) -> Dict[str, Any]:
        """Get configuration for a specific payer."""
        return cls.PAYER_CONFIG.get(payer_key, {})
    
    @classmethod
    def get_sorted_payers(cls) -> list:
        """Get payers sorted by priority."""
        return sorted(cls.PAYER_CONFIG.items(), key=lambda x: x[1].get("priority", 999))
    
    @classmethod
    def validate_config(cls) -> bool:
        """Validate that required configuration is present."""
        required_env_vars = [
            "AWS_REGION",
            "CLAUDE_MODEL_ID"
        ]
        
        for var in required_env_vars:
            if not getattr(cls, var):
                print(f"❌ Missing required environment variable: {var}")
                return False
        
        return True
