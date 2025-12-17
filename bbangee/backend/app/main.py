from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import engine, Base
from app.routers import people, access, voice, devices, ros2, scenario, robot, armband

app = FastAPI(title="Security System API")

# ✅ CORS를 가장 먼저
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://192.168.10.50:5173",
        
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# ✅ 1. CORS를 가장 먼저

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

@app.get("/")
def hello():
    return {"msg": "Backend running!"}
