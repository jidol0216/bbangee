#!/usr/bin/env python3
"""
Grip Pose Calculator Node
마스크와 Depth 정보로부터 그래스핑 포즈만 계산하는 경량 노드

sam3_grip_node.py가 무거울 경우 분리하여 사용
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
import numpy as np
import json
from threading import Lock

from sensor_msgs.msg import Image, CameraInfo, PointCloud2
from geometry_msgs.msg import PoseStamped
from std_msgs.msg import Float64, String, Header
from visualization_msgs.msg import Marker
from cv_bridge import CvBridge

from .utils.depth_to_pointcloud import DepthToPointCloud, create_pointcloud2_msg
from .utils.grasp_utils import (
    GraspUtils,
    create_pose_stamped_msg,
    create_grasp_marker
)


class GripPoseCalculator(Node):
    """그래스핑 포즈 계산 노드"""
    
    def __init__(self):
        super().__init__('grip_pose_calculator')
        
        # 파라미터
        self.declare_parameter('min_depth', 0.1)
        self.declare_parameter('max_depth', 2.0)
        self.declare_parameter('voxel_size', 0.003)
        self.declare_parameter('gripper_max_width', 110.0)
        self.declare_parameter('gripper_min_width', 0.0)
        self.declare_parameter('camera_frame', 'camera_color_optical_frame')
        
        self.min_depth = self.get_parameter('min_depth').value
        self.max_depth = self.get_parameter('max_depth').value
        self.voxel_size = self.get_parameter('voxel_size').value
        self.gripper_max_width = self.get_parameter('gripper_max_width').value
        self.gripper_min_width = self.get_parameter('gripper_min_width').value
        self.camera_frame = self.get_parameter('camera_frame').value
        
        # 초기화
        self.cv_bridge = CvBridge()
        self.data_lock = Lock()
        
        self.mask_image = None
        self.depth_image = None
        self.rgb_image = None
        self.camera_info = None
        
        # 컴포넌트
        self.depth_converter = DepthToPointCloud(
            min_depth=self.min_depth,
            max_depth=self.max_depth
        )
        
        self.grasp_utils = GraspUtils(
            gripper_max_width=self.gripper_max_width,
            gripper_min_width=self.gripper_min_width
        )
        
        # QoS
        sensor_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=1
        )
        
        # Subscribers
        self.mask_sub = self.create_subscription(
            Image,
            '/grip/mask',
            self._mask_callback,
            10
        )
        
        self.depth_sub = self.create_subscription(
            Image,
            '/camera/camera/aligned_depth_to_color/image_raw',
            self._depth_callback,
            sensor_qos
        )
        
        self.rgb_sub = self.create_subscription(
            Image,
            '/camera/camera/color/image_raw',
            self._rgb_callback,
            sensor_qos
        )
        
        self.camera_info_sub = self.create_subscription(
            CameraInfo,
            '/camera/camera/aligned_depth_to_color/camera_info',
            self._camera_info_callback,
            sensor_qos
        )
        
        # Publishers
        self.pointcloud_pub = self.create_publisher(PointCloud2, '/grip/pointcloud', 10)
        self.grasp_pose_pub = self.create_publisher(PoseStamped, '/grip/grasp_pose', 10)
        self.gripper_width_pub = self.create_publisher(Float64, '/grip/gripper_width', 10)
        self.grasp_info_pub = self.create_publisher(String, '/grip/grasp_info', 10)
        self.marker_pub = self.create_publisher(Marker, '/grip/grasp_marker', 10)
        
        self.get_logger().info("Grip Pose Calculator Node initialized")
    
    def _mask_callback(self, msg: Image):
        """마스크 수신 시 처리"""
        with self.data_lock:
            try:
                self.mask_image = self.cv_bridge.imgmsg_to_cv2(msg, 'mono8')
            except Exception as e:
                self.get_logger().error(f"Mask conversion error: {e}")
                return
        
        self._process()
    
    def _depth_callback(self, msg: Image):
        """Depth 이미지 콜백"""
        with self.data_lock:
            try:
                self.depth_image = self.cv_bridge.imgmsg_to_cv2(msg, 'passthrough')
            except Exception as e:
                self.get_logger().error(f"Depth conversion error: {e}")
    
    def _rgb_callback(self, msg: Image):
        """RGB 이미지 콜백"""
        with self.data_lock:
            try:
                self.rgb_image = self.cv_bridge.imgmsg_to_cv2(msg, 'rgb8')
            except Exception as e:
                self.get_logger().error(f"RGB conversion error: {e}")
    
    def _camera_info_callback(self, msg: CameraInfo):
        """CameraInfo 콜백"""
        with self.data_lock:
            self.camera_info = msg
            self.depth_converter.update_from_camera_info_msg(msg)
    
    def _process(self):
        """마스크 기반 3D 처리"""
        with self.data_lock:
            if self.mask_image is None or self.depth_image is None:
                return
            
            mask = self.mask_image.copy()
            depth = self.depth_image.copy()
            rgb = self.rgb_image.copy() if self.rgb_image is not None else None
        
        # 헤더
        now = self.get_clock().now().to_msg()
        header = Header()
        header.stamp = now
        header.frame_id = self.camera_frame
        
        # 3D 포인트 생성
        points_3d, rgb_values = self.depth_converter.depth_to_3d_points(
            depth, mask, rgb
        )
        
        if len(points_3d) < 10:
            self.get_logger().debug("Not enough points for grasp calculation")
            return
        
        # 다운샘플링
        points_3d, rgb_values = self.depth_converter.downsample_voxel(
            points_3d, rgb_values, self.voxel_size
        )
        
        # PointCloud2 발행
        try:
            pc_msg = create_pointcloud2_msg(points_3d, rgb_values, header)
            self.pointcloud_pub.publish(pc_msg)
        except Exception as e:
            self.get_logger().error(f"PointCloud publish error: {e}")
        
        # 그래스핑 포즈 계산
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
            
            # JSON 발행
            info_msg = String()
            info_msg.data = json.dumps(info_3d, indent=2)
            self.grasp_info_pub.publish(info_msg)
            
            self.get_logger().info(
                f"Grasp: width={info_3d['grip_width_mm']:.1f}mm, "
                f"compatible={info_3d['gripper_compatible']}"
            )


def main(args=None):
    rclpy.init(args=args)
    
    node = GripPoseCalculator()
    
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
