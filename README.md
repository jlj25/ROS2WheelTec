# Tennis Ball Follower for WHEELTEC ROS 2

[English](README.md) | [简体中文](README_CN.md)

This package adds a conservative RGB-D tennis-ball tracker and a separately
gated velocity controller. It does not modify the vendor packages.

Version 0.3.0 also includes an optional YOLO detector for general sports balls.
The original HSV tracker remains available, and neither tracker publishes
`/cmd_vel` directly. See
[`docs/YOLO_JETSON_SETUP_zh-CN.md`](docs/YOLO_JETSON_SETUP_zh-CN.md) for the
Jetson setup and first-test workflow.

The first Jetson Orin NX hardware test successfully detected and followed a
tennis ball at reduced speed. See the
[v0.3.0 Chinese update notes](docs/UPDATE_NOTES_v0.3.0_zh-CN.md) for measured
rates, validated behavior, and current limitations.

## Safety design

- The default launch starts only the tracker and cannot move the robot.
- The controller is optional and starts disabled.
- Movement requires a fresh target and, by default, a fresh lidar scan.
- Target loss, stale lidar data, or a front obstacle publishes a zero Twist.
- Optional low-speed reverse correction is guarded by a separate rear lidar sector.
- Current speed limits are 0.25 m/s forward, 0.06 m/s reverse, and 0.55 rad/s angular.
- The target distance is 0.50 m with a 0.03 m deadband.
- Forward and reverse motion use separate lidar safety sectors.

Do not run another `/cmd_vel` controller at the same time. For the first motion
test, lift the drive wheels or use an open area with an accessible emergency
stop.

## Install on the robot

Copy this directory to the robot's workspace, then build it:

```bash
cd /home/wheeltec/wheeltec_ros2/src
colcon build --packages-select tennis_ball_follower_ros2 --symlink-install
source /home/wheeltec/wheeltec_ros2/install/setup.bash
```

## Stage 1: detection only

Start the Astra camera separately. If another user already has the camera node
running in the same ROS domain, do not start a second camera node.

```bash
ros2 launch tennis_ball_follower_ros2 tennis_ball_follow.launch.py
```

The default launch does not start the controller. Inspect:

```bash
ros2 topic echo /tennis_ball/visible
ros2 topic echo /tennis_ball/position
rqt_image_view
```

In `rqt_image_view`, select `/tennis_ball/debug_image`. Adjust the HSV values in
`config/tennis_ball.yaml` until only the tennis ball is white in the mask inset.

After installing the optional YOLO runtime, start general ball detection with:

```bash
ros2 launch tennis_ball_follower_ros2 ball_yolo_follow.launch.py
```

Do not run the HSV and YOLO trackers simultaneously because they publish the
same compatibility topics. The YOLO debug image is
`/tennis_ball/yolo_debug_image`.

## Stage 2: controller without enabling movement

Start the base and lidar, then start both package nodes:

```bash
ros2 launch turn_on_wheeltec_robot turn_on_wheeltec_robot.launch.py
ros2 launch turn_on_wheeltec_robot wheeltec_lidar.launch.py
ros2 launch tennis_ball_follower_ros2 tennis_ball_follow.launch.py run_controller:=true
```

Confirm these states before enabling:

```bash
ros2 topic echo /tennis_ball_follower/state
ros2 topic hz /scan
```

## Stage 3: explicit enable and stop

Enable only after detection, depth, and lidar have been verified:

```bash
ros2 topic pub --once /tennis_ball_follower/enable std_msgs/msg/Bool "{data: true}"
```

Stop immediately with:

```bash
ros2 topic pub --once /tennis_ball_follower/enable std_msgs/msg/Bool "{data: false}"
```

## Reverse correction

Version 0.2.0 can back away slowly when the ball is closer than the configured
target distance. The default reverse limit is 0.06 m/s. Reverse motion is
allowed only with fresh lidar data and a clear rear sector; otherwise the
controller enters `REAR_OBSTACLE_STOP`. Keep the lidar scan plane clear for a
full 360 degrees and never disable the rear safety check for floor testing.

`Ctrl+C` also publishes a zero Twist during normal shutdown.

## Expected units and topics

- `/tennis_ball/position` uses `turn_on_wheeltec_robot/msg/Position`.
- `angle_x` is radians; positive means the ball is left of image center.
- `distance` is millimeters for compatibility with WHEELTEC code.
- Astra `16UC1` depth is converted from millimeters to meters internally.

If the camera topics differ, edit the topic parameters in
`config/tennis_ball.yaml` rather than editing Python source.

