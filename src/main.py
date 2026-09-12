from fastapi import FastAPI

from features.health.router import router as health_router

app = FastAPI(title="PhysioTrack API")

app.include_router(health_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0")
