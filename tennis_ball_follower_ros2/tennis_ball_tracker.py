#!/usr/bin/env python3
"""Detect a tennis ball in synchronized RGB and depth images."""

import math
import time

import cv2
from cv_bridge import CvBridge
import message_filters
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, qos_profile_sensor_data
from sensor_msgs.msg import CameraInfo, Image
from std_msgs.msg import Bool
from turn_on_wheeltec_robot.msg import Position


class TennisBallTracker(Node):
    """HSV/shape detector with robust depth measurement and visibility output."""

    def __init__(self):
        super().__init__('tennis_ball_tracker')
        self.bridge = CvBridge()
        self._declare_parameters()
        self._load_parameters()

        self.fx = None
        self.cx = None
        self.last_frame_time = None
        self.visible = False
        self.warned_size_mismatch = False

        self.position_pub = self.create_publisher(
            Position, self.position_topic, QoSProfile(depth=10))
        self.visible_pub = self.create_publisher(
            Bool, self.visible_topic, QoSProfile(depth=10))
        self.debug_pub = self.create_publisher(
            Image, self.debug_image_topic, QoSProfile(depth=1))

        self.camera_info_sub = self.create_subscription(
            CameraInfo,
            self.camera_info_topic,
            self._camera_info_callback,
            qos_profile_sensor_data)

        color_sub = message_filters.Subscriber(
            self, Image, self.color_image_topic,
            qos_profile=qos_profile_sensor_data)
        depth_sub = message_filters.Subscriber(
            self, Image, self.depth_image_topic,
            qos_profile=qos_profile_sensor_data)
        self.synchronizer = message_filters.ApproximateTimeSynchronizer(
            [color_sub, depth_sub], queue_size=15, slop=0.08)
        self.synchronizer.registerCallback(self._image_callback)

        self.watchdog_timer = self.create_timer(0.10, self._watchdog_callback)
        self.get_logger().info(
            'Tennis-ball tracker started; it never publishes /cmd_vel.')

    def _declare_parameters(self):
        defaults = {
            'color_image_topic': '/camera/color/image_raw',
            'depth_image_topic': '/camera/depth/image_raw',
            'camera_info_topic': '/camera/color/camera_info',
            'position_topic': '/tennis_ball/position',
            'visible_topic': '/tennis_ball/visible',
            'debug_image_topic': '/tennis_ball/debug_image',
            'lower_h': 22,
            'lower_s': 65,
            'lower_v': 65,
            'upper_h': 58,
            'upper_s': 255,
            'upper_v': 255,
            'min_contour_area': 70.0,
            'max_contour_area': 80000.0,
            'min_radius_px': 4.0,
            'min_circularity': 0.52,
            'min_aspect_ratio': 0.55,
            'max_aspect_ratio': 1.80,
            'morphology_kernel': 5,
            'min_depth_m': 0.30,
            'max_depth_m': 3.00,
            'minimum_depth_samples': 8,
            'depth_unit_scale': 0.0,
            'allow_monocular_fallback': False,
            'ball_diameter_m': 0.067,
            'frame_timeout_s': 0.30,
            'publish_debug_image': True,
        }
        for name, value in defaults.items():
            self.declare_parameter(name, value)

    def _load_parameters(self):
        for name in (
                'color_image_topic', 'depth_image_topic', 'camera_info_topic',
                'position_topic', 'visible_topic', 'debug_image_topic'):
            setattr(self, name, self.get_parameter(name).value)

        self.lower_hsv = np.array([
            self.get_parameter('lower_h').value,
            self.get_parameter('lower_s').value,
            self.get_parameter('lower_v').value], dtype=np.uint8)
        self.upper_hsv = np.array([
            self.get_parameter('upper_h').value,
            self.get_parameter('upper_s').value,
            self.get_parameter('upper_v').value], dtype=np.uint8)

        numeric_names = (
            'min_contour_area', 'max_contour_area', 'min_radius_px',
            'min_circularity', 'min_aspect_ratio', 'max_aspect_ratio',
            'min_depth_m', 'max_depth_m', 'depth_unit_scale',
            'ball_diameter_m', 'frame_timeout_s')
        for name in numeric_names:
            setattr(self, name, float(self.get_parameter(name).value))
        self.morphology_kernel = int(
            self.get_parameter('morphology_kernel').value)
        self.minimum_depth_samples = int(
            self.get_parameter('minimum_depth_samples').value)
        self.allow_monocular_fallback = bool(
            self.get_parameter('allow_monocular_fallback').value)
        self.publish_debug_image = bool(
            self.get_parameter('publish_debug_image').value)

    def _camera_info_callback(self, msg):
        if len(msg.k) >= 3 and msg.k[0] > 0.0:
            self.fx = float(msg.k[0])
            self.cx = float(msg.k[2])

    def _image_callback(self, color_msg, depth_msg):
        self.last_frame_time = time.monotonic()
        try:
            frame = self.bridge.imgmsg_to_cv2(
                color_msg, desired_encoding='bgr8')
            depth = self.bridge.imgmsg_to_cv2(
                depth_msg, desired_encoding='passthrough')
        except Exception as exc:  # cv_bridge can throw multiple exception types.
            self.get_logger().error(f'Image conversion failed: {exc}')
            self._publish_not_visible()
            return

        if depth.ndim != 2:
            self.get_logger().error(
                f'Expected a single-channel depth image, got {depth.shape}')
            self._publish_not_visible()
            return

        if depth.shape[:2] != frame.shape[:2]:
            if not self.warned_size_mismatch:
                self.get_logger().warning(
                    'Color/depth sizes differ; resizing depth with nearest-neighbor. '
                    'Verify depth-to-color alignment before motion tests.')
                self.warned_size_mismatch = True
            depth = cv2.resize(
                depth, (frame.shape[1], frame.shape[0]),
                interpolation=cv2.INTER_NEAREST)

        detection, mask = self._detect(frame, depth, depth_msg.encoding)
        if detection is None:
            self._publish_not_visible()
            self._publish_debug(frame, mask, None)
            return

        center, radius, distance_m, contour = detection
        image_cx = self.cx if self.cx is not None else frame.shape[1] / 2.0
        focal_x = self.fx if self.fx is not None else frame.shape[1] / 1.1547
        angle_x = math.atan2(image_cx - center[0], focal_x)

        msg = Position()
        msg.angle_x = float(angle_x)
        msg.angle_y = 0.0
        msg.distance = float(distance_m * 1000.0)  # Keep WHEELTEC's millimeter convention.
        self.position_pub.publish(msg)
        self.visible_pub.publish(Bool(data=True))
        self.visible = True
        self._publish_debug(frame, mask, (center, radius, distance_m, contour))

    def _detect(self, frame, depth, depth_encoding):
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, self.lower_hsv, self.upper_hsv)

        kernel_size = max(1, self.morphology_kernel)
        if kernel_size % 2 == 0:
            kernel_size += 1
        kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

        contours = cv2.findContours(
            mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[-2]
        candidates = []
        for contour in contours:
            area = float(cv2.contourArea(contour))
            if area < self.min_contour_area or area > self.max_contour_area:
                continue
            perimeter = float(cv2.arcLength(contour, True))
            if perimeter <= 0.0:
                continue
            circularity = 4.0 * math.pi * area / (perimeter * perimeter)
            if circularity < self.min_circularity:
                continue
            x, y, width, height = cv2.boundingRect(contour)
            aspect = width / max(float(height), 1.0)
            if not self.min_aspect_ratio <= aspect <= self.max_aspect_ratio:
                continue
            (center_x, center_y), radius = cv2.minEnclosingCircle(contour)
            if radius < self.min_radius_px:
                continue
            score = area * max(circularity, 0.0)
            candidates.append((score, contour, (center_x, center_y), radius))

        for _, contour, center, radius in sorted(
                candidates, key=lambda item: item[0], reverse=True):
            distance_m = self._contour_depth(
                contour, depth, depth_encoding)
            if distance_m is None and self.allow_monocular_fallback and self.fx:
                distance_m = self.fx * self.ball_diameter_m / max(2.0 * radius, 1.0)
            if distance_m is None:
                continue
            if self.min_depth_m <= distance_m <= self.max_depth_m:
                return (center, radius, distance_m, contour), mask

        return None, mask

    def _contour_depth(self, contour, depth, encoding):
        contour_mask = np.zeros(depth.shape, dtype=np.uint8)
        cv2.drawContours(contour_mask, [contour], -1, 255, thickness=-1)
        erode_size = max(3, self.morphology_kernel)
        kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (erode_size, erode_size))
        contour_mask = cv2.erode(contour_mask, kernel, iterations=1)
        values = depth[contour_mask > 0].astype(np.float32, copy=False)
        if values.size == 0:
            return None

        scale = self.depth_unit_scale
        if scale <= 0.0:
            scale = 0.001 if ('16U' in encoding.upper() or np.issubdtype(depth.dtype, np.integer)) else 1.0
        values_m = values * scale
        valid = values_m[
            np.isfinite(values_m)
            & (values_m >= self.min_depth_m)
            & (values_m <= self.max_depth_m)]
        if valid.size < self.minimum_depth_samples:
            return None
        return float(np.median(valid))

    def _publish_not_visible(self):
        self.visible_pub.publish(Bool(data=False))
        msg = Position()
        msg.angle_x = 0.0
        msg.angle_y = 0.0
        msg.distance = 0.0
        self.position_pub.publish(msg)
        self.visible = False

    def _publish_debug(self, frame, mask, detection):
        if not self.publish_debug_image:
            return
        debug = frame.copy()
        if detection is not None:
            center, radius, distance_m, contour = detection
            cv2.drawContours(debug, [contour], -1, (255, 0, 0), 2)
            cv2.circle(
                debug, (int(center[0]), int(center[1])), int(radius),
                (0, 0, 255), 2)
            cv2.putText(
                debug, f'{distance_m:.2f} m',
                (int(center[0]) + 8, int(center[1]) - 8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
        small_mask = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
        small_mask = cv2.resize(
            small_mask, (debug.shape[1] // 3, debug.shape[0] // 3))
        debug[:small_mask.shape[0], :small_mask.shape[1]] = small_mask
        # Construct the message directly. Some ROS 2 Humble images ship an
        # older cv_bridge/OpenCV combination whose cv2_to_imgmsg lookup raises
        # KeyError for otherwise valid uint8 BGR arrays.
        debug = np.ascontiguousarray(debug, dtype=np.uint8)
        msg = Image()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.height = int(debug.shape[0])
        msg.width = int(debug.shape[1])
        msg.encoding = 'bgr8'
        msg.is_bigendian = False
        msg.step = int(debug.shape[1] * 3)
        msg.data = debug.tobytes()
        self.debug_pub.publish(msg)

    def _watchdog_callback(self):
        if self.last_frame_time is None:
            return
        if time.monotonic() - self.last_frame_time > self.frame_timeout_s and self.visible:
            self._publish_not_visible()


def main(args=None):
    rclpy.init(args=args)
    node = TennisBallTracker()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()

