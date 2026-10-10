"""Add importance to signals and opportunities

Revision ID: add_signal_importance
Revises: a1b2c3d4e5f6
Create Date: 2026-05-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "add_signal_importance"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "signals",
        sa.Column(
            "importance",
            sa.String(length=10),
            nullable=False,
            server_default="strong",
            comment="weak, medium, strong",
        ),
    )
    op.add_column(
        "opportunities",
        sa.Column(
            "importance",
            sa.String(length=10),
            nullable=False,
            server_default="strong",
            comment="weak, medium, strong",
        ),
    )

    op.execute(
        "UPDATE signals SET importance = CASE type "
        "WHEN 'minor_activity' THEN 'weak' "
        "WHEN 'page_redesign' THEN 'medium' "
        "WHEN 'recent_activity' THEN 'medium' "
        "WHEN 'tool_added' THEN 'medium' "
        "WHEN 'new_site' THEN 'medium' "
        "ELSE 'strong' END"
    )
    op.execute(
        "UPDATE opportunities SET importance = CASE signal_type "
        "WHEN 'minor_activity' THEN 'weak' "
        "WHEN 'page_redesign' THEN 'medium' "
        "WHEN 'recent_activity' THEN 'medium' "
        "WHEN 'tool_added' THEN 'medium' "
        "WHEN 'new_site' THEN 'medium' "
        "ELSE 'strong' END"
    )
    op.execute(
        "UPDATE signals SET importance = payload_json->>'importance' "
        "WHERE payload_json->>'importance' IN ('weak', 'medium', 'strong')"
    )

    op.create_index(
        "ix_opportunities_importance",
        "opportunities",
        ["importance"],
        unique=False,
    )
    op.create_index(
        "ix_signals_importance",
        "signals",
        ["importance"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_signals_importance", table_name="signals")
    op.drop_index("ix_opportunities_importance", table_name="opportunities")
    op.drop_column("opportunities", "importance")
    op.drop_column("signals", "importance")
