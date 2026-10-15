# Jetson Orin 上的 YOLO 小球检测

适用环境：Jetson Linux R36.4.3（JetPack 6.2）、CUDA 12.6、Python 3.10、ROS 2 Humble。

## 方案

版本 0.3.0 新增 `ball_yolo_tracker`，默认加载轻量级 `yolo11n.pt`，只保留 COCO 类别 32 `sports ball`。它不依赖颜色，因此黄绿色游泳池不应再因为颜色相近而被选中。

节点继续发布原控制器使用的兼容话题：

- `/tennis_ball/visible`
- `/tennis_ball/position`
- `/tennis_ball/yolo_debug_image`

这里的话题名中的 `tennis_ball` 仅用于兼容旧控制器，YOLO 目标是通用的 `sports ball`。

## 第一步：只检查环境，不安装

不要先执行普通的 `pip install torch torchvision`。Jetson 需要与 JetPack、CUDA 匹配的 NVIDIA PyTorch；错误的 pip 包可能让 GPU 加速失效。

在小车运行：

```bash
cat /proc/device-tree/model; echo
free -h

python3 - <<'PY'
import importlib.util

for name in ('torch', 'torchvision', 'ultralytics', 'tensorrt'):
    print(f'{name}:', 'FOUND' if importlib.util.find_spec(name) else 'MISSING')

try:
    import torch
    print('torch version:', torch.__version__)
    print('CUDA available:', torch.cuda.is_available())
    print('torch CUDA:', torch.version.cuda)
    if torch.cuda.is_available():
        print('GPU:', torch.cuda.get_device_name(0))
except Exception as exc:
    print('torch check error:', repr(exc))

try:
    import tensorrt
    print('TensorRT version:', tensorrt.__version__)
except Exception as exc:
    print('TensorRT check error:', repr(exc))
PY

dpkg-query -W 'nvidia-jetpack' 'nvidia-tensorrt' 'tensorrt' 2>/dev/null
```

根据这组输出再选择安装方式，避免破坏小车已有的 CUDA/PyTorch 环境。

如果检查结果显示 NVIDIA PyTorch、Torchvision 和 TensorRT 均已存在且 CUDA 可用，只缺少 Ultralytics，先只安装 Ultralytics 本体：

```bash
python3 -m pip install --user --no-deps ultralytics
```

`--no-deps` 很重要：它避免 pip 替换 Jetson 专用的 PyTorch、Torchvision、OpenCV 或 NumPy。安装后使用 `YOLO_AUTOINSTALL=False` 做导入检查；缺少的普通 Python 依赖再逐项补充。

## 第二步：编译 0.3.0 软件包

将新版软件包放入工作空间后执行：

```bash
cd /home/wheeltec/wheeltec_ros2
source /opt/ros/humble/setup.bash
rm -rf build/tennis_ball_follower_ros2 install/tennis_ball_follower_ros2
colcon build \
  --packages-select tennis_ball_follower_ros2 \
  --symlink-install
```

这里只删除本软件包的旧构建产物，不会删除其他 ROS 2 软件包。

## 第三步：只测试检测，不启动控制器

先启动 Astra 相机，然后在新终端加载环境：

```bash
source /opt/ros/humble/setup.bash
export AMENT_PREFIX_PATH="/home/wheeltec/wheeltec_ros2/install/tennis_ball_follower_ros2:$AMENT_PREFIX_PATH"
export PYTHONPATH="/home/wheeltec/wheeltec_ros2/install/tennis_ball_follower_ros2/lib/python3.10/site-packages:$PYTHONPATH"
export PATH="/home/wheeltec/wheeltec_ros2/install/tennis_ball_follower_ros2/lib/tennis_ball_follower_ros2:$PATH"

ros2 launch tennis_ball_follower_ros2 ball_yolo_follow.launch.py
```

实验室网络可能禁止下载 GitHub Release 附件。请在其他电脑下载官方 `yolo11n.pt`，复制到小车的 `/home/wheeltec/models/yolo11n.pt`。默认配置已经使用这个固定路径，因此运行时不会再次尝试联网下载。

检查结果：

```bash
ros2 topic echo /tennis_ball/visible --once
ros2 topic echo /tennis_ball/position --once
ros2 topic hz /tennis_ball/position
```

在 `rqt_image_view` 中选择 `/tennis_ball/yolo_debug_image`，检查框是否确实落在小球上。此阶段不要启动 `tennis_ball_follower`，小车不会运动。

## 不同尺寸小球的距离

RGB-D 深度有效时，小球的实际直径不会影响测距。如果球面导致 Astra 深度无效，程序会使用单目尺寸备用测距，此时必须将 `ball_diameter_m` 改成实际直径，否则停车距离会有系统性误差。

当前默认值 `0.067 m` 对应网球。更换乒乓球时应测量并修改为约 `0.040 m`；其他球请使用实际测量值。

## TensorRT 优化安排

先用 PyTorch 模型验证识别是否正确，再在小车本机导出 FP16 TensorRT engine。TensorRT engine 与 GPU 和运行时版本有关，不应直接使用其他电脑导出的文件。优化后的目标是减少延迟，而不是改变检测结果。

