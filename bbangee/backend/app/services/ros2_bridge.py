"""
ROS2 브릿지 통신 모듈
=====================
/tmp JSON 파일 기반 IPC 통합 (쓰기/읽기)

Before: _write_command() 가 ros2.py, robot.py, scenario.py, pistol_grip.py 4곳에 복붙
After : 이 모듈 하나에서 import
"""

import json
import os
import time

from app.services.config import (
    ROS2_COMMAND_FILE,
    ROS2_STATE_FILE,
    COLLISION_COMMAND_FILE,
    COLLISION_STATE_FILE,
)


# ============================================
# 명령 쓰기 (FastAPI → ROS2 노드)
# ============================================

def write_command(command: dict, command_file: str = ROS2_COMMAND_FILE) -> None:
    """ROS2 브릿지에 JSON 명령 전달"""
    command["timestamp"] = time.time()
    with open(command_file, "w") as f:
        json.dump(command, f)


def write_collision_command(cmd: dict) -> None:
    """충돌 복구 전용 명령"""
    write_command(cmd, COLLISION_COMMAND_FILE)


# ============================================
# 상태 읽기 (ROS2 노드 → FastAPI)
# ============================================

_DEFAULT_STATE: dict = {
    "timestamp": 0,
    "robot": {
        "connected": False,
        "mode": "unknown",
        "joint_positions": [0.0] * 6,
        "status": "idle",
    },
    "camera": {"connected": False, "streaming": False},
    "face_tracking": {
        "enabled": False,
        "face_detected": False,
        "face_position": {"x": 0, "y": 0, "z": 0},
        "tracking_target": None,
    },
    "system": {
        "bringup_running": False,
        "camera_running": False,
        "detection_running": False,
        "tracking_running": False,
        "joint_tracking_running": False,
    },
}


def read_state(state_file: str = ROS2_STATE_FILE) -> dict:
    """ROS2 상태 파일 읽기"""
    if not os.path.exists(state_file):
        return _DEFAULT_STATE.copy()
    try:
        with open(state_file, "r") as f:
            return json.load(f)
    except Exception:
        return _DEFAULT_STATE.copy()


def read_collision_state() -> dict:
    """충돌 복구 상태 파일 읽기"""
    default = {
        "robot_state": "UNKNOWN",
        "robot_state_code": -1,
        "is_safe_stop": False,
        "is_recovering": False,
        "last_action": "",
        "log": [],
        "timestamp": 0,
    }
    if not os.path.exists(COLLISION_STATE_FILE):
        return default
    try:
        with open(COLLISION_STATE_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return default


def is_bridge_running(state: dict | None = None) -> bool:
    """브릿지 노드가 실행 중인지 (상태 파일이 5초 이내이면 True)"""
    if state is None:
        state = read_state()
    return (time.time() - state.get("timestamp", 0)) < 5


# ============================================
# 고수준 명령 헬퍼
# ============================================

def send_robot_motion(motion_id: str, motion_name: str,
                      joints: list[float], velocity: float,
                      acceleration: float) -> None:
    """로봇 모션 명령 전송"""
    write_command({
        "type": "robot_motion",
        "data": {
            "motion_id": motion_id,
            "motion_name": motion_name,
            "joints": joints,
            "velocity": velocity,
            "acceleration": acceleration,
        },
    })


def send_robot_command(command: str, params: dict | None = None) -> None:
    """로봇 명령 전송 (stop, home, start 등)"""
    write_command({
        "type": "robot_command",
        "data": {
            "command": command,
            "params": params or {},
        },
    })


def send_tracking_speed(multiplier: float) -> None:
    """추적 속도 배율 명령"""
    write_command({
        "type": "robot_command",
        "data": {
            "command": "speed_boost",
            "speed_multiplier": multiplier,
        },
    })
