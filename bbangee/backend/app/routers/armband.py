"""
Armband Detection Router (리팩토링)
- HTTP 자기호출(scenario/ocr) → scenario_manager 직접 참조
- 하드코딩 경로/상수 → config 모듈
- OCR 상태 제어용 internal 함수 추가 (scenario에서 직접 호출)
"""

import cv2
import numpy as np
import threading
import time
from fastapi import APIRouter, Response
from fastapi.responses import StreamingResponse
from typing import Tuple
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
from ultralytics import YOLO
import easyocr

from app.services.config import (
    ARMBAND_MODEL_PATH,
    ARMBAND_COLOR_TOPIC,
    ARMBAND_CONFIDENCE_THRESHOLD,
    ARMBAND_WARPED_SIZE,
    ARMBAND_ALLY_KEYWORDS,
    ARMBAND_ENEMY_KEYWORDS,
)

router = APIRouter(prefix="/armband", tags=["armband"])

# ==================== 전역 상태 ====================

armband_state = {
    "model": None,
    "node": None,
    "latest_frame": None,
    "latest_raw_result": None,
    "latest_roi_result": None,
    "detection_info": None,
    "ocr_result": None,
    "running": False,
    "last_update": 0,
    "ocr_enabled": False,
}
state_lock = threading.Lock()

# OCR 리더 초기화
print("EasyOCR 한글 리더 로드 중...")
ocr_reader = easyocr.Reader(["ko"], gpu=True)
print("EasyOCR 로드 완료!")


# ==================== 내부 API (scenario에서 직접 호출) ====================

def set_ocr_enabled_internal(enabled: bool):
    """scenario.py 에서 직접 호출 (HTTP 자기호출 대체)"""
    with state_lock:
        armband_state["ocr_enabled"] = enabled
        if not enabled:
            armband_state["latest_raw_result"] = None
            armband_state["latest_roi_result"] = None
            armband_state["detection_info"] = None
            armband_state["ocr_result"] = None
    print(f" OCR {'활성화' if enabled else '비활성화'}")


# ==================== 시나리오 연동 (직접 호출) ====================

def _send_ocr_to_scenario(armband_detected: bool, faction: str, confidence: float):
    """OCR 결과를 시나리오 모듈로 직접 전달 (HTTP 제거)"""
    try:
        from app.routers.scenario import scenario_manager
        import asyncio

        # 이미 이벤트 루프가 있으면 그걸 사용, 없으면 새로 생성
        try:
            loop = asyncio.get_running_loop()
            # 이미 루프가 실행 중이면 태스크로 스케줄
            asyncio.ensure_future(
                scenario_manager.process_ocr_result(armband_detected, faction, confidence)
            )
        except RuntimeError:
            # 루프가 없으면 새로 실행
            loop = asyncio.new_event_loop()
            loop.run_until_complete(
                scenario_manager.process_ocr_result(armband_detected, faction, confidence)
            )
            loop.close()
    except Exception:
        pass  # 시나리오 연동 실패는 무시


# ==================== Helper Functions ====================

def order_points(pts: np.ndarray) -> np.ndarray:
    center = np.mean(pts, axis=0)
    angles = np.arctan2(pts[:, 1] - center[1], pts[:, 0] - center[0])
    sorted_indices = np.argsort(angles)
    sorted_pts = pts[sorted_indices]
    s = sorted_pts.sum(axis=1)
    tl_idx = np.argmin(s)
    return np.roll(sorted_pts, -tl_idx, axis=0)


def crop_obb_roi(image: np.ndarray, obb_points: np.ndarray,
                 output_size: Tuple[int, int] = ARMBAND_WARPED_SIZE,
                 padding_ratio: float = 0.15) -> np.ndarray:
    x_coords = obb_points[:, 0]
    y_coords = obb_points[:, 1]
    x1, y1 = int(np.min(x_coords)), int(np.min(y_coords))
    x2, y2 = int(np.max(x_coords)), int(np.max(y_coords))

    box_w, box_h = x2 - x1, y2 - y1
    pad_x, pad_y = int(box_w * padding_ratio), int(box_h * padding_ratio)
    x1, y1 = max(0, x1 - pad_x), max(0, y1 - pad_y)
    x2, y2 = min(image.shape[1], x2 + pad_x), min(image.shape[0], y2 + pad_y)

    cropped = image[y1:y2, x1:x2]
    if cropped.size == 0:
        return np.zeros((output_size[1], output_size[0], 3), dtype=np.uint8)

    h, w = cropped.shape[:2]
    target_w, target_h = output_size
    scale = min(target_w / w, target_h / h)
    new_w, new_h = int(w * scale), int(h * scale)
    resized = cv2.resize(cropped, (new_w, new_h))

    canvas = np.zeros((target_h, target_w, 3), dtype=np.uint8)
    x_off = (target_w - new_w) // 2
    y_off = (target_h - new_h) // 2
    canvas[y_off:y_off + new_h, x_off:x_off + new_w] = resized
    return canvas


def recognize_armband_text(warped_image: np.ndarray) -> dict:
    try:
        results = ocr_reader.readtext(warped_image)
        if not results:
            return {"text": "", "confidence": 0, "faction": "UNKNOWN", "raw_results": []}

        best = max(results, key=lambda x: x[2])
        _, text, conf = best

        faction = "UNKNOWN"
        for kw in ARMBAND_ALLY_KEYWORDS:
            if kw in text:
                faction = "ALLY"
                break
        for kw in ARMBAND_ENEMY_KEYWORDS:
            if kw in text:
                faction = "ENEMY"
                break

        return {
            "text": text,
            "confidence": float(conf),
            "faction": faction,
            "raw_results": [(str(r[1]), float(r[2])) for r in results],
        }
    except Exception as e:
        print(f"OCR 오류: {e}")
        return {"text": "", "confidence": 0, "faction": "ERROR", "raw_results": []}


def draw_obb_detection(image: np.ndarray, obb_points: np.ndarray,
                       conf: float, class_name: str) -> np.ndarray:
    result = image.copy()
    points = obb_points.astype(np.int32)
    cv2.polylines(result, [points], True, (0, 255, 0), 2)
    center = np.mean(points, axis=0).astype(int)
    cv2.circle(result, tuple(center), 5, (0, 0, 255), -1)

    label = f"{class_name}: {conf:.0%}"
    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
    lx, ly = center[0] - tw // 2, center[1] - 20
    cv2.rectangle(result, (lx - 2, ly - th - 2), (lx + tw + 2, ly + 2), (0, 100, 0), -1)
    cv2.putText(result, label, (lx, ly), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    return result


# ==================== ROS2 Node ====================

class ArmbandDetectorNode(Node):
    def __init__(self):
        super().__init__("armband_detector_web")
        self.bridge = CvBridge()
        self.get_logger().info(f"모델 로드 중: {ARMBAND_MODEL_PATH}")
        self.model = YOLO(ARMBAND_MODEL_PATH)
        self.get_logger().info("모델 로드 완료!")
        self.subscription = self.create_subscription(
            Image, ARMBAND_COLOR_TOPIC, self.image_callback, 10
        )

    def image_callback(self, msg):
        try:
            cv_image = self.bridge.imgmsg_to_cv2(msg, "bgr8")
            results = self.model(cv_image, verbose=False)

            raw_result = cv_image.copy()
            roi_result = None
            detection_info = None
            ocr_result = None
            best_conf = 0
            best_obb = None

            for r in results:
                if r.obb is not None and len(r.obb) > 0:
                    for box in r.obb:
                        conf = float(box.conf.cpu().numpy()[0])
                        if conf >= ARMBAND_CONFIDENCE_THRESHOLD and conf > best_conf:
                            best_conf = conf
                            best_obb = box

            if best_obb is not None:
                obb_points = best_obb.xyxyxyxy.cpu().numpy()[0]
                cls = int(best_obb.cls.cpu().numpy()[0])
                class_name = self.model.names[cls]

                raw_result = draw_obb_detection(raw_result, obb_points, best_conf, class_name)
                roi_result = crop_obb_roi(cv_image, obb_points)
                ocr_result = recognize_armband_text(roi_result)

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

                if armband_state.get("ocr_enabled", False):
                    _send_ocr_to_scenario(True, ocr_result["faction"], ocr_result["confidence"])
            else:
                cv2.putText(raw_result, "No Armband Detected", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (100, 100, 100), 2)
                detection_info = {"detected": False}
                if armband_state.get("ocr_enabled", False):
                    _send_ocr_to_scenario(False, "UNKNOWN", 0)

            with state_lock:
                armband_state["latest_frame"] = cv_image
                armband_state["latest_raw_result"] = raw_result
                armband_state["latest_roi_result"] = roi_result
                armband_state["detection_info"] = detection_info
                if ocr_result is not None:
                    armband_state["ocr_result"] = ocr_result
                    armband_state["ocr_result_time"] = time.time()
                elif armband_state.get("ocr_result_time", 0) + 3.0 < time.time():
                    armband_state["ocr_result"] = None
                armband_state["last_update"] = time.time()

        except Exception as e:
            self.get_logger().error(f"처리 오류: {e}")


# ==================== ROS2 Thread ====================

def ros2_spin_thread():
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
    threading.Thread(target=ros2_spin_thread, daemon=True).start()
    print("Armband 감지 스레드 시작됨")


@router.get("/status")
def get_armband_status():
    with state_lock:
        info = armband_state.get("detection_info")
        ocr = armband_state.get("ocr_result")
        return {
            "running": armband_state["running"],
            "last_update": armband_state["last_update"],
            "detection": info if info else {"detected": False},
            "ocr": ocr if ocr else {"text": "", "confidence": 0, "faction": "UNKNOWN"},
            "ocr_enabled": armband_state.get("ocr_enabled", False),
        }


@router.post("/ocr/enable")
def enable_ocr():
    set_ocr_enabled_internal(True)
    return {"success": True, "ocr_enabled": True}


@router.post("/ocr/disable")
def disable_ocr():
    set_ocr_enabled_internal(False)
    return {"success": True, "ocr_enabled": False}


def _get_frame_or_placeholder(ocr_enabled: bool, frame, size=(640, 480)):
    if frame is not None:
        return frame
    placeholder = np.zeros((size[1], size[0], 3), dtype=np.uint8)
    text = "Standby..." if not ocr_enabled else "Waiting for camera..."
    pos = (250, 240) if not ocr_enabled else (150, 240)
    color = (80, 80, 80) if not ocr_enabled else (100, 100, 100)
    cv2.putText(placeholder, text, pos, cv2.FONT_HERSHEY_SIMPLEX, 1, color, 2)
    return placeholder


@router.get("/raw/frame")
def get_raw_frame():
    with state_lock:
        ocr_on = armband_state.get("ocr_enabled", False)
        frame = armband_state.get("latest_raw_result") if ocr_on else None
    frame = _get_frame_or_placeholder(ocr_on, frame)
    _, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return Response(content=jpeg.tobytes(), media_type="image/jpeg")


@router.get("/raw/stream")
def get_raw_stream():
    def generate():
        while True:
            with state_lock:
                ocr_on = armband_state.get("ocr_enabled", False)
                frame = armband_state.get("latest_raw_result") if ocr_on else None
            frame = _get_frame_or_placeholder(ocr_on, frame)
            _, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg.tobytes() + b"\r\n"
            time.sleep(0.05)

    return StreamingResponse(generate(), media_type="multipart/x-mixed-replace; boundary=frame")


@router.get("/roi/frame")
def get_roi_frame():
    ws = ARMBAND_WARPED_SIZE
    with state_lock:
        ocr_on = armband_state.get("ocr_enabled", False)
        frame = armband_state.get("latest_roi_result") if ocr_on else None
        info = armband_state.get("detection_info")

    if frame is None or (info and not info.get("detected", False)):
        placeholder = np.zeros((ws[1], ws[0], 3), dtype=np.uint8)
        txt = "Standby" if not ocr_on else "No ROI"
        cv2.putText(placeholder, txt, (50, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (80, 80, 80), 2)
        frame = placeholder

    _, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return Response(content=jpeg.tobytes(), media_type="image/jpeg")


@router.get("/roi/stream")
def get_roi_stream():
    ws = ARMBAND_WARPED_SIZE

    def generate():
        while True:
            with state_lock:
                ocr_on = armband_state.get("ocr_enabled", False)
                frame = armband_state.get("latest_roi_result") if ocr_on else None
                info = armband_state.get("detection_info")

            if frame is not None and info and info.get("detected", False):
                _, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            else:
                ph = np.zeros((ws[1], ws[0], 3), dtype=np.uint8)
                txt = "Standby" if not ocr_on else "No ROI"
                cv2.putText(ph, txt, (50, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (80, 80, 80), 2)
                _, jpeg = cv2.imencode(".jpg", ph, [cv2.IMWRITE_JPEG_QUALITY, 85])

            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg.tobytes() + b"\r\n"
            time.sleep(0.1)

    return StreamingResponse(generate(), media_type="multipart/x-mixed-replace; boundary=frame")
