"""Codex CLI as PHAROS's offline LLM, for jobs that run on the owner's Mac.

Port of the hardened ``codex exec`` provider in CognitiveOS's Valerie bridge:
one subprocess per request from an empty temporary directory, every tool-like
feature disabled, user config and rules ignored, read-only sandbox, ephemeral
session, prompt on stdin (never argv, which ``ps`` shows) and output held to a
strict JSON schema. It uses the CLI's ChatGPT login; ``OPENAI_*`` and
``CODEX_API*`` variables are removed so it can never bill an API key.

Production never imports this: the API serves results, the Mac computes them.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Features that give the model hands (shell, browser, apps, plugins, …). Only
# the ones this CLI version knows are passed to ``--disable``.
TOOL_FEATURES = (
    "shell_tool", "unified_exec", "apps", "plugins", "browser_use", "browser_use_external",
    "browser_use_full_cdp_access", "computer_use", "image_generation", "in_app_browser", "view_image",
    "skill_search", "tool_suggest", "sleep_tool", "code_mode", "code_mode_host", "shell_snapshot",
    "skill_mcp_dependency_install", "remote_plugin", "goals",
)


class LLMUnavailable(RuntimeError):
    """Codex is missing, signed out, timed out or returned nothing usable."""


def find_codex() -> str | None:
    """PHAROS_CODEX_PATH, then PATH, then the newest binary bundled with the ChatGPT VS Code extension."""
    explicit = os.getenv("PHAROS_CODEX_PATH")
    if explicit and Path(explicit).is_file():
        return explicit
    on_path = shutil.which("codex")
    if on_path:
        return on_path
    bundled = sorted(Path.home().glob(".vscode/extensions/openai.chatgpt-*/bin/macos-aarch64/codex"))
    return str(bundled[-1]) if bundled else None


def openai_strict(node):
    """A JSON Schema in the form OpenAI structured outputs require: every value has a type (a bare
    ``const`` becomes a one-value enum) and every property is required, optional ones as nullable."""
    if isinstance(node, list):
        return [openai_strict(item) for item in node]
    if not isinstance(node, dict):
        return node
    node = {key: openai_strict(value) for key, value in node.items()}
    if "const" in node:
        value = node.pop("const")
        node.setdefault("type", "string" if isinstance(value, str) else
                        "boolean" if isinstance(value, bool) else "integer")
        node["enum"] = [value]
    if node.get("type") == "object" and "properties" in node:
        required = set(node.get("required", []))
        for key, child in node["properties"].items():
            if key not in required:
                node["properties"][key] = _nullable(child)
        node["required"] = list(node["properties"])
        node["additionalProperties"] = False
    return node


def _nullable(node: dict) -> dict:
    if "anyOf" in node:
        return dict(node, anyOf=node["anyOf"] + [{"type": "null"}])
    kind = node.get("type")
    if isinstance(kind, str):
        node = dict(node, type=[kind, "null"])
        if "enum" in node:
            node["enum"] = node["enum"] + [None]
        return node
    return {"anyOf": [node, {"type": "null"}]}


def drop_nulls(value):
    """Undo ``openai_strict``'s nulls so callers see only the fields the model filled."""
    if isinstance(value, dict):
        return {key: drop_nulls(item) for key, item in value.items() if item is not None}
    if isinstance(value, list):
        return [drop_nulls(item) for item in value]
    return value


@dataclass
class Usage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    seconds: float = 0.0
    failures: int = 0
    per_call: list[dict] = field(default_factory=list)


class CodexCLI:
    """``complete(instructions, prompt, schema) -> dict`` through ``codex exec``.

    ``max_calls`` bounds one run (a job's budget); exceeding it raises
    ``LLMUnavailable`` instead of silently spending more of the subscription.
    """

    def __init__(self, path: str | None = None, model: str | None = None, effort: str = "low",
                 timeout: float = 180, max_calls: int | None = None):
        self.path = path or find_codex()
        self.model = model or os.getenv("PHAROS_CODEX_MODEL") or None
        self.effort = effort
        self.timeout = timeout
        self.max_calls = max_calls
        self.usage = Usage()
        self._disable: list[str] | None = None
        self._ready: tuple[float, bool] | None = None

    @staticmethod
    def env() -> dict[str, str]:
        return {k: v for k, v in os.environ.items() if not k.startswith(("OPENAI_", "CODEX_API"))}

    def _run_cli(self, *args: str, timeout: float = 15) -> subprocess.CompletedProcess:
        return subprocess.run([self.path, *args], capture_output=True, text=True, timeout=timeout,
                              env=self.env(), cwd=tempfile.gettempdir())

    def ready(self) -> bool:
        """Installed and signed in with ChatGPT (cached for a minute)."""
        if self._ready and time.monotonic() - self._ready[0] < 60:
            return self._ready[1]
        ok = False
        if self.path and Path(self.path).is_file():
            try:
                out = self._run_cli("login", "status")
                ok = out.returncode == 0 and "chatgpt" in (out.stdout + out.stderr).lower()
            except (OSError, subprocess.SubprocessError):
                ok = False
        self._ready = (time.monotonic(), ok)
        return ok

    def _features_to_disable(self) -> list[str]:
        if self._disable is None:
            known: set[str] = set()
            try:
                out = self._run_cli("features", "list")
                known = {line.split()[0] for line in out.stdout.splitlines() if line.strip()}
            except (OSError, subprocess.SubprocessError):
                pass
            # An unknown feature name could fail the command; without a list, disable nothing extra.
            self._disable = [f for f in TOOL_FEATURES if f in known]
        return self._disable

    def complete(self, instructions: str, prompt: str, schema: dict, *, effort: str | None = None,
                 timeout: float | None = None) -> dict:
        if self.max_calls is not None and self.usage.calls >= self.max_calls:
            raise LLMUnavailable(f"call budget of {self.max_calls} reached")
        if not self.ready():
            raise LLMUnavailable("codex is not installed or not signed in with ChatGPT")
        workdir = tempfile.mkdtemp(prefix="pharos-codex-")
        t0 = time.monotonic()
        self.usage.calls += 1
        try:
            schema_path, out_path = os.path.join(workdir, "schema.json"), os.path.join(workdir, "out.json")
            with open(schema_path, "w") as handle:
                json.dump(openai_strict(schema), handle)
            argv = [self.path, "exec", "-c", f'model_reasoning_effort="{effort or self.effort}"',
                    "-c", 'web_search="disabled"']
            if self.model:
                argv += ["-m", self.model]
            for feature in self._features_to_disable():
                argv += ["--disable", feature]
            argv += ["--ephemeral", "--skip-git-repo-check", "--ignore-user-config", "--ignore-rules",
                     "-s", "read-only", "--output-schema", schema_path, "--json", "-o", out_path, "-"]
            text = "# Instructions\n" + instructions + "\n\n# Request\n" + prompt
            process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, text=True, env=self.env(), cwd=workdir,
                                       start_new_session=True)
            try:
                stdout, stderr = process.communicate(text, timeout=timeout or self.timeout)
            except subprocess.TimeoutExpired as exc:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except OSError:
                    pass
                process.communicate()
                raise LLMUnavailable("codex timed out") from exc
            if process.returncode != 0 or not os.path.exists(out_path):
                logger.warning("codex exec failed (exit %s): %s", process.returncode, (stderr or "")[-300:])
                raise LLMUnavailable("codex exec failed")
            usage = {}
            for line in stdout.splitlines():
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if event.get("type") == "turn.completed":
                    usage = event.get("usage") or {}
            try:
                with open(out_path) as handle:
                    result = drop_nulls(json.load(handle))
            except ValueError as exc:
                raise LLMUnavailable("codex returned output that is not JSON") from exc
            seconds = time.monotonic() - t0
            self.usage.input_tokens += usage.get("input_tokens", 0)
            self.usage.output_tokens += usage.get("output_tokens", 0) + usage.get("reasoning_output_tokens", 0)
            self.usage.seconds += seconds
            self.usage.per_call.append({"seconds": round(seconds, 1), **usage})
            return result
        except LLMUnavailable:
            self.usage.failures += 1
            raise
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
