"""
Robot Motion Router (리팩토링)
- MOTIONS 딕셔너리 → robot_motions 모듈
- _write_command → ros2_bridge 모듈
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.robot_motions import MOTIONS, execute_motion
from app.services.ros2_bridge import send_robot_motion, send_robot_command

router = APIRouter(prefix="/robot", tags=["Robot"])


class MotionRequest(BaseModel):
    motion: str


class CustomMotionRequest(BaseModel):
    joints: list
    velocity: float = 30.0
    acceleration: float = 25.0


@router.get("/motions")
def get_available_motions():
    return {
        "motions": [
            {"id": mid, "name": m["name"], "description": m["description"]}
            for mid, m in MOTIONS.items()
        ]
    }


@router.get("/motions/{motion_id}")
def get_motion_detail(motion_id: str):
    if motion_id not in MOTIONS:
        raise HTTPException(status_code=404, detail=f"Motion '{motion_id}' not found")
    return {"id": motion_id, **MOTIONS[motion_id]}


@router.post("/motion")
def execute_motion_endpoint(req: MotionRequest):
    if req.motion not in MOTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown motion '{req.motion}'. Available: {list(MOTIONS.keys())}",
        )
    execute_motion(req.motion)
    m = MOTIONS[req.motion]
    return {
        "success": True,
        "message": f"모션 '{m['name']}' 실행 중",
        "motion": req.motion,
        "joints": m["joints"],
    }


@router.post("/motion/custom")
def execute_custom_motion(req: CustomMotionRequest):
    if len(req.joints) != 6:
        raise HTTPException(status_code=400, detail="joints must have 6 values")
    send_robot_motion("custom", "Custom", req.joints, req.velocity, req.acceleration)
    return {"success": True, "message": "사용자 정의 모션 실행 중", "joints": req.joints}


@router.post("/stop")
def stop_robot():
    send_robot_command("stop")
    return {"success": True, "message": "로봇 정지 명령 전송"}
