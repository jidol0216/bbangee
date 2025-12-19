#!/usr/bin/env python3
"""
TTS Engine for Voice Auth
=========================

지원 엔진:
- elevenlabs: 고품질 AI 음성 (API 키 필요)
- gtts: Google TTS (무료, 인터넷 필요)
- pyttsx3: 오프라인 TTS (기본)
"""

import os
import io
import tempfile
from threading import Lock
from typing import Optional

# ElevenLabs API 키 (환경변수 또는 직접 설정)
ELEVENLABS_API_KEY = os.getenv(
    "ELEVENLABS_API_KEY", 
    "sk_65b082009dbdb686eedff09fbd15c0fb146cef393b75bbf4"
)

# ElevenLabs 음성 ID (한국어 지원 음성)
# pNInz6obpgDQGcFmaJgB = Adam (영어)
# 한국어 더 잘하는 음성: Rachel, Bella 등
DEFAULT_VOICE_ID = "pNInz6obpgDQGcFmaJgB"


class TTSEngine:
    """Thread-safe TTS 엔진"""
    
    _instance: Optional['TTSEngine'] = None
    _lock = Lock()
    
    def __init__(self, engine_type: str = "elevenlabs", voice_id: str = None):
        self.engine_type = engine_type
        self.voice_id = voice_id or DEFAULT_VOICE_ID
        self._client = None
        self._pyttsx3_engine = None
        
        # ElevenLabs 초기화
        if engine_type == "elevenlabs":
            if not ELEVENLABS_API_KEY or ELEVENLABS_API_KEY.startswith("sk_"):
                try:
                    from elevenlabs.client import ElevenLabs
                    self._client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
                    print(f"✅ ElevenLabs TTS 초기화 완료 (voice: {self.voice_id})")
                except Exception as e:
                    print(f"⚠️ ElevenLabs 초기화 실패: {e}, pyttsx3로 fallback")
                    self.engine_type = "pyttsx3"
            else:
                print("⚠️ ELEVENLABS_API_KEY 없음, pyttsx3로 fallback")
                self.engine_type = "pyttsx3"
    
    @classmethod
    def get_instance(cls, engine_type: str = "elevenlabs") -> 'TTSEngine':
        """싱글톤 인스턴스 반환"""
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(engine_type=engine_type)
            return cls._instance
    
    def speak(self, text: str) -> bool:
        """텍스트를 음성으로 변환하여 재생"""
        print(f"🔊 TTS [{self.engine_type}]: \"{text}\"")
        
        try:
            if self.engine_type == "elevenlabs":
                return self._speak_elevenlabs(text)
            elif self.engine_type == "gtts":
                return self._speak_gtts(text)
            else:
                return self._speak_pyttsx3(text)
        except Exception as e:
            print(f"❌ TTS 오류 ({self.engine_type}): {e}")
            # Fallback to pyttsx3
            if self.engine_type != "pyttsx3":
                print("→ pyttsx3로 fallback")
                return self._speak_pyttsx3(text)
            return False
    
    def _speak_elevenlabs(self, text: str) -> bool:
        """ElevenLabs TTS (고품질 AI 음성)"""
        try:
            import sounddevice as sd
            import numpy as np
            from pydub import AudioSegment
            
            # 음성 생성
            audio_generator = self._client.text_to_speech.convert(
                voice_id=self.voice_id,
                text=text,
                model_id="eleven_multilingual_v2",  # 다국어 지원
                output_format="mp3_44100_128"
            )
            
            # Generator를 바이트로 변환
            audio_bytes = b"".join(audio_generator)
            
            # MP3 → PCM 변환
            audio = AudioSegment.from_mp3(io.BytesIO(audio_bytes))
            
            # 스테레오 → 모노 변환 (필요시)
            if audio.channels == 2:
                audio = audio.set_channels(1)
            
            samples = np.array(audio.get_array_of_samples(), dtype=np.int16)
            
            # 재생
            sd.play(samples, samplerate=audio.frame_rate)
            sd.wait()
            
            return True
            
        except Exception as e:
            print(f"ElevenLabs TTS 오류: {e}")
            raise
    
    def _speak_gtts(self, text: str) -> bool:
        """Google TTS (무료)"""
        try:
            from gtts import gTTS
            import pygame
            
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            
            tts = gTTS(text=text, lang='ko')
            
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as f:
                tts.save(f.name)
                temp_path = f.name
            
            pygame.mixer.music.load(temp_path)
            pygame.mixer.music.play()
            
            while pygame.mixer.music.get_busy():
                pygame.time.Clock().tick(10)
            
            os.unlink(temp_path)
            return True
            
        except Exception as e:
            print(f"gTTS 오류: {e}")
            raise
    
    def _speak_pyttsx3(self, text: str) -> bool:
        """pyttsx3 오프라인 TTS"""
        try:
            import pyttsx3
            
            with self._lock:
                if self._pyttsx3_engine is None:
                    self._pyttsx3_engine = pyttsx3.init()
                
                self._pyttsx3_engine.say(text)
                self._pyttsx3_engine.runAndWait()
            
            return True
            
        except Exception as e:
            print(f"pyttsx3 오류: {e}")
            return False


# 간편 사용을 위한 모듈 레벨 함수
def say(text: str, engine_type: str = "elevenlabs") -> bool:
    """텍스트를 음성으로 출력"""
    engine = TTSEngine.get_instance(engine_type)
    return engine.speak(text)


# 테스트
if __name__ == "__main__":
    print("=== TTS Engine Test ===")
    
    # ElevenLabs 테스트
    print("\n1. ElevenLabs TTS:")
    say("정지! 손들어! 암구호! 까마귀!", "elevenlabs")
    
    # pyttsx3 테스트 (fallback)
    print("\n2. pyttsx3 TTS:")
    say("암구호 일치. 통과하십시오.", "pyttsx3")
