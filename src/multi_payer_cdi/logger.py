"""
Logging utilities for Multi-Payer CDI system.
"""

import os
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

from .config import Config


class CDILogger:
    """Centralized logging for CDI system."""
    
    _loggers = {}
    
    @classmethod
    def setup_logger(cls, name: str, log_file: Optional[str] = None) -> logging.Logger:
        """
        Set up a logger with file and console handlers.
        
        Args:
            name: Logger name
            log_file: Optional specific log file name
            
        Returns:
            Configured logger
        """
        if name in cls._loggers:
            return cls._loggers[name]
        
        logger = logging.getLogger(name)
        logger.setLevel(logging.DEBUG if Config.DEBUG_MODE else logging.INFO)
        
        # Clear existing handlers
        logger.handlers.clear()
        
        # Create formatters
        detailed_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        simple_formatter = logging.Formatter(
            '%(levelname)s - %(message)s'
        )
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(simple_formatter)
        logger.addHandler(console_handler)
        
        # File handler
        if log_file is None:
            log_file = f"{name}_{datetime.now().strftime('%Y%m%d')}.log"
        
        log_path = os.path.join(Config.LOG_DIR, log_file)
        file_handler = logging.FileHandler(log_path, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(detailed_formatter)
        logger.addHandler(file_handler)
        
        cls._loggers[name] = logger
        return logger
    
    @classmethod
    def log_llm_call(cls, model: str, prompt_tokens: int, completion_tokens: int, 
                     cost: float, cache_hit: bool = False, purpose: str = ""):
        """
        Log LLM API call details.
        
        Args:
            model: Model ID
            prompt_tokens: Input tokens
            completion_tokens: Output tokens  
            cost: Estimated cost
            cache_hit: Whether this was a cache hit
            purpose: Purpose of the call (extraction, compliance, etc.)
        """
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "type": "llm_call",
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "cost": cost,
            "cache_hit": cache_hit,
            "purpose": purpose
        }
        
        # Append to LLM log file
        llm_log_file = os.path.join(
            Config.LOG_DIR, 
            f"llm_calls_{datetime.now().strftime('%Y%m%d')}.jsonl"
        )
        
        with open(llm_log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry) + '\n')
    
    @classmethod
    def log_opensearch_query(cls, index: str, query: str, hits: int, 
                             response_time_ms: float, payer: str = ""):
        """
        Log OpenSearch query details.
        
        Args:
            index: Index name
            query: Search query
            hits: Number of results
            response_time_ms: Response time in milliseconds
            payer: Payer name if applicable
        """
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "type": "opensearch_query",
            "index": index,
            "query": query[:200],  # Truncate long queries
            "hits": hits,
            "response_time_ms": response_time_ms,
            "payer": payer
        }
        
        # Append to OpenSearch log file
        os_log_file = os.path.join(
            Config.LOG_DIR,
            f"opensearch_queries_{datetime.now().strftime('%Y%m%d')}.jsonl"
        )
        
        with open(os_log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry) + '\n')
    
    @classmethod
    def log_json_search(cls, payer: str, query: str, hits: int, 
                       search_time_ms: float):
        """
        Log JSON guideline search details.
        
        Args:
            payer: Payer name
            query: Search query
            hits: Number of results
            search_time_ms: Search time in milliseconds
        """
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "type": "json_search",
            "payer": payer,
            "query": query[:200],  # Truncate long queries
            "hits": hits,
            "search_time_ms": search_time_ms
        }
        
        # Append to JSON search log file
        json_log_file = os.path.join(
            Config.LOG_DIR,
            f"json_searches_{datetime.now().strftime('%Y%m%d')}.jsonl"
        )
        
        with open(json_log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry) + '\n')
    
    @classmethod
    def log_processing_result(cls, file_name: str, payers_processed: int,
                              procedures_evaluated: int, total_cost: float,
                              execution_time: float, success: bool = True,
                              error: str = ""):
        """
        Log file processing result.
        
        Args:
            file_name: Name of processed file
            payers_processed: Number of payers evaluated
            procedures_evaluated: Total procedures evaluated
            total_cost: Total processing cost
            execution_time: Total execution time in seconds
            success: Whether processing succeeded
            error: Error message if failed
        """
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "type": "processing_result",
            "file_name": file_name,
            "payers_processed": payers_processed,
            "procedures_evaluated": procedures_evaluated,
            "total_cost": total_cost,
            "execution_time": execution_time,
            "success": success,
            "error": error
        }
        
        # Append to processing log file
        proc_log_file = os.path.join(
            Config.LOG_DIR,
            f"processing_{datetime.now().strftime('%Y%m%d')}.jsonl"
        )
        
        with open(proc_log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry) + '\n')
    
    @classmethod
    def save_output(cls, file_name: str, result: Dict[str, Any], 
                    output_type: str = "json"):
        """
        Save processing output to outputs directory.
        
        Args:
            file_name: Original file name
            result: Processing result
            output_type: Output format (json, txt)
        """
        # Create timestamped filename
        base_name = Path(file_name).stem
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = f"{base_name}_{timestamp}.{output_type}"
        output_path = os.path.join(Config.OUTPUT_DIR, output_file)
        
        # Save based on type
        if output_type == "json":
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False, default=str)
        else:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(str(result))
        
        logger = cls.setup_logger("cdi_system")
        logger.info(f"Output saved to: {output_path}")
        
        return output_path
    
    @classmethod
    def save_numbered_chart(cls, file_name: str, numbered_chart: str):
        """
        Save numbered medical chart to outputs directory.
        
        Args:
            file_name: Original file name
            numbered_chart: Medical chart with line numbers
        """
        # Create timestamped filename
        base_name = Path(file_name).stem
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = f"{base_name}_{timestamp}_numbered_chart.txt"
        output_path = os.path.join(Config.OUTPUT_DIR, output_file)
        
        # Save numbered chart
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(numbered_chart)
        
        logger = cls.setup_logger("cdi_system")
        logger.info(f"Numbered medical chart saved to: {output_path}")
        
        return output_path


def get_logger(name: str) -> logging.Logger:
    """
    Get or create a logger.
    
    Args:
        name: Logger name
        
    Returns:
        Logger instance
    """
    return CDILogger.setup_logger(name)


