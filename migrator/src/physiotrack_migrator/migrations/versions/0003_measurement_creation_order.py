"""Persist creation order for stable cross-type collection ordering."""

import sqlalchemy as sa
from alembic import op

revision = "0003_measurement_creation_order"
down_revision = "0002_dedicated_measurements"
branch_labels = None
depends_on = None

TABLES = (
    "heart_rate_measurements",
    "sleep_measurements",
    "activity_measurements",
    "blood_pressure_measurements",
)


def upgrade() -> None:
    for table in TABLES:
        op.add_column(
            table,
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("clock_timestamp()"),
            ),
            schema="public",
        )


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_column(table, "created_at", schema="public")
