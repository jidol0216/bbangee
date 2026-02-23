"""
오디오 서비스
=============
마이크 녹음, STT, 경고음 생성

Before: voice.py 에 record_audio / speech_to_text 직접 정의,
        scenario.py 에 _play_alert_buzzer 에서 numpy WAV 합성
After : 이 모듈에서 통합 관리
"""

import threading
from app.services.config import MIC_DEVICE_INDEX, MIC_SAMPLE_RATE


# ============================================
# 마이크 녹음
# ============================================

def record_audio(duration: float = 3.5,
                 device_index: int | None = None) -> tuple[bytes, int]:
    """
    마이크 녹음

    Returns:
        (raw_audio_bytes, sample_rate)
    """
    import pyaudio
    import traceback

    if device_index is None:
        device_index = MIC_DEVICE_INDEX

    CHUNK = 4096
    CHANNELS = 1
    FORMAT = pyaudio.paInt16
    RATE = MIC_SAMPLE_RATE

    print(f"🎤 [record] 시작 duration={duration}, device={device_index}", flush=True)

    p = pyaudio.PyAudio()
    try:
        try:
            info = p.get_device_info_by_index(device_index)
            print(f"🎤 마이크: [{device_index}] {info['name']}", flush=True)
        except Exception as e:
            print(f"⚠️ 장치 {device_index} 정보 조회 실패: {e}", flush=True)
            traceback.print_exc()

        stream = p.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=RATE,
            input=True,
            input_device_index=device_index,
            frames_per_buffer=CHUNK,
        )

        frames: list[bytes] = []
        num_chunks = int(RATE / CHUNK * duration)
        for _ in range(num_chunks):
            data = stream.read(CHUNK, exception_on_overflow=False)
            frames.append(data)

        stream.stop_stream()
        stream.close()

        audio_bytes = b"".join(frames)
        print(f"🎤 [record] 완료! bytes={len(audio_bytes)}", flush=True)
        return audio_bytes, RATE

    except Exception as e:
        print(f"❌ [record] 에러: {e}", flush=True)
        traceback.print_exc()
        return b"", RATE
    finally:
        p.terminate()


# ============================================
# STT (Google Speech Recognition)
# ============================================

def speech_to_text(audio_data: bytes, rate: int | None = None) -> str:
    """Google STT 로 음성→텍스트 변환"""
    import speech_recognition as sr

    if rate is None:
        rate = MIC_SAMPLE_RATE

    recognizer = sr.Recognizer()
    audio = sr.AudioData(audio_data, rate, 2)  # 16bit = 2 bytes

    try:
        return recognizer.recognize_google(audio, language="ko-KR")
    except sr.UnknownValueError:
        return ""
    except sr.RequestError as e:
        print(f"STT 서비스 오류: {e}")
        return ""


def check_passphrase(recognized: str, answer: str) -> bool:
    """암구호 일치 여부 확인 (공백 무시)"""
    return answer.replace(" ", "").strip() in recognized.replace(" ", "").strip()


# ============================================
# 경고음 / 부저음
# ============================================

def play_alert_buzzer(alert_type: str = "warning") -> None:
    """
    경고 부저음 재생 (별도 스레드)

    alert_type:
        "warning"  — 짧은 비프 3회
        "critical" — 8초 사이렌
    """
    thread = threading.Thread(target=_generate_and_play_buzzer, args=(alert_type,))
    thread.start()


def _generate_and_play_buzzer(alert_type: str) -> None:
    try:
        import numpy as np
        import subprocess
        import tempfile
        import os
        import wave

        sample_rate = 44100
        volume = 0.25

        if alert_type == "warning":
            duration = 0.3
            freq = 880
            t = np.linspace(0, duration, int(sample_rate * duration), False)
            beep = np.sin(2 * np.pi * freq * t) * volume
            silence = np.zeros(int(sample_rate * 0.15))
            audio = np.concatenate([beep, silence, beep, silence, beep])

        elif alert_type == "critical":
            duration = 8.0
            t = np.linspace(0, duration, int(sample_rate * duration), False)
            freq_low, freq_high = 600, 1000
            freq_mod = freq_low + (freq_high - freq_low) * (
                0.5 + 0.5 * np.sin(2 * np.pi * 4 * t)
            )
            phase = np.cumsum(2 * np.pi * freq_mod / sample_rate)
            audio = np.sin(phase) * volume
            fade_len = int(sample_rate * 1.0)
            audio[-fade_len:] *= np.linspace(1, 0, fade_len)
        else:
            return

        audio = (audio * 32767).astype(np.int16)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            temp_path = f.name
            with wave.open(temp_path, "w") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(sample_rate)
                wav_file.writeframes(audio.tobytes())

        subprocess.run(["aplay", "-q", temp_path], check=True)
        os.unlink(temp_path)

    except Exception as e:
        print(f"부저음 재생 오류: {e}")
