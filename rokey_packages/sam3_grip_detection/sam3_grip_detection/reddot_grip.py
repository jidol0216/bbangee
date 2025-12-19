#!/usr/bin/env python3
"""
reddot_grip.py - 빨간점 YOLO 검출 → 좌표 변환 → 그리퍼로 잡기

동작 순서:
1. 카메라에서 빨간점 YOLO 검출
2. 빨간점 중심 픽셀 → 3D 카메라 좌표 (depth 사용)
3. 카메라 좌표 → 로봇 베이스 좌표 변환
4. 빨간점에서 Z축 -35mm (아래) 위치로 이동
5. 그리퍼로 잡기
6. 들어올리기
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from sensor_msgs.msg import Image, CameraInfo
from geometry_msgs.msg import PointStamped
from visualization_msgs.msg import Marker
from cv_bridge import CvBridge
import cv2
import numpy as np
from scipy.spatial.transform import Rotation
import time
import os
import sys

# OnRobot 그리퍼 모듈 경로 추가
sys.path.append('/home/rokey/ros2_ws/src/archive/face_tracking_pkg/day1/2_calibration')

# YOLO
from ultralytics import YOLO

import DR_init

# ============== 설정 ==============
ROBOT_ID = "dsr01"
ROBOT_MODEL = "m0609"
VELOCITY, ACC = 60, 60

# 그리퍼 설정 (최대값)
GRIPPER_NAME = "rg2"
TOOLCHANGER_IP = "192.168.1.1"
TOOLCHANGER_PORT = "502"
GRIPPER_OPEN_WIDTH = 110   # mm - RG2 최대
GRIPPER_CLOSE_WIDTH = 0    # mm - 최대한 닫기 (물체에 맞춰 자동 정지)
GRIPPER_FORCE = 400        # N - RG2 최대

# 카메라 토픽
COLOR_TOPIC = "/camera/camera/color/image_raw"
DEPTH_TOPIC = "/camera/camera/aligned_depth_to_color/image_raw"
CAMERA_INFO_TOPIC = "/camera/camera/color/camera_info"

# YOLO 모델 경로 (학습 후 수정)
YOLO_MODEL_PATH = "/home/rokey/Desktop/2day/reddot.pt"

# 캘리브레이션 파일 경로 (Eye-on-Hand: T_gripper2camera)
# Translation: (45.5, 109.9, 245.7)mm - 사용자 제공 원본 파일
CALIBRATION_FILE = "/home/rokey/ros2_ws/src/T_gripper2camera.npy"

# 카메라 180도 회전 여부 (카메라가 뒤집힐)
CAMERA_FLIPPED = True  # True: 이미지 180도 회전

# 빨간점에서 잡을 위치 오프셋
REDDOT_Z_OFFSET = -35.0    # mm - 빨간점 중심에서 아래로 35mm

# Z축 접근/들어올리기 오프셋
Z_APPROACH_OFFSET = 100    # mm - 접근 시 위에서
Z_LIFT_OFFSET = 100        # mm - 들어올리기

# 테스트 모드
TEST_MODE = False  # True: 로봇 없이 좌표만 출력

# 신뢰도 임계값
CONFIDENCE_THRESHOLD = 0.5

# 실시간 화면 표시
SHOW_DISPLAY = True  # True: 검출 결과 실시간 표시

DR_init.__dsr__id = ROBOT_ID
DR_init.__dsr__model = ROBOT_MODEL


def posx_to_matrix(posx):
    """로봇 posx [x,y,z,rx,ry,rz] → 4x4 변환행렬"""
    x, y, z, rx, ry, rz = posx
    R = Rotation.from_euler('ZYZ', [rx, ry, rz], degrees=True).as_matrix()
    T = np.eye(4)
    T[:3, :3] = R
    T[:3, 3] = [x, y, z]
    return T


class ReddotGrip(Node):
    def __init__(self):
        super().__init__('reddot_grip_node')
        
        self.bridge = CvBridge()
        self.color_image = None
        self.depth_image = None
        self.camera_info = None
        self.fx, self.fy, self.cx, self.cy = None, None, None, None
        
        # YOLO 모델 로드
        self._load_yolo_model()
        
        # 캘리브레이션 로드
        self._load_calibration()
        
        # 로봇/그리퍼 초기화
        if not TEST_MODE:
            self._init_robot()
        else:
            self.get_logger().warn('⚠️ TEST MODE - 로봇 동작 없이 좌표만 출력')
        
        # QoS 설정
        qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=1
        )
        
        # 카메라 구독
        self.color_sub = self.create_subscription(
            Image, COLOR_TOPIC, self._color_callback, qos)
        self.depth_sub = self.create_subscription(
            Image, DEPTH_TOPIC, self._depth_callback, qos)
        self.info_sub = self.create_subscription(
            CameraInfo, CAMERA_INFO_TOPIC, self._info_callback, 10)
        
        # RViz 시각화 퍼블리셔
        self.detection_image_pub = self.create_publisher(Image, '/reddot/detection_image', 10)
        self.grip_marker_pub = self.create_publisher(Marker, '/reddot/grip_marker', 10)
        self.grip_point_pub = self.create_publisher(PointStamped, '/reddot/grip_point', 10)
        
        self.get_logger().info('=' * 50)
        self.get_logger().info('🔴 ReddotGrip 노드 시작')
        self.get_logger().info(f'   YOLO 모델: {YOLO_MODEL_PATH}')
        self.get_logger().info(f'   캘리브레이션: {CALIBRATION_FILE}')
        self.get_logger().info(f'   빨간점 오프셋: Z{REDDOT_Z_OFFSET}mm')
        self.get_logger().info(f'   카메라 플립: {CAMERA_FLIPPED}')
        self.get_logger().info(f'   RViz 토픽: /reddot/detection_image, /reddot/grip_marker')
        self.get_logger().info('=' * 50)
        
        # 메인 타이머 (1초마다 검출 시도)
        self.create_timer(1.0, self._main_loop)
        
        self.detection_count = 0
        self.grip_executed = False
        
        # 파일 준비 상태
        self.files_ready = False
        self.last_check_time = 0
        
        # 실시간 화면 표시
        self.last_detection = None
        if SHOW_DISPLAY:
            self.create_timer(0.05, self._display_loop)  # 20fps
            self.get_logger().info('🖥️ 실시간 화면 표시 활성화 (ESC: 종료)')
    
    def _load_yolo_model(self):
        """YOLO 모델 로드"""
        if os.path.exists(YOLO_MODEL_PATH):
            self.get_logger().info(f'📦 YOLO 모델 로딩: {YOLO_MODEL_PATH}')
            self.yolo_model = YOLO(YOLO_MODEL_PATH)
            self.get_logger().info('✅ YOLO 모델 로드 완료')
            return True
        else:
            self.get_logger().warn(f'⏳ YOLO 모델 대기 중: {YOLO_MODEL_PATH}')
            self.yolo_model = None
            return False
    
    def _load_calibration(self):
        """캘리브레이션 파일 로드"""
        if os.path.exists(CALIBRATION_FILE):
            self.T_gripper2camera = np.load(CALIBRATION_FILE).copy()
            translation = self.T_gripper2camera[:3, 3].copy()
            
            # 회전행렬 검증 (det=-1이면 left-handed, SVD로 수정)
            R = self.T_gripper2camera[:3, :3]
            det = np.linalg.det(R)
            if det < 0:
                U, S, Vt = np.linalg.svd(R)
                R_fixed = U @ Vt
                self.T_gripper2camera[:3, :3] = R_fixed
                self.get_logger().info(f'⚠️ 회전행렬 det={det:.2f} → SVD 수정됨')
            
            # 단위 확인: mm 단위면 그대로 사용 (>1), m 단위면 mm로 변환 (<1)
            if np.all(np.abs(translation) < 1.0):  # m 단위로 추정
                self.T_gripper2camera[:3, 3] *= 1000.0  # m -> mm
                self.get_logger().info(f'✅ 캘리브레이션 로드 (m→mm 변환)')
            else:
                self.get_logger().info(f'✅ 캘리브레이션 로드 (mm 단위)')
            
            final_trans = self.T_gripper2camera[:3, 3]
            self.get_logger().info(f'   Translation: ({final_trans[0]:.1f}, {final_trans[1]:.1f}, {final_trans[2]:.1f}) mm')
            return True
        else:
            self.get_logger().warn(f'⏳ 캘리브레이션 대기 중: {CALIBRATION_FILE}')
            self.T_gripper2camera = np.eye(4)
            return False
    
    def _check_files_ready(self):
        """파일 준비 상태 확인 및 로드"""
        if self.files_ready:
            return True
        
        # 5초마다 체크
        current_time = time.time()
        if current_time - self.last_check_time < 5.0:
            return False
        
        self.last_check_time = current_time
        
        yolo_ready = False
        calib_ready = False
        
        # YOLO 모델 체크
        if self.yolo_model is None:
            yolo_ready = self._load_yolo_model()
        else:
            yolo_ready = True
        
        # 캘리브레이션 체크
        if not os.path.exists(CALIBRATION_FILE) or np.array_equal(self.T_gripper2camera, np.eye(4)):
            calib_ready = self._load_calibration()
        else:
            calib_ready = True
        
        if yolo_ready and calib_ready:
            self.get_logger().info('🎉 모든 파일 준비 완료! 검출 시작합니다.')
            self.files_ready = True
            return True
        
        return False
    
    def _init_robot(self):
        """로봇 및 그리퍼 초기화"""
        # DR_init.__dsr__node는 main()에서 이미 설정됨
        
        from DSR_ROBOT2 import set_robot_mode, set_robot_system
        
        self.get_logger().info('🤖 로봇 초기화...')
        set_robot_mode(1)  # 자동 모드로 변경 (0: 수동, 1: 자동)
        set_robot_system(0)
        
        try:
            from onrobot import RG
            self.gripper = RG(GRIPPER_NAME, TOOLCHANGER_IP, TOOLCHANGER_PORT)
            self.gripper_available = True
            self.get_logger().info('✅ 그리퍼 연결 성공')
        except Exception as e:
            self.get_logger().warn(f'⚠️ 그리퍼 연결 실패: {e}')
            self.gripper_available = False
    
    def _color_callback(self, msg):
        """컬러 이미지 콜백"""
        img = self.bridge.imgmsg_to_cv2(msg, 'bgr8')
        # 카메라가 180도 회전된 경우 이미지 플립
        if CAMERA_FLIPPED:
            img = cv2.flip(img, -1)  # -1: 상하좌우 모두 플립 (180도 회전)
        self.color_image = img
    
    def _depth_callback(self, msg):
        """듀스 이미지 콜백"""
        img = self.bridge.imgmsg_to_cv2(msg, 'passthrough')
        # 카메라가 180도 회전된 경우 이미지 플립
        if CAMERA_FLIPPED:
            img = cv2.flip(img, -1)
        self.depth_image = img
    
    def _info_callback(self, msg):
        """카메라 정보 콜백"""
        if self.camera_info is None:
            self.camera_info = msg
            self.fx = msg.k[0]
            self.fy = msg.k[4]
            self.cx = msg.k[2]
            self.cy = msg.k[5]
            self.get_logger().info(f'📷 카메라 정보: fx={self.fx:.1f}, fy={self.fy:.1f}')
    
    def _detect_reddot(self):
        """YOLO로 빨간점 검출"""
        if self.yolo_model is None or self.color_image is None:
            return None
        
        # YOLO 추론
        results = self.yolo_model(self.color_image, verbose=False)
        
        if len(results) == 0 or results[0].boxes is None:
            return None
        
        boxes = results[0].boxes
        if len(boxes) == 0:
            return None
        
        # 가장 신뢰도 높은 검출 선택
        best_idx = boxes.conf.argmax().item()
        conf = boxes.conf[best_idx].item()
        
        if conf < CONFIDENCE_THRESHOLD:
            return None
        
        # 바운딩 박스 중심 계산
        box = boxes.xyxy[best_idx].cpu().numpy()
        cx = int((box[0] + box[2]) / 2)
        cy = int((box[1] + box[3]) / 2)
        
        return {
            'center': (cx, cy),
            'box': box,
            'confidence': conf
        }
    
    def _pixel_to_camera_coord(self, px, py):
        """픽셀 좌표 → 카메라 3D 좌표"""
        if self.depth_image is None or self.fx is None:
            return None
        
        # depth 값 (mm)
        depth = self.depth_image[py, px]
        
        if depth == 0 or depth > 2000:  # 유효하지 않은 depth
            return None
        
        # 카메라 좌표 (mm)
        z = float(depth)
        x = (px - self.cx) * z / self.fx
        y = (py - self.cy) * z / self.fy
        
        return np.array([x, y, z])
    
    def _camera_to_base_coord(self, camera_coord, robot_pos):
        """카메라 좌표 → 로봇 베이스 좌표"""
        coord = np.append(camera_coord, 1)  # Homogeneous
        
        base2gripper = posx_to_matrix(robot_pos)
        base2cam = base2gripper @ self.T_gripper2camera
        
        base_coord = np.dot(base2cam, coord)
        return base_coord[:3]
    
    def _display_loop(self):
        """실시간 화면 표시"""
        # 카메라 이미지가 없으면 대기 화면 표시
        if self.color_image is None:
            display_img = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(display_img, 'Waiting for camera...', (150, 240),
                       cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2)
            cv2.putText(display_img, f'Color Topic: {COLOR_TOPIC}', (50, 300),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
            cv2.putText(display_img, f'Depth Topic: {DEPTH_TOPIC}', (50, 330),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
            cv2.imshow('Reddot Detection', display_img)
            return
        
        # 화면에 표시할 이미지 복사
        display_img = self.color_image.copy()
        
        # YOLO 검출 수행 (화면용)
        if self.yolo_model is not None:
            results = self.yolo_model(display_img, verbose=False)
            
            if len(results) > 0 and results[0].boxes is not None:
                boxes = results[0].boxes
                for i in range(len(boxes)):
                    conf = boxes.conf[i].item()
                    if conf >= CONFIDENCE_THRESHOLD:
                        box = boxes.xyxy[i].cpu().numpy().astype(int)
                        x1, y1, x2, y2 = box
                        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                        
                        # 바운딩 박스 그리기
                        cv2.rectangle(display_img, (x1, y1), (x2, y2), (0, 0, 255), 2)
                        
                        # 중심점 그리기
                        cv2.circle(display_img, (cx, cy), 5, (0, 255, 0), -1)
                        cv2.circle(display_img, (cx, cy), 10, (0, 255, 0), 2)
                        
                        # 신뢰도 표시
                        label = f'Reddot {conf:.2f}'
                        cv2.putText(display_img, label, (x1, y1 - 10),
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
                        
                        # 깊이 정보 표시
                        if self.depth_image is not None and self.fx is not None:
                            depth = self.depth_image[cy, cx]
                            if depth > 0 and depth < 2000:
                                z = float(depth)
                                x_cam = (cx - self.cx) * z / self.fx
                                y_cam = (cy - self.cy) * z / self.fy
                                coord_text = f'Cam: ({x_cam:.0f}, {y_cam:.0f}, {z:.0f})mm'
                                cv2.putText(display_img, coord_text, (x1, y2 + 20),
                                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 2)
        
        # 상태 정보 표시
        status = 'READY' if self.files_ready else 'LOADING...'
        if self.grip_executed:
            status = 'GRIP DONE!'
        cv2.putText(display_img, f'Status: {status}', (10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.putText(display_img, f'Detections: {self.detection_count}/3', (10, 60),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        
        # 화면 표시 (waitKey는 main에서 처리)
        cv2.imshow('Reddot Detection', display_img)
        
        # RViz로도 이미지 퍼블리시
        try:
            img_msg = self.bridge.cv2_to_imgmsg(display_img, 'bgr8')
            img_msg.header.stamp = self.get_clock().now().to_msg()
            img_msg.header.frame_id = 'camera_color_optical_frame'
            self.detection_image_pub.publish(img_msg)
        except Exception as e:
            pass
    
    def _publish_grip_marker(self, base_coord):
        """그립 위치를 RViz 마커로 퍼블리시"""
        # PointStamped 퍼블리시
        point_msg = PointStamped()
        point_msg.header.stamp = self.get_clock().now().to_msg()
        point_msg.header.frame_id = 'base_link'
        point_msg.point.x = base_coord[0] / 1000.0  # mm -> m
        point_msg.point.y = base_coord[1] / 1000.0
        point_msg.point.z = base_coord[2] / 1000.0
        self.grip_point_pub.publish(point_msg)
        
        # Marker 퍼블리시 (구체)
        marker = Marker()
        marker.header.stamp = self.get_clock().now().to_msg()
        marker.header.frame_id = 'base_link'
        marker.ns = 'grip_position'
        marker.id = 0
        marker.type = Marker.SPHERE
        marker.action = Marker.ADD
        
        marker.pose.position.x = base_coord[0] / 1000.0
        marker.pose.position.y = base_coord[1] / 1000.0
        marker.pose.position.z = base_coord[2] / 1000.0
        marker.pose.orientation.w = 1.0
        
        marker.scale.x = 0.03  # 30mm 구체
        marker.scale.y = 0.03
        marker.scale.z = 0.03
        
        marker.color.r = 1.0
        marker.color.g = 0.0
        marker.color.b = 0.0
        marker.color.a = 0.8
        
        marker.lifetime.sec = 30
        
        self.grip_marker_pub.publish(marker)
        self.get_logger().info(f'📍 RViz 마커 퍼블리시: ({base_coord[0]:.1f}, {base_coord[1]:.1f}, {base_coord[2]:.1f}) mm')
    
    def _main_loop(self):
        """메인 루프: 검출 → 잡기"""
        if self.grip_executed:
            return
        
        # 파일 준비 확인
        if not self._check_files_ready():
            return
        
        if self.color_image is None or self.depth_image is None:
            return
        
        # 빨간점 검출
        detection = self._detect_reddot()
        
        if detection is None:
            self.detection_count = 0
            return
        
        self.detection_count += 1
        cx, cy = detection['center']
        conf = detection['confidence']
        
        self.get_logger().info(f'🔴 빨간점 검출! 픽셀=({cx}, {cy}), 신뢰도={conf:.2f}, 연속={self.detection_count}')
        
        # 3번 연속 검출 시 그립 실행
        if self.detection_count >= 3:
            self._execute_grip(cx, cy)
    
    def _execute_grip(self, px, py):
        """그립 실행"""
        self.get_logger().info('=' * 50)
        self.get_logger().info('🎯 그립 실행 시작!')
        
        # 1. 픽셀 → 카메라 좌표
        camera_coord = self._pixel_to_camera_coord(px, py)
        if camera_coord is None:
            self.get_logger().error('❌ Depth 값 없음')
            return
        
        self.get_logger().info(f'📍 카메라 좌표: ({camera_coord[0]:.1f}, {camera_coord[1]:.1f}, {camera_coord[2]:.1f}) mm')
        
        # 2. 빨간점에서 Z -35mm 오프셋 적용 (잡을 위치)
        grip_camera_coord = camera_coord.copy()
        grip_camera_coord[2] += REDDOT_Z_OFFSET  # 카메라 Z축 방향으로 오프셋
        
        self.get_logger().info(f'📍 잡을 위치 (카메라): ({grip_camera_coord[0]:.1f}, {grip_camera_coord[1]:.1f}, {grip_camera_coord[2]:.1f}) mm')
        
        # 3. 현재 로봇 위치 가져오기
        if TEST_MODE:
            # 테스트용 현재 위치
            robot_pos = [450.0, 0.0, 400.0, 0.0, 180.0, 0.0]
            self.get_logger().info(f'📍 현재 로봇 위치 (테스트): {robot_pos}')
        else:
            from DSR_ROBOT2 import get_current_posx
            robot_pos, _ = get_current_posx()
            self.get_logger().info(f'📍 현재 로봇 위치: {robot_pos}')
        
        # 4. 카메라 좌표 → 베이스 좌표
        base_coord = self._camera_to_base_coord(grip_camera_coord, robot_pos)
        
        self.get_logger().info(f'🎯 베이스 좌표: ({base_coord[0]:.1f}, {base_coord[1]:.1f}, {base_coord[2]:.1f}) mm')
        
        # RViz 마커 퍼블리시
        self._publish_grip_marker(base_coord)
        
        # 5. 로봇 이동 및 그립
        if TEST_MODE:
            self._simulate_grip(base_coord, robot_pos)
        else:
            self._do_grip(base_coord, robot_pos)
        
        self.grip_executed = True
        self.get_logger().info('✅ 그립 완료!')
        self.get_logger().info('=' * 50)
    
    def _simulate_grip(self, base_coord, robot_pos):
        """테스트 모드: 시뮬레이션"""
        rx, ry, rz = robot_pos[3], robot_pos[4], robot_pos[5]
        
        self.get_logger().info('\n[TEST MODE - 동작 시뮬레이션]')
        self.get_logger().info(f'1. 그리퍼 열기... 폭={GRIPPER_OPEN_WIDTH}mm')
        
        approach_z = base_coord[2] + Z_APPROACH_OFFSET
        self.get_logger().info(f'2. 접근 위치로 이동... ({base_coord[0]:.1f}, {base_coord[1]:.1f}, {approach_z:.1f})')
        
        self.get_logger().info(f'3. 타겟 위치로 내려가기... ({base_coord[0]:.1f}, {base_coord[1]:.1f}, {base_coord[2]:.1f})')
        
        self.get_logger().info(f'4. 그리퍼 닫기... 폭={GRIPPER_CLOSE_WIDTH}mm, 힘={GRIPPER_FORCE}N')
        
        lift_z = base_coord[2] + Z_LIFT_OFFSET
        self.get_logger().info(f'5. 들어올리기... ({base_coord[0]:.1f}, {base_coord[1]:.1f}, {lift_z:.1f})')
    
    def _do_grip(self, base_coord, robot_pos):
        """실제 그립 동작"""
        from DSR_ROBOT2 import movel, mwait
        from DR_common2 import posx
        
        rx, ry, rz = robot_pos[3], robot_pos[4], robot_pos[5]
        x, y, z = base_coord[0], base_coord[1], base_coord[2]
        
        # 안전: Z 최소값 설정 (바닥 충돌 방지)
        Z_MIN = 50.0  # mm - 최소 높이
        if z < Z_MIN:
            self.get_logger().warn(f'⚠️ Z={z:.1f}mm이 너무 낮음! Z={Z_MIN}mm로 조정')
            z = Z_MIN
        
        # 그립 방향 - 아래를 향하도록 고정 (ZYZ 오일러)
        # 기존 방향 대신 아래 방향 고정
        rx, ry, rz = 0.0, 180.0, 0.0  # 아래를 바라보는 자세
        self.get_logger().info(f'📐 그립 방향: rx={rx}, ry={ry}, rz={rz}')
        
        # 1. 그리퍼 열기
        self.get_logger().info(f'1. 그리퍼 열기... 폭={GRIPPER_OPEN_WIDTH}mm')
        if self.gripper_available:
            self.gripper.move_gripper(GRIPPER_OPEN_WIDTH * 10, force_val=GRIPPER_FORCE)
            time.sleep(1.0)
            while self.gripper.get_status()[0]:
                time.sleep(0.3)
        
        # 2. 접근 위치로 이동
        approach_z = z + Z_APPROACH_OFFSET
        self.get_logger().info(f'2. 접근 위치로 이동... Z={approach_z:.1f}mm')
        approach_pos = posx([x, y, approach_z, rx, ry, rz])
        movel(approach_pos, vel=VELOCITY, acc=ACC)
        mwait()
        
        # 3. 타겟 위치로 내려가기
        self.get_logger().info(f'3. 타겟 위치로 내려가기... Z={z:.1f}mm')
        target_pos = posx([x, y, z, rx, ry, rz])
        movel(target_pos, vel=30, acc=30)
        mwait()
        
        # 4. 그리퍼 닫기
        self.get_logger().info(f'4. 그리퍼 닫기... 힘={GRIPPER_FORCE}N')
        if self.gripper_available:
            self.gripper.close_gripper(force_val=GRIPPER_FORCE)
            while self.gripper.get_status()[0]:
                time.sleep(0.3)
        time.sleep(0.5)
        
        # 5. 들어올리기
        lift_z = z + Z_LIFT_OFFSET
        self.get_logger().info(f'5. 들어올리기... Z={lift_z:.1f}mm')
        lift_pos = posx([x, y, lift_z, rx, ry, rz])
        movel(lift_pos, vel=30, acc=30)
        mwait()


def main(args=None):
    rclpy.init(args=args)
    
    # DSR 노드 먼저 생성 (DSR_ROBOT2 import 전에 필요)
    dsr_node = rclpy.create_node("dsr_reddot_control", namespace=ROBOT_ID)
    DR_init.__dsr__node = dsr_node
    
    node = ReddotGrip()
    
    # Executor로 두 노드 모두 관리
    from rclpy.executors import SingleThreadedExecutor
    executor = SingleThreadedExecutor()
    executor.add_node(node)
    executor.add_node(dsr_node)
    
    try:
        # cv2.waitKey는 메인 스레드에서만 작동하므로 spin_once 사용
        while rclpy.ok():
            executor.spin_once(timeout_sec=0.01)
            
            # OpenCV 창 업데이트 (메인 스레드에서)
            if SHOW_DISPLAY:
                key = cv2.waitKey(1) & 0xFF
                if key == 27:  # ESC
                    print("\n🛑 ESC 종료")
                    break
    except KeyboardInterrupt:
        pass
    finally:
        if SHOW_DISPLAY:
            cv2.destroyAllWindows()
        executor.shutdown()
        node.destroy_node()
        dsr_node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()