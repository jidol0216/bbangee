"""
ROS2 Router (리팩토링)
- _read_state / _write_command → ros2_bridge 서비스
- 파일 경로 → config 모듈
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any
import os
import time

from app.services.ros2_bridge import (
    read_state,
    write_command,
    read_collision_state,
    write_collision_command,
    is_bridge_running,
    send_robot_command,
)
from app.services.config import ROS2_CAMERA_FRAME

router = APIRouter(prefix="/ros2", tags=["ROS2"])


class TrackingCommand(BaseModel):
    enable: bool

class RobotCommand(BaseModel):
    command: str
    params: Optional[Dict[str, Any]] = None

class CollisionCommand(BaseModel):
    command: str


# ===== Status Endpoints =====

@router.get("/status")
def get_ros2_status():
    state = read_state()
    return {"bridge_running": is_bridge_running(state), "state": state}

@router.get("/robot")
def get_robot_status():
    return read_state().get("robot", {})

@router.get("/camera")
def get_camera_status():
    return read_state().get("camera", {})

@router.get("/face_tracking")
def get_face_tracking_status():
    return read_state().get("face_tracking", {})

@router.get("/system")
def get_system_status():
    return read_state().get("system", {})


# ===== Commands =====

VALID_ROBOT_COMMANDS = [
    "take_control", "start", "stop", "home", "ready",
    "mode1", "mode2", "j6_rotate", "tracking_on", "tracking_off",
]

@router.post("/tracking/enable")
def set_tracking_enable(cmd: TrackingCommand):
    write_command({"type": "tracking_enable", "value": cmd.enable})
    return {"success": True, "message": f"Tracking {'enabled' if cmd.enable else 'disabled'}"}


@router.post("/robot/command")
def send_robot_cmd(cmd: RobotCommand):
    if cmd.command not in VALID_ROBOT_COMMANDS:
        raise HTTPException(status_code=400, detail=f"Invalid command. Valid: {VALID_ROBOT_COMMANDS}")
    send_robot_command(cmd.command, cmd.params)
    return {"success": True, "message": f"Command '{cmd.command}' sent"}


@router.get("/nodes")
def get_running_nodes():
    system = read_state().get("system", {})
    node_map = {
        "bringup_running": "dsr_bringup",
        "camera_running": "realsense_camera",
        "detection_running": "face_detection_node",
        "tracking_running": "face_tracking_node",
        "joint_tracking_running": "joint_tracking_node",
    }
    nodes = [
        {"name": name, "status": "running"}
        for key, name in node_map.items()
        if system.get(key)
    ]
    return {"nodes": nodes, "count": len(nodes)}


# ===== Camera Streaming =====

_last_valid_frame = None
_last_frame_time = 0


def _read_frame_safe():
    global _last_valid_frame, _last_frame_time

    if not os.path.exists(ROS2_CAMERA_FRAME):
        return _last_valid_frame

    try:
        mtime = os.path.getmtime(ROS2_CAMERA_FRAME)
        if mtime == _last_frame_time and _last_valid_frame:
            return _last_valid_frame

        with open(ROS2_CAMERA_FRAME, "rb") as f:
            frame = f.read()

        if len(frame) > 2 and frame[:2] == b"\xff\xd8" and frame[-2:] == b"\xff\xd9":
            _last_valid_frame = frame
            _last_frame_time = mtime
            return frame
        return _last_valid_frame
    except Exception:
        return _last_valid_frame


@router.get("/camera/frame")
def get_camera_frame():
    if not os.path.exists(ROS2_CAMERA_FRAME):
        raise HTTPException(status_code=404, detail="No camera frame available")
    if time.time() - os.path.getmtime(ROS2_CAMERA_FRAME) > 10:
        raise HTTPException(status_code=404, detail="Camera stream inactive")
    return FileResponse(ROS2_CAMERA_FRAME, media_type="image/jpeg")


def _generate_mjpeg():
    while True:
        frame = _read_frame_safe()
        if frame:
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n"
                b"Content-Length: " + str(len(frame)).encode() + b"\r\n\r\n"
                + frame + b"\r\n"
            )
        time.sleep(0.05)


@router.get("/camera/stream")
def camera_stream():
    return StreamingResponse(_generate_mjpeg(), media_type="multipart/x-mixed-replace; boundary=frame")


# ===== Collision Recovery =====

VALID_COLLISION_COMMANDS = [
    "check_status", "auto_recovery", "move_home",
    "move_down_slow", "move_down_fast", "monitor_start", "monitor_stop",
]

@router.get("/collision/status")
def get_collision_status():
    state = read_collision_state()
    node_running = (time.time() - state.get("timestamp", 0)) < 3
    return {"node_running": node_running, "state": state}


@router.post("/collision/command")
def send_collision_cmd(cmd: CollisionCommand):
    if cmd.command not in VALID_COLLISION_COMMANDS:
        raise HTTPException(status_code=400, detail=f"Invalid command. Valid: {VALID_COLLISION_COMMANDS}")
    write_collision_command({"command": cmd.command})
    return {"success": True, "message": f"Command '{cmd.command}' sent"}
