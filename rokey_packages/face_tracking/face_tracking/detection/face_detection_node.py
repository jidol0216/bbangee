#!/usr/bin/env python3
"""
Face Detection Node - ROS2 인터페이스

YoloDetector를 사용한 얼굴 감지 ROS2 노드
감지 결과를 토픽으로 발행

Subscribed Topics:
    /camera/camera/color/image_raw - RealSense 컬러 이미지
    /joint_tracking/state - 추적 상태 (IDLE, TRACKING 등)

Published Topics:
    /face_detection/image - 얼굴 표시된 이미지
    /face_detection/faces - 얼굴 좌표 [center_x, center_y, w, h]
"""
import cv2
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import Float32MultiArray, String
from cv_bridge import CvBridge
import threading
import requests
import sys
from pathlib import Path

from .yolo_detector import YoloDetector, Detection
import numpy as np


class HierarchicalIFFFilter:
    """
    2단계 계층적 베이지안 IFF 필터
    
    CNN의 2단계 구조에 맞춰 설계:
    - Stage 1: 완장 유무 신념 (NO_BAND vs BAND)
    - Stage 2: 텍스트 분류 신념 (TONGIL vs MELGONG)
    
    핵심 원리:
    1. Stage 1이 BAND로 확정될 때까지 Stage 2 업데이트 보류
    2. Stage 1 확정 후 Stage 2에서 ALLY/ENEMY 결정
    3. 각 단계는 독립적인 신념 배열 유지
    """
    
    def __init__(self, 
                 band_threshold=0.75,    # Stage 1: 완장 있음 확정 임계값
                 text_threshold=0.70,    # Stage 2: 텍스트 확정 임계값
                 decay=0.92,             # 시간 감쇠 (신념 유지력)
                 learning_rate=0.35):    # 새 관측 반영 비율
        """
        Args:
            band_threshold: Stage 1에서 BAND 확정 임계값 (75%)
            text_threshold: Stage 2에서 TONGIL/MELGONG 확정 임계값 (70%)
            decay: 시간 감쇠 계수 (uniform으로 회귀)
            learning_rate: 새 관측의 가중치 (높을수록 빠른 반응)
        """
        self.band_threshold = band_threshold
        self.text_threshold = text_threshold
        self.decay = decay
        self.learning_rate = learning_rate
        
        # Stage 1: 완장 유무 신념 [NO_BAND, BAND]
        self.band_belief = np.array([0.5, 0.5], dtype=np.float64)
        
        # Stage 2: 텍스트 분류 신념 [TONGIL, MELGONG]
        self.text_belief = np.array([0.5, 0.5], dtype=np.float64)
        
        # 상태 추적
        self.update_count = 0
        self.band_confirmed = False      # Stage 1 확정 여부
        self.text_confirmed = False      # Stage 2 확정 여부
        self.confirmed_state = None      # 최종 확정 상태
        self.confirmed_count = 0         # 연속 확정 횟수
        
        # 상태 레이블
        self.band_labels = ['NO_BAND', 'BAND']
        self.text_labels = ['TONGIL', 'MELGONG']
        self.iff_states = ['ALLY', 'ENEMY', 'UNKNOWN']
    
    def update(self, stage1, stage2):
        """
        2단계 계층적 베이지안 업데이트
        
        Args:
            stage1: dict {'no_band': float, 'has_band': float} - Stage 1 CNN 출력
            stage2: dict {'tongil': float, 'melgong': float} - Stage 2 CNN 출력
        
        Returns:
            dict: 업데이트된 신념 정보
        """
        self.update_count += 1
        
        # ========================================
        # Stage 1: 완장 유무 신념 업데이트 (항상 수행)
        # ========================================
        obs_band = np.array([stage1['no_band'], stage1['has_band']], dtype=np.float64)
        obs_band = np.clip(obs_band, 0.01, 0.99)
        
        # 시간 감쇠 (uniform 방향으로)
        uniform_band = np.array([0.5, 0.5])
        self.band_belief = self.decay * self.band_belief + (1 - self.decay) * uniform_band
        
        # 베이지안 업데이트: posterior ∝ likelihood × prior
        self.band_belief = self.band_belief * obs_band
        self.band_belief /= self.band_belief.sum()  # 정규화
        
        # Stage 1 확정 체크
        band_prob = self.band_belief[1]  # BAND 확률
        no_band_prob = self.band_belief[0]  # NO_BAND 확률
        
        # ========================================
        # Stage 2: 텍스트 신념 업데이트 (BAND 신호 있을 때만)
        # ========================================
        # Stage 1이 BAND 방향으로 기울어지면 Stage 2도 업데이트
        # (완전 확정 전에도 부분적으로 학습 시작)
        if band_prob >= 0.55:  # BAND가 우세해지기 시작하면
            obs_text = np.array([stage2['tongil'], stage2['melgong']], dtype=np.float64)
            obs_text = np.clip(obs_text, 0.01, 0.99)
            
            # Stage 1 확정도에 비례한 학습률 조정
            # BAND가 확실할수록 Stage 2 학습 강화
            stage2_weight = min(1.0, (band_prob - 0.55) / 0.20)  # 0.55~0.75 → 0~1
            effective_lr = self.learning_rate * (0.3 + 0.7 * stage2_weight)
            
            # 시간 감쇠 (약하게)
            uniform_text = np.array([0.5, 0.5])
            self.text_belief = 0.95 * self.text_belief + 0.05 * uniform_text
            
            # 베이지안 업데이트
            self.text_belief = self.text_belief * obs_text
            self.text_belief /= self.text_belief.sum()
        else:
            # NO_BAND 우세 시 Stage 2를 uniform으로 빠르게 감쇠
            # 이전 텍스트 분류 정보를 잊어야 다음 완장 인식 시 깨끗하게 시작
            uniform_text = np.array([0.5, 0.5])
            decay_to_uniform = 0.7  # 빠른 망각
            self.text_belief = decay_to_uniform * self.text_belief + (1 - decay_to_uniform) * uniform_text
        
        # ========================================
        # 최종 IFF 상태 결정
        # ========================================
        tongil_prob = self.text_belief[0]
        melgong_prob = self.text_belief[1]
        
        # 판정 로직:
        # 1. NO_BAND가 threshold 이상 → UNKNOWN
        # 2. BAND + TONGIL threshold 이상 → ALLY
        # 3. BAND + MELGONG threshold 이상 → ENEMY
        # 4. 그 외 → UNKNOWN (불확실)
        
        if no_band_prob >= self.band_threshold:
            # Stage 1: NO_BAND 확정
            iff_state = 'UNKNOWN'
            confidence = no_band_prob
            is_confirmed = True
            self.band_confirmed = True
            self.text_confirmed = False
        elif band_prob >= self.band_threshold:
            # Stage 1: BAND 확정 → Stage 2로 진행
            self.band_confirmed = True
            
            if tongil_prob >= self.text_threshold:
                # Stage 2: TONGIL 확정 → ALLY
                iff_state = 'ALLY'
                confidence = band_prob * tongil_prob
                is_confirmed = True
                self.text_confirmed = True
            elif melgong_prob >= self.text_threshold:
                # Stage 2: MELGONG 확정 → ENEMY
                iff_state = 'ENEMY'
                confidence = band_prob * melgong_prob
                is_confirmed = True
                self.text_confirmed = True
            else:
                # Stage 2 미확정 (텍스트 불확실)
                if tongil_prob > melgong_prob:
                    iff_state = 'ALLY'
                    confidence = band_prob * tongil_prob
                else:
                    iff_state = 'ENEMY'
                    confidence = band_prob * melgong_prob
                is_confirmed = False
                self.text_confirmed = False
        else:
            # Stage 1 미확정 (완장 유무 불확실)
            self.band_confirmed = False
            self.text_confirmed = False
            iff_state = 'UNKNOWN'
            confidence = max(no_band_prob, 1.0 - band_prob)
            is_confirmed = False
        
        # 확정 카운트 업데이트
        if is_confirmed:
            if self.confirmed_state == iff_state:
                self.confirmed_count += 1
            else:
                self.confirmed_state = iff_state
                self.confirmed_count = 1
        else:
            # 미확정 시 카운트 감소 (급격히 리셋하지 않음)
            self.confirmed_count = max(0, self.confirmed_count - 1)
            if self.confirmed_count == 0:
                self.confirmed_state = None
        
        # 3-상태 belief 배열 생성 (하위 호환성)
        # ALLY = BAND × TONGIL, ENEMY = BAND × MELGONG, UNKNOWN = NO_BAND
        belief_3state = np.array([
            band_prob * tongil_prob,   # ALLY
            band_prob * melgong_prob,  # ENEMY
            no_band_prob               # UNKNOWN
        ])
        belief_3state /= belief_3state.sum()
        
        return {
            'state': iff_state,
            'confidence': confidence,
            'belief': belief_3state,
            'is_confirmed': is_confirmed,
            'confirmed_count': self.confirmed_count,
            # 추가 디버그 정보
            'band_belief': self.band_belief.copy(),
            'text_belief': self.text_belief.copy(),
            'band_confirmed': self.band_confirmed,
            'text_confirmed': self.text_confirmed
        }
    
    def reset(self):
        """신념 초기화"""
        self.band_belief = np.array([0.5, 0.5], dtype=np.float64)
        self.text_belief = np.array([0.5, 0.5], dtype=np.float64)
        self.update_count = 0
        self.band_confirmed = False
        self.text_confirmed = False
        self.confirmed_state = None
        self.confirmed_count = 0
    
    def get_belief_str(self):
        """현재 신념 상태 문자열 (하위 호환)"""
        # 3-상태 belief 계산
        band_prob = self.band_belief[1]
        no_band_prob = self.band_belief[0]
        tongil_prob = self.text_belief[0]
        melgong_prob = self.text_belief[1]
        
        ally = band_prob * tongil_prob
        enemy = band_prob * melgong_prob
        unknown = no_band_prob
        total = ally + enemy + unknown
        
        return f"ALLY:{ally/total:.0%} ENEMY:{enemy/total:.0%} UNKNOWN:{unknown/total:.0%}"
    
    def get_stage_str(self):
        """Stage별 신념 상태 문자열"""
        s1_status = "" if self.band_confirmed else "?"
        s2_status = "" if self.text_confirmed else "?"
        return (f"S1{s1_status}[NB:{self.band_belief[0]:.0%}/B:{self.band_belief[1]:.0%}] "
                f"S2{s2_status}[T:{self.text_belief[0]:.0%}/M:{self.text_belief[1]:.0%}]")


# band_cnn 패키지 경로 추가 (절대 경로 사용)
BAND_CNN_PATH = Path("/home/rokey/ros2_ws/src/band_cnn")
BAND_CNN_AVAILABLE = False

if BAND_CNN_PATH.exists():
    sys.path.insert(0, str(BAND_CNN_PATH))
    try:
        # CNN 방식 사용 (안정적)
        from band_classifier import BandClassifier
        BAND_CNN_AVAILABLE = True
    except ImportError as e:
        print(f"band_classifier import 실패: {e}")
        BAND_CNN_AVAILABLE = False


class FaceDetectionNode(Node):
    """얼굴 감지 ROS2 노드"""
    
    def __init__(self):
        super().__init__('face_detection_node')
        
        self.bridge = CvBridge()
        self.current_frame = None
        
        # 파라미터 선언
        self._declare_parameters()
        
        # 파라미터 로드
        params = self._load_parameters()
        
        # Detector 초기화 (로거 전달)
        self.detector = YoloDetector(
            model_path=params['model_path'],
            confidence_threshold=params['confidence_threshold'],
            use_gpu=params['use_gpu'],
            use_tensorrt=params['use_tensorrt'],
            use_fp16=params['use_fp16'],
            input_size=params['input_size'],
            use_preprocessing=params['use_preprocessing'],
            use_roi_tracking=params['use_roi_tracking'],
            logger=self.get_logger()
        )
        
        self.show_window = params['show_window']
        
        # FPS 측정
        self.frame_count = 0
        self.fps = 0.0
        self.last_fps_time = self.get_clock().now()
        
        # 신뢰도 히스토리 (안정화)
        self.confidence_history = []
        self.history_size = 5
        
        # ========================================
        # 시나리오 연동 설정
        # ========================================
        self.scenario_api_url = "http://localhost:8000/scenario"
        self.scenario_enabled = True  # 시나리오 연동 활성화
        self.scenario_triggered = False  # 이미 트리거 되었는지
        self.detection_stable_count = 0  # 안정적인 감지 횟수
        self.detection_threshold = 10  # N프레임 연속 감지 시 트리거 (약 0.3초)
        self.no_detection_count = 0  # 미감지 카운터
        self.reset_threshold = 90  # N프레임 미감지 시 리셋 (약 3초)
        self.tracking_active = False  # 추적 상태 (joint_tracking_node에서 수신)
        
        # ========================================
        # 피아식별 (IFF) CNN + 베이지안 필터 설정
        # ========================================
        self.iff_enabled = True  # 자동 피아식별 활성화
        self.iff_classifier = None
        self.last_iff_result = None
        self.cnn_frame_skip = 0  # CNN 프레임 스킵
        self.cnn_skip_interval = 2  # 2프레임마다 1번 CNN 수행
        
        # IFF 락 메커니즘 - 시나리오 진행 중 IFF 결과 변경 방지
        self.iff_locked = False  # True: IFF 결과 고정, 업데이트 안 함
        self.iff_locked_result = None  # 락된 IFF 결과 저장
        
        # 180도 회전 카메라 설정
        self.use_flipped = params.get('use_flipped_image', True)
        if self.use_flipped:
            self.image_topic = '/camera/flipped/color/image_raw'
        else:
            self.image_topic = '/camera/camera/color/image_raw'
        
        # 2단계 계층적 베이지안 필터 초기화
        self.iff_belief_filter = HierarchicalIFFFilter(
            band_threshold=0.70,     # Stage 1: 완장 확정 임계값 (70%)
            text_threshold=0.65,     # Stage 2: 텍스트 확정 임계값 (65%)
            decay=0.92,              # 시간 감쇠 (신념 유지력)
            learning_rate=0.35       # 새 관측 반영 비율
        )
        
        if BAND_CNN_AVAILABLE and self.iff_enabled:
            try:
                self.iff_classifier = BandClassifier()
                if self.iff_classifier.load_models():
                    self.get_logger().info(" 피아식별(IFF) CNN 로드 완료")
                else:
                    self.iff_classifier = None
                    self.get_logger().warn(" IFF CNN 로드 실패 - 수동 모드")
            except Exception as e:
                self.iff_classifier = None
                self.get_logger().warn(f" IFF CNN 초기화 실패: {e}")
        else:
            self.get_logger().info("ℹ IFF CNN 비활성화 - 수동 피아식별 모드")
        
        # 구독자
        self.image_sub = self.create_subscription(
            Image,
            self.image_topic,
            self.image_callback,
            10
        )
        
        # 추적 상태 구독 (joint_tracking_node가 발행)
        self.tracking_state_sub = self.create_subscription(
            String,
            '/joint_tracking/state',
            self.tracking_state_callback,
            10
        )
        
        # 발행자
        self.image_pub = self.create_publisher(Image, '/face_detection/image', 10)
        self.faces_pub = self.create_publisher(Float32MultiArray, '/face_detection/faces', 10)
        
        # 타이머 (30Hz)
        self.timer = self.create_timer(0.033, self.process_loop)
        
        self._print_startup_info()
    
    def _declare_parameters(self):
        """파라미터 선언"""
        self.declare_parameter('model_path', '')
        self.declare_parameter('confidence_threshold', 0.4)
        self.declare_parameter('show_window', False)
        self.declare_parameter('use_gpu', True)
        self.declare_parameter('use_tensorrt', True)
        self.declare_parameter('use_fp16', True)
        self.declare_parameter('input_size', 1280)
        self.declare_parameter('use_preprocessing', True)
        self.declare_parameter('use_roi_tracking', True)
        self.declare_parameter('use_flipped_image', True)  # 180도 회전 카메라
    
    def _load_parameters(self) -> dict:
        """파라미터 로드"""
        return {
            'model_path': self.get_parameter('model_path').value,
            'confidence_threshold': self.get_parameter('confidence_threshold').value,
            'show_window': self.get_parameter('show_window').value,
            'use_gpu': self.get_parameter('use_gpu').value,
            'use_tensorrt': self.get_parameter('use_tensorrt').value,
            'use_fp16': self.get_parameter('use_fp16').value,
            'input_size': self.get_parameter('input_size').value,
            'use_preprocessing': self.get_parameter('use_preprocessing').value,
            'use_roi_tracking': self.get_parameter('use_roi_tracking').value,
            'use_flipped_image': self.get_parameter('use_flipped_image').value,
        }
    
    def _print_startup_info(self):
        """시작 정보 출력"""
        stats = self.detector.get_stats()
        self.get_logger().info("=" * 60)
        self.get_logger().info(" Face Detection Node 시작!")
        self.get_logger().info(f"  Device: {stats['device'].upper()}")
        self.get_logger().info(f"  TensorRT: {'' if stats['tensorrt'] else ''}")
        self.get_logger().info(f"  FP16: {'' if stats['fp16'] else ''}")
        self.get_logger().info(f"  ROI Tracking: {'' if stats['roi_tracking'] else ''}")
        self.get_logger().info(f"  Scenario Trigger: {'' if self.scenario_enabled else ''}")
        self.get_logger().info(f"  Flipped Image: {'' if self.use_flipped else ''}")
        self.get_logger().info("  Topics:")
        self.get_logger().info(f"    Sub: {self.image_topic}")
        self.get_logger().info("    Sub: /joint_tracking/state")
        self.get_logger().info("    Pub: /face_detection/faces")
        self.get_logger().info("    Pub: /face_detection/image")
        self.get_logger().info("=" * 60)
    
    def tracking_state_callback(self, msg):
        """추적 상태 수신 콜백 (JSON 형식)"""
        import json
        try:
            state_data = json.loads(msg.data)
            state = state_data.get('state', 'IDLE').upper()
        except (json.JSONDecodeError, AttributeError):
            # JSON이 아니면 단순 문자열로 처리
            state = msg.data.upper()
        
        was_tracking = self.tracking_active
        self.tracking_active = (state == "TRACKING")
        
        if self.tracking_active != was_tracking:
            if self.tracking_active:
                self.get_logger().info(" 추적 모드 활성화 - 시나리오 트리거 대기")
                # 추적 시작 시 시나리오 상태 리셋
                self.scenario_triggered = False
                self.detection_stable_count = 0
                # IFF 락 해제 (새 추적 시작)
                if self.iff_locked:
                    self.iff_locked = False
                    self.iff_locked_result = None
                    self.get_logger().info(" IFF 락 해제 (새 추적 시작)")
            else:
                self.get_logger().info("⏸ 추적 모드 비활성화")
    
    def trigger_scenario(self):
        """시나리오 API 호출 (비동기) - 추적 중일 때만"""
        # 추적 모드가 아니면 트리거하지 않음
        if not self.tracking_active:
            return
        
        # 피아식별 CNN 결과 가져오기
        iff_result = self.last_iff_result
        
        def call_api():
            try:
                # 1단계: 감지 알림
                response = requests.post(
                    f"{self.scenario_api_url}/detect",
                    timeout=2.0
                )
                if response.status_code == 200:
                    self.get_logger().info(" 시나리오 트리거됨! /scenario/detect 호출 완료")
                else:
                    self.get_logger().warn(f"시나리오 API 응답 오류: {response.status_code}")
                    return
                
                # 2단계: 자동 피아식별 (CNN 결과가 있고 UNKNOWN이 아닌 경우)
                if iff_result and iff_result['iff'] != 'UNKNOWN':
                    import time
                    time.sleep(0.5)  # 팝업 표시 대기
                    
                    is_ally = (iff_result['iff'] == 'ALLY')
                    identify_response = requests.post(
                        f"{self.scenario_api_url}/identify",
                        json={"is_ally": is_ally},
                        timeout=2.0
                    )
                    if identify_response.status_code == 200:
                        iff_str = "아군" if is_ally else "적군"
                        self.get_logger().info(
                            f" 자동 피아식별: {iff_str} "
                            f"(완장: {iff_result['band']}, 신뢰도: {iff_result['conf']:.1%})"
                        )
                else:
                    self.get_logger().info(" 완장 미감지 - 수동 피아식별 대기")
                    
            except requests.exceptions.RequestException as e:
                self.get_logger().warn(f"시나리오 API 호출 실패 (서버 미실행?): {e}")
        
        self.scenario_triggered = True
        self.detection_stable_count = 0
        
        # 피아식별 결과 락 - 시나리오 진행 중 IFF 변경 방지
        if self.last_iff_result is not None:
            self.iff_locked = True
            self.iff_locked_result = self.last_iff_result.copy()
            self.get_logger().info(f" IFF 결과 락: {self.iff_locked_result['iff']} (Conf: {self.iff_locked_result['conf']:.0%})")
        
        self.get_logger().info(" [추적 중] 얼굴 감지 안정화 - 시나리오 트리거!")
        
        # 백그라운드 스레드에서 API 호출 (블로킹 방지)
        thread = threading.Thread(target=call_api, daemon=True)
        thread.start()
    
    def classify_iff(self, frame, detection):
        """피아식별 CNN + 2단계 계층적 베이지안 신념 업데이트"""
        if self.iff_classifier is None:
            return None
                # IFF 락 상태면 저장된 결과 반환 (시나리오 진행 중 변경 방지)
        if self.iff_locked and self.iff_locked_result is not None:
            return self.iff_locked_result
                # CNN 프레임 스킵
        self.cnn_frame_skip += 1
        if self.cnn_frame_skip < self.cnn_skip_interval:
            return self.last_iff_result
        self.cnn_frame_skip = 0
        
        try:
            # CNN에서 raw softmax 확률 가져오기 (디버그 정보 포함)
            debug_result = self.iff_classifier.get_iff_likelihood_debug(frame)
            
            if debug_result is None:
                return self.last_iff_result
            
            stage1 = debug_result['stage1']  # {no_band, has_band}
            stage2 = debug_result['stage2']  # {tongil, melgong}
            
            # 2단계 계층적 베이지안 업데이트
            belief_result = self.iff_belief_filter.update(stage1, stage2)
            
            # 디버그 로그: CNN raw → 필터 신념 상태
            self.get_logger().info(
                f" CNN[NB:{stage1['no_band']:.0%}/B:{stage1['has_band']:.0%}|T:{stage2['tongil']:.0%}/M:{stage2['melgong']:.0%}] → "
                f"{self.iff_belief_filter.get_stage_str()} → "
                f"{self.iff_belief_filter.get_belief_str()}"
            )
            
            # 결과 구성
            iff_state = belief_result['state']
            confidence = belief_result['confidence']
            is_confirmed = belief_result['is_confirmed']
            
            # 확정 여부에 따른 band 문자열
            if iff_state == 'ALLY':
                band = 'BAND-TONGIL'
            elif iff_state == 'ENEMY':
                band = 'BAND-MELGONG'
            else:
                band = 'NO_BAND'
            
            result = {
                'iff': iff_state,
                'band': band,
                'conf': confidence,
                'stable': is_confirmed,
                'belief': belief_result['belief'].tolist()
            }
            
            # 확정 시 로그
            if is_confirmed and belief_result['confirmed_count'] == 1:
                self.get_logger().info(
                    f" 베이지안 확정: IFF={iff_state}, Conf={confidence:.0%}"
                )
            
            self.last_iff_result = result
            return result
            
        except Exception as e:
            self.get_logger().warn(f"IFF CNN 오류: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def image_callback(self, msg):
        """이미지 수신 콜백"""
        try:
            self.current_frame = self.bridge.imgmsg_to_cv2(msg, "bgr8")
        except Exception as e:
            self.get_logger().error(f"이미지 변환 실패: {e}")
    
    def process_loop(self):
        """메인 처리 루프 (30Hz)"""
        if self.current_frame is None:
            return
        
        frame = self.current_frame.copy()
        
        # 감지 수행
        detection = self.detector.detect(frame)
        
        # 결과 처리
        faces_msg = Float32MultiArray()
        num_faces = 0
        
        if detection:
            num_faces = 1
            cx, cy = detection.center
            
            # 바운딩 박스 그리기
            color = (0, 255, 0) if self.detector.no_detection_count == 0 else (0, 255, 255)
            cv2.rectangle(frame, (detection.x1, detection.y1), 
                         (detection.x2, detection.y2), color, 2)
            cv2.circle(frame, (cx, cy), 5, (0, 0, 255), -1)
            
            # 신뢰도 평활화
            self.confidence_history.append(detection.confidence)
            if len(self.confidence_history) > self.history_size:
                self.confidence_history.pop(0)
            smoothed_conf = sum(self.confidence_history) / len(self.confidence_history)
            
            cv2.putText(frame, f"Conf: {smoothed_conf:.2f}",
                       (detection.x1, detection.y1 - 10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            
            # 메시지 데이터
            faces_msg.data = [float(cx), float(cy), 
                             float(detection.width), float(detection.height)]
            
            # ========================================
            # 피아식별 CNN 분류 (베이지안 신념 업데이트)
            # ========================================
            if self.iff_classifier is not None:
                iff_result = self.classify_iff(frame, detection)
                if iff_result:
                    is_stable = iff_result.get('stable', False)
                    iff_str = iff_result['iff']
                    band_str = iff_result['band']
                    conf = iff_result['conf']
                    
                    self.last_iff_result = iff_result
                    
                    # 화면에 IFF 결과 표시
                    iff_labels = {'ALLY': '아군', 'ENEMY': '적군', 'UNKNOWN': '??????'}
                    iff_colors = {
                        'ALLY': (0, 255, 0),      # 초록
                        'ENEMY': (0, 0, 255),     # 빨강
                        'UNKNOWN': (0, 165, 255)  # 주황
                    }
                    
                    label = iff_labels.get(iff_str, '??????')
                    color = iff_colors.get(iff_str, (128, 128, 128))
                    
                    # 확정 상태 표시 (베이지안)
                    stable_mark = "확정" if is_stable else "수렴중"
                    cv2.putText(frame, f"IFF: {label} ({conf:.0%}) {stable_mark}",
                               (detection.x1, detection.y2 + 25),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
            
            # ========================================
            # 시나리오 트리거 (연속 감지 + IFF 안정화 시)
            # ========================================
            self.no_detection_count = 0
            if self.scenario_enabled and not self.scenario_triggered:
                self.detection_stable_count += 1
                # 베이지안 IFF 확정 시 또는 얼굴만 30프레임 감지 시 트리거
                iff_ready = (self.last_iff_result and 
                            self.last_iff_result['iff'] != 'UNKNOWN' and 
                            self.last_iff_result.get('stable', False))
                face_only_ready = self.detection_stable_count >= self.detection_threshold * 3
                
                if iff_ready or face_only_ready:
                    self.trigger_scenario()
        else:
            # 미감지 시
            self.detection_stable_count = 0
            self.no_detection_count += 1
            
            # 오랜 미감지 시 베이지안 필터 + 시나리오 리셋
            if self.no_detection_count >= self.reset_threshold:
                if self.iff_belief_filter:
                    self.iff_belief_filter.reset()
                if self.scenario_triggered:
                    self.scenario_triggered = False
                    # IFF 락 해제
                    if self.iff_locked:
                        self.iff_locked = False
                        self.iff_locked_result = None
                        self.get_logger().info(" IFF 락 해제")
                    self.get_logger().info(" 얼굴 미감지 - 베이지안 필터 및 시나리오 리셋")
        
        # FPS 계산
        self.frame_count += 1
        current_time = self.get_clock().now()
        time_diff = (current_time - self.last_fps_time).nanoseconds / 1e9
        
        if time_diff >= 1.0:
            self.fps = self.frame_count / time_diff
            self.frame_count = 0
            self.last_fps_time = current_time
        
        # 정보 표시
        cv2.putText(frame, f"Faces: {num_faces}", (10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 0), 2)
        cv2.putText(frame, f"FPS: {self.fps:.1f}", (10, 70),
                   cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 0), 2)
        cv2.putText(frame, f"Inference: {self.detector.avg_inference_time:.1f}ms", (10, 110),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 0, 0), 2)
        
        # 최적화 상태
        stats = self.detector.get_stats()
        opt_list = []
        if stats['tensorrt']:
            opt_list.append("TRT")
        if stats['fp16']:
            opt_list.append("FP16")
        if stats['roi_tracking']:
            opt_list.append("ROI")
        cv2.putText(frame, f"YOLOv8 [{', '.join(opt_list)}]", (10, 150),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        
        # 발행
        try:
            img_msg = self.bridge.cv2_to_imgmsg(frame, "bgr8")
            self.image_pub.publish(img_msg)
        except Exception as e:
            self.get_logger().error(f"이미지 발행 실패: {e}")
        
        self.faces_pub.publish(faces_msg)
        
        # OpenCV 창
        if self.show_window:
            cv2.imshow("Face Detection", frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q') or key == 27:
                self.get_logger().info("종료합니다.")
                cv2.destroyAllWindows()
                rclpy.shutdown()


def main(args=None):
    rclpy.init(args=args)
    node = FaceDetectionNode()
    
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        cv2.destroyAllWindows()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
