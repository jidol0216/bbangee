"""
motion.py - 모션 제어
======================

로봇 이동 관련 기능을 제공합니다.

주요 기능:
    - 홈 위치 이동 (move_joint)
    - 충돌 테스트용 이동 (바닥 방향)
    - 로봇 모드 설정

사용 서비스:
    - /dsr01/motion/move_joint (MoveJoint)
    - /dsr01/system/set_robot_mode (SetRobotMode)
"""

import rclpy
from rclpy.node import Node
import time
from datetime import timedelta, timezone, datetime

from dsr_msgs2.srv import MoveJoint, SetRobotMode

from .config import ROBOT_ID, HOME_POSITION


class MotionController:
    """
    모션 제어 클래스
    
    주요 기능:
        - 로봇 모드 설정 (자동 모드)
        - 홈 위치 이동
        - 충돌 테스트용 이동
    """
    
    def __init__(self, node: Node):
        """
        Args:
            node: ROS2 노드 인스턴스
        """
        self.node = node
        self.kst = timezone(timedelta(hours=9))
        
        # 서비스 클라이언트 생성
        self.move_joint_client = node.create_client(
            MoveJoint, f"/{ROBOT_ID}/motion/move_joint"
        )
        self.mode_client = node.create_client(
            SetRobotMode, f"/{ROBOT_ID}/system/set_robot_mode"
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
    # 모드 설정
    # ========================================
    
    def set_autonomous_mode(self) -> bool:
        """
        로봇을 자동 모드로 설정
        
        서비스: /dsr01/system/set_robot_mode
        파라미터: robot_mode = 1 (AUTONOMOUS)
        """
        if not self._wait_for(self.mode_client, "SetRobotMode"):
            return False
        
        req = SetRobotMode.Request()
        req.robot_mode = 1  # ROBOT_MODE_AUTONOMOUS
        
        res = self._call(self.mode_client, req, "SetRobotMode")
        if res and res.success:
            self.log("✓ 자동 모드 설정 완료")
            return True
        
        self.log("✗ 자동 모드 설정 실패")
        return False
    
    # ========================================
    # 이동 명령
    # ========================================
    
    def move_to_home(self) -> bool:
        """
        홈 위치로 이동
        
        서비스: /dsr01/motion/move_joint
        목표: HOME_POSITION [0, 0, 90, 0, 90, 0]
        """
        self.log("홈 위치로 이동 중...")
        
        # 자동 모드 설정
        if not self.set_autonomous_mode():
            return False
        time.sleep(0.3)
        
        # move_joint 서비스 호출
        if not self._wait_for(self.move_joint_client, "MoveJoint"):
            return False
        
        req = MoveJoint.Request()
        req.pos = HOME_POSITION  # [0.0, 0.0, 90.0, 0.0, 90.0, 0.0]
        req.vel = 30.0           # 속도 30%
        req.acc = 30.0           # 가속도 30%
        req.time = 0.0
        req.radius = 0.0
        req.mode = 0             # absolute
        req.blend_type = 0
        req.sync_type = 0        # sync (동기)
        
        self.log(f"목표 위치: {HOME_POSITION}")
        res = self._call(self.move_joint_client, req, "MoveJoint", timeout=30.0)
        
        if res and res.success:
            self.log("✓ 홈 위치 도착 완료!")
            return True
        else:
            self.log("✗ 홈 이동 실패")
            return False
    
    def move_down_slow(self) -> bool:
        """
        충돌 테스트: 바닥 방향으로 천천히 이동
        
        J2=60°, J3=30° → 팔이 아래로 많이 숙여짐
        속도 10%로 천천히 이동
        """
        self.log("⚠️  충돌 테스트 - 바닥 방향으로 천천히 이동...")
        
        if not self.set_autonomous_mode():
            return False
        time.sleep(0.3)
        
        if not self._wait_for(self.move_joint_client, "MoveJoint"):
            return False
        
        req = MoveJoint.Request()
        req.pos = [0.0, 60.0, 30.0, 0.0, 90.0, 0.0]  # 바닥 방향
        req.vel = 10.0   # 천천히
        req.acc = 10.0
        req.time = 0.0
        req.radius = 0.0
        req.mode = 0
        req.blend_type = 0
        req.sync_type = 1  # 비동기 (충돌 감지를 위해)
        
        self.log("바닥 방향으로 천천히 이동 (J2=60°, J3=30°)")
        self.log("⚠️  바닥에 닿으면 SAFE_STOP 발생!")
        
        res = self._call(self.move_joint_client, req, "MoveJoint", timeout=5.0)
        
        if res and res.success:
            self.log("모션 명령 전송 완료")
            return True
        return False
    
    def move_down_fast(self) -> bool:
        """
        충돌 테스트: 바닥 방향으로 빠르게 이동
        
        J2=45°, J3=45° → 팔이 아래로 숙여짐
        속도 20%
        """
        self.log("⚠️  충돌 테스트 - 바닥 방향으로 빠르게 이동...")
        
        if not self.set_autonomous_mode():
            return False
        time.sleep(0.3)
        
        if not self._wait_for(self.move_joint_client, "MoveJoint"):
            return False
        
        req = MoveJoint.Request()
        req.pos = [0.0, 45.0, 45.0, 0.0, 90.0, 0.0]  # 바닥 방향
        req.vel = 20.0
        req.acc = 20.0
        req.time = 0.0
        req.radius = 0.0
        req.mode = 0
        req.blend_type = 0
        req.sync_type = 1  # 비동기
        
        self.log("바닥 방향으로 빠르게 이동 (J2=45°, J3=45°)")
        self.log("⚠️  바닥에 닿으면 SAFE_STOP 발생!")
        
        res = self._call(self.move_joint_client, req, "MoveJoint", timeout=5.0)
        
        if res and res.success:
            self.log("모션 명령 전송 완료")
            return True
        return False
