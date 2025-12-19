from setuptools import setup, find_packages
import os
from glob import glob

package_name = 'sam3_grip_detection'

setup(
    name=package_name,
    version='1.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        # Launch files
        (os.path.join('share', package_name, 'launch'), 
            glob(os.path.join('launch', '*launch.[pxy][yma]*'))),
        # Config files
        (os.path.join('share', package_name, 'config'), 
            glob(os.path.join('config', '*.yaml'))),
        # RViz files
        (os.path.join('share', package_name, 'rviz'), 
            glob(os.path.join('rviz', '*.rviz'))),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Rokey',
    maintainer_email='rokey@example.com',
    description='SAM3-based gun grip 3D segmentation for robot grasping',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'sam3_grip_node = sam3_grip_detection.sam3_grip_node:main',
            'grip_pose_calculator = sam3_grip_detection.grip_pose_calculator:main',
            'detection_viewer = sam3_grip_detection.detection_viewer:main',
            'tracking_viewer = sam3_grip_detection.tracking_viewer:main',
            'go_pick = sam3_grip_detection.go_pick:main',
            'test_publisher = sam3_grip_detection.test_publisher:main',
        ],
    },
)
