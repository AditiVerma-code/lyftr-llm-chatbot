import time
import logging
from typing import Dict, Any, Optional, List, Tuple
import litellm
from app.config import settings
from app.models import ChatMetadata

logger = logging.getLogger(__name__)

# Initialize LiteLLM's built-in local cache
try:
    litellm.enable_cache(type="local")
    cache_enabled_status = True
except Exception as e:
    logger.error(f"Failed to enable litellm cache: {e}")
    cache_enabled_status = False


class AllProvidersUnavailableException(Exception):
    """Raised when every key in the pool fails or is simulated to fail."""
    pass


def parse_simulate_failure_header(header_val: Optional[str]) -> Dict[str, int]:
    """
    Parses X-Simulate-Failure header.
    Format: comma-separated <key_id>=<status> pairs; * means every key.
    Allowed statuses: 429, 500, 502, 503.
    Examples:
      'key_1=429' -> {'key_1': 429}
      'key_1=429,key_2=500' -> {'key_1': 429, 'key_2': 500}
      '*=429' -> {'*': 429}
    """
    if not header_val:
        return {}
    
    allowed_statuses = {429, 500, 502, 503}
    failures = {}
    for part in header_val.split(","):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            k = k.strip()
            v = v.strip()
            try:
                status_code = int(v)
                if status_code in allowed_statuses:
                    failures[k] = status_code
                else:
                    logger.warning(f"Ignoring unsupported simulated status: {status_code}")
            except ValueError:
                pass
    return failures


def generate_mock_reply(messages: List[Dict[str, str]]) -> str:
    """Generates an appropriate mock reply based on the conversation."""
    last_msg = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            last_msg = m.get("content", "").lower()
            break

    if "capital of france" in last_msg:
        return "The capital of France is Paris."
    elif "hello" in last_msg or "hi" in last_msg:
        return "Hello! How can I help you today?"
    elif "who are you" in last_msg:
        return "I am an AI assistant powered by LiteLLM."
    else:
        return f"This is an automated response to: '{last_msg[:60]}...' Context contains {len(messages)} message(s)."


def execute_chat_completion(
    messages: List[Dict[str, str]],
    model: Optional[str] = None,
    simulate_failure_header: Optional[str] = None
) -> Tuple[str, ChatMetadata]:
    """
    Executes completion across the key pool with automatic fallback and caching.
    Returns (reply_text, ChatMetadata).
    Raises AllProvidersUnavailableException if every key fails.
    """
    start_time = time.perf_counter()
    target_model = model or settings.DEFAULT_MODEL
    key_pool = settings.key_pool
    
    # Check if failure simulation is enabled and requested
    simulated_failures = {}
    is_simulation_active = False
    if settings.ENABLE_FAILURE_SIMULATION and simulate_failure_header:
        simulated_failures = parse_simulate_failure_header(simulate_failure_header)
        if simulated_failures:
            is_simulation_active = True

    # When simulating key failure, bypass cache to ensure key failover is evaluated.
    # When not simulating, check LiteLLM cache first.
    use_cache = not is_simulation_active

    fallback_attempts = 0

    # If caching is enabled and simulation is not active, try LiteLLM completion with cache check
    for idx, (key_id, api_key) in enumerate(key_pool):
        # 1. Check failure simulation
        if is_simulation_active:
            status_code = None
            if "*" in simulated_failures:
                status_code = simulated_failures["*"]
            elif key_id in simulated_failures:
                status_code = simulated_failures[key_id]

            if status_code is not None:
                logger.info(f"Simulating provider failure for {key_id} with status {status_code}")
                fallback_attempts += 1
                continue

        # 2. Determine if key is mock
        is_mock_key = settings.MOCK_LLM or api_key.startswith("mock_") or api_key.startswith("test_") or api_key.startswith("dummy_")

        try:
            kwargs = {
                "model": target_model,
                "messages": messages,
                "api_key": api_key,
                "caching": use_cache,
            }
            if is_mock_key:
                kwargs["mock_response"] = generate_mock_reply(messages)

            response = litellm.completion(**kwargs)

            # Check if this was served from cache
            hidden_params = getattr(response, "_hidden_params", {}) or {}
            is_cache_hit = bool(hidden_params.get("cache_hit"))

            # Calculate server-measured latency in ms
            elapsed_ms = max(1, int((time.perf_counter() - start_time) * 1000))

            # Extract reply text
            reply_text = ""
            if hasattr(response, "choices") and response.choices:
                first_choice = response.choices[0]
                if hasattr(first_choice, "message") and hasattr(first_choice.message, "content"):
                    reply_text = first_choice.message.content or ""
            if not reply_text:
                reply_text = "I received your message."

            # Extract token counts
            input_tokens = 0
            output_tokens = 0
            if hasattr(response, "usage") and response.usage:
                input_tokens = getattr(response.usage, "prompt_tokens", 0) or 0
                output_tokens = getattr(response.usage, "completion_tokens", 0) or 0

            # Fallback estimation if tokens are 0
            if input_tokens == 0:
                total_chars = sum(len(m.get("content", "")) for m in messages)
                input_tokens = max(1, total_chars // 4)
            if output_tokens == 0:
                output_tokens = max(1, len(reply_text) // 4)

            reported_model = getattr(response, "model", None) or target_model

            if is_cache_hit:
                # Cache hit contract: key_id is null, fallback_attempts is 0, resolution_source is LLM_CACHE
                meta = ChatMetadata(
                    resolution_source="LLM_CACHE",
                    model=reported_model,
                    latency_ms=elapsed_ms,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    key_id=None,
                    fallback_attempts=0
                )
            else:
                meta = ChatMetadata(
                    resolution_source="LIVE_INFERENCE",
                    model=reported_model,
                    latency_ms=elapsed_ms,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    key_id=key_id,
                    fallback_attempts=fallback_attempts
                )

            return reply_text, meta

        except Exception as exc:
            err_str = str(exc).lower()
            logger.warning(f"Key {key_id} failed: {exc}")
            # Provider failure (rate limit, quota, 5xx, or network failure)
            fallback_attempts += 1
            continue

    # If we exhausted all keys without success
    raise AllProvidersUnavailableException("all providers unavailable")
