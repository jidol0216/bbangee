# app/routers/devices.py
from fastapi import APIRouter
from pydantic import BaseModel
import requests

router = APIRouter(prefix="/device", tags=["Device"])

# 🔵 ESP32 IP 주소 (시리얼에서 확인한 값)
ESP32_IP = "192.168.10.50"
ESP32_BASE = f"http://{ESP32_IP}"

# ======================
# 공통 요청 함수
# ======================
def call_esp32(path: str):
    try:
        r = requests.get(f"{ESP32_BASE}{path}", timeout=1)
        return r.text
    except Exception as e:
        raise RuntimeError(f"ESP32 connection failed: {e}")

# ======================
# Pydantic Models
# ======================
class ServoCommand(BaseModel):
    target: bool  # true = ON, false = OFF

class LaserCommand(BaseModel):
    target: bool  # true = ON, false = OFF

# ======================
# Servo API (함수명 유지)
# ======================
@router.post("/servo")
def control_servo(cmd: ServoCommand):
    try:
        if cmd.target:
            call_esp32("/servo/on")
        else:
            call_esp32("/servo/off")

        return {
            "status": "ok",
            "servo_state": cmd.target
        }
    except Exception as e:
        return {
            "status": "error",
            "msg": str(e)
        }

# ======================
# Laser API (함수명 유지)
# ======================
@router.post("/laser")
def control_laser(cmd: LaserCommand):
    try:
        if cmd.target:
            call_esp32("/laser/on")
        else:
            call_esp32("/laser/off")

        return {
            "status": "ok",
            "laser_state": cmd.target
        }
    except Exception as e:
        return {
            "status": "error",
            "msg": str(e)
        }
