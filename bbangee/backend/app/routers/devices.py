# app/routers/devices.py
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Union, Optional
import requests
import json
import os

router = APIRouter(prefix="/device", tags=["Device"])

# 자동 모드 설정 파일
AUTO_MODE_FILE = '/tmp/ros2_auto_mode.json'
STATE_FILE = '/tmp/ros2_bridge_state.json'

# 🔵 ESP32 IP 주소 (시리얼에서 확인한 값)
ESP32_IP = "192.168.10.50"
ESP32_BASE = f"http://{ESP32_IP}"

# ESP32 연결 상태 추적
esp32_connection_status = {
    'connected': False,
    'last_check': None,
    'last_success': None,
    'fail_count': 0
}

# ======================
# 공통 요청 함수
# ======================
def ping_esp32() -> dict:
    """ESP32 연결 상태 확인 (ping)"""
    import time
    try:
        start = time.time()
        # ESP32의 기본 응답 확인 (간단한 GET 요청)
        r = requests.get(f"{ESP32_BASE}/", timeout=2)
        latency = (time.time() - start) * 1000  # ms
        
        esp32_connection_status['connected'] = True
        esp32_connection_status['last_check'] = time.time()
        esp32_connection_status['last_success'] = time.time()
        esp32_connection_status['fail_count'] = 0
        
        return {
            'connected': True,
            'latency_ms': round(latency, 1),
            'ip': ESP32_IP
        }
    except requests.exceptions.ConnectTimeout:
        esp32_connection_status['connected'] = False
        esp32_connection_status['fail_count'] += 1
        return {'connected': False, 'error': 'Connection timeout', 'ip': ESP32_IP}
    except requests.exceptions.ConnectionError:
        esp32_connection_status['connected'] = False
        esp32_connection_status['fail_count'] += 1
        return {'connected': False, 'error': 'Connection refused', 'ip': ESP32_IP}
    except Exception as e:
        esp32_connection_status['connected'] = False
        esp32_connection_status['fail_count'] += 1
        return {'connected': False, 'error': str(e), 'ip': ESP32_IP}

def call_esp32(path: str, data: str, retry: bool = True):
    """ESP32에 POST 요청 (text/plain body) - 자동 재시도 포함"""
    max_retries = 3 if retry else 1
    last_error = None
    
    for attempt in range(max_retries):
        try:
            r = requests.post(
                f"{ESP32_BASE}{path}",
                data=data,
                headers={"Content-Type": "text/plain"},
                timeout=2
            )
            # 성공 시 연결 상태 업데이트
            import time
            esp32_connection_status['connected'] = True
            esp32_connection_status['last_success'] = time.time()
            esp32_connection_status['fail_count'] = 0
            return r.text
        except Exception as e:
            last_error = e
            esp32_connection_status['connected'] = False
            esp32_connection_status['fail_count'] += 1
            if attempt < max_retries - 1:
                import time
                time.sleep(0.3)  # 재시도 전 대기
    
    raise RuntimeError(f"ESP32 connection failed after {max_retries} attempts: {last_error}")

def parse_target(target: Union[bool, str]) -> bool:
    """target을 bool 또는 str("on"/"off") 모두 받아서 bool로 변환"""
    if isinstance(target, bool):
        return target
    if isinstance(target, str):
        return target.lower() in ("on", "true", "1")
    return False

# ======================
# Pydantic Models
# ======================
class ServoCommand(BaseModel):
    target: Union[bool, str]  # true/"on" = ON, false/"off" = OFF

class LaserCommand(BaseModel):
    target: Union[bool, str]  # true/"on" = ON, false/"off" = OFF

# ======================
# Servo API
# ======================
@router.post("/servo")
def control_servo(cmd: ServoCommand):
    try:
        is_on = parse_target(cmd.target)
        call_esp32("/device/servo", "on" if is_on else "off")

        return {
            "status": "ok",
            "servo_state": is_on
        }
    except Exception as e:
        return {
            "status": "error",
            "msg": str(e)
        }

# ======================
# Laser API
# ======================
@router.post("/laser")
def control_laser(cmd: LaserCommand):
    try:
        is_on = parse_target(cmd.target)
        call_esp32("/device/laser", "on" if is_on else "off")

        return {
            "status": "ok",
            "laser_state": is_on
        }
    except Exception as e:
        return {
            "status": "error",
            "msg": str(e)
        }

# ======================
# ESP32 Health Check & Reset
# ======================
@router.get("/esp32/status")
def get_esp32_status():
    """ESP32 연결 상태 확인 (ping)"""
    result = ping_esp32()
    return {
        "status": "ok" if result['connected'] else "error",
        **result,
        "fail_count": esp32_connection_status['fail_count']
    }

@router.post("/esp32/reset")
def reset_esp32():
    """ESP32 초기화 (레이저/서보 OFF 후 상태 리셋)"""
    results = {'laser': False, 'servo': False, 'ping': False}
    errors = []
    
    # 1. 레이저 OFF
    try:
        call_esp32("/device/laser", "off", retry=True)
        results['laser'] = True
    except Exception as e:
        errors.append(f"laser: {e}")
    
    # 2. 서보 OFF
    try:
        call_esp32("/device/servo", "off", retry=True)
        results['servo'] = True
    except Exception as e:
        errors.append(f"servo: {e}")
    
    # 3. 연결 확인
    ping_result = ping_esp32()
    results['ping'] = ping_result['connected']
    
    if results['laser'] and results['servo'] and results['ping']:
        return {
            "status": "ok",
            "message": "ESP32 reset successful",
            "results": results
        }
    else:
        return {
            "status": "partial" if any(results.values()) else "error",
            "message": "ESP32 reset had issues",
            "results": results,
            "errors": errors
        }

# ======================
# Auto Mode Models
# ======================
class AutoModeCommand(BaseModel):
    laser: Optional[bool] = None
    servo: Optional[bool] = None
    timeout: Optional[float] = None  # 미감지 타임아웃 (초)

# ======================
# Auto Mode API
# ======================
@router.get("/auto")
def get_auto_mode():
    """자동 모드 상태 조회"""
    # 1. 설정 파일에서 읽기
    auto_config = {'laser': False, 'servo': False, 'timeout': 1.0}
    if os.path.exists(AUTO_MODE_FILE):
        try:
            with open(AUTO_MODE_FILE, 'r') as f:
                auto_config = json.load(f)
        except:
            pass
    
    # 2. 실시간 상태 파일에서 읽기 (현재 ON/OFF 상태)
    current_state = {'laser_state': False, 'servo_state': False}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                state = json.load(f)
                auto_state = state.get('auto_mode', {})
                current_state['laser_state'] = auto_state.get('laser_state', False)
                current_state['servo_state'] = auto_state.get('servo_state', False)
        except:
            pass
    
    return {
        "status": "ok",
        "laser_auto": auto_config.get('laser', False),
        "servo_auto": auto_config.get('servo', False),
        "timeout": auto_config.get('timeout', 1.0),
        "laser_state": current_state['laser_state'],
        "servo_state": current_state['servo_state']
    }

@router.post("/auto")
def set_auto_mode(cmd: AutoModeCommand):
    """자동 모드 설정 (얼굴 감지 → 레이저/서보 자동 ON/OFF)"""
    # 기존 설정 로드
    current = {'laser': False, 'servo': False, 'timeout': 1.0}
    if os.path.exists(AUTO_MODE_FILE):
        try:
            with open(AUTO_MODE_FILE, 'r') as f:
                current = json.load(f)
        except:
            pass
    
    # 새 설정 적용
    if cmd.laser is not None:
        current['laser'] = cmd.laser
    if cmd.servo is not None:
        current['servo'] = cmd.servo
    if cmd.timeout is not None:
        current['timeout'] = max(0.5, min(5.0, cmd.timeout))  # 0.5~5초 제한
    
    # 파일로 저장 (bridge_node가 읽음)
    try:
        with open(AUTO_MODE_FILE, 'w') as f:
            json.dump(current, f)
        return {
            "status": "ok",
            "laser_auto": current['laser'],
            "servo_auto": current['servo'],
            "timeout": current['timeout']
        }
    except Exception as e:
        return {"status": "error", "msg": str(e)}
