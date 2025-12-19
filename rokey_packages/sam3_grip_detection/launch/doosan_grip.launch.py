#!/usr/bin/env python3
"""
Doosan M0609 Robot Integration Launch File
두산 로봇과 연동하여 그래스핑 실행
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from ament_index_python.packages import get_package_share_directory
import os


def generate_launch_description():
    # Package directories
    pkg_sam3_grip = get_package_share_directory('sam3_grip_detection')
    
    # Launch arguments
    robot_model_arg = DeclareLaunchArgument(
        'robot_model',
        default_value='m0609',
        description='Doosan robot model (m0609, m1013, etc.)'
    )
    
    robot_ip_arg = DeclareLaunchArgument(
        'robot_ip',
        default_value='192.168.137.100',
        description='Robot IP address'
    )
    
    sam3_path_arg = DeclareLaunchArgument(
        'sam3_path',
        default_value=os.path.expanduser('~/Desktop/2day/sam3/sam3'),
        description='SAM3 library path'
    )
    
    # SAM3 Grip Detection Node
    sam3_grip_node = Node(
        package='sam3_grip_detection',
        executable='sam3_grip_node',
        name='sam3_grip_node',
        output='screen',
        parameters=[{
            'sam3_path': LaunchConfiguration('sam3_path'),
            'process_rate': 2.0,
            'confidence_threshold': 0.3,
            'camera_frame': 'camera_color_optical_frame',
            'robot_base_frame': 'base_link',
            'min_depth': 0.1,
            'max_depth': 2.0,
            'voxel_size': 0.003,
            'gripper_max_width': 110.0,
            'gripper_min_width': 0.0,
        }]
    )
    
    # Static TF: camera_link -> base_link (예시, 실제 캘리브레이션 필요)
    # 실제 사용 시 Hand-Eye Calibration 결과로 대체
    static_tf_camera = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='camera_to_base_tf',
        arguments=[
            '0.5', '0.0', '0.8',      # x, y, z (meters)
            '0.0', '0.7071', '0.0', '0.7071',  # qx, qy, qz, qw (looking down)
            'base_link', 'camera_link'
        ]
    )
    
    # RViz
    rviz_config = os.path.join(pkg_sam3_grip, 'rviz', 'grip_detection.rviz')
    rviz_node = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2',
        arguments=['-d', rviz_config],
        output='screen',
    )
    
    return LaunchDescription([
        robot_model_arg,
        robot_ip_arg,
        sam3_path_arg,
        sam3_grip_node,
        static_tf_camera,
        rviz_node,
    ])
