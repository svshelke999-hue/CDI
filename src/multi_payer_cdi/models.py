"""
Data models for the Multi-Payer CDI Compliance Checker.
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class UsageInfo:
    """Token usage and cost information with prompt caching support."""
    input_tokens: int = 0
    output_tokens: int = 0
    model_id: str = "unknown"
    input_cost: float = 0.0
    output_cost: float = 0.0
    total_cost: float = 0.0
    
    # Prompt caching metrics (Anthropic server-side caching)
    cache_creation_input_tokens: int = 0  # Tokens written to cache (25% more expensive)
    cache_read_input_tokens: int = 0      # Tokens read from cache (90% cheaper)
    cache_write_cost: float = 0.0
    cache_read_cost: float = 0.0
    
    def calculate_costs(
        self, 
        input_cost_per_1k: float = 0.003, 
        output_cost_per_1k: float = 0.015,
        cache_write_cost_per_1k: float = 0.00375,
        cache_read_cost_per_1k: float = 0.0003
    ):
        """Calculate costs based on token usage including prompt caching."""
        # Regular input tokens
        self.input_cost = (self.input_tokens / 1000) * input_cost_per_1k
        
        # Output tokens
        self.output_cost = (self.output_tokens / 1000) * output_cost_per_1k
        
        # Cache write tokens (25% more expensive)
        self.cache_write_cost = (self.cache_creation_input_tokens / 1000) * cache_write_cost_per_1k
        
        # Cache read tokens (90% cheaper)
        self.cache_read_cost = (self.cache_read_input_tokens / 1000) * cache_read_cost_per_1k
        
        self.total_cost = self.input_cost + self.output_cost + self.cache_write_cost + self.cache_read_cost
    
    @property
    def cache_hit(self) -> bool:
        """Returns True if cache was read from."""
        return self.cache_read_input_tokens > 0
    
    @property
    def cache_created(self) -> bool:
        """Returns True if cache was written."""
        return self.cache_creation_input_tokens > 0


@dataclass
class CacheStats:
    """Cache statistics tracking for both file-based and prompt caching."""
    # File-based cache stats (local disk caching)
    extraction_hits: int = 0
    extraction_misses: int = 0
    compliance_hits: int = 0
    compliance_misses: int = 0
    cache_evictions: int = 0
    total_savings_usd: float = 0.0
    
    # Prompt cache stats (Anthropic server-side caching)
    prompt_cache_writes: int = 0          # Number of times cache was created
    prompt_cache_reads: int = 0           # Number of times cache was read
    prompt_cache_write_tokens: int = 0    # Total tokens written to cache
    prompt_cache_read_tokens: int = 0     # Total tokens read from cache
    prompt_cache_savings_usd: float = 0.0 # Cost savings from prompt caching
    
    last_updated: str = ""
    
    def __post_init__(self):
        if not self.last_updated:
            self.last_updated = datetime.now().isoformat()
    
    def get_hit_rate(self) -> float:
        """Calculate overall file cache hit rate."""
        total_hits = self.extraction_hits + self.compliance_hits
        total_requests = total_hits + self.extraction_misses + self.compliance_misses
        return (total_hits / total_requests * 100) if total_requests > 0 else 0.0
    
    def get_prompt_cache_hit_rate(self) -> float:
        """Calculate prompt cache hit rate."""
        total_calls = self.prompt_cache_writes + self.prompt_cache_reads
        return (self.prompt_cache_reads / total_calls * 100) if total_calls > 0 else 0.0


@dataclass
class PayerConfig:
    """Configuration for a specific payer."""
    name: str
    os_index: str
    filter_terms: List[str]
    priority: int


@dataclass
class ProcedureResult:
    """Result of procedure evaluation for a specific payer."""
    procedure_evaluated: str
    variant_or_subprocedure: str
    policy_name: str
    decision: str  # "Sufficient", "Insufficient"
    primary_reasons: List[str]
    requirement_checklist: List[Dict[str, Any]]
    timing_validation: Dict[str, Any]
    contraindications_exclusions: Dict[str, Any]
    coding_implications: Dict[str, Any]
    improvement_recommendations: Dict[str, Any]
    guideline_availability: Dict[str, Any]


@dataclass
class ComplianceResult:
    """Complete compliance evaluation result for a payer."""
    payer_name: str
    procedures_evaluated: int
    procedure_results: List[ProcedureResult]
    usage: UsageInfo
    sources: List[Dict[str, Any]]
    error: Optional[str] = None


@dataclass
class ProcessingResult:
    """Complete processing result for a medical chart."""
    file_name: str
    extraction_data: Dict[str, Any]
    payer_results: Dict[str, ComplianceResult]
    total_usage: UsageInfo
    total_cost: float
    execution_times: Dict[str, float]
    sources: List[Dict[str, Any]]
    numbered_medical_chart: Optional[str] = None
    original_chart: Optional[str] = None
    improved_chart_by_ai: Optional[str] = None
    enhanced_by_ai: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    payer_summary: Dict[str, Any] = field(default_factory=dict)


class ExtractionData:
    """Data extracted from medical chart."""
    
    def __init__(self, cpt_codes: List[str], procedures: List[str], summary: str):
        self.cpt_codes = cpt_codes
        self.procedures = procedures
        self.summary = summary
        self.has_cpt_codes = len(cpt_codes) > 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return {
            "cpt": self.cpt_codes,
            "procedure": self.procedures,
            "summary": self.summary,
            "has_cpt_codes": self.has_cpt_codes
        }
    
    @classmethod
    def from_json(cls, json_str: str) -> 'ExtractionData':
        """Create from JSON string."""
        import json
        data = json.loads(json_str)
        return cls(
            cpt_codes=data.get("cpt", []),
            procedures=data.get("procedure", []),
            summary=data.get("summary", "")
        )
