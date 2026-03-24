"""Bridge a legacy missing Alembic revision.

Revision ID: 55d73e06ef07
Revises: 2eba58309625
Create Date: 2026-03-23 10:00:00.000000
"""

from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "55d73e06ef07"
down_revision: Union[str, None] = "2eba58309625"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Legacy deployments already stamped this revision, but the original file
    # is missing from the repository. Keeping it as a no-op preserves upgrade
    # continuity for existing volumes.
    pass


def downgrade() -> None:
    pass
