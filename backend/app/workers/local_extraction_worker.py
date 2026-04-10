"""
Phase 6 — Local Extraction Worker

A lightweight, standalone worker intended to run on a local machine with
an NVIDIA GPU.  It consumes jobs from the remote Redis queue
(``pharos_extraction_jobs``), passes each diff to a locally-hosted LLM
(Ollama / vLLM at an OpenAI-compatible endpoint), extracts a structured
coding-rule JSON schema, and POSTs the result back to the cloud
backend's ``/api/patterns/propose`` route.

Usage
-----
    # Ensure Ollama is running locally:
    #   ollama serve
    #   ollama pull codellama:13b

    python -m app.workers.local_extraction_worker \
        --redis-url redis://your-cloud-redis:6379/0 \
        --api-url   https://pharos.onrender.com \
        --api-token YOUR_BEARER_TOKEN \
        --llm-url   http://localhost:11434 \
        --model     codellama:13b

Environment Variables (override CLI flags)
------------------------------------------
    PHAROS_REDIS_URL        Redis connection string
    PHAROS_API_URL          Cloud backend base URL
    PHAROS_API_TOKEN        Bearer token for /api/patterns/propose
    PHAROS_LLM_URL          Local LLM endpoint (Ollama/vLLM)
    PHAROS_LLM_MODEL        Model name to use for extraction
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from typing import Any, Dict, Optional

import httpx
import redis

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("pharos.extraction_worker")

# ============================================================================
# LLM Interface
# ============================================================================

EXTRACTION_SYSTEM_PROMPT = """\
You are a senior software architect.  Given a unified diff of a Python file,
extract the single most important **coding rule** that the change represents.

Return ONLY a JSON object with these keys (no markdown fences):
{
  "rule_name": "<short PascalCase name, e.g. UseAsyncContextManagers>",
  "rule_description": "<1-3 sentence description of the pattern>",
  "rule_schema": {
    "applies_to": "<file glob or module path>",
    "pattern_type": "<error_handling | naming | architecture | async | testing | other>",
    "example_before": "<short code snippet before the change>",
    "example_after": "<short code snippet after the change>",
    "rationale": "<why this pattern is preferred>"
  },
  "confidence": <float 0.0–1.0>
}
"""


def extract_rule_via_llm(
    diff: str,
    file_path: str,
    llm_url: str,
    model: str,
) -> Optional[Dict[str, Any]]:
    """
    Send a diff to the local LLM and parse the structured rule response.

    Uses the ``/v1/chat/completions`` OpenAI-compatible endpoint exposed
    by Ollama and vLLM.
    """
    user_prompt = (
        f"File: {file_path}\n\n"
        f"```diff\n{diff}\n```\n\n"
        "Extract the coding rule as JSON."
    )

    # Ollama exposes /v1/chat/completions when running with OpenAI compat
    # but also exposes /api/chat natively.  We try the OpenAI path first.
    endpoint = f"{llm_url.rstrip('/')}/v1/chat/completions"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 1024,
    }

    try:
        with httpx.Client(timeout=120) as client:
            resp = client.post(endpoint, json=payload)
            resp.raise_for_status()

        content = resp.json()["choices"][0]["message"]["content"]

        # Strip markdown fences if the model wraps the JSON
        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1]
        if content.endswith("```"):
            content = content.rsplit("```", 1)[0]
        content = content.strip()

        return json.loads(content)

    except (httpx.HTTPError, json.JSONDecodeError, KeyError, IndexError) as exc:
        logger.error("LLM extraction failed: %s", exc)
        return None


# ============================================================================
# Job Processing
# ============================================================================


def process_job(
    job_json: str,
    llm_url: str,
    model: str,
    api_url: str,
    api_token: str,
) -> bool:
    """
    Process a single extraction job:
    1. Deserialize the Redis message.
    2. Call the local LLM.
    3. POST the extracted rule to the cloud backend.

    Returns True on success.
    """
    try:
        job = json.loads(job_json)
    except json.JSONDecodeError:
        logger.error("Malformed job payload — skipping")
        return False

    diff = job.get("diff", "")
    file_path = job.get("file_path", "unknown")
    repository = job.get("repository", "")
    commit_sha = job.get("commit_sha", "")

    logger.info("Processing: %s @ %s — %s", file_path, commit_sha[:8], repository)

    rule = extract_rule_via_llm(diff, file_path, llm_url, model)
    if rule is None:
        logger.warning("LLM returned no usable rule for %s — skipping", file_path)
        return False

    # POST to the cloud backend
    propose_url = f"{api_url.rstrip('/')}/api/patterns/propose"
    payload = {
        "repository": repository,
        "commit_sha": commit_sha,
        "file_path": file_path,
        "diff_payload": diff,
        "rule_name": rule.get("rule_name", "UnnamedRule"),
        "rule_description": rule.get("rule_description", ""),
        "rule_schema": rule.get("rule_schema", {}),
        "confidence": float(rule.get("confidence", 0.0)),
    }

    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                propose_url,
                json=payload,
                headers={"Authorization": f"Bearer {api_token}"},
            )
            resp.raise_for_status()

        result = resp.json()
        logger.info(
            "Rule proposed: %s (id=%s, status=%s)",
            payload["rule_name"],
            result.get("id"),
            result.get("status"),
        )
        return True

    except httpx.HTTPError as exc:
        logger.error("Failed to POST rule to cloud: %s", exc)
        return False


# ============================================================================
# Main Loop
# ============================================================================


def run_worker(
    redis_url: str,
    queue_name: str,
    llm_url: str,
    model: str,
    api_url: str,
    api_token: str,
    poll_interval: float = 2.0,
):
    """
    Blocking loop: BRPOP from the Redis queue, process each job, repeat.
    """
    r = redis.Redis.from_url(redis_url, decode_responses=True)

    logger.info("=" * 60)
    logger.info("Pharos Local Extraction Worker")
    logger.info("  Redis:     %s", redis_url)
    logger.info("  Queue:     %s", queue_name)
    logger.info("  LLM:       %s (%s)", llm_url, model)
    logger.info("  API:       %s", api_url)
    logger.info("=" * 60)

    while True:
        try:
            # BRPOP blocks until a message is available (timeout=poll_interval)
            result = r.brpop(queue_name, timeout=int(poll_interval))
            if result is None:
                continue

            _, job_json = result
            process_job(job_json, llm_url, model, api_url, api_token)

        except redis.ConnectionError as exc:
            logger.error("Redis connection lost: %s — retrying in 5s", exc)
            time.sleep(5)
        except KeyboardInterrupt:
            logger.info("Shutting down extraction worker")
            break


# ============================================================================
# CLI Entry Point
# ============================================================================


def main():
    parser = argparse.ArgumentParser(
        description="Pharos Local Extraction Worker — consumes diffs from Redis, "
        "extracts rules via a local LLM, posts them to the cloud backend.",
    )
    parser.add_argument(
        "--redis-url",
        default=os.getenv("PHAROS_REDIS_URL", "redis://localhost:6379/0"),
        help="Redis connection URL (default: redis://localhost:6379/0)",
    )
    parser.add_argument(
        "--queue",
        default=os.getenv("PHAROS_REDIS_QUEUE", "pharos_extraction_jobs"),
        help="Redis queue name (default: pharos_extraction_jobs)",
    )
    parser.add_argument(
        "--llm-url",
        default=os.getenv("PHAROS_LLM_URL", "http://localhost:11434"),
        help="Local LLM endpoint (default: http://localhost:11434)",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("PHAROS_LLM_MODEL", "codellama:13b"),
        help="LLM model name (default: codellama:13b)",
    )
    parser.add_argument(
        "--api-url",
        default=os.getenv("PHAROS_API_URL", "http://localhost:8000"),
        help="Cloud backend base URL",
    )
    parser.add_argument(
        "--api-token",
        default=os.getenv("PHAROS_API_TOKEN", ""),
        help="Bearer token for the cloud backend",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=2.0,
        help="Seconds between BRPOP timeouts (default: 2.0)",
    )

    args = parser.parse_args()

    if not args.api_token:
        logger.error("--api-token (or PHAROS_API_TOKEN env var) is required")
        sys.exit(1)

    run_worker(
        redis_url=args.redis_url,
        queue_name=args.queue,
        llm_url=args.llm_url,
        model=args.model,
        api_url=args.api_url,
        api_token=args.api_token,
        poll_interval=args.poll_interval,
    )


if __name__ == "__main__":
    main()
