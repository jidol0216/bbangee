#!/usr/bin/env python3
"""
pistol_grip_node.py - 권총 파지/거치 ROS2 노드

명령 파일 감시하여 권총 파지/거치 동작 실행
- /tmp/ros2_bridge_command.json 감시
- pistol_action 타입 처리

로봇 이동: ros2 service call (subprocess)
그리퍼 제어: HTTP API (curl)
"""

import rclpy
from rclpy.node import Node
import json
import os
import time
import subprocess

# Robot settings
ROBOT_ID = "dsr01"
ROBOT_MODEL = "m0609"

# 명령 파일 경로
COMMAND_FILE = '/tmp/ros2_bridge_command.json'


class PistolGripNode:
    """권총 파지/거치 노드"""
    
    def __init__(self, node):
        self.node = node
        self.get_logger = node.get_logger
        
        self.last_command_time = 0
        self.is_executing = False
        
        # 명령 파일 감시 타이머 (10Hz)
        self.timer = node.create_timer(0.1, self._check_commands)
        
        self.get_logger().info(' PistolGripNode 시작!')
        self.get_logger().info('   로봇 이동: ros2 service call')
        self.get_logger().info('   그리퍼: HTTP API')
    
    def _gripper_open(self):
        """그리퍼 열기 (HTTP API)"""
        import subprocess
        try:
            subprocess.run(
                ['curl', '-s', '-X', 'POST', 'http://localhost:8000/gripper/action', 
                 '-H', 'Content-Type: application/json', '-d', '{"action": "open"}'],
                timeout=5
            )
            time.sleep(1.5)  # 그리퍼 동작 대기
            self.get_logger().info('   그리퍼 열림')
        except Exception as e:
            self.get_logger().error(f'그리퍼 열기 실패: {e}')
    
    def _gripper_close(self, width=30):
        """그리퍼 닫기 (HTTP API)"""
        import subprocess
        try:
            subprocess.run(
                ['curl', '-s', '-X', 'POST', 'http://localhost:8000/gripper/action',
                 '-H', 'Content-Type: application/json', '-d', '{"action": "close"}'],
                timeout=5
            )
            time.sleep(1.5)  # 그리퍼 동작 대기
            self.get_logger().info(f'   그리퍼 닫힘')
        except Exception as e:
            self.get_logger().error(f'그리퍼 닫기 실패: {e}')
    
    def _move_to_position(self, pos, vel=60, acc=60):
        """위치로 이동 (ros2 service call)"""
        import subprocess
        try:
            # MoveLine 서비스 호출
            service_data = (
                f"{{pos: [{pos['x']}, {pos['y']}, {pos['z']}, "
                f"{pos['rx']}, {pos['ry']}, {pos['rz']}], "
                f"vel: [{vel}, {vel}], acc: [{acc}, {acc}], "
                f"time: 0.0, radius: 0.0, ref: 0, mode: 0}}"
            )
            
            result = subprocess.run(
                ['ros2', 'service', 'call', '/dsr01/motion/move_line',
                 'dsr_msgs2/srv/MoveLine', service_data],
                capture_output=True, text=True, timeout=30
            )
            
            if result.returncode == 0:
                self.get_logger().info('   이동 완료!')
            else:
                self.get_logger().error(f'   이동 실패: {result.stderr}')
                
        except subprocess.TimeoutExpired:
            self.get_logger().warn('   이동 타임아웃 (30초)')
        except Exception as e:
            self.get_logger().error(f'이동 실패: {e}')
    
    def _check_commands(self):
        """명령 파일 확인"""
        if not os.path.exists(COMMAND_FILE):
            return
        
        if self.is_executing:
            self.get_logger().warn('이미 실행 중...')
            return
        
        try:
            with open(COMMAND_FILE, 'r') as f:
                command = json.load(f)
            
            cmd_type = command.get('type', '')
            self.get_logger().info(f' 명령 파일 읽음: type={cmd_type}')
            
            # 새 명령인지 확인
            cmd_time = command.get('timestamp', 0)
            if cmd_time <= self.last_command_time:
                self.get_logger().warn(f'이미 처리된 명령 (time={cmd_time})')
                return
            
            # pistol_action만 처리
            if cmd_type != 'pistol_action':
                self.get_logger().info(f'무시: {cmd_type} (pistol_action 아님)')
                return
            
            self.last_command_time = cmd_time
            self.get_logger().info(f' pistol_action 명령 처리 시작')
            
            # 처리된 명령 삭제
            os.remove(COMMAND_FILE)
            self.get_logger().info(' 명령 파일 삭제됨')
            
            # 직접 실행 (쓰레딩 사용 안함 - spin 충돌 방지)
            data = command.get('data', {})
            self._execute_action(data)
            
        except Exception as e:
            self.get_logger().error(f'명령 처리 에러: {e}')
    
    def _execute_action(self, data: dict):
        """파지/거치 동작 실행"""
        action = data.get('action', '')
        
        self.is_executing = True
        try:
            if action == 'grip':
                self._do_grip(data)
            elif action == 'holster':
                self._do_holster(data)
            else:
                self.get_logger().warn(f'알 수 없는 액션: {action}')
        except Exception as e:
            self.get_logger().error(f'동작 실행 에러: {e}')
            import traceback
            traceback.print_exc()
        finally:
            self.is_executing = False
    
    def _move_to_joint(self, joints, vel=60, acc=60):
        """조인트 위치로 이동 (ros2 service call - movej)"""
        import subprocess
        try:
            # MoveJoint 서비스 호출
            service_data = (
                f"{{pos: {joints}, "
                f"vel: {vel}, acc: {acc}, "
                f"time: 0.0, radius: 0.0, mode: 0, blend_type: 0, sync_type: 0}}"
            )
            
            result = subprocess.run(
                ['ros2', 'service', 'call', '/dsr01/motion/move_joint',
                 'dsr_msgs2/srv/MoveJoint', service_data],
                capture_output=True, text=True, timeout=30
            )
            
            if result.returncode == 0:
                self.get_logger().info('   조인트 이동 완료!')
            else:
                self.get_logger().error(f'   조인트 이동 실패: {result.stderr}')
                
        except subprocess.TimeoutExpired:
            self.get_logger().warn('   조인트 이동 타임아웃 (30초)')
        except Exception as e:
            self.get_logger().error(f'조인트 이동 실패: {e}')

    def _do_grip(self, data: dict):
        """
         권총 파지 (Pick up)
        1. 그리퍼 열기
        2. 위치로 이동
        3. 그리퍼 닫기
        4. Z축 들어올리기 (+150mm)
        """
        pos = data.get('position', data.get('a1', {}))
        z_lift = data.get('z_lift', 150)
        grip_width = data.get('grip_width', 3)
        vel = data.get('velocity', 60)
        acc = data.get('acceleration', 60)
        
        self.get_logger().info('=' * 50)
        self.get_logger().info(' 권총 파지 시작')
        self.get_logger().info(f'   파지 위치: ({pos["x"]:.1f}, {pos["y"]:.1f}, {pos["z"]:.1f})')
        self.get_logger().info(f'   들어올리기: +{z_lift}mm')
        self.get_logger().info('=' * 50)
        
        # === 1. 그리퍼 열기 ===
        self.get_logger().info('1 그리퍼 열기...')
        self._gripper_open()
        
        # === 2. 위치로 이동 ===
        self.get_logger().info(f'2 파지 위치로 이동...')
        self._move_to_position(pos, vel, acc)
        
        # === 3. 그리퍼 닫기 ===
        self.get_logger().info(f'3 그리퍼 닫기 (잡기)...')
        self._gripper_close(grip_width)
        
        # === 4. Z축 들어올리기 ===
        lift_pos = pos.copy()
        lift_pos['z'] = pos['z'] + z_lift
        self.get_logger().info(f'4 Z축 들어올리기... Z={lift_pos["z"]:.1f}mm (+{z_lift}mm)')
        self._move_to_position(lift_pos, vel=30, acc=30)  # 느린 속도로 들어올리기
        
        self.get_logger().info('=' * 50)
        self.get_logger().info(' 권총 파지 완료! (시작위치 버튼 누르세요)')
        self.get_logger().info('=' * 50)
    
    def _do_holster(self, data: dict):
        """
         권총 거치 (Put down)
        1. 위치로 이동
        2. 그리퍼 열기
        """
        pos = data.get('position', data.get('a1', {}))
        vel = data.get('velocity', 60)
        acc = data.get('acceleration', 60)
        
        self.get_logger().info('=' * 50)
        self.get_logger().info(' 권총 거치 시작')
        self.get_logger().info(f'   위치: ({pos["x"]:.1f}, {pos["y"]:.1f}, {pos["z"]:.1f})')
        self.get_logger().info('=' * 50)
        
        # === 1. 위치로 이동 ===
        self.get_logger().info(f'1 위치로 이동...')
        self._move_to_position(pos, vel, acc)
        
        # === 2. 그리퍼 열기 ===
        self.get_logger().info('2 그리퍼 열기 (놓기)...')
        self._gripper_open()
        
        self.get_logger().info('=' * 50)
        self.get_logger().info(' 권총 거치 완료!')
        self.get_logger().info('=' * 50)


def main(args=None):
    rclpy.init(args=args)
    
    # 간단한 노드 생성
    node = rclpy.create_node('pistol_grip_node', namespace=ROBOT_ID)
    
    try:
        grip_node = PistolGripNode(node)
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f' 에러: {e}')
        import traceback
        traceback.print_exc()
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
