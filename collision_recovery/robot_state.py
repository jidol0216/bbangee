"""
robot_state.py - 로봇 상태 조회 및 모니터링
============================================

ROS2 서비스를 통해 로봇 상태를 조회하고 관리합니다.

사용 서비스:
    - /dsr01/system/get_robot_state (GetRobotState)
    - /dsr01/system/get_last_alarm (GetLastAlarm)
    - /dsr01/aux_control/get_current_posj (GetCurrentPosj)
"""

import rclpy
from rclpy.node import Node
from datetime import timedelta, timezone, datetime

from dsr_msgs2.srv import GetRobotState, GetLastAlarm, GetCurrentPosj

from .config import ROBOT_ID, STATE_CODES


def state_name(code: int) -> str:
    """상태 코드를 이름으로 변환"""
    return STATE_CODES.get(code, f"UNKNOWN({code})")


class RobotStateManager:
    """
    로봇 상태 관리 클래스
    
    주요 기능:
        - 현재 로봇 상태 조회 (STANDBY, SAFE_STOP 등)
        - SAFE_STOP/SAFE_OFF 상태 판별
        - 현재 관절 위치 조회
        - 마지막 알람 조회
    """
    
    def __init__(self, node: Node):
        """
        Args:
            node: ROS2 노드 인스턴스
        """
        self.node = node
        self.kst = timezone(timedelta(hours=9))
        
        # 서비스 클라이언트 생성
        self.state_client = node.create_client(
            GetRobotState, f"/{ROBOT_ID}/system/get_robot_state"
        )
        self.alarm_client = node.create_client(
            GetLastAlarm, f"/{ROBOT_ID}/system/get_last_alarm"
        )
        self.posj_client = node.create_client(
            GetCurrentPosj, f"/{ROBOT_ID}/aux_control/get_current_posj"
        )
    
    def log(self, msg: str):
        """타임스탬프와 함께 로그 출력"""
        now = datetime.now(self.kst).strftime("%H:%M:%S")
        self.node.get_logger().info(f"[{now}] {msg}")
    
    def _wait_for(self, client, name: str, timeout: float = 3.0) -> bool:
        """서비스 준비 대기"""
        if not client.wait_for_service(timeout_sec=timeout):
            self.log(f"[{name}] 서비스를 사용할 수 없음")
            return False
        return True
    
    def _call(self, client, req, name: str, timeout: float = 3.0):
        """서비스 동기 호출"""
        future = client.call_async(req)
        rclpy.spin_until_future_complete(self.node, future, timeout_sec=timeout)
        if future.result() is None:
            self.log(f"[{name}] 응답 없음")
            return None
        return future.result()
    
    # ========================================
    # 상태 조회 메서드
    # ========================================
    
    def get_state(self) -> int | None:
        """
        현재 로봇 상태 조회
        
        Returns:
            상태 코드 (1=STANDBY, 5=SAFE_STOP 등) 또는 None
        
        사용 서비스: /dsr01/system/get_robot_state
        """
        if not self._wait_for(self.state_client, "GetRobotState", timeout=1.0):
            return None
        
        req = GetRobotState.Request()
        res = self._call(self.state_client, req, "GetRobotState", timeout=1.0)
        
        if res and res.success:
            return res.robot_state
        return None
    
    def get_state_name(self) -> str:
        """현재 상태를 이름으로 반환"""
        state = self.get_state()
        return state_name(state) if state is not None else "UNKNOWN"
    
    def is_safe_stop(self, state: int = None) -> bool:
        """
        SAFE_STOP 상태인지 확인 (충돌 감지됨 - 노란 링)
        
        Args:
            state: 확인할 상태 코드 (None이면 현재 상태 조회)
        """
        if state is None:
            state = self.get_state()
        return state in (5, 9)  # SAFE_STOP or SAFE_STOP2
    
    def is_safe_off(self, state: int = None) -> bool:
        """
        SAFE_OFF 상태인지 확인 (서보 OFF)
        
        Args:
            state: 확인할 상태 코드 (None이면 현재 상태 조회)
        """
        if state is None:
            state = self.get_state()
        return state in (3, 10)  # SAFE_OFF or SAFE_OFF2
    
    def is_standby(self, state: int = None) -> bool:
        """
        STANDBY 상태인지 확인 (정상 대기)
        
        Args:
            state: 확인할 상태 코드 (None이면 현재 상태 조회)
        """
        if state is None:
            state = self.get_state()
        return state == 1
    
    # ========================================
    # 위치/알람 조회
    # ========================================
    
    def get_current_position(self) -> list | None:
        """
        현재 관절 위치 조회
        
        Returns:
            [J1, J2, J3, J4, J5, J6] 각도 리스트 또는 None
        
        사용 서비스: /dsr01/aux_control/get_current_posj
        """
        if not self._wait_for(self.posj_client, "GetCurrentPosj", timeout=1.0):
            return None
        
        req = GetCurrentPosj.Request()
        res = self._call(self.posj_client, req, "GetCurrentPosj", timeout=1.0)
        
        if res and res.success:
            return list(res.pos)
        return None
    
    def get_last_alarm(self):
        """
        마지막 알람 조회
        
        사용 서비스: /dsr01/system/get_last_alarm
        """
        if not self._wait_for(self.alarm_client, "GetLastAlarm", timeout=1.0):
            return None
        
        req = GetLastAlarm.Request()
        res = self._call(self.alarm_client, req, "GetLastAlarm", timeout=1.0)
        
        if res:
            self.log(f"알람 - 레벨: {res.log_alarm.level}, 메시지: {res.log_alarm.msg}")
            return res.log_alarm
        return None
    
    def print_status(self):
        """현재 상태 및 위치 출력"""
        state = self.get_state()
        pos = self.get_current_position()
        
        self.log(f"상태: {state_name(state) if state else 'UNKNOWN'} ({state})")
        if pos:
            self.log(f"위치: J1={pos[0]:.1f}°, J2={pos[1]:.1f}°, J3={pos[2]:.1f}°, "
                    f"J4={pos[3]:.1f}°, J5={pos[4]:.1f}°, J6={pos[5]:.1f}°")
