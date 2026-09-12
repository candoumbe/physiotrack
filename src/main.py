from fastapi import FastAPI

from features.health.router import router as health_router
from telemetry import setup_telemetry

app = FastAPI(title="PhysioTrack API")

setup_telemetry(app)

app.include_router(health_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0")
