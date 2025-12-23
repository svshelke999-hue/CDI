#!/usr/bin/env python3
"""
TEST PROMPT CACHING IMPLEMENTATION FOR CDI PROJECT
==================================================

This script demonstrates and validates Anthropic's Prompt Caching feature
in the CDI (Clinical Documentation Improvement) project.

What this test does:
1. Loads comprehensive CDI system prompt (1024+ tokens)
2. Makes multiple API calls with the same system prompt
3. First call creates cache (shows cache_creation_input_tokens)
4. Subsequent calls read from cache (shows cache_read_input_tokens)
5. Calculates and displays cost savings

Expected Results:
✓ Call 1: Creates cache (cache_creation_input_tokens > 0)
✓ Call 2-3: Read from cache (cache_read_input_tokens > 0)
✓ Cost reduction: ~40-50% on calls 2-3
✓ Latency improvement: ~10-20%

Requirements:
- AWS credentials configured
- Model must support caching (use inference profile ARN)
- System prompt must be >= 1024 tokens (Claude 3.7 Sonnet)
- ENABLE_PROMPT_CACHING=true in config

Author: CDI Development Team
Date: October 2025
"""

import os
import sys
import json
import time
from datetime import datetime
from typing import List, Dict, Tuple

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from multi_payer_cdi.bedrock_client import BedrockClient
from multi_payer_cdi.config import Config
from multi_payer_cdi.cache_manager import CacheManager


class PromptCachingValidator:
    """Validates prompt caching implementation."""
    
    def __init__(self):
        """Initialize validator."""
        self.cache_manager = CacheManager()
        self.results = []
        
        # Load CDI system prompt
        prompt_path = os.path.join("prompts", "cdi_system_prompt.txt")
        if os.path.exists(prompt_path):
            with open(prompt_path, 'r', encoding='utf-8') as f:
                self.system_prompt = f.read()
        else:
            print(f"⚠️  WARNING: System prompt file not found: {prompt_path}")
            print("Using minimal system prompt for testing...")
            self.system_prompt = self._create_minimal_system_prompt()
        
        # Validate system prompt length
        estimated_tokens = len(self.system_prompt.split()) * 1.3
        print(f"\n{'='*70}")
        print(f"PROMPT CACHING VALIDATION TEST")
        print(f"{'='*70}")
        print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Model: {Config.CLAUDE_MODEL_ID}")
        print(f"Region: {Config.AWS_REGION}")
        print(f"Prompt Caching: {'ENABLED' if Config.ENABLE_PROMPT_CACHING else 'DISABLED'}")
        print(f"Min Cache Tokens: {Config.MIN_CACHE_TOKENS}")
        print(f"System Prompt Length: ~{estimated_tokens:.0f} tokens")
        
        # Check for common configuration issues
        model_id = Config.CLAUDE_MODEL_ID
        if not model_id.startswith(("us.", "eu.", "ap-", "inference-profile/")):
            print(f"\n*** WARNING: Model ID missing region prefix! ***")
            print(f"Current: {model_id}")
            print(f"Should be: us.{model_id}")
            print(f"Prompt caching REQUIRES cross-region inference profile!")
            print(f"Fix in config.py or set CLAUDE_MODEL_ID=us.{model_id}")
        
        if estimated_tokens < Config.MIN_CACHE_TOKENS:
            print(f"⚠️  WARNING: System prompt may be below minimum!")
            print(f"   Required: {Config.MIN_CACHE_TOKENS} tokens")
            print(f"   Estimated: {estimated_tokens:.0f} tokens")
            print(f"   Caching may not activate!")
        else:
            print(f"✓ System prompt meets minimum token requirement")
        
        print(f"{'='*70}\n")
    
    def _create_minimal_system_prompt(self) -> str:
        """Create a minimal system prompt that meets token requirements."""
        # This is a fallback if the file doesn't exist
        # Repeated content to reach minimum tokens
        base_prompt = """You are an expert Clinical Documentation Improvement (CDI) specialist 
        and medical coding consultant with comprehensive knowledge of CPT, ICD-10, and payer-specific 
        medical necessity guidelines. """
        
        # Repeat to reach minimum tokens
        repeated_prompt = base_prompt * 100  # ~1300 tokens
        return repeated_prompt
    
    def run_without_caching(self, queries: List[str]) -> List[Dict]:
        """
        Test WITHOUT prompt caching (baseline).
        
        Args:
            queries: List of test queries
            
        Returns:
            List of result dictionaries
        """
        print(f"\n{'='*70}")
        print(f"TEST 1: WITHOUT PROMPT CACHING (Baseline)")
        print(f"{'='*70}\n")
        
        results = []
        
        for i, query in enumerate(queries, 1):
            print(f"[{i}/{len(queries)}] Query: {query[:60]}...")
            
            start_time = time.time()
            response, usage_info = BedrockClient.call_claude(
                prompt=query,
                max_tokens=500,
                temperature=0.0,
                system_prompt=self.system_prompt,
                enable_prompt_caching=False  # Explicitly disable
            )
            latency_ms = (time.time() - start_time) * 1000
            
            result = {
                "query": query,
                "input_tokens": usage_info.get("input_tokens", 0),
                "output_tokens": usage_info.get("output_tokens", 0),
                "cache_write_tokens": usage_info.get("cache_creation_input_tokens", 0),
                "cache_read_tokens": usage_info.get("cache_read_input_tokens", 0),
                "cost": usage_info.get("cost", 0),
                "latency_ms": latency_ms
            }
            
            results.append(result)
            
            print(f"      Input: {result['input_tokens']}, "
                  f"Output: {result['output_tokens']}, "
                  f"Cost: ${result['cost']:.6f}, "
                  f"Latency: {latency_ms:.0f}ms")
            
            # Small delay between calls
            if i < len(queries):
                time.sleep(0.5)
        
        return results
    
    def run_with_caching(self, queries: List[str]) -> List[Dict]:
        """
        Test WITH prompt caching.
        
        Args:
            queries: List of test queries
            
        Returns:
            List of result dictionaries
        """
        print(f"\n{'='*70}")
        print(f"TEST 2: WITH PROMPT CACHING")
        print(f"{'='*70}")
        print(f"ℹ️  Call 1 creates cache, calls 2-3 read from cache\n")
        
        results = []
        
        for i, query in enumerate(queries, 1):
            cache_status = "Cache Write" if i == 1 else "Cache Read"
            print(f"[{i}/{len(queries)}] {cache_status}: {query[:60]}...")
            
            start_time = time.time()
            response, usage_info = BedrockClient.call_claude(
                prompt=query,
                max_tokens=500,
                temperature=0.0,
                system_prompt=self.system_prompt,
                enable_prompt_caching=True  # Explicitly enable
            )
            latency_ms = (time.time() - start_time) * 1000
            
            result = {
                "query": query,
                "input_tokens": usage_info.get("input_tokens", 0),
                "output_tokens": usage_info.get("output_tokens", 0),
                "cache_write_tokens": usage_info.get("cache_creation_input_tokens", 0),
                "cache_read_tokens": usage_info.get("cache_read_input_tokens", 0),
                "cost": usage_info.get("cost", 0),
                "latency_ms": latency_ms
            }
            
            results.append(result)
            
            # Update cache manager stats
            if result['cache_write_tokens'] > 0 or result['cache_read_tokens'] > 0:
                # Calculate savings (difference between regular input cost and cache cost)
                regular_cost = (result['cache_read_tokens'] / 1000) * Config.INPUT_COST_PER_1K
                cache_cost = (result['cache_read_tokens'] / 1000) * Config.CACHE_READ_COST_PER_1K
                savings = regular_cost - cache_cost
                
                self.cache_manager.update_prompt_cache_stats(
                    cache_write_tokens=result['cache_write_tokens'],
                    cache_read_tokens=result['cache_read_tokens'],
                    savings=savings
                )
            
            print(f"      Input: {result['input_tokens']}, "
                  f"Output: {result['output_tokens']}, "
                  f"Cache Write: {result['cache_write_tokens']}, "
                  f"Cache Read: {result['cache_read_tokens']}, "
                  f"Cost: ${result['cost']:.6f}, "
                  f"Latency: {latency_ms:.0f}ms")
            
            # Small delay between calls (but within 5 min cache TTL)
            if i < len(queries):
                time.sleep(0.5)
        
        return results
    
    def analyze_results(
        self, 
        no_cache_results: List[Dict], 
        cache_results: List[Dict]
    ):
        """
        Analyze and display results comparison.
        
        Args:
            no_cache_results: Results without caching
            cache_results: Results with caching
        """
        print(f"\n{'='*70}")
        print(f"RESULTS ANALYSIS")
        print(f"{'='*70}")
        
        # Calculate totals
        no_cache_cost = sum(r['cost'] for r in no_cache_results)
        cache_cost = sum(r['cost'] for r in cache_results)
        no_cache_latency = sum(r['latency_ms'] for r in no_cache_results) / len(no_cache_results)
        cache_latency = sum(r['latency_ms'] for r in cache_results) / len(cache_results)
        
        # Savings
        cost_savings = no_cache_cost - cache_cost
        cost_savings_pct = (cost_savings / no_cache_cost * 100) if no_cache_cost > 0 else 0
        latency_savings = no_cache_latency - cache_latency
        latency_savings_pct = (latency_savings / no_cache_latency * 100) if no_cache_latency > 0 else 0
        
        print(f"\n💰 COST ANALYSIS:")
        print(f"   Without Caching: ${no_cache_cost:.6f}")
        print(f"   With Caching:    ${cache_cost:.6f}")
        print(f"   Savings:         ${cost_savings:.6f} ({cost_savings_pct:.1f}% reduction)")
        
        print(f"\n⚡ PERFORMANCE ANALYSIS:")
        print(f"   Without Caching: {no_cache_latency:.0f}ms avg")
        print(f"   With Caching:    {cache_latency:.0f}ms avg")
        if latency_savings > 0:
            print(f"   Improvement:     {latency_savings:.0f}ms ({latency_savings_pct:.1f}% faster)")
        else:
            print(f"   Difference:      {abs(latency_savings):.0f}ms slower (network variance)")
        
        print(f"\n🔍 CACHE VERIFICATION:")
        if cache_results[0]['cache_write_tokens'] > 0:
            print(f"   Call 1 - Cache Written: {cache_results[0]['cache_write_tokens']} tokens ✓")
        else:
            print(f"   Call 1 - Cache Written: 0 tokens ❌ CACHING NOT WORKING!")
        
        for i in range(1, len(cache_results)):
            if cache_results[i]['cache_read_tokens'] > 0:
                print(f"   Call {i+1} - Cache Read:    {cache_results[i]['cache_read_tokens']} tokens ✓")
            else:
                print(f"   Call {i+1} - Cache Read:    0 tokens ❌ CACHE NOT REUSED!")
        
        # Projections
        calls_1k = 1000
        projected_no_cache = (no_cache_cost / len(no_cache_results)) * calls_1k
        projected_cache = (cache_cost / len(cache_results)) * calls_1k
        projected_savings = projected_no_cache - projected_cache
        
        print(f"\n📈 PROJECTIONS (1,000 calls):")
        print(f"   Without Caching: ${projected_no_cache:.2f}")
        print(f"   With Caching:    ${projected_cache:.2f}")
        print(f"   Total Savings:   ${projected_savings:.2f}")
        
        print(f"\n📈 PROJECTIONS (10,000 calls/month):")
        print(f"   Monthly Savings:  ${projected_savings * 10:.2f}")
        print(f"   Annual Savings:   ${projected_savings * 120:.2f}")
        
        # Verification summary
        print(f"\n✅ VERIFICATION CHECKLIST:")
        checklist = {
            "Model supports caching": Config.CLAUDE_INFERENCE_PROFILE_ARN != "" or "anthropic.claude-3" in Config.CLAUDE_MODEL_ID,
            "Prompt caching enabled": Config.ENABLE_PROMPT_CACHING,
            "System prompt >= min tokens": len(self.system_prompt.split()) * 1.3 >= Config.MIN_CACHE_TOKENS,
            "Cache created (call 1)": cache_results[0]['cache_write_tokens'] > 0,
            "Cache read (call 2+)": any(r['cache_read_tokens'] > 0 for r in cache_results[1:]),
            "Cost savings achieved": cost_savings > 0
        }
        
        for check, passed in checklist.items():
            status = "✓" if passed else "❌"
            print(f"   {status} {check}")
        
        all_passed = all(checklist.values())
        
        print(f"\n{'='*70}")
        if all_passed:
            print(f"✅ PROMPT CACHING IS WORKING CORRECTLY!")
            print(f"   Cost Reduction: {cost_savings_pct:.1f}%")
            print(f"   Ready for production use!")
        else:
            print(f"❌ PROMPT CACHING IS NOT WORKING PROPERLY!")
            print(f"\nTROUBLESHOOTING TIPS:")
            if not checklist["Model supports caching"]:
                print(f"   • Use cross-region inference profile (e.g., us.anthropic.claude-3-5-haiku-20241022-v1:0)")
            if not checklist["Prompt caching enabled"]:
                print(f"   • Set ENABLE_PROMPT_CACHING=true in config")
            if not checklist["System prompt >= min tokens"]:
                print(f"   • Expand system prompt to >= {Config.MIN_CACHE_TOKENS} tokens")
            if not checklist["Cache created (call 1)"]:
                print(f"   • Check model ID includes region prefix (us., eu., etc.)")
                print(f"   • Verify model has caching support enabled in AWS")
            if not checklist["Cache read (call 2+)"]:
                print(f"   • Ensure calls made within 5 minutes")
                print(f"   • Verify system prompt is identical across calls")
        print(f"{'='*70}\n")
        
        # Save cache stats
        self.cache_manager.save_cache_stats()
        self.cache_manager.print_cache_stats()


def main():
    """Main test execution."""
    # Test queries
    queries = [
        "What are the key CPT codes for knee arthroscopy with meniscectomy?",
        "Explain the medical necessity criteria for lumbar spinal fusion.",
        "What documentation is required for coronary artery bypass graft (CABG)?"
    ]
    
    # Initialize validator
    validator = PromptCachingValidator()
    
    # Check configuration
    if not Config.ENABLE_PROMPT_CACHING:
        print("\n⚠️  WARNING: Prompt caching is DISABLED in configuration!")
        print("Set ENABLE_PROMPT_CACHING=true to enable it.\n")
        response = input("Continue with test anyway? (y/n): ")
        if response.lower() != 'y':
            print("Test cancelled.")
            return
    
    # Run tests
    try:
        # Test 1: Without caching (baseline)
        no_cache_results = validator.run_without_caching(queries)
        
        # Wait before cache test
        print("\n⏳ Waiting 2 seconds before cache test...")
        time.sleep(2)
        
        # Test 2: With caching
        cache_results = validator.run_with_caching(queries)
        
        # Analyze results
        validator.analyze_results(no_cache_results, cache_results)
        
    except Exception as e:
        print(f"\n❌ ERROR during test: {e}")
        import traceback
        traceback.print_exc()
        print("\nPossible issues:")
        print("- AWS credentials not configured")
        print("- Model not available in your region")
        print("- Insufficient IAM permissions")
        print("- Model doesn't support prompt caching")


if __name__ == "__main__":
    main()

