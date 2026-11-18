from fastapi import HTTPException, Request, status

from features.measurements.service import MeasurementService


def get_measurement_service(request: Request) -> MeasurementService:
    service = getattr(request.app.state, "measurement_service", None)
    if not isinstance(service, MeasurementService):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Measurement storage is not initialized.",
        )
    return service
