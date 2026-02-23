"""
ROS2 Router for FastAPI Backend
- ROS2 상태 조회
- ROS2 명령 전송
- 카메라 이미지 스트리밍
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any
import json
import os
import time

router = APIRouter(prefix="/ros2", tags=["ROS2"])

# 파일 경로 (ROS2 브릿지 노드와 공유)
STATE_FILE = '/tmp/ros2_bridge_state.json'
COMMAND_FILE = '/tmp/ros2_bridge_command.json'
IMAGE_FILE = '/tmp/ros2_camera_frame.jpg'


class TrackingCommand(BaseModel):
    enable: bool


class RobotCommand(BaseModel):
    command: str  # 'home', 'stop', 'tracking_on', 'tracking_off'
    params: Optional[Dict[str, Any]] = None


def _read_state() -> dict:
    """ROS2 상태 파일 읽기"""
    default_state = {
        'timestamp': 0,
        'robot': {
            'connected': False,
            'mode': 'unknown',
            'joint_positions': [0.0] * 6,
            'status': 'idle'
        },
        'camera': {
            'connected': False,
            'streaming': False
        },
        'face_tracking': {
            'enabled': False,
            'face_detected': False,
            'face_position': {'x': 0, 'y': 0, 'z': 0},
            'tracking_target': None
        },
        'system': {
            'bringup_running': False,
            'camera_running': False,
            'detection_running': False,
            'tracking_running': False,
            'joint_tracking_running': False
        }
    }
    
    if not os.path.exists(STATE_FILE):
        return default_state
    
    try:
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return default_state


def _write_command(command: dict):
    """ROS2 명령 파일 작성"""
    command['timestamp'] = time.time()
    with open(COMMAND_FILE, 'w') as f:
        json.dump(command, f)


# ===== API Endpoints =====

@router.get("/status")
def get_ros2_status():
    """전체 ROS2 상태 조회"""
    state = _read_state()
    
    # 상태 파일이 5초 이상 오래되면 브릿지 노드가 실행 중이 아님
    is_bridge_running = (time.time() - state.get('timestamp', 0)) < 5
    
    return {
        "bridge_running": is_bridge_running,
        "state": state
    }


@router.get("/robot")
def get_robot_status():
    """로봇 상태만 조회"""
    state = _read_state()
    return state.get('robot', {})


@router.get("/camera")
def get_camera_status():
    """카메라 상태 조회"""
    state = _read_state()
    return state.get('camera', {})


@router.get("/face_tracking")
def get_face_tracking_status():
    """얼굴 트래킹 상태 조회"""
    state = _read_state()
    return state.get('face_tracking', {})


@router.get("/system")
def get_system_status():
    """시스템(노드 실행) 상태 조회"""
    state = _read_state()
    return state.get('system', {})


@router.post("/tracking/enable")
def set_tracking_enable(cmd: TrackingCommand):
    """얼굴 트래킹 활성화/비활성화"""
    _write_command({
        'type': 'tracking_enable',
        'value': cmd.enable
    })
    return {"success": True, "message": f"Tracking {'enabled' if cmd.enable else 'disabled'}"}


@router.post("/robot/command")
def send_robot_command(cmd: RobotCommand):
    """로봇 명령 전송"""
    valid_commands = [
        'take_control',  # 웹 제어권 가져오기
        'start',         # 추적 시작
        'stop',          # 추적 중지
        'home',          # 홈 위치로 이동
        'ready',         # 시작 위치로 이동
        'mode1',         # 직접 제어 모드
        'mode2',         # 최적 제어 모드
        'j6_rotate',     # J6 180도 회전 (카메라 방향 전환)
        'tracking_on', 
        'tracking_off'
    ]
    
    if cmd.command not in valid_commands:
        raise HTTPException(status_code=400, detail=f"Invalid command. Valid: {valid_commands}")
    
    _write_command({
        'type': 'robot_command',
        'data': {
            'command': cmd.command,
            'params': cmd.params or {}
        }
    })
    return {"success": True, "message": f"Command '{cmd.command}' sent"}


@router.get("/nodes")
def get_running_nodes():
    """실행 중인 노드 목록"""
    state = _read_state()
    system = state.get('system', {})
    
    nodes = []
    if system.get('bringup_running'):
        nodes.append({'name': 'dsr_bringup', 'status': 'running'})
    if system.get('camera_running'):
        nodes.append({'name': 'realsense_camera', 'status': 'running'})
    if system.get('detection_running'):
        nodes.append({'name': 'face_detection_node', 'status': 'running'})
    if system.get('tracking_running'):
        nodes.append({'name': 'face_tracking_node', 'status': 'running'})
    if system.get('joint_tracking_running'):
        nodes.append({'name': 'joint_tracking_node', 'status': 'running'})
    
    return {"nodes": nodes, "count": len(nodes)}


# ===== Camera Streaming =====

# 마지막 유효한 프레임 캐시
_last_valid_frame = None
_last_frame_time = 0

@router.get("/camera/frame")
def get_camera_frame():
    """현재 카메라 프레임 (JPEG)"""
    if not os.path.exists(IMAGE_FILE):
        raise HTTPException(status_code=404, detail="No camera frame available")
    
    # 파일이 10초 이상 오래되면 스트리밍 안됨
    if time.time() - os.path.getmtime(IMAGE_FILE) > 10:
        raise HTTPException(status_code=404, detail="Camera stream inactive")
    
    return FileResponse(IMAGE_FILE, media_type="image/jpeg")


def _read_frame_safe():
    """안전하게 프레임 읽기 - 깨진 파일 방지"""
    global _last_valid_frame, _last_frame_time
    
    if not os.path.exists(IMAGE_FILE):
        return _last_valid_frame
    
    try:
        # 파일 수정 시간 확인
        mtime = os.path.getmtime(IMAGE_FILE)
        
        # 파일이 업데이트되지 않았으면 캐시 사용
        if mtime == _last_frame_time and _last_valid_frame:
            return _last_valid_frame
        
        # 파일 읽기
        with open(IMAGE_FILE, 'rb') as f:
            frame = f.read()
        
        # JPEG 유효성 검사 (SOI, EOI 마커 확인)
        if len(frame) > 2 and frame[:2] == b'\xff\xd8' and frame[-2:] == b'\xff\xd9':
            _last_valid_frame = frame
            _last_frame_time = mtime
            return frame
        else:
            # 깨진 JPEG면 캐시 사용
            return _last_valid_frame
            
    except Exception:
        return _last_valid_frame


def _generate_mjpeg():
    """MJPEG 스트림 생성기 - 안정화 버전"""
    while True:
        frame = _read_frame_safe()
        if frame:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n'
                   b'Content-Length: ' + str(len(frame)).encode() + b'\r\n\r\n' 
                   + frame + b'\r\n')
        time.sleep(0.05)  # 20fps (더 안정적)


@router.get("/camera/stream")
def camera_stream():
    """MJPEG 스트림"""
    return StreamingResponse(
        _generate_mjpeg(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


# ===== Collision Recovery =====

COLLISION_STATE_FILE = '/tmp/collision_recovery_state.json'
COLLISION_COMMAND_FILE = '/tmp/collision_recovery_command.json'


class CollisionCommand(BaseModel):
    command: str  # 'check_status', 'auto_recovery', 'move_home', 'move_down_slow', 'move_down_fast', 'monitor_start', 'monitor_stop'


def _read_collision_state() -> dict:
    """충돌 복구 상태 읽기"""
    default = {
        'robot_state': 'UNKNOWN',
        'robot_state_code': -1,
        'is_safe_stop': False,
        'is_recovering': False,
        'last_action': '',
        'log': [],
        'timestamp': 0
    }
    if not os.path.exists(COLLISION_STATE_FILE):
        return default
    try:
        with open(COLLISION_STATE_FILE, 'r') as f:
            return json.load(f)
    except:
        return default


def _write_collision_command(cmd: dict):
    """충돌 복구 명령 작성"""
    cmd['timestamp'] = time.time()
    with open(COLLISION_COMMAND_FILE, 'w') as f:
        json.dump(cmd, f)


@router.get("/collision/status")
def get_collision_status():
    """충돌 복구 상태 조회"""
    state = _read_collision_state()
    is_node_running = (time.time() - state.get('timestamp', 0)) < 3
    return {
        "node_running": is_node_running,
        "state": state
    }


@router.post("/collision/command")
def send_collision_command(cmd: CollisionCommand):
    """충돌 복구 명령 전송"""
    valid_commands = [
        'check_status',      # 상태 확인
        'auto_recovery',     # 자동 복구
        'move_home',         # 홈 위치 이동
        'move_down_slow',    # 충돌 테스트 (느림)
        'move_down_fast',    # 충돌 테스트 (빠름)
        'monitor_start',     # 모니터링 시작
        'monitor_stop',      # 모니터링 중지
    ]
    if cmd.command not in valid_commands:
        raise HTTPException(status_code=400, detail=f"Invalid command. Valid: {valid_commands}")
    
    _write_collision_command({'command': cmd.command})
    return {"success": True, "message": f"Command '{cmd.command}' sent"}
