"""API client for proposed-rules endpoints (Phase 6 Feedback Loop)."""

from typing import Any, Dict, List, Optional

from pharos_cli.client.api_client import SyncAPIClient


class RulesClient:
    """Client for /api/patterns/rules endpoints."""

    def __init__(self, api_client: SyncAPIClient):
        self.api = api_client

    def list_rules(
        self,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Fetch proposed rules, optionally filtered by status."""
        params: Dict[str, Any] = {"limit": limit}
        if status:
            params["status"] = status
        return self.api.get("/api/patterns/rules", params=params)

    def accept_rule(self, rule_id: str) -> Dict[str, Any]:
        """Accept a proposed rule (set status → ACTIVE)."""
        return self.api.patch(f"/api/patterns/rules/{rule_id}?action=accept")

    def reject_rule(self, rule_id: str) -> Dict[str, Any]:
        """Reject a proposed rule."""
        return self.api.patch(f"/api/patterns/rules/{rule_id}?action=reject")
