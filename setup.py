from glob import glob
import os

from setuptools import find_packages, setup


package_name = 'tennis_ball_follower_ros2'

setup(
    name=package_name,
    version='0.3.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
         ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.launch.py')),
        (os.path.join('share', package_name, 'config'), glob('config/*.yaml')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='wheeltec',
    maintainer_email='wheeltec@localhost',
    description='Safe RGB-D tennis-ball follower for WHEELTEC ROS 2 robots.',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'tennis_ball_tracker = tennis_ball_follower_ros2.tennis_ball_tracker:main',
            'ball_yolo_tracker = tennis_ball_follower_ros2.ball_yolo_tracker:main',
            'tennis_ball_follower = tennis_ball_follower_ros2.tennis_ball_follower:main',
        ],
    },
)

