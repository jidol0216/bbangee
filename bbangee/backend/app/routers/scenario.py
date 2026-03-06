"""
시나리오 State Machine - 초병 로봇 대응 시퀀스

상태 흐름:
  IDLE → DETECTED → IDENTIFY → PASSWORD_CHECK →
    ├─ ALLY_PASS (아군 통과)
    ├─ ALLY_ALERT (아군 오답)
    ├─ ENEMY_CRITICAL (적군 정답 - 기밀유출)
    └─ ENEMY_ENGAGE (적군 오답 - 대응)

리팩토링:
  - HTTP 자기호출 → 서비스 직접 호출
  - MOTIONS 복붙 → robot_motions 모듈 import
  - _write_command 복붙 → ros2_bridge 모듈 import
  - God Class → 상태머신 로직만 유지, 하드웨어 제어는 서비스 위임
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Optional, List
from enum import Enum
from datetime import datetime
import asyncio
import json
import threading

# 서비스 모듈 직접 import (HTTP 자기호출 제거!)
from app.services import tts_service, audio_service, device_control
from app.services.robot_motions import execute_motion
from app.services.ros2_bridge import send_robot_command, send_tracking_speed, write_command

router = APIRouter(prefix="/scenario", tags=["Scenario"])


# ============================================
# 상태 정의
# ============================================

class ScenarioState(str, Enum):
    IDLE = "IDLE"
    DETECTED = "DETECTED"
    IDENTIFY = "IDENTIFY"
    PASSWORD_CHECK = "PASSWORD_CHECK"
    ALLY_PASS = "ALLY_PASS"
    ALLY_ALERT = "ALLY_ALERT"
    ENEMY_CRITICAL = "ENEMY_CRITICAL"
    ENEMY_ENGAGE = "ENEMY_ENGAGE"


class PersonType(str, Enum):
    UNKNOWN = "UNKNOWN"
    ALLY = "ALLY"
    ENEMY = "ENEMY"


# ============================================
# 시나리오 상태 관리
# ============================================

class ScenarioManager:
    def __init__(self):
        self.state = ScenarioState.IDLE
        self.person_type: PersonType = PersonType.UNKNOWN
        self.detection_time: Optional[datetime] = None
        self.history: List[dict] = []
        self.websockets: List[WebSocket] = []

        # 암구호 문답식
        from app.services.config import DEFAULT_PASSWORD_CHALLENGE, DEFAULT_PASSWORD_RESPONSE
        self.password_challenge = DEFAULT_PASSWORD_CHALLENGE
        self.password_response = DEFAULT_PASSWORD_RESPONSE

        # 서버 시작 시 Voice API와 암구호 동기화
        self._init_sync_voice_passphrase()

        # OCR 자동 피아식별 설정
        self.ocr_ally_count = 0
        self.ocr_enemy_count = 0
        self.ocr_confidence_threshold = 0.3
        self.ocr_fail_count = 0
        self.ocr_fail_tts_threshold = 15
        self.ocr_fail_tts_played = False
        self.ocr_locked = False
        self.ocr_locked_faction = None
        self.ocr_timeout = 30.0

        # 상태 전이 지연 설정
        self.delay_after_detect = 0.3
        self.delay_after_identify = 5.0

    # ========================================
    # 암구호 관리
    # ========================================

    def set_password(self, challenge: str, response: str = None) -> dict:
        old_c, old_r = self.password_challenge, self.password_response
        self.password_challenge = challenge.strip()
        if response:
            self.password_response = response.strip()

        self._sync_voice_passphrase()
        self._add_history(
            f"암구호 변경: {old_c}/{old_r} → {self.password_challenge}/{self.password_response}"
        )
        return {"success": True, "challenge": self.password_challenge, "response": self.password_response}

    def _sync_voice_passphrase(self):
        """Voice 모듈의 auth_state 와 암구호 동기화 (직접 참조)"""
        try:
            from app.routers.voice import set_passphrase_internal
            set_passphrase_internal(self.password_challenge, self.password_response)
            print(f" Voice 암구호 동기화: {self.password_challenge} → {self.password_response}")
        except Exception as e:
            print(f"Voice 동기화 실패: {e}")

    def _init_sync_voice_passphrase(self):
        def delayed_sync():
            import time
            time.sleep(3)
            self._sync_voice_passphrase()
        threading.Thread(target=delayed_sync, daemon=True).start()

    def get_password(self) -> dict:
        return {"challenge": self.password_challenge, "response": self.password_response}

    # ========================================
    # 상태 조회
    # ========================================

    def get_status(self) -> dict:
        return {
            "state": self.state.value,
            "person_type": self.person_type.value,
            "detection_time": self.detection_time.isoformat() if self.detection_time else None,
            "history": self.history[-10:],
            "available_actions": self._get_available_actions(),
            "password_challenge": self.password_challenge,
            "password_response": self.password_response,
        }

    def _get_available_actions(self) -> List[str]:
        actions = {
            ScenarioState.IDLE: ["detect"],
            ScenarioState.DETECTED: ["identify_ally", "identify_enemy", "reset"],
            ScenarioState.IDENTIFY: ["check_password", "reset"],
            ScenarioState.PASSWORD_CHECK: ["submit_password", "reset"],
            ScenarioState.ALLY_PASS: ["reset"],
            ScenarioState.ALLY_ALERT: ["reset"],
            ScenarioState.ENEMY_CRITICAL: ["reset"],
            ScenarioState.ENEMY_ENGAGE: ["reset"],
        }
        return actions.get(self.state, ["reset"])

    def _add_history(self, event: str):
        self.history.append({
            "time": datetime.now().isoformat(),
            "state": self.state.value,
            "event": event,
        })

    async def broadcast(self, data: dict):
        for ws in self.websockets[:]:
            try:
                await ws.send_json(data)
            except Exception:
                self.websockets.remove(ws)

    # ========================================
    # 상태 전이 메서드
    # ========================================

    async def on_face_detected(self) -> dict:
        if self.state != ScenarioState.IDLE:
            return {"success": False, "message": "이미 감지 상태입니다"}

        self.state = ScenarioState.DETECTED
        self.detection_time = datetime.now()
        self.person_type = PersonType.UNKNOWN
        self._add_history("접근자 감지됨")

        # OCR 비활성화 → TTS → OCR 활성화  (직접 호출!)
        self._set_ocr_enabled(False)

        await self._speak("정지! 신원을 확인합니다.")
        await asyncio.sleep(self.delay_after_detect)
        await self._speak("접근자 얼굴 감지. 식별 시퀀스 진행.")

        self._set_ocr_enabled(True)

        await self.broadcast({
            "type": "state_change",
            "state": self.state.value,
            "message": "접근자 감지! 피아식별 필요",
            "popup": {"show": False},
        })
        return {"success": True, "state": self.state.value}

    async def identify_person(self, is_ally: bool) -> dict:
        if self.state != ScenarioState.DETECTED:
            return {"success": False, "message": "감지 상태가 아닙니다"}

        self._set_ocr_enabled(False)

        self.person_type = PersonType.ALLY if is_ally else PersonType.ENEMY
        self.state = ScenarioState.PASSWORD_CHECK

        person_str = "아군" if is_ally else "적군"
        self._add_history(f"{person_str}으로 식별")

        if is_ally:
            send_robot_command("stop")
            await asyncio.sleep(0.5)
            execute_motion("high_ready")

        await self.broadcast({
            "type": "state_change",
            "state": self.state.value,
            "person_type": self.person_type.value,
            "message": f"{person_str} 식별됨 - 암구호 확인 중",
            "popup": {"show": False},
        })

        # 음성 인증 시작 (직접 호출!)
        self._start_voice_auth()
        return {"success": True, "state": self.state.value, "person_type": self.person_type.value}

    async def submit_password(self, password: str) -> dict:
        if self.state != ScenarioState.PASSWORD_CHECK:
            return {"success": False, "message": "암구호 확인 상태가 아닙니다"}

        is_correct = password.strip() == self.password_response

        if self.person_type == PersonType.ALLY:
            if is_correct:
                self.state = ScenarioState.ALLY_PASS
                self._add_history("아군 암구호 정답 - 통과 승인")
                result_msg, alert_level = " 아군 통과 승인", "success"
                execute_motion("salute")
                await self._speak("충성!")
            else:
                self.state = ScenarioState.ALLY_ALERT
                self._add_history("아군 암구호 오답 - 경고")
                result_msg, alert_level = " 아군 암구호 오답 - 경고 발령", "warning"
                execute_motion("high_ready")
                await self._speak("암구호가 틀렸습니다. 움직이지 마세요.")
        else:  # ENEMY
            if is_correct:
                self.state = ScenarioState.ENEMY_CRITICAL
                self._add_history("적군 암구호 정답 - 기밀유출 의심")
                result_msg, alert_level = " 적군이 암구호 정답 - 기밀유출!", "critical"
                await self._play_enemy_critical_alert()
            else:
                self.state = ScenarioState.ENEMY_ENGAGE
                self._add_history("적군 암구호 오답 - 대응")
                result_msg, alert_level = " 적군 대응 - 침입자!", "danger"

                await asyncio.sleep(1.0)
                device_control.control_servo(True)
                await self._play_enemy_engage_alert()

            send_tracking_speed(1.5)
            send_tracking_speed(1.5)

        await self.broadcast({
            "type": "scenario_result",
            "state": self.state.value,
            "message": result_msg,
            "alert_level": alert_level,
            "is_correct": is_correct,
            "spoken_password": password,
        })
        return {"success": True, "state": self.state.value, "is_correct": is_correct, "message": result_msg}

    # ========================================
    # OCR 처리
    # ========================================

    async def process_ocr_result(self, armband_detected: bool, faction: str, confidence: float) -> dict:
        if self.state != ScenarioState.DETECTED:
            return {"success": False, "message": "DETECTED 상태가 아닙니다"}

        if self.ocr_locked and self.ocr_locked_faction:
            return {"success": True, "action": "locked", "faction": self.ocr_locked_faction}

        if not armband_detected:
            return {"success": True, "action": "waiting", "message": "완장 감지 대기 중"}

        if faction in ["UNKNOWN", "ERROR", ""]:
            self.ocr_fail_count += 1
            if self.ocr_fail_count >= self.ocr_fail_tts_threshold and not self.ocr_fail_tts_played:
                if self.state != ScenarioState.DETECTED:
                    return {"success": False, "message": "상태가 변경되어 OCR 무시"}
                self.ocr_fail_tts_played = True
                self._add_history("OCR 실패 반복")
                await self.broadcast({"type": "ocr_guide", "message": "OCR 인식 대기 중"})
            return {"success": True, "action": "waiting", "message": "OCR 인식 대기 중"}

        # OCR 성공 → 누적
        if faction == "ALLY" and confidence >= self.ocr_confidence_threshold:
            self.ocr_ally_count += 1
        elif faction == "ENEMY" and confidence >= self.ocr_confidence_threshold:
            self.ocr_enemy_count += 1

        await self.broadcast({
            "type": "ocr_update",
            "ally_count": self.ocr_ally_count,
            "enemy_count": self.ocr_enemy_count,
            "last_faction": faction,
            "confidence": confidence,
        })

        if self.ocr_ally_count > 0 or self.ocr_enemy_count > 0:
            if self.ocr_ally_count > self.ocr_enemy_count:
                final_faction = "ALLY"
            elif self.ocr_enemy_count > self.ocr_ally_count:
                final_faction = "ENEMY"
            else:
                final_faction = faction

            self.ocr_locked = True
            self.ocr_locked_faction = final_faction
            self.ocr_fail_count = 0

            is_ally = (final_faction == "ALLY")
            self._add_history(f"OCR 자동 피아식별: {final_faction}")
            result = await self.identify_person(is_ally)
            result["auto_identified"] = True
            result["ocr_locked"] = True
            return result

        return {"success": True, "action": "waiting", "message": "OCR 인식 대기 중"}

    # ========================================
    # 리셋
    # ========================================

    async def reset(self) -> dict:
        self.state = ScenarioState.IDLE
        self.person_type = PersonType.UNKNOWN
        self.detection_time = None
        self.ocr_ally_count = 0
        self.ocr_enemy_count = 0
        self.ocr_fail_count = 0
        self.ocr_fail_tts_played = False
        self.ocr_locked = False
        self.ocr_locked_faction = None
        self._add_history("시나리오 리셋")

        # 서비스 직접 호출 (HTTP 자기호출 제거!)
        self._set_ocr_enabled(False)
        self._reset_voice_state()
        send_tracking_speed(1.0)
        device_control.control_servo(False)
        device_control.control_laser(False)

        await self.broadcast({"type": "reset", "state": self.state.value, "message": "시나리오 초기화됨"})
        return {"success": True, "state": self.state.value}

    # ========================================
    # 하드웨어 제어 헬퍼 (HTTP → 직접 호출)
    # ========================================

    def _set_ocr_enabled(self, enabled: bool):
        """armband 모듈의 OCR 상태 직접 변경"""
        try:
            from app.routers.armband import set_ocr_enabled_internal
            set_ocr_enabled_internal(enabled)
            print(f" OCR {'활성화' if enabled else '비활성화'}")
        except Exception as e:
            print(f"OCR 상태 변경 실패: {e}")

    async def _speak(self, text: str, voice: str = "eric"):
        """TTS 재생 (서비스 직접 호출)"""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, tts_service.speak, text, voice)
        await asyncio.sleep(0.5)

    def _start_voice_auth(self, timeout_sec: float = 5.0):
        """음성 인증 시작 (voice 모듈 직접 호출)"""
        try:
            from app.routers.voice import start_scenario_auth_internal
            start_scenario_auth_internal(timeout_sec, "eric")
            print(" [시나리오] 음성 인증 시작")
        except Exception as e:
            print(f"[시나리오] 음성 인증 시작 실패: {e}")

    def _reset_voice_state(self):
        """Voice 상태 리셋 (직접 호출)"""
        try:
            from app.routers.voice import reset_voice_internal
            reset_voice_internal()
            print(" Voice 상태 리셋")
        except Exception as e:
            print(f"Voice 상태 리셋 실패: {e}")

    async def _play_enemy_critical_alert(self):
        await self._speak("경고! 기밀 유출 의심! 비상 알림 발령!")
        await asyncio.sleep(2.5)
        audio_service.play_alert_buzzer("warning")
        await asyncio.sleep(0.3)
        await self._speak("경고! 경고! 경고!")

    async def _play_enemy_engage_alert(self):
        await self._speak("코드 레드 발령, 코드 레드 발령, 침입자 대응 조치할 것!")
        await asyncio.sleep(2.5)
        audio_service.play_alert_buzzer("critical")
        await asyncio.sleep(9)
        device_control.control_servo(False)
        print(" 서보 OFF (사이렌 종료)")


# 싱글톤
scenario_manager = ScenarioManager()


# ============================================
# API 엔드포인트
# ============================================

class IdentifyRequest(BaseModel):
    is_ally: bool

class PasswordRequest(BaseModel):
    password: str

class SetPasswordRequest(BaseModel):
    challenge: str
    response: str = None

class OcrResultRequest(BaseModel):
    armband_detected: bool
    faction: str
    confidence: float


@router.get("/status")
async def get_status():
    return scenario_manager.get_status()

@router.post("/detect")
async def face_detected():
    return await scenario_manager.on_face_detected()

@router.post("/identify")
async def identify_person(req: IdentifyRequest):
    return await scenario_manager.identify_person(req.is_ally)

@router.post("/password")
async def submit_password(req: PasswordRequest):
    return await scenario_manager.submit_password(req.password)

@router.post("/reset")
async def reset_scenario():
    return await scenario_manager.reset()

@router.post("/ocr")
async def process_ocr(req: OcrResultRequest):
    return await scenario_manager.process_ocr_result(
        armband_detected=req.armband_detected,
        faction=req.faction,
        confidence=req.confidence,
    )

@router.get("/password")
async def get_password():
    return scenario_manager.get_password()

@router.post("/password/set")
async def set_password(req: SetPasswordRequest):
    if not req.challenge.strip():
        return {"success": False, "message": "질문 암구호는 빈 값일 수 없습니다"}
    return scenario_manager.set_password(req.challenge, req.response)


# ============================================
# WebSocket
# ============================================

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    scenario_manager.websockets.append(websocket)
    await websocket.send_json({"type": "init", **scenario_manager.get_status()})
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        scenario_manager.websockets.remove(websocket)
