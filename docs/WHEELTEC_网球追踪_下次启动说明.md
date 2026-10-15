# WHEELTEC 网球追踪：下次启动说明

更新日期：2026-10-15  
适用版本：`tennis_ball_follower_ros2 0.2.0`

## 当前已验证状态

- Astra RGB-D 相机可输出 640×480 彩色图和 `16UC1` 深度图。
- 网球检测话题为 `/tennis_ball/visible` 和 `/tennis_ball/position`。
- Astra 对网球表面的直接深度不稳定，因此启用了单目尺寸备用测距。
- 激光雷达 `/scan` 正常频率约为 `10 Hz`。
- 目标丢失、雷达失联、前方障碍和后方障碍均会触发停车。
- 最大前进速度：`0.25 m/s`。
- 最大倒车速度：`0.06 m/s`。
- 最大角速度：`0.55 rad/s`。
- 目标距离：`0.50 m`，距离死区：`0.03 m`。
- 前后雷达停车距离：`0.45 m`。
- 控制器每次启动默认都是 `DISABLED`，必须手动启用。
- 当前配置关闭调试图发布：`publish_debug_image: false`。

## 启动前注意

1. 确认没有其他人正在使用 Astra 相机。
2. 清空小车前后区域，保证雷达水平扫描平面尽量 360° 无遮挡。
3. 确保有人可以立即发送停止命令或关闭底盘电源。
4. 不要同时运行手势控制、键盘控制、导航或其他 `/cmd_vel` 发布节点。
5. `wheeltec_sensors.launch.py` 已包含底盘、雷达和相机，不要再分别重复启动这些节点。

## 终端 1：启动底盘、雷达和相机

```bash
source /opt/ros/humble/setup.bash
source /home/wheeltec/wheeltec_ros2/install/setup.bash

ros2 launch turn_on_wheeltec_robot wheeltec_sensors.launch.py
```

保持该终端运行。如果底盘、雷达和相机已经分别启动并工作正常，不要重复执行本步骤。

## 终端 2：启动网球检测器

```bash
source /opt/ros/humble/setup.bash

export AMENT_PREFIX_PATH="/home/wheeltec/wheeltec_ros2/install/tennis_ball_follower_ros2:$AMENT_PREFIX_PATH"
export PYTHONPATH="/home/wheeltec/wheeltec_ros2/install/tennis_ball_follower_ros2/lib/python3.10/site-packages:$PYTHONPATH"
export PATH="/home/wheeltec/wheeltec_ros2/install/tennis_ball_follower_ros2/lib/tennis_ball_follower_ros2:$PATH"

ros2 launch tennis_ball_follower_ros2 tennis_ball_follow.launch.py
```

保持该终端运行。默认启动文件只运行检测器，不发布 `/cmd_vel`。

## 终端 3：启动运动控制器

```bash
source /opt/ros/humble/setup.bash

export AMENT_PREFIX_PATH="/home/wheeltec/wheeltec_ros2/install/tennis_ball_follower_ros2:$AMENT_PREFIX_PATH"
export PYTHONPATH="/home/wheeltec/wheeltec_ros2/install/tennis_ball_follower_ros2/lib/python3.10/site-packages:$PYTHONPATH"
export PATH="/home/wheeltec/wheeltec_ros2/install/tennis_ball_follower_ros2/lib/tennis_ball_follower_ros2:$PATH"

ros2 run tennis_ball_follower_ros2 tennis_ball_follower \
  --ros-args \
  --params-file /home/wheeltec/wheeltec_ros2/install/tennis_ball_follower_ros2/share/tennis_ball_follower_ros2/config/tennis_ball.yaml
```

正常启动时显示：

```text
State: DISABLED
Follower started DISABLED
```

保持该终端运行。

## 终端 4：启动检查

### 检查传感器

```bash
timeout 5s ros2 topic hz /camera/color/image_raw
timeout 5s ros2 topic hz /camera/depth/image_raw
timeout 5s ros2 topic hz /scan
```

`/scan` 应稳定在约 `10 Hz`。

### 检查网球

将网球放在相机前约 `0.7～1.2 m`：

```bash
ros2 topic echo /tennis_ball/visible --once
ros2 topic echo /tennis_ball/position --once
```

球在画面中时，`visible` 应为 `true`，位置消息应包含有效的角度和距离。

### 检查速度连接

```bash
ros2 topic info /cmd_vel -v
```

必须满足：

- `Publisher count` 为 1，发布者是 `tennis_ball_follower`。
- `Subscription count` 至少为 1，订阅者包含 `wheeltec_robot`。

### 检查当前参数

```bash
ros2 param get /tennis_ball_follower target_distance_m
ros2 param get /tennis_ball_follower allow_reverse
ros2 param get /tennis_ball_follower max_linear_speed_mps
ros2 param get /tennis_ball_follower max_reverse_speed_mps
ros2 param get /tennis_ball_follower lidar_stop_distance_m
ros2 param get /tennis_ball_follower lidar_rear_stop_distance_m
```

应分别为：

```text
0.50
True
0.25
0.06
0.45
0.45
```

## 启用跟随

所有检查通过后执行：

```bash
ros2 topic pub --once \
  /tennis_ball_follower/enable \
  std_msgs/msg/Bool \
  "{data: true}"
```

预期行为：

- 网球距离大于约 `0.53 m` 时，小车向前追踪。
- 网球距离约为 `0.47～0.53 m` 时，小车停止前后移动。
- 网球距离小于约 `0.47 m` 时，小车低速倒车。
- 网球偏左或偏右时，小车转向目标。
- 拿走网球后，小车停车并进入 `TARGET_LOST`。
- 前方 `0.45 m` 内有障碍时进入 `OBSTACLE_STOP`。
- 倒车时后方 `0.45 m` 内有障碍时进入 `REAR_OBSTACLE_STOP`。
- 雷达数据断流时进入 `LIDAR_STALE`。

## 停止与结束实验

立即停止：

```bash
ros2 topic pub --once \
  /tennis_ball_follower/enable \
  std_msgs/msg/Bool \
  "{data: false}"
```

必要时直接关闭底盘电源。结束实验时建议按以下顺序：

1. 发送 `enable=false`。
2. 在控制器终端按 `Ctrl+C`。
3. 在检测器终端按 `Ctrl+C`。
4. 在传感器/底盘终端按 `Ctrl+C`。

## 常见问题

### Package not found

重新执行终端 2 或终端 3 中的三个 `export`，然后检查：

```bash
ros2 pkg prefix tennis_ball_follower_ros2
```

### 相机 Resource busy

说明另一个进程占用了相机，或者重复启动了相机节点：

```bash
pgrep -af 'astra_camera|orbbec'
```

确认无人使用后，只结束明确属于重复启动的进程。

### 雷达节点存在但 `/scan` 没有数据

```bash
ros2 node list | grep lslidar
ls -l /dev/wheeltec_lidar
sudo fuser -v /dev/wheeltec_lidar
```

保持雷达旋转部分和水平扫描平面无遮挡。普通障碍只会产生近距离读数；雷达被物理卡住、供电异常或串口通信异常才可能导致完全没有数据。

### 网球一直不可见

```bash
ros2 topic hz /camera/color/image_raw
ros2 topic hz /camera/depth/image_raw
ros2 node list | grep tennis_ball_tracker
ros2 param get /tennis_ball_tracker allow_monocular_fallback
```

`allow_monocular_fallback` 应为 `True`。

### 小车不移动

```bash
ros2 topic echo /tennis_ball_follower/state
ros2 topic echo /tennis_ball/position --once
ros2 topic hz /scan
```

根据状态检查 `DISABLED`、`TARGET_LOST`、`LIDAR_STALE`、`OBSTACLE_STOP` 或 `REAR_OBSTACLE_STOP`。如果网球已经处于目标距离死区内，速度为零属于正确行为。

## 当前功能边界

当前雷达功能属于安全停车保护，不会主动选择路线绕过障碍。未来计划包括 YOLO 网球检测和追踪过程中的低速自动绕障，详见 [ROADMAP.md](ROADMAP.md)。

