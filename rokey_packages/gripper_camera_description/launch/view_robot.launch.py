#!/usr/bin/env python3
"""
Launch file for viewing the gripper + camera assembly in RViz
"""

import os
import subprocess
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from ament_index_python.packages import get_package_share_directory


def generate_launch_description():
    # Package paths
    pkg_path = get_package_share_directory('gripper_camera_description')
    
    # URDF file
    urdf_file = os.path.join(pkg_path, 'urdf', 'm0609_gripper_camera.urdf.xacro')
    
    # Process xacro to get robot description
    robot_description_content = subprocess.check_output(['xacro', urdf_file]).decode('utf-8')
    robot_description = ParameterValue(robot_description_content, value_type=str)

    return LaunchDescription([
        # Robot State Publisher
        Node(
            package='robot_state_publisher',
            executable='robot_state_publisher',
            name='robot_state_publisher',
            output='screen',
            parameters=[{
                'robot_description': robot_description,
                'use_sim_time': False,
            }]
        ),

        # Joint State Publisher GUI
        Node(
            package='joint_state_publisher_gui',
            executable='joint_state_publisher_gui',
            name='joint_state_publisher_gui',
            output='screen',
        ),

        # RViz
        Node(
            package='rviz2',
            executable='rviz2',
            name='rviz2',
            output='screen',
        ),
    ])
