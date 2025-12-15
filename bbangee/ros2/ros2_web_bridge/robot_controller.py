#!/usr/bin/env python3
"""
Robot Controller Node
- 웹에서 받은 명령을 실제 ROS2 서비스로 호출
- 로봇 제어 (홈, 정지 등)
"""

import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from std_msgs.msg import Bool, String
from sensor_msgs.msg import JointState
import json
import os
import time

# Doosan 서비스/액션 임포트
try:
    from dsr_msgs2.srv import MoveJoint, MoveStop, SetRobotMode
    from dsr_msgs2.msg import RobotState
    HAS_DSR = True
except ImportError:
    HAS_DSR = False
    print("[WARN] dsr_msgs2 not found. Robot control disabled.")

# 명령 파일 경로 (FastAPI가 작성)
COMMAND_FILE = '/tmp/ros2_bridge_command.json'


class RobotController(Node):
    def __init__(self):
        super().__init__('robot_controller')
        
        self.last_command_time = 0
        
        # Doosan 서비스 클라이언트
        if HAS_DSR:
            self.move_joint_client = self.create_client(
                MoveJoint, 
                '/dsr01/motion/move_joint'
            )
            self.stop_client = self.create_client(
                MoveStop,
                '/dsr01/motion/move_stop'
            )
            self.set_mode_client = self.create_client(
                SetRobotMode,
                '/dsr01/system/set_robot_mode'
            )
        
        # 트래킹 활성화 퍼블리셔
        self.tracking_enable_pub = self.create_publisher(
            Bool,
            '/face_tracking/enable',
            10
        )
        
        # joint_tracking_node 웹 명령 퍼블리셔
        from std_msgs.msg import String
        self.web_cmd_pub = self.create_publisher(
            String,
            '/joint_tracking/web_command',
            10
        )
        
        # 명령 파일 확인 타이머 (10Hz)
        self.create_timer(0.1, self._check_commands)
        
        self.get_logger().info('Robot Controller started!')
        if not HAS_DSR:
            self.get_logger().warn('DSR messages not available - control disabled')

    def _check_commands(self):
        """명령 파일 확인 및 처리"""
        if not os.path.exists(COMMAND_FILE):
            return
        
        try:
            with open(COMMAND_FILE, 'r') as f:
                command = json.load(f)
            
            # 새 명령인지 확인
            cmd_time = command.get('timestamp', 0)
            if cmd_time <= self.last_command_time:
                return
            
            self.last_command_time = cmd_time
            
            # 명령 처리
            cmd_type = command.get('type', '')
            
            if cmd_type == 'tracking_enable':
                self._handle_tracking_enable(command.get('value', False))
            
            elif cmd_type == 'robot_command':
                self._handle_robot_command(command.get('data', {}))
            
            elif cmd_type == 'robot_motion':
                self._handle_robot_motion(command.get('data', {}))
            
            # 처리된 명령 파일 삭제
            os.remove(COMMAND_FILE)
            
        except Exception as e:
            self.get_logger().error(f'Error processing command: {e}')

    def _handle_tracking_enable(self, enable: bool):
        """트래킹 활성화/비활성화"""
        msg = Bool()
        msg.data = enable
        self.tracking_enable_pub.publish(msg)
        self.get_logger().info(f'Tracking {"enabled" if enable else "disabled"}')

    def _send_web_command(self, cmd: str):
        """joint_tracking_node에 웹 명령 전송"""
        from std_msgs.msg import String
        msg = String()
        msg.data = cmd
        self.web_cmd_pub.publish(msg)
        self.get_logger().info(f'Web command sent: {cmd}')

    def _handle_robot_command(self, data: dict):
        """로봇 명령 처리"""
        cmd = data.get('command', '')
        
        # joint_tracking_node로 전달할 명령들
        web_commands = ['take_control', 'start', 'stop', 'home', 'ready', 'mode1', 'mode2']
        
        if cmd in web_commands:
            self._send_web_command(cmd)
        elif cmd == 'tracking_on':
            self._handle_tracking_enable(True)
        elif cmd == 'tracking_off':
            self._handle_tracking_enable(False)
        elif cmd == 'speed_boost':
            # 추적 속도 증가 명령
            multiplier = data.get('speed_multiplier', 1.5)
            self._send_web_command(f'speed:{multiplier}')
            self.get_logger().info(f'⚡ 추적 속도 증가: {multiplier}배')
        else:
            self.get_logger().warn(f'Unknown command: {cmd}')

    def _handle_robot_motion(self, data: dict):
        """로봇 모션 실행 (미리 정의된 조인트 위치)"""
        if not HAS_DSR:
            self.get_logger().warn('DSR not available - cannot execute motion')
            return
        
        motion_id = data.get('motion_id', 'custom')
        motion_name = data.get('motion_name', 'Unknown')
        joints = data.get('joints', [0.0] * 6)
        velocity = data.get('velocity', 30.0)
        acceleration = data.get('acceleration', 25.0)
        
        self.get_logger().info(f'🤖 모션 실행: {motion_name} ({motion_id})')
        self.get_logger().info(f'   Joints: {joints}')
        
        if not self.move_joint_client.wait_for_service(timeout_sec=2.0):
            self.get_logger().error('MoveJoint service not available')
            return
        
        request = MoveJoint.Request()
        request.pos = joints
        request.vel = velocity
        request.acc = acceleration
        request.time = 0.0
        request.radius = 0.0
        request.mode = 0
        request.blend_type = 0
        request.sync_type = 0  # 비동기 실행 (UI 블로킹 방지)
        
        future = self.move_joint_client.call_async(request)
        self.get_logger().info(f'✅ 모션 "{motion_name}" 명령 전송 완료')

    def _move_to_home(self):
        """홈 위치로 이동"""
        if not HAS_DSR:
            self.get_logger().warn('DSR not available')
            return
        
        if not self.move_joint_client.wait_for_service(timeout_sec=1.0):
            self.get_logger().error('MoveJoint service not available')
            return
        
        # 홈 위치 (face_tracking 패키지 HOME_JOINTS)
        request = MoveJoint.Request()
        request.pos = [0.0, 0.0, 90.0, 0.0, 90.0, 0.0]  # HOME_JOINTS
        request.vel = 30.0
        request.acc = 30.0
        request.time = 0.0
        request.radius = 0.0
        request.mode = 0
        request.blend_type = 0
        request.sync_type = 1  # 동기 실행 (face_tracking과 동일)
        
        future = self.move_joint_client.call_async(request)
        self.get_logger().info('Moving to home position...')

    def _move_to_ready(self):
        """시작(준비) 위치로 이동 - 얼굴 트래킹용"""
        if not HAS_DSR:
            self.get_logger().warn('DSR not available')
            return
        
        if not self.move_joint_client.wait_for_service(timeout_sec=1.0):
            self.get_logger().error('MoveJoint service not available')
            return
        
        # 시작 위치 (face_tracking 패키지 START_JOINTS)
        request = MoveJoint.Request()
        request.pos = [3.06, 2.84, 92.13, 86.07, -1.43, 8.33]  # START_JOINTS
        request.vel = 30.0
        request.acc = 30.0
        request.time = 0.0
        request.radius = 0.0
        request.mode = 0
        request.blend_type = 0
        request.sync_type = 1  # 동기 실행 (face_tracking과 동일)
        
        future = self.move_joint_client.call_async(request)
        self.get_logger().info('Moving to ready position...')

    def _stop_robot(self):
        """로봇 정지"""
        if not HAS_DSR:
            self.get_logger().warn('DSR not available')
            return
        
        if not self.stop_client.wait_for_service(timeout_sec=1.0):
            self.get_logger().error('MoveStop service not available')
            return
        
        request = MoveStop.Request()
        request.stop_mode = 0  # STOP_TYPE_QUICK
        
        future = self.stop_client.call_async(request)
        self.get_logger().info('Robot stopped!')


def main(args=None):
    rclpy.init(args=args)
    node = RobotController()
    
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
