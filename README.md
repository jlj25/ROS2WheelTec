# Ball Follower for WHEELTEC ROS 2

[English](README.md) | [简体中文](README_CN.md)

This package adds conservative RGB-D ball trackers and a separately
gated velocity controller. It does not modify the vendor packages.

Version 0.3.0 also includes an optional YOLO detector for general sports balls.
The original HSV tracker remains available, and neither tracker publishes
`/cmd_vel` directly. See
[`docs/YOLO_JETSON_SETUP_zh-CN.md`](docs/YOLO_JETSON_SETUP_zh-CN.md) for the
Jetson setup and first-test workflow.

The first Jetson Orin NX hardware test successfully detected and followed a
small ball at reduced speed. See the
[v0.3.0 Chinese update notes](docs/UPDATE_NOTES_v0.3.0_zh-CN.md) for measured
rates, validated behavior, and current limitations.

## Scope and prerequisites

This repository is itself a ROS 2 Python package named
`tennis_ball_follower_ros2`; it is not a complete robot software stack. It
depends on WHEELTEC's `turn_on_wheeltec_robot` package, base driver, Astra RGB-D
camera driver, and lidar driver.

The validated platform uses ROS 2 Humble, a Jetson Orin NX, an Astra RGB-D
camera, and an LSLIDAR N10Plus. Other robots or topic names require configuration
changes. The YOLO tracker also requires Ultralytics and
`/home/wheeltec/models/yolo11n.pt`; follow the
[Jetson YOLO setup guide](docs/YOLO_JETSON_SETUP_zh-CN.md).

## Current YOLO detection scope

The default `yolo11n.pt` model uses COCO class 32, `sports ball`. It does not
distinguish tennis balls, footballs, basketballs, volleyballs, table-tennis
balls, or other subtypes. Common sports balls may be detected, but only a tennis
ball has been validated on the robot so far; other ball types are not yet
verified.

Very small, heavily occluded, unusual, or under-represented balls may be missed.
If the depth camera has no valid reading, the monocular fallback assumes
`ball_diameter_m: 0.067`, approximately a tennis-ball diameter. Change that
parameter or disable the fallback when using a substantially different ball.

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

Clone this repository directly into the workspace `src` directory. A downloaded
ZIP also works, but the extracted package directory must contain `package.xml`
directly rather than another nested copy of the repository directory.

```bash
cd /home/wheeltec/wheeltec_ros2/src
git clone https://github.com/jlj25/ROS2WheelTec.git tennis_ball_follower_ros2

cd /home/wheeltec/wheeltec_ros2
source /opt/ros/humble/setup.bash
colcon build --packages-select tennis_ball_follower_ros2 --symlink-install
source /home/wheeltec/wheeltec_ros2/install/setup.bash

ros2 pkg prefix tennis_ball_follower_ros2
```

The final command should print the installed package path. A missing
`turn_on_wheeltec_robot` dependency means that the WHEELTEC vendor workspace is
not present or has not been built.

## Stage 1: start the base, lidar, and camera

In terminal 1:

```bash
source /opt/ros/humble/setup.bash
source /home/wheeltec/wheeltec_ros2/install/setup.bash
ros2 launch turn_on_wheeltec_robot wheeltec_sensors.launch.py
```

This WHEELTEC launch file starts all three devices. Keep it running and do not
start duplicate camera or lidar nodes. If a particular WHEELTEC model does not
provide the combined launch file, run these in three separately sourced
terminals:

```bash
ros2 launch turn_on_wheeltec_robot turn_on_wheeltec_robot.launch.py
ros2 launch turn_on_wheeltec_robot wheeltec_camera.launch.py
ros2 launch turn_on_wheeltec_robot wheeltec_lidar.launch.py
```

An Astra `Resource busy` error normally means that another process owns the
camera. Check with the current user before terminating an unknown process.

## Stage 2: detection only

In terminal 2, start either YOLO:

```bash
source /opt/ros/humble/setup.bash
source /home/wheeltec/wheeltec_ros2/install/setup.bash
ros2 launch tennis_ball_follower_ros2 ball_yolo_follow.launch.py
```

The default launch does not start the controller. Inspect:

```bash
ros2 topic echo /tennis_ball/visible
ros2 topic echo /tennis_ball/position
rqt_image_view
```

or use the HSV fallback:

```bash
ros2 launch tennis_ball_follower_ros2 tennis_ball_follow.launch.py
```

Do not run the HSV and YOLO trackers simultaneously because they publish the
same compatibility topics. The YOLO debug image is
`/tennis_ball/yolo_debug_image`; the HSV debug image is
`/tennis_ball/debug_image`.

## Stage 3: controller without enabling movement

After the base, sensors, and one detector are working, start the controller in
terminal 3:

```bash
source /opt/ros/humble/setup.bash
source /home/wheeltec/wheeltec_ros2/install/setup.bash
ros2 run tennis_ball_follower_ros2 tennis_ball_follower \
  --ros-args \
  --params-file /home/wheeltec/wheeltec_ros2/install/tennis_ball_follower_ros2/share/tennis_ball_follower_ros2/config/tennis_ball.yaml
```

Confirm these states before enabling:

```bash
ros2 topic echo /tennis_ball_follower/state
ros2 topic hz /scan
```

## Stage 4: explicit enable and stop

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

