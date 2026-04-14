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

MASTER_REPO_SYSTEM_PROMPT = """\
You are a senior software architect analyzing a legendary open-source repository.
Given a batch of representative source files from the repository, produce a
**Profile Blueprint** — a complete JSON description of the coding personality
embodied by this codebase.

You must intelligently infer the profile metadata from the code you read.

Return ONLY a JSON object with these keys (no markdown fences):
{
  "profile_id": "<snake_case identifier, e.g. sys_hacker, pythonic_architect>",
  "name": "<human-readable name, e.g. The Systems Hacker>",
  "description": "<2-4 sentence description of the coding philosophy>",
  "best_suited_for": {
    "languages": ["<list of programming languages this style excels in>"],
    "tasks": ["<list of task types: systems programming, API design, data pipelines, etc.>"]
  },
  "core_directives": [
    {
      "rule_name": "<PascalCase, e.g. PreferExplicitMemoryManagement>",
      "rule_description": "<1-3 sentence description>",
      "rule_schema": {
        "applies_to": "<file glob or module path>",
        "pattern_type": "<error_handling | naming | architecture | async | testing | performance | other>",
        "example_code": "<short representative code snippet>",
        "rationale": "<why this pattern is preferred in this codebase>"
      },
      "confidence": <float 0.0-1.0>
    }
  ]
}

Extract 5-15 core directives that capture the most distinctive architectural
decisions, naming conventions, error-handling strategies, and performance
patterns in the codebase.  Focus on what makes this codebase *unique*, not
generic best practices.
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


def extract_profile_blueprint(
    file_contents: Dict[str, str],
    repo_name: str,
    llm_url: str,
    model: str,
) -> Optional[Dict[str, Any]]:
    """
    Analyze a batch of representative source files from a master repository
    and extract a full Profile Blueprint via the local LLM.

    Args:
        file_contents: Mapping of file_path -> file content (top files from repo).
        repo_name: Human-readable repository name for context.
        llm_url: OpenAI-compatible LLM endpoint.
        model: Model name to use.

    Returns:
        Parsed Profile Blueprint dict, or None on failure.
    """
    # Build a concatenated view of the codebase for the LLM
    file_sections = []
    for path, content in file_contents.items():
        # Truncate individual files to keep prompt within limits
        truncated = content[:4000] if len(content) > 4000 else content
        file_sections.append(f"=== {path} ===\n{truncated}")

    combined = "\n\n".join(file_sections)

    user_prompt = (
        f"Repository: {repo_name}\n\n"
        f"Below are representative source files from this repository:\n\n"
        f"{combined}\n\n"
        "Analyze this codebase and produce the Profile Blueprint JSON."
    )

    endpoint = f"{llm_url.rstrip('/')}/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": MASTER_REPO_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 4096,
    }

    try:
        with httpx.Client(timeout=300) as client:
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

        blueprint = json.loads(content)

        # Validate required keys
        required = {"profile_id", "name", "description", "best_suited_for", "core_directives"}
        if not required.issubset(blueprint.keys()):
            missing = required - set(blueprint.keys())
            logger.error("Blueprint missing required keys: %s", missing)
            return None

        return blueprint

    except (httpx.HTTPError, json.JSONDecodeError, KeyError, IndexError) as exc:
        logger.error("Master repo extraction failed: %s", exc)
        return None


def ingest_master_repo(
    repo_path: str,
    llm_url: str,
    model: str,
    api_url: str,
    api_token: str,
    max_files: int = 30,
) -> bool:
    """
    Ingest a legendary repository and create a CodingProfile with linked rules.

    1. Scan the repo for representative source files.
    2. Send them to the local LLM for Profile Blueprint extraction.
    3. POST the CodingProfile to the backend.
    4. POST each core_directive as a ProposedRule linked to the profile.

    Args:
        repo_path: Local path to the cloned master repository.
        llm_url: OpenAI-compatible LLM endpoint.
        model: Model name.
        api_url: Pharos cloud backend base URL.
        api_token: Bearer token for API auth.
        max_files: Max source files to send to the LLM.

    Returns:
        True on success.
    """
    from pathlib import Path

    repo = Path(repo_path)
    if not repo.exists():
        logger.error("Repository path does not exist: %s", repo_path)
        return False

    repo_name = repo.name

    # Collect representative source files (largest Python/C/Go/Rust files first)
    code_extensions = {".py", ".c", ".h", ".go", ".rs", ".js", ".ts", ".java", ".rb", ".cpp"}
    excludes = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", "test", "tests"}

    candidates = []
    for filepath in repo.rglob("*"):
        if not filepath.is_file():
            continue
        parts = set(filepath.relative_to(repo).parts)
        if parts.intersection(excludes):
            continue
        if filepath.suffix.lower() in code_extensions:
            try:
                size = filepath.stat().st_size
                if 500 < size < 100_000:  # Skip tiny and huge files
                    candidates.append((filepath, size))
            except OSError:
                continue

    # Sort by size descending to get the meatiest files
    candidates.sort(key=lambda x: x[1], reverse=True)
    selected = candidates[:max_files]

    if not selected:
        logger.error("No suitable source files found in %s", repo_path)
        return False

    # Read file contents
    file_contents: Dict[str, str] = {}
    for filepath, _ in selected:
        try:
            rel_path = str(filepath.relative_to(repo))
            file_contents[rel_path] = filepath.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            logger.warning("Failed to read %s: %s", filepath, exc)

    logger.info("Extracting profile blueprint from %d files in %s", len(file_contents), repo_name)

    # Extract blueprint via LLM
    blueprint = extract_profile_blueprint(file_contents, repo_name, llm_url, model)
    if blueprint is None:
        logger.error("Failed to extract profile blueprint for %s", repo_name)
        return False

    profile_id = blueprint["profile_id"]
    logger.info("Blueprint extracted: %s (%s)", blueprint["name"], profile_id)

    # POST the CodingProfile to the backend
    profile_url = f"{api_url.rstrip('/')}/api/patterns/profiles/coding"
    profile_payload = {
        "id": profile_id,
        "name": blueprint["name"],
        "description": blueprint["description"],
        "best_suited_for": blueprint["best_suited_for"],
    }

    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                profile_url,
                json=profile_payload,
                headers={"Authorization": f"Bearer {api_token}"},
            )
            resp.raise_for_status()
        logger.info("CodingProfile created: %s", profile_id)
    except httpx.HTTPError as exc:
        logger.error("Failed to POST CodingProfile: %s", exc)
        return False

    # POST each core directive as a ProposedRule linked to the profile
    propose_url = f"{api_url.rstrip('/')}/api/patterns/propose"
    directives = blueprint.get("core_directives", [])
    success_count = 0

    for directive in directives:
        rule_payload = {
            "repository": repo_name,
            "commit_sha": "master-analysis",
            "file_path": directive.get("rule_schema", {}).get("applies_to", "*"),
            "diff_payload": directive.get("rule_schema", {}).get("example_code", ""),
            "rule_name": directive.get("rule_name", "UnnamedRule"),
            "rule_description": directive.get("rule_description", ""),
            "rule_schema": directive.get("rule_schema", {}),
            "confidence": float(directive.get("confidence", 0.0)),
            "profile_id": profile_id,
        }

        try:
            with httpx.Client(timeout=30) as client:
                resp = client.post(
                    propose_url,
                    json=rule_payload,
                    headers={"Authorization": f"Bearer {api_token}"},
                )
                resp.raise_for_status()
            success_count += 1
        except httpx.HTTPError as exc:
            logger.warning("Failed to POST directive %s: %s", directive.get("rule_name"), exc)

    logger.info(
        "Master repo ingestion complete: %s — %d/%d directives posted",
        repo_name, success_count, len(directives),
    )
    return success_count > 0


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
    subparsers = parser.add_subparsers(dest="command")

    # Default: run the Redis queue worker
    worker_parser = subparsers.add_parser("worker", help="Run the Redis queue extraction worker")
    worker_parser.add_argument(
        "--redis-url",
        default=os.getenv("PHAROS_REDIS_URL", "redis://localhost:6379/0"),
        help="Redis connection URL (default: redis://localhost:6379/0)",
    )
    worker_parser.add_argument(
        "--queue",
        default=os.getenv("PHAROS_REDIS_QUEUE", "pharos_extraction_jobs"),
        help="Redis queue name (default: pharos_extraction_jobs)",
    )
    worker_parser.add_argument(
        "--poll-interval",
        type=float,
        default=2.0,
        help="Seconds between BRPOP timeouts (default: 2.0)",
    )

    # New: ingest a master repository to create a CodingProfile
    master_parser = subparsers.add_parser(
        "ingest-master",
        help="Analyze a legendary repo and create a CodingProfile with linked rules",
    )
    master_parser.add_argument(
        "repo_path",
        help="Local path to the cloned master repository",
    )
    master_parser.add_argument(
        "--max-files",
        type=int,
        default=30,
        help="Max source files to analyze (default: 30)",
    )

    # Shared arguments for both subcommands
    for sub in (worker_parser, master_parser):
        sub.add_argument(
            "--llm-url",
            default=os.getenv("PHAROS_LLM_URL", "http://localhost:11434"),
            help="Local LLM endpoint (default: http://localhost:11434)",
        )
        sub.add_argument(
            "--model",
            default=os.getenv("PHAROS_LLM_MODEL", "codellama:13b"),
            help="LLM model name (default: codellama:13b)",
        )
        sub.add_argument(
            "--api-url",
            default=os.getenv("PHAROS_API_URL", "http://localhost:8000"),
            help="Cloud backend base URL",
        )
        sub.add_argument(
            "--api-token",
            default=os.getenv("PHAROS_API_TOKEN", ""),
            help="Bearer token for the cloud backend",
        )

    args = parser.parse_args()

    # Default to 'worker' if no subcommand given
    if args.command is None:
        args.command = "worker"
        # Re-parse with worker defaults for backward compat
        args = worker_parser.parse_args(sys.argv[1:])
        # Apply shared defaults
        if not hasattr(args, "llm_url"):
            args.llm_url = os.getenv("PHAROS_LLM_URL", "http://localhost:11434")
        if not hasattr(args, "model"):
            args.model = os.getenv("PHAROS_LLM_MODEL", "codellama:13b")
        if not hasattr(args, "api_url"):
            args.api_url = os.getenv("PHAROS_API_URL", "http://localhost:8000")
        if not hasattr(args, "api_token"):
            args.api_token = os.getenv("PHAROS_API_TOKEN", "")
        args.command = "worker"

    if not args.api_token:
        logger.error("--api-token (or PHAROS_API_TOKEN env var) is required")
        sys.exit(1)

    if args.command == "worker":
        run_worker(
            redis_url=args.redis_url,
            queue_name=args.queue,
            llm_url=args.llm_url,
            model=args.model,
            api_url=args.api_url,
            api_token=args.api_token,
            poll_interval=args.poll_interval,
        )
    elif args.command == "ingest-master":
        success = ingest_master_repo(
            repo_path=args.repo_path,
            llm_url=args.llm_url,
            model=args.model,
            api_url=args.api_url,
            api_token=args.api_token,
            max_files=args.max_files,
        )
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
