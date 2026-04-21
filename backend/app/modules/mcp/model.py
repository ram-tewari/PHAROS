"""
MCP Module Database Models

SQLAlchemy models for MCP sessions.
"""

from datetime import datetime
from sqlalchemy import Column, DateTime, Index, Integer, JSON, String

from ...shared.base_model import Base


class MCPSession(Base):
    """MCP session for multi-turn interactions"""

    __tablename__ = "mcp_sessions"

    id = Column(String, primary_key=True)  # UUID
    user_id = Column(Integer, nullable=True)  # No FK constraint for flexibility
    context = Column(JSON, nullable=False, default=dict)
    tool_invocations = Column(JSON, nullable=False, default=list)
    status = Column(String, nullable=False, default="active")  # "active", "closed"
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_activity = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    # Note: User relationship is optional and may not exist in all environments
    # user = relationship("User", backref="mcp_sessions")

    # Indexes
    __table_args__ = (
        Index("idx_mcp_user", "user_id"),
        Index("idx_mcp_status", "status"),
        Index("idx_mcp_activity", "last_activity"),
    )

    def __repr__(self):
        return (
            f"<MCPSession(id={self.id}, user_id={self.user_id}, status={self.status})>"
        )
