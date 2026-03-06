"""
Voice Authentication API Router (리팩토링)
==========================================

변경사항:
  - ElevenLabs TTS → tts_service 로 분리
  - record_audio / speech_to_text → audio_service 로 분리
  - run_auth_process / run_auth_process_for_scenario → _run_auth 하나로 통합
  - HTTP 자기호출(scenario/password) → scenario_manager 직접 호출
  - API 키 / 하드코딩 → config 에서 로드
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
import io
import json
import os
import threading
import time

from app.services import tts_service, audio_service
from app.services.config import VOICE_STATE_FILE, DEFAULT_PASSWORD_CHALLENGE, DEFAULT_PASSWORD_RESPONSE

router = APIRouter(prefix="/voice", tags=["Voice"])

# ==================== 인증 상태 ====================

auth_state = {
    "status": "IDLE",
    "question": DEFAULT_PASSWORD_CHALLENGE,
    "answer": DEFAULT_PASSWORD_RESPONSE,
    "recognized_text": "",
    "last_result": None,
    "enabled": True,
    "scenario_locked": False,
}
_state_lock = threading.Lock()


def _save_state():
    try:
        with open(VOICE_STATE_FILE, "w") as f:
            json.dump(auth_state, f)
    except Exception as e:
        print(f"상태 저장 실패: {e}")


def _load_state():
    global auth_state
    try:
        if os.path.exists(VOICE_STATE_FILE):
            with open(VOICE_STATE_FILE, "r") as f:
                auth_state.update(json.load(f))
    except Exception as e:
        print(f"상태 로드 실패: {e}")


# ==================== 내부 API (scenario 에서 직접 호출용) ====================

def set_passphrase_internal(question: str, answer: str):
    """scenario.py 에서 직접 호출하여 암구호 동기화"""
    with _state_lock:
        auth_state["question"] = question
        auth_state["answer"] = answer
        _save_state()


def reset_voice_internal():
    """scenario.py 에서 직접 호출하여 상태 리셋"""
    with _state_lock:
        auth_state["status"] = "IDLE"
        auth_state["recognized_text"] = ""
        auth_state["last_result"] = None
        auth_state["scenario_locked"] = False
        _save_state()


def start_scenario_auth_internal(timeout_sec: float = 5.0, voice: str = "eric"):
    """scenario.py 에서 직접 호출하여 시나리오 전용 인증 시작"""
    with _state_lock:
        if auth_state["status"] != "IDLE":
            return
        auth_state["status"] = "PROCESSING"
        auth_state["scenario_locked"] = True
        _save_state()

    voice_id = tts_service.resolve_voice_id(voice)
    t = threading.Thread(
        target=_run_auth,
        args=(timeout_sec, voice_id, True),
        daemon=True,
    )
    t.start()


# ==================== 통합 인증 프로세스 ====================

def _submit_to_scenario(password: str) -> dict:
    """인식된 암구호를 시나리오 시스템에 직접 제출"""
    try:
        from app.routers.scenario import scenario_manager
        import asyncio

        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(scenario_manager.submit_password(password))
        loop.close()
        print(f" 시나리오 암구호 제출: '{password}' → {result}")
        return result
    except Exception as e:
        print(f"시나리오 암구호 제출 실패: {e}")
        return {"success": False, "error": str(e)}


def _run_auth(timeout_sec: float, voice_id: str, is_scenario: bool = False):
    """
    통합 암구호 인증 프로세스 (백그라운드 스레드)

    Before: run_auth_process() + run_auth_process_for_scenario() 95% 동일 코드 2벌
    After : is_scenario 플래그로 분기
    """
    global auth_state

    try:
        with _state_lock:
            question = auth_state["question"]
            answer = auth_state["answer"]

        # 1. TTS 질문
        tag = "[시나리오]" if is_scenario else "[보이스패널]"
        print(f" {tag} TTS 시작: 암구호! {question}!", flush=True)
        tts_service.speak(f"암구호! {question}!", voice_id)
        time.sleep(1.0)

        # 2. 상태: LISTENING
        with _state_lock:
            auth_state["status"] = "LISTENING"
            auth_state["recognized_text"] = ""
            _save_state()

        # 3. 녹음
        audio_data, sample_rate = audio_service.record_audio(duration=5.0)

        # 4. 상태: PROCESSING
        with _state_lock:
            auth_state["status"] = "PROCESSING"
            _save_state()

        # 5. STT
        recognized = audio_service.speech_to_text(audio_data, rate=sample_rate)
        print(f" {tag} 인식된 텍스트: '{recognized}'", flush=True)

        with _state_lock:
            auth_state["recognized_text"] = recognized

        # 6. 시나리오 제출
        if recognized.strip():
            _submit_to_scenario(recognized.strip())
        else:
            print(f" {tag} 인식된 텍스트 없음 - 제출 건너뜀", flush=True)

        # 7. 로컬 비교
        is_match = audio_service.check_passphrase(recognized, answer)

        with _state_lock:
            auth_state["status"] = "SUCCESS" if is_match else "FAILED"
            auth_state["last_result"] = is_match
            _save_state()

        # 8. IDLE 복귀
        with _state_lock:
            auth_state["status"] = "IDLE"
            if is_scenario:
                auth_state["scenario_locked"] = False
            _save_state()

        if is_scenario:
            print(" [시나리오] 음성 인증 완료, 보이스 패널 락 해제", flush=True)

    except Exception as e:
        print(f"인증 프로세스 오류: {e}")
        with _state_lock:
            auth_state["status"] = "ERROR"
            auth_state["recognized_text"] = str(e)
            if is_scenario:
                auth_state["scenario_locked"] = False
            _save_state()
        time.sleep(1)
        with _state_lock:
            auth_state["status"] = "IDLE"
            _save_state()


def _run_listen_only(timeout_sec: float = 3.5):
    """TTS 없이 음성 인식만 (시나리오 호출용)"""
    global auth_state

    try:
        with _state_lock:
            answer = auth_state["answer"]
            auth_state["status"] = "LISTENING"
            auth_state["recognized_text"] = ""
            _save_state()

        audio_data, sample_rate = audio_service.record_audio(duration=timeout_sec)

        with _state_lock:
            auth_state["status"] = "PROCESSING"
            _save_state()

        recognized = audio_service.speech_to_text(audio_data, rate=sample_rate)
        with _state_lock:
            auth_state["recognized_text"] = recognized

        if recognized.strip():
            _submit_to_scenario(recognized.strip())

        is_match = audio_service.check_passphrase(recognized, answer) if recognized else False

        with _state_lock:
            auth_state["status"] = "SUCCESS" if is_match else "FAILED"
            auth_state["last_result"] = is_match
            _save_state()

        time.sleep(2)
        with _state_lock:
            auth_state["status"] = "IDLE"
            _save_state()

    except Exception as e:
        print(f"[자동인식] 오류: {e}")
        with _state_lock:
            auth_state["status"] = "ERROR"
            _save_state()
        time.sleep(3)
        with _state_lock:
            auth_state["status"] = "IDLE"
            _save_state()


# ==================== Models ====================

class PassphraseRequest(BaseModel):
    question: str = "까마귀"
    answer: str = "백두산"

class TTSRequest(BaseModel):
    text: str
    voice: str = "eric"

class AuthRequest(BaseModel):
    timeout_sec: float = 3.5
    voice: str = "eric"

class VoiceRequest(BaseModel):
    is_ally: bool

class WelcomeRequest(BaseModel):
    name: Optional[str] = None


# ==================== Endpoints ====================

@router.get("/status")
def get_voice_auth_status():
    with _state_lock:
        return {
            "enabled": auth_state.get("enabled", True),
            "status": auth_state.get("status", "IDLE"),
            "question": auth_state.get("question"),
            "answer": auth_state.get("answer"),
            "recognized_text": auth_state.get("recognized_text", ""),
            "last_result": auth_state.get("last_result"),
            "voice_auth_running": True,
        }


@router.post("/reset")
def reset_voice_state():
    reset_voice_internal()
    return {"success": True, "message": "Voice 상태 리셋됨"}


@router.post("/passphrase")
def set_passphrase(req: PassphraseRequest):
    set_passphrase_internal(req.question, req.answer)
    return {"success": True, "question": req.question, "answer": req.answer}


@router.post("/request-auth")
async def request_auth(req: AuthRequest):
    with _state_lock:
        if auth_state.get("scenario_locked", False):
            return {"success": False, "error": "시나리오 진행 중 - 보이스 패널 사용 불가"}
        if auth_state["status"] != "IDLE":
            return {"success": False, "error": "이미 인증 진행 중"}
        auth_state["status"] = "PROCESSING"
        _save_state()

    voice_id = tts_service.resolve_voice_id(req.voice)
    threading.Thread(target=_run_auth, args=(req.timeout_sec, voice_id, False), daemon=True).start()
    return {"success": True, "message": "인증 시작됨"}


@router.post("/scenario-request-auth")
async def scenario_request_auth(req: AuthRequest):
    with _state_lock:
        if auth_state["status"] != "IDLE":
            return {"success": False, "error": "이미 인증 진행 중"}
        auth_state["status"] = "PROCESSING"
        auth_state["scenario_locked"] = True
        _save_state()

    voice_id = tts_service.resolve_voice_id(req.voice)
    threading.Thread(target=_run_auth, args=(req.timeout_sec, voice_id, True), daemon=True).start()
    return {"success": True, "message": "시나리오 인증 시작됨"}


@router.post("/speak")
def speak_text(req: TTSRequest):
    success = tts_service.speak(req.text, req.voice)
    return {"success": success}


@router.post("/tts")
def get_tts_audio(req: TTSRequest):
    try:
        audio_bytes = tts_service.speak_stream_bytes(req.text, req.voice)
        return StreamingResponse(
            io.BytesIO(audio_bytes),
            media_type="audio/mpeg",
            headers={"Content-Disposition": "inline; filename=speech.mp3"},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/voices")
def get_available_voices():
    return {
        "voices": [
            {"id": "eric", "name": "Eric", "description": "남성 (기본)"},
            {"id": "chris", "name": "Chris", "description": "남성 - 친근한"},
            {"id": "sarah", "name": "Sarah", "description": "여성 - 차분한"},
            {"id": "jessica", "name": "Jessica", "description": "여성 - 밝은"},
        ]
    }


@router.post("/listen-only")
async def listen_only(background_tasks: BackgroundTasks, timeout_sec: float = 3.5):
    with _state_lock:
        if auth_state["status"] != "IDLE":
            return {"success": False, "error": "이미 인식 진행 중"}
        auth_state["status"] = "PROCESSING"
        _save_state()
    background_tasks.add_task(_run_listen_only, timeout_sec)
    return {"success": True, "message": "음성 인식 시작됨"}


# ==================== Legacy Endpoints ====================

@router.post("/classify")
def speak_classify(req: VoiceRequest):
    text = "아군으로 확인되었습니다. 통과하십시오." if req.is_ally else "적군으로 확인되었습니다. 정지하십시오!"
    return {"success": tts_service.speak(text)}


@router.post("/ask-password")
def ask_password():
    with _state_lock:
        question = auth_state.get("question", "까마귀")
    return {"success": tts_service.speak(f"정지! 암구호! {question}!")}


@router.post("/password-result")
def password_result(correct: bool = True):
    text = "암구호 일치. 통과하십시오." if correct else "암구호 불일치. 정지하십시오!"
    return {"success": tts_service.speak(text)}


@router.post("/welcome")
def welcome(req: WelcomeRequest = None):
    name = req.name if req else None
    text = f"{name}님, 환영합니다. 통과하십시오." if name else "환영합니다. 통과하십시오."
    return {"success": tts_service.speak(text)}


@router.post("/access-denied")
def access_denied():
    return {"success": tts_service.speak("출입이 거부되었습니다. 정지하십시오!")}
