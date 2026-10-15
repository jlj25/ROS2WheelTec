#!/usr/bin/env python3
"""Safety-gated velocity controller for a tracked tennis ball."""

import math
import time

from geometry_msgs.msg import Twist
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, qos_profile_sensor_data
from sensor_msgs.msg import LaserScan
from std_msgs.msg import Bool, String
from turn_on_wheeltec_robot.msg import Position


def clamp(value, lower, upper):
    return max(lower, min(upper, value))


def normalize_angle(angle):
    return math.atan2(math.sin(angle), math.cos(angle))


class TennisBallFollower(Node):
    """Convert fresh target observations into bounded, obstacle-gated Twist commands."""

    def __init__(self):
        super().__init__('tennis_ball_follower')
        self._declare_parameters()
        self._load_parameters()

        qos = QoSProfile(depth=10)
        self.cmd_pub = self.create_publisher(Twist, self.cmd_vel_topic, qos)
        self.state_pub = self.create_publisher(String, self.state_topic, qos)
        self.position_sub = self.create_subscription(
            Position, self.position_topic, self._position_callback, qos)
        self.visible_sub = self.create_subscription(
            Bool, self.visible_topic, self._visible_callback, qos)
        self.enable_sub = self.create_subscription(
            Bool, self.enable_topic, self._enable_callback, qos)
        self.scan_sub = self.create_subscription(
            LaserScan, self.scan_topic, self._scan_callback,
            qos_profile_sensor_data)

        self.enabled = self.enabled_on_start
        self.target_visible = False
        self.target_angle = 0.0
        self.measured_distance_m = 0.0
        self.last_target_time = None
        self.last_scan_time = None
        self.front_obstacle_distance = math.inf
        self.rear_obstacle_distance = math.inf
        self.last_control_time = time.monotonic()
        self.last_linear = 0.0
        self.last_angular = 0.0
        self.motion_active = False
        self.last_state = None

        self.timer = self.create_timer(
            1.0 / self.control_rate_hz, self._control_callback)
        self._set_state('DISABLED')
        self.get_logger().warning(
            'Follower started DISABLED. Enable explicitly on the enable topic.')

    def _declare_parameters(self):
        defaults = {
            'position_topic': '/tennis_ball/position',
            'visible_topic': '/tennis_ball/visible',
            'scan_topic': '/scan',
            'enable_topic': '/tennis_ball_follower/enable',
            'cmd_vel_topic': '/cmd_vel',
            'state_topic': '/tennis_ball_follower/state',
            'enabled_on_start': False,
            'require_lidar': True,
            'target_timeout_s': 0.25,
            'lidar_timeout_s': 0.50,
            'control_rate_hz': 20.0,
            'target_distance_m': 0.80,
            'distance_deadband_m': 0.10,
            'angle_deadband_rad': 0.06,
            'linear_angle_limit_rad': 0.45,
            'kp_linear': 0.35,
            'kp_angular': 1.20,
            'max_linear_speed_mps': 0.12,
            'allow_reverse': False,
            'max_reverse_speed_mps': 0.06,
            'max_angular_speed_rps': 0.35,
            'max_linear_accel_mps2': 0.25,
            'max_angular_accel_rps2': 0.80,
            'lidar_front_half_angle_deg': 28.0,
            'lidar_stop_distance_m': 0.50,
            'lidar_rear_half_angle_deg': 28.0,
            'lidar_rear_stop_distance_m': 0.45,
        }
        for name, value in defaults.items():
            self.declare_parameter(name, value)

    def _load_parameters(self):
        topic_names = (
            'position_topic', 'visible_topic', 'scan_topic', 'enable_topic',
            'cmd_vel_topic', 'state_topic')
        for name in topic_names:
            setattr(self, name, self.get_parameter(name).value)
        self.enabled_on_start = bool(self.get_parameter('enabled_on_start').value)
        self.require_lidar = bool(self.get_parameter('require_lidar').value)
        self.allow_reverse = bool(self.get_parameter('allow_reverse').value)
        numeric_names = (
            'target_timeout_s', 'lidar_timeout_s', 'control_rate_hz',
            'distance_deadband_m', 'angle_deadband_rad',
            'linear_angle_limit_rad', 'kp_linear', 'kp_angular',
            'max_linear_speed_mps', 'max_angular_speed_rps',
            'max_reverse_speed_mps',
            'max_linear_accel_mps2', 'max_angular_accel_rps2',
            'lidar_front_half_angle_deg', 'lidar_stop_distance_m',
            'lidar_rear_half_angle_deg', 'lidar_rear_stop_distance_m')
        for name in numeric_names:
            setattr(self, name, float(self.get_parameter(name).value))
        self.target_distance_setpoint_m = float(
            self.get_parameter('target_distance_m').value)

    def _position_callback(self, msg):
        if msg.distance <= 0.0 or not math.isfinite(msg.distance):
            self.target_visible = False
            return
        self.target_angle = float(msg.angle_x)
        self.measured_distance_m = float(msg.distance) / 1000.0
        self.last_target_time = time.monotonic()

    def _visible_callback(self, msg):
        self.target_visible = bool(msg.data)
        if not self.target_visible:
            self.last_target_time = None

    def _enable_callback(self, msg):
        self.enabled = bool(msg.data)
        if not self.enabled:
            self._stop_once()
            self._set_state('DISABLED')
        else:
            self.get_logger().warning('Follower ENABLED by topic command.')

    def _scan_callback(self, msg):
        front_minimum = math.inf
        rear_minimum = math.inf
        front_half_angle = math.radians(self.lidar_front_half_angle_deg)
        rear_half_angle = math.radians(self.lidar_rear_half_angle_deg)
        angle = msg.angle_min
        for distance in msg.ranges:
            normalized = normalize_angle(angle)
            valid = (
                math.isfinite(distance)
                and msg.range_min <= distance <= msg.range_max)
            if valid and abs(normalized) <= front_half_angle:
                front_minimum = min(front_minimum, float(distance))
            rear_error = abs(abs(normalized) - math.pi)
            if valid and rear_error <= rear_half_angle:
                rear_minimum = min(rear_minimum, float(distance))
            angle += msg.angle_increment
        self.front_obstacle_distance = front_minimum
        self.rear_obstacle_distance = rear_minimum
        self.last_scan_time = time.monotonic()

    def _control_callback(self):
        now = time.monotonic()
        dt = clamp(now - self.last_control_time, 0.001, 0.2)
        self.last_control_time = now

        if not self.enabled:
            self._stop_once()
            self._set_state('DISABLED')
            return

        target_fresh = (
            self.target_visible
            and self.last_target_time is not None
            and now - self.last_target_time <= self.target_timeout_s)
        if not target_fresh:
            self._stop_once()
            self._set_state('TARGET_LOST')
            return

        lidar_fresh = (
            self.last_scan_time is not None
            and now - self.last_scan_time <= self.lidar_timeout_s)
        if self.require_lidar and not lidar_fresh:
            self._stop_once()
            self._set_state('LIDAR_STALE')
            return
        angle_error = self.target_angle
        distance_error = self.measured_distance_m - self.target_distance_setpoint_m
        angular = 0.0 if abs(angle_error) < self.angle_deadband_rad else self.kp_angular * angle_error
        angular = clamp(
            angular, -self.max_angular_speed_rps, self.max_angular_speed_rps)

        linear = 0.0
        if (distance_error > self.distance_deadband_m
                and abs(angle_error) <= self.linear_angle_limit_rad):
            linear = clamp(
                self.kp_linear * distance_error,
                0.0, self.max_linear_speed_mps)
        elif (self.allow_reverse
                and distance_error < -self.distance_deadband_m
                and abs(angle_error) <= self.linear_angle_limit_rad):
            linear = clamp(
                self.kp_linear * distance_error,
                -self.max_reverse_speed_mps, 0.0)

        if (lidar_fresh and linear >= 0.0
                and self.front_obstacle_distance < self.lidar_stop_distance_m):
            self._stop_once()
            self._set_state('OBSTACLE_STOP')
            return
        if (lidar_fresh and linear < 0.0
                and self.rear_obstacle_distance < self.lidar_rear_stop_distance_m):
            self._stop_once()
            self._set_state('REAR_OBSTACLE_STOP')
            return

        # Never coast through zero when changing between forward and reverse.
        if linear * self.last_linear < 0.0:
            self.last_linear = 0.0

        max_linear_step = self.max_linear_accel_mps2 * dt
        max_angular_step = self.max_angular_accel_rps2 * dt
        linear = self.last_linear + clamp(
            linear - self.last_linear, -max_linear_step, max_linear_step)
        angular = self.last_angular + clamp(
            angular - self.last_angular, -max_angular_step, max_angular_step)

        cmd = Twist()
        cmd.linear.x = float(linear)
        cmd.angular.z = float(angular)
        self.cmd_pub.publish(cmd)
        self.last_linear = linear
        self.last_angular = angular
        self.motion_active = abs(linear) > 1e-4 or abs(angular) > 1e-4
        self._set_state('TRACKING')

    def _stop_once(self):
        if self.motion_active or abs(self.last_linear) > 1e-4 or abs(self.last_angular) > 1e-4:
            self.cmd_pub.publish(Twist())
        self.last_linear = 0.0
        self.last_angular = 0.0
        self.motion_active = False

    def _set_state(self, state):
        if state == self.last_state:
            return
        self.last_state = state
        self.state_pub.publish(String(data=state))
        self.get_logger().info(f'State: {state}')

    def stop(self):
        self.cmd_pub.publish(Twist())
        self.last_linear = 0.0
        self.last_angular = 0.0
        self.motion_active = False


def main(args=None):
    rclpy.init(args=args)
    node = TennisBallFollower()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.stop()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()

