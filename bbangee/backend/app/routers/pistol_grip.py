"""
권총 파지/거치 API (리팩토링)
- _write_command → ros2_bridge 모듈
- 하드코딩 상수 → config 모듈
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from app.services.ros2_bridge import write_command
from app.services.config import (
    PISTOL_POSITION,
    PISTOL_Z_LIFT_OFFSET,
    PISTOL_GRIP_SETTINGS,
    PISTOL_MOTION_SETTINGS,
)

router = APIRouter(prefix="/pistol", tags=["Pistol Grip"])

# 런타임에 업데이트 가능한 위치 (config 기본값으로 초기화)
_current_position = dict(PISTOL_POSITION)


class GripRequest(BaseModel):
    force: Optional[int] = PISTOL_GRIP_SETTINGS["force"]
    grip_width: Optional[int] = PISTOL_GRIP_SETTINGS["close_width"]


@router.get("/settings")
def get_pistol_settings():
    return {
        "position": _current_position,
        "grip_settings": PISTOL_GRIP_SETTINGS,
        "motion_settings": PISTOL_MOTION_SETTINGS,
    }


@router.post("/grip")
def pistol_grip(req: GripRequest = GripRequest()):
    write_command({
        "type": "pistol_action",
        "data": {
            "action": "grip",
            "position": _current_position,
            "z_lift": PISTOL_Z_LIFT_OFFSET,
            "grip_width": req.grip_width,
            "force": req.force,
            "velocity": PISTOL_MOTION_SETTINGS["velocity"],
            "acceleration": PISTOL_MOTION_SETTINGS["acceleration"],
        },
    })
    return {
        "success": True,
        "message": "🔫 권총 파지 명령 전송",
        "action": "grip",
    }


@router.post("/holster")
def pistol_holster(req: GripRequest = GripRequest()):
    write_command({
        "type": "pistol_action",
        "data": {
            "action": "holster",
            "position": _current_position,
            "force": req.force,
            "velocity": PISTOL_MOTION_SETTINGS["velocity"],
            "acceleration": PISTOL_MOTION_SETTINGS["acceleration"],
        },
    })
    return {
        "success": True,
        "message": "🔫 권총 거치 명령 전송",
        "action": "holster",
    }


@router.post("/update_position")
def update_position(x: float, y: float, z: float, rx: float, ry: float, rz: float):
    _current_position.update(x=x, y=y, z=z, rx=rx, ry=ry, rz=rz)
    return {"success": True, "position": _current_position}
