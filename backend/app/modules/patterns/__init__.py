"""
Pattern Learning Engine

Analyzes codebases via AST parsing and Git history to build
developer coding psychology profiles (architectural standards,
syntax habits, success/failure patterns).
"""

from .router import patterns_router

__all__ = ["patterns_router"]
