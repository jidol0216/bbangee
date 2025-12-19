#!/usr/bin/env python3
"""
Head Detection → Laser Control Test
====================================
얼굴 감지 시 ESP32 레이저 ON, 미감지 시 OFF

사용법:
  1. 백엔드 서버 실행: cd backend && uvicorn app.main:app --port 8000
  2. ROS2 face_detection 노드 실행
  3. 이 스크립트 실행: python3 test_head_laser.py

필요 토픽:
  - /face_detection/faces (Float32MultiArray)
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32MultiArray
import requests
import time


class HeadLaserTest(Node):
    def __init__(self):
        super().__init__('head_laser_test')
        
        # ESP32 API 설정
        self.api_url = "http://localhost:8000/device/laser"
        self.esp32_direct_url = "http://192.168.10.46/device/laser"
        self.use_backend = True  # True: 백엔드 API, False: ESP32 직접
        
        # 상태 관리
        self.laser_on = False
        self.last_detection_time = 0
        self.timeout = 1.0  # 1초 미감지 시 레이저 OFF
        
        # 구독자
        self.sub = self.create_subscription(
            Float32MultiArray,
            '/face_detection/faces',
            self.faces_callback,
            10
        )
        
        # 타이머 (레이저 OFF 체크)
        self.timer = self.create_timer(0.1, self.check_timeout)
        
        self.get_logger().info('🎯 Head → Laser Test Node 시작!')
        self.get_logger().info(f'   API: {"Backend" if self.use_backend else "ESP32 Direct"}')
        self.get_logger().info('   토픽: /face_detection/faces')
        self.get_logger().info('   Timeout: %.1f초' % self.timeout)
    
    def set_laser(self, on: bool):
        """레이저 ON/OFF"""
        if self.laser_on == on:
            return  # 이미 같은 상태
        
        try:
            if self.use_backend:
                # 백엔드 API 사용
                r = requests.post(
                    self.api_url,
                    json={"target": on},
                    timeout=0.5
                )
            else:
                # ESP32 직접 호출
                r = requests.post(
                    self.esp32_direct_url,
                    data="on" if on else "off",
                    headers={"Content-Type": "text/plain"},
                    timeout=0.5
                )
            
            self.laser_on = on
            status = "🔴 ON" if on else "⚫ OFF"
            self.get_logger().info(f'레이저 {status}')
            
        except Exception as e:
            self.get_logger().warn(f'레이저 제어 실패: {e}')
    
    def faces_callback(self, msg: Float32MultiArray):
        """얼굴 감지 콜백"""
        if len(msg.data) >= 4:
            # 얼굴 감지됨!
            cx, cy, w, h = msg.data[0], msg.data[1], msg.data[2], msg.data[3]
            self.last_detection_time = time.time()
            
            if not self.laser_on:
                self.get_logger().info(f'👤 얼굴 감지! ({cx:.0f}, {cy:.0f})')
                self.set_laser(True)
    
    def check_timeout(self):
        """미감지 타임아웃 체크"""
        if self.laser_on:
            elapsed = time.time() - self.last_detection_time
            if elapsed > self.timeout:
                self.get_logger().info('👻 얼굴 미감지 (timeout)')
                self.set_laser(False)


def main(args=None):
    rclpy.init(args=args)
    node = HeadLaserTest()
    
    print("\n" + "="*50)
    print("   얼굴 감지 → 레이저 제어 테스트")
    print("="*50)
    print("  - 얼굴 감지: 레이저 ON 🔴")
    print("  - 1초 미감지: 레이저 OFF ⚫")
    print("  - Ctrl+C로 종료")
    print("="*50 + "\n")
    
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        print("\n종료 중...")
        node.set_laser(False)  # 레이저 OFF
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
