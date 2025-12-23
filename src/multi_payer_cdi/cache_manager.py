"""
Prompt caching system for reducing LLM API costs.
"""

import os
import json
import pickle
import hashlib
import threading
from typing import Optional, Tuple, Dict, Any
from datetime import datetime, timedelta

from .config import Config
from .models import CacheStats


class CacheManager:
    """Manages prompt caching to reduce LLM API costs."""
    
    def __init__(self):
        self.cache_stats = CacheStats()
        self.cache_lock = threading.Lock()
        self.ensure_cache_dir()
        self.load_cache_stats()
    
    def ensure_cache_dir(self):
        """Ensure cache directory exists."""
        os.makedirs(Config.CACHE_DIR, exist_ok=True)
    
    def get_cache_key(
        self, 
        prompt: str, 
        system_prompt: Optional[str] = None, 
        max_tokens: int = 800, 
        temperature: float = 0.0
    ) -> str:
        """Generate a cache key for a prompt."""
        key_data = {
            "prompt": prompt,
            "system_prompt": system_prompt,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "model_id": Config.CLAUDE_MODEL_ID
        }
        key_string = json.dumps(key_data, sort_keys=True)
        return hashlib.sha256(key_string.encode()).hexdigest()
    
    def is_cache_valid(self, cache_file: str) -> bool:
        """Check if cache file is still valid based on TTL."""
        if not os.path.exists(cache_file):
            return False
        
        file_time = datetime.fromtimestamp(os.path.getmtime(cache_file))
        return datetime.now() - file_time < timedelta(hours=Config.CACHE_TTL_HOURS)
    
    def load_from_cache(self, cache_key: str) -> Optional[Tuple[str, Dict[str, Any]]]:
        """Load response from cache if valid."""
        if not Config.ENABLE_CACHE:
            return None
        
        cache_file = os.path.join(Config.CACHE_DIR, f"{cache_key}.pkl")
        
        if not self.is_cache_valid(cache_file):
            if os.path.exists(cache_file):
                os.remove(cache_file)
                with self.cache_lock:
                    self.cache_stats.cache_evictions += 1
            return None
        
        try:
            with open(cache_file, 'rb') as f:
                cached_data = pickle.load(f)
                return cached_data["response"], cached_data["usage_info"]
        except Exception as e:
            print(f"⚠️ Cache load error: {e}")
            return None
    
    def save_to_cache(self, cache_key: str, response: str, usage_info: Dict[str, Any]):
        """Save response to cache."""
        if not Config.ENABLE_CACHE:
            return
        
        self.ensure_cache_dir()
        cache_file = os.path.join(Config.CACHE_DIR, f"{cache_key}.pkl")
        
        try:
            cached_data = {
                "response": response,
                "usage_info": usage_info,
                "timestamp": datetime.now().isoformat()
            }
            with open(cache_file, 'wb') as f:
                pickle.dump(cached_data, f)
        except Exception as e:
            print(f"⚠️ Cache save error: {e}")
    
    def update_cache_stats(self, cache_type: str, hit: bool, savings: float = 0.0):
        """Update file-based cache statistics."""
        with self.cache_lock:
            if cache_type == "extraction":
                if hit:
                    self.cache_stats.extraction_hits += 1
                else:
                    self.cache_stats.extraction_misses += 1
            elif cache_type == "compliance":
                if hit:
                    self.cache_stats.compliance_hits += 1
                else:
                    self.cache_stats.compliance_misses += 1
            
            if savings > 0:
                self.cache_stats.total_savings_usd += savings
            
            self.cache_stats.last_updated = datetime.now().isoformat()
    
    def update_prompt_cache_stats(
        self, 
        cache_write_tokens: int = 0, 
        cache_read_tokens: int = 0,
        savings: float = 0.0
    ):
        """
        Update prompt cache statistics (Anthropic server-side caching).
        
        Args:
            cache_write_tokens: Tokens written to cache (first call)
            cache_read_tokens: Tokens read from cache (subsequent calls)
            savings: Cost savings from cache read vs regular input
        """
        with self.cache_lock:
            if cache_write_tokens > 0:
                self.cache_stats.prompt_cache_writes += 1
                self.cache_stats.prompt_cache_write_tokens += cache_write_tokens
            
            if cache_read_tokens > 0:
                self.cache_stats.prompt_cache_reads += 1
                self.cache_stats.prompt_cache_read_tokens += cache_read_tokens
                self.cache_stats.prompt_cache_savings_usd += savings
            
            self.cache_stats.last_updated = datetime.now().isoformat()
    
    def save_cache_stats(self):
        """Save cache statistics to file."""
        try:
            cache_stats_file = os.path.join(Config.CACHE_DIR, "cache_stats.json")
            with open(cache_stats_file, 'w') as f:
                json.dump(self.cache_stats.__dict__, f, indent=2)
        except Exception as e:
            print(f"⚠️ Failed to save cache stats: {e}")
    
    def load_cache_stats(self):
        """Load cache statistics from file."""
        try:
            cache_stats_file = os.path.join(Config.CACHE_DIR, "cache_stats.json")
            if os.path.exists(cache_stats_file):
                with open(cache_stats_file, 'r') as f:
                    loaded_stats = json.load(f)
                    self.cache_stats.__dict__.update(loaded_stats)
        except Exception as e:
            print(f"⚠️ Failed to load cache stats: {e}")
    
    def print_cache_stats(self):
        """Print comprehensive cache statistics."""
        print(f"\n[CACHE] File-Based Cache Statistics:")
        print(f"  • Extraction hits: {self.cache_stats.extraction_hits}")
        print(f"  • Extraction misses: {self.cache_stats.extraction_misses}")
        print(f"  • Compliance hits: {self.cache_stats.compliance_hits}")
        print(f"  • Compliance misses: {self.cache_stats.compliance_misses}")
        print(f"  • Cache evictions: {self.cache_stats.cache_evictions}")
        print(f"  • File cache savings: ${self.cache_stats.total_savings_usd:.6f}")
        print(f"  • File cache hit rate: {self.cache_stats.get_hit_rate():.1f}%")
        
        # Prompt cache statistics
        if self.cache_stats.prompt_cache_writes > 0 or self.cache_stats.prompt_cache_reads > 0:
            print(f"\n[CACHE] Prompt Cache Statistics (Anthropic):")
            print(f"  • Cache writes: {self.cache_stats.prompt_cache_writes}")
            print(f"  • Cache reads: {self.cache_stats.prompt_cache_reads}")
            print(f"  • Tokens cached: {self.cache_stats.prompt_cache_write_tokens:,}")
            print(f"  • Tokens read from cache: {self.cache_stats.prompt_cache_read_tokens:,}")
            print(f"  • Prompt cache savings: ${self.cache_stats.prompt_cache_savings_usd:.6f}")
            print(f"  • Prompt cache hit rate: {self.cache_stats.get_prompt_cache_hit_rate():.1f}%")
        
        # Total savings
        total_savings = self.cache_stats.total_savings_usd + self.cache_stats.prompt_cache_savings_usd
        print(f"\n[CACHE] Total Savings (File + Prompt): ${total_savings:.6f}")
    
    def cleanup_old_cache(self):
        """Clean up old cache files."""
        if not os.path.exists(Config.CACHE_DIR):
            return
        
        current_time = datetime.now()
        cleaned_count = 0
        
        for filename in os.listdir(Config.CACHE_DIR):
            if filename.endswith('.pkl'):
                file_path = os.path.join(Config.CACHE_DIR, filename)
                file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                
                if current_time - file_time > timedelta(hours=Config.CACHE_TTL_HOURS):
                    try:
                        os.remove(file_path)
                        cleaned_count += 1
                    except Exception as e:
                        print(f"⚠️ Failed to remove old cache file {filename}: {e}")
        
        if cleaned_count > 0:
            print(f"🧹 Cleaned up {cleaned_count} old cache files")
