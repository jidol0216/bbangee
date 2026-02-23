"""
TTS 서비스
==========
ElevenLabs + gTTS fallback 로직을 한 곳에서 관리

Before: voice.py 에 elevenlabs_speak() 정의 → scenario.py 가 HTTP 로 호출
After : tts_service.speak() 직접 호출
"""

import io
import sys
import threading

from app.services.config import (
    ELEVENLABS_API_KEY,
    ELEVENLABS_VOICE_IDS,
    DEFAULT_VOICE_ID,
    TTS_VOLUME_BOOST_DB,
)

# TTS 동시 실행 방지
_tts_lock = threading.Lock()


def resolve_voice_id(voice_name: str) -> str:
    """음성 이름 → ElevenLabs voice_id"""
    return ELEVENLABS_VOICE_IDS.get(voice_name, DEFAULT_VOICE_ID)


def speak(text: str, voice: str = "eric",
          volume_boost_db: float | None = None) -> bool:
    """
    ElevenLabs TTS 재생 (서버 스피커) — 재생 완료까지 블로킹

    Args:
        text: 발화할 텍스트
        voice: 음성 이름 (eric / chris / sarah / jessica) 또는 voice_id
        volume_boost_db: 볼륨 증폭 dB (None 이면 config 기본값)

    Returns:
        성공 여부
    """
    if volume_boost_db is None:
        volume_boost_db = TTS_VOLUME_BOOST_DB
    voice_id = resolve_voice_id(voice) if len(voice) < 30 else voice

    with _tts_lock:
        print(f"[TTS] 시작: '{text}' (볼륨 +{volume_boost_db}dB)", flush=True)
        sys.stdout.flush()

        try:
            from elevenlabs import ElevenLabs
            import sounddevice as sd
            from pydub import AudioSegment
            import numpy as np

            client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
            audio = client.text_to_speech.convert(
                voice_id=voice_id,
                model_id="eleven_multilingual_v2",
                text=text,
            )
            audio_bytes = b"".join(audio)

            audio_segment = AudioSegment.from_mp3(io.BytesIO(audio_bytes))
            audio_segment = audio_segment + volume_boost_db

            samples = audio_segment.get_array_of_samples()
            audio_data = np.array(samples, dtype=np.int16)
            if audio_segment.channels == 2:
                audio_data = audio_data.reshape((-1, 2))

            sd.play(audio_data, samplerate=audio_segment.frame_rate)
            sd.wait()
            print("[TTS] 재생 완료", flush=True)
            return True

        except Exception as e:
            import traceback
            print(f"[TTS] 에러: {e}", flush=True)
            traceback.print_exc()
            # gTTS fallback
            try:
                from tts.TTS import TTS as GttsEngine
                engine = GttsEngine(engine_type="gtts")
                t = threading.Thread(target=engine.speak, args=(text,))
                t.start()
                t.join(timeout=10)
                print(f"[TTS] gTTS fallback 완료: '{text}'", flush=True)
                return True
            except Exception as e2:
                print(f"[TTS] fallback 에러: {e2}", flush=True)
            return False


def speak_stream_bytes(text: str, voice: str = "eric") -> bytes:
    """
    TTS 오디오 바이트 반환 (웹 브라우저 재생용 MP3)
    """
    from elevenlabs import ElevenLabs

    client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
    voice_id = resolve_voice_id(voice)
    audio = client.text_to_speech.convert(
        voice_id=voice_id,
        model_id="eleven_multilingual_v2",
        text=text,
    )
    return b"".join(audio)
