"""Split measurement variants without changing their stored representation."""

from importlib import import_module

import sqlalchemy as sa
from alembic import op

from physiotrack_migrator.migration_safety_error import MigrationSafetyError

revision = "0002_dedicated_measurements"
down_revision = "0001_measurements"
branch_labels = None
depends_on = None

VARIANTS = {
    "heart_rate": ("bpm",),
    "sleep": ("duration_minutes", "quality_score"),
    "activity": ("steps", "calories"),
    "blood_pressure": ("systolic", "diastolic", "unit"),
}
COMMON = ("id", "subject_id", "date_of_measure")
INTEGERS = {"bpm", "duration_minutes", "steps", "systolic", "diastolic"}
OPTIONAL = {"quality_score", "calories"}


def _reflect(name, expected):
    connection = op.get_bind()
    table = sa.Table(name, sa.MetaData(), schema="public", autoload_with=connection)
    if set(table.c.keys()) != set(expected):
        raise MigrationSafetyError(
            "Migration stopped: unexpected measurement columns. "
            "Restore the expected revision schema before retrying."
        )
    op.execute(sa.text(f'LOCK TABLE public."{name}" IN ACCESS EXCLUSIVE MODE'))
    return table


def _combined(legacy, tables):
    return sa.union_all(
        *[
            sa.select(
                *[
                    (
                        table.c[column.name]
                        if column.name in table.c
                        else sa.literal(variant)
                        if column.name == "type"
                        else sa.cast(sa.null(), column.type)
                    ).label(column.name)
                    for column in legacy.c
                ]
            )
            for variant, table in tables.items()
        ]
    )


def _verify(legacy, tables):
    connection = op.get_bind()
    combined = _combined(legacy, tables).subquery()
    original = sa.select(legacy)
    restored = sa.select(combined)
    for difference in (
        original.except_all(restored),
        restored.except_all(original),
    ):
        if connection.scalar(sa.select(sa.exists(difference))):
            raise MigrationSafetyError(
                "Migration stopped: measurement copy differs from its source. "
                "No tables were removed; inspect the source schema before retrying."
            )


def upgrade() -> None:
    legacy = _reflect("measurements", (*COMMON, "type", *sum(VARIANTS.values(), ())))
    tables = {}
    for variant, fields in VARIANTS.items():
        name = f"{variant}_measurements"
        tables[variant] = op.create_table(
            name,
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("subject_id", sa.Text(), nullable=True),
            sa.Column("date_of_measure", sa.Text(), nullable=False),
            *[
                sa.Column(
                    field,
                    sa.Numeric()
                    if field in INTEGERS
                    else sa.Text()
                    if field == "unit"
                    else sa.Double(),
                    nullable=field in OPTIONAL,
                )
                for field in fields
            ],
            sa.PrimaryKeyConstraint("id", name=f"pk_{name}"),
            sa.CheckConstraint(
                "subject_id IS NULL OR length(subject_id) > 0",
                name="ck_subject_nonempty",
            ),
            *[
                sa.CheckConstraint(
                    f"{field} NOT IN ('NaN'::numeric, 'Infinity'::numeric, "
                    f"'-Infinity'::numeric) AND {field} = trunc({field})",
                    name=f"ck_{field}_integer",
                )
                for field in fields
                if field in INTEGERS
            ],
            *(
                [sa.CheckConstraint("unit = 'mmHg'", name="ck_unit_mmhg")]
                if variant == "blood_pressure"
                else []
            ),
            schema="public",
            comment="physiotrack-migrator",
        )
        columns = (*COMMON, *fields)
        op.get_bind().execute(
            tables[variant]
            .insert()
            .from_select(
                columns,
                sa.select(*(legacy.c[field] for field in columns)).where(
                    legacy.c.type == variant
                ),
            )
        )
    _verify(legacy, tables)
    op.drop_table("measurements", schema="public")


def downgrade() -> None:
    tables = {
        variant: _reflect(f"{variant}_measurements", (*COMMON, *fields))
        for variant, fields in VARIANTS.items()
    }
    identifiers = sa.union_all(
        *(sa.select(table.c.id) for table in tables.values())
    ).subquery()
    if op.get_bind().scalar(
        sa.select(
            sa.exists(
                sa.select(identifiers.c.id)
                .group_by(identifiers.c.id)
                .having(sa.func.count() > 1)
            )
        )
    ):
        raise MigrationSafetyError(
            "Downgrade stopped: UUIDs overlap across measurement tables. "
            "Assign globally unique IDs before retrying the downgrade to 0001_measurements."
        )
    initial = import_module(
        "physiotrack_migrator.migrations.versions.0001_measurements"
    )
    initial.upgrade()
    legacy = _reflect("measurements", (*COMMON, "type", *sum(VARIANTS.values(), ())))
    op.get_bind().execute(
        legacy.insert().from_select(legacy.c.keys(), _combined(legacy, tables))
    )
    _verify(legacy, tables)
    for table in tables.values():
        op.drop_table(table.name, schema="public")
