#!/usr/bin/env python3
"""
YOLO Face Detector - 순수 감지 로직

TensorRT 최적화를 포함한 YOLOv8 기반 얼굴 감지기
ROS2 의존성 없음 - 순수 Python 클래스

Features:
    - TensorRT 엔진 자동 변환 (NVIDIA GPU)
    - FP16 Half Precision 추론
    - ROI 기반 빠른 추적
    - CLAHE 전처리 (조명 보정)
"""
import cv2
import numpy as np
import os
import time
from typing import Optional, Tuple, Dict, List
from dataclasses import dataclass


@dataclass
class Detection:
    """감지 결과 데이터 클래스"""
    x1: int
    y1: int
    x2: int
    y2: int
    confidence: float
    
    @property
    def center(self) -> Tuple[int, int]:
        """바운딩 박스 중심점"""
        return ((self.x1 + self.x2) // 2, (self.y1 + self.y2) // 2)
    
    @property
    def width(self) -> int:
        return self.x2 - self.x1
    
    @property
    def height(self) -> int:
        return self.y2 - self.y1
    
    @property
    def area(self) -> int:
        return self.width * self.height


class YoloDetector:
    """
    YOLOv8 기반 얼굴 감지기
    
    TensorRT 최적화와 ROI 기반 추적을 지원합니다.
    """
    
    def __init__(
        self,
        model_path: str = '',
        confidence_threshold: float = 0.4,
        use_gpu: bool = True,
        use_tensorrt: bool = True,
        use_fp16: bool = True,
        input_size: int = 1280,
        use_preprocessing: bool = True,
        use_roi_tracking: bool = True,
        logger=None
    ):
        """
        Args:
            model_path: YOLO 모델 경로 (.pt 또는 .engine)
            confidence_threshold: 감지 신뢰도 임계값
            use_gpu: GPU 사용 여부
            use_tensorrt: TensorRT 최적화 사용
            use_fp16: FP16 추론 사용
            input_size: 입력 이미지 크기
            use_preprocessing: CLAHE 전처리 적용
            use_roi_tracking: ROI 기반 추적 사용
            logger: 로거 (ROS2 logger 또는 print)
        """
        self.confidence_threshold = confidence_threshold
        self.use_tensorrt = use_tensorrt
        self.use_fp16 = use_fp16
        self.input_size = input_size
        self.use_preprocessing = use_preprocessing
        self.use_roi_tracking = use_roi_tracking
        self.logger = logger
        
        # 모델 경로 설정
        self.model_path = self._resolve_model_path(model_path)
        
        # GPU 설정
        self.device, self.cuda_available = self._setup_device(use_gpu)
        
        # TensorRT 불가 시 비활성화
        if not self.cuda_available:
            self.use_tensorrt = False
            self.use_fp16 = False
        
        # 모델 로드
        self.model = self._load_model()
        
        # CLAHE 초기화
        self.clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        
        # ROI 추적 상태
        self.last_detection: Optional[Detection] = None
        self.roi_margin = 100  # 픽셀
        self.roi_fail_count = 0
        self.max_roi_fail = 3
        
        # 깜빡임 방지
        self.no_detection_count = 0
        self.max_no_detection = 5
        
        # 성능 측정
        self.inference_times: List[float] = []
        self.avg_inference_time = 0.0
    
    def _log(self, msg: str, level: str = 'info'):
        """로그 출력"""
        if self.logger:
            if hasattr(self.logger, level):
                getattr(self.logger, level)(msg)
            else:
                self.logger(msg)
        else:
            print(f"[{level.upper()}] {msg}")
    
    def _resolve_model_path(self, model_path: str) -> str:
        """모델 경로 확인 및 기본 경로 설정"""
        if model_path and os.path.exists(model_path):
            return model_path
        
        # 기본 경로들
        default_paths = [
            '/home/rokey/ros2_ws/src/rokey_packages/face_tracking/models/yolov8n-face.pt',
            '/home/rokey/ros2_ws/src/face_tracking/models/yolov8n-face.pt',
            '/home/rokey/ros2_ws/src/face_tracking_pkg/models/yolov8n-face.pt',
        ]
        
        for path in default_paths:
            if os.path.exists(path):
                return path
        
        raise FileNotFoundError(f"모델 파일을 찾을 수 없습니다: {default_paths}")
    
    def _setup_device(self, use_gpu: bool) -> Tuple[str, bool]:
        """GPU 설정"""
        if not use_gpu:
            return 'cpu', False
        
        try:
            import torch
            if torch.cuda.is_available():
                gpu_name = torch.cuda.get_device_name(0)
                self._log(f"🚀 GPU 감지: {gpu_name}")
                return 'cuda', True
        except Exception as e:
            self._log(f"⚠️ GPU 확인 실패: {e}", 'warn')
        
        return 'cpu', False
    
    def _load_model(self):
        """모델 로드 (TensorRT 우선)"""
        from ultralytics import YOLO
        
        engine_path = self.model_path.replace('.pt', '.engine')
        
        # TensorRT 엔진 로드 시도
        if self.use_tensorrt and self.cuda_available:
            if os.path.exists(engine_path):
                self._log(f"🔥 TensorRT 엔진 로딩: {engine_path}")
                try:
                    model = YOLO(engine_path)
                    self._log("✅ TensorRT 엔진 로드 성공!")
                    return model
                except Exception as e:
                    self._log(f"⚠️ TensorRT 로드 실패: {e}", 'warn')
            
            # TensorRT 엔진 생성
            self._log("🔧 TensorRT 엔진 생성 중... (1-2분 소요)")
            try:
                model = YOLO(self.model_path)
                model.export(
                    format='engine',
                    half=self.use_fp16,
                    imgsz=self.input_size,
                    device=0
                )
                if os.path.exists(engine_path):
                    self._log("✅ TensorRT 엔진 생성 완료!")
                    return YOLO(engine_path)
            except Exception as e:
                self._log(f"⚠️ TensorRT 변환 실패: {e}", 'warn')
        
        # 일반 YOLO 모델
        self._log(f"🔄 YOLO 모델 로딩: {self.model_path}")
        return YOLO(self.model_path)
    
    def preprocess(self, frame: np.ndarray) -> np.ndarray:
        """
        이미지 전처리 (CLAHE 적응형 히스토그램 평활화)
        
        조명 변화에 강건한 감지를 위해 적용
        """
        if not self.use_preprocessing:
            return frame
        
        # LAB 색공간 변환
        lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        lab[:, :, 0] = self.clahe.apply(lab[:, :, 0])
        return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    
    def _get_roi(self, frame_shape: Tuple[int, ...]) -> Optional[Tuple[int, int, int, int]]:
        """이전 감지 기반 ROI 계산"""
        if not self.use_roi_tracking or self.last_detection is None:
            return None
        
        h, w = frame_shape[:2]
        det = self.last_detection
        
        x1 = max(0, det.x1 - self.roi_margin)
        y1 = max(0, det.y1 - self.roi_margin)
        x2 = min(w, det.x2 + self.roi_margin)
        y2 = min(h, det.y2 + self.roi_margin)
        
        if (x2 - x1) < 100 or (y2 - y1) < 100:
            return None
        
        return (x1, y1, x2, y2)
    
    def _detect_in_roi(self, frame: np.ndarray, roi: Tuple[int, int, int, int]):
        """ROI 영역에서 감지"""
        x1, y1, x2, y2 = roi
        roi_frame = frame[y1:y2, x1:x2]
        
        results = self.model.predict(
            roi_frame,
            conf=self.confidence_threshold,
            device=self.device,
            half=self.use_fp16 and self.cuda_available,
            verbose=False
        )
        return results, (x1, y1)
    
    def _detect_full(self, frame: np.ndarray):
        """전체 프레임 감지"""
        results = self.model.predict(
            frame,
            conf=self.confidence_threshold,
            device=self.device,
            imgsz=self.input_size,
            half=self.use_fp16 and self.cuda_available,
            verbose=False
        )
        return results
    
    def detect(self, frame: np.ndarray) -> Optional[Detection]:
        """
        프레임에서 얼굴 감지
        
        Args:
            frame: BGR 이미지 (numpy array)
        
        Returns:
            Detection 또는 None
        """
        # 전처리
        processed = self.preprocess(frame)
        
        # 추론 시간 측정
        start_time = time.time()
        
        # ROI 기반 감지 시도
        results = None
        offset = (0, 0)
        roi = self._get_roi(frame.shape)
        
        if roi is not None:
            results, offset = self._detect_in_roi(processed, roi)
            
            # ROI 실패 시 전체 프레임
            if not results or len(results) == 0 or \
               results[0].boxes is None or len(results[0].boxes) == 0:
                self.roi_fail_count += 1
                if self.roi_fail_count >= self.max_roi_fail:
                    results = self._detect_full(processed)
                    offset = (0, 0)
                    self.roi_fail_count = 0
            else:
                self.roi_fail_count = 0
        else:
            results = self._detect_full(processed)
        
        # 추론 시간 기록
        inference_time = (time.time() - start_time) * 1000
        self.inference_times.append(inference_time)
        if len(self.inference_times) > 30:
            self.inference_times.pop(0)
        self.avg_inference_time = sum(self.inference_times) / len(self.inference_times)
        
        # 결과 처리 - 가장 큰 얼굴 선택
        best_detection = None
        max_area = 0
        offset_x, offset_y = offset
        
        if results and len(results) > 0 and results[0].boxes is not None:
            for box in results[0].boxes:
                coords = box.xyxy[0].cpu().numpy().copy()
                x1 = int(coords[0] + offset_x)
                y1 = int(coords[1] + offset_y)
                x2 = int(coords[2] + offset_x)
                y2 = int(coords[3] + offset_y)
                conf = float(box.conf[0].cpu().numpy())
                area = (x2 - x1) * (y2 - y1)
                
                if area > max_area:
                    max_area = area
                    best_detection = Detection(x1, y1, x2, y2, conf)
        
        # 깜빡임 방지
        if best_detection is None:
            self.no_detection_count += 1
            if self.last_detection and self.no_detection_count <= self.max_no_detection:
                # 이전 감지 유지 (신뢰도 감쇠)
                decay = 0.9 ** self.no_detection_count
                best_detection = Detection(
                    self.last_detection.x1,
                    self.last_detection.y1,
                    self.last_detection.x2,
                    self.last_detection.y2,
                    self.last_detection.confidence * decay
                )
        else:
            self.no_detection_count = 0
            self.last_detection = best_detection
        
        return best_detection
    
    def get_stats(self) -> Dict:
        """성능 통계 반환"""
        return {
            'avg_inference_ms': self.avg_inference_time,
            'device': self.device,
            'tensorrt': self.use_tensorrt and self.cuda_available,
            'fp16': self.use_fp16 and self.cuda_available,
            'roi_tracking': self.use_roi_tracking,
        }
