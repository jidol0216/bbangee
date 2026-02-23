"""
ESP32 디바이스 제어 라우터 (리팩토링)
- ESP32 통신 로직 → device_control 서비스
- 파일 경로 → config 모듈
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Union, Optional
import json
import os

from app.services import device_control
from app.services.config import ROS2_AUTO_MODE_FILE, ROS2_STATE_FILE

router = APIRouter(prefix="/device", tags=["Device"])


# ==================== Models ====================

class ServoCommand(BaseModel):
    target: Union[bool, str]

class LaserCommand(BaseModel):
    target: Union[bool, str]

class AutoModeCommand(BaseModel):
    laser: Optional[bool] = None
    servo: Optional[bool] = None
    timeout: Optional[float] = None


# ==================== Servo / Laser ====================

@router.post("/servo")
def control_servo(cmd: ServoCommand):
    on = device_control.parse_target(cmd.target)
    return device_control.control_servo(on)


@router.post("/laser")
def control_laser(cmd: LaserCommand):
    on = device_control.parse_target(cmd.target)
    return device_control.control_laser(on)


# ==================== ESP32 Health ====================

@router.get("/esp32/status")
def get_esp32_status():
    result = device_control.ping()
    conn = device_control.get_connection_status()
    return {"status": "ok" if result["connected"] else "error", **result, "fail_count": conn["fail_count"]}


@router.post("/esp32/reset")
def reset_esp32():
    return device_control.reset_all()


# ==================== Auto Mode ====================

@router.get("/auto")
def get_auto_mode():
    auto_config = {"laser": False, "servo": False, "timeout": 1.0}
    if os.path.exists(ROS2_AUTO_MODE_FILE):
        try:
            with open(ROS2_AUTO_MODE_FILE, "r") as f:
                auto_config = json.load(f)
        except Exception:
            pass

    current_state = {"laser_state": False, "servo_state": False}
    if os.path.exists(ROS2_STATE_FILE):
        try:
            with open(ROS2_STATE_FILE, "r") as f:
                state = json.load(f)
                auto = state.get("auto_mode", {})
                current_state["laser_state"] = auto.get("laser_state", False)
                current_state["servo_state"] = auto.get("servo_state", False)
        except Exception:
            pass

    return {
        "status": "ok",
        "laser_auto": auto_config.get("laser", False),
        "servo_auto": auto_config.get("servo", False),
        "timeout": auto_config.get("timeout", 1.0),
        **current_state,
    }


@router.post("/auto")
def set_auto_mode(cmd: AutoModeCommand):
    current = {"laser": False, "servo": False, "timeout": 1.0}
    if os.path.exists(ROS2_AUTO_MODE_FILE):
        try:
            with open(ROS2_AUTO_MODE_FILE, "r") as f:
                current = json.load(f)
        except Exception:
            pass

    if cmd.laser is not None:
        current["laser"] = cmd.laser
    if cmd.servo is not None:
        current["servo"] = cmd.servo
    if cmd.timeout is not None:
        current["timeout"] = max(0.5, min(5.0, cmd.timeout))

    try:
        with open(ROS2_AUTO_MODE_FILE, "w") as f:
            json.dump(current, f)
        return {
            "status": "ok",
            "laser_auto": current["laser"],
            "servo_auto": current["servo"],
            "timeout": current["timeout"],
        }
    except Exception as e:
        return {"status": "error", "msg": str(e)}
