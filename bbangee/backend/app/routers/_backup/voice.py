"""
Voice Authentication API Router
================================

웹에서 직접 암구호 인증 테스트를 위한 API.

기능:
1. 암구호 인증 요청 (/request-auth) - 직접 TTS + 마이크 + STT 처리
2. 암구호 설정 변경 (/passphrase) - 메모리/파일에 저장
3. 상태 조회 (/status) - 현재 상태 반환
4. ElevenLabs TTS (/speak) - 직접 텍스트 발화

구조:
    [Web UI] <-> [FastAPI Backend] (직접 처리)
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import os
import json
import io
import time
import threading
import requests
from dotenv import load_dotenv
from typing import Optional

load_dotenv()

router = APIRouter(prefix="/voice", tags=["Voice"])

# 시나리오 API 연동
SCENARIO_API_URL = "http://localhost:8000/scenario"

# 상태 파일 경로
STATE_FILE = "/tmp/voice_auth_state.json"

# ElevenLabs 설정
ELEVENLABS_API_KEY = "sk_65b082009dbdb686eedff09fbd15c0fb146cef393b75bbf4"
ELEVENLABS_VOICE_IDS = {
    "eric": "cjVigY5qzO86Huf0OWal",      # 남성 - 부드럽고 신뢰감
    "chris": "iP95p4xoKVk53GoZ742B",     # 남성 - 친근하고 편안한
    "sarah": "EXAVITQu4vr4xnSDxMaL",     # 여성 - 차분하고 신뢰감
    "jessica": "cgSgspJ2msm6clMCkdW9",   # 여성 - 밝고 따뜻한
}
DEFAULT_VOICE_ID = "cjVigY5qzO86Huf0OWal"  # Eric (남성)

# 현재 인증 상태 (메모리) - 시나리오와 동일한 기본값
auth_state = {
    "status": "IDLE",  # IDLE, LISTENING, PROCESSING, SUCCESS, FAILED, ERROR
    "question": "로키",      # 시나리오와 동일
    "answer": "협동",        # 시나리오와 동일
    "recognized_text": "",
    "last_result": None,
    "enabled": True,
    "scenario_locked": False  # 시나리오가 사용 중일 때 True (보이스 패널 차단)
}
state_lock = threading.Lock()

# TTS 동시 실행 방지 락
tts_lock = threading.Lock()


# ==================== Models ====================

class PassphraseRequest(BaseModel):
    """암구호 설정 요청"""
    question: str = "까마귀"
    answer: str = "백두산"



class TTSRequest(BaseModel):
    """TTS 요청"""
    text: str
    voice: str = "adam"  # adam, nicole, daniel


class AuthRequest(BaseModel):
    """암구호 인증 요청"""
    timeout_sec: float = 3.5
    voice: str = "eric"  # 음성 선택: eric, chris, sarah, jessica


# ==================== Helper Functions ====================

def save_state():
    """상태를 파일에 저장"""
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(auth_state, f)
    except Exception as e:
        print(f"상태 저장 실패: {e}")


def load_state():
    """파일에서 상태 로드"""
    global auth_state
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                loaded = json.load(f)
                auth_state.update(loaded)
    except Exception as e:
        print(f"상태 로드 실패: {e}")


def elevenlabs_speak(text: str, voice_id: str = DEFAULT_VOICE_ID, volume_boost_db: float = 10.0) -> bool:
    """
    ElevenLabs TTS로 텍스트 발화 (서버 스피커)
    volume_boost_db: 볼륨 증폭 (dB). 기본 +10dB
    
     tts_lock으로 동시 실행 방지 - 한 번에 하나의 TTS만 재생
    """
    import sys
    
    # 락 획득 대기 (다른 TTS가 끝날 때까지)
    with tts_lock:
        print(f"[TTS] 시작: '{text}' (볼륨 +{volume_boost_db}dB)", flush=True)
        sys.stdout.flush()
        
        try:
            from elevenlabs import ElevenLabs
            import sounddevice as sd
            from pydub import AudioSegment
            import numpy as np
            
            client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
            print("[TTS] ElevenLabs 클라이언트 생성됨", flush=True)
            
            audio = client.text_to_speech.convert(
                voice_id=voice_id,
                model_id="eleven_multilingual_v2",
                text=text
            )
            print("[TTS] 오디오 생성됨", flush=True)
            
            audio_bytes = b"".join(audio)
            print(f"[TTS] 오디오 바이트: {len(audio_bytes)}", flush=True)
            
            audio_segment = AudioSegment.from_mp3(io.BytesIO(audio_bytes))
            
            # 볼륨 증폭 (+dB)
            audio_segment = audio_segment + volume_boost_db
            print(f"[TTS] 볼륨 증폭: +{volume_boost_db}dB", flush=True)
            
            samples = audio_segment.get_array_of_samples()
            
            audio_data = np.array(samples, dtype=np.int16)
            if audio_segment.channels == 2:
                audio_data = audio_data.reshape((-1, 2))
            
            print("[TTS] 재생 시작", flush=True)
            sd.play(audio_data, samplerate=audio_segment.frame_rate)
            sd.wait()
            print("[TTS] 재생 완료", flush=True)
            
            return True
        except Exception as e:
            import traceback
            print(f"[TTS] 에러: {e}", flush=True)
            traceback.print_exc()
            return False


def record_audio(duration: float = 3.5, device_index: int = 4) -> bytes:
    """
    마이크에서 녹음 (C270 HD WEBCAM - 장치 인덱스 4)
    """
    import pyaudio
    import traceback
    
    CHUNK = 4096
    CHANNELS = 1
    FORMAT = pyaudio.paInt16
    RATE = 48000  # C270 웹캠 기본 샘플레이트
    
    print(f" [record_audio] 시작 - duration={duration}, device={device_index}", flush=True)
    
    p = pyaudio.PyAudio()
    
    try:
        # C270 웹캠 마이크 사용 (장치 4)
        try:
            info = p.get_device_info_by_index(device_index)
            print(f" 마이크: [{device_index}] {info['name']}", flush=True)
        except Exception as e:
            print(f" 장치 {device_index} 정보 조회 실패: {e}", flush=True)
            traceback.print_exc()
        
        print(f" [record_audio] stream 열기 시도...", flush=True)
        stream = p.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=RATE,
            input=True,
            input_device_index=device_index,
            frames_per_buffer=CHUNK
        )
        print(f" [record_audio] stream 열림!", flush=True)
        
        frames = []
        num_chunks = int(RATE / CHUNK * duration)
        
        print(f" {duration}초 녹음 중... (chunks: {num_chunks})", flush=True)
        for i in range(num_chunks):
            data = stream.read(CHUNK, exception_on_overflow=False)
            frames.append(data)
        
        stream.stop_stream()
        stream.close()
        
        audio_bytes = b"".join(frames)
        print(f" [record_audio] 완료! bytes={len(audio_bytes)}", flush=True)
        
        return audio_bytes, RATE
    except Exception as e:
        print(f" [record_audio] 에러: {e}", flush=True)
        traceback.print_exc()
        return b"", RATE
    finally:
        p.terminate()


def speech_to_text(audio_data: bytes, rate: int = 48000) -> str:
    """
    Google STT로 음성을 텍스트로 변환
    """
    import speech_recognition as sr
    
    recognizer = sr.Recognizer()
    audio = sr.AudioData(audio_data, rate, 2)  # 16bit = 2bytes
    
    try:
        text = recognizer.recognize_google(audio, language="ko-KR")
        return text
    except sr.UnknownValueError:
        return ""
    except sr.RequestError as e:
        print(f"STT 서비스 오류: {e}")
        return ""


def check_passphrase(recognized: str, answer: str) -> bool:
    """암구호 일치 여부 확인"""
    normalized_text = recognized.replace(" ", "").strip()
    normalized_answer = answer.replace(" ", "").strip()
    return normalized_answer in normalized_text


def submit_to_scenario(password: str) -> dict:
    """
    인식된 암구호를 시나리오 시스템에 자동 제출
    """
    try:
        response = requests.post(
            f"{SCENARIO_API_URL}/password",
            json={"password": password},
            timeout=5
        )
        result = response.json()
        print(f" 시나리오 암구호 제출: '{password}' → {result}")
        return result
    except Exception as e:
        print(f"시나리오 암구호 제출 실패: {e}")
        return {"success": False, "error": str(e)}


def run_auth_process(timeout_sec: float, voice_id: str = DEFAULT_VOICE_ID):
    """
    암구호 인증 프로세스 실행 (백그라운드)
    
    1. TTS로 질문 출력 (정지!는 시나리오에서 이미 말함)
    2. 마이크 녹음
    3. STT로 텍스트 변환
    4. 암구호 비교 및 결과 TTS
    """
    global auth_state
    
    try:
        with state_lock:
            question = auth_state["question"]
            answer = auth_state["answer"]
        
        # 1. TTS: 질문만 (정지!는 시나리오에서 이미 말함)
        print(f" TTS 시작: 암구호! {question}!", flush=True)
        elevenlabs_speak(f"암구호! {question}!", voice_id)
        print(" TTS 완료, 1초 대기 후 녹음 시작", flush=True)
        time.sleep(1.0)  # TTS 끝난 후 잠시 대기 (마이크가 TTS 소리 안 잡도록)
        
        # 2. 상태 변경: LISTENING
        with state_lock:
            auth_state["status"] = "LISTENING"
            auth_state["recognized_text"] = ""
            save_state()
        
        # 3. 마이크 녹음 (5초)
        audio_data, sample_rate = record_audio(duration=5.0)
        
        # 4. 상태 변경: PROCESSING
        with state_lock:
            auth_state["status"] = "PROCESSING"
            save_state()
        
        # 5. STT
        recognized = speech_to_text(audio_data, rate=sample_rate)
        print(f" 인식된 텍스트: '{recognized}'", flush=True)
        
        with state_lock:
            auth_state["recognized_text"] = recognized
        
        # 6. 시나리오 시스템에 자동 제출 (인식된 텍스트가 있으면)
        if recognized.strip():
            scenario_result = submit_to_scenario(recognized.strip())
            print(f" 시나리오 제출 결과: {scenario_result}", flush=True)
        else:
            print(" 인식된 텍스트 없음 - 시나리오 제출 건너뜀", flush=True)
        
        # 7. 암구호 비교 (로컬 확인용)
        is_match = check_passphrase(recognized, answer)
        
        # 8. 결과 처리
        with state_lock:
            if is_match:
                auth_state["status"] = "SUCCESS"
                auth_state["last_result"] = True
            else:
                auth_state["status"] = "FAILED"
                auth_state["last_result"] = False
            save_state()
        
        # 9. 결과 TTS는 시나리오 시스템에서 처리하므로 생략
        # (시나리오가 암구호 결과에 따라 TTS를 재생함)
        
        # 10. 바로 IDLE로 복귀 (다음 인증 가능하도록)
        with state_lock:
            auth_state["status"] = "IDLE"
            save_state()
            
    except Exception as e:
        print(f"인증 프로세스 오류: {e}")
        with state_lock:
            auth_state["status"] = "ERROR"
            auth_state["recognized_text"] = str(e)
            save_state()
        
        time.sleep(1)
        with state_lock:
            auth_state["status"] = "IDLE"
            save_state()


def run_auth_process_for_scenario(timeout_sec: float, voice_id: str = DEFAULT_VOICE_ID):
    """
    시나리오 전용 암구호 인증 프로세스 (백그라운드)
    
    run_auth_process와 동일하지만:
    - scenario_locked 플래그를 해제함
    - 완료 후 보이스 패널 사용 가능하도록 복원
    """
    global auth_state
    
    try:
        with state_lock:
            question = auth_state["question"]
            answer = auth_state["answer"]
        
        # 1. TTS: 질문
        print(f" [시나리오] TTS 시작: 암구호! {question}!", flush=True)
        elevenlabs_speak(f"암구호! {question}!", voice_id)
        print(" [시나리오] TTS 완료, 1초 대기 후 녹음 시작", flush=True)
        time.sleep(1.0)
        
        # 2. 상태 변경: LISTENING
        with state_lock:
            auth_state["status"] = "LISTENING"
            auth_state["recognized_text"] = ""
            save_state()
        
        # 3. 마이크 녹음 (5초)
        audio_data, sample_rate = record_audio(duration=5.0)
        
        # 4. 상태 변경: PROCESSING
        with state_lock:
            auth_state["status"] = "PROCESSING"
            save_state()
        
        # 5. STT
        recognized = speech_to_text(audio_data, rate=sample_rate)
        print(f" [시나리오] 인식된 텍스트: '{recognized}'", flush=True)
        
        with state_lock:
            auth_state["recognized_text"] = recognized
        
        # 6. 시나리오 시스템에 자동 제출
        if recognized.strip():
            scenario_result = submit_to_scenario(recognized.strip())
            print(f" [시나리오] 제출 결과: {scenario_result}", flush=True)
        else:
            print(" [시나리오] 인식된 텍스트 없음 - 시나리오 제출 건너뜀", flush=True)
        
        # 7. 암구호 비교
        is_match = check_passphrase(recognized, answer)
        
        # 8. 결과 처리
        with state_lock:
            if is_match:
                auth_state["status"] = "SUCCESS"
                auth_state["last_result"] = True
            else:
                auth_state["status"] = "FAILED"
                auth_state["last_result"] = False
            save_state()
        
        # 9. IDLE로 복귀 + scenario_locked 해제
        with state_lock:
            auth_state["status"] = "IDLE"
            auth_state["scenario_locked"] = False  # 시나리오 락 해제
            save_state()
        print(" [시나리오] 음성 인증 완료, 보이스 패널 락 해제", flush=True)
            
    except Exception as e:
        print(f"[시나리오] 인증 프로세스 오류: {e}")
        with state_lock:
            auth_state["status"] = "ERROR"
            auth_state["recognized_text"] = str(e)
            auth_state["scenario_locked"] = False  # 에러 시에도 락 해제
            save_state()
        
        time.sleep(1)
        with state_lock:
            auth_state["status"] = "IDLE"
            save_state()


# ==================== Endpoints ====================

@router.get("/status")
def get_voice_auth_status():
    """음성 인증 상태 조회"""
    with state_lock:
        return {
            "enabled": auth_state.get("enabled", True),
            "status": auth_state.get("status", "IDLE"),
            "question": auth_state.get("question", "까마귀"),
            "answer": auth_state.get("answer", "백두산"),
            "recognized_text": auth_state.get("recognized_text", ""),
            "last_result": auth_state.get("last_result"),
            "voice_auth_running": True  # 백엔드에서 직접 처리하므로 항상 True
        }


@router.post("/reset")
def reset_voice_state():
    """Voice 상태 강제 리셋 (시나리오 리셋 시 호출)"""
    with state_lock:
        auth_state["status"] = "IDLE"
        auth_state["recognized_text"] = ""
        auth_state["last_result"] = None
        auth_state["scenario_locked"] = False  # 시나리오 락도 해제
        save_state()
    
    return {"success": True, "message": "Voice 상태 리셋됨"}


@router.post("/passphrase")
def set_passphrase(req: PassphraseRequest):
    """암구호 설정 변경"""
    with state_lock:
        auth_state["question"] = req.question
        auth_state["answer"] = req.answer
        save_state()
    
    return {
        "success": True,
        "question": req.question,
        "answer": req.answer
    }


@router.post("/request-auth")
async def request_auth(req: AuthRequest):
    """
    암구호 인증 요청 (보이스 패널용 - 시나리오 진행 중 차단됨)
    
    백그라운드에서 TTS → 마이크 녹음 → STT → 판정 진행
    """
    with state_lock:
        # 시나리오가 사용 중이면 차단
        if auth_state.get("scenario_locked", False):
            return {"success": False, "error": "시나리오 진행 중 - 보이스 패널 사용 불가"}
        if auth_state["status"] != "IDLE":
            return {"success": False, "error": "이미 인증 진행 중"}
        auth_state["status"] = "PROCESSING"
        save_state()
    
    # threading으로 백그라운드 실행 (BackgroundTasks 대신)
    voice_id = ELEVENLABS_VOICE_IDS.get(req.voice, DEFAULT_VOICE_ID)
    thread = threading.Thread(target=run_auth_process, args=(req.timeout_sec, voice_id), daemon=True)
    thread.start()
    
    return {"success": True, "message": "인증 시작됨"}


@router.post("/scenario-request-auth")
async def scenario_request_auth(req: AuthRequest):
    """
    암구호 인증 요청 (시나리오 전용 - 우선순위 높음)
    
    시나리오에서만 호출. scenario_locked 플래그 설정하여 보이스 패널 차단
    """
    with state_lock:
        if auth_state["status"] != "IDLE":
            return {"success": False, "error": "이미 인증 진행 중"}
        auth_state["status"] = "PROCESSING"
        auth_state["scenario_locked"] = True  # 시나리오 전용 락
        save_state()
    
    # threading으로 백그라운드 실행
    voice_id = ELEVENLABS_VOICE_IDS.get(req.voice, DEFAULT_VOICE_ID)
    thread = threading.Thread(target=run_auth_process_for_scenario, args=(req.timeout_sec, voice_id), daemon=True)
    thread.start()
    
    return {"success": True, "message": "시나리오 인증 시작됨"}


@router.post("/speak")
def speak_text(req: TTSRequest):
    """
    텍스트를 음성으로 변환하여 서버 스피커로 재생 (ElevenLabs)
    """
    voice_id = ELEVENLABS_VOICE_IDS.get(req.voice, DEFAULT_VOICE_ID)
    success = elevenlabs_speak(req.text, voice_id)
    
    return {"success": success}


@router.post("/tts")
def get_tts_audio(req: TTSRequest):
    """
    텍스트를 음성으로 변환하여 오디오 스트림 반환 (웹 브라우저 재생용)
    """
    try:
        from elevenlabs import ElevenLabs
        
        client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
        voice_id = ELEVENLABS_VOICE_IDS.get(req.voice, DEFAULT_VOICE_ID)
        
        audio = client.text_to_speech.convert(
            voice_id=voice_id,
            model_id="eleven_multilingual_v2",
            text=req.text
        )
        
        audio_bytes = b"".join(audio)
        
        return StreamingResponse(
            io.BytesIO(audio_bytes),
            media_type="audio/mpeg",
            headers={"Content-Disposition": "inline; filename=speech.mp3"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/voices")
def get_available_voices():
    """사용 가능한 ElevenLabs 음성 목록"""
    return {
        "voices": [
            {"id": "eric", "name": "Eric", "description": "남성 (기본)"},
            {"id": "chris", "name": "Chris", "description": "남성 - 친근한"},
            {"id": "sarah", "name": "Sarah", "description": "여성 - 차분한"},
            {"id": "jessica", "name": "Jessica", "description": "여성 - 밝은"},
        ]
    }


# ==================== Legacy Endpoints ====================

class VoiceRequest(BaseModel):
    is_ally: bool


@router.post("/classify")
def speak_classify(req: VoiceRequest):
    """아군/적군 판정 결과 음성"""
    if req.is_ally:
        text = "아군으로 확인되었습니다. 통과하십시오."
    else:
        text = "적군으로 확인되었습니다. 정지하십시오!"
    
    success = elevenlabs_speak(text)
    return {"success": success}


@router.post("/ask-password")
def ask_password():
    """암구호 질문 음성"""
    with state_lock:
        question = auth_state.get("question", "까마귀")
    
    text = f"정지! 암구호! {question}!"
    success = elevenlabs_speak(text)
    return {"success": success}


@router.post("/password-result")
def password_result(correct: bool = True):
    """암구호 결과 음성"""
    if correct:
        text = "암구호 일치. 통과하십시오."
    else:
        text = "암구호 불일치. 정지하십시오!"
    
    success = elevenlabs_speak(text)
    return {"success": success}


class WelcomeRequest(BaseModel):
    name: Optional[str] = None


@router.post("/welcome")
def welcome(req: WelcomeRequest = None):
    """환영 인사"""
    name = req.name if req else None
    if name:
        text = f"{name}님, 환영합니다. 통과하십시오."
    else:
        text = "환영합니다. 통과하십시오."
    
    success = elevenlabs_speak(text)
    return {"success": success}


@router.post("/access-denied")
def access_denied():
    """출입 거부 음성"""
    text = "출입이 거부되었습니다. 정지하십시오!"
    success = elevenlabs_speak(text)
    return {"success": success}


def run_listen_only_process(timeout_sec: float = 3.5):
    """
    음성 인식만 수행 (TTS 없이) - 시나리오에서 호출용
    
    1. 마이크 녹음
    2. STT로 텍스트 변환
    3. 시나리오에 자동 제출
    """
    global auth_state
    
    try:
        with state_lock:
            answer = auth_state["answer"]
        
        # 1. 상태 변경: LISTENING
        with state_lock:
            auth_state["status"] = "LISTENING"
            auth_state["recognized_text"] = ""
            save_state()
        
        # 2. 마이크 녹음
        audio_data, sample_rate = record_audio(duration=timeout_sec)
        
        # 3. 상태 변경: PROCESSING
        with state_lock:
            auth_state["status"] = "PROCESSING"
            save_state()
        
        # 4. STT
        recognized = speech_to_text(audio_data, rate=sample_rate)
        print(f" [자동인식] 인식된 텍스트: {recognized}")
        
        with state_lock:
            auth_state["recognized_text"] = recognized
        
        # 5. 시나리오 시스템에 자동 제출 (인식된 텍스트가 있으면)
        if recognized.strip():
            scenario_result = submit_to_scenario(recognized.strip())
            print(f" [자동인식] 시나리오 제출 결과: {scenario_result}")
        else:
            print(" [자동인식] 인식된 텍스트 없음 - 제출 스킵")
        
        # 6. 암구호 비교 (로컬 확인용)
        is_match = check_passphrase(recognized, answer) if recognized else False
        
        # 7. 결과 처리
        with state_lock:
            if is_match:
                auth_state["status"] = "SUCCESS"
                auth_state["last_result"] = True
            else:
                auth_state["status"] = "FAILED"
                auth_state["last_result"] = False
            save_state()
        
        # 8. 잠시 후 IDLE로 복귀
        time.sleep(2)
        with state_lock:
            auth_state["status"] = "IDLE"
            save_state()
            
        return recognized
            
    except Exception as e:
        print(f"[자동인식] 오류: {e}")
        with state_lock:
            auth_state["status"] = "ERROR"
            auth_state["recognized_text"] = str(e)
            save_state()
        
        time.sleep(3)
        with state_lock:
            auth_state["status"] = "IDLE"
            save_state()
        
        return ""


@router.post("/listen-only")
async def listen_only(background_tasks: BackgroundTasks, timeout_sec: float = 3.5):
    """
    TTS 없이 음성 인식만 시작 (시나리오에서 호출용)
    """
    with state_lock:
        if auth_state["status"] != "IDLE":
            return {"success": False, "error": "이미 인식 진행 중"}
        auth_state["status"] = "PROCESSING"
        save_state()
    
    # 백그라운드에서 음성 인식 실행
    background_tasks.add_task(run_listen_only_process, timeout_sec)
    
    return {"success": True, "message": "음성 인식 시작됨"}
