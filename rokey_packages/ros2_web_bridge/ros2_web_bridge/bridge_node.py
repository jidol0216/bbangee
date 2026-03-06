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
import requests
from threading import Lock

# 상태 저장 파일 경로
STATE_FILE = '/tmp/ros2_bridge_state.json'
AUTO_MODE_FILE = '/tmp/ros2_auto_mode.json'

# ESP32 설정
ESP32_IP = "192.168.10.46"
ESP32_BASE = f"http://{ESP32_IP}"


class BridgeNode(Node):
    def __init__(self):
        super().__init__('ros2_web_bridge')
        
        self.state_lock = Lock()
        
        # 자동 모드 상태
        self.auto_mode = {
            'laser': False,      # 레이저 자동 모드
            'servo': False,      # 서보 자동 모드
            'timeout': 1.0       # 미감지 타임아웃 (초)
        }
        self.laser_on = False
        self.servo_on = False
        self.last_face_time = 0
        
        # 자동 모드 설정 파일 로드
        self._load_auto_mode()
        
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
                'control_source': 'web',  # terminal 또는 web (기본: web)
                'control_mode': 1,  # 1: 직접 제어, 2: 최적 제어 (디폴트: 기본)
                'control_allowed': True  # 웹 제어권일 때만 True
            },
            # 암구호 인증 상태 추가
            'voice_auth': {
                'enabled': False,
                'status': 'IDLE',  # IDLE, LISTENING, PROCESSING, SUCCESS, FAILED, ERROR
                'question_passphrase': '까마귀',
                'answer_passphrase': '백두산',
                'recognized_text': '',
                'last_result': None  # True, False, None
            },
            'system': {
                'bringup_running': False,
                'camera_running': False,
                'detection_running': False,
                'tracking_running': False,
                'joint_tracking_running': False,
                'voice_auth_running': False  # voice_auth 노드 상태 추가
            },
            'auto_mode': {
                'laser': False,
                'servo': False,
                'laser_state': False,
                'servo_state': False
            }
        }
        
        # 구독자들 설정
        self._setup_subscribers()
        
        # 퍼블리셔 설정 (웹 → ROS2)
        self._setup_publishers()
        
        # 상태 저장 타이머 (1Hz)
        self.create_timer(1.0, self._save_state)
        
        # 노드 상태 확인 타이머 (2초마다)
        self.create_timer(2.0, self._check_nodes)
        
        # 자동 모드 타임아웃 체크 타이머 (10Hz)
        self.create_timer(0.1, self._check_auto_timeout)
        
        # 자동 모드 설정 파일 감시 타이머 (1Hz)
        self.create_timer(1.0, self._load_auto_mode)
        
        self.get_logger().info('ROS2 Web Bridge started!')
        self.get_logger().info(f'  Auto Mode: Laser={self.auto_mode["laser"]}, Servo={self.auto_mode["servo"]}')

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
        
        # Voice Auth 상태 구독 - /auth_status
        try:
            from voice_auth_msgs.msg import AuthStatus
            self.auth_status_sub = self.create_subscription(
                AuthStatus,
                '/auth_status',
                self._auth_status_callback,
                10
            )
            self.get_logger().info('  - /auth_status (voice_auth)')
        except ImportError:
            self.get_logger().warn('voice_auth_msgs not found, skipping auth_status subscription')
        
        self.get_logger().info('Subscribed to:')
        self.get_logger().info('  - /dsr01/joint_states')
        self.get_logger().info('  - /face_detection/faces')
        self.get_logger().info('  - /face_tracking/marker_robot')
        self.get_logger().info('  - /joint_tracking/state')
    
    def _setup_publishers(self):
        """웹에서 ROS2로 보내는 퍼블리셔 설정"""
        # 암구호 설정용 퍼블리셔
        self.question_pub = self.create_publisher(String, '/passphrase/question', 10)
        self.answer_pub = self.create_publisher(String, '/passphrase/answer', 10)
        
        self.get_logger().info('Publishers:')
        self.get_logger().info('  - /passphrase/question')
        self.get_logger().info('  - /passphrase/answer')
    
    def set_passphrase(self, question: str, answer: str):
        """웹에서 암구호 설정 (외부에서 호출)"""
        msg_q = String()
        msg_q.data = question
        self.question_pub.publish(msg_q)
        
        msg_a = String()
        msg_a.data = answer
        self.answer_pub.publish(msg_a)
        
        with self.state_lock:
            self.state['voice_auth']['question_passphrase'] = question
            self.state['voice_auth']['answer_passphrase'] = answer
        
        self.get_logger().info(f'암구호 설정: {question} → {answer}')

    def _joint_callback(self, msg: JointState):
        """로봇 관절 상태 콜백"""
        # 모든 값이 0인 메시지는 무시 (더미 퍼블리셔에서 오는 것)
        if all(abs(p) < 0.0001 for p in msg.position):
            return
            
        with self.state_lock:
            self.state['robot']['connected'] = True
            
            # 조인트 이름과 위치를 매핑하여 정렬 (joint_1 ~ joint_6 순서로)
            joint_map = {}
            for name, pos in zip(msg.name, msg.position):
                # joint_1, joint_2, ... joint_6 형태의 이름에서 번호 추출
                if name.startswith('joint_'):
                    try:
                        joint_num = int(name.split('_')[1])
                        if 1 <= joint_num <= 6:
                            joint_map[joint_num] = pos
                    except (ValueError, IndexError):
                        pass
            
            # joint_1 ~ joint_6 순서로 정렬하여 배열 생성
            positions_deg = []
            for i in range(1, 7):  # joint_1 부터 joint_6 까지
                if i in joint_map:
                    positions_deg.append(joint_map[i] * 180.0 / 3.14159)
                else:
                    positions_deg.append(0.0)  # 없는 조인트는 0으로
            
            self.state['robot']['joint_positions'] = positions_deg
            
            # 속도로 이동 상태 판단 (속도가 0.01 이상이면 moving)
            if msg.velocity:
                is_moving = any(abs(v) > 0.01 for v in msg.velocity)
                self.state['robot']['status'] = 'moving' if is_moving else 'idle'
            
            self.state['timestamp'] = time.time()

    def _faces_callback(self, msg: Float32MultiArray):
        """얼굴 감지 콜백 - /face_detection/faces [cx, cy, w, h]"""
        face_detected = len(msg.data) >= 4
        
        with self.state_lock:
            if face_detected:
                # 얼굴 감지됨
                self.state['face_tracking']['face_detected'] = True
                self.state['face_tracking']['face_2d'] = {
                    'cx': msg.data[0],
                    'cy': msg.data[1],
                    'w': msg.data[2],
                    'h': msg.data[3]
                }
                self.last_face_time = time.time()
                
                # 자동 모드 - 얼굴 감지 시 ON
                if self.auto_mode['laser'] and not self.laser_on:
                    self._control_esp32('laser', True)
                if self.auto_mode['servo'] and not self.servo_on:
                    self._control_esp32('servo', True)
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
    
    def _auth_status_callback(self, msg):
        """voice_auth 상태 콜백 - AuthStatus 메시지"""
        # 상태 코드 매핑
        status_map = {
            0: 'IDLE',
            1: 'LISTENING',
            2: 'PROCESSING',
            3: 'SUCCESS',
            4: 'FAILED',
            5: 'ERROR'
        }
        
        with self.state_lock:
            self.state['voice_auth']['enabled'] = True
            self.state['voice_auth']['status'] = status_map.get(msg.status, 'UNKNOWN')
            self.state['voice_auth']['recognized_text'] = msg.recognized_text
            
            # expected_passphrase 파싱 (형식: "질문→정답")
            if '→' in msg.expected_passphrase:
                parts = msg.expected_passphrase.split('→')
                self.state['voice_auth']['question_passphrase'] = parts[0]
                self.state['voice_auth']['answer_passphrase'] = parts[1]
            
            # 결과 저장
            if msg.status == 3:  # SUCCESS
                self.state['voice_auth']['last_result'] = True
            elif msg.status == 4:  # FAILED
                self.state['voice_auth']['last_result'] = False
            
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
            self.state['system']['voice_auth_running'] = 'voice_auth_node' in node_names
            
            # 카메라 연결 상태
            self.state['camera']['connected'] = self.state['system']['camera_running']
            
            # voice_auth 활성화 상태
            self.state['voice_auth']['enabled'] = self.state['system']['voice_auth_running']
            
            self.state['timestamp'] = time.time()

    def _save_state(self):
        """상태를 파일로 저장 (FastAPI가 읽을 수 있도록)"""
        with self.state_lock:
            self.state['timestamp'] = time.time()
            # 자동 모드 상태 반영
            self.state['auto_mode']['laser'] = self.auto_mode['laser']
            self.state['auto_mode']['servo'] = self.auto_mode['servo']
            self.state['auto_mode']['laser_state'] = self.laser_on
            self.state['auto_mode']['servo_state'] = self.servo_on
            try:
                with open(STATE_FILE, 'w') as f:
                    json.dump(self.state, f, indent=2)
            except Exception as e:
                self.get_logger().error(f'Failed to save state: {e}')
    
    def _load_auto_mode(self):
        """자동 모드 설정 파일 로드"""
        if os.path.exists(AUTO_MODE_FILE):
            try:
                with open(AUTO_MODE_FILE, 'r') as f:
                    data = json.load(f)
                    old_laser = self.auto_mode['laser']
                    old_servo = self.auto_mode['servo']
                    self.auto_mode['laser'] = data.get('laser', False)
                    self.auto_mode['servo'] = data.get('servo', False)
                    self.auto_mode['timeout'] = data.get('timeout', 1.0)
                    
                    # 변경 시 로그
                    if old_laser != self.auto_mode['laser'] or old_servo != self.auto_mode['servo']:
                        self.get_logger().info(f'Auto Mode updated: Laser={self.auto_mode["laser"]}, Servo={self.auto_mode["servo"]}')
            except Exception as e:
                pass  # 파일 없으면 기본값 사용
    
    def _check_auto_timeout(self):
        """자동 모드 타임아웃 체크 - 미감지 시 OFF"""
        now = time.time()
        elapsed = now - self.last_face_time
        
        # 타임아웃 초과 시 OFF
        if elapsed > self.auto_mode['timeout']:
            if self.auto_mode['laser'] and self.laser_on:
                self._control_esp32('laser', False)
            if self.auto_mode['servo'] and self.servo_on:
                self._control_esp32('servo', False)
    
    def _control_esp32(self, device: str, on: bool):
        """ESP32 디바이스 제어 (레이저/서보)"""
        try:
            r = requests.post(
                f"{ESP32_BASE}/device/{device}",
                data="on" if on else "off",
                headers={"Content-Type": "text/plain"},
                timeout=0.5
            )
            if device == 'laser':
                self.laser_on = on
            elif device == 'servo':
                self.servo_on = on
            
            status = "ON" if on else "OFF"
            self.get_logger().info(f' Auto {device.upper()} {status}')
        except Exception as e:
            pass  # 타임아웃 무시 (스트림 차단 방지)


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
