from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from tts.classify_real import ClassifyVoice
from openai import OpenAI
import os
from dotenv import load_dotenv
import io

load_dotenv()

router = APIRouter(prefix="/voice", tags=["Voice"])

# ClassifyVoice는 lazy loading (필요시에만 초기화)
_voice_instance = None

def get_voice():
    global _voice_instance
    if _voice_instance is None:
        try:
            _voice_instance = ClassifyVoice()
        except Exception as e:
            print(f"ClassifyVoice 초기화 실패: {e}")
            return None
    return _voice_instance

class VoiceRequest(BaseModel):
    is_ally: bool

class TTSRequest(BaseModel):
    text: str
    voice: str = "onyx"  # alloy, echo, fable, onyx, nova, shimmer

@router.post("/classify")
def speak_classify(req: VoiceRequest):
    voice = get_voice()
    if voice is None:
        return {"success": False, "error": "TTS 초기화 실패"}
    success = voice.speak_result(req.is_ally)
    return {"success": success}

@router.post("/ask-password")
def ask_password():
    """적군 감지 시 암구호 질문 - 자동 호출용"""
    voice = get_voice()
    if voice is None:
        return {"success": False, "error": "TTS 초기화 실패"}
    try:
        success = voice.ask_password()
        return {"success": success}
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.post("/password-result")
def password_result(correct: bool = True):
    """암구호 결과 음성"""
    voice = get_voice()
    if voice is None:
        return {"success": False, "error": "TTS 초기화 실패"}
    try:
        if correct:
            success = voice.password_correct()
        else:
            success = voice.password_wrong()
        return {"success": success}
    except Exception as e:
        return {"success": False, "error": str(e)}

class WelcomeRequest(BaseModel):
    name: str = None

@router.post("/welcome")
def welcome(req: WelcomeRequest = None):
    """환영 인사"""
    voice = get_voice()
    if voice is None:
        return {"success": False, "error": "TTS 초기화 실패"}
    try:
        name = req.name if req else None
        success = voice.welcome(name)
        return {"success": success}
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.post("/access-denied")
def access_denied():
    """출입 거부 음성"""
    voice = get_voice()
    if voice is None:
        return {"success": False, "error": "TTS 초기화 실패"}
    try:
        success = voice.access_denied()
        return {"success": success}
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.post("/speak")
def speak_text(req: TTSRequest):
    """텍스트를 음성으로 변환하여 스피커로 재생"""
    voice = get_voice()
    if voice is None:
        return {"success": False, "error": "TTS 초기화 실패"}
    try:
        success = voice.tts.speak(req.text)
        return {"success": success}
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.post("/tts")
def get_tts_audio(req: TTSRequest):
    """텍스트를 음성으로 변환하여 오디오 스트림 반환 (웹 재생용)"""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {"error": "OPENAI_API_KEY not configured"}
    
    try:
        client = OpenAI(api_key=api_key)
        response = client.audio.speech.create(
            model="tts-1",
            voice=req.voice,
            input=req.text,
            response_format="mp3"
        )
        
        # MP3 스트림 반환
        audio_bytes = io.BytesIO(response.read())
        return StreamingResponse(
            audio_bytes,
            media_type="audio/mpeg",
            headers={"Content-Disposition": "inline; filename=speech.mp3"}
        )
    except Exception as e:
        return {"error": str(e)}

@router.get("/voices")
def get_available_voices():
    """사용 가능한 음성 목록"""
    return {
        "voices": [
            {"id": "alloy", "name": "Alloy", "description": "중성적인 음성"},
            {"id": "echo", "name": "Echo", "description": "남성적인 음성"},
            {"id": "fable", "name": "Fable", "description": "영국식 음성"},
            {"id": "onyx", "name": "Onyx", "description": "깊은 남성 음성"},
            {"id": "nova", "name": "Nova", "description": "여성적인 음성"},
            {"id": "shimmer", "name": "Shimmer", "description": "밝은 여성 음성"},
        ]
    }
