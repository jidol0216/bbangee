# app/routers/devices.py
from fastapi import APIRouter
from pydantic import BaseModel
import requests

router = APIRouter(prefix="/device", tags=["Device"])

ESP32_BASE = "http://192.168.10.50"

class ServoCommand(BaseModel):
    target: bool

class LaserCommand(BaseModel):
    target: bool

def post_esp(path: str, on: bool):
    requests.post(
        f"{ESP32_BASE}{path}",
        data="on" if on else "off",
        headers={"Content-Type": "text/plain"},
        timeout=1,
    )

@router.post("/servo")
def control_servo(cmd: ServoCommand):
    post_esp("/device/servo", cmd.target)
    return {"status": "ok", "servo_state": cmd.target}

@router.post("/laser")
def control_laser(cmd: LaserCommand):
    post_esp("/device/laser", cmd.target)
    return {"status": "ok", "laser_state": cmd.target}
