from setuptools import setup, find_packages
import os
from glob import glob

package_name = 'face_tracking'

setup(
    name=package_name,
    version='2.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        # Launch files
        (os.path.join('share', package_name, 'launch'), 
            glob('launch/*.launch.py')),
        # Config files
        (os.path.join('share', package_name, 'config'), 
            glob('config/*.yaml')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='rokey',
    maintainer_email='rokey@example.com',
    description='Face Tracking Package - Refactored Version',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            # Detection
            'face_detection_node = face_tracking.detection.face_detection_node:main',
            # Tracking
            'face_tracking_node = face_tracking.tracking.face_tracking_node:main',
            # Control
            'joint_tracking_node = face_tracking.control.joint_tracking_node:main',
        ],
    },
)
