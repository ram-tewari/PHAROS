"""
Integration Tests — Master Programmer Personalities (Coding Profiles)

Tests the full vertical slice:
1. Database: CodingProfile + linked ProposedRule storage/retrieval
2. API: GET /api/patterns/profiles/coding returns correct JSON for Ronin
3. Context Assembly: profile_id swaps the rule set injected into context
"""

import time
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from app.database.models import (
    CodingProfile,
    ProposedRule,
    RuleStatus,
)


# ============================================================================
# Test 1: Database — Store and retrieve CodingProfile + linked rules
# ============================================================================


class TestCodingProfileDatabase:
    def test_create_and_retrieve_profile(self, db: Session):
        """Verify we can store a rich CodingProfile and link rules to it."""
        profile = CodingProfile(
            id="sys_hacker",
            name="The Systems Hacker",
            description="Low-level C mastery with explicit memory management.",
            best_suited_for={
                "languages": ["C", "Rust"],
                "tasks": ["systems programming", "kernel development"],
            },
        )
        db.add(profile)
        db.commit()

        rule1 = ProposedRule(
            repository="redis/redis",
            commit_sha="abc1234",
            file_path="src/server.c",
            diff_payload="- malloc\n+ zmalloc",
            rule_name="UseCustomAllocator",
            rule_description="Always use zmalloc instead of raw malloc.",
            rule_schema={
                "applies_to": "src/**/*.c",
                "pattern_type": "performance",
                "example_code": "ptr = zmalloc(sizeof(robj));",
                "rationale": "Tracks memory usage and enables jemalloc.",
            },
            confidence=0.95,
            status=RuleStatus.ACTIVE.value,
            profile_id="sys_hacker",
        )
        rule2 = ProposedRule(
            repository="redis/redis",
            commit_sha="def5678",
            file_path="src/networking.c",
            diff_payload="+ if (c->flags & CLIENT_CLOSE_ASAP)",
            rule_name="GuardClientFlags",
            rule_description="Check client flags before writing to socket.",
            rule_schema={
                "applies_to": "src/networking.c",
                "pattern_type": "error_handling",
                "example_code": "if (c->flags & CLIENT_CLOSE_ASAP) return;",
                "rationale": "Prevents writes to closing connections.",
            },
            confidence=0.88,
            status=RuleStatus.ACTIVE.value,
            profile_id="sys_hacker",
        )
        db.add_all([rule1, rule2])
        db.commit()

        # Retrieve and verify
        fetched = db.query(CodingProfile).filter_by(id="sys_hacker").first()
        assert fetched is not None
        assert fetched.name == "The Systems Hacker"
        assert "C" in fetched.best_suited_for["languages"]
        assert len(fetched.rules) == 2
        assert {r.rule_name for r in fetched.rules} == {
            "UseCustomAllocator",
            "GuardClientFlags",
        }

    def test_null_profile_id_is_personal_baseline(self, db: Session):
        """Rules with NULL profile_id belong to the personal baseline."""
        rule = ProposedRule(
            repository="my/repo",
            commit_sha="aaa1111",
            file_path="app.py",
            diff_payload="some diff",
            rule_name="PersonalRule",
            rule_description="A personal coding rule.",
            rule_schema={"pattern_type": "naming"},
            confidence=0.7,
            profile_id=None,
        )
        db.add(rule)
        db.commit()

        baseline = (
            db.query(ProposedRule)
            .filter(ProposedRule.profile_id.is_(None))
            .all()
        )
        assert len(baseline) == 1
        assert baseline[0].rule_name == "PersonalRule"


# ============================================================================
# Test 2: API — GET /api/patterns/profiles/coding
# ============================================================================


class TestCodingProfileAPI:
    def test_list_coding_profiles_returns_correct_structure(
        self, client: TestClient, db: Session
    ):
        """Verify GET /api/patterns/profiles/coding returns JSON for Ronin."""
        p1 = CodingProfile(
            id="sys_hacker",
            name="The Systems Hacker",
            description="Low-level C mastery.",
            best_suited_for={"languages": ["C"], "tasks": ["systems"]},
        )
        p2 = CodingProfile(
            id="pythonic_arch",
            name="The Pythonic Architect",
            description="Idiomatic Python with clean abstractions.",
            best_suited_for={"languages": ["Python"], "tasks": ["API design"]},
        )
        db.add_all([p1, p2])
        db.commit()

        resp = client.get("/api/patterns/profiles/coding")
        assert resp.status_code == 200

        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 2

        ids = {p["id"] for p in data}
        assert ids == {"sys_hacker", "pythonic_arch"}

        for profile in data:
            assert "id" in profile
            assert "name" in profile
            assert "description" in profile
            assert "best_suited_for" in profile
            assert isinstance(profile["best_suited_for"], dict)

    def test_create_coding_profile_via_api(
        self, client: TestClient, db: Session
    ):
        """Verify POST /api/patterns/profiles/coding creates a profile."""
        payload = {
            "id": "go_pragmatist",
            "name": "The Go Pragmatist",
            "description": "Simple, explicit, zero-magic Go code.",
            "best_suited_for": {
                "languages": ["Go"],
                "tasks": ["microservices", "CLI tools"],
            },
        }

        resp = client.post("/api/patterns/profiles/coding", json=payload)
        assert resp.status_code == 201

        data = resp.json()
        assert data["id"] == "go_pragmatist"
        assert data["name"] == "The Go Pragmatist"
        assert "Go" in data["best_suited_for"]["languages"]

        record = db.query(CodingProfile).filter_by(id="go_pragmatist").first()
        assert record is not None

    def test_empty_profiles_returns_empty_list(self, client: TestClient):
        """When no profiles exist, returns an empty list."""
        resp = client.get("/api/patterns/profiles/coding")
        assert resp.status_code == 200
        assert resp.json() == []


# ============================================================================
# Test 3: Context Assembly — profile_id swaps the rule set
# ============================================================================


class TestContextSwapping:
    def test_profile_id_returns_profile_rules(self, db: Session):
        """
        Passing profile_id='sys_hacker' should return rules from that
        profile, not the personal baseline.
        """
        from app.modules.mcp.context_service import ContextAssemblyService

        profile = CodingProfile(
            id="sys_hacker",
            name="The Systems Hacker",
            description="Low-level C mastery.",
            best_suited_for={"languages": ["C"], "tasks": ["systems"]},
        )
        db.add(profile)
        db.commit()

        rule = ProposedRule(
            repository="redis/redis",
            commit_sha="abc1234",
            file_path="src/server.c",
            diff_payload="zmalloc diff",
            rule_name="UseCustomAllocator",
            rule_description="Always use zmalloc.",
            rule_schema={
                "pattern_type": "performance",
                "example_code": "zmalloc(sz);",
            },
            confidence=0.95,
            status=RuleStatus.ACTIVE.value,
            profile_id="sys_hacker",
        )
        personal = ProposedRule(
            repository="my/repo",
            commit_sha="zzz9999",
            file_path="app.py",
            diff_payload="personal diff",
            rule_name="PersonalRule",
            rule_description="My personal style.",
            rule_schema={"pattern_type": "naming"},
            confidence=0.7,
            status=RuleStatus.ACTIVE.value,
            profile_id=None,
        )
        db.add_all([rule, personal])
        db.commit()

        mock_embedding = MagicMock()
        service = ContextAssemblyService(db, None, mock_embedding)

        patterns, elapsed = service._fetch_profile_rules("sys_hacker", time.time())

        assert len(patterns) == 1
        assert patterns[0].description == "Always use zmalloc."
        assert patterns[0].frequency == 0.95

    def test_nonexistent_profile_returns_empty(self, db: Session):
        """A nonexistent profile_id should return zero patterns."""
        from app.modules.mcp.context_service import ContextAssemblyService

        mock_embedding = MagicMock()
        service = ContextAssemblyService(db, None, mock_embedding)

        patterns, elapsed = service._fetch_profile_rules(
            "nonexistent_profile", time.time()
        )
        assert len(patterns) == 0

    def test_different_profiles_return_different_rules(self, db: Session):
        """
        Switching between profile_id='sys_hacker' and profile_id='pythonic_arch'
        should return completely different rule sets.
        """
        from app.modules.mcp.context_service import ContextAssemblyService

        for pid, name, rule_name, desc in [
            (
                "sys_hacker",
                "The Systems Hacker",
                "UseZmalloc",
                "Use zmalloc for allocation.",
            ),
            (
                "pythonic_arch",
                "The Pythonic Architect",
                "UseDataclasses",
                "Prefer dataclasses over dicts.",
            ),
        ]:
            profile = CodingProfile(
                id=pid,
                name=name,
                description=f"{name} desc.",
                best_suited_for={"languages": [], "tasks": []},
            )
            db.add(profile)
            db.commit()

            rule = ProposedRule(
                repository="test/repo",
                commit_sha="abc1234",
                file_path="test.py",
                diff_payload="diff",
                rule_name=rule_name,
                rule_description=desc,
                rule_schema={"pattern_type": "architecture"},
                confidence=0.9,
                status=RuleStatus.ACTIVE.value,
                profile_id=pid,
            )
            db.add(rule)
            db.commit()

        mock_embedding = MagicMock()
        service = ContextAssemblyService(db, None, mock_embedding)

        sys_patterns, _ = service._fetch_profile_rules(
            "sys_hacker", time.time()
        )
        py_patterns, _ = service._fetch_profile_rules(
            "pythonic_arch", time.time()
        )

        assert len(sys_patterns) == 1
        assert len(py_patterns) == 1
        assert sys_patterns[0].description == "Use zmalloc for allocation."
        assert py_patterns[0].description == "Prefer dataclasses over dicts."
