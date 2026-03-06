#!/usr/bin/env python3
"""
Voice Authentication Node for CoBotSentry
==========================================

ROS2 노드로 변환된 암구호 인증 시스템.

기능:
- Service: /request_auth - 암구호 인증 요청 (동기)
- Subscriber: /passphrase - 웹에서 암구호 설정 수신
- Publisher: /auth_status - 인증 상태 브로드캐스트

사용:
    ros2 run voice_auth voice_auth_node
    
서비스 호출:
    ros2 service call /request_auth voice_auth_msgs/srv/RequestAuth "{timeout_sec: 5.0}"
    
암구호 설정:
    ros2 topic pub /passphrase std_msgs/msg/String "data: '까마귀'" --once
"""

import rclpy
from rclpy.node import Node
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor

from std_msgs.msg import String
from voice_auth_msgs.msg import AuthStatus
from voice_auth_msgs.srv import RequestAuth

import pyaudio
import speech_recognition as sr
from threading import Lock
from builtin_interfaces.msg import Time


class MicConfig:
    """마이크 설정"""
    chunk: int = 12000
    rate: int = 48000
    channels: int = 1
    record_seconds: float = 3.5
    fmt: int = pyaudio.paInt16
    device_index: int = 10  # C270 HD WEBCAM
    buffer_size: int = 24000


class MicController:
    """마이크 녹음 컨트롤러"""
    
    def __init__(self, config: MicConfig = None):
        self.config = config or MicConfig()
        self.audio = None
        self.stream = None

    def open_stream(self):
        """PyAudio 인스턴스 생성 및 스트림 열기"""
        self.audio = pyaudio.PyAudio()
        
        # USB 웹캠 마이크 지원
        device_index = self.config.device_index
        channels = self.config.channels
        
        if device_index is not None:
            info = self.audio.get_device_info_by_index(device_index)
            channels = min(self.config.channels, int(info['maxInputChannels']))
        
        self.stream = self.audio.open(
            format=self.config.fmt,
            channels=channels,
            rate=self.config.rate,
            input=True,
            input_device_index=device_index,
            frames_per_buffer=self.config.chunk,
        )

    def close_stream(self):
        """스트림 및 PyAudio 종료"""
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        if self.audio:
            self.audio.terminate()
            self.audio = None

    def record_raw(self, record_seconds: float = None) -> bytes:
        """
        마이크에서 녹음하여 순수 PCM 데이터 반환
        
        Args:
            record_seconds: 녹음 시간 (초). None이면 기본값 사용.
            
        Returns:
            PCM 바이트 데이터
        """
        self.open_stream()
        
        duration = record_seconds or self.config.record_seconds
        frames = []
        num_chunks = int(self.config.rate / self.config.chunk * duration)

        for _ in range(num_chunks):
            data = self.stream.read(self.config.chunk, exception_on_overflow=False)
            frames.append(data)

        self.close_stream()
        return b"".join(frames)


# ElevenLabs TTS 엔진 사용
from voice_auth.tts_engine import TTSEngine


class VoiceAuthNode(Node):
    """암구호 인증 ROS2 노드"""
    
    # 상태 상수 (AuthStatus.msg와 동기화)
    STATUS_IDLE = 0
    STATUS_LISTENING = 1
    STATUS_PROCESSING = 2
    STATUS_SUCCESS = 3
    STATUS_FAILED = 4
    STATUS_ERROR = 5
    
    def __init__(self):
        super().__init__('voice_auth_node')
        
        # 콜백 그룹 (Service가 블로킹되어도 다른 콜백 처리 가능)
        self.callback_group = ReentrantCallbackGroup()
        
        # 파라미터 선언 (질문-대답 암구호 체계)
        self.declare_parameter('question_passphrase', '까마귀')  # 초병이 말하는 질문
        self.declare_parameter('answer_passphrase', '백두산')    # 접근자가 대답해야 하는 정답
        self.declare_parameter('default_timeout_sec', 3.5)
        self.declare_parameter('warning_message', '정지! 손들어!')
        self.declare_parameter('enable_tts', True)
        self.declare_parameter('mic_device_index', 10)  # C270 HD WEBCAM
        
        # 현재 암구호 (웹에서 동적 변경 가능)
        self._question = self.get_parameter('question_passphrase').value
        self._answer = self.get_parameter('answer_passphrase').value
        self._passphrase_lock = Lock()
        
        # ===== Publishers =====
        self.status_pub = self.create_publisher(
            AuthStatus,
            '/auth_status',
            10
        )
        
        # ===== Subscribers =====
        # 질문 암구호 (초병이 말함)
        self.question_sub = self.create_subscription(
            String,
            '/passphrase/question',
            self.question_callback,
            10,
            callback_group=self.callback_group
        )
        # 정답 암구호 (접근자가 대답해야 함)
        self.answer_sub = self.create_subscription(
            String,
            '/passphrase/answer',
            self.answer_callback,
            10,
            callback_group=self.callback_group
        )
        
        # ===== Services =====
        self.auth_service = self.create_service(
            RequestAuth,
            '/request_auth',
            self.handle_auth_request,
            callback_group=self.callback_group
        )
        
        # 마이크 컨트롤러 (USB 웹캠 마이크 사용)
        mic_config = MicConfig()
        mic_config.device_index = self.get_parameter('mic_device_index').value
        self.mic = MicController(mic_config)
        self.recognizer = sr.Recognizer()
        
        # 상태 발행 타이머 (1Hz)
        self._current_status = self.STATUS_IDLE
        self._recognized_text = ""
        self.create_timer(1.0, self.publish_status)
        
        self.get_logger().info(f'Voice Auth Node 시작됨')
        self.get_logger().info(f'  질문 암구호: {self._question}')
        self.get_logger().info(f'  정답 암구호: {self._answer}')
        self.get_logger().info(f'  마이크 장치: {mic_config.device_index}')
        self.get_logger().info(f'  Service: /request_auth')
        self.get_logger().info(f'  Topic Sub: /passphrase/question, /passphrase/answer')
        self.get_logger().info(f'  Topic Pub: /auth_status')
    
    @property
    def question(self) -> str:
        """현재 질문 암구호 (thread-safe)"""
        with self._passphrase_lock:
            return self._question
    
    @question.setter
    def question(self, value: str):
        with self._passphrase_lock:
            self._question = value
    
    @property
    def answer(self) -> str:
        """현재 정답 암구호 (thread-safe)"""
        with self._passphrase_lock:
            return self._answer
    
    @answer.setter
    def answer(self, value: str):
        with self._passphrase_lock:
            self._answer = value
    
    def question_callback(self, msg: String):
        """/passphrase/question 토픽 콜백 - 질문 암구호 변경"""
        old = self.question
        self.question = msg.data.strip()
        self.get_logger().info(f'질문 암구호 변경: "{old}" → "{self.question}"')
    
    def answer_callback(self, msg: String):
        """/passphrase/answer 토픽 콜백 - 정답 암구호 변경"""
        old = self.answer
        self.answer = msg.data.strip()
        self.get_logger().info(f'정답 암구호 변경: "{old}" → "{self.answer}"')
    
    def publish_status(self):
        """현재 인증 상태를 브로드캐스트"""
        msg = AuthStatus()
        msg.status = self._current_status
        msg.recognized_text = self._recognized_text
        msg.expected_passphrase = f"{self.question}→{self.answer}"  # 질문→정답 형식
        msg.stamp = self.get_clock().now().to_msg()
        self.status_pub.publish(msg)
    
    def handle_auth_request(
        self, 
        request: RequestAuth.Request, 
        response: RequestAuth.Response
    ) -> RequestAuth.Response:
        """
        /request_auth 서비스 핸들러
        
        Flow:
        1. TTS로 경고 메시지 출력
        2. 마이크 녹음 (지정된 시간)
        3. Google STT로 텍스트 변환
        4. 암구호와 비교하여 결과 반환
        """
        self.get_logger().info('암구호 인증 요청 수신')
        
        # 타임아웃 설정
        timeout = request.timeout_sec if request.timeout_sec > 0 else \
                  self.get_parameter('default_timeout_sec').value
        
        try:
            # 1. TTS 경고 + 질문 암구호
            if self.get_parameter('enable_tts').value:
                self._current_status = self.STATUS_IDLE
                warning_msg = self.get_parameter('warning_message').value
                self.get_logger().info(f'TTS 출력: "{warning_msg}"')
                TTSEngine.get_instance().speak(warning_msg)
                
                # 질문 암구호 말하기
                question_msg = f"암구호! {self.question}!"
                self.get_logger().info(f'TTS 출력: "{question_msg}"')
                TTSEngine.get_instance().speak(question_msg)
            
            # 2. 녹음 시작
            self._current_status = self.STATUS_LISTENING
            self.publish_status()  # 즉시 상태 발행
            self.get_logger().info(f'{timeout}초 동안 녹음 시작...')
            
            pcm_data = self.mic.record_raw(record_seconds=timeout)
            
            # 3. STT 처리
            self._current_status = self.STATUS_PROCESSING
            self.publish_status()
            self.get_logger().info('STT 처리 중...')
            
            audio_data = sr.AudioData(
                pcm_data, 
                self.mic.config.rate, 
                2  # 16bit = 2bytes
            )
            
            try:
                recognized = self.recognizer.recognize_google(
                    audio_data, 
                    language="ko-KR"
                )
                self.get_logger().info(f'인식된 텍스트: "{recognized}"')
            except sr.UnknownValueError:
                self._current_status = self.STATUS_FAILED
                self._recognized_text = ""
                response.success = False
                response.recognized_text = ""
                response.message = "음성을 인식하지 못했습니다"
                self.get_logger().warn(response.message)
                return response
            except sr.RequestError as e:
                self._current_status = self.STATUS_ERROR
                self._recognized_text = ""
                response.success = False
                response.recognized_text = ""
                response.message = f"STT 서비스 오류: {e}"
                self.get_logger().error(response.message)
                return response
            
            # 4. 암구호 비교
            self._recognized_text = recognized
            is_match = self._check_passphrase(recognized)
            
            if is_match:
                self._current_status = self.STATUS_SUCCESS
                response.success = True
                response.message = "암구호 인증 성공"
                self.get_logger().info(f' {response.message}')
            else:
                self._current_status = self.STATUS_FAILED
                response.success = False
                response.message = f"암구호 불일치 (인식: {recognized})"
                self.get_logger().warn(f' {response.message}')
            
            response.recognized_text = recognized
            return response
            
        except Exception as e:
            self._current_status = self.STATUS_ERROR
            response.success = False
            response.recognized_text = ""
            response.message = f"인증 처리 중 오류: {e}"
            self.get_logger().error(response.message)
            return response
        
        finally:
            # 일정 시간 후 IDLE로 복귀
            self.create_timer(3.0, self._reset_to_idle, callback_group=self.callback_group)
    
    def _reset_to_idle(self):
        """상태를 IDLE로 리셋"""
        self._current_status = self.STATUS_IDLE
        # 타이머는 한 번만 실행되어야 하므로 destroy
        # (ROS2에서는 one-shot 타이머가 없어서 이렇게 처리)
    
    def _check_passphrase(self, recognized_text: str) -> bool:
        """
        인식된 텍스트가 정답 암구호를 포함하는지 검사
        
        질문-대답 체계:
            초병: "까마귀!" (question)
            접근자: "백두산!" (answer) ← 이것과 비교
        
        Args:
            recognized_text: STT로 인식된 텍스트
            
        Returns:
            정답 암구호 포함 여부
        """
        # 공백 제거 후 비교 (띄어쓰기 차이 무시)
        normalized_text = recognized_text.replace(" ", "").strip()
        normalized_answer = self.answer.replace(" ", "").strip()
        
        return normalized_answer in normalized_text


def main(args=None):
    """ROS2 entry point with robust error handling"""
    import time
    
    max_retries = 5
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            rclpy.init(args=args)
            
            node = VoiceAuthNode()
            
            # Service가 블로킹되어도 다른 콜백이 처리되도록 MultiThreadedExecutor 사용
            executor = MultiThreadedExecutor()
            executor.add_node(node)
            
            try:
                executor.spin()
            except KeyboardInterrupt:
                print("Voice Auth Node: KeyboardInterrupt received, shutting down...")
                break
            except Exception as e:
                print(f"Voice Auth Node: Executor error - {e}")
                retry_count += 1
                if retry_count < max_retries:
                    print(f"Voice Auth Node: Retrying ({retry_count}/{max_retries})...")
                    time.sleep(2)
            finally:
                try:
                    node.destroy_node()
                except:
                    pass
                try:
                    if rclpy.ok():
                        rclpy.shutdown()
                except:
                    pass
                    
        except Exception as e:
            print(f"Voice Auth Node: Init error - {e}")
            retry_count += 1
            if retry_count < max_retries:
                print(f"Voice Auth Node: Retrying ({retry_count}/{max_retries})...")
                time.sleep(2)
            try:
                rclpy.shutdown()
            except:
                pass
    
    if retry_count >= max_retries:
        print(f"Voice Auth Node: Max retries ({max_retries}) exceeded, exiting.")


if __name__ == '__main__':
    main()
