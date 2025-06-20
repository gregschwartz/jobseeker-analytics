"""add_interview_briefing_to_user_emails

Revision ID: 187df55577a9
Revises: c256d0279ea6
Create Date: 2025-06-19 23:38:07.476171

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '187df55577a9'
down_revision: Union[str, None] = 'c256d0279ea6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('user_emails', sa.Column('interview_briefing', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('user_emails', 'interview_briefing')
