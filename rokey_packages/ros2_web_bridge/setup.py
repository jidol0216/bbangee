from setuptools import setup

package_name = 'ros2_web_bridge'

setup(
    name=package_name,
    version='0.0.1',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='rokey',
    maintainer_email='rokey@example.com',
    description='ROS2 Web Bridge for bbangee system',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'bridge_node = ros2_web_bridge.bridge_node:main',
            'status_publisher = ros2_web_bridge.status_publisher:main',
            'robot_controller = ros2_web_bridge.robot_controller:main',
            'camera_streamer = ros2_web_bridge.camera_streamer:main',
            'collision_recovery = ros2_web_bridge.collision_recovery_node:main',
            'pistol_grip_node = ros2_web_bridge.pistol_grip_node:main',
            'check_start_position = ros2_web_bridge.check_start_position:main',
        ],
    },
)
