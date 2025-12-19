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
        # 피아식별 (IFF) CNN 설정
        # ========================================
        self.iff_enabled = True  # 자동 피아식별 활성화
        self.iff_classifier = None
        self.last_iff_result = None
        self.iff_confidence_threshold = 0.6  # CNN 신뢰도 임계값 (60%)
        self.iff_stable_count = 0  # IFF 결과 안정화 카운터
        self.iff_stable_threshold = 5  # 안정화 프레임 수
        self.iff_history = []  # IFF 결과 히스토리
        self.iff_history_size = 15  # 히스토리 크기
        self.cnn_frame_skip = 0  # CNN 프레임 스킵
        self.cnn_skip_interval = 2  # 2프레임마다 1번 CNN 수행
        
        if BAND_CNN_AVAILABLE and self.iff_enabled:
            try:
                self.iff_classifier = BandClassifier()
                if self.iff_classifier.load_models():
                    self.get_logger().info("✅ 피아식별(IFF) CNN 로드 완료")
                else:
                    self.iff_classifier = None
                    self.get_logger().warn("⚠️ IFF CNN 로드 실패 - 수동 모드")
            except Exception as e:
                self.iff_classifier = None
                self.get_logger().warn(f"⚠️ IFF CNN 초기화 실패: {e}")
        else:
            self.get_logger().info("ℹ️ IFF CNN 비활성화 - 수동 피아식별 모드")
        
        # 구독자
        self.image_sub = self.create_subscription(
            Image,
            '/camera/camera/color/image_raw',
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
        }
    
    def _print_startup_info(self):
        """시작 정보 출력"""
        stats = self.detector.get_stats()
        self.get_logger().info("=" * 60)
        self.get_logger().info("🎥 Face Detection Node 시작!")
        self.get_logger().info(f"  Device: {stats['device'].upper()}")
        self.get_logger().info(f"  TensorRT: {'✅' if stats['tensorrt'] else '❌'}")
        self.get_logger().info(f"  FP16: {'✅' if stats['fp16'] else '❌'}")
        self.get_logger().info(f"  ROI Tracking: {'✅' if stats['roi_tracking'] else '❌'}")
        self.get_logger().info(f"  Scenario Trigger: {'✅' if self.scenario_enabled else '❌'}")
        self.get_logger().info("  Topics:")
        self.get_logger().info("    Sub: /camera/camera/color/image_raw")
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
                self.get_logger().info("🎯 추적 모드 활성화 - 시나리오 트리거 대기")
                # 추적 시작 시 시나리오 상태 리셋
                self.scenario_triggered = False
                self.detection_stable_count = 0
            else:
                self.get_logger().info("⏸️ 추적 모드 비활성화")
    
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
                    self.get_logger().info("🚨 시나리오 트리거됨! /scenario/detect 호출 완료")
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
                            f"🎖️ 자동 피아식별: {iff_str} "
                            f"(완장: {iff_result['band']}, 신뢰도: {iff_result['conf']:.1%})"
                        )
                else:
                    self.get_logger().info("👁️ 완장 미감지 - 수동 피아식별 대기")
                    
            except requests.exceptions.RequestException as e:
                self.get_logger().warn(f"시나리오 API 호출 실패 (서버 미실행?): {e}")
        
        self.scenario_triggered = True
        self.detection_stable_count = 0
        self.get_logger().info("🎯 [추적 중] 얼굴 감지 안정화 - 시나리오 트리거!")
        
        # 백그라운드 스레드에서 API 호출 (블로킹 방지)
        thread = threading.Thread(target=call_api, daemon=True)
        thread.start()
    
    def classify_iff(self, frame, detection):
        """피아식별 CNN - 전체 프레임 사용 (학습 데이터와 일치)"""
        if self.iff_classifier is None:
            return None
        
        # CNN 프레임 스킵
        self.cnn_frame_skip += 1
        if self.cnn_frame_skip < self.cnn_skip_interval:
            return self.last_iff_result
        self.cnn_frame_skip = 0
        
        try:
            # 전체 프레임으로 CNN 분류 (학습 데이터가 전체 프레임이므로)
            iff, band, conf = self.iff_classifier.classify_iff(frame)
            
            # 디버그 로그
            self.get_logger().info(f"🔍 CNN 결과: IFF={iff}, Band={band}, Conf={conf:.1%}")
            
            result = {'iff': iff, 'band': band, 'conf': conf}
            self.last_iff_result = result
            return result
            
        except Exception as e:
            self.get_logger().warn(f"IFF CNN 오류: {e}")
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
        
        # ROI 영역 표시 (디버그용 - 보라색)
        roi = self.detector._get_roi(frame.shape)
        if roi is not None:
            cv2.rectangle(frame, (roi[0], roi[1]), (roi[2], roi[3]), (255, 0, 255), 1)
        
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
            # 피아식별 CNN 분류 (투표 없이 원본 결과 직접 표시)
            # ========================================
            if self.iff_classifier is not None:
                iff_result = self.classify_iff(frame, detection)
                if iff_result:
                    # 디버그: CNN 원본 결과 로그
                    self.get_logger().info(
                        f"🎯 CNN 결과: IFF={iff_result['iff']}, "
                        f"Band={iff_result['band']}, Conf={iff_result['conf']:.1%}"
                    )
                    
                    self.last_iff_result = iff_result
                    
                    # 화면에 IFF 결과 표시 (한국어)
                    iff_labels = {'ALLY': '아군', 'ENEMY': '적군', 'UNKNOWN': '미상'}
                    iff_color = {'ALLY': (0, 255, 0), 'ENEMY': (0, 0, 255), 'UNKNOWN': (128, 128, 128)}
                    label = iff_labels.get(iff_result['iff'], '미상')
                    color = iff_color.get(iff_result['iff'], (255, 255, 255))
                    
                    # 완장 분류 결과도 함께 표시
                    band_text = iff_result['band']
                    cv2.putText(frame, f"IFF: {label} ({iff_result['conf']:.0%})",
                               (detection.x1, detection.y2 + 25),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
                    cv2.putText(frame, f"Band: {band_text}",
                               (detection.x1, detection.y2 + 50),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
            
            # ========================================
            # 시나리오 트리거 (연속 감지 + IFF 안정화 시)
            # ========================================
            self.no_detection_count = 0
            if self.scenario_enabled and not self.scenario_triggered:
                self.detection_stable_count += 1
                # IFF 결과가 안정화되었거나 (10프레임), 얼굴만 30프레임 감지 시 트리거
                iff_ready = (self.last_iff_result and 
                            self.last_iff_result['iff'] != 'UNKNOWN' and 
                            self.iff_stable_count >= self.iff_stable_threshold)
                face_only_ready = self.detection_stable_count >= self.detection_threshold * 3
                
                if iff_ready or face_only_ready:
                    self.trigger_scenario()
        else:
            # 미감지 시
            self.detection_stable_count = 0
            self.no_detection_count += 1
            
            # 오랜 미감지 시 시나리오 리셋 가능 상태로
            if self.scenario_triggered and self.no_detection_count >= self.reset_threshold:
                self.scenario_triggered = False
                self.get_logger().info("👁️ 얼굴 미감지 - 시나리오 재트리거 가능")
        
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
