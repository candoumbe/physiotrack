"""Store measurement subject identifiers as UUIDs."""

import sqlalchemy as sa
from alembic import op

from physiotrack_migrator.migration_safety_error import MigrationSafetyError

revision = "0004_subject_id_uuid"
down_revision = "0003_measurement_creation_order"
branch_labels = None
depends_on = None

TABLES = (
    "heart_rate_measurements",
    "sleep_measurements",
    "activity_measurements",
    "blood_pressure_measurements",
)
UUID_PATTERN = (
    "^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def upgrade() -> None:
    bind = op.get_bind()
    for table in TABLES:
        invalid = bind.scalar(
            sa.text(
                f"SELECT EXISTS (SELECT 1 FROM public.{table} "
                "WHERE subject_id IS NOT NULL AND subject_id !~ :pattern)"
            ),
            {"pattern": UUID_PATTERN},
        )
        if invalid:
            raise MigrationSafetyError(
                f"Upgrade stopped: {table}.subject_id contains values that are not "
                "UUIDs. Replace or clear them before retrying the upgrade to "
                "0004_subject_id_uuid."
            )

    for table in TABLES:
        op.drop_constraint("ck_subject_nonempty", table, schema="public", type_="check")
        op.alter_column(
            table,
            "subject_id",
            existing_type=sa.Text(),
            type_=sa.UUID(),
            existing_nullable=True,
            postgresql_using="subject_id::uuid",
            schema="public",
        )


def downgrade() -> None:
    for table in reversed(TABLES):
        op.alter_column(
            table,
            "subject_id",
            existing_type=sa.UUID(),
            type_=sa.Text(),
            existing_nullable=True,
            postgresql_using="subject_id::text",
            schema="public",
        )
        op.create_check_constraint(
            "ck_subject_nonempty",
            table,
            "subject_id IS NULL OR length(subject_id) > 0",
            schema="public",
        )
