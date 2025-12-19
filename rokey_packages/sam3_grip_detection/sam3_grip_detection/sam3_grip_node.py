#!/usr/bin/env python3
"""
SAM3 Grip Detection Node
메인 ROS2 노드 - 실시간 권총 손잡이 검출 및 그래스핑 정보 발행

Subscribed Topics:
    /camera/color/image_raw (sensor_msgs/Image)
    /camera/aligned_depth_to_color/image_raw (sensor_msgs/Image)
    /camera/aligned_depth_to_color/camera_info (sensor_msgs/CameraInfo)

Published Topics:
    /grip/mask (sensor_msgs/Image)
    /grip/pointcloud (sensor_msgs/PointCloud2)
    /grip/detection_image (sensor_msgs/Image)
    /grip/grasp_pose (geometry_msgs/PoseStamped)
    /grip/gripper_width (std_msgs/Float64)
    /grip/grasp_info (std_msgs/String)
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
import numpy as np
import cv2
import json
from threading import Lock
from datetime import datetime

# ROS2 메시지
from sensor_msgs.msg import Image, CameraInfo, PointCloud2, PointField
from geometry_msgs.msg import PoseStamped
from std_msgs.msg import Float64, String, Header
from visualization_msgs.msg import Marker
from cv_bridge import CvBridge

# 로컬 모듈
from .utils.sam3_wrapper import Sam3Wrapper
from .utils.depth_to_pointcloud import DepthToPointCloud, create_pointcloud2_msg
from .utils.grasp_utils import (
    GraspUtils, 
    create_pose_stamped_msg, 
    create_grasp_marker
)


class Sam3GripNode(Node):
    """SAM3 기반 권총 손잡이 검출 ROS2 노드"""
    
    def __init__(self):
        super().__init__('sam3_grip_node')
        
        # 파라미터 선언
        self._declare_parameters()
        
        # 파라미터 로드
        self._load_parameters()
        
        # 컴포넌트 초기화
        self.cv_bridge = CvBridge()
        self.data_lock = Lock()
        
        # 데이터 버퍼
        self.rgb_image = None
        self.depth_image = None
        self.camera_info = None
        self.last_process_time = None
        
        # SAM3 래퍼
        self.sam3 = Sam3Wrapper(
            sam3_path=self.sam3_path,
            hf_token=self.hf_token
        )
        
        # Depth-3D 변환기
        self.depth_converter = DepthToPointCloud(
            min_depth=self.min_depth,
            max_depth=self.max_depth
        )
        
        # 그래스핑 유틸리티
        self.grasp_utils = GraspUtils(
            gripper_max_width=self.gripper_max_width,
            gripper_min_width=self.gripper_min_width
        )
        
        # QoS 설정
        sensor_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=1
        )
        
        # Subscribers
        self.rgb_sub = self.create_subscription(
            Image,
            self.rgb_topic,
            self._rgb_callback,
            sensor_qos
        )
        
        self.depth_sub = self.create_subscription(
            Image,
            self.depth_topic,
            self._depth_callback,
            sensor_qos
        )
        
        self.camera_info_sub = self.create_subscription(
            CameraInfo,
            self.camera_info_topic,
            self._camera_info_callback,
            sensor_qos
        )
        
        # Publishers
        self.mask_pub = self.create_publisher(Image, '/grip/mask', 10)
        self.pointcloud_pub = self.create_publisher(PointCloud2, '/grip/pointcloud', 10)
        self.detection_image_pub = self.create_publisher(Image, '/grip/detection_image', 10)
        self.grasp_pose_pub = self.create_publisher(PoseStamped, '/grip/grasp_pose', 10)
        self.gripper_width_pub = self.create_publisher(Float64, '/grip/gripper_width', 10)
        self.grasp_info_pub = self.create_publisher(String, '/grip/grasp_info', 10)
        self.marker_pub = self.create_publisher(Marker, '/grip/grasp_marker', 10)
        
        # 처리 타이머
        timer_period = 1.0 / self.process_rate
        self.process_timer = self.create_timer(timer_period, self._process_callback)
        
        # 모델 로드
        self.model_loaded = False
        self.get_logger().info("SAM3 Grip Detection Node initialized")
        self.get_logger().info(f"  RGB Topic: {self.rgb_topic}")
        self.get_logger().info(f"  Depth Topic: {self.depth_topic}")
        self.get_logger().info(f"  Process Rate: {self.process_rate} Hz")
        
        # 모델 로드 시작
        self._load_model()
    
    def _declare_parameters(self):
        """ROS2 파라미터 선언"""
        self.declare_parameter('sam3_path', '')
        self.declare_parameter('hf_token', '')
        self.declare_parameter('text_prompt', 'gun grip')
        self.declare_parameter('confidence_threshold', 0.3)
        self.declare_parameter('process_rate', 10.0)  # 높은 시도 빈도
        self.declare_parameter('min_depth', 0.1)
        self.declare_parameter('max_depth', 2.0)
        self.declare_parameter('voxel_size', 0.003)
        self.declare_parameter('gripper_max_width', 110.0)
        self.declare_parameter('gripper_min_width', 0.0)
        self.declare_parameter('camera_frame', 'camera_color_optical_frame')
        self.declare_parameter('robot_base_frame', 'base_link')
        self.declare_parameter('fast_mode', True)  # 빠른 모드 (상위 프롬프트만 사용)
        self.declare_parameter('ultra_fast', True)  # 울트라 빠른 모드 (단일 프롬프트 + 리사이즈)
        self.declare_parameter('early_exit_score', 0.6)  # 조기 종료 점수
        
        # 토픽 파라미터 (RealSense 기본값)
        self.declare_parameter('rgb_topic', '/camera/camera/color/image_raw')
        self.declare_parameter('depth_topic', '/camera/camera/aligned_depth_to_color/image_raw')
        self.declare_parameter('camera_info_topic', '/camera/camera/aligned_depth_to_color/camera_info')
    
    def _load_parameters(self):
        """파라미터 로드"""
        self.sam3_path = self.get_parameter('sam3_path').value
        if not self.sam3_path:
            import os
            self.sam3_path = os.path.expanduser('~/Desktop/2day/sam3/sam3')
        
        self.hf_token = self.get_parameter('hf_token').value
        self.text_prompt = self.get_parameter('text_prompt').value
        self.confidence_threshold = self.get_parameter('confidence_threshold').value
        self.process_rate = self.get_parameter('process_rate').value
        self.min_depth = self.get_parameter('min_depth').value
        self.max_depth = self.get_parameter('max_depth').value
        self.voxel_size = self.get_parameter('voxel_size').value
        self.gripper_max_width = self.get_parameter('gripper_max_width').value
        self.gripper_min_width = self.get_parameter('gripper_min_width').value
        self.camera_frame = self.get_parameter('camera_frame').value
        self.robot_base_frame = self.get_parameter('robot_base_frame').value
        
        self.rgb_topic = self.get_parameter('rgb_topic').value
        self.depth_topic = self.get_parameter('depth_topic').value
        self.camera_info_topic = self.get_parameter('camera_info_topic').value
        self.fast_mode = self.get_parameter('fast_mode').value
        self.ultra_fast = self.get_parameter('ultra_fast').value
        self.early_exit_score = self.get_parameter('early_exit_score').value
    
    def _load_model(self):
        """SAM3 모델 로드"""
        self.get_logger().info("Loading SAM3 model...")
        
        if self.sam3.load_model():
            self.model_loaded = True
            self.get_logger().info("SAM3 model loaded successfully!")
        else:
            self.get_logger().error("Failed to load SAM3 model")
    
    def _rgb_callback(self, msg: Image):
        """RGB 이미지 콜백"""
        with self.data_lock:
            try:
                self.rgb_image = self.cv_bridge.imgmsg_to_cv2(msg, 'rgb8')
            except Exception as e:
                self.get_logger().error(f"RGB conversion error: {e}")
    
    def _depth_callback(self, msg: Image):
        """Depth 이미지 콜백"""
        with self.data_lock:
            try:
                self.depth_image = self.cv_bridge.imgmsg_to_cv2(msg, 'passthrough')
            except Exception as e:
                self.get_logger().error(f"Depth conversion error: {e}")
    
    def _camera_info_callback(self, msg: CameraInfo):
        """CameraInfo 콜백"""
        with self.data_lock:
            self.camera_info = msg
            self.depth_converter.update_from_camera_info_msg(msg)
    
    def _process_callback(self):
        """주기적 처리 콜백"""
        if not self.model_loaded:
            return
        
        with self.data_lock:
            if self.rgb_image is None or self.depth_image is None:
                return
            
            rgb = self.rgb_image.copy()
            depth = self.depth_image.copy()
        
        try:
            self._detect_and_publish(rgb, depth)
        except Exception as e:
            self.get_logger().error(f"Processing error: {e}")
    
    def _detect_and_publish(self, rgb_image: np.ndarray, depth_image: np.ndarray):
        """검출 및 결과 발행"""
        from PIL import Image as PILImage
        
        start_time = datetime.now()
        
        # PIL 이미지로 변환
        pil_image = PILImage.fromarray(rgb_image)
        
        # SAM3 검출 (ultra_fast 모드로 최적화)
        result = self.sam3.find_gun_grip(
            pil_image,
            confidence_threshold=self.confidence_threshold,
            fast_mode=self.fast_mode,
            ultra_fast=self.ultra_fast,
            resize_for_speed=True,
            early_exit_score=self.early_exit_score
        )
        
        if result is None:
            self.get_logger().debug("No grip detected")
            return
        
        # 타임스탬프
        now = self.get_clock().now().to_msg()
        header = Header()
        header.stamp = now
        header.frame_id = self.camera_frame
        
        # 마스크 이미지 발행
        mask_np = self.sam3.get_mask_image(result, rgb_image.shape[:2])
        self._publish_mask(mask_np, header)
        
        # 검출 시각화 이미지 발행
        detection_image = self._create_detection_image(rgb_image, result, mask_np)
        self._publish_detection_image(detection_image, header)
        
        # 3D 포인트클라우드 생성
        points_3d, rgb_values = self.depth_converter.depth_to_3d_points(
            depth_image, 
            mask_np, 
            rgb_image
        )
        
        if len(points_3d) > 0:
            # 다운샘플링
            points_3d, rgb_values = self.depth_converter.downsample_voxel(
                points_3d, rgb_values, self.voxel_size
            )
            
            # PointCloud2 발행
            self._publish_pointcloud(points_3d, rgb_values, header)
            
            # 그래스핑 포즈 계산 및 발행
            self._publish_grasp_info(
                result, points_3d, mask_np, header
            )
        
        # 처리 시간 로깅
        elapsed = (datetime.now() - start_time).total_seconds()
        self.get_logger().info(
            f"Detection: score={result['total_score']:.2f}, "
            f"prompt={result['prompt']}, "
            f"points={len(points_3d)}, "
            f"time={elapsed:.2f}s"
        )
    
    def _publish_mask(self, mask: np.ndarray, header: Header):
        """마스크 이미지 발행"""
        try:
            msg = self.cv_bridge.cv2_to_imgmsg(mask, 'mono8')
            msg.header = header
            self.mask_pub.publish(msg)
        except Exception as e:
            self.get_logger().error(f"Mask publish error: {e}")
    
    def _publish_detection_image(self, image: np.ndarray, header: Header):
        """검출 시각화 이미지 발행"""
        try:
            msg = self.cv_bridge.cv2_to_imgmsg(image, 'rgb8')
            msg.header = header
            self.detection_image_pub.publish(msg)
        except Exception as e:
            self.get_logger().error(f"Detection image publish error: {e}")
    
    def _publish_pointcloud(self, 
                           points_3d: np.ndarray, 
                           rgb_values: np.ndarray,
                           header: Header):
        """PointCloud2 발행"""
        try:
            msg = create_pointcloud2_msg(points_3d, rgb_values, header)
            self.pointcloud_pub.publish(msg)
        except Exception as e:
            self.get_logger().error(f"PointCloud publish error: {e}")
    
    def _publish_grasp_info(self,
                           result: dict,
                           points_3d: np.ndarray,
                           mask: np.ndarray,
                           header: Header):
        """그래스핑 정보 발행"""
        # 2D 정보 추출
        info_2d = self.grasp_utils.extract_grasp_info_2d(
            mask,
            result['box_coords'],
            mask.shape[:2]
        )
        
        # 3D 정보 추출
        info_3d = self.grasp_utils.calculate_grasp_pose_3d(points_3d)
        
        if info_3d:
            # PoseStamped 발행
            pose_msg = create_pose_stamped_msg(info_3d, header)
            self.grasp_pose_pub.publish(pose_msg)
            
            # 그리퍼 너비 발행
            width_msg = Float64()
            width_msg.data = info_3d['recommended_gripper_width_mm']
            self.gripper_width_pub.publish(width_msg)
            
            # 마커 발행
            marker_msg = create_grasp_marker(info_3d, header)
            self.marker_pub.publish(marker_msg)
        
        # JSON 정보 발행
        full_info = self.grasp_utils.create_grasp_info_json(
            info_2d, info_3d, result['total_score']
        )
        
        info_msg = String()
        info_msg.data = json.dumps(full_info, indent=2)
        self.grasp_info_pub.publish(info_msg)
    
    def _create_detection_image(self,
                               rgb_image: np.ndarray,
                               result: dict,
                               mask: np.ndarray) -> np.ndarray:
        """검출 결과 시각화 이미지 생성"""
        output = rgb_image.copy()
        
        # 마스크 오버레이 (반투명 초록색)
        mask_colored = np.zeros_like(output)
        mask_colored[mask > 127] = [0, 255, 0]
        output = cv2.addWeighted(output, 0.7, mask_colored, 0.3, 0)
        
        # 바운딩 박스
        x1, y1, x2, y2 = result['box_coords']
        cv2.rectangle(output, (x1, y1), (x2, y2), (0, 255, 0), 2)
        
        # 중심점
        cx, cy = result['center']
        cv2.circle(output, (cx, cy), 5, (255, 0, 0), -1)
        
        # 텍스트 정보
        text = f"{result['prompt']}: {result['total_score']:.2f}"
        cv2.putText(output, text, (x1, y1-10), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
        
        return output


class GripPoseCalculator(Node):
    """그래스핑 포즈만 계산하는 경량 노드 (선택적)"""
    
    def __init__(self):
        super().__init__('grip_pose_calculator')
        self.get_logger().info("Grip Pose Calculator Node initialized")


def main(args=None):
    rclpy.init(args=args)
    
    node = Sam3GripNode()
    
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        try:
            rclpy.shutdown()
        except Exception:
            pass  # Already shutdown


if __name__ == '__main__':
    main()
