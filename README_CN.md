# WHEELTEC ROS 2 小球视觉跟随

[English](README.md) | [简体中文](README_CN.md)

本软件包为 WHEELTEC ROS 2 小车提供基于 Astra RGB-D 相机的小球检测，以及独立启用的运动控制器。它不会修改厂商原有软件包。

版本 0.3.0 新增了可选的 YOLO 通用小球检测器。原有 HSV 小球检测器仍然保留，YOLO 节点也不会直接控制小车。Jetson 安装与首次测试步骤见 [docs/YOLO_JETSON_SETUP_zh-CN.md](docs/YOLO_JETSON_SETUP_zh-CN.md)。

首轮 Jetson Orin NX 实机测试已经完成：小球检测、RGB-D 测距和低速跟随均正常。现场结果与已知限制见 [docs/UPDATE_NOTES_v0.3.0_zh-CN.md](docs/UPDATE_NOTES_v0.3.0_zh-CN.md)。

## 安全设计

- 默认启动文件只运行检测器，不会控制小车运动。
- 运动控制器独立启动，并且每次启动时默认为 `DISABLED`。
- 小车运动要求目标数据与激光雷达数据均保持新鲜。
- 小球丢失、雷达断流或检测到障碍物时立即停止。
- 距离过近时允许低速倒车修正，并使用独立的后方雷达安全区。
- 当前最大前进速度为 `0.25 m/s`，最大倒车速度为 `0.06 m/s`，最大角速度为 `0.55 rad/s`。
- 目标距离为 `0.50 m`，距离死区为 `0.03 m`。
- 前后雷达停车距离均为 `0.45 m`。

不要同时运行手势控制、键盘控制、导航或其他 `/cmd_vel` 发布节点。首次运动测试必须选择空旷区域，并确保可以立即发送停止命令或关闭底盘电源。

## 安装到小车

将软件包复制到小车工作空间的 `src` 目录，然后编译：

```bash
cd /home/wheeltec/wheeltec_ros2
source /opt/ros/humble/setup.bash
colcon build \
  --packages-select tennis_ball_follower_ros2 \
  --symlink-install
```

每个新终端都需要加载 ROS 2 环境。若工作空间顶层环境未能发现本包，可使用：

```bash
source /opt/ros/humble/setup.bash
export AMENT_PREFIX_PATH="/home/wheeltec/wheeltec_ros2/install/tennis_ball_follower_ros2:$AMENT_PREFIX_PATH"
export PYTHONPATH="/home/wheeltec/wheeltec_ros2/install/tennis_ball_follower_ros2/lib/python3.10/site-packages:$PYTHONPATH"
export PATH="/home/wheeltec/wheeltec_ros2/install/tennis_ball_follower_ros2/lib/tennis_ball_follower_ros2:$PATH"
```

## 第一阶段：只启动检测器

相机已经被其他进程使用时，不要重复启动相机节点。

```bash
ros2 launch tennis_ball_follower_ros2 tennis_ball_follow.launch.py
```

默认启动方式不会发布 `/cmd_vel`。检查检测结果：

```bash
ros2 topic echo /tennis_ball/visible --once
ros2 topic echo /tennis_ball/position --once
```

安装好 YOLO 运行环境后，可改用通用小球检测器：

```bash
ros2 launch tennis_ball_follower_ros2 ball_yolo_follow.launch.py
```

YOLO 和 HSV 检测器会发布相同的控制接口，因此不能同时启动。YOLO 调试图话题为 `/tennis_ball/yolo_debug_image`。

## 第二阶段：启动控制器

底盘、雷达和相机正常运行后，启动控制器：

```bash
ros2 run tennis_ball_follower_ros2 tennis_ball_follower \
  --ros-args \
  --params-file /home/wheeltec/wheeltec_ros2/install/tennis_ball_follower_ros2/share/tennis_ball_follower_ros2/config/tennis_ball.yaml
```

控制器启动后应显示：

```text
State: DISABLED
```

启用前检查：

```bash
ros2 topic hz /scan
ros2 topic info /cmd_vel -v
```

`/scan` 应约为 `10 Hz`，并且 `/cmd_vel` 应只有 `tennis_ball_follower` 一个发布者，订阅者应包含 `wheeltec_robot`。

## 启用与停止

确认环境安全后启用：

```bash
ros2 topic pub --once \
  /tennis_ball_follower/enable \
  std_msgs/msg/Bool \
  "{data: true}"
```

停止：

```bash
ros2 topic pub --once \
  /tennis_ball_follower/enable \
  std_msgs/msg/Bool \
  "{data: false}"
```

## 倒车修正

当小球距离小于约 `0.47 m` 时，小车会以不超过 `0.06 m/s` 的速度倒车；距离约为 `0.47～0.53 m` 时停止前后移动。倒车仅在雷达数据正常且后方 `0.45 m` 范围内无障碍时允许，否则进入 `REAR_OBSTACLE_STOP`。

## 话题与单位

- `/tennis_ball/position` 使用 `turn_on_wheeltec_robot/msg/Position`。
- `angle_x` 使用弧度。
- `distance` 使用毫米，以兼容 WHEELTEC 原有消息。
- Astra 的 `16UC1` 深度图在程序内部由毫米转换为米。

更完整的每次启动步骤请参阅 [小球追踪：下次启动说明](docs/WHEELTEC_网球追踪_下次启动说明.md)。未来功能规划请参阅 [docs/ROADMAP.md](docs/ROADMAP.md)。

