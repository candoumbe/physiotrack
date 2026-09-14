from fastapi import FastAPI

from features.health.router import router as health_router
from features.measurements.router import router as measurements_router

app = FastAPI(title="PhysioTrack API")

app.include_router(health_router)
app.include_router(measurements_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0")
