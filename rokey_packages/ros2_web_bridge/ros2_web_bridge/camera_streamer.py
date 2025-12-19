#!/usr/bin/env python3
"""
Camera Streamer Node
- ROS2 이미지 토픽을 구독하여 JPEG으로 저장
- FastAPI가 MJPEG 스트리밍으로 제공
"""

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
import cv2
import os
import time
from threading import Lock

# 이미지 저장 경로
IMAGE_FILE = '/tmp/ros2_camera_frame.jpg'
IMAGE_LOCK_FILE = '/tmp/ros2_camera_frame.lock'


class CameraStreamer(Node):
    def __init__(self):
        super().__init__('camera_streamer')
        
        self.bridge = CvBridge()
        self.frame_lock = Lock()
        self.last_frame_time = 0
        
        # /face_detection/image 토픽 구독 (얼굴 검출 결과가 그려진 이미지)
        self.image_sub = self.create_subscription(
            Image,
            '/face_detection/image',
            self._image_callback,
            10
        )
        
        # 백업: raw 카메라 이미지
        self.raw_image_sub = self.create_subscription(
            Image,
            '/camera/color/image_raw',
            self._raw_image_callback,
            10
        )
        
        self.has_detection_image = False
        
        self.get_logger().info('Camera Streamer started!')
        self.get_logger().info('Subscribing to /face_detection/image and /camera/color/image_raw')

    def _image_callback(self, msg: Image):
        """얼굴 검출 이미지 콜백 (우선)"""
        self.has_detection_image = True
        self._save_frame(msg)

    def _raw_image_callback(self, msg: Image):
        """Raw 카메라 이미지 콜백 (백업)"""
        # face_detection 이미지가 없을 때만 사용
        if not self.has_detection_image:
            self._save_frame(msg)
        
        # 5초간 detection 이미지 없으면 raw 사용
        if time.time() - self.last_frame_time > 5:
            self.has_detection_image = False

    def _save_frame(self, msg: Image):
        """프레임을 JPEG로 저장"""
        try:
            # ROS Image -> OpenCV
            cv_image = self.bridge.imgmsg_to_cv2(msg, 'bgr8')
            
            # JPEG로 인코딩 및 저장
            with self.frame_lock:
                cv2.imwrite(IMAGE_FILE, cv_image, [cv2.IMWRITE_JPEG_QUALITY, 80])
                self.last_frame_time = time.time()
                
        except Exception as e:
            self.get_logger().error(f'Error saving frame: {e}')


def main(args=None):
    rclpy.init(args=args)
    node = CameraStreamer()
    
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
