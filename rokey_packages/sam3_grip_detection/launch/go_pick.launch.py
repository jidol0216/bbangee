#!/usr/bin/env python3
"""
Go Pick Launch File
SAM3 검출 좌표 기반 로봇 피킹 노드 실행
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    # Launch arguments
    z_offset_arg = DeclareLaunchArgument(
        'z_offset',
        default_value='50.0',
        description='Z-axis offset in mm (adjust based on experiments)'
    )
    
    approach_height_arg = DeclareLaunchArgument(
        'approach_height',
        default_value='100.0',
        description='Approach height in mm'
    )
    
    velocity_arg = DeclareLaunchArgument(
        'velocity',
        default_value='30',
        description='Robot movement velocity'
    )
    
    acceleration_arg = DeclareLaunchArgument(
        'acceleration',
        default_value='30',
        description='Robot movement acceleration'
    )
    
    auto_pick_arg = DeclareLaunchArgument(
        'auto_pick',
        default_value='false',
        description='Enable automatic picking when pose received'
    )
    
    # Go Pick Node
    go_pick_node = Node(
        package='sam3_grip_detection',
        executable='go_pick',
        name='go_pick_node',
        output='screen',
        parameters=[{
            'z_offset': LaunchConfiguration('z_offset'),
            'approach_height': LaunchConfiguration('approach_height'),
            'velocity': LaunchConfiguration('velocity'),
            'acceleration': LaunchConfiguration('acceleration'),
            'auto_pick': LaunchConfiguration('auto_pick'),
        }]
    )
    
    return LaunchDescription([
        z_offset_arg,
        approach_height_arg,
        velocity_arg,
        acceleration_arg,
        auto_pick_arg,
        go_pick_node,
    ])
