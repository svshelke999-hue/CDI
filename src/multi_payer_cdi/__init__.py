"""
Multi-Payer CDI Compliance Checker

Enhanced Clinical Documentation Improvement (CDI) system with multi-payer support,
RAG integration, and comprehensive prompt caching.
"""

__version__ = "1.0.0"
__author__ = "CDI Team"

from .core import MultiPayerCDI
from .models import (
    PayerConfig,
    CacheStats,
    ComplianceResult,
    ProcedureResult,
    UsageInfo
)
from .logger import CDILogger, get_logger

__all__ = [
    "MultiPayerCDI",
    "PayerConfig", 
    "CacheStats",
    "ComplianceResult",
    "ProcedureResult",
    "UsageInfo",
    "CDILogger",
    "get_logger"
]
