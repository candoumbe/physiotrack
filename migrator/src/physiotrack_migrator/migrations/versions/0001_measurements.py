"""Initial physiological measurement variants, with no business persistence code."""

import sqlalchemy as sa
from alembic import op

revision = "0001_measurements"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "measurements",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("subject_id", sa.Text(), nullable=True),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("date_of_measure", sa.Text(), nullable=False),
        sa.Column("bpm", sa.Numeric(), nullable=True),
        sa.Column("duration_minutes", sa.Numeric(), nullable=True),
        sa.Column("quality_score", sa.Double(), nullable=True),
        sa.Column("steps", sa.Numeric(), nullable=True),
        sa.Column("calories", sa.Double(), nullable=True),
        sa.Column("systolic", sa.Numeric(), nullable=True),
        sa.Column("diastolic", sa.Numeric(), nullable=True),
        sa.Column("unit", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_measurements"),
        sa.CheckConstraint(
            "subject_id IS NULL OR length(subject_id) > 0", name="ck_subject_nonempty"
        ),
        sa.CheckConstraint(
            "type IN ('heart_rate', 'sleep', 'activity', 'blood_pressure')",
            name="ck_measurement_type",
        ),
        *[
            sa.CheckConstraint(
                f"{column} IS NULL OR ({column} NOT IN ('NaN'::numeric, 'Infinity'::numeric, "
                f"'-Infinity'::numeric) AND {column} = trunc({column}))",
                name=f"ck_{column}_integer",
            )
            for column in ("bpm", "duration_minutes", "steps", "systolic", "diastolic")
        ],
        sa.CheckConstraint(
            "(type = 'heart_rate' AND bpm IS NOT NULL AND duration_minutes IS NULL "
            "AND quality_score IS NULL AND steps IS NULL AND calories IS NULL "
            "AND systolic IS NULL AND diastolic IS NULL AND unit IS NULL) OR "
            "(type = 'sleep' AND duration_minutes IS NOT NULL AND bpm IS NULL "
            "AND steps IS NULL AND calories IS NULL AND systolic IS NULL "
            "AND diastolic IS NULL AND unit IS NULL) OR "
            "(type = 'activity' AND steps IS NOT NULL AND bpm IS NULL "
            "AND duration_minutes IS NULL AND quality_score IS NULL "
            "AND systolic IS NULL AND diastolic IS NULL AND unit IS NULL) OR "
            "(type = 'blood_pressure' AND systolic IS NOT NULL AND diastolic IS NOT NULL "
            "AND unit IS NOT NULL AND unit = 'mmHg' AND bpm IS NULL "
            "AND duration_minutes IS NULL AND quality_score IS NULL "
            "AND steps IS NULL AND calories IS NULL)",
            name="ck_measurement_variant",
        ),
        schema="public",
        comment="physiotrack-migrator",
    )


def downgrade() -> None:
    op.drop_table("measurements", schema="public")
