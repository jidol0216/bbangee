#!/usr/bin/env python3
"""
Tracking-based Detection Viewer
SAM3 검출 결과를 OpenCV 트래커로 실시간 추적하는 뷰어

전략: 
- SAM3는 느리게 (~0.8초) 검출
- 그 사이에 OpenCV 트래커로 bbox를 실시간 추적
- 검출이 업데이트되면 트래커 재초기화
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
import numpy as np
import cv2
from cv_bridge import CvBridge
import time

from sensor_msgs.msg import Image
from std_msgs.msg import Float64
from geometry_msgs.msg import PoseStamped


class TrackingViewer(Node):
    """트래킹 기반 실시간 뷰어"""
    
    def __init__(self):
        super().__init__('tracking_viewer')
        
        # 파라미터
        self.declare_parameter('window_name', 'Grip Tracking Viewer')
        self.declare_parameter('rgb_topic', '/camera/camera/color/image_raw')
        
        self.window_name = self.get_parameter('window_name').value
        self.rgb_topic = self.get_parameter('rgb_topic').value
        
        # CV Bridge
        self.cv_bridge = CvBridge()
        
        # 데이터 버퍼
        self.live_image = None
        self.detection_mask = None
        self.gripper_width = None
        self.grasp_pose = None
        
        # 트래커 관련
        self.tracker = None
        self.tracking_bbox = None
        self.tracker_initialized = False
        self.last_detection_time = 0
        self.detection_timeout = 2.0  # 2초 안에 새 검출 없으면 트래커 리셋
        
        # FPS 계산
        self.fps = 0
        self.frame_count = 0
        self.fps_start_time = time.time()
        
        # QoS
        sensor_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=1
        )
        
        # Subscribers
        self.rgb_sub = self.create_subscription(
            Image, self.rgb_topic, self._rgb_callback, sensor_qos)
        
        self.mask_sub = self.create_subscription(
            Image, '/grip/mask', self._mask_callback, 10)
        
        self.width_sub = self.create_subscription(
            Float64, '/grip/gripper_width', self._width_callback, 10)
        
        self.pose_sub = self.create_subscription(
            PoseStamped, '/grip/grasp_pose', self._pose_callback, 10)
        
        # OpenCV 윈도우
        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(self.window_name, 1280, 720)
        
        # 디스플레이 타이머 (60 FPS 목표)
        self.display_timer = self.create_timer(1.0 / 60.0, self._display_callback)
        
        self.get_logger().info(f"Tracking Viewer started")
        self.get_logger().info("Press 'q' to quit, 'r' to reset tracker")
    
    def _rgb_callback(self, msg: Image):
        """실시간 카메라 이미지 콜백"""
        try:
            self.live_image = self.cv_bridge.imgmsg_to_cv2(msg, 'bgr8')
        except Exception as e:
            self.get_logger().error(f"RGB conversion error: {e}")
    
    def _mask_callback(self, msg: Image):
        """마스크 콜백 - 트래커 업데이트"""
        try:
            mask = self.cv_bridge.imgmsg_to_cv2(msg, 'mono8')
            self.detection_mask = mask
            
            # 마스크에서 바운딩 박스 추출
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if contours:
                largest = max(contours, key=cv2.contourArea)
                x, y, w, h = cv2.boundingRect(largest)
                
                # 트래커 초기화/재초기화
                if self.live_image is not None:
                    self._init_tracker((x, y, w, h))
                    self.last_detection_time = time.time()
                    
        except Exception as e:
            self.get_logger().error(f"Mask conversion error: {e}")
    
    def _width_callback(self, msg: Float64):
        self.gripper_width = msg.data
    
    def _pose_callback(self, msg: PoseStamped):
        self.grasp_pose = msg
    
    def _init_tracker(self, bbox):
        """트래커 초기화 (또는 bbox 저장)"""
        try:
            # OpenCV contrib 트래커 시도
            tracker_created = False
            for tracker_class in ['TrackerCSRT', 'TrackerKCF', 'TrackerMIL']:
                try:
                    # 새 API
                    tracker_fn = getattr(cv2, tracker_class, None)
                    if tracker_fn:
                        self.tracker = tracker_fn.create()
                        tracker_created = True
                        break
                except:
                    pass
                
                try:
                    # legacy API
                    legacy = getattr(cv2, 'legacy', None)
                    if legacy:
                        tracker_fn = getattr(legacy, f'{tracker_class}_create', None)
                        if tracker_fn:
                            self.tracker = tracker_fn()
                            tracker_created = True
                            break
                except:
                    pass
            
            if tracker_created:
                self.tracker.init(self.live_image, bbox)
                self.tracker_initialized = True
                self.get_logger().info(f"Tracker initialized with bbox: {bbox}")
            else:
                # 트래커 없이 bbox만 저장 (fallback)
                self.tracker = None
                self.tracker_initialized = True
                self.get_logger().warn("No tracker available, using mask overlay only")
            
            self.tracking_bbox = bbox
            
        except Exception as e:
            self.get_logger().error(f"Tracker init error: {e}")
            # fallback: bbox만 저장
            self.tracking_bbox = bbox
            self.tracker = None
            self.tracker_initialized = True
    
    def _update_tracker(self, frame):
        """트래커 업데이트"""
        if not self.tracker_initialized:
            return None
        
        # 타임아웃 체크
        if time.time() - self.last_detection_time > self.detection_timeout:
            self.tracker_initialized = False
            return None
        
        # 트래커가 있으면 업데이트
        if self.tracker is not None:
            try:
                success, bbox = self.tracker.update(frame)
                if success:
                    self.tracking_bbox = tuple(map(int, bbox))
                    return self.tracking_bbox
            except:
                pass
        
        # 트래커 없거나 실패하면 마지막 bbox 반환
        return self.tracking_bbox
    
    def _display_callback(self):
        """디스플레이 업데이트"""
        if self.live_image is None:
            wait_img = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(wait_img, "Waiting for camera...", 
                       (150, 240), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            cv2.imshow(self.window_name, wait_img)
            cv2.waitKey(1)
            return
        
        display = self.live_image.copy()
        
        # 트래커 업데이트 및 bbox 그리기
        bbox = self._update_tracker(self.live_image)
        if bbox:
            x, y, w, h = bbox
            cv2.rectangle(display, (x, y), (x+w, y+h), (0, 255, 0), 3)
            
            # 중심점
            cx, cy = x + w//2, y + h//2
            cv2.circle(display, (cx, cy), 5, (0, 0, 255), -1)
            
            # 마스크 오버레이 (있으면)
            if self.detection_mask is not None:
                mask_colored = np.zeros_like(display)
                # 마스크 크기가 다르면 리사이즈
                if self.detection_mask.shape[:2] != display.shape[:2]:
                    mask_resized = cv2.resize(self.detection_mask, 
                                             (display.shape[1], display.shape[0]))
                else:
                    mask_resized = self.detection_mask
                mask_colored[:, :, 1] = mask_resized  # 초록색
                display = cv2.addWeighted(display, 0.7, mask_colored, 0.3, 0)
        
        # FPS 계산
        self.frame_count += 1
        elapsed = time.time() - self.fps_start_time
        if elapsed > 1.0:
            self.fps = self.frame_count / elapsed
            self.frame_count = 0
            self.fps_start_time = time.time()
        
        # 정보 오버레이
        display = self._add_info_overlay(display)
        
        cv2.imshow(self.window_name, display)
        
        # 키 처리
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q') or key == 27:
            self.get_logger().info("Quit requested")
            cv2.destroyAllWindows()
            rclpy.shutdown()
        elif key == ord('r'):
            self.tracker_initialized = False
            self.get_logger().info("Tracker reset")
    
    def _add_info_overlay(self, image):
        """정보 오버레이"""
        h, w = image.shape[:2]
        
        # 배경
        overlay = image.copy()
        cv2.rectangle(overlay, (10, 10), (350, 160), (0, 0, 0), -1)
        image = cv2.addWeighted(overlay, 0.6, image, 0.4, 0)
        
        y = 30
        color = (0, 255, 0)
        
        # FPS
        cv2.putText(image, f"FPS: {self.fps:.1f}", (20, y), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        y += 30
        
        # 트래킹 상태
        status = "TRACKING" if self.tracker_initialized else "WAITING"
        status_color = (0, 255, 0) if self.tracker_initialized else (0, 0, 255)
        cv2.putText(image, f"Status: {status}", (20, y), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, status_color, 2)
        y += 30
        
        # 그리퍼 너비
        if self.gripper_width:
            cv2.putText(image, f"Gripper: {self.gripper_width:.1f} mm", (20, y), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
            y += 25
        
        # 포즈
        if self.grasp_pose:
            p = self.grasp_pose.pose.position
            cv2.putText(image, f"Pos: ({p.x:.3f}, {p.y:.3f}, {p.z:.3f})", (20, y), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
        
        # 조작 안내
        cv2.putText(image, "q:quit | r:reset", (w - 130, h - 20), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        
        return image
    
    def destroy_node(self):
        cv2.destroyAllWindows()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = TrackingViewer()
    
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        cv2.destroyAllWindows()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
