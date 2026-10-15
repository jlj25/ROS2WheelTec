# Roadmap

## In progress: YOLO general ball detector

- Add a lightweight YOLO detector as a second tracker implementation. The first implementation is included in version 0.3.0.
- Validate the PyTorch implementation on Jetson Orin NX. Tennis-ball detection, RGB-D distance, and reduced-speed following are complete.
- Preserve the existing `/tennis_ball/visible` and `/tennis_ball/position` interfaces so the motion controller does not need to change.
- Start with the pretrained COCO `sports ball` class so detection is not tied to color.
- If pretrained detection is insufficient for very small balls, fine-tune a single general `ball` class with laboratory images.
- Include the yellow-green inflatable pool and other similarly colored objects as negative training examples.
- Keep depth-based distance measurement with the known-size monocular fallback.
- Run the color tracker and YOLO tracker on separate topics during A/B testing.
- Export and benchmark an FP16 TensorRT engine to improve the current ROS output rate of about 6 Hz.
- Test the pretrained detector against the yellow-green inflatable pool and additional ball types.

## Planned: obstacle avoidance while tracking

- Extend the current stop-only lidar protection into a low-speed avoidance state machine.
- Compare free space on the left and right before choosing a detour direction.
- Handle temporary target loss while going around an obstacle.
- Reacquire the ball before returning to normal tracking.
- Keep front and rear emergency-stop gates active throughout avoidance.

The current release performs emergency stopping only; it does not autonomously route around obstacles.

