#!/usr/bin/env python3
"""
Image Flip Node
===============
RealSense 카메라가 180도 회전 장착된 경우 이미지를 반전시키는 노드

입력 토픽:
  /camera/camera/color/image_raw
  /camera/camera/aligned_depth_to_color/image_raw

출력 토픽:
  /camera/flipped/color/image_raw
  /camera/flipped/depth/image_raw

사용법:
  ros2 run camera_utils image_flip_node
"""

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image, CameraInfo
from cv_bridge import CvBridge
import cv2


class ImageFlipNode(Node):
    def __init__(self):
        super().__init__('image_flip_node')
        
        self.bridge = CvBridge()
        
        # Parameters
        self.declare_parameter('input_color_topic', '/camera/camera/color/image_raw')
        self.declare_parameter('input_depth_topic', '/camera/camera/aligned_depth_to_color/image_raw')
        self.declare_parameter('input_camera_info_topic', '/camera/camera/color/camera_info')
        self.declare_parameter('output_color_topic', '/camera/flipped/color/image_raw')
        self.declare_parameter('output_depth_topic', '/camera/flipped/depth/image_raw')
        self.declare_parameter('output_camera_info_topic', '/camera/flipped/camera_info')
        
        input_color = self.get_parameter('input_color_topic').value
        input_depth = self.get_parameter('input_depth_topic').value
        input_info = self.get_parameter('input_camera_info_topic').value
        output_color = self.get_parameter('output_color_topic').value
        output_depth = self.get_parameter('output_depth_topic').value
        output_info = self.get_parameter('output_camera_info_topic').value
        
        # Subscribers
        self.color_sub = self.create_subscription(
            Image, input_color, self.color_callback, 10)
        self.depth_sub = self.create_subscription(
            Image, input_depth, self.depth_callback, 10)
        self.info_sub = self.create_subscription(
            CameraInfo, input_info, self.info_callback, 10)
        
        # Publishers
        self.color_pub = self.create_publisher(Image, output_color, 10)
        self.depth_pub = self.create_publisher(Image, output_depth, 10)
        self.info_pub = self.create_publisher(CameraInfo, output_info, 10)
        
        self.get_logger().info('🔄 Image Flip Node started')
        self.get_logger().info(f'   Color: {input_color} → {output_color}')
        self.get_logger().info(f'   Depth: {input_depth} → {output_depth}')
    
    def flip_image(self, img):
        """180도 회전 (상하좌우 반전)"""
        return cv2.flip(img, -1)  # -1 = flip both axes
    
    def color_callback(self, msg: Image):
        try:
            # ROS Image → OpenCV
            cv_image = self.bridge.imgmsg_to_cv2(msg, desired_encoding='passthrough')
            
            # 180도 반전
            flipped = self.flip_image(cv_image)
            
            # OpenCV → ROS Image
            flipped_msg = self.bridge.cv2_to_imgmsg(flipped, encoding=msg.encoding)
            flipped_msg.header = msg.header
            
            self.color_pub.publish(flipped_msg)
        except Exception as e:
            self.get_logger().error(f'Color flip error: {e}')
    
    def depth_callback(self, msg: Image):
        try:
            # ROS Image → OpenCV
            cv_image = self.bridge.imgmsg_to_cv2(msg, desired_encoding='passthrough')
            
            # 180도 반전
            flipped = self.flip_image(cv_image)
            
            # OpenCV → ROS Image
            flipped_msg = self.bridge.cv2_to_imgmsg(flipped, encoding=msg.encoding)
            flipped_msg.header = msg.header
            
            self.depth_pub.publish(flipped_msg)
        except Exception as e:
            self.get_logger().error(f'Depth flip error: {e}')
    
    def info_callback(self, msg: CameraInfo):
        """CameraInfo도 전달 (principal point 조정 필요 시 여기서 처리)"""
        # 180도 회전 시 principal point (cx, cy)는 변경 필요:
        # cx_new = width - cx
        # cy_new = height - cy
        # 하지만 URDF에서 TF가 처리하므로 그대로 전달
        new_msg = msg
        self.info_pub.publish(new_msg)


def main(args=None):
    rclpy.init(args=args)
    node = ImageFlipNode()
    
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
