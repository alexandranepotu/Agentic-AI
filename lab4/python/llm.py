"""llm.py - one helper for every Lab 4 experiment: a single model call, measured.

Install once, inside your virtual environment from Labs 2 and 3:

    pip install google-genai python-dotenv pydantic pytest

    google-genai    the Gemini SDK used by this file
    python-dotenv   loads GEMINI_API_KEY from your .env file
    pydantic        the structured outputs in Experiments 3, 4 and 5
    pytest          the offline tests: pytest test_exp4_day.py test_exp5_tools.py

Tested with Python 3.14, google-genai 2.31.0, python-dotenv 1.2.4, pydantic 2.14.1, pytest 9.1.1.
The .env with GEMINI_API_KEY=... must be in this folder or in one of its parent folders.
Experiment 5 also needs your agent_core.py from Lab 3 in this folder.

Settings (environment variables, all optional):
    LAB_MODEL     the model (default gemini-3.5-flash-lite; fallback gemini-3.1-flash-lite, which has its own quota)
    LAB_TIMEOUT   seconds to wait for one answer (default 30); a timed-out request is tried 3 times in all
"""
import os
import time
from dataclasses import dataclass
from typing import Any

import httpx
from dotenv import load_dotenv
from google import genai
from google.genai import errors, types

load_dotenv()
MODEL = os.getenv("LAB_MODEL", "gemini-3.5-flash-lite")
TIMEOUT_S = float(os.getenv("LAB_TIMEOUT", "30"))
ATTEMPTS = 3

# The SDK retries overloads (503) and timeouts by itself. 429 is NOT in this list on purpose:
# a daily quota will not come back in a minute, so ask() handles 429 itself.
client = genai.Client(http_options=types.HttpOptions(
    timeout=int(TIMEOUT_S * 1000),  # milliseconds, per request
    retry_options=types.HttpRetryOptions(attempts=ATTEMPTS, initial_delay=2.0,
                                         http_status_codes=[408, 500, 502, 503, 504]),
))


class QuotaExhausted(RuntimeError):
    """The free tier's daily request limit for this model is used up."""


def _generate(contents, config):
    """One request: fail fast on a daily quota, wait and retry a per-minute limit, give up on a timeout."""
    for attempt in range(3):
        try:
            return client.models.generate_content(model=MODEL, contents=contents, config=config)
        except errors.ClientError as e:
            if e.code != 429:
                raise
            if "PerDay" in str(e):
                raise QuotaExhausted(
                    f"The free tier's daily request limit for {MODEL} is used up (about 500 requests per day). "
                    "Wait until it resets, use another API key, or switch model: "
                    "set LAB_MODEL=gemini-3.1-flash-lite"
                ) from None
            if attempt == 2:
                raise
            print(f"  .. rate limited (429), waiting {20 * (attempt + 1)} s")
            time.sleep(20 * (attempt + 1))  # a per-minute limit: it clears quickly
        except httpx.TimeoutException:
            raise TimeoutError(f"No answer from {MODEL} within {TIMEOUT_S:g} s, {ATTEMPTS} attempts "
                               "(the service may be overloaded; set LAB_TIMEOUT to wait longer)") from None


@dataclass
class Reply:
    text: str
    parsed: Any          # the validated object when a schema was given
    in_tokens: int
    out_tokens: int      # includes thinking tokens
    seconds: float


def ask(prompt: str, *, system: str | None = None, temperature: float | None = None,
        schema: Any = None, contents: list | None = None) -> Reply:
    """One call. `schema` = a Pydantic model for structured output. `contents` overrides `prompt`
    when you need a multi-turn history."""
    config = types.GenerateContentConfig(
        system_instruction=system,
        temperature=temperature,
        response_mime_type="application/json" if schema else None,
        response_schema=schema,
    )
    t0 = time.perf_counter()
    res = _generate(contents or prompt, config)
    u = res.usage_metadata
    return Reply(
        text=res.text or "",
        parsed=res.parsed if schema else None,
        in_tokens=u.prompt_token_count or 0,
        out_tokens=(u.candidates_token_count or 0) + (u.thoughts_token_count or 0),
        seconds=time.perf_counter() - t0,
    )
