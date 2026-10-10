"""Add working_paths to domains

Revision ID: add_working_paths
Revises: f7e99962b145
Create Date: 2026-02-05 22:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'add_working_paths'
down_revision: Union[str, None] = 'f7e99962b145'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add working_paths column to domains table
    op.add_column('domains', sa.Column('working_paths', postgresql.JSON(astext_type=sa.Text()), nullable=True, comment='List of URLs that have successfully returned relevant content (for optimization)'))


def downgrade() -> None:
    # Remove working_paths column
    op.drop_column('domains', 'working_paths')
