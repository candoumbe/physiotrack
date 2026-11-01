from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.types import TypeDecorator


class MeasurementDateTime(TypeDecorator[datetime]):
    impl = sa.Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return None if value is None else value.isoformat()

    def process_result_value(self, value, dialect):
        return None if value is None else datetime.fromisoformat(value)
