"""
ESP32 디바이스 제어 서비스
==========================
서보/레이저 제어 + 연결 상태 관리

Before: devices.py 라우터 안에 비즈니스 로직이 혼재
After : 이 서비스에서 로직 관리, 라우터는 thin layer
"""

import time
from typing import Union

import requests

from app.services.config import ESP32_BASE_URL, ESP32_IP

# 연결 상태 추적
_connection: dict = {
    "connected": False,
    "last_check": None,
    "last_success": None,
    "fail_count": 0,
}


def get_connection_status() -> dict:
    """현재 연결 상태 사본 반환"""
    return {**_connection, "ip": ESP32_IP}


def ping() -> dict:
    """ESP32 연결 상태 확인"""
    try:
        start = time.time()
        requests.get(f"{ESP32_BASE_URL}/", timeout=2)
        latency = (time.time() - start) * 1000

        _connection.update(
            connected=True,
            last_check=time.time(),
            last_success=time.time(),
            fail_count=0,
        )
        return {"connected": True, "latency_ms": round(latency, 1), "ip": ESP32_IP}

    except requests.exceptions.ConnectTimeout:
        _connection.update(connected=False, fail_count=_connection["fail_count"] + 1)
        return {"connected": False, "error": "Connection timeout", "ip": ESP32_IP}
    except requests.exceptions.ConnectionError:
        _connection.update(connected=False, fail_count=_connection["fail_count"] + 1)
        return {"connected": False, "error": "Connection refused", "ip": ESP32_IP}
    except Exception as e:
        _connection.update(connected=False, fail_count=_connection["fail_count"] + 1)
        return {"connected": False, "error": str(e), "ip": ESP32_IP}


def call_esp32(path: str, data: str, retry: bool = True) -> str:
    """ESP32 에 POST 요청 (text/plain body)"""
    max_retries = 3 if retry else 1
    last_error: Exception | None = None

    for attempt in range(max_retries):
        try:
            r = requests.post(
                f"{ESP32_BASE_URL}{path}",
                data=data,
                headers={"Content-Type": "text/plain"},
                timeout=2,
            )
            _connection.update(connected=True, last_success=time.time(), fail_count=0)
            return r.text
        except Exception as e:
            last_error = e
            _connection.update(connected=False, fail_count=_connection["fail_count"] + 1)
            if attempt < max_retries - 1:
                time.sleep(0.3)

    raise RuntimeError(
        f"ESP32 connection failed after {max_retries} attempts: {last_error}"
    )


# ============================================
# 고수준 헬퍼
# ============================================

def parse_target(target: Union[bool, str]) -> bool:
    """target 을 bool/str 모두 받아서 bool 로 변환"""
    if isinstance(target, bool):
        return target
    if isinstance(target, str):
        return target.lower() in ("on", "true", "1")
    return False


def control_servo(on: bool) -> dict:
    """서보 ON/OFF"""
    try:
        call_esp32("/device/servo", "on" if on else "off")
        return {"status": "ok", "servo_state": on}
    except Exception as e:
        return {"status": "error", "msg": str(e)}


def control_laser(on: bool) -> dict:
    """레이저 ON/OFF"""
    try:
        call_esp32("/device/laser", "on" if on else "off")
        return {"status": "ok", "laser_state": on}
    except Exception as e:
        return {"status": "error", "msg": str(e)}


def reset_all() -> dict:
    """레이저 + 서보 OFF 후 ping"""
    results = {"laser": False, "servo": False, "ping": False}
    errors: list[str] = []

    try:
        call_esp32("/device/laser", "off", retry=True)
        results["laser"] = True
    except Exception as e:
        errors.append(f"laser: {e}")

    try:
        call_esp32("/device/servo", "off", retry=True)
        results["servo"] = True
    except Exception as e:
        errors.append(f"servo: {e}")

    ping_result = ping()
    results["ping"] = ping_result["connected"]

    if all(results.values()):
        return {"status": "ok", "message": "ESP32 reset successful", "results": results}
    return {
        "status": "partial" if any(results.values()) else "error",
        "message": "ESP32 reset had issues",
        "results": results,
        "errors": errors,
    }
