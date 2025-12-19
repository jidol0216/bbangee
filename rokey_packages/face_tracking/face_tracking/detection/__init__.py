"""
Detection Module - Face Detection using YOLOv8

Classes:
    YoloDetector: YOLO-based face detector with TensorRT optimization
    
Nodes:
    face_detection_node: ROS2 node for face detection
"""
from .yolo_detector import YoloDetector

__all__ = ['YoloDetector']
