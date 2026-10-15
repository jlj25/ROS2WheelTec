# WHEELTEC ROS 2 小球视觉跟随

[English](README.md) | [简体中文](README_CN.md)

本软件包为 WHEELTEC ROS 2 小车提供基于 Astra RGB-D 相机的小球检测，以及独立启用的运动控制器。它不会修改厂商原有软件包。

版本 0.3.0 新增了可选的 YOLO 通用小球检测器。原有 HSV 小球检测器仍然保留，YOLO 节点也不会直接控制小车。Jetson 安装与首次测试步骤见 [docs/YOLO_JETSON_SETUP_zh-CN.md](docs/YOLO_JETSON_SETUP_zh-CN.md)。

首轮 Jetson Orin NX 实机测试已经完成：小球检测、RGB-D 测距和低速跟随均正常。现场结果与已知限制见 [docs/UPDATE_NOTES_v0.3.0_zh-CN.md](docs/UPDATE_NOTES_v0.3.0_zh-CN.md)。

## 适用范围与前置条件

本仓库本身就是一个 ROS 2 Python 软件包，ROS 2 包名为 `tennis_ball_follower_ros2`。它不是完整的小车系统，依赖 WHEELTEC 原厂工作空间中的 `turn_on_wheeltec_robot` 软件包、底盘驱动、Astra RGB-D 相机驱动和激光雷达驱动。

当前实机验证环境为 ROS 2 Humble、Jetson Orin NX、Astra RGB-D 相机和雷神 N10Plus 激光雷达。其他小车或不同的话题名称需要修改配置后才能使用。使用 YOLO 检测器还需要按照 [Jetson YOLO 安装说明](docs/YOLO_JETSON_SETUP_zh-CN.md)安装 Ultralytics，并把 `yolo11n.pt` 放到 `/home/wheeltec/models/yolo11n.pt`。

## YOLO 当前识别范围

默认模型 `yolo11n.pt` 使用 COCO 的 `sports ball` 类（类别编号 `32`）。它只判断画面中的物体是否属于“运动用球”，不会进一步区分网球、足球、篮球、排球或乒乓球等具体种类。因此这些常见球类都有可能被识别，但目前实机只验证过网球，不能把其他球类视为已经测试通过。

过小、严重遮挡、外观特殊或训练集中较少见的球可能无法识别。深度相机没有返回有效距离时，程序会按照配置中的 `ball_diameter_m: 0.067` 估算距离；该数值接近网球直径，换用尺寸差异较大的球时，备用估算距离会不准确，需要修改配置或关闭单目备用测距。

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

推荐直接把本仓库克隆到小车工作空间的 `src` 目录。也可以下载 ZIP，但解压后的目录必须直接包含 `package.xml`，不能多套一层同名目录。

```bash
cd /home/wheeltec/wheeltec_ros2/src
git clone https://github.com/jlj25/ROS2WheelTec.git tennis_ball_follower_ros2

cd /home/wheeltec/wheeltec_ros2
source /opt/ros/humble/setup.bash
colcon build \
  --packages-select tennis_ball_follower_ros2 \
  --symlink-install
source /home/wheeltec/wheeltec_ros2/install/setup.bash

ros2 pkg prefix tennis_ball_follower_ros2
```

最后一条命令应输出本包的安装路径。如果提示缺少 `turn_on_wheeltec_robot`，说明当前不是配套的 WHEELTEC 工作空间，或原厂软件包尚未编译。

每个新终端都需要加载 ROS 2 环境。若工作空间顶层环境未能发现本包，可使用：

```bash
source /opt/ros/humble/setup.bash
export AMENT_PREFIX_PATH="/home/wheeltec/wheeltec_ros2/install/tennis_ball_follower_ros2:$AMENT_PREFIX_PATH"
export PYTHONPATH="/home/wheeltec/wheeltec_ros2/install/tennis_ball_follower_ros2/lib/python3.10/site-packages:$PYTHONPATH"
export PATH="/home/wheeltec/wheeltec_ros2/install/tennis_ball_follower_ros2/lib/tennis_ball_follower_ros2:$PATH"
```

## 第一阶段：启动底盘、雷达和相机

在终端 1 中运行：

```bash
source /opt/ros/humble/setup.bash
source /home/wheeltec/wheeltec_ros2/install/setup.bash

ros2 launch turn_on_wheeltec_robot wheeltec_sensors.launch.py
```

这个原厂启动文件会同时启动底盘、雷达和相机，保持该终端运行，不要重复启动相机或雷达节点。如果该组合启动文件不适用于其他 WHEELTEC 型号，也可以分别在三个终端运行：

```bash
ros2 launch turn_on_wheeltec_robot turn_on_wheeltec_robot.launch.py
ros2 launch turn_on_wheeltec_robot wheeltec_camera.launch.py
ros2 launch turn_on_wheeltec_robot wheeltec_lidar.launch.py
```

每个命令都需要在已加载 ROS 2 和工作空间环境的新终端中运行。相机报告 `Resource busy` 通常表示相机已被其他进程占用；先确认现有节点或询问使用者，不要直接结束不明进程。

## 第二阶段：只启动检测器

在终端 2 中选择一种检测器。使用 YOLO：

```bash
source /opt/ros/humble/setup.bash
source /home/wheeltec/wheeltec_ros2/install/setup.bash
ros2 launch tennis_ball_follower_ros2 ball_yolo_follow.launch.py
```

默认启动方式不会发布 `/cmd_vel`。检查检测结果：

```bash
ros2 topic echo /tennis_ball/visible --once
ros2 topic echo /tennis_ball/position --once
```

如果 YOLO 环境尚未配置，可以改用 HSV 颜色检测器：

```bash
ros2 launch tennis_ball_follower_ros2 tennis_ball_follow.launch.py
```

YOLO 和 HSV 检测器会发布相同的控制接口，因此不能同时启动。YOLO 调试图话题为 `/tennis_ball/yolo_debug_image`。

### 可选：查看 YOLO 识别框

安装并启动图像查看器：

```bash
sudo apt install ros-humble-rqt-image-view
source /opt/ros/humble/setup.bash
rqt_image_view
```

在窗口顶部的话题下拉框中选择：

```text
/tennis_ball/yolo_debug_image
```

绿色框表示 YOLO 当前选中的小球，标签同时显示置信度和 RGB-D 距离。通过 SSH 查看图形界面时，需要先在电脑端启动 X Server（Windows 可使用 XLaunch），并使用 `ssh -Y wheeltec@<小车IP>` 连接；`echo $DISPLAY` 应有输出。

配置文件中的 `publish_debug_image` 必须为 `true` 才会发布调试图。查看完成后可以关闭 `rqt_image_view`；追求最高输出频率时可把该参数设为 `false`，这不会关闭小球检测或控制话题。

## 第三阶段：启动控制器

确认底盘、雷达、相机和检测器正常运行后，在终端 3 启动控制器：

```bash
source /opt/ros/humble/setup.bash
source /home/wheeltec/wheeltec_ros2/install/setup.bash

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

## 第四阶段：启用与停止

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

更完整的每次启动步骤请参阅 [小球追踪：下次启动说明](docs/WHEELTEC_网球追踪_下次启动说明.md)。未来功能规划请参阅 [中文未来计划](docs/ROADMAP_zh-CN.md)。

