# app/routers/gripper.py
"""
그리퍼 제어 API
- OnRobot RG2 그리퍼 제어
- gripper_rviz_sync 패키지와 연동
- 파일 기반 상태 공유
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
import subprocess
import json
import os
import time

from app.services.config import GRIPPER_STATE_FILE, GRIPPER_COMMAND_FILE

router = APIRouter(prefix="/gripper", tags=["Gripper"])

# ROS2 환경 설정
def run_ros2_command(cmd: list, timeout: float = 5.0) -> subprocess.CompletedProcess:
    """ROS2 명령 실행 (환경변수 포함)"""
    full_cmd = f"source /opt/ros/humble/setup.bash && source /home/rokey/ros2_ws/install/setup.bash && {' '.join(cmd)}"
    return subprocess.run(
        ['bash', '-c', full_cmd],
        capture_output=True, 
        text=True, 
        timeout=timeout
    )

# 그리퍼 상태 캐시
gripper_state = {
    'width': 0.0,
    'force': 20.0,
    'grip_detected': False,
    'connected': False,
    'last_update': 0
}

# ======================
# Pydantic Models
# ======================
class GripperCommand(BaseModel):
    width: Optional[float] = None   # mm (0~110)
    force: Optional[float] = None   # N (0~40)

class GripperAction(BaseModel):
    action: str  # "open" or "close"

# ======================
# 그리퍼 상태 조회
# ======================
@router.get("/status")
def get_gripper_status():
    """그리퍼 상태 조회"""
    # 먼저 파일에서 읽기 시도 (빠름)
    if os.path.exists(GRIPPER_STATE_FILE):
        try:
            with open(GRIPPER_STATE_FILE, 'r') as f:
                data = json.load(f)
            # 5초 이내 업데이트면 유효
            if time.time() - data.get('timestamp', 0) < 5.0:
                return {
                    "status": "ok",
                    "width": data.get('width', 0),
                    "force": gripper_state['force'],
                    "grip_detected": data.get('grip_detected', False),
                    "connected": True
                }
        except:
            pass
    
    # 파일 없으면 ros2 topic으로 직접 읽기 (느림)
    try:
        result = run_ros2_command(
            ['timeout', '3', 'ros2', 'topic', 'echo', '--once', '/gripper/width/current'],
            timeout=5.0
        )
        if result.returncode == 0 and 'data:' in result.stdout:
            for line in result.stdout.split('\n'):
                if 'data:' in line:
                    width = float(line.split(':')[1].strip())
                    gripper_state['width'] = width
                    gripper_state['connected'] = True
                    break
        else:
            gripper_state['connected'] = False
    except:
        gripper_state['connected'] = False
    
    return {
        "status": "ok" if gripper_state['connected'] else "disconnected",
        "width": gripper_state['width'],
        "force": gripper_state['force'],
        "grip_detected": gripper_state['grip_detected'],
        "connected": gripper_state['connected']
    }

# ======================
# 그리퍼 열기/닫기
# ======================
def run_ros2_service_async(service_name: str, service_type: str):
    """비동기로 ROS2 서비스 호출"""
    import threading
    
    def call_service():
        try:
            full_cmd = f"source /opt/ros/humble/setup.bash && source /home/rokey/ros2_ws/install/setup.bash && ros2 service call {service_name} {service_type}"
            subprocess.run(
                ['bash', '-c', full_cmd],
                capture_output=True,
                text=True,
                timeout=10.0
            )
        except Exception as e:
            print(f"ROS2 service call error: {e}")
    
    thread = threading.Thread(target=call_service, daemon=True)
    thread.start()
    return thread

@router.post("/action")
def gripper_action(cmd: GripperAction):
    """그리퍼 열기/닫기 (ROS2 서비스 호출)"""
    if cmd.action not in ['open', 'close']:
        return {"status": "error", "msg": "Invalid action. Use 'open' or 'close'"}
    
    service_name = f'/gripper/{cmd.action}'
    run_ros2_service_async(service_name, 'std_srvs/srv/Trigger')
    
    return {
        "status": "ok",
        "action": cmd.action,
        "msg": f"Gripper {cmd.action} command sent"
    }

# ======================
# 그리퍼 폭/힘 설정
# ======================
def run_ros2_topic_pub_async(topic: str, msg_type: str, data: str):
    """비동기로 ROS2 토픽 발행"""
    import threading
    
    def publish():
        try:
            full_cmd = f"source /opt/ros/humble/setup.bash && source /home/rokey/ros2_ws/install/setup.bash && ros2 topic pub --once {topic} {msg_type} '{data}'"
            subprocess.run(
                ['bash', '-c', full_cmd],
                capture_output=True,
                text=True,
                timeout=10.0
            )
        except Exception as e:
            print(f"ROS2 topic pub error: {e}")
    
    thread = threading.Thread(target=publish, daemon=True)
    thread.start()
    return thread

@router.post("/command")
def gripper_command(cmd: GripperCommand):
    """그리퍼 폭/힘 설정 - Combined 토픽 사용으로 race condition 방지"""
    results = {}
    
    # 기본값 설정
    width_val = cmd.width if cmd.width is not None else gripper_state['width']
    force_val = cmd.force if cmd.force is not None else gripper_state['force']
    
    # 범위 제한
    width_val = max(0, min(110, width_val))
    force_val = max(0, min(40, force_val))
    
    # Combined 토픽으로 한번에 전송 (Float32MultiArray: [width, force])
    data = f"{{data: [{width_val}, {force_val}]}}"
    run_ros2_topic_pub_async('/gripper/command', 'std_msgs/msg/Float32MultiArray', data)
    
    # 상태 업데이트
    if cmd.width is not None:
        results['width'] = width_val
        gripper_state['width'] = width_val
    if cmd.force is not None:
        results['force'] = force_val
        gripper_state['force'] = force_val
    
    return {
        "status": "ok",
        "results": results
    }

# ======================
# 빠른 프리셋
# ======================
@router.post("/preset/{preset_name}")
def gripper_preset(preset_name: str):
    """그리퍼 프리셋 (자주 쓰는 설정)"""
    presets = {
        'full_open': {'width': 110, 'force': 20},
        'half_open': {'width': 55, 'force': 20},
        'gentle_close': {'width': 0, 'force': 10},
        'firm_close': {'width': 0, 'force': 40},
        'pick_small': {'width': 30, 'force': 25},
        'pick_large': {'width': 80, 'force': 30},
    }
    
    if preset_name not in presets:
        return {
            "status": "error",
            "msg": f"Unknown preset. Available: {list(presets.keys())}"
        }
    
    preset = presets[preset_name]
    return gripper_command(GripperCommand(**preset))
