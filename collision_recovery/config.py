"""
config.py - 로봇 설정 및 상수 정의
===================================

이 모듈은 로봇 연결 정보와 상태 코드를 정의합니다.

ROS2 네임스페이스: /dsr01
로봇 모델: M0609 (6축 협동로봇)
"""

# ==============================
# 로봇 기본 설정
# ==============================
ROBOT_ID = "dsr01"          # ROS2 네임스페이스
ROBOT_MODEL = "m0609"       # 로봇 모델명

# ==============================
# 홈 위치 (관절 각도, 단위: degree)
# ==============================
# [J1, J2, J3, J4, J5, J6]
HOME_POSITION = [0.0, -30.0, 100.0, 70.0, 90.0, 0.0]  # 카메라 높이 올림

# ==============================
# 로봇 상태 코드
# ==============================
# GetRobotState 서비스 응답값
STATE_CODES = {
    0: "INITIALIZING",     # 초기화 중
    1: "STANDBY",          # 대기 (정상) ✅
    2: "MOVING",           # 동작 중
    3: "SAFE_OFF",         # 서보 OFF
    4: "TEACHING",         # 티칭 모드
    5: "SAFE_STOP",        # 충돌 감지 ⚠️ (노란 링)
    6: "EMERGENCY_STOP",   # 비상 정지 🔴 (빨간 링)
    7: "HOMING",           # 원점 복귀 중
    8: "RECOVERY",         # 복구 모드
    9: "SAFE_STOP2",       # 충돌 감지 2
    10: "SAFE_OFF2",       # 서보 OFF 2
}

# ==============================
# 로봇 제어 명령 코드
# ==============================
# SetRobotControl 서비스 요청값
CONTROL_COMMANDS = {
    "RESET_SAFE_STOP": 2,   # SAFE_STOP 리셋 (충돌 해제)
    "SERVO_ON": 3,          # 서보 ON (SAFE_OFF → STANDBY)
    "RESET_RECOVERY": 7,    # RECOVERY 모드 해제
}

# ==============================
# 안전 모드 코드
# ==============================
# SetSafetyMode 서비스 요청값
SAFETY_MODE = {
    "RECOVERY": 2,          # 복구 모드
}

SAFETY_EVENT = {
    "ENTER": 0,             # 복구 모드 진입
    "EXECUTE": 1,           # 복구 실행
    "COMPLETE": 2,          # 복구 완료
}

# ==============================
# Jog 축 코드
# ==============================
# Jog 서비스 요청값
JOG_AXIS = {
    "J1": 0, "J2": 1, "J3": 2, "J4": 3, "J5": 4, "J6": 5,  # 관절 공간
    "X": 6, "Y": 7, "Z": 8, "RX": 9, "RY": 10, "RZ": 11,   # 작업 공간
}

JOG_REFERENCE = {
    "BASE": 0,              # 베이스 좌표계
    "TOOL": 1,              # 툴 좌표계
}


def state_name(code: int) -> str:
    """상태 코드를 이름으로 변환"""
    return STATE_CODES.get(code, f"UNKNOWN({code})")
