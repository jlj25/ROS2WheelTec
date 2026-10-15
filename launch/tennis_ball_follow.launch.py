import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    package_share = get_package_share_directory('tennis_ball_follower_ros2')
    default_params = os.path.join(package_share, 'config', 'tennis_ball.yaml')

    params_file = LaunchConfiguration('params_file')
    run_controller = LaunchConfiguration('run_controller')

    return LaunchDescription([
        DeclareLaunchArgument(
            'params_file',
            default_value=default_params,
            description='Path to the tracker and follower parameter file.'),
        DeclareLaunchArgument(
            'run_controller',
            default_value='false',
            description='Start the /cmd_vel controller. It still starts disabled.'),
        Node(
            package='tennis_ball_follower_ros2',
            executable='tennis_ball_tracker',
            name='tennis_ball_tracker',
            output='screen',
            parameters=[params_file]),
        Node(
            package='tennis_ball_follower_ros2',
            executable='tennis_ball_follower',
            name='tennis_ball_follower',
            output='screen',
            parameters=[params_file],
            condition=IfCondition(run_controller)),
    ])

