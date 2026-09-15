from fastapi import FastAPI

from features.health.router import router as health_router
from features.measurements.router import router as measurements_router
from physiotrack.problem_details import register_problem_details_handlers


def create_app() -> FastAPI:
    app = FastAPI(title="PhysioTrack API")
    register_problem_details_handlers(app)
    app.include_router(health_router)
    app.include_router(measurements_router)

    return app

app = create_app()

if __name__ == "__main__":
    import os

    import uvicorn

    # Get the port to use from PORT environment variable
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
