${repr(message) | n}

revision = ${repr(up_revision) | n}
down_revision = ${repr(down_revision) | n}
branch_labels = ${repr(branch_labels) | n}
depends_on = ${repr(depends_on) | n}


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass