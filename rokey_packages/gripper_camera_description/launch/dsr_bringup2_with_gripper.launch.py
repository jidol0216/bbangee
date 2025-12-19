#!/usr/bin/env python3
# 
#  dsr_bringup2_with_gripper.launch.py
#  
#  Launches Doosan robot with OnRobot RG2 gripper and Intel RealSense D435i camera
#  Based on dsr_bringup2_rviz.launch.py with gripper_camera_description integration
#
#  Usage:
#    ros2 launch gripper_camera_description dsr_bringup2_with_gripper.launch.py mode:=real host:=192.168.1.100 port:=12345 model:=m0609
#

import os
import subprocess

from launch import LaunchDescription
from launch.actions import RegisterEventHandler, DeclareLaunchArgument, TimerAction, GroupAction
from launch.event_handlers import OnProcessExit
from launch.substitutions import Command, FindExecutable, PathJoinSubstitution, LaunchConfiguration, PythonExpression
from launch.conditions import IfCondition, UnlessCondition

from launch_ros.actions import Node, SetRemap
from launch_ros.substitutions import FindPackageShare
from launch_ros.parameter_descriptions import ParameterValue
from ament_index_python.packages import get_package_share_directory
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource


def read_update_rate():
    """Read update_rate from dsr_controller2 config yaml"""
    try:
        import yaml
        yaml_path = os.path.join(
            get_package_share_directory('dsr_controller2'),
            'config', 'dsr_update_rate.yaml'
        )
        if os.path.exists(yaml_path):
            with open(yaml_path, 'r') as f:
                config = yaml.safe_load(f)
                rate = config.get('update_rate', 100)
                print(f'[gripper_camera] Loaded update_rate from YAML: {rate}')
                return rate
    except Exception as e:
        print(f'[gripper_camera] Could not read update_rate: {e}')
    return 100


def generate_launch_description():
    ARGUMENTS = [ 
        DeclareLaunchArgument('name',  default_value='dsr01',     description='NAME_SPACE'),
        DeclareLaunchArgument('host',  default_value='127.0.0.1', description='ROBOT_IP'),
        DeclareLaunchArgument('port',  default_value='12345',     description='ROBOT_PORT'),
        DeclareLaunchArgument('mode',  default_value='virtual',   description='OPERATION MODE'),
        DeclareLaunchArgument('model', default_value='m0609',     description='ROBOT_MODEL'),
        DeclareLaunchArgument('color', default_value='white',     description='ROBOT_COLOR'),
        DeclareLaunchArgument('gui',   default_value='false',     description='Start RViz2'),
        DeclareLaunchArgument('gz',    default_value='false',     description='USE GAZEBO SIM'),
        DeclareLaunchArgument('rt_host', default_value='192.168.137.50', description='ROBOT_RT_IP'),
        DeclareLaunchArgument('remap_tf', default_value='false',  description='REMAP TF'),
    ]

    mode = LaunchConfiguration("mode")
    update_rate = str(read_update_rate())

    # ============================================================
    # URDF: Use gripper_camera_description's complete robot URDF
    # This includes: m0609 + OnRobot RG2 + RealSense D435i
    # ============================================================
    gripper_camera_pkg = get_package_share_directory('gripper_camera_description')
    urdf_file = os.path.join(gripper_camera_pkg, 'urdf', 'm0609_gripper_camera.urdf.xacro')
    
    # Process xacro at launch time
    robot_description_content = subprocess.check_output(['xacro', urdf_file]).decode('utf-8')
    robot_description = {"robot_description": ParameterValue(robot_description_content, value_type=str)}

    # For ros2_control_node, we need the original robot description with hardware interface
    dsr_xacro_path = os.path.join(get_package_share_directory('dsr_description2'), 'xacro')
    
    robot_description_control = Command(
        [
            PathJoinSubstitution([FindExecutable(name="xacro")]),
            " ",
            PathJoinSubstitution([
                FindPackageShare("dsr_description2"),
                "xacro",
                LaunchConfiguration('model'),
            ]),
            ".urdf.xacro",
            " name:=", LaunchConfiguration('name'),
            " host:=", LaunchConfiguration('host'),
            " rt_host:=", LaunchConfiguration('rt_host'),
            " port:=", LaunchConfiguration('port'),
            " mode:=", LaunchConfiguration('mode'),
            " model:=", LaunchConfiguration('model'),
            " update_rate:=", update_rate,
        ]
    )

    robot_controllers = [
        PathJoinSubstitution([
            FindPackageShare("dsr_controller2"),
            "config",
            "dsr_update_rate.yaml",
        ]),
        PathJoinSubstitution([
            FindPackageShare("dsr_controller2"),
            "config",
            "dsr_controller2.yaml",
        ])
    ]

    rviz_config_file = PathJoinSubstitution(
        [FindPackageShare("dsr_description2"), "rviz", "default.rviz"]
    )

    # ============================================================
    # Nodes
    # ============================================================
    
    run_emulator_node = Node(
        package="dsr_bringup2",
        executable="run_emulator",
        namespace=LaunchConfiguration('name'),
        parameters=[
            {"name":    LaunchConfiguration('name')},
            {"rate":    100},
            {"standby": 5000},
            {"command": True},
            {"host":    LaunchConfiguration('host')},
            {"port":    LaunchConfiguration('port')},
            {"mode":    LaunchConfiguration('mode')},
            {"model":   LaunchConfiguration('model')},
            {"gripper": "none"},
            {"mobile":  "none"},
            {"rt_host": LaunchConfiguration('rt_host')},
        ],
        condition=IfCondition(PythonExpression(["'", mode, "' == 'virtual'"])),
        output="screen",
    )

    # ros2_control_node uses the original URDF (with hardware interface)
    control_node = Node(
        package="controller_manager",
        executable="ros2_control_node",
        namespace=LaunchConfiguration('name'),
        parameters=[{"robot_description": robot_description_control}] + robot_controllers,
        output="both",
    )

    # robot_state_publisher uses the COMPLETE URDF (with gripper + camera)
    robot_state_pub_node = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        name='robot_state_publisher',
        namespace=LaunchConfiguration('name'),
        output='both',
        parameters=[robot_description]
    )

    rviz_node = Node(
        package="rviz2",
        executable="rviz2",
        namespace=LaunchConfiguration('name'),
        name="rviz2",
        output="log",
        arguments=["-d", rviz_config_file],
    )

    joint_state_broadcaster_spawner = Node(
        package="controller_manager",
        namespace=LaunchConfiguration('name'),
        executable="spawner",
        arguments=["joint_state_broadcaster", "-c", "controller_manager"],
    )

    robot_controller_spawner = Node(
        package="controller_manager",
        namespace=LaunchConfiguration('name'),
        executable="spawner",
        arguments=["dsr_controller2", "-c", "controller_manager"],
    )

    # ============================================================
    # Gripper Joint State Publisher
    # Publishes joint states for gripper fingers using joint_state_publisher_gui
    # or joint_state_publisher with preset values
    # Joint names from onrobot_ros: gripper_joint, gripper_mirror_joint,
    # gripper_finger_1_truss_arm_joint, gripper_finger_1_finger_tip_joint,
    # gripper_finger_2_truss_arm_joint, gripper_finger_2_finger_tip_joint
    # ============================================================
    gripper_joint_state_publisher = Node(
        package='joint_state_publisher',
        executable='joint_state_publisher',
        name='gripper_joint_state_publisher',
        namespace=LaunchConfiguration('name'),
        parameters=[{
            'source_list': ['joint_states'],  # Subscribe to robot joint states
            'zeros': {
                # Main gripper joint (controls finger 1 moment arm)
                'gripper_joint': 0.4,
                # Mirror joint (controls finger 2 moment arm) - mimic of gripper_joint
                'gripper_mirror_joint': 0.4,
                # Truss arm joints (mimic of gripper_joint)
                'gripper_finger_1_truss_arm_joint': 0.4,
                'gripper_finger_2_truss_arm_joint': 0.4,
                # Finger tip joints (mimic of gripper_joint with negative axis)
                'gripper_finger_1_finger_tip_joint': 0.4,
                'gripper_finger_2_finger_tip_joint': 0.4,
            }
        }],
        output='screen',
    )

    # Combined joint state relay (merges robot + gripper joint states)
    # This is needed because robot_state_publisher expects all joints in one topic

    # ============================================================
    # TF handling (same as original dsr_bringup2_rviz)
    # ============================================================
    original_tf_nodes = GroupAction(
        actions=[
            robot_state_pub_node,
            rviz_node
        ],
        condition=UnlessCondition(LaunchConfiguration('remap_tf'))
    )

    remapped_tf_nodes = GroupAction(
        actions=[
            SetRemap(src='/tf', dst='tf'),
            SetRemap(src='/tf_static', dst='tf_static'),
            robot_state_pub_node,
            rviz_node
        ],
        condition=IfCondition(LaunchConfiguration('remap_tf'))
    )

    # ============================================================
    # Launch sequence
    # ============================================================
    nodes = [
        run_emulator_node,
        original_tf_nodes,
        remapped_tf_nodes,
        robot_controller_spawner,
        joint_state_broadcaster_spawner,
        control_node,
        gripper_joint_state_publisher,
    ]

    return LaunchDescription(ARGUMENTS + nodes)
