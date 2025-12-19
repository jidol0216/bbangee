#!/usr/bin/env python3
"""
Image Flip Launch File
======================
180도 회전된 RealSense 카메라용 이미지 반전 노드 실행

Usage:
  ros2 launch camera_utils image_flip.launch.py
"""

from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        Node(
            package='camera_utils',
            executable='image_flip_node',
            name='image_flip_node',
            output='screen',
            parameters=[{
                'input_color_topic': '/camera/camera/color/image_raw',
                'input_depth_topic': '/camera/camera/aligned_depth_to_color/image_raw',
                'input_camera_info_topic': '/camera/camera/color/camera_info',
                'output_color_topic': '/camera/flipped/color/image_raw',
                'output_depth_topic': '/camera/flipped/depth/image_raw',
                'output_camera_info_topic': '/camera/flipped/camera_info',
            }]
        ),
    ])
