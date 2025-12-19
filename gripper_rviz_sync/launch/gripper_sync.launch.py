#!/usr/bin/env python3
"""
OnRobot RG2 Gripper RViz Sync Launch File

토픽 구조 (직관적인 명명):
  /robot/joint_states     ← 로봇 6축 (dsr01에서 리맵)
  /gripper/joint_states   ← 그리퍼 2축 (이 패키지에서 발행)
  /gripper/width/current  ← 현재 그리퍼 폭 (mm)
  /gripper/width/command  ← 그리퍼 폭 명령 (mm)
  /gripper/force/command  ← 그리퍼 힘 명령 (N)
  /gripper/grip_detected  ← 물체 감지 여부
  /merged/joint_states    ← 합쳐진 8축
  /joint_states           ← RViz용 (merged와 동일)
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
import os
from ament_index_python.packages import get_package_share_directory


def generate_launch_description():
    # Launch arguments
    modbus_host_arg = DeclareLaunchArgument(
        'modbus_host',
        default_value='192.168.1.1',
        description='OnRobot Compute Box IP address'
    )
    
    modbus_port_arg = DeclareLaunchArgument(
        'modbus_port',
        default_value='502',
        description='Modbus TCP port'
    )
    
    # 1. Gripper State Publisher - 그리퍼 상태를 Modbus로 읽어서 발행
    gripper_state_publisher = Node(
        package='gripper_rviz_sync',
        executable='gripper_state_publisher.py',
        name='gripper_state_publisher',
        output='screen',
        parameters=[{
            'modbus_host': LaunchConfiguration('modbus_host'),
            'modbus_port': LaunchConfiguration('modbus_port'),
            'modbus_unit_id': 65,
            'publish_rate': 30.0,
            # 실제 URDF 조인트 이름 (onrobot_description 패키지)
            'main_joint_name': 'gripper_joint',
            'mirror_joint_name': 'gripper_mirror_joint',
            'max_width_mm': 110.0,
            'joint_max_angle': 1.3,  # URDF limit: 0~1.3 rad
        }]
    )
    
    # 2. Gripper Controller - 그리퍼 제어 명령 처리
    gripper_controller = Node(
        package='gripper_rviz_sync',
        executable='gripper_controller.py',
        name='gripper_controller',
        output='screen',
        parameters=[{
            'modbus_host': LaunchConfiguration('modbus_host'),
            'modbus_port': LaunchConfiguration('modbus_port'),
            'modbus_unit_id': 65,
            'default_force': 20.0,
            'open_width': 110.0,  # RG2 최대 개방폭
            'close_width': 0.0,
        }]
    )
    
    # 3. Joint State Merger - 그리퍼 조인트만 /dsr01/joint_states에 발행
    joint_state_merger = Node(
        package='gripper_rviz_sync',
        executable='joint_state_merger.py',
        name='joint_state_merger',
        output='screen',
        parameters=[{
            'gripper_joint_states_topic': '/gripper/joint_states',
            'output_joint_states_topic': '/dsr01/joint_states',
        }]
    )
    
    return LaunchDescription([
        modbus_host_arg,
        modbus_port_arg,
        gripper_state_publisher,
        gripper_controller,
        joint_state_merger,
    ])
