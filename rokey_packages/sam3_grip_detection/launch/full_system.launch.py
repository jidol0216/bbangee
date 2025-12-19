#!/usr/bin/env python3
"""
Full System Launch File
RealSense 카메라 + SAM3 그립 검출 + RViz2 통합 실행
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
    use_rviz_arg = DeclareLaunchArgument(
        'use_rviz',
        default_value='true',
        description='Launch RViz2'
    )
    
    sam3_path_arg = DeclareLaunchArgument(
        'sam3_path',
        default_value=os.path.expanduser('~/Desktop/2day/sam3/sam3'),
        description='SAM3 library path'
    )
    
    hf_token_arg = DeclareLaunchArgument(
        'hf_token',
        default_value='',
        description='HuggingFace token'
    )
    
    process_rate_arg = DeclareLaunchArgument(
        'process_rate',
        default_value='2.0',
        description='Processing rate in Hz'
    )
    
    # RealSense Camera Node
    # realsense_node = IncludeLaunchDescription(
    #     PythonLaunchDescriptionSource([
    #         PathJoinSubstitution([
    #             FindPackageShare('realsense2_camera'),
    #             'launch',
    #             'rs_launch.py'
    #         ])
    #     ]),
    #     launch_arguments={
    #         'align_depth.enable': 'true',
    #         'pointcloud.enable': 'false',
    #         'depth_module.profile': '640x480x30',
    #         'rgb_camera.profile': '640x480x30',
    #     }.items()
    # )
    
    # RealSense 노드 (직접 실행)
    realsense_node = Node(
        package='realsense2_camera',
        executable='realsense2_camera_node',
        name='camera',
        namespace='camera',
        output='screen',
        parameters=[{
            'align_depth.enable': True,
            'pointcloud.enable': False,
            'depth_module.profile': '640x480x30',
            'rgb_camera.profile': '640x480x30',
        }]
    )
    
    # SAM3 Grip Detection Node
    sam3_grip_node = Node(
        package='sam3_grip_detection',
        executable='sam3_grip_node',
        name='sam3_grip_node',
        output='screen',
        parameters=[{
            'sam3_path': LaunchConfiguration('sam3_path'),
            'hf_token': LaunchConfiguration('hf_token'),
            'process_rate': LaunchConfiguration('process_rate'),
            'confidence_threshold': 0.3,
            'camera_frame': 'camera_color_optical_frame',
            'min_depth': 0.1,
            'max_depth': 2.0,
            'voxel_size': 0.003,
            'gripper_max_width': 110.0,
            'gripper_min_width': 0.0,
            'rgb_topic': '/camera/camera/color/image_raw',
            'depth_topic': '/camera/camera/aligned_depth_to_color/image_raw',
            'camera_info_topic': '/camera/camera/aligned_depth_to_color/camera_info',
        }]
    )
    
    # RViz2
    rviz_config = os.path.join(pkg_sam3_grip, 'rviz', 'grip_detection.rviz')
    rviz_node = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2',
        arguments=['-d', rviz_config],
        output='screen',
    )
    
    return LaunchDescription([
        use_rviz_arg,
        sam3_path_arg,
        hf_token_arg,
        process_rate_arg,
        realsense_node,
        sam3_grip_node,
        rviz_node,
    ])
