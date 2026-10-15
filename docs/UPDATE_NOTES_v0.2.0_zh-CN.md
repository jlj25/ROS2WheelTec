# 网球视觉跟随系统更新说明

发布日期：2026-10-15  
软件包：`tennis_ball_follower_ros2`  
代码版本：`0.2.0`  
适用平台：WHEELTEC ROS 2 Humble 小车、Astra RGB-D 相机、雷神 N10Plus 激光雷达

## 更新目的

本次更新在原有“识别网球并向前跟随”的基础上，加入近距离位置修正和后方安全保护，使小车能够在距离网球过近时低速倒车，并根据现场测试缩短跟随距离、提高前进速度。

## 主要功能修改

### 1. 新增低速倒车修正

- 当网球距离小于目标距离下限时，小车可以自动低速倒车。
- 倒车仅用于位置修正，不作为高速追踪动作。
- 默认最大倒车速度为 `0.06 m/s`。
- 从前进切换到倒车或从倒车切换到前进时，速度先经过零点，避免直接反向冲击。

### 2. 新增后方雷达安全区

- 新增独立的后方雷达检测区域。
- 后方检测半角为 `28°`。
- 后方障碍停车距离为 `0.45 m`。
- 请求倒车时，如果后方安全区内存在障碍物，控制器立即停车并进入：

  ```text
  REAR_OBSTACLE_STOP
  ```

- 雷达数据超时、目标丢失以及控制器未启用时，仍会停车。

### 3. 保留前方安全停车

- 前进时继续检查雷达正前方约 `±28°` 区域。
- 现场配置的前方停车距离调整为 `0.45 m`。
- 检测到过近障碍物时进入：

  ```text
  OBSTACLE_STOP
  ```

### 4. 优化网球测距兼容性

- 保持启用单目尺寸备用测距：`allow_monocular_fallback: true`。
- Astra 深度数据无法稳定测量网球表面时，可根据网球直径与图像尺寸估计距离。
- 为兼容当前系统的旧版 `cv_bridge`，默认关闭调试图发布：`publish_debug_image: false`。

## 当前现场运行参数

以下是完成本次调试后，小车上采用的参数：

```yaml
target_distance_m: 0.50
distance_deadband_m: 0.03

kp_linear: 0.50
kp_angular: 1.60

max_linear_speed_mps: 0.25
max_reverse_speed_mps: 0.06
max_angular_speed_rps: 0.55

max_linear_accel_mps2: 0.55
max_angular_accel_rps2: 1.40

angle_deadband_rad: 0.04
linear_angle_limit_rad: 0.50

allow_reverse: true
require_lidar: true

lidar_front_half_angle_deg: 28.0
lidar_stop_distance_m: 0.45
lidar_rear_half_angle_deg: 28.0
lidar_rear_stop_distance_m: 0.45
```

## 当前预期行为

- 网球距离大于约 `0.53 m`：小车向前追踪。
- 网球距离约为 `0.47～0.53 m`：小车停止前后移动，并继续进行必要的方向调整。
- 网球距离小于约 `0.47 m`：小车以不超过 `0.06 m/s` 的速度倒车。
- 最大前进速度为 `0.25 m/s`。
- 前方障碍距离小于 `0.45 m`：禁止继续前进。
- 后方障碍距离小于 `0.45 m`：禁止倒车。
- 网球丢失、雷达数据超时或收到禁用命令：停车。

实际停车距离会受到单目估距误差、地面摩擦、控制延迟和网球运动影响，`0.50 m` 是控制目标，不代表厘米级精确定位。

## 新增控制器参数

| 参数 | 默认/现场值 | 说明 |
|---|---:|---|
| `allow_reverse` | `true` | 是否允许近距离倒车修正 |
| `max_reverse_speed_mps` | `0.06` | 最大倒车速度 |
| `lidar_rear_half_angle_deg` | `28.0` | 后方雷达安全区半角 |
| `lidar_rear_stop_distance_m` | `0.45` | 后方障碍停车距离 |

## 安装和构建问题记录

### 重复软件包

备份包曾放在工作空间的 `src/` 目录中，导致 `colcon` 同时发现两个同名包并报错：

```text
Duplicate package names not supported
```

处理方法是将备份移动到工作空间外：

```bash
mkdir -p /home/wheeltec/package_backups
mv \
  /home/wheeltec/wheeltec_ros2/src/tennis_ball_follower_ros2.backup_20261015 \
  /home/wheeltec/package_backups/
```

### 旧符号链接冲突

首次重新构建时，旧版 `--symlink-install` 产物导致配置文件链接冲突。处理方法是只清理该软件包的可再生成目录：

```bash
rm -rf \
  /home/wheeltec/wheeltec_ros2/build/tennis_ball_follower_ros2 \
  /home/wheeltec/wheeltec_ros2/install/tennis_ball_follower_ros2
```

随后重新执行：

```bash
cd /home/wheeltec/wheeltec_ros2
source /opt/ros/humble/setup.bash
colcon build \
  --packages-select tennis_ball_follower_ros2 \
  --symlink-install
```

## 启动后的验证项目

每次重新启动后建议检查：

```bash
ros2 param get /tennis_ball_follower target_distance_m
ros2 param get /tennis_ball_follower allow_reverse
ros2 param get /tennis_ball_follower max_linear_speed_mps
ros2 param get /tennis_ball_follower max_reverse_speed_mps
ros2 param get /tennis_ball_follower lidar_stop_distance_m
ros2 param get /tennis_ball_follower lidar_rear_stop_distance_m
```

并确认：

```bash
ros2 topic hz /scan
ros2 topic info /cmd_vel -v
```

- `/scan` 应稳定在约 `10 Hz`。
- `/cmd_vel` 应只有 `tennis_ball_follower` 一个发布者。
- `wheeltec_robot` 应为 `/cmd_vel` 的订阅者。

## 安全注意事项

1. 雷达水平扫描平面需要保持 360° 尽量无遮挡，尤其是车载电池不能遮住后方安全区。
2. 不要同时运行手势控制、键盘控制、导航或其他 `/cmd_vel` 发布节点。
3. 控制器每次启动默认处于 `DISABLED`，检查完成后才能发送启用命令。
4. 第一次测试新参数时，应保证前后均有足够空间，并随时准备发送 `enable=false`。
5. 不建议在没有后方雷达保护的情况下继续提高倒车速度。

## 回退方式

更新前的软件包备份保存在：

```text
/home/wheeltec/package_backups/tennis_ball_follower_ros2.backup_20261015
```

需要回退时，应先禁用并停止网球跟随节点，再恢复备份、清理该包的构建产物并重新编译。

## 版本文件

本次代码升级压缩包：

```text
tennis_ball_follower_ros2_v0.2.0.zip
```

注意：该压缩包初始默认配置为目标距离 `0.60 m`、最大前进速度 `0.20 m/s`；小车现场随后进一步调整为本文记录的 `0.50 m` 和 `0.25 m/s`。代码功能版本仍为 `0.2.0`。

