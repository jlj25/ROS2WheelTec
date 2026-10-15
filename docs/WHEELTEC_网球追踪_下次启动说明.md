# WHEELTEC 小球追踪：下次启动说明

更新日期：2026-10-15
适用版本：`tennis_ball_follower_ros2 0.3.0`
当前推荐检测器：YOLO11n `sports ball`

## 当前已验证状态

- Jetson Orin NX 16GB，JetPack 6.2，CUDA 12.6，TensorRT 10.3。
- Ultralytics 8.4.177 与 NVIDIA PyTorch 2.6.0-rc1 GPU 推理正常。
- YOLO 模型位于 `/home/wheeltec/models/yolo11n.pt`。
- YOLO 能稳定框住网球，快速左右移动时不容易丢失。
- 手完全遮挡网球后目标丢失，小车按安全策略停车。
- Astra RGB-D 距离在约 `0.5 m`、`1.0 m`、`1.5 m` 处基本正确。
- 彩色图约 `23 Hz`，深度图约 `28 Hz`，当前 YOLO ROS 输出约 `6 Hz`。
- YOLO 低速实车跟随已经验证成功。
- 原 HSV 网球检测器仍然保留，可作为回退方案。

## 当前安全策略

1. 控制器每次启动默认为 `DISABLED`，必须手动启用。
2. YOLO 与 HSV 检测器不能同时运行，它们发布相同的目标话题。
3. 不要同时运行手势、键盘、导航或其他 `/cmd_vel` 发布节点。
4. 网球被遮挡、目标丢失、雷达断流或检测到障碍物时停车。
5. 当前 YOLO 输出约 `6 Hz`，在完成 TensorRT 优化前推荐使用低速参数。
6. 确保小车前后区域空旷，并随时准备发送 `enable=false` 或关闭底盘电源。

## 启动前快速检查

确认模型和环境：

```bash
ls -lh /home/wheeltec/models/yolo11n.pt

YOLO_AUTOINSTALL=False python3 - <<'PY'
import torch
import ultralytics
print('Ultralytics:', ultralytics.__version__)
print('PyTorch:', torch.__version__)
print('CUDA available:', torch.cuda.is_available())
PY
```

预期：模型约 `5.4 MB`，`CUDA available: True`。

## 终端 1：启动底盘、雷达和相机

```bash
source /opt/ros/humble/setup.bash
source /home/wheeltec/wheeltec_ros2/install/setup.bash

ros2 launch turn_on_wheeltec_robot wheeltec_sensors.launch.py
```

保持该终端运行。该启动文件已经包含底盘、雷达和相机，不要重复启动 Astra 或雷达节点。

若相机报告 `Resource busy`，先确认是否已有正常相机节点或其他同学正在使用，不要直接结束不明进程。

## 终端 2：启动 YOLO 小球检测器

```bash
source /opt/ros/humble/setup.bash

export AMENT_PREFIX_PATH="/home/wheeltec/wheeltec_ros2/install/tennis_ball_follower_ros2:$AMENT_PREFIX_PATH"
export PYTHONPATH="/home/wheeltec/wheeltec_ros2/install/tennis_ball_follower_ros2/lib/python3.10/site-packages:$PYTHONPATH"
export PATH="/home/wheeltec/wheeltec_ros2/install/tennis_ball_follower_ros2/lib/tennis_ball_follower_ros2:$PATH"

ros2 launch tennis_ball_follower_ros2 ball_yolo_follow.launch.py
```

保持该终端运行。该命令默认只启动检测器，不会控制小车运动。

正常日志应包含：

```text
Loading YOLO model: /home/wheeltec/models/yolo11n.pt
YOLO ball tracker started; it never publishes /cmd_vel.
```

`torchvision.io` 关于 `libnvjpeg.so.12` 的警告目前可以忽略，因为本程序使用 OpenCV 与 `cv_bridge` 读取图像，GPU 推理已经验证成功。

## HSV 回退方式

如果 YOLO 环境故障，可以停止 YOLO 节点，然后改用旧版 HSV 检测器：

```bash
ros2 launch tennis_ball_follower_ros2 tennis_ball_follow.launch.py
```

不能同时运行上述两个检测器。

## 终端 3：启动低速运动控制器

在完成 TensorRT 优化前，推荐使用低速覆盖参数：

```bash
source /opt/ros/humble/setup.bash

export AMENT_PREFIX_PATH="/home/wheeltec/wheeltec_ros2/install/tennis_ball_follower_ros2:$AMENT_PREFIX_PATH"
export PYTHONPATH="/home/wheeltec/wheeltec_ros2/install/tennis_ball_follower_ros2/lib/python3.10/site-packages:$PYTHONPATH"
export PATH="/home/wheeltec/wheeltec_ros2/install/tennis_ball_follower_ros2/lib/tennis_ball_follower_ros2:$PATH"

ros2 run tennis_ball_follower_ros2 tennis_ball_follower \
  --ros-args \
  --params-file /home/wheeltec/wheeltec_ros2/install/tennis_ball_follower_ros2/share/tennis_ball_follower_ros2/config/tennis_ball.yaml \
  -p max_linear_speed_mps:=0.10 \
  -p max_angular_speed_rps:=0.30 \
  -p max_reverse_speed_mps:=0.04
```

正常启动时显示：

```text
State: DISABLED
Follower started DISABLED
```

保持该终端运行。

## 终端 4：启用前检查

### 检查相机、雷达和 YOLO

```bash
timeout 5s ros2 topic hz /camera/color/image_raw
timeout 5s ros2 topic hz /camera/depth/image_raw
timeout 5s ros2 topic hz /scan
timeout 5s ros2 topic hz /tennis_ball/position
```

当前现场参考值：

```text
彩色图：约 23 Hz
深度图：约 28 Hz
雷达：约 10 Hz
YOLO 位置：约 6 Hz
```

### 检查目标

将网球放在相机前约 `0.7～1.2 m`：

```bash
ros2 topic echo /tennis_ball/visible --once
ros2 topic echo /tennis_ball/position --once
```

预期 `visible: true`，并且 `distance` 为合理的毫米值。

### 检查控制器临时速度

```bash
ros2 param get /tennis_ball_follower max_linear_speed_mps
ros2 param get /tennis_ball_follower max_angular_speed_rps
ros2 param get /tennis_ball_follower max_reverse_speed_mps
```

本轮低速配置应分别为：

```text
0.10
0.30
0.04
```

### 检查 `/cmd_vel`

```bash
ros2 topic info /cmd_vel -v
```

必须满足：

- 发布者只有 `tennis_ball_follower`。
- 订阅者包含 `wheeltec_robot`。
- 不存在 `gesture_control` 或其他控制节点发布 `/cmd_vel`。

## 启用 YOLO 跟随

所有检查通过后执行：

```bash
ros2 topic pub --once \
  /tennis_ball_follower/enable \
  std_msgs/msg/Bool \
  "{data: true}"
```

当前预期行为：

- 球距离大于约 `0.53 m`：小车低速向前追踪。
- 球距离约为 `0.47～0.53 m`：停止前后移动并继续方向调整。
- 球距离小于约 `0.47 m`：以不超过 `0.04 m/s` 的本轮限速倒车。
- 球左右移动：小车转向目标。
- 球被遮挡或拿走：进入 `TARGET_LOST` 并停车。
- 前方障碍过近：进入 `OBSTACLE_STOP`。
- 倒车时后方障碍过近：进入 `REAR_OBSTACLE_STOP`。
- 雷达数据断流：进入 `LIDAR_STALE`。

## 查看 YOLO 识别框（可选）

正式跟随时不需要打开调试画面。需要调试时，Windows 先启动 XLaunch，再新开 PowerShell：

```powershell
$env:DISPLAY="127.0.0.1:0.0"
ssh -Y wheeltec@小车IP
```

小车终端确认 `$DISPLAY` 有值，然后执行：

```bash
source /opt/ros/humble/setup.bash
ros2 run rqt_image_view rqt_image_view
```

在窗口顶部选择：

```text
/tennis_ball/yolo_debug_image
```

X11 图像转发较慢，只用于观察绿色框。测试完成后关闭 `rqt_image_view`。

## 停止与结束实验

随时可以发送：

```bash
ros2 topic pub --once \
  /tennis_ball_follower/enable \
  std_msgs/msg/Bool \
  "{data: false}"
```

结束顺序：

1. 发送 `enable=false`。
2. 在控制器终端按 `Ctrl+C`。
3. 在 YOLO 检测器终端按 `Ctrl+C`。
4. 关闭 `rqt_image_view` 和 XLaunch。
5. 在传感器/底盘终端按 `Ctrl+C`。

必要时直接关闭底盘电源。

## 常见问题

### Package not found

重新执行终端 2 或终端 3 的三个 `export`，然后检查：

```bash
ros2 pkg prefix tennis_ball_follower_ros2
```

### 模型不存在或尝试联网下载

```bash
ls -lh /home/wheeltec/models/yolo11n.pt
```

默认配置必须指向：

```text
/home/wheeltec/models/yolo11n.pt
```

实验室网络可能对 GitHub Release 返回 HTTP 403，应在 Windows 下载模型后通过 `scp` 传入，不要依赖小车自动下载。

### YOLO 节点存在但一直是 false

```bash
ros2 topic list -t | grep tennis_ball
ros2 topic hz /camera/color/image_raw
ros2 topic hz /camera/depth/image_raw
ros2 topic hz /tennis_ball/position
```

先把网球放近到约 `0.5～1.0 m`，确保光线充足并让球在画面中占有足够像素。

### 小车不移动

```bash
ros2 topic echo /tennis_ball_follower/state
ros2 topic info /cmd_vel -v
ros2 topic hz /scan
```

重点检查 `DISABLED`、`TARGET_LOST`、`LIDAR_STALE`、`OBSTACLE_STOP` 和 `REAR_OBSTACLE_STOP`。

### rqt_image_view 命令找不到

正确启动方式是：

```bash
ros2 run rqt_image_view rqt_image_view
```

不是直接运行 `rqt_image_view`。

## 当前功能边界

- 当前只完成网球实测，其他球类还没有验证。
- 黄绿色游泳池需要重新放入画面确认不会被 YOLO 误检。
- 当前约 `6 Hz` 的 YOLO 输出适合低速验证，尚未完成 TensorRT 加速。
- 雷达目前提供安全停车，不会主动规划路线绕过障碍。
- 更换不同直径的小球时，如果使用单目备用测距，需要同步修改 `ball_diameter_m`。

进一步的实现与测试记录见 [UPDATE_NOTES_v0.3.0_zh-CN.md](UPDATE_NOTES_v0.3.0_zh-CN.md)。

