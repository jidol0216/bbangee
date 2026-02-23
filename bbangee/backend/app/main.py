from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import engine, Base
from app.services.config import CORS_ORIGINS
from app.routers import people, access, voice, devices, ros2, scenario, robot, armband, gripper, pistol_grip

app = FastAPI(title="Security System API")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# DB 생성
Base.metadata.create_all(bind=engine)

# 라우터 등록
app.include_router(people.router)
app.include_router(access.router)
app.include_router(voice.router)
app.include_router(devices.router)
app.include_router(ros2.router)
app.include_router(scenario.router)
app.include_router(robot.router)
app.include_router(armband.router)
app.include_router(gripper.router)
app.include_router(pistol_grip.router)


@app.get("/")
def hello():
    return {"msg": "Backend running!"}
