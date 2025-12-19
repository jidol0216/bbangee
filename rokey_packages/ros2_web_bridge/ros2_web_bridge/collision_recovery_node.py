#!/usr/bin/env python3
"""
Collision Recovery Web Bridge Node
- 웹에서 받은 명령으로 충돌 복구 실행
- /tmp 파일 기반 통신
- MultiThreadedExecutor 사용하여 서비스 콜백 내 동기 호출 지원
"""

import rclpy
from rclpy.node import Node
from rclpy.executors import MultiThreadedExecutor
from rclpy.callback_groups import ReentrantCallbackGroup, MutuallyExclusiveCallbackGroup
import json
import os
import time
from datetime import timedelta, timezone, datetime
import threading

# Doosan 서비스 임포트
try:
    from dsr_msgs2.srv import (
        GetRobotState, 
        SetRobotControl, 
        SetSafetyMode, 
        SetRobotMode,
        MoveJoint, 
        Jog
    )
    HAS_DSR = True
except ImportError:
    HAS_DSR = False
    print("[WARN] dsr_msgs2 not found. Collision recovery disabled.")


# 파일 경로
STATE_FILE = '/tmp/collision_recovery_state.json'
COMMAND_FILE = '/tmp/collision_recovery_command.json'

# 로봇 설정
ROBOT_ID = "dsr01"
HOME_POSITION = [0.0, -30.0, 100.0, 70.0, 90.0, 0.0]  # 카메라 높이 올림

# 상태 코드
STATE_CODES = {
    0: "INITIALIZING", 1: "STANDBY", 2: "MOVING", 3: "SAFE_OFF",
    4: "TEACHING", 5: "SAFE_STOP", 6: "EMERGENCY_STOP", 7: "HOMING",
    8: "RECOVERY", 9: "SAFE_STOP2", 10: "SAFE_OFF2"
}

# 제어 명령
CONTROL_RESET_SAFE_STOP = 2
CONTROL_SERVO_ON = 3
CONTROL_RESET_RECOVERY = 7


class CollisionRecoveryWebNode(Node):
    def __init__(self):
        super().__init__('collision_recovery_web')
        
        self.kst = timezone(timedelta(hours=9))
        self.logs = []
        self.is_recovering = False
        self.is_monitoring = False
        self.last_command_time = 0
        self.executor = None  # Will be set from main()
        
        # Callback groups for concurrent execution
        self.service_cb_group = ReentrantCallbackGroup()
        self.timer_cb_group = MutuallyExclusiveCallbackGroup()
        
        # 상태 초기화
        self.state = {
            'robot_state': 'UNKNOWN',
            'robot_state_code': -1,
            'is_safe_stop': False,
            'is_recovering': False,
            'last_action': '',
            'log': [],
            'timestamp': 0
        }
        
        if HAS_DSR:
            # 서비스 클라이언트 생성 (with callback group)
            self.state_client = self.create_client(
                GetRobotState, f"/{ROBOT_ID}/system/get_robot_state",
                callback_group=self.service_cb_group
            )
            self.control_client = self.create_client(
                SetRobotControl, f"/{ROBOT_ID}/system/set_robot_control",
                callback_group=self.service_cb_group
            )
            self.safety_client = self.create_client(
                SetSafetyMode, f"/{ROBOT_ID}/system/set_safety_mode",
                callback_group=self.service_cb_group
            )
            self.mode_client = self.create_client(
                SetRobotMode, f"/{ROBOT_ID}/system/set_robot_mode",
                callback_group=self.service_cb_group
            )
            self.move_joint_client = self.create_client(
                MoveJoint, f"/{ROBOT_ID}/motion/move_joint",
                callback_group=self.service_cb_group
            )
            self.jog_client = self.create_client(
                Jog, f"/{ROBOT_ID}/motion/jog",
                callback_group=self.service_cb_group
            )
        
        # 타이머: 상태 업데이트 및 명령 확인 (separate callback group)
        self.create_timer(0.5, self.update_loop, callback_group=self.timer_cb_group)
        
        self._log("충돌 복구 웹 노드 시작")
        self.get_logger().info("Collision Recovery Web Node started")
    
    def _log(self, msg: str):
        """로그 추가"""
        now = datetime.now(self.kst).strftime("%H:%M:%S")
        log_entry = f"[{now}] {msg}"
        self.logs.append(log_entry)
        # 최근 20개만 유지
        if len(self.logs) > 20:
            self.logs = self.logs[-20:]
        self.get_logger().info(msg)
    
    def _write_state(self):
        """상태 파일 작성"""
        self.state['log'] = self.logs.copy()
        self.state['timestamp'] = time.time()
        self.state['is_recovering'] = self.is_recovering
        try:
            with open(STATE_FILE, 'w') as f:
                json.dump(self.state, f)
        except Exception as e:
            self.get_logger().error(f"State write error: {e}")
    
    def _read_command(self) -> dict | None:
        """명령 파일 읽기"""
        if not os.path.exists(COMMAND_FILE):
            return None
        try:
            with open(COMMAND_FILE, 'r') as f:
                cmd = json.load(f)
            # 이미 처리한 명령이면 스킵
            if cmd.get('timestamp', 0) <= self.last_command_time:
                return None
            self.last_command_time = cmd.get('timestamp', 0)
            # 파일 삭제
            os.remove(COMMAND_FILE)
            return cmd
        except:
            return None
    
    def _wait_for(self, client, timeout: float = 5.0) -> bool:
        """서비스 대기"""
        return client.wait_for_service(timeout_sec=timeout)
    
    def _call_sync(self, client, req, timeout: float = 10.0):
        """서비스 동기 호출 (MultiThreadedExecutor 사용 시)"""
        if not client.service_is_ready():
            self.get_logger().warn(f"Service not ready")
            return None
        
        future = client.call_async(req)
        
        # Wait for result with timeout
        start_time = time.time()
        while not future.done():
            if time.time() - start_time > timeout:
                self.get_logger().warn(f"Service call timeout after {timeout}s")
                return None
            time.sleep(0.05)  # Small sleep to avoid busy waiting
        
        return future.result()
    
    # ========================================
    # 상태 조회
    # ========================================
    
    def get_robot_state(self) -> int | None:
        """로봇 상태 조회"""
        if not HAS_DSR:
            self._log("⚠️ dsr_msgs2 없음")
            return None
        if not self._wait_for(self.state_client, 3.0):
            self._log("⚠️ get_robot_state 서비스 없음 - bringup 실행 확인")
            return None
        
        req = GetRobotState.Request()
        res = self._call_sync(self.state_client, req, 3.0)
        if res and res.success:
            return res.robot_state
        return None
    
    def is_safe_stop(self, state: int) -> bool:
        """SAFE_STOP 상태인지"""
        return state in (5, 9)
    
    def is_standby(self, state: int) -> bool:
        """STANDBY 상태인지"""
        return state == 1
    
    # ========================================
    # 복구 동작
    # ========================================
    
    def reset_safe_stop(self) -> bool:
        """SAFE_STOP 리셋"""
        if not HAS_DSR or not self._wait_for(self.control_client):
            return False
        req = SetRobotControl.Request()
        req.robot_control = CONTROL_RESET_SAFE_STOP
        res = self._call_sync(self.control_client, req)
        return res and res.success
    
    def enter_recovery_mode(self) -> bool:
        """RECOVERY 모드 진입"""
        if not HAS_DSR or not self._wait_for(self.safety_client):
            return False
        req = SetSafetyMode.Request()
        req.safety_mode = 2  # RECOVERY
        req.safety_event = 0  # ENTER
        res = self._call_sync(self.safety_client, req)
        return res and res.success
    
    def jog_up(self, duration: float = 2.5) -> bool:
        """Z축 위로 Jog - 충돌 위치에서 벗어나기"""
        self._log("Jog 서비스 확인 중...")
        if not HAS_DSR or not self._wait_for(self.jog_client, 1.0):
            self._log("⚠️ Jog 서비스 없음")
            return False
        
        # Jog 시작 요청
        req = Jog.Request()
        req.jog_axis = 8  # Z축
        req.move_reference = 0  # BASE 좌표계
        req.speed = 30.0  # 30% 속도로 위로
        
        self._log(f"Jog 시작: Z축 위로 {duration}초, 속도 30%...")
        res = self._call_sync(self.jog_client, req)
        if res and res.success:
            self._log("✓ Jog 명령 전송 성공")
            time.sleep(duration)
            
            # 정지 - 새 요청 객체 사용
            stop_req = Jog.Request()
            stop_req.jog_axis = 8  # Z축
            stop_req.move_reference = 0  # BASE
            stop_req.speed = 0.0  # 정지
            
            stop_res = self._call_sync(self.jog_client, stop_req)
            if stop_res and stop_res.success:
                self._log("✓ Jog 정지")
            else:
                self._log("⚠️ Jog 정지 실패 (자연 정지 대기)")
                time.sleep(0.5)  # 자연 정지 대기
            return True
        else:
            self._log("⚠️ Jog 명령 실패 - RECOVERY 모드 확인 필요")
            return False
    
    def complete_recovery(self) -> bool:
        """RECOVERY 완료"""
        if not HAS_DSR or not self._wait_for(self.safety_client):
            return False
        req = SetSafetyMode.Request()
        req.safety_mode = 2  # RECOVERY
        req.safety_event = 2  # COMPLETE
        res = self._call_sync(self.safety_client, req)
        return res and res.success
    
    def exit_recovery_mode(self) -> bool:
        """RECOVERY 모드 해제"""
        if not HAS_DSR or not self._wait_for(self.control_client):
            return False
        req = SetRobotControl.Request()
        req.robot_control = CONTROL_RESET_RECOVERY
        res = self._call_sync(self.control_client, req)
        return res and res.success
    
    def servo_on(self) -> bool:
        """Servo ON"""
        if not HAS_DSR or not self._wait_for(self.control_client, 5.0):
            self._log("⚠️ set_robot_control 서비스 없음")
            return False
        req = SetRobotControl.Request()
        req.robot_control = CONTROL_SERVO_ON
        res = self._call_sync(self.control_client, req)
        return res and res.success
    
    def set_autonomous_mode(self) -> bool:
        """자동 모드 설정"""
        if not HAS_DSR or not self._wait_for(self.mode_client, 5.0):
            self._log("⚠️ set_robot_mode 서비스 없음")
            return False
        req = SetRobotMode.Request()
        req.robot_mode = 1
        res = self._call_sync(self.mode_client, req)
        if res and res.success:
            self._log("✓ 자동 모드 설정됨")
            return True
        self._log("✗ 자동 모드 설정 실패")
        return False
    
    # ========================================
    # 모션
    # ========================================
    
    def move_home(self) -> bool:
        """홈 위치 이동"""
        self._log("홈 위치로 이동 중...")
        if not self.set_autonomous_mode():
            self._log("자동 모드 설정 실패")
            return False
        
        if not HAS_DSR or not self._wait_for(self.move_joint_client, 5.0):
            self._log("⚠️ move_joint 서비스 없음")
            return False
        
        req = MoveJoint.Request()
        req.pos = HOME_POSITION
        req.vel = 30.0
        req.acc = 30.0
        req.time = 0.0
        req.radius = 0.0
        req.mode = 0
        req.blend_type = 0
        req.sync_type = 1  # 비동기 - 명령만 전송
        
        res = self._call_sync(self.move_joint_client, req, 5.0)
        if res and res.success:
            self._log("✓ 홈 이동 명령 전송")
            # 모션 완료 대기 (MOVING → STANDBY)
            for i in range(100):  # 최대 10초 대기
                time.sleep(0.1)
                state = self.get_robot_state()
                if state == 1:  # STANDBY
                    self._log("✓ 홈 위치 도착")
                    return True
                elif state in (5, 9):  # SAFE_STOP - 충돌 발생
                    self._log("⚠️ 홈 이동 중 충돌 발생")
                    return False
            self._log("⚠️ 홈 이동 타임아웃")
            return False
        self._log("✗ 홈 이동 실패")
        return False
    
    def move_down(self, fast: bool = False) -> bool:
        """바닥 방향 이동 (충돌 테스트)"""
        if fast:
            self._log("⚠️ 충돌 테스트 - 빠른 이동")
            pos = [0.0, 45.0, 45.0, 0.0, 90.0, 0.0]
            vel = 20.0
        else:
            self._log("⚠️ 충돌 테스트 - 느린 이동")
            pos = [0.0, 60.0, 30.0, 0.0, 90.0, 0.0]
            vel = 10.0
        
        if not self.set_autonomous_mode():
            self._log("자동 모드 설정 실패")
            return False
        
        if not HAS_DSR or not self._wait_for(self.move_joint_client, 5.0):
            self._log("⚠️ move_joint 서비스 없음")
            return False
        
        req = MoveJoint.Request()
        req.pos = pos
        req.vel = vel
        req.acc = vel
        req.time = 0.0
        req.radius = 0.0
        req.mode = 0
        req.blend_type = 0
        req.sync_type = 1  # 비동기
        
        res = self._call_sync(self.move_joint_client, req, 10.0)
        if res and res.success:
            self._log("✓ 모션 명령 전송됨")
            return True
        self._log("✗ 모션 명령 실패")
        return False
    
    def _start_collision_test(self, fast: bool = False):
        """충돌 테스트 시작 - 충돌 감지 후 자동 복구 + 홈 복귀"""
        import threading
        
        def collision_test_thread():
            # 1. 아래로 이동 시작
            if not self.move_down(fast=fast):
                return
            
            # 2. 충돌 대기 (최대 30초)
            self._log("충돌 대기 중... (최대 30초)")
            for i in range(60):  # 0.5초 * 60 = 30초
                time.sleep(0.5)
                state = self.get_robot_state()
                if state is not None and self.is_safe_stop(state):
                    self._log(">>> 충돌 감지! 자동 복구 시작...")
                    break
            else:
                self._log("충돌 없음 - 테스트 종료")
                return
            
            # 3. 자동 복구
            if self.auto_recovery():
                self._log("복구 성공! 2초 후 홈으로 이동...")
                time.sleep(2.0)  # 안정화 대기 시간 증가
                
                # 홈 이동 (최대 3번 재시도)
                for retry in range(3):
                    if self.move_home():
                        self._log("✅ 충돌 테스트 완료!")
                        return
                    self._log(f"홈 이동 재시도... ({retry+1}/3)")
                    time.sleep(1.0)
                
                self._log("⚠️ 홈 이동 실패 - 수동 조작 필요")
            else:
                self._log("⚠️ 복구 실패")
        
        # 별도 쓰레드에서 실행 (타이머 콜백 블로킹 방지)
        thread = threading.Thread(target=collision_test_thread, daemon=True)
        thread.start()
    
    # ========================================
    # 자동 복구 시퀀스
    # ========================================
    
    def auto_recovery(self) -> bool:
        """전체 자동 복구"""
        self.is_recovering = True
        self._log("=" * 30)
        self._log("자동 복구 시퀀스 시작")
        
        for attempt in range(5):
            state = self.get_robot_state()
            if state is None:
                self._log("상태 조회 실패")
                self.is_recovering = False
                return False
            
            state_name = STATE_CODES.get(state, f"UNKNOWN({state})")
            self._log(f"[시도 {attempt+1}/5] 상태: {state_name}")
            
            if self.is_standby(state):
                self._log("✅ 이미 STANDBY 상태!")
                self.is_recovering = False
                return True
            
            # 1. SAFE_STOP 리셋
            if self.is_safe_stop(state):
                self._log("노란 링(SAFE_STOP) 감지!")
                if self.reset_safe_stop():
                    self._log("✓ SAFE_STOP 리셋")
                time.sleep(0.5)
            
            # 2. RECOVERY 진입
            if self.enter_recovery_mode():
                self._log("✓ RECOVERY 모드 진입")
            time.sleep(0.5)  # RECOVERY 모드 안정화 대기 (0.3 → 0.5)
            
            # 3. Jog 위로 (충돌 위치에서 충분히 벗어나기)
            self._log("Jog로 위로 이동 중...")
            jog_success = self.jog_up(2.5)  # 2.5초 동안 위로
            if not jog_success:
                self._log("Jog 실패 - 재시도 필요")
            time.sleep(0.5)  # 안정화 대기
            
            # 4. RECOVERY 완료
            if self.complete_recovery():
                self._log("✓ RECOVERY 완료")
            time.sleep(0.5)
            
            # 5. RECOVERY 해제
            if self.exit_recovery_mode():
                self._log("✓ RECOVERY 모드 해제")
            time.sleep(0.5)
            
            # 6. Servo ON
            state = self.get_robot_state()
            if state != 1:
                if self.servo_on():
                    self._log("✓ Servo ON")
                time.sleep(1.0)
            
            # 결과 확인
            state = self.get_robot_state()
            if self.is_standby(state):
                self._log("✅ 복구 성공! STANDBY 상태")
                self.is_recovering = False
                return True
            
            self._log("재시도...")
            time.sleep(0.5)
        
        self._log("⚠️ 복구 실패")
        self.is_recovering = False
        return False
    
    # ========================================
    # 메인 루프
    # ========================================
    
    def update_loop(self):
        """주기적 업데이트"""
        # 상태 업데이트
        state = self.get_robot_state()
        if state is not None:
            self.state['robot_state_code'] = state
            self.state['robot_state'] = STATE_CODES.get(state, f"UNKNOWN({state})")
            self.state['is_safe_stop'] = self.is_safe_stop(state)
        
        # 모니터링 모드
        if self.is_monitoring and state is not None:
            if self.is_safe_stop(state) and not self.is_recovering:
                self._log(">>> SAFE_STOP 감지! 자동 복구 시작...")
                if self.auto_recovery():
                    # 복구 성공 후 안전하게 홈으로 이동
                    self._log("복구 완료! 2초 후 홈으로 이동...")
                    time.sleep(2.0)  # 충분히 안정화 대기
                    self.move_home()
        
        # 명령 확인
        cmd = self._read_command()
        if cmd:
            command = cmd.get('command', '')
            self._log(f"명령 수신: {command}")
            self.state['last_action'] = command
            
            if command == 'check_status':
                state = self.get_robot_state()
                state_name = STATE_CODES.get(state, 'UNKNOWN') if state else 'UNKNOWN'
                self._log(f"현재 상태: {state_name}")
                
            elif command == 'auto_recovery':
                if self.auto_recovery():
                    self._log("복구 완료! 홈으로 이동...")
                    time.sleep(1.0)
                    self.move_home()
                
            elif command == 'move_home':
                self.move_home()
                
            elif command == 'move_down_slow':
                self._start_collision_test(fast=False)
                
            elif command == 'move_down_fast':
                self._start_collision_test(fast=True)
                
            elif command == 'monitor_start':
                self.is_monitoring = True
                self._log("🔍 모니터링 모드 시작 - SAFE_STOP 시 자동 복구")
                
            elif command == 'monitor_stop':
                self.is_monitoring = False
                self._log("모니터링 모드 중지")
        
        # 상태 저장
        self._write_state()


def main(args=None):
    rclpy.init(args=args)
    node = CollisionRecoveryWebNode()
    
    # Use MultiThreadedExecutor for concurrent service calls
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    node.executor = executor
    
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
