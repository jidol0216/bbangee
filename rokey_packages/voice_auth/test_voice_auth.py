#!/usr/bin/env python3
"""
Voice Auth 독립 테스트 스크립트 (질문-대답 암구호 체계)
====================================================

ROS2 없이 터미널에서 암구호 인증 시스템을 테스트합니다.

실제 군대 암구호 체계:
    초병: "까마귀!" (질문)
    접근자: "백두산!" (정답)

사용법:
    python3 test_voice_auth.py
    python3 test_voice_auth.py --question 까마귀 --answer 백두산
    python3 test_voice_auth.py -q 통일 -a 대한민국 -d 10
"""

import argparse
import pyaudio
import speech_recognition as sr
import os
import sys
from threading import Lock

# TTS 엔진 경로 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'voice_auth'))
from tts_engine import TTSEngine


class MicConfig:
    """마이크 설정"""
    chunk: int = 12000
    rate: int = 48000
    channels: int = 1
    record_seconds: int = 5
    fmt: int = pyaudio.paInt16
    device_index: int = None  # None이면 기본 장치


class MicController:
    """마이크 녹음 컨트롤러"""
    
    def __init__(self, config: MicConfig = None):
        self.config = config or MicConfig()
        self.audio = None
        self.stream = None

    def open_stream(self):
        """PyAudio 인스턴스 생성 및 스트림 열기"""
        self.audio = pyaudio.PyAudio()
        
        # 장치별 설정 조정
        device_index = self.config.device_index
        rate = self.config.rate
        channels = self.config.channels
        
        if device_index is not None:
            # 지정된 장치의 정보 확인
            info = self.audio.get_device_info_by_index(device_index)
            # 장치가 지원하는 채널 수로 조정
            channels = min(self.config.channels, int(info['maxInputChannels']))
            print(f"  마이크: {info['name']} (장치 {device_index})")
        
        self.stream = self.audio.open(
            format=self.config.fmt,
            channels=channels,
            rate=rate,
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
        """마이크에서 녹음하여 순수 PCM 데이터 반환"""
        self.open_stream()
        
        duration = record_seconds or self.config.record_seconds
        frames = []
        num_chunks = int(self.config.rate / self.config.chunk * duration)

        print(f" {duration}초 동안 녹음 중...")
        for i in range(num_chunks):
            data = self.stream.read(self.config.chunk, exception_on_overflow=False)
            frames.append(data)
            # 진행 표시
            progress = (i + 1) / num_chunks * 100
            print(f"\r   진행: {progress:.0f}%", end="", flush=True)
        
        print()  # 줄바꿈
        self.close_stream()
        return b"".join(frames)


def tts_say(text: str):
    """ElevenLabs TTS로 텍스트 출력"""
    TTSEngine.get_instance().speak(text)


def list_audio_devices():
    """사용 가능한 마이크 장치 목록 출력"""
    p = pyaudio.PyAudio()
    print("\n=== 사용 가능한 마이크 장치 ===")
    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        if info['maxInputChannels'] > 0:
            print(f"  [{i}] {info['name']}")
    p.terminate()
    print()


def check_passphrase(recognized_text: str, answer: str) -> bool:
    """
    인식된 텍스트가 정답 암구호를 포함하는지 검사
    """
    normalized_text = recognized_text.replace(" ", "").strip()
    normalized_answer = answer.replace(" ", "").strip()
    return normalized_answer in normalized_text


def run_auth_test(question: str, answer: str, timeout: float, device_index: int = None):
    """
    암구호 인증 테스트 실행 (질문-대답 체계)
    
    1. 설정된 암구호 표시
    2. TTS로 질문 암구호 출력 ("까마귀!")
    3. 마이크 녹음
    4. STT로 텍스트 변환
    5. 정답 암구호와 일치 여부 판정
    """
    print("=" * 60)
    print("        CoBotSentry 암구호 인증 테스트")
    print("        (질문-대답 체계)")
    print("=" * 60)
    print()
    print(f" 질문 암구호: \"{question}\"")
    print(f" 정답 암구호: \"{answer}\"")
    print(f"⏱  녹음 시간: {timeout}초")
    print()
    print("-" * 60)
    
    # 마이크 설정
    config = MicConfig()
    config.device_index = device_index
    
    # 1. TTS 경고 메시지
    warning_message = "정지! 손들어!"
    tts_say(warning_message)
    
    # 2. TTS 질문 암구호
    print()
    tts_say(f"암구호! {question}!")
    
    print()
    print("-" * 60)
    
    # 3. 마이크 녹음
    mic = MicController(config)
    pcm_data = mic.record_raw(record_seconds=timeout)
    
    print("-" * 60)
    print()
    
    # 4. STT 처리
    print(" STT 처리 중...")
    recognizer = sr.Recognizer()
    audio_data = sr.AudioData(pcm_data, mic.config.rate, 2)  # 16bit = 2bytes
    
    try:
        recognized = recognizer.recognize_google(audio_data, language="ko-KR")
        print(f" 인식된 텍스트: \"{recognized}\"")
    except sr.UnknownValueError:
        print(" 음성을 인식하지 못했습니다.")
        print()
        print("=" * 60)
        print("        결과: 인증 실패 (음성 인식 불가)")
        print("=" * 60)
        tts_say("암구호 불일치. 정지하십시오!")
        return False
    except sr.RequestError as e:
        print(f" STT 서비스 오류: {e}")
        print()
        print("=" * 60)
        print("        결과: 인증 실패 (서비스 오류)")
        print("=" * 60)
        return False
    
    print()
    print("-" * 60)
    
    # 5. 암구호 비교 (정답과 비교)
    is_match = check_passphrase(recognized, answer)
    
    print()
    print("=" * 60)
    if is_match:
        print(f"    결과: 일치합니다!")
        print(f"    기대 정답: \"{answer}\"")
        print(f"    인식된 답: \"{recognized}\"")
        print()
        print("   >>> 암구호 인증 성공 <<<")
        tts_say("암구호 일치. 통과하십시오.")
    else:
        print(f"    결과: 일치하지 않습니다!")
        print(f"    기대 정답: \"{answer}\"")
        print(f"    인식된 답: \"{recognized}\"")
        print()
        print("   >>> 암구호 인증 실패 <<<")
        tts_say("암구호 불일치. 정지하십시오!")
    print("=" * 60)
    print()
    
    return is_match


def main():
    parser = argparse.ArgumentParser(
        description="CoBotSentry 암구호 인증 테스트 (질문-대답 체계)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
암구호 체계:
    초병이 질문 암구호를 말하면, 접근자는 정답 암구호로 대답해야 합니다.
    예) 초병: "까마귀!" → 접근자: "백두산!"

예시:
    python3 test_voice_auth.py                                    # 기본: 까마귀→백두산
    python3 test_voice_auth.py --question 통일 --answer 대한민국  # 커스텀 암구호
    python3 test_voice_auth.py -q 까마귀 -a 백두산 -d 10          # USB 웹캠 마이크
    python3 test_voice_auth.py --list-devices                     # 마이크 목록 확인
        """
    )
    
    parser.add_argument(
        '-q', '--question',
        type=str,
        default='까마귀',
        help='질문 암구호 (초병이 말함, 기본값: 까마귀)'
    )
    
    parser.add_argument(
        '-a', '--answer',
        type=str,
        default='백두산',
        help='정답 암구호 (접근자가 대답해야 함, 기본값: 백두산)'
    )
    
    parser.add_argument(
        '-t', '--timeout',
        type=float,
        default=3.5,
        help='녹음 시간 (초, 기본값: 3.5)'
    )
    
    parser.add_argument(
        '-d', '--device',
        type=int,
        default=10,  # C270 HD WEBCAM
        help='마이크 장치 인덱스 (기본값: 10=USB 웹캠)'
    )
    
    parser.add_argument(
        '--list-devices',
        action='store_true',
        help='사용 가능한 마이크 장치 목록 출력'
    )
    
    args = parser.parse_args()
    
    # 장치 목록만 출력
    if args.list_devices:
        list_audio_devices()
        return 0
    
    try:
        result = run_auth_test(
            question=args.question,
            answer=args.answer,
            timeout=args.timeout,
            device_index=args.device
        )
        return 0 if result else 1
    except KeyboardInterrupt:
        print("\n\n테스트가 취소되었습니다.")
        return 130


if __name__ == "__main__":
    exit(main())
