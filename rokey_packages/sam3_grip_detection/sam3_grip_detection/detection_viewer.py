#!/usr/bin/env python3
"""
Detection Viewer Node
OpenCV 창으로 실시간 카메라 이미지 + 디텍션 결과를 시각화하는 노드

Subscribed Topics:
    /camera/camera/color/image_raw (sensor_msgs/Image) - 실시간 카메라 이미지
    /grip/detection_image (sensor_msgs/Image) - 디텍션 결과 이미지
    /grip/mask (sensor_msgs/Image) - 디텍션 마스크
    /grip/gripper_width (std_msgs/Float64) - 그리퍼 너비
    /grip/grasp_pose (geometry_msgs/PoseStamped) - 그래스핑 포즈
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
import numpy as np
import cv2
from cv_bridge import CvBridge

from sensor_msgs.msg import Image
from std_msgs.msg import Float64
from geometry_msgs.msg import PoseStamped


class DetectionViewer(Node):
    """디텍션 결과를 OpenCV 창으로 시각화하는 노드"""
    
    def __init__(self):
        super().__init__('detection_viewer')
        
        # 파라미터 선언
        self.declare_parameter('window_name', 'Grip Detection Viewer')
        self.declare_parameter('window_width', 1280)
        self.declare_parameter('window_height', 720)
        self.declare_parameter('show_info', True)
        self.declare_parameter('rgb_topic', '/camera/camera/color/image_raw')
        
        # 파라미터 로드
        self.window_name = self.get_parameter('window_name').value
        self.window_width = self.get_parameter('window_width').value
        self.window_height = self.get_parameter('window_height').value
        self.show_info = self.get_parameter('show_info').value
        self.rgb_topic = self.get_parameter('rgb_topic').value
        
        # CV Bridge
        self.cv_bridge = CvBridge()
        
        # 데이터 버퍼
        self.live_image = None  # 실시간 카메라 이미지
        self.detection_image = None  # 디텍션 결과 이미지
        self.detection_mask = None  # 디텍션 마스크
        self.gripper_width = None
        self.grasp_pose = None
        
        # 실시간 카메라용 QoS (BEST_EFFORT)
        sensor_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=1
        )
        
        # Subscribers - 실시간 카메라 이미지
        self.rgb_sub = self.create_subscription(
            Image,
            self.rgb_topic,
            self._rgb_callback,
            sensor_qos
        )
        
        # 디텍션 결과
        self.detection_sub = self.create_subscription(
            Image,
            '/grip/detection_image',
            self._detection_callback,
            10
        )
        
        # 디텍션 마스크
        self.mask_sub = self.create_subscription(
            Image,
            '/grip/mask',
            self._mask_callback,
            10
        )
        
        self.width_sub = self.create_subscription(
            Float64,
            '/grip/gripper_width',
            self._width_callback,
            10
        )
        
        self.pose_sub = self.create_subscription(
            PoseStamped,
            '/grip/grasp_pose',
            self._pose_callback,
            10
        )
        
        # OpenCV 윈도우 생성
        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(self.window_name, self.window_width, self.window_height)
        
        # 디스플레이 타이머 (30 FPS)
        self.display_timer = self.create_timer(1.0 / 30.0, self._display_callback)
        
        self.get_logger().info(f"Detection Viewer started - Window: {self.window_name}")
        self.get_logger().info("Press 'q' or ESC to quit, 'm' to toggle mode")
        
        # 표시 모드: 'live' = 실시간+마스크, 'detection' = 디텍션 결과만
        self.display_mode = 'live'
    
    def _rgb_callback(self, msg: Image):
        """실시간 카메라 이미지 콜백"""
        try:
            self.live_image = self.cv_bridge.imgmsg_to_cv2(msg, 'rgb8')
        except Exception as e:
            self.get_logger().error(f"RGB image conversion error: {e}")
    
    def _detection_callback(self, msg: Image):
        """디텍션 이미지 콜백"""
        try:
            self.detection_image = self.cv_bridge.imgmsg_to_cv2(msg, 'rgb8')
        except Exception as e:
            self.get_logger().error(f"Detection image conversion error: {e}")
    
    def _mask_callback(self, msg: Image):
        """디텍션 마스크 콜백"""
        try:
            self.detection_mask = self.cv_bridge.imgmsg_to_cv2(msg, 'mono8')
        except Exception as e:
            self.get_logger().error(f"Mask conversion error: {e}")
    
    def _width_callback(self, msg: Float64):
        """그리퍼 너비 콜백"""
        self.gripper_width = msg.data
    
    def _pose_callback(self, msg: PoseStamped):
        """그래스핑 포즈 콜백"""
        self.grasp_pose = msg
    
    def _display_callback(self):
        """디스플레이 업데이트 콜백"""
        display_image = None
        
        if self.display_mode == 'live' and self.live_image is not None:
            # 실시간 이미지에 마스크 오버레이
            display_image = self.live_image.copy()
            
            if self.detection_mask is not None:
                # 마스크를 초록색으로 오버레이
                mask_colored = np.zeros_like(display_image)
                mask_colored[:, :, 1] = self.detection_mask  # 초록 채널
                display_image = cv2.addWeighted(display_image, 0.7, mask_colored, 0.3, 0)
            
        elif self.detection_image is not None:
            display_image = self.detection_image.copy()
        
        if display_image is None:
            # 대기 화면 표시
            wait_image = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(wait_image, "Waiting for camera...", 
                       (150, 240), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            cv2.imshow(self.window_name, wait_image)
        else:
            # RGB -> BGR 변환 (OpenCV용)
            display_image = cv2.cvtColor(display_image, cv2.COLOR_RGB2BGR)
            
            # 정보 오버레이
            if self.show_info:
                display_image = self._add_info_overlay(display_image)
            
            cv2.imshow(self.window_name, display_image)
        
        # 키 입력 처리
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q') or key == 27:  # 'q' 또는 ESC
            self.get_logger().info("Quit requested")
            cv2.destroyAllWindows()
            rclpy.shutdown()
        elif key == ord('m'):  # 모드 전환
            self.display_mode = 'detection' if self.display_mode == 'live' else 'live'
            self.get_logger().info(f"Display mode: {self.display_mode}")
    
    def _add_info_overlay(self, image: np.ndarray) -> np.ndarray:
        """정보 오버레이 추가"""
        h, w = image.shape[:2]
        
        # 반투명 배경 박스
        overlay = image.copy()
        cv2.rectangle(overlay, (10, 10), (350, 150), (0, 0, 0), -1)
        image = cv2.addWeighted(overlay, 0.6, image, 0.4, 0)
        
        # 텍스트 색상
        text_color = (0, 255, 0)
        
        # 모드 표시
        y_offset = 30
        mode_text = f"Mode: {self.display_mode.upper()} (press 'm' to toggle)"
        cv2.putText(image, mode_text, (20, y_offset), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
        y_offset += 25
        
        # 그리퍼 너비 정보
        if self.gripper_width is not None:
            width_text = f"Gripper Width: {self.gripper_width:.1f} mm"
            cv2.putText(image, width_text, (20, y_offset), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, text_color, 2)
            y_offset += 30
        
        # 그래스핑 포즈 정보
        if self.grasp_pose is not None:
            pos = self.grasp_pose.pose.position
            pos_text = f"Position: ({pos.x:.3f}, {pos.y:.3f}, {pos.z:.3f})"
            cv2.putText(image, pos_text, (20, y_offset), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, text_color, 2)
            y_offset += 25
            
            ori = self.grasp_pose.pose.orientation
            ori_text = f"Orientation: ({ori.x:.2f}, {ori.y:.2f}, {ori.z:.2f}, {ori.w:.2f})"
            cv2.putText(image, ori_text, (20, y_offset), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, text_color, 1)
        
        # 조작 안내
        cv2.putText(image, "q:quit | m:mode", (w - 150, h - 20), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        
        return image
    
    def destroy_node(self):
        """노드 종료 시 정리"""
        cv2.destroyAllWindows()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    
    node = DetectionViewer()
    
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
