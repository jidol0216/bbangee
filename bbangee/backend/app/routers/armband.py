"""
Armband Detection Router - OBB 기반 완장 감지 API

1차 피아식별용 완장 감지
- Raw 이미지: OBB 바운딩 박스가 표시된 원본
- Warped 이미지: ROI를 펼쳐서 정렬한 이미지
- OCR: 완장 텍스트 인식 (통일/멸공)
"""

import cv2
import numpy as np
import threading
import time
import io
from fastapi import APIRouter, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, Tuple, List
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from cv_bridge import CvBridge

# YOLO OBB
from ultralytics import YOLO

# EasyOCR for Korean text recognition
import easyocr

router = APIRouter(prefix="/armband", tags=["armband"])

# ==================== 설정 ====================
MODEL_PATH = "/home/rokey/ros2_ws/src/obb/runs/obb/armband_v1/weights/best.pt"
COLOR_TOPIC = "/camera/camera/color/image_raw"
CONFIDENCE_THRESHOLD = 0.5
WARPED_SIZE = (200, 80)  # 펼친 ROI 크기 (가로, 세로)

# 아군/적군 판별 키워드
ALLY_KEYWORDS = ["통일"]      # 아군 키워드
ENEMY_KEYWORDS = ["멸공"]     # 적군 키워드

# ==================== 전역 상태 ====================
armband_state = {
    "model": None,
    "ocr_reader": None,             # EasyOCR 리더
    "bridge": None,
    "node": None,
    "latest_frame": None,
    "latest_raw_result": None,      # OBB 박스가 그려진 이미지
    "latest_warped_result": None,   # 펼친 ROI 이미지
    "detection_info": None,         # 감지 정보
    "ocr_result": None,             # OCR 결과
    "running": False,
    "last_update": 0,
}
state_lock = threading.Lock()

# OCR 리더 초기화 (서버 시작 시 한 번만)
print("EasyOCR 한글 리더 로드 중...")
ocr_reader = easyocr.Reader(['ko'], gpu=True)
print("EasyOCR 로드 완료!")


# ==================== Helper Functions ====================

def order_points(pts: np.ndarray) -> np.ndarray:
    """
    OBB 4개 점을 순서대로 정렬 (top-left, top-right, bottom-right, bottom-left)
    """
    # 중심점 계산
    center = np.mean(pts, axis=0)
    
    # 각 점의 각도 계산
    angles = np.arctan2(pts[:, 1] - center[1], pts[:, 0] - center[0])
    
    # 각도로 정렬 (반시계 방향)
    sorted_indices = np.argsort(angles)
    sorted_pts = pts[sorted_indices]
    
    # top-left가 첫 번째가 되도록 조정
    # 가장 왼쪽 위 점 찾기
    s = sorted_pts.sum(axis=1)
    tl_idx = np.argmin(s)
    
    # 순서 재배열
    ordered = np.roll(sorted_pts, -tl_idx, axis=0)
    
    return ordered


def warp_obb_roi(image: np.ndarray, obb_points: np.ndarray, 
                 output_size: Tuple[int, int] = WARPED_SIZE) -> np.ndarray:
    """
    OBB ROI를 직사각형으로 펼치기 (perspective transform)
    """
    # 점 순서 정렬
    ordered_pts = order_points(obb_points)
    
    # 목표 좌표 (직사각형)
    w, h = output_size
    dst_pts = np.array([
        [0, 0],
        [w - 1, 0],
        [w - 1, h - 1],
        [0, h - 1]
    ], dtype=np.float32)
    
    # Perspective Transform
    src_pts = ordered_pts.astype(np.float32)
    M = cv2.getPerspectiveTransform(src_pts, dst_pts)
    warped = cv2.warpPerspective(image, M, (w, h))
    
    return warped


def recognize_armband_text(warped_image: np.ndarray) -> dict:
    """
    Warped ROI 이미지에서 한글 텍스트 인식
    
    Returns:
        {
            "text": "통일",           # 인식된 텍스트
            "confidence": 0.99,       # 신뢰도
            "faction": "ALLY",        # ALLY, ENEMY, UNKNOWN
            "raw_results": [...]      # 전체 OCR 결과
        }
    """
    global ocr_reader
    
    try:
        # OCR 실행
        results = ocr_reader.readtext(warped_image)
        
        if not results:
            return {
                "text": "",
                "confidence": 0,
                "faction": "UNKNOWN",
                "raw_results": []
            }
        
        # 가장 높은 신뢰도 결과 선택
        best_result = max(results, key=lambda x: x[2])
        bbox, text, conf = best_result
        
        # 아군/적군 판별
        faction = "UNKNOWN"
        for keyword in ALLY_KEYWORDS:
            if keyword in text:
                faction = "ALLY"
                break
        for keyword in ENEMY_KEYWORDS:
            if keyword in text:
                faction = "ENEMY"
                break
        
        return {
            "text": text,
            "confidence": float(conf),
            "faction": faction,
            "raw_results": [(str(r[1]), float(r[2])) for r in results]
        }
        
    except Exception as e:
        print(f"OCR 오류: {e}")
        return {
            "text": "",
            "confidence": 0,
            "faction": "ERROR",
            "raw_results": []
        }


def draw_obb_detection(image: np.ndarray, obb_points: np.ndarray, 
                       conf: float, class_name: str) -> np.ndarray:
    """
    OBB 바운딩 박스와 정보를 이미지에 그리기
    """
    result = image.copy()
    points = obb_points.astype(np.int32)
    
    # OBB 박스 그리기 (초록색)
    cv2.polylines(result, [points], True, (0, 255, 0), 2)
    
    # 중심점
    center = np.mean(points, axis=0).astype(int)
    cv2.circle(result, tuple(center), 5, (0, 0, 255), -1)
    
    # 라벨
    label = f"{class_name}: {conf:.0%}"
    (text_w, text_h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
    
    # 라벨 배경
    label_x = center[0] - text_w // 2
    label_y = center[1] - 20
    cv2.rectangle(result, 
                  (label_x - 2, label_y - text_h - 2),
                  (label_x + text_w + 2, label_y + 2),
                  (0, 100, 0), -1)
    cv2.putText(result, label, (label_x, label_y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    
    return result


class ArmbandDetectorNode(Node):
    """ROS2 노드: RealSense에서 이미지 받아 Armband 감지"""
    
    def __init__(self):
        super().__init__('armband_detector_web')
        
        self.bridge = CvBridge()
        
        # YOLO 모델 로드
        self.get_logger().info(f"모델 로드 중: {MODEL_PATH}")
        self.model = YOLO(MODEL_PATH)
        self.get_logger().info("모델 로드 완료!")
        
        # 이미지 구독
        self.subscription = self.create_subscription(
            Image,
            COLOR_TOPIC,
            self.image_callback,
            10
        )
        
        self.get_logger().info(f"Armband 감지 시작: {COLOR_TOPIC}")
    
    def image_callback(self, msg):
        global armband_state
        
        try:
            # ROS 이미지 -> OpenCV
            cv_image = self.bridge.imgmsg_to_cv2(msg, "bgr8")
            
            # YOLO OBB 추론
            results = self.model(cv_image, verbose=False)
            
            raw_result = cv_image.copy()
            warped_result = None
            detection_info = None
            best_conf = 0
            best_obb = None
            
            for result in results:
                if result.obb is not None and len(result.obb) > 0:
                    for box in result.obb:
                        conf = float(box.conf.cpu().numpy()[0])
                        
                        if conf >= CONFIDENCE_THRESHOLD and conf > best_conf:
                            best_conf = conf
                            best_obb = box
            
            # 가장 높은 신뢰도의 감지 결과 처리
            if best_obb is not None:
                obb_points = best_obb.xyxyxyxy.cpu().numpy()[0]
                cls = int(best_obb.cls.cpu().numpy()[0])
                class_name = self.model.names[cls]
                
                # Raw 이미지에 OBB 그리기
                raw_result = draw_obb_detection(raw_result, obb_points, best_conf, class_name)
                
                # Warped ROI 생성
                warped_result = warp_obb_roi(cv_image, obb_points)
                
                # OCR 실행 (한글 텍스트 인식)
                ocr_result = recognize_armband_text(warped_result)
                
                # 감지 정보
                center = np.mean(obb_points, axis=0)
                detection_info = {
                    "detected": True,
                    "class": class_name,
                    "confidence": best_conf,
                    "center": center.tolist(),
                    "ocr_text": ocr_result["text"],
                    "ocr_confidence": ocr_result["confidence"],
                    "faction": ocr_result["faction"],
                }
            else:
                # 감지 없음
                cv2.putText(raw_result, "No Armband Detected", (10, 30),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (100, 100, 100), 2)
                detection_info = {"detected": False}
                ocr_result = None
            
            # 상태 업데이트
            with state_lock:
                armband_state["latest_frame"] = cv_image
                armband_state["latest_raw_result"] = raw_result
                armband_state["latest_warped_result"] = warped_result
                armband_state["detection_info"] = detection_info
                armband_state["ocr_result"] = ocr_result
                armband_state["last_update"] = time.time()
                
        except Exception as e:
            self.get_logger().error(f"처리 오류: {e}")


# ==================== ROS2 스레드 ====================

def ros2_spin_thread():
    """ROS2 노드 스핀 스레드"""
    global armband_state
    
    try:
        if not rclpy.ok():
            rclpy.init()
        
        node = ArmbandDetectorNode()
        armband_state["node"] = node
        armband_state["running"] = True
        
        while armband_state["running"] and rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0.1)
            
    except Exception as e:
        print(f"ROS2 스레드 오류: {e}")
    finally:
        armband_state["running"] = False


# ==================== Endpoints ====================

@router.on_event("startup")
async def startup_armband():
    """서버 시작 시 ROS2 노드 시작"""
    thread = threading.Thread(target=ros2_spin_thread, daemon=True)
    thread.start()
    print("Armband 감지 스레드 시작됨")


@router.get("/status")
def get_armband_status():
    """Armband 감지 상태 조회 (OCR 결과 포함)"""
    with state_lock:
        info = armband_state.get("detection_info")
        ocr = armband_state.get("ocr_result")
        return {
            "running": armband_state["running"],
            "last_update": armband_state["last_update"],
            "detection": info if info else {"detected": False},
            "ocr": ocr if ocr else {"text": "", "confidence": 0, "faction": "UNKNOWN"}
        }


@router.get("/raw/frame")
def get_raw_frame():
    """Raw 이미지 (OBB 박스 표시) - 단일 프레임"""
    with state_lock:
        frame = armband_state.get("latest_raw_result")
        
    if frame is None:
        # 플레이스홀더 이미지
        placeholder = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.putText(placeholder, "Waiting for camera...", (150, 240),
                   cv2.FONT_HERSHEY_SIMPLEX, 1, (100, 100, 100), 2)
        frame = placeholder
    
    _, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return Response(content=jpeg.tobytes(), media_type="image/jpeg")


@router.get("/raw/stream")
def get_raw_stream():
    """Raw 이미지 MJPEG 스트림"""
    def generate():
        while True:
            with state_lock:
                frame = armband_state.get("latest_raw_result")
            
            if frame is not None:
                _, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
            
            time.sleep(0.05)  # ~20fps
    
    return StreamingResponse(generate(), media_type="multipart/x-mixed-replace; boundary=frame")


@router.get("/warped/frame")
def get_warped_frame():
    """Warped ROI 이미지 - 단일 프레임"""
    with state_lock:
        frame = armband_state.get("latest_warped_result")
        info = armband_state.get("detection_info")
    
    if frame is None or (info and not info.get("detected", False)):
        # 플레이스홀더
        placeholder = np.zeros((WARPED_SIZE[1], WARPED_SIZE[0], 3), dtype=np.uint8)
        cv2.putText(placeholder, "No ROI", (50, 45),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (100, 100, 100), 2)
        frame = placeholder
    
    _, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return Response(content=jpeg.tobytes(), media_type="image/jpeg")


@router.get("/warped/stream")
def get_warped_stream():
    """Warped ROI MJPEG 스트림"""
    def generate():
        while True:
            with state_lock:
                frame = armband_state.get("latest_warped_result")
                info = armband_state.get("detection_info")
            
            if frame is not None and info and info.get("detected", False):
                _, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
            else:
                # 플레이스홀더
                placeholder = np.zeros((WARPED_SIZE[1], WARPED_SIZE[0], 3), dtype=np.uint8)
                cv2.putText(placeholder, "No ROI", (50, 45),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (100, 100, 100), 2)
                _, jpeg = cv2.imencode('.jpg', placeholder, [cv2.IMWRITE_JPEG_QUALITY, 85])
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
            
            time.sleep(0.1)  # ~10fps (ROI는 덜 자주 업데이트해도 됨)
    
    return StreamingResponse(generate(), media_type="multipart/x-mixed-replace; boundary=frame")
