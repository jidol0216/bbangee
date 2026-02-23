"""
로봇 모션 정의
==============
MOTIONS 딕셔너리 단일 소스 (robot.py, scenario.py 에서 공유)

Before: 3곳에 복붙 + "robot.py와 동기화!" 주석
After : 이 파일 하나에서 import
"""

from app.services.ros2_bridge import send_robot_motion

# ============================================
# 미리 정의된 조인트 포지션 (deg)
# ============================================

MOTIONS: dict[str, dict] = {
    "salute": {
        "name": "경례",
        "description": "거수경례 자세 - 팔을 들어 경례",
        "joints": [3.0, 0.0, 60.0, 120.0, 45.0, 0.0],
        "velocity": 25.0,
        "acceleration": 20.0,
    },
    "high_ready": {
        "name": "High Ready",
        "description": "경계 자세 (위를 향함)",
        "joints": [3.0, -20.0, 92.0, 86.0, 0.0, 0.0],
        "velocity": 30.0,
        "acceleration": 25.0,
    },
    "home": {
        "name": "홈",
        "description": "홈 위치 - 안전 자세",
        "joints": [0.0, 0.0, 90.0, 0.0, 90.0, 0.0],
        "velocity": 30.0,
        "acceleration": 25.0,
    },
    "barrier_open": {
        "name": "차단봉 열기",
        "description": "차단봉 개방 동작",
        "joints": [3.0, -15.0, 80.0, 100.0, -20.0, 0.0],
        "velocity": 20.0,
        "acceleration": 15.0,
    },
    "threat": {
        "name": "위협",
        "description": "위협 자세 - 적 대응",
        "joints": [35.0, -20.0, 110.0, 50.0, 10.0, 0.0],
        "velocity": 40.0,
        "acceleration": 35.0,
    },
}


def execute_motion(motion_id: str) -> bool:
    """모션 실행 (MOTIONS에서 찾아 ROS2 브릿지로 전송)"""
    if motion_id not in MOTIONS:
        return False
    m = MOTIONS[motion_id]
    send_robot_motion(
        motion_id=motion_id,
        motion_name=m["name"],
        joints=m["joints"],
        velocity=m["velocity"],
        acceleration=m["acceleration"],
    )
    return True
