#!/usr/bin/env python3
"""Detect a ball with YOLO and publish the existing follower interface."""

import math
import os
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


class BallYoloTracker(Node):
    """YOLO sports-ball detector with RGB-D distance measurement."""

    def __init__(self):
        super().__init__('ball_yolo_tracker')
        self.bridge = CvBridge()
        self._declare_parameters()
        self._load_parameters()

        try:
            from ultralytics import YOLO
        except ImportError as exc:
            self.get_logger().fatal(
                'The ultralytics Python package is not installed. See '
                'docs/YOLO_JETSON_SETUP_zh-CN.md before starting this node.')
            raise RuntimeError('ultralytics is required for YOLO detection') from exc

        self.get_logger().info(f'Loading YOLO model: {self.model_path}')
        self.model = YOLO(self.model_path)
        self.fx = None
        self.cx = None
        self.last_frame_time = None
        self.visible = False
        self.previous_center = None
        self.previous_detection_time = None
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
            [color_sub, depth_sub], queue_size=10, slop=0.08)
        self.synchronizer.registerCallback(self._image_callback)

        self.watchdog_timer = self.create_timer(0.10, self._watchdog_callback)
        self.get_logger().info(
            'YOLO ball tracker started; it never publishes /cmd_vel.')

    def _declare_parameters(self):
        defaults = {
            'color_image_topic': '/camera/color/image_raw',
            'depth_image_topic': '/camera/depth/image_raw',
            'camera_info_topic': '/camera/color/camera_info',
            'position_topic': '/tennis_ball/position',
            'visible_topic': '/tennis_ball/visible',
            'debug_image_topic': '/tennis_ball/yolo_debug_image',
            'model_path': 'yolo11n.pt',
            'target_class_ids': [32],
            'confidence_threshold': 0.35,
            'iou_threshold': 0.45,
            'image_size': 640,
            'max_detections': 10,
            'device': '0',
            'use_half_precision': True,
            'tracking_memory_s': 0.50,
            'tracking_position_weight': 0.25,
            'depth_roi_scale': 0.50,
            'min_depth_m': 0.30,
            'max_depth_m': 3.00,
            'minimum_depth_samples': 8,
            'depth_unit_scale': 0.0,
            'allow_monocular_fallback': True,
            'ball_diameter_m': 0.067,
            'frame_timeout_s': 0.30,
            'publish_debug_image': True,
        }
        for name, value in defaults.items():
            self.declare_parameter(name, value)

    def _load_parameters(self):
        string_names = (
            'color_image_topic', 'depth_image_topic', 'camera_info_topic',
            'position_topic', 'visible_topic', 'debug_image_topic',
            'model_path', 'device')
        for name in string_names:
            setattr(self, name, str(self.get_parameter(name).value))

        self.target_class_ids = [
            int(value) for value in
            self.get_parameter('target_class_ids').value]
        self.image_size = int(self.get_parameter('image_size').value)
        self.max_detections = int(
            self.get_parameter('max_detections').value)
        self.minimum_depth_samples = int(
            self.get_parameter('minimum_depth_samples').value)

        numeric_names = (
            'confidence_threshold', 'iou_threshold', 'tracking_memory_s',
            'tracking_position_weight', 'depth_roi_scale', 'min_depth_m',
            'max_depth_m', 'depth_unit_scale', 'ball_diameter_m',
            'frame_timeout_s')
        for name in numeric_names:
            setattr(self, name, float(self.get_parameter(name).value))

        self.use_half_precision = bool(
            self.get_parameter('use_half_precision').value)
        self.allow_monocular_fallback = bool(
            self.get_parameter('allow_monocular_fallback').value)
        self.publish_debug_image = bool(
            self.get_parameter('publish_debug_image').value)

        if not 0.0 < self.depth_roi_scale <= 1.0:
            raise ValueError('depth_roi_scale must be in (0, 1]')
        if self.ball_diameter_m <= 0.0:
            raise ValueError('ball_diameter_m must be positive')

        expanded_model_path = os.path.expanduser(self.model_path)
        if expanded_model_path != self.model_path:
            self.model_path = expanded_model_path

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
        except Exception as exc:
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

        try:
            detection = self._detect(frame, depth, depth_msg.encoding)
        except Exception as exc:
            self.get_logger().error(f'YOLO inference failed: {exc}')
            self._publish_not_visible()
            return

        if detection is None:
            self._publish_not_visible()
            self._publish_debug(frame, None)
            return

        box, confidence, class_id, distance_m = detection
        x1, y1, x2, y2 = box
        center_x = (x1 + x2) * 0.5
        center_y = (y1 + y2) * 0.5
        self.previous_center = (center_x, center_y)
        self.previous_detection_time = time.monotonic()

        image_cx = self.cx if self.cx is not None else frame.shape[1] / 2.0
        focal_x = self.fx if self.fx is not None else frame.shape[1] / 1.1547
        angle_x = math.atan2(image_cx - center_x, focal_x)

        msg = Position()
        msg.angle_x = float(angle_x)
        msg.angle_y = 0.0
        msg.distance = float(distance_m * 1000.0)
        self.position_pub.publish(msg)
        self.visible_pub.publish(Bool(data=True))
        self.visible = True
        self._publish_debug(
            frame, (box, confidence, class_id, distance_m))

    def _detect(self, frame, depth, depth_encoding):
        results = self.model.predict(
            source=frame,
            conf=self.confidence_threshold,
            iou=self.iou_threshold,
            imgsz=self.image_size,
            classes=self.target_class_ids or None,
            max_det=self.max_detections,
            device=self.device,
            half=self.use_half_precision,
            verbose=False)
        if not results or results[0].boxes is None:
            return None

        boxes = results[0].boxes
        if len(boxes) == 0:
            return None

        xyxy_values = boxes.xyxy.detach().cpu().numpy()
        confidence_values = boxes.conf.detach().cpu().numpy()
        class_values = boxes.cls.detach().cpu().numpy().astype(int)

        height, width = frame.shape[:2]
        diagonal = max(math.hypot(width, height), 1.0)
        remember_previous = (
            self.previous_center is not None
            and self.previous_detection_time is not None
            and time.monotonic() - self.previous_detection_time
            <= self.tracking_memory_s)

        candidates = []
        for raw_box, confidence, class_id in zip(
                xyxy_values, confidence_values, class_values):
            x1 = float(np.clip(raw_box[0], 0, width - 1))
            y1 = float(np.clip(raw_box[1], 0, height - 1))
            x2 = float(np.clip(raw_box[2], x1 + 1, width))
            y2 = float(np.clip(raw_box[3], y1 + 1, height))
            center = ((x1 + x2) * 0.5, (y1 + y2) * 0.5)

            score = float(confidence)
            if remember_previous:
                displacement = math.hypot(
                    center[0] - self.previous_center[0],
                    center[1] - self.previous_center[1]) / diagonal
                score -= self.tracking_position_weight * displacement

            candidates.append((score, (x1, y1, x2, y2),
                               float(confidence), int(class_id)))

        for _, box, confidence, class_id in sorted(
                candidates, key=lambda item: item[0], reverse=True):
            distance_m = self._box_depth(box, depth, depth_encoding)
            if distance_m is None and self.allow_monocular_fallback and self.fx:
                pixel_diameter = max(
                    1.0, min(box[2] - box[0], box[3] - box[1]))
                distance_m = self.fx * self.ball_diameter_m / pixel_diameter
            if distance_m is None:
                continue
            if self.min_depth_m <= distance_m <= self.max_depth_m:
                return box, confidence, class_id, distance_m
        return None

    def _box_depth(self, box, depth, encoding):
        x1, y1, x2, y2 = box
        center_x = (x1 + x2) * 0.5
        center_y = (y1 + y2) * 0.5
        roi_width = max(2.0, (x2 - x1) * self.depth_roi_scale)
        roi_height = max(2.0, (y2 - y1) * self.depth_roi_scale)
        left = max(0, int(center_x - roi_width * 0.5))
        right = min(depth.shape[1], int(center_x + roi_width * 0.5) + 1)
        top = max(0, int(center_y - roi_height * 0.5))
        bottom = min(depth.shape[0], int(center_y + roi_height * 0.5) + 1)
        values = depth[top:bottom, left:right].astype(
            np.float32, copy=False).reshape(-1)
        if values.size == 0:
            return None

        scale = self.depth_unit_scale
        if scale <= 0.0:
            scale = 0.001 if (
                '16U' in encoding.upper()
                or np.issubdtype(depth.dtype, np.integer)) else 1.0
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

    def _publish_debug(self, frame, detection):
        if not self.publish_debug_image:
            return
        debug = frame.copy()
        if detection is not None:
            box, confidence, class_id, distance_m = detection
            x1, y1, x2, y2 = [int(value) for value in box]
            cv2.rectangle(debug, (x1, y1), (x2, y2), (0, 255, 0), 2)
            label = f'ball {confidence:.2f} {distance_m:.2f} m'
            cv2.putText(
                debug, label, (x1, max(20, y1 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)

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
        if (time.monotonic() - self.last_frame_time > self.frame_timeout_s
                and self.visible):
            self._publish_not_visible()


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = BallYoloTracker()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()

