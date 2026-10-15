# 小球视觉跟随系统 v0.3.0 更新说明

发布日期：2026-10-15  
软件包：`tennis_ball_follower_ros2`  
适用平台：WHEELTEC ROS 2 Humble 小车、Astra RGB-D 相机、雷神 N10Plus 激光雷达、Jetson Orin NX 16GB

## 更新目标

本次更新在原有 HSV 颜色与形状检测器之外，新增基于 Ultralytics YOLO 的通用小球检测器。第一阶段使用 COCO 预训练模型的 `sports ball` 类，不再依赖黄绿色外观，从而降低黄绿色游泳池等大型同色物体造成误跟随的风险。

原有 HSV 检测器和运动控制器均保留。YOLO 节点只发布目标位置，不直接发布 `/cmd_vel`；控制器仍需独立启动并显式启用。

## 硬件与软件环境

```text
设备：NVIDIA Jetson Orin NX Engineering Reference Developer Kit Super
内存：15 GiB
JetPack：6.2+b77
Jetson Linux：R36.4.3
CUDA：12.6
TensorRT：10.3.0
Python：3.10.12
ROS：Humble
PyTorch：2.6.0-rc1
Torchvision：0.21.0
Ultralytics：8.4.177
OpenCV：5.0.0
NumPy：1.26.4
功耗模式：MAXN_SUPER
```

PyTorch 已确认能够访问 Orin GPU。Ultralytics 使用 `--no-deps` 安装，以避免 pip 覆盖 Jetson 专用的 PyTorch、Torchvision、OpenCV 或 NumPy。

## 新增代码

### YOLO 检测节点

新增可执行程序：

```text
ball_yolo_tracker
```

主要功能：

- 加载轻量级 `yolo11n.pt`。
- 默认只保留 COCO 类别 32 `sports ball`。
- 在检测框中心区域读取 Astra 深度并取有效值中位数。
- Astra 无法返回球面深度时，按照配置的实际球直径进行单目备用测距。
- 多个候选球同时出现时，优先保持与上一帧目标位置连续的检测框。
- 使用 GPU FP16 推理，即 `quantize=16`。
- 禁用 Ultralytics 运行时自动安装，保护 Jetson 系统依赖。
- 发布调试图，但不直接控制底盘。

### 新增启动文件

```text
launch/ball_yolo_follow.launch.py
```

默认只启动 `ball_yolo_tracker`。只有显式指定 `run_controller:=true` 才会同时启动运动控制器，而控制器仍保持 `DISABLED`。

### 新增配置文件

```text
config/ball_yolo.yaml
```

当前关键配置：

```yaml
model_path: /home/wheeltec/models/yolo11n.pt
target_class_ids: [32]
confidence_threshold: 0.35
iou_threshold: 0.45
image_size: 640
device: "0"
inference_quantization: 16
allow_monocular_fallback: true
ball_diameter_m: 0.067
publish_debug_image: true
```

模型使用固定本地路径，是因为实验室网络访问 GitHub Release 附件时返回 HTTP 403。模型由 Windows 下载后通过 `scp` 传输到：

```text
/home/wheeltec/models/yolo11n.pt
```

## 兼容接口

为避免修改已经验证过的控制器，YOLO 节点继续使用原接口：

- `/tennis_ball/visible`
- `/tennis_ball/position`
- `/tennis_ball/yolo_debug_image`

话题名称中的 `tennis_ball` 仅用于向后兼容。检测类别实际为通用 `sports ball`。

HSV 与 YOLO 检测器不能同时运行，因为它们会发布相同的目标话题。

## 首轮实机测试结果

### 模型与 GPU

空白图 GPU 推理成功：

```text
preprocess: 约 25.1 ms
inference: 约 22.8 ms
postprocess: 约 2.4 ms
```

空白图检测数量为 0，符合预期。

### ROS 话题频率

关闭 `rqt_image_view` 后测得：

```text
/camera/color/image_raw: 约 23 Hz
/camera/depth/image_raw: 约 28 Hz
/tennis_ball/position: 约 5.9～6.0 Hz
/tennis_ball/yolo_debug_image: 约 5.7～5.8 Hz
```

相机帧率正常，当前瓶颈位于 PyTorch YOLO 节点的完整 ROS 处理链路。约 6 Hz 可以用于低速验证，但在恢复 `0.25 m/s` 前仍建议完成 TensorRT 优化。

### 识别与测距

- 网球能够出现稳定绿色检测框。
- 快速左右移动网球时不容易丢失。
- 手完全遮挡网球后检测丢失，属于预期行为；控制器会因 `TARGET_LOST` 停车，不根据旧位置盲目运动。
- `0.5 m`、`1.0 m`、`1.5 m` 附近的测距结果基本正确。
- 当前只完成网球测试，其他球类及黄绿色游泳池仍需现场复测。

### 低速实车跟随

首次 YOLO 实车测试采用临时限速：

```yaml
max_linear_speed_mps: 0.10
max_angular_speed_rps: 0.30
max_reverse_speed_mps: 0.04
```

测试结果：

- 小车能够向网球靠近。
- 约在原设定目标距离 `0.50 m` 附近停止。
- 网球左右移动时能够转向跟随。
- 检测丢失后能够安全停车。
- 雷达安全门和显式启用机制继续生效。

上述限速通过命令行参数临时覆盖，代码中的日常配置仍保留：前进 `0.25 m/s`、倒车 `0.06 m/s`、角速度 `0.55 rad/s`。

## 图形调试

小车安装：

```bash
sudo apt install xauth ros-humble-rqt-image-view
```

Windows 使用 XLaunch，并通过带 X11 转发的新 SSH 会话连接：

```powershell
$env:DISPLAY="127.0.0.1:0.0"
ssh -Y wheeltec@小车IP
```

小车中使用 ROS 2 启动插件：

```bash
source /opt/ros/humble/setup.bash
ros2 run rqt_image_view rqt_image_view
```

选择 `/tennis_ball/yolo_debug_image`。X11 图像转发延迟较大，因此只用于调试，正式跟随时应关闭。

## 已知警告与处理原则

### Torchvision 的 libnvjpeg 警告

Torchvision 报告缺少 `libnvjpeg.so.12`。当前程序使用 OpenCV 和 `cv_bridge` 读取图像，不使用 `torchvision.io`，且 GPU 推理已经成功，因此本阶段不处理该警告。

### pip check 的附加依赖提示

`pip check` 报告 Ultralytics 缺少 `nvidia-ml-py`、`opencv-python`、`polars` 和 `ultralytics-thop`。当前实时检测路径已经成功运行，不依赖这些监控、表格或模型分析功能。

特别注意：系统已经存在 `opencv-contrib-python`，不要为了满足包元数据再安装 `opencv-python`，以免影响 ROS `cv_bridge`。其他与本项目无关的 Mediapipe、Jupyter 和 pipx 依赖提示也暂不处理。

## 安全要求

1. YOLO 和 HSV 检测器不能同时发布目标话题。
2. `/cmd_vel` 只能保留 `tennis_ball_follower` 一个发布者。
3. 控制器启动后默认为 `DISABLED`，检查相机、目标、雷达和速度连接后才可启用。
4. 遮挡或目标丢失时继续保持停车策略，不延长旧目标预测来驱动小车。
5. 在 YOLO 输出仍约为 6 Hz 时，应优先采用低速测试参数。
6. 调试画面只用于观察，不作为安全判断依据。

## 后续计划

1. 在 Orin NX 本机导出并测试 FP16 TensorRT engine。
2. 比较 TensorRT 与 PyTorch 的检测准确率、端到端话题频率和延迟。
3. 将调试图发布改为非阻塞方式，并在正式运行配置中关闭。
4. 使用黄绿色游泳池验证误识别是否消除。
5. 测试足球、篮球、乒乓球等不同尺寸目标；单目备用测距时同步修改 `ball_diameter_m`。
6. 按 `0.10 → 0.15 → 0.20 → 0.25 m/s` 逐级恢复跟随速度。
7. 如果预训练模型对小尺寸球漏检，再收集实验室图像并微调统一的 `ball` 类模型。

## 相关文档与代码

- GitHub 仓库：<https://github.com/jlj25/ROS2WheelTec>
- Jetson 配置说明：`docs/YOLO_JETSON_SETUP_zh-CN.md`
- 每次启动说明：`docs/WHEELTEC_网球追踪_下次启动说明.md`
- v0.2.0 更新说明：`docs/UPDATE_NOTES_v0.2.0_zh-CN.md`

