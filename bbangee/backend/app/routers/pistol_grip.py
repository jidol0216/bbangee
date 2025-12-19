# app/routers/pistol_grip.py
"""
권총 파지/거치 API
- 권총 파지: 위치로 이동 → 그리퍼 닫기
- 권총 거치: 위치로 이동 → 그리퍼 열기
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import json
import time
import os

router = APIRouter(prefix="/pistol", tags=["Pistol Grip"])

# ROS2 브릿지 명령 파일
COMMAND_FILE = '/tmp/ros2_bridge_command.json'

# ============================================
# 좌표 설정 (파지/거치 동일 위치)
# ============================================

# 권총 거치대 위치 (파지/거치 위치)
PISTOL_POSITION = {
    'x': 459.930,
    'y': 32.670,
    'z': 167.870,
    'rx': 91.47,
    'ry': -125.79,
    'rz': 80.9,
}

# 시작 위치 (웹 버튼과 동일) - 조인트 값
START_JOINTS = [3.0, -20.0, 92.0, 86.0, 0.0, 0.0]  # J1~J6

# 들어올리기 높이
Z_LIFT_OFFSET = 400  # mm (40cm)

# 그리퍼 설정
GRIP_SETTINGS = {
    'open_width': 110,      # 열림 폭 (mm)
    'close_width': 0,       # 닫힘 폭 (mm) - 최대한 좁게
    'force': 400,           # 그리퍼 힘 (N) - RG2 최대
}

# 이동 속도
MOTION_SETTINGS = {
    'velocity': 60,
    'acceleration': 60,
}


def _write_command(command: dict):
    """ROS2 브릿지에 명령 전달"""
    command['timestamp'] = time.time()
    with open(COMMAND_FILE, 'w') as f:
        json.dump(command, f)


class GripRequest(BaseModel):
    """파지/거치 요청"""
    force: Optional[int] = GRIP_SETTINGS['force']
    grip_width: Optional[int] = GRIP_SETTINGS['close_width']


# ============================================
# API Endpoints
# ============================================

@router.get("/settings")
def get_pistol_settings():
    """권총 파지/거치 설정 조회"""
    return {
        "position": PISTOL_POSITION,
        "grip_settings": GRIP_SETTINGS,
        "motion_settings": MOTION_SETTINGS,
    }


@router.post("/grip")
def pistol_grip(req: GripRequest = GripRequest()):
    """
    🔫 권총 파지 (Pick up)
    
    순서:
    1. 그리퍼 열기
    2. 위치로 이동
    3. 그리퍼 닫기 (잡기)
    """
    _write_command({
        'type': 'pistol_action',
        'data': {
            'action': 'grip',
            'position': PISTOL_POSITION,
            'z_lift': Z_LIFT_OFFSET,
            'grip_width': req.grip_width,
            'force': req.force,
            'velocity': MOTION_SETTINGS['velocity'],
            'acceleration': MOTION_SETTINGS['acceleration'],
        }
    })
    
    return {
        "success": True,
        "message": "🔫 권총 파지 명령 전송",
        "action": "grip",
        "description": "그리퍼 열기 → 위치 이동 → 그리퍼 닫기 → 들어올리기 → 홈 이동"
    }


@router.post("/holster")
def pistol_holster(req: GripRequest = GripRequest()):
    """
    🔫 권총 거치 (Put down)
    
    순서:
    1. 위치로 이동
    2. 그리퍼 열기 (놓기)
    """
    _write_command({
        'type': 'pistol_action',
        'data': {
            'action': 'holster',
            'position': PISTOL_POSITION,
            'force': req.force,
            'velocity': MOTION_SETTINGS['velocity'],
            'acceleration': MOTION_SETTINGS['acceleration'],
        }
    })
    
    return {
        "success": True,
        "message": "🔫 권총 거치 명령 전송",
        "action": "holster",
        "description": "위치 이동 → 그리퍼 열기"
    }


@router.post("/update_position")
def update_position(
    x: float, y: float, z: float,
    rx: float, ry: float, rz: float
):
    """권총 거치대 위치 업데이트"""
    global PISTOL_POSITION
    PISTOL_POSITION = {'x': x, 'y': y, 'z': z, 'rx': rx, 'ry': ry, 'rz': rz}
    return {"success": True, "position": PISTOL_POSITION}
