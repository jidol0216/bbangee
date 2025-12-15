#!/usr/bin/env python3
"""
ROS2 Web Bridge Node
- ROS2 토픽들을 구독하여 전역 상태로 저장
- FastAPI 백엔드가 이 상태를 조회할 수 있도록 파일로 공유

실제 face_tracking 패키지 토픽:
    /face_detection/faces - Float32MultiArray [cx, cy, w, h]
    /face_tracking/marker_robot - Marker (로봇 좌표계 3D 위치)
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Bool, Float32MultiArray
from sensor_msgs.msg import JointState
from geometry_msgs.msg import Point
from visualization_msgs.msg import Marker
import json
import os
import time
from threading import Lock

# 상태 저장 파일 경로
STATE_FILE = '/tmp/ros2_bridge_state.json'


class BridgeNode(Node):
    def __init__(self):
        super().__init__('ros2_web_bridge')
        
        self.state_lock = Lock()
        self.state = {
            'timestamp': 0,
            'robot': {
                'connected': False,
                'mode': 'unknown',  # 'manual', 'auto'
                'joint_positions': [0.0] * 6,
                'status': 'idle'  # 'idle', 'moving', 'error'
            },
            'camera': {
                'connected': False,
                'streaming': False
            },
            'face_tracking': {
                'enabled': False,
                'face_detected': False,
                'face_position': {'x': 0, 'y': 0, 'z': 0},
                'tracking_target': None
            },
            'joint_tracking': {
                'state': 'IDLE',  # IDLE, TRACKING, RETURN_HOME
                'control_source': 'terminal',  # terminal 또는 web
                'control_mode': 1,  # 1: 직접 제어, 2: 최적 제어
                'control_allowed': False  # 웹 제어권일 때만 True
            },
            'system': {
                'bringup_running': False,
                'camera_running': False,
                'detection_running': False,
                'tracking_running': False,
                'joint_tracking_running': False
            }
        }
        
        # 구독자들 설정
        self._setup_subscribers()
        
        # 상태 저장 타이머 (1Hz)
        self.create_timer(1.0, self._save_state)
        
        # 노드 상태 확인 타이머 (2초마다)
        self.create_timer(2.0, self._check_nodes)
        
        self.get_logger().info('ROS2 Web Bridge started!')

    def _setup_subscribers(self):
        """ROS2 토픽 구독자 설정 - face_tracking 패키지 실제 토픽 사용"""
        from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
        
        # joint_states용 QoS - BEST_EFFORT로 모든 퍼블리셔와 호환
        joint_qos = QoSProfile(
            depth=10,
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE
        )
        
        # Joint States (로봇 관절 상태)
        self.joint_sub = self.create_subscription(
            JointState,
            '/dsr01/joint_states',
            self._joint_callback,
            joint_qos
        )
        
        # Face Detection 결과 - Float32MultiArray [cx, cy, w, h]
        self.faces_sub = self.create_subscription(
            Float32MultiArray,
            '/face_detection/faces',
            self._faces_callback,
            10
        )
        
        # Face Tracking 로봇 좌표 마커 - Marker (실제 3D 위치)
        self.marker_robot_sub = self.create_subscription(
            Marker,
            '/face_tracking/marker_robot',
            self._marker_robot_callback,
            10
        )
        
        # Joint Tracking 상태 - IDLE, TRACKING, RETURN_HOME
        from std_msgs.msg import String
        self.joint_tracking_state_sub = self.create_subscription(
            String,
            '/joint_tracking/state',
            self._joint_tracking_state_callback,
            10
        )
        
        self.get_logger().info('Subscribed to:')
        self.get_logger().info('  - /dsr01/joint_states')
        self.get_logger().info('  - /face_detection/faces')
        self.get_logger().info('  - /face_tracking/marker_robot')
        self.get_logger().info('  - /joint_tracking/state')

    def _joint_callback(self, msg: JointState):
        """로봇 관절 상태 콜백"""
        with self.state_lock:
            self.state['robot']['connected'] = True
            # radian to degree 변환
            positions_deg = [p * 180.0 / 3.14159 for p in msg.position]
            self.state['robot']['joint_positions'] = positions_deg
            
            # 속도로 이동 상태 판단 (속도가 0.01 이상이면 moving)
            if msg.velocity:
                is_moving = any(abs(v) > 0.01 for v in msg.velocity)
                self.state['robot']['status'] = 'moving' if is_moving else 'idle'
            
            self.state['timestamp'] = time.time()

    def _faces_callback(self, msg: Float32MultiArray):
        """얼굴 감지 콜백 - /face_detection/faces [cx, cy, w, h]"""
        with self.state_lock:
            if len(msg.data) >= 4:
                # 얼굴 감지됨
                self.state['face_tracking']['face_detected'] = True
                self.state['face_tracking']['face_2d'] = {
                    'cx': msg.data[0],
                    'cy': msg.data[1],
                    'w': msg.data[2],
                    'h': msg.data[3]
                }
            else:
                # 얼굴 없음
                self.state['face_tracking']['face_detected'] = False
            
            self.state['timestamp'] = time.time()

    def _marker_robot_callback(self, msg: Marker):
        """얼굴 3D 위치 콜백 - /face_tracking/marker_robot (로봇 좌표계)"""
        with self.state_lock:
            # Marker의 pose.position에서 3D 좌표 추출 (mm 단위)
            self.state['face_tracking']['face_position'] = {
                'x': msg.pose.position.x * 1000,  # m -> mm
                'y': msg.pose.position.y * 1000,
                'z': msg.pose.position.z * 1000
            }
            self.state['face_tracking']['enabled'] = True
            self.state['timestamp'] = time.time()

    def _joint_tracking_state_callback(self, msg):
        """joint_tracking_node 상태 콜백 - JSON 형식 {state, control_source, control_mode}"""
        import json
        with self.state_lock:
            try:
                data = json.loads(msg.data)
                self.state['joint_tracking']['state'] = data.get('state', 'IDLE')
                self.state['joint_tracking']['control_source'] = data.get('control_source', 'terminal')
                self.state['joint_tracking']['control_mode'] = data.get('control_mode', 1)
                # 웹 제어권일 때만 웹에서 제어 허용
                self.state['joint_tracking']['control_allowed'] = (data.get('control_source') == 'web')
            except json.JSONDecodeError:
                # 이전 버전 호환 (단순 문자열)
                self.state['joint_tracking']['state'] = msg.data
                self.state['joint_tracking']['control_allowed'] = (msg.data == 'IDLE')
            self.state['timestamp'] = time.time()

    def _check_nodes(self):
        """실행 중인 노드 확인"""
        node_names = self.get_node_names()
        
        with self.state_lock:
            # 각 노드 실행 상태 확인
            self.state['system']['bringup_running'] = any('dsr' in n.lower() for n in node_names)
            self.state['system']['camera_running'] = any('realsense' in n.lower() or 'camera' in n.lower() for n in node_names)
            self.state['system']['detection_running'] = 'face_detection_node' in node_names
            self.state['system']['tracking_running'] = 'face_tracking_node' in node_names
            self.state['system']['joint_tracking_running'] = 'joint_tracking_node' in node_names
            
            # 카메라 연결 상태
            self.state['camera']['connected'] = self.state['system']['camera_running']
            
            self.state['timestamp'] = time.time()

    def _save_state(self):
        """상태를 파일로 저장 (FastAPI가 읽을 수 있도록)"""
        with self.state_lock:
            self.state['timestamp'] = time.time()
            try:
                with open(STATE_FILE, 'w') as f:
                    json.dump(self.state, f, indent=2)
            except Exception as e:
                self.get_logger().error(f'Failed to save state: {e}')


def main(args=None):
    rclpy.init(args=args)
    node = BridgeNode()
    
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
