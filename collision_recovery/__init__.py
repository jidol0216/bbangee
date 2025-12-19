"""
두산 로봇 충돌 감지 및 자동 복구 패키지
==========================================

모듈 구조:
├── config.py          # 로봇 설정 및 상수
├── robot_state.py     # 상태 조회 및 모니터링
├── recovery.py        # 복구 시퀀스
├── motion.py          # 모션 제어 (move, jog)
├── collision_demo.py  # 메인 데모 실행
└── main.py            # 진입점

사용 예:
    python3 -m collision_recovery.main
"""

from .config import ROBOT_ID, ROBOT_MODEL, HOME_POSITION
from .robot_state import RobotStateManager, state_name
from .recovery import RecoveryManager
from .motion import MotionController

__all__ = [
    'ROBOT_ID',
    'ROBOT_MODEL', 
    'HOME_POSITION',
    'RobotStateManager',
    'RecoveryManager',
    'MotionController',
    'state_name',
]
