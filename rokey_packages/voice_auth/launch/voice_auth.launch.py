#!/usr/bin/env python3
"""
Voice Auth Launch File
======================

사용:
    ros2 launch voice_auth voice_auth.launch.py
    ros2 launch voice_auth voice_auth.launch.py passphrase:=백두산
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
import os
from ament_index_python.packages import get_package_share_directory


def generate_launch_description():
    # 패키지 경로
    pkg_dir = get_package_share_directory('voice_auth')
    config_file = os.path.join(pkg_dir, 'config', 'voice_auth.yaml')
    
    # Launch arguments (질문-대답 암구호 체계)
    question_arg = DeclareLaunchArgument(
        'question',
        default_value='까마귀',
        description='질문 암구호 (초병이 말함)'
    )
    
    answer_arg = DeclareLaunchArgument(
        'answer',
        default_value='백두산',
        description='정답 암구호 (접근자가 대답해야 함)'
    )
    
    timeout_arg = DeclareLaunchArgument(
        'timeout',
        default_value='3.5',
        description='녹음 타임아웃 (초)'
    )
    
    enable_tts_arg = DeclareLaunchArgument(
        'enable_tts',
        default_value='true',
        description='TTS 경고 활성화'
    )
    
    mic_device_arg = DeclareLaunchArgument(
        'mic_device',
        default_value='10',
        description='마이크 장치 인덱스 (10=USB 웹캠)'
    )
    
    # Voice Auth Node
    voice_auth_node = Node(
        package='voice_auth',
        executable='voice_auth_node',
        name='voice_auth_node',
        output='screen',
        parameters=[
            config_file,
            {
                'question_passphrase': LaunchConfiguration('question'),
                'answer_passphrase': LaunchConfiguration('answer'),
                'default_timeout_sec': LaunchConfiguration('timeout'),
                'enable_tts': LaunchConfiguration('enable_tts'),
                'mic_device_index': LaunchConfiguration('mic_device'),
            }
        ],
    )
    
    return LaunchDescription([
        question_arg,
        answer_arg,
        timeout_arg,
        enable_tts_arg,
        mic_device_arg,
        voice_auth_node,
    ])
