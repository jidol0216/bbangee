import os
import io
import tempfile
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

class TTS:
    """TTS 엔진 - gTTS(무료) 또는 OpenAI 지원"""
    
    def __init__(self, engine_type="gtts", voice_id="nova"):
        self.engine_type = engine_type
        self.voice_id = voice_id
        
        if engine_type == "openai":
            from openai import OpenAI
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                print(" OPENAI_API_KEY 없음, gTTS로 fallback")
                self.engine_type = "gtts"
            else:
                self.client = OpenAI(api_key=api_key)

    def speak(self, text: str) -> bool:
        """텍스트를 음성으로 변환하여 스피커로 재생"""
        try:
            if self.engine_type == "openai":
                return self._speak_openai(text)
            else:
                return self._speak_gtts(text)
        except Exception as e:
            print(f"TTS 오류: {e}")
            # OpenAI 실패 시 gTTS로 fallback
            if self.engine_type == "openai":
                print("→ gTTS로 fallback 시도")
                return self._speak_gtts(text)
            return False

    def _speak_openai(self, text: str) -> bool:
        """OpenAI TTS"""
        try:
            import sounddevice as sd
            import numpy as np
            from pydub import AudioSegment
            
            response = self.client.audio.speech.create(
                model="tts-1",
                voice=self.voice_id,
                input=text
            )
            
            # MP3 → PCM 변환
            mp3_data = response.read()
            audio = AudioSegment.from_mp3(io.BytesIO(mp3_data))
            samples = np.array(audio.get_array_of_samples())
            
            sd.play(samples, samplerate=audio.frame_rate)
            sd.wait()
            return True
        except Exception as e:
            print(f"OpenAI TTS 오류: {e}")
            raise

    def _speak_gtts(self, text: str) -> bool:
        """Google TTS (무료) - 음량 증폭 적용"""
        try:
            from gtts import gTTS
            import pygame
            
            # pygame mixer 초기화
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            
            # TTS 생성
            tts = gTTS(text=text, lang='ko')
            
            # 임시 파일에 저장
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as f:
                tts.save(f.name)
                temp_path = f.name
            
            # 음량 증폭 (pydub 사용)
            try:
                from pydub import AudioSegment
                audio = AudioSegment.from_mp3(temp_path)
                audio = audio + 6  # +6dB 증폭 (약 2배)
                audio.export(temp_path, format="mp3")
            except:
                pass  # pydub 없으면 원본 사용
            
            pygame.mixer.music.load(temp_path)
            pygame.mixer.music.set_volume(1.0)  # 최대 볼륨
            pygame.mixer.music.play()
            
            # 재생 완료 대기
            while pygame.mixer.music.get_busy():
                pygame.time.Clock().tick(10)
            
            # 임시 파일 삭제
            os.unlink(temp_path)
            return True
        except Exception as e:
            print(f"gTTS 오류: {e}")
            return False
    
    def get_audio_bytes(self, text: str) -> bytes:
        """음성 데이터를 바이트로 반환 (웹 브라우저용)"""
        try:
            if self.engine_type == "openai":
                response = self.client.audio.speech.create(
                    model="tts-1",
                    voice=self.voice_id,
                    input=text
                )
                return response.read()
            else:
                from gtts import gTTS
                tts = gTTS(text=text, lang='ko')
                mp3_buffer = io.BytesIO()
                tts.write_to_fp(mp3_buffer)
                mp3_buffer.seek(0)
                return mp3_buffer.read()
        except Exception as e:
            print(f"get_audio_bytes 오류: {e}")
            return b""
