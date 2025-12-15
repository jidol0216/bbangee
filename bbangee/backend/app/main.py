from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import engine, Base
from app.routers import people, access, voice, devices

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

@app.get("/")
def hello():
    return {"msg": "Backend running!"}
