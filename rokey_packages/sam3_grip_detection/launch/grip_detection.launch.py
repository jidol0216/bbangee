#!/usr/bin/env python3
"""
Grip Detection Launch File
SAM3 그립 검출 노드 단독 실행
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
import os


def generate_launch_description():
    # Launch arguments
    sam3_path_arg = DeclareLaunchArgument(
        'sam3_path',
        default_value=os.path.expanduser('~/Desktop/2day/sam3/sam3'),
        description='SAM3 library path'
    )
    
    hf_token_arg = DeclareLaunchArgument(
        'hf_token',
        default_value='',
        description='HuggingFace token for model download'
    )
    
    process_rate_arg = DeclareLaunchArgument(
        'process_rate',
        default_value='10.0',
        description='Processing rate in Hz'
    )
    
    confidence_threshold_arg = DeclareLaunchArgument(
        'confidence_threshold',
        default_value='0.3',
        description='Detection confidence threshold'
    )
    
    camera_frame_arg = DeclareLaunchArgument(
        'camera_frame',
        default_value='camera_color_optical_frame',
        description='Camera frame ID'
    )
    
    # SAM3 Grip Node
    sam3_grip_node = Node(
        package='sam3_grip_detection',
        executable='sam3_grip_node',
        name='sam3_grip_node',
        output='screen',
        parameters=[{
            'sam3_path': LaunchConfiguration('sam3_path'),
            'hf_token': LaunchConfiguration('hf_token'),
            'process_rate': LaunchConfiguration('process_rate'),
            'confidence_threshold': LaunchConfiguration('confidence_threshold'),
            'camera_frame': LaunchConfiguration('camera_frame'),
            'min_depth': 0.1,
            'max_depth': 2.0,
            'voxel_size': 0.003,
            'gripper_max_width': 110.0,
            'gripper_min_width': 0.0,
            'rgb_topic': '/camera/camera/color/image_raw',
            'depth_topic': '/camera/camera/aligned_depth_to_color/image_raw',
            'camera_info_topic': '/camera/camera/aligned_depth_to_color/camera_info',
            'fast_mode': True,  # 빠른 모드 활성화
            'ultra_fast': True,  # 울트라 빠른 모드 (단일 프롬프트 + 리사이즈)
            'early_exit_score': 0.5,  # 낮추면 더 빨리 종료
        }]
    )
    
    return LaunchDescription([
        sam3_path_arg,
        hf_token_arg,
        process_rate_arg,
        confidence_threshold_arg,
        camera_frame_arg,
        sam3_grip_node,
    ])
