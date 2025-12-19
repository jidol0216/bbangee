#!/usr/bin/env python3
"""
ROS2 Status Publisher
- 웹에서 받은 명령을 ROS2로 발행
- Face tracking enable/disable 제어
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool, String
from geometry_msgs.msg import Point
import json
import os
import time

# 명령 파일 경로 (FastAPI가 작성)
COMMAND_FILE = '/tmp/ros2_bridge_command.json'


class StatusPublisher(Node):
    def __init__(self):
        super().__init__('status_publisher')
        
        # 발행자 설정
        self.tracking_enable_pub = self.create_publisher(
            Bool,
            '/face_tracking/enable_command',
            10
        )
        
        self.command_pub = self.create_publisher(
            String,
            '/web_command',
            10
        )
        
        # 명령 파일 확인 타이머 (10Hz)
        self.create_timer(0.1, self._check_commands)
        
        self.last_command_time = 0
        
        self.get_logger().info('Status Publisher started!')

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
                msg = Bool()
                msg.data = command.get('value', False)
                self.tracking_enable_pub.publish(msg)
                self.get_logger().info(f'Tracking enable: {msg.data}')
            
            elif cmd_type == 'robot_command':
                msg = String()
                msg.data = json.dumps(command.get('data', {}))
                self.command_pub.publish(msg)
                self.get_logger().info(f'Robot command: {msg.data}')
            
            # 처리된 명령 파일 삭제
            os.remove(COMMAND_FILE)
            
        except Exception as e:
            self.get_logger().error(f'Error processing command: {e}')


def main(args=None):
    rclpy.init(args=args)
    node = StatusPublisher()
    
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
