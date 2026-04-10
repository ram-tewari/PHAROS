#!/usr/bin/env python
"""Test all CLI subcommands to identify which work and which are broken."""

import subprocess
import sys
from typing import Dict, List, Tuple
from dataclasses import dataclass
from enum import Enum


class TestStatus(Enum):
    PASS = "✅ PASS"
    FAIL = "❌ FAIL"
    SKIP = "⏭️  SKIP"


@dataclass
class CommandTest:
    group: str
    command: str
    args: List[str]
    description: str
    status: TestStatus = TestStatus.SKIP
    error: str = ""
    requires_backend: bool = False


def run_command(cmd: List[str], timeout: int = 5) -> Tuple[int, str, str]:
    """Run a command and return exit code, stdout, stderr."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd="."
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "