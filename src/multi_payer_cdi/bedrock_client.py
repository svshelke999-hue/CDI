"""
AWS Bedrock client for Claude AI integration.
"""

import json
import threading
from typing import Tuple, Dict, Any, Optional

import boto3
import botocore

from .config import Config
from .logger import CDILogger


class BedrockClient:
    """Thread-safe AWS Bedrock client for Claude AI."""
    
    # Thread-local storage for client instances
    _thread_local = threading.local()
    
    @classmethod
    def get_client(cls):
        """Get thread-local Bedrock client."""
        if not hasattr(cls._thread_local, 'bedrock_client'):
            cls._thread_local.bedrock_client = boto3.client(
                "bedrock-runtime", 
                region_name=Config.AWS_REGION, 
                config=botocore.config.Config(read_timeout=180, connect_timeout=60)
            )
        return cls._thread_local.bedrock_client
    
    @classmethod
    def call_claude(
        cls, 
        prompt: str, 
        max_tokens: int = 800, 
        temperature: float = 0.0, 
        system_prompt: Optional[str] = None,
        enable_prompt_caching: bool = None
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Call Claude via AWS Bedrock with optional prompt caching.
        
        Args:
            prompt: User prompt text
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            system_prompt: Optional system prompt (will be cached if caching enabled)
            enable_prompt_caching: Enable Anthropic's prompt caching (defaults to Config setting)
            
        Returns:
            Tuple of (response_text, usage_info)
            
        Notes:
            Prompt caching requires:
            - Model must support caching (use cross-region inference profile)
            - System prompt must be >= MIN_CACHE_TOKENS (typically 1024-2048)
            - First call creates cache (costs 25% more)
            - Subsequent calls read cache (costs 90% less)
            - Cache TTL: 5 minutes of inactivity
        """
        client = cls.get_client()
        
        # Default to config setting if not specified
        if enable_prompt_caching is None:
            enable_prompt_caching = Config.ENABLE_PROMPT_CACHING
        
        messages = [
            {
                "role": "user",
                "content": [{"type": "text", "text": prompt}],
            }
        ]
        
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": messages,
        }
        
        if system_prompt:
            if enable_prompt_caching:
                # CRITICAL: Use cache_control to enable prompt caching
                # System prompt must be in array format with cache_control block
                body["system"] = [
                    {
                        "type": "text",
                        "text": system_prompt,
                        "cache_control": {"type": "ephemeral"}
                    }
                ]
                
                # Validate token count (rough estimate)
                estimated_tokens = len(system_prompt.split()) * 1.3
                if estimated_tokens < Config.MIN_CACHE_TOKENS:
                    print(f"[WARNING] System prompt may be below minimum cache tokens "
                          f"(~{estimated_tokens:.0f} < {Config.MIN_CACHE_TOKENS}). "
                          f"Caching may not activate!")
            else:
                # Standard system prompt (no caching)
                body["system"] = system_prompt
        
        # Try primary model first, fallback to secondary if needed
        try:
            if Config.CLAUDE_INFERENCE_PROFILE_ARN:
                resp = client.invoke_model(
                    inferenceProfileArn=Config.CLAUDE_INFERENCE_PROFILE_ARN,
                    body=json.dumps(body),
                    accept="application/json",
                    contentType="application/json",
                )
            else:
                resp = client.invoke_model(
                    modelId=Config.CLAUDE_MODEL_ID,
                    body=json.dumps(body),
                    accept="application/json",
                    contentType="application/json",
                )
        except client.exceptions.ValidationException as e:
            error_msg = str(e)
            
            # Check if it's the inference profile error
            if "inference profile" in error_msg.lower() or "on-demand throughput" in error_msg.lower():
                print(f"[ERROR] Model requires inference profile. Current model: {Config.CLAUDE_MODEL_ID}. "
                      f"Add 'us.' prefix for prompt caching support. "
                      f"Example: us.anthropic.claude-3-7-sonnet-20250219-v1:0")
            
            # Fallback to secondary model
            print(f"[INFO] Attempting fallback to: {Config.CLAUDE_FALLBACK_MODEL_ID}")
            resp = client.invoke_model(
                modelId=Config.CLAUDE_FALLBACK_MODEL_ID,
                body=json.dumps(body),
                accept="application/json",
                contentType="application/json",
            )
        
        # Parse response
        payload = json.loads(resp["body"].read())
        content = payload.get("content", [])
        
        if not content or not isinstance(content, list):
            # If response is in unexpected format, return raw payload
            return json.dumps(payload), {
                "input_tokens": 0, 
                "output_tokens": 0, 
                "model_id": Config.CLAUDE_MODEL_ID
            }
        
        # Concatenate text segments
        texts = [c.get("text", "") for c in content if isinstance(c, dict)]
        response_text = "\n".join([t for t in texts if t])
        
        usage_info = payload.get("usage", {})
        model_id = resp.get("modelId", Config.CLAUDE_MODEL_ID)
        
        # Extract all token counts including cache metrics
        input_tokens = usage_info.get("input_tokens", 0)
        output_tokens = usage_info.get("output_tokens", 0)
        cache_write_tokens = usage_info.get("cache_creation_input_tokens", 0)
        cache_read_tokens = usage_info.get("cache_read_input_tokens", 0)
        
        # Calculate cost with prompt caching
        cost = cls._calculate_cost(input_tokens, output_tokens, cache_write_tokens, cache_read_tokens)
        
        # Log cache activity if present (using print for visibility)
        if cache_write_tokens > 0:
            print(f"[CACHE] Prompt cache created: {cache_write_tokens} tokens")
        if cache_read_tokens > 0:
            print(f"[CACHE] Prompt cache hit: {cache_read_tokens} tokens (90% cheaper!)")
        
        return response_text, {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_creation_input_tokens": cache_write_tokens,
            "cache_read_input_tokens": cache_read_tokens,
            "model_id": model_id,
            "cost": cost
        }
    
    @classmethod
    def _calculate_cost(
        cls,
        input_tokens: int,
        output_tokens: int,
        cache_write_tokens: int = 0,
        cache_read_tokens: int = 0
    ) -> float:
        """
        Calculate total cost including prompt caching costs.
        
        Args:
            input_tokens: Regular input tokens
            output_tokens: Output tokens
            cache_write_tokens: Tokens written to cache (25% more expensive)
            cache_read_tokens: Tokens read from cache (90% cheaper)
            
        Returns:
            Total cost in USD
        """
        # Regular tokens (not cached)
        regular_input_cost = (input_tokens / 1000) * Config.INPUT_COST_PER_1K
        
        # Cache write tokens (25% more expensive than regular)
        cache_write_cost = (cache_write_tokens / 1000) * Config.CACHE_WRITE_COST_PER_1K
        
        # Cache read tokens (90% cheaper than regular)
        cache_read_cost = (cache_read_tokens / 1000) * Config.CACHE_READ_COST_PER_1K
        
        # Output tokens (always same price)
        output_cost = (output_tokens / 1000) * Config.OUTPUT_COST_PER_1K
        
        return regular_input_cost + cache_write_cost + cache_read_cost + output_cost
