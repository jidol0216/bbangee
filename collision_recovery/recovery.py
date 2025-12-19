"""
recovery.py - 충돌 복구 시퀀스
===============================

SAFE_STOP(충돌) 상태에서 STANDBY(정상)로 복구하는 시퀀스를 관리합니다.

복구 시퀀스:
    1. SAFE_STOP 리셋 (set_robot_control = 2)
    2. RECOVERY 모드 진입 (set_safety_mode: ENTER)
    3. Jog로 충돌 위치 이탈 (jog: Z축 위로)
    4. RECOVERY 완료 (set_safety_mode: COMPLETE)
    5. RECOVERY 모드 해제 (set_robot_control = 7)
    6. Servo ON (set_robot_control = 3)

사용 서비스:
    - /dsr01/system/set_robot_control (SetRobotControl)
    - /dsr01/system/set_safety_mode (SetSafetyMode)
    - /dsr01/motion/jog (Jog)
"""

import rclpy
from rclpy.node import Node
import time
from datetime import timedelta, timezone, datetime

from dsr_msgs2.srv import SetRobotControl, SetSafetyMode, Jog

from .config import (
    ROBOT_ID, 
    CONTROL_COMMANDS, 
    SAFETY_MODE, 
    SAFETY_EVENT,
    JOG_AXIS,
    JOG_REFERENCE,
)
from .robot_state import RobotStateManager, state_name


class RecoveryManager:
    """
    충돌 복구 관리 클래스
    
    주요 기능:
        - SAFE_STOP 리셋
        - RECOVERY 모드 진입/완료/해제
        - Jog로 충돌 위치 이탈
        - Servo ON
        - 전체 자동 복구 시퀀스
    """
    
    def __init__(self, node: Node, state_manager: RobotStateManager):
        """
        Args:
            node: ROS2 노드 인스턴스
            state_manager: RobotStateManager 인스턴스
        """
        self.node = node
        self.state = state_manager
        self.kst = timezone(timedelta(hours=9))
        
        # 서비스 클라이언트 생성
        self.control_client = node.create_client(
            SetRobotControl, f"/{ROBOT_ID}/system/set_robot_control"
        )
        self.safety_client = node.create_client(
            SetSafetyMode, f"/{ROBOT_ID}/system/set_safety_mode"
        )
        self.jog_client = node.create_client(
            Jog, f"/{ROBOT_ID}/motion/jog"
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
    # 개별 복구 단계
    # ========================================
    
    def reset_safe_stop(self) -> bool:
        """
        Step 1: SAFE_STOP 상태 리셋
        
        서비스: /dsr01/system/set_robot_control
        파라미터: robot_control = 2 (CONTROL_RESET_SAFE_STOP)
        """
        self.log("SAFE_STOP 리셋 시도...")
        
        if not self._wait_for(self.control_client, "SetRobotControl"):
            return False
        
        req = SetRobotControl.Request()
        req.robot_control = CONTROL_COMMANDS["RESET_SAFE_STOP"]  # 2
        
        res = self._call(self.control_client, req, "SetRobotControl(RESET_SAFE_STOP)")
        if res and res.success:
            self.log("✓ SAFE_STOP 리셋 성공")
            return True
        else:
            self.log("✗ SAFE_STOP 리셋 실패")
            return False
    
    def enter_recovery_mode(self) -> bool:
        """
        Step 2: RECOVERY 모드 진입
        
        서비스: /dsr01/system/set_safety_mode
        파라미터: safety_mode=2, safety_event=0 (ENTER)
        """
        self.log("RECOVERY 모드 진입 중...")
        
        if not self._wait_for(self.safety_client, "SetSafetyMode"):
            return False
        
        req = SetSafetyMode.Request()
        req.safety_mode = SAFETY_MODE["RECOVERY"]    # 2
        req.safety_event = SAFETY_EVENT["ENTER"]     # 0
        
        res = self._call(self.safety_client, req, "SetSafetyMode(ENTER)")
        if res and res.success:
            self.log("✓ RECOVERY ENTER 성공")
            return True
        else:
            self.log("✗ RECOVERY ENTER 실패")
            return False
    
    def jog_up(self, duration: float = 1.5) -> bool:
        """
        Step 3: Jog로 Z축 위로 이동 (충돌 위치에서 벗어나기)
        
        서비스: /dsr01/motion/jog
        파라미터: jog_axis=8 (Z축), speed=20.0 (위로)
        
        Args:
            duration: Jog 이동 시간 (초)
        """
        self.log("Jog로 Z축 위로 이동 중...")
        
        if not self._wait_for(self.jog_client, "Jog", timeout=1.0):
            self.log("⚠️ Jog 서비스 없음")
            return False
        
        # Z축 위로 이동
        req = Jog.Request()
        req.jog_axis = JOG_AXIS["Z"]           # 8
        req.move_reference = JOG_REFERENCE["BASE"]  # 0
        req.speed = 20.0                       # 20% 속도로 위로
        
        res = self._call(self.jog_client, req, "Jog(Z+)")
        if res and res.success:
            self.log(f"✓ Jog 시작 - {duration}초 동안 위로 이동")
            time.sleep(duration)
            
            # Jog 정지
            req_stop = Jog.Request()
            req_stop.jog_axis = JOG_AXIS["Z"]
            req_stop.move_reference = JOG_REFERENCE["BASE"]
            req_stop.speed = 0.0  # 정지
            self._call(self.jog_client, req_stop, "Jog(STOP)")
            self.log("✓ Jog 정지")
            return True
        else:
            self.log("⚠️ Jog 실패")
            return False
    
    def complete_recovery(self) -> bool:
        """
        Step 4: RECOVERY 완료
        
        서비스: /dsr01/system/set_safety_mode
        파라미터: safety_mode=2, safety_event=2 (COMPLETE)
        """
        self.log("RECOVERY 완료 처리 중...")
        
        if not self._wait_for(self.safety_client, "SetSafetyMode"):
            return False
        
        req = SetSafetyMode.Request()
        req.safety_mode = SAFETY_MODE["RECOVERY"]      # 2
        req.safety_event = SAFETY_EVENT["COMPLETE"]    # 2
        
        res = self._call(self.safety_client, req, "SetSafetyMode(COMPLETE)")
        if res and res.success:
            self.log("✓ RECOVERY 완료")
            return True
        else:
            self.log("✗ RECOVERY 완료 실패")
            return False
    
    def exit_recovery_mode(self) -> bool:
        """
        Step 5: RECOVERY 모드 해제
        
        서비스: /dsr01/system/set_robot_control
        파라미터: robot_control = 7 (CONTROL_RESET_RECOVERY)
        """
        self.log("RECOVERY 모드 해제 중...")
        
        if not self._wait_for(self.control_client, "SetRobotControl"):
            return False
        
        req = SetRobotControl.Request()
        req.robot_control = CONTROL_COMMANDS["RESET_RECOVERY"]  # 7
        
        res = self._call(self.control_client, req, "SetRobotControl(RESET_RECOVERY)")
        if res and res.success:
            self.log("✓ RECOVERY 모드 해제 성공")
            return True
        else:
            self.log("✗ RECOVERY 모드 해제 실패")
            return False
    
    def servo_on(self) -> bool:
        """
        Step 6: Servo ON (SAFE_OFF → STANDBY)
        
        서비스: /dsr01/system/set_robot_control
        파라미터: robot_control = 3 (CONTROL_RESET_SAFE_OFF)
        """
        self.log("Servo ON 시도...")
        
        if not self._wait_for(self.control_client, "SetRobotControl"):
            return False
        
        req = SetRobotControl.Request()
        req.robot_control = CONTROL_COMMANDS["SERVO_ON"]  # 3
        
        res = self._call(self.control_client, req, "SetRobotControl(SERVO_ON)")
        if res and res.success:
            self.log("✓ Servo ON 성공")
            return True
        else:
            self.log("✗ Servo ON 실패")
            return False
    
    # ========================================
    # 전체 자동 복구 시퀀스
    # ========================================
    
    def auto_recovery(self, max_attempts: int = 5) -> bool:
        """
        전체 자동 복구 시퀀스 실행
        
        복구 흐름:
            SAFE_STOP → 리셋 → RECOVERY ENTER → Jog 위로 
            → RECOVERY COMPLETE → 해제 → Servo ON → STANDBY
        
        Args:
            max_attempts: 최대 시도 횟수
            
        Returns:
            복구 성공 여부
        """
        self.log("=" * 40)
        self.log("자동 복구 시퀀스 시작")
        self.log("=" * 40)
        
        for attempt in range(max_attempts):
            current_state = self.state.get_state()
            if current_state is None:
                self.log("로봇 상태를 확인할 수 없음")
                return False
            
            self.log(f"[시도 {attempt + 1}/{max_attempts}] 상태: {state_name(current_state)}")
            
            # 이미 STANDBY면 성공
            if self.state.is_standby(current_state):
                self.log("✅ 이미 STANDBY 상태!")
                return True
            
            # 1. SAFE_STOP 리셋
            if self.state.is_safe_stop(current_state):
                self.log(">>> 노란 링(SAFE_STOP) 감지!")
                if not self.reset_safe_stop():
                    time.sleep(0.5)
                    continue
                time.sleep(0.5)
            
            # 2. RECOVERY 모드 진입
            self.enter_recovery_mode()
            time.sleep(0.3)
            
            # 3. Jog로 위로 이동 (충돌 위치 이탈)
            self.jog_up(duration=1.5)
            time.sleep(0.3)
            
            # 4. RECOVERY 완료
            self.complete_recovery()
            time.sleep(0.5)
            
            # 5. RECOVERY 모드 해제
            self.exit_recovery_mode()
            time.sleep(0.5)
            
            # 6. Servo ON (STANDBY가 아니면 시도)
            current_state = self.state.get_state()
            self.log(f"RECOVERY 해제 후 상태: {state_name(current_state)} ({current_state})")
            
            if current_state != 1:  # STANDBY가 아니면
                self.log("Servo ON 시도...")
                self.servo_on()
                time.sleep(1.0)
            
            # 결과 확인
            current_state = self.state.get_state()
            if self.state.is_standby(current_state):
                self.log("✅ 복구 성공! STANDBY 상태")
                return True
            
            self.log(f"아직 복구 안됨, 재시도... (상태: {state_name(current_state)})")
            time.sleep(0.5)
        
        # 최종 상태 확인
        final_state = self.state.get_state()
        self.log(f"최종 상태: {state_name(final_state)}")
        self.log("=" * 40)
        
        if self.state.is_standby(final_state):
            return True
        else:
            self.log(f"⚠️ 복구 실패: {state_name(final_state)}")
            return False
