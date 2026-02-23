"""
Robot Motion Router - 로봇 모션 제어 API

경례, Low Ready 등 미리 정의된 모션 실행
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import json
import time
import os

router = APIRouter(prefix="/robot", tags=["Robot"])

# ROS2 브릿지와 통신하는 명령 파일
COMMAND_FILE = '/tmp/ros2_bridge_command.json'

# ============================================
# 미리 정의된 조인트 포지션 (deg)
# 현재 시작 위치 기준: [3.1, 2.8, 92.1, 86.1, -1.4, 8.3]
# ============================================

MOTIONS = {
    # 경례 모션 - 로봇이 거수경례하는 자세
    "salute": {
        "name": "경례",
        "description": "거수경례 자세 - 팔을 들어 경례",
        "joints": [3.0, 0.0, 60.0, 120.0, 45.0, 0.0],  # J5: 45도
        "velocity": 25.0,
        "acceleration": 20.0,
    },
    
    # High Ready - 위를 향한 경계 자세 (아군 식별 시 사용)
    "high_ready": {
        "name": "High Ready",
        "description": "경계 자세 (위를 향함)",
        "joints": [3.0, -20.0, 92.0, 86.0, 0.0, 0.0],  # 위를 바라봄
        "velocity": 30.0,
        "acceleration": 25.0,
    },
    
    # 홈 위치 - 완전 접힌 상태
    "home": {
        "name": "홈",
        "description": "홈 위치 - 안전 자세",
        "joints": [0.0, 0.0, 90.0, 0.0, 90.0, 0.0],  # HOME_JOINTS
        "velocity": 30.0,
        "acceleration": 25.0,
    },
    
    # 차단봉 열기 동작 (시뮬레이션)
    "barrier_open": {
        "name": "차단봉 열기",
        "description": "차단봉 개방 동작",
        "joints": [3.0, -15.0, 80.0, 100.0, -20.0, 0.0],
        "velocity": 20.0,
        "acceleration": 15.0,
    },
    
    # 위협 자세 - 적 대응용
    "threat": {
        "name": "위협",
        "description": "위협 자세 - 적 대응",
        "joints": [35.0, -20.0, 110.0, 50.0, 10.0, 0.0],
        "velocity": 40.0,
        "acceleration": 35.0,
    },
}


class MotionRequest(BaseModel):
    motion: str


class CustomMotionRequest(BaseModel):
    joints: list  # 6개 조인트 각도 (deg)
    velocity: float = 30.0
    acceleration: float = 25.0


def _write_command(command: dict):
    """ROS2 브릿지에 명령 전달"""
    command['timestamp'] = time.time()
    with open(COMMAND_FILE, 'w') as f:
        json.dump(command, f)


@router.get("/motions")
def get_available_motions():
    """사용 가능한 모션 목록"""
    return {
        "motions": [
            {
                "id": motion_id,
                "name": motion["name"],
                "description": motion["description"],
            }
            for motion_id, motion in MOTIONS.items()
        ]
    }


@router.get("/motions/{motion_id}")
def get_motion_detail(motion_id: str):
    """특정 모션 상세 정보"""
    if motion_id not in MOTIONS:
        raise HTTPException(status_code=404, detail=f"Motion '{motion_id}' not found")
    
    motion = MOTIONS[motion_id]
    return {
        "id": motion_id,
        **motion
    }


@router.post("/motion")
def execute_motion(req: MotionRequest):
    """미리 정의된 모션 실행"""
    if req.motion not in MOTIONS:
        raise HTTPException(
            status_code=400, 
            detail=f"Unknown motion '{req.motion}'. Available: {list(MOTIONS.keys())}"
        )
    
    motion = MOTIONS[req.motion]
    
    # ROS2 브릿지로 명령 전송
    _write_command({
        'type': 'robot_motion',
        'data': {
            'motion_id': req.motion,
            'motion_name': motion['name'],
            'joints': motion['joints'],
            'velocity': motion['velocity'],
            'acceleration': motion['acceleration'],
        }
    })
    
    return {
        "success": True,
        "message": f"모션 '{motion['name']}' 실행 중",
        "motion": req.motion,
        "joints": motion['joints']
    }


@router.post("/motion/custom")
def execute_custom_motion(req: CustomMotionRequest):
    """사용자 정의 조인트 위치로 이동"""
    if len(req.joints) != 6:
        raise HTTPException(status_code=400, detail="joints must have 6 values")
    
    _write_command({
        'type': 'robot_motion',
        'data': {
            'motion_id': 'custom',
            'motion_name': 'Custom',
            'joints': req.joints,
            'velocity': req.velocity,
            'acceleration': req.acceleration,
        }
    })
    
    return {
        "success": True,
        "message": "사용자 정의 모션 실행 중",
        "joints": req.joints
    }


@router.post("/stop")
def stop_robot():
    """로봇 정지"""
    _write_command({
        'type': 'robot_command',
        'data': {
            'command': 'stop'
        }
    })
    
    return {"success": True, "message": "로봇 정지 명령 전송"}
