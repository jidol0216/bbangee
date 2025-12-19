from setuptools import setup, find_packages
import os
from glob import glob

package_name = 'voice_auth'

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
            glob('launch/*.launch.py')),
        # Config files
        (os.path.join('share', package_name, 'config'), 
            glob('config/*.yaml')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='rokey',
    maintainer_email='rokey@example.com',
    description='Voice-based Passphrase Authentication for CoBotSentry',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'voice_auth_node = voice_auth.voice_auth_node:main',
        ],
    },
)
