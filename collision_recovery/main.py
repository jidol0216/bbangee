#!/usr/bin/env python3
"""
main.py - 충돌 복구 데모 진입점
================================

사용법:
    cd /home/taesla/cobot1_ws
    source install/setup.bash
    python3 -m collision_recovery.main

또는:
    python3 /path/to/collision_recovery/main.py
"""

import rclpy
from rclpy.node import Node
import time
import sys
import os

# 직접 실행 시 패키지 경로 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collision_recovery.config import ROBOT_ID, state_name
from collision_recovery.robot_state import RobotStateManager
from collision_recovery.recovery import RecoveryManager
from collision_recovery.motion import MotionController


class CollisionRecoveryNode(Node):
    """
    충돌 복구 데모 노드
    
    구성 요소:
        - RobotStateManager: 상태 조회
        - RecoveryManager: 복구 시퀀스
        - MotionController: 모션 제어
    """
    
    def __init__(self):
        super().__init__("collision_recovery_demo", namespace=ROBOT_ID)
        
        # 매니저 초기화
        self.state = RobotStateManager(self)
        self.recovery = RecoveryManager(self, self.state)
        self.motion = MotionController(self)
        
        self.get_logger().info("충돌 복구 데모 노드 초기화 완료")
    
    def log(self, msg: str):
        """로그 출력 (RobotStateManager의 log 사용)"""
        self.state.log(msg)


def run_demo(node: CollisionRecoveryNode, choice: str):
    """데모 실행"""
    
    if choice == '1':
        # 현재 상태 확인 및 복구
        node.log("=" * 50)
        node.log("현재 상태 확인 및 복구")
        node.log("=" * 50)
        
        current = node.state.get_state()
        node.log(f"현재 상태: {state_name(current)}")
        
        if node.state.is_safe_stop(current):
            node.log(">>> SAFE_STOP 감지! 복구 시작...")
            if node.recovery.auto_recovery():
                node.log("복구 성공! 홈 위치로 이동")
                node.motion.move_to_home()
        else:
            node.log("정상 상태 - 홈 위치로 이동")
            node.motion.move_to_home()
    
    elif choice == '2':
        # 충돌 테스트 - 빠른 이동
        node.log("=" * 50)
        node.log("충돌 테스트 - 빠른 이동")
        node.log("=" * 50)
        
        node.motion.move_down_fast()
        
        # 충돌 대기
        node.log("충돌 대기 중... (최대 30초)")
        for i in range(60):
            time.sleep(0.5)
            if node.state.is_safe_stop():
                node.log(">>> 충돌 감지! SAFE_STOP")
                break
        
        # 복구
        if node.state.is_safe_stop():
            if node.recovery.auto_recovery():
                node.motion.move_to_home()
    
    elif choice == '3':
        # 충돌 테스트 - 천천히 이동
        node.log("=" * 50)
        node.log("충돌 테스트 - 천천히 이동")
        node.log("=" * 50)
        
        node.motion.move_down_slow()
        
        # 충돌 대기
        node.log("충돌 대기 중... (최대 30초)")
        for i in range(60):
            time.sleep(0.5)
            if node.state.is_safe_stop():
                node.log(">>> 충돌 감지! SAFE_STOP")
                break
        
        # 복구
        if node.state.is_safe_stop():
            if node.recovery.auto_recovery():
                node.motion.move_to_home()
    
    elif choice == '4':
        # 상태 모니터링
        node.log("=" * 50)
        node.log("상태 모니터링 모드")
        node.log("로봇을 손으로 밀어서 충돌을 유발하세요!")
        node.log("=" * 50)
        
        while True:
            current = node.state.get_state()
            if current is None:
                node.log("연결 끊김!")
                break
            
            node.log(f"상태: {state_name(current)}")
            
            if node.state.is_safe_stop(current):
                node.log(">>> SAFE_STOP 감지! 자동 복구 시작...")
                if node.recovery.auto_recovery():
                    node.motion.move_to_home()
                break
            
            time.sleep(1)


def main(args=None):
    rclpy.init(args=args)
    
    node = CollisionRecoveryNode()
    
    try:
        print("\n" + "=" * 60)
        print("  두산 로봇 충돌 감지 및 자동 복구 데모")
        print("  (모듈화 버전)")
        print("=" * 60)
        print("\n옵션을 선택하세요:")
        print("  1. 현재 상태 확인 및 복구")
        print("  2. 충돌 테스트 - 빠른 이동 (J2=45°, J3=45°)")
        print("  3. 충돌 테스트 - 천천히 이동 (J2=60°, J3=30°) ★추천")
        print("  4. 상태 모니터링 모드 (수동 충돌)")
        print("  q. 종료")
        print()
        
        choice = input("선택 (1/2/3/4/q): ").strip()
        
        if choice in ['1', '2', '3', '4']:
            if choice in ['2', '3']:
                print("\n⚠️  주의: 로봇이 움직입니다!")
                print("안전 확인 후 Enter를 누르세요...")
                input()
            run_demo(node, choice)
        elif choice == 'q':
            print("종료합니다.")
        else:
            print("잘못된 선택입니다.")
        
        node.log("=" * 50)
        node.log("데모 완료!")
        node.log("=" * 50)
        
    except KeyboardInterrupt:
        node.log("사용자에 의해 중단됨")
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
