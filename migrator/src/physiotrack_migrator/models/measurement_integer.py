import sqlalchemy as sa
from sqlalchemy.types import TypeDecorator


class MeasurementInteger(TypeDecorator[int]):
    impl = sa.Numeric
    cache_ok = True

    def process_result_value(self, value, dialect):
        return None if value is None else int(value)
