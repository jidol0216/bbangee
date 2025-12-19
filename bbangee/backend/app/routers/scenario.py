"""
시나리오 State Machine - 초병 로봇 대응 시퀀스

상태 흐름:
  IDLE → DETECTED → IDENTIFY → PASSWORD_CHECK → 
    ├─ ALLY_PASS (아군 통과)
    ├─ ALLY_ALERT (아군 오답)
    ├─ ENEMY_CRITICAL (적군 정답 - 기밀유출)
    └─ ENEMY_ENGAGE (적군 오답 - 대응)
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Optional, List
from enum import Enum
from datetime import datetime
import asyncio
import json

router = APIRouter(prefix="/scenario", tags=["Scenario"])

# ============================================
# 상태 정의
# ============================================

class ScenarioState(str, Enum):
    IDLE = "IDLE"                    # 초기 경계
    DETECTED = "DETECTED"            # 접근자 감지
    IDENTIFY = "IDENTIFY"            # 피아식별 대기
    PASSWORD_CHECK = "PASSWORD_CHECK" # 암구호 확인 중
    ALLY_PASS = "ALLY_PASS"          # 아군 통과 승인
    ALLY_ALERT = "ALLY_ALERT"        # 아군 암구호 오답
    ENEMY_CRITICAL = "ENEMY_CRITICAL" # 적군 암구호 정답 (기밀유출)
    ENEMY_ENGAGE = "ENEMY_ENGAGE"    # 적군 대응


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
        # 암구호 문답식 (Challenge-Response)
        self.password_challenge = "로키"  # 로봇이 물어보는 질문
        self.password_response = "협동"   # 사용자가 답해야 하는 응답
        
        # 서버 시작 시 Voice API와 암구호 동기화
        self._init_sync_voice_passphrase()
        
        # OCR 자동 피아식별 설정 (누적 방식)
        self.ocr_ally_count = 0             # "아군" 인식 횟수 (누적)
        self.ocr_enemy_count = 0            # "적군" 인식 횟수 (누적)
        self.ocr_confidence_threshold = 0.3 # 자동 식별에 필요한 최소 신뢰도 (낮춤)
        self.ocr_fail_count = 0             # 완장 감지 O, OCR 실패 카운트
        self.ocr_fail_tts_threshold = 15    # OCR 실패 TTS 안내 임계값
        self.ocr_fail_tts_played = False    # OCR 실패 TTS 재생 여부
        self.ocr_locked = False             # OCR 결과 락 여부
        self.ocr_locked_faction = None      # 락된 OCR 결과
        self.ocr_timeout = 30.0             # OCR 인식 타임아웃 (초)
        
        # 상태 전이 지연 설정 (사람 연기 시간 확보)
        self.delay_after_detect = 0.3       # 얼굴 감지 후 TTS 완료 대기 (초)
        self.delay_after_identify = 5.0     # 피아식별 후 암구호 TTS 대기 (초)
    
    def set_password(self, challenge: str, response: str = None) -> dict:
        """암구호 변경 (문답식) - Voice API와 동기화"""
        old_challenge = self.password_challenge
        old_response = self.password_response
        
        self.password_challenge = challenge.strip()
        if response:
            self.password_response = response.strip()
        
        # Voice API 암구호도 동기화
        self._sync_voice_passphrase()
        
        self._add_history(f"암구호 변경: {old_challenge}/{old_response} → {self.password_challenge}/{self.password_response}")
        return {
            "success": True, 
            "challenge": self.password_challenge,
            "response": self.password_response
        }
    
    def _sync_voice_passphrase(self):
        """Voice API 암구호와 동기화"""
        try:
            import requests
            requests.post(
                "http://localhost:8000/voice/passphrase",
                json={"question": self.password_challenge, "answer": self.password_response},
                timeout=1.0
            )
            print(f"🔄 Voice API 암구호 동기화: {self.password_challenge} → {self.password_response}")
        except Exception as e:
            print(f"Voice API 동기화 실패: {e}")
    
    def _init_sync_voice_passphrase(self):
        """서버 시작 시 Voice API 암구호 초기화 (지연 실행)"""
        import threading
        def delayed_sync():
            import time
            time.sleep(3)  # 서버 완전히 시작된 후 동기화
            self._sync_voice_passphrase()
        
        thread = threading.Thread(target=delayed_sync, daemon=True)
        thread.start()
    
    def get_password(self) -> dict:
        """현재 암구호 조회"""
        return {
            "challenge": self.password_challenge,
            "response": self.password_response
        }
    
    def get_status(self) -> dict:
        return {
            "state": self.state.value,
            "person_type": self.person_type.value,
            "detection_time": self.detection_time.isoformat() if self.detection_time else None,
            "history": self.history[-10:],  # 최근 10개
            "available_actions": self._get_available_actions(),
            "password_challenge": self.password_challenge,
            "password_response": self.password_response,
        }
    
    def _get_available_actions(self) -> List[str]:
        """현재 상태에서 가능한 액션"""
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
            "event": event
        })
    
    async def broadcast(self, data: dict):
        """모든 WebSocket 클라이언트에 브로드캐스트"""
        for ws in self.websockets[:]:
            try:
                await ws.send_json(data)
            except:
                self.websockets.remove(ws)
    
    # ========================================
    # 상태 전이 메서드
    # ========================================
    
    async def on_face_detected(self) -> dict:
        """얼굴 감지됨"""
        if self.state != ScenarioState.IDLE:
            return {"success": False, "message": "이미 감지 상태입니다"}
        
        self.state = ScenarioState.DETECTED
        self.detection_time = datetime.now()
        self.person_type = PersonType.UNKNOWN
        self._add_history("접근자 감지됨")
        
        # OCR 비활성화 (검은 화면 유지)
        await self._set_ocr_enabled(False)
        
        # TTS 1: 정지 명령
        await self._play_tts("정지! 신원을 확인합니다.")
        
        # TTS 완료 대기
        await asyncio.sleep(self.delay_after_detect)
        
        # TTS 2: 식별 시퀀스 안내
        await self._play_tts("접근자 얼굴 감지. 식별 시퀀스 진행.")
        
        # OCR 활성화 (이제 RAW/ROI 화면 표시됨)
        await self._set_ocr_enabled(True)
        
        # 0.5초 후 피아식별띠 안내 TTS
        await asyncio.sleep(0.5)
        await self._play_tts("카메라 렌즈에 피아식별띠를 위치시키십시오.")
        
        # 브로드캐스트
        await self.broadcast({
            "type": "state_change",
            "state": self.state.value,
            "message": "접근자 감지! 피아식별 필요",
            "popup": {
                "show": False,  # 팝업 비활성화
                "title": "⚠️ 접근자 감지",
                "message": "아군/적군을 판정해주세요",
                "buttons": ["아군", "적군"]
            }
        })
        
        return {"success": True, "state": self.state.value}
    
    async def identify_person(self, is_ally: bool) -> dict:
        """피아 식별"""
        if self.state != ScenarioState.DETECTED:
            return {"success": False, "message": "감지 상태가 아닙니다"}
        
        # 🔒 OCR 비활성화 (피아식별 완료 후 더 이상 OCR 불필요)
        await self._set_ocr_enabled(False)
        
        self.person_type = PersonType.ALLY if is_ally else PersonType.ENEMY
        self.state = ScenarioState.PASSWORD_CHECK
        
        person_str = "아군" if is_ally else "적군"
        self._add_history(f"{person_str}으로 식별")
        
        # 아군이면: 추적 중지 → High Ready 자세로 전환
        if is_ally:
            await self._send_tracking_stop()  # 추적 중지
            await asyncio.sleep(0.5)  # 잠시 대기
            await self._execute_robot_motion("high_ready")
        
        # 브로드캐스트
        await self.broadcast({
            "type": "state_change",
            "state": self.state.value,
            "person_type": self.person_type.value,
            "message": f"{person_str} 식별됨 - 암구호 확인 중",
            "popup": {
                "show": False,  # 팝업 비활성화
                "title": f"🔒 암구호: {self.password_challenge}!",
                "message": "응답 암구호를 입력하세요",
                "input": True
            }
        })
        
        # 🎤 자동 음성 인식 시작 (Voice Panel 방식: TTS + 녹음 + STT + 제출)
        await self._start_voice_auth()
        
        return {"success": True, "state": self.state.value, "person_type": self.person_type.value}
    
    async def submit_password(self, password: str) -> dict:
        """암구호 응답 제출"""
        if self.state != ScenarioState.PASSWORD_CHECK:
            return {"success": False, "message": "암구호 확인 상태가 아닙니다"}
        
        # 응답 암구호와 비교
        is_correct = password.strip() == self.password_response
        robot_motion = None  # 실행할 로봇 모션
        
        # 분기 처리
        if self.person_type == PersonType.ALLY:
            if is_correct:
                self.state = ScenarioState.ALLY_PASS
                self._add_history("아군 암구호 정답 - 통과 승인")
                result_msg = "✅ 아군 통과 승인"
                alert_level = "success"
                robot_motion = "salute"  # 경례 모션으로 시나리오 종료
                # 경례 모션 먼저 실행 후 TTS
                await self._execute_robot_motion(robot_motion)
                await self._play_tts("충성!")
                robot_motion = None  # 이미 실행함
            else:
                self.state = ScenarioState.ALLY_ALERT
                self._add_history("아군 암구호 오답 - 경고")
                result_msg = "⚠️ 아군 암구호 오답 - 경고 발령"
                alert_level = "warning"
                robot_motion = "high_ready"  # High Ready 유지
                await self._execute_robot_motion(robot_motion)
                await self._play_tts("암구호가 틀렸습니다. 움직이지 마세요.")
                robot_motion = None  # 이미 실행함
        else:  # ENEMY
            if is_correct:
                self.state = ScenarioState.ENEMY_CRITICAL
                self._add_history("적군 암구호 정답 - 기밀유출 의심")
                await self._play_enemy_critical_alert()  # TTS + 경고음 + "경고! 경고! 경고!"
                result_msg = "🚨 적군이 암구호 정답 - 기밀유출!"
                alert_level = "critical"
            else:
                self.state = ScenarioState.ENEMY_ENGAGE
                self._add_history("적군 암구호 오답 - 대응")
                
                # 🔫 1초 후 서보 ON (조준 자세)
                await asyncio.sleep(1.0)
                await self._control_device("servo", True)
                
                await self._play_enemy_engage_alert()  # 사이렌 + "코드 레드 발령..."
                result_msg = "🔴 적군 대응 - 침입자!"
                alert_level = "danger"
            
            # 적군: 추적 속도 증가 (더 빠르게 추적)
            await self._send_tracking_speed_boost()
            await self._send_tracking_speed_boost()
        
        # 아군만 로봇 모션 실행
        if robot_motion:
            await self._execute_robot_motion(robot_motion)
        
        # 브로드캐스트
        await self.broadcast({
            "type": "scenario_result",
            "state": self.state.value,
            "message": result_msg,
            "alert_level": alert_level,
            "is_correct": is_correct,
            "spoken_password": password  # 제출된 암구호
        })
        
        return {
            "success": True,
            "state": self.state.value,
            "is_correct": is_correct,
            "message": result_msg
        }
    
    async def _send_tracking_speed_boost(self):
        """추적 속도 증가 명령 전송"""
        import time as time_module
        
        command = {
            'type': 'robot_command',
            'timestamp': time_module.time(),
            'data': {
                'command': 'speed_boost',
                'speed_multiplier': 1.5  # 1.5배 빠르게
            }
        }
        
        command_file = '/tmp/ros2_bridge_command.json'
        try:
            with open(command_file, 'w') as f:
                json.dump(command, f)
            print("⚡ 추적 속도 증가 명령 전송")
            self._add_history("추적 속도 증가")
        except Exception as e:
            print(f"추적 속도 증가 명령 전송 실패: {e}")
    
    async def _send_tracking_speed_reset(self):
        """추적 속도 초기화 명령 전송"""
        import time as time_module
        
        command = {
            'type': 'robot_command',
            'timestamp': time_module.time(),
            'data': {
                'command': 'speed_boost',
                'speed_multiplier': 1.0  # 기본 속도로 복귀
            }
        }
        
        command_file = '/tmp/ros2_bridge_command.json'
        try:
            with open(command_file, 'w') as f:
                json.dump(command, f)
            print("🔄 추적 속도 초기화")
        except Exception as e:
            print(f"추적 속도 초기화 실패: {e}")
    
    async def process_ocr_result(self, armband_detected: bool, faction: str, confidence: float) -> dict:
        """
        OCR 결과 처리 및 자동 피아식별 (누적 방식)
        
        - 한 번이라도 "아군" 인식 → ALLY로 픽스
        - 한 번이라도 "적군" 인식 → ENEMY로 픽스
        - 둘 다 인식된 경우 → 더 많이 인식된 쪽으로 결정
        
        Args:
            armband_detected: 완장 감지 여부
            faction: OCR 인식 결과 ("ALLY", "ENEMY", "UNKNOWN")
            confidence: OCR 신뢰도 (0~1)
        
        Returns:
            처리 결과
        """
        # DETECTED 상태가 아니면 무시
        if self.state != ScenarioState.DETECTED:
            return {"success": False, "message": "DETECTED 상태가 아닙니다"}
        
        # 이미 OCR 결과가 락되어 있으면 락된 결과 반환
        if self.ocr_locked and self.ocr_locked_faction:
            return {
                "success": True,
                "action": "locked",
                "faction": self.ocr_locked_faction,
                "message": f"OCR 결과 락됨: {self.ocr_locked_faction}"
            }
        
        # 완장이 감지되지 않은 경우
        if not armband_detected:
            return {
                "success": True,
                "action": "waiting",
                "ally_count": self.ocr_ally_count,
                "enemy_count": self.ocr_enemy_count,
                "message": "완장 감지 대기 중"
            }
        
        # 완장이 감지되었으나 OCR이 실패한 경우 (UNKNOWN)
        if faction in ["UNKNOWN", "ERROR", ""]:
            self.ocr_fail_count += 1
            
            # OCR 실패가 반복되면 TTS 안내 (한 번만) - 상태 재확인
            if self.ocr_fail_count >= self.ocr_fail_tts_threshold and not self.ocr_fail_tts_played:
                # 상태가 변경되었으면 무시
                if self.state != ScenarioState.DETECTED:
                    return {"success": False, "message": "상태가 변경되어 OCR 무시"}
                
                self.ocr_fail_tts_played = True  # TTS 전에 플래그 설정 (race condition 방지)
                await self._play_tts("카메라 렌즈에 피아식별띠를 잘 보이게 위치시키십시오.")
                self._add_history("OCR 실패 반복 - TTS 안내")
                
                # 브로드캐스트
                await self.broadcast({
                    "type": "ocr_guide",
                    "message": "피아식별띠를 카메라에 잘 보이게 해주세요",
                    "ocr_fail_count": self.ocr_fail_count,
                    "ally_count": self.ocr_ally_count,
                    "enemy_count": self.ocr_enemy_count
                })
            
            return {
                "success": True,
                "action": "waiting",
                "ocr_fail_count": self.ocr_fail_count,
                "ally_count": self.ocr_ally_count,
                "enemy_count": self.ocr_enemy_count,
                "message": "완장 감지됨, OCR 인식 대기 중"
            }
        
        # OCR 성공! → 누적 카운트 증가
        if faction == "ALLY" and confidence >= self.ocr_confidence_threshold:
            self.ocr_ally_count += 1
            print(f"✅ ALLY 인식! (누적: ALLY={self.ocr_ally_count}, ENEMY={self.ocr_enemy_count})")
            
        elif faction == "ENEMY" and confidence >= self.ocr_confidence_threshold:
            self.ocr_enemy_count += 1
            print(f"❌ ENEMY 인식! (누적: ALLY={self.ocr_ally_count}, ENEMY={self.ocr_enemy_count})")
        
        # 브로드캐스트 (UI 업데이트)
        await self.broadcast({
            "type": "ocr_update",
            "ally_count": self.ocr_ally_count,
            "enemy_count": self.ocr_enemy_count,
            "last_faction": faction,
            "confidence": confidence
        })
        
        # 🔒 한 번이라도 인식되면 → 즉시 락 및 피아식별
        if self.ocr_ally_count > 0 or self.ocr_enemy_count > 0:
            # 더 많이 인식된 쪽으로 결정 (같으면 먼저 인식된 쪽)
            if self.ocr_ally_count > self.ocr_enemy_count:
                final_faction = "ALLY"
            elif self.ocr_enemy_count > self.ocr_ally_count:
                final_faction = "ENEMY"
            else:
                # 동률 → 방금 인식된 쪽으로
                final_faction = faction
            
            # 🔒 OCR 결과 락
            self.ocr_locked = True
            self.ocr_locked_faction = final_faction
            print(f"🔒 OCR 결과 락: {final_faction} (ALLY={self.ocr_ally_count}, ENEMY={self.ocr_enemy_count})")
            
            # OCR 실패 카운트 리셋 (TTS 플래그는 유지! - PASSWORD_CHECK에서 TTS 방지)
            self.ocr_fail_count = 0
            # self.ocr_fail_tts_played = False  # 리셋하지 않음 - race condition 방지
            
            # 자동 피아식별 실행
            is_ally = (final_faction == "ALLY")
            self._add_history(f"OCR 자동 피아식별: {final_faction} (ALLY={self.ocr_ally_count}, ENEMY={self.ocr_enemy_count})")
            
            result = await self.identify_person(is_ally)
            result["auto_identified"] = True
            result["ocr_ally_count"] = self.ocr_ally_count
            result["ocr_enemy_count"] = self.ocr_enemy_count
            result["ocr_locked"] = True
            
            return result
        
        # 아직 ALLY/ENEMY 인식 안됨
        return {
            "success": True,
            "action": "waiting",
            "faction": faction,
            "confidence": confidence,
            "ally_count": self.ocr_ally_count,
            "enemy_count": self.ocr_enemy_count,
            "message": "OCR 인식 대기 중"
        }
    
    async def reset(self) -> dict:
        """시나리오 리셋"""
        self.state = ScenarioState.IDLE
        self.person_type = PersonType.UNKNOWN
        self.detection_time = None
        
        # OCR 상태 리셋 (누적 카운트 포함)
        self.ocr_ally_count = 0           # ALLY 누적 카운트 리셋
        self.ocr_enemy_count = 0          # ENEMY 누적 카운트 리셋
        self.ocr_fail_count = 0
        self.ocr_fail_tts_played = False
        self.ocr_locked = False           # 🔓 OCR 락 해제
        self.ocr_locked_faction = None    # 🔓 락된 결과 초기화
        
        self._add_history("시나리오 리셋")
        
        # OCR 비활성화 (검은 화면으로)
        await self._set_ocr_enabled(False)
        
        # Voice 상태 리셋 (이전 인증 상태 초기화)
        await self._reset_voice_state()
        
        # 추적 속도 초기화
        await self._send_tracking_speed_reset()
        
        # 디바이스 초기화 (서보, 레이저 OFF)
        await self._control_device("servo", False)
        await self._control_device("laser", False)
        
        await self.broadcast({
            "type": "reset",
            "state": self.state.value,
            "message": "시나리오 초기화됨"
        })
        
        return {"success": True, "state": self.state.value}
    
    async def _set_ocr_enabled(self, enabled: bool):
        """OCR 활성화/비활성화 (armband 화면 제어)"""
        import requests
        try:
            endpoint = "enable" if enabled else "disable"
            response = requests.post(
                f"http://localhost:8000/armband/ocr/{endpoint}",
                timeout=1
            )
            result = response.json()
            print(f"🎯 OCR {'활성화' if enabled else '비활성화'}: {result}")
        except Exception as e:
            print(f"OCR 상태 변경 실패: {e}")

    async def _control_device(self, device: str, on: bool):
        """ESP32 디바이스 제어 (서보, 레이저)"""
        import requests
        try:
            response = requests.post(
                f"http://localhost:8000/device/{device}",
                json={"target": on},
                timeout=1
            )
            result = response.json()
            action = "ON" if on else "OFF"
            print(f"🎯 {device.upper()} {action}: {result.get('status')}")
            self._add_history(f"{device.upper()} {action}")
        except Exception as e:
            print(f"디바이스 제어 실패 ({device}): {e}")
    
    async def _play_tts(self, text: str, voice: str = "eric"):
        """TTS 재생 (ElevenLabs - Voice Panel과 동일) - 재생 완료까지 대기"""
        import httpx
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "http://localhost:8000/voice/speak",
                    json={"text": text, "voice": voice},
                    timeout=30.0  # TTS 재생 완료까지 쵩분한 타임아웃
                )
                result = response.json()
                print(f"🔊 TTS (ElevenLabs): '{text}' → {result}")
                # TTS 재생 완료 후 사람이 반응할 여유 시간
                await asyncio.sleep(0.5)
        except Exception as e:
            print(f"TTS 오류: {e}")
            # ElevenLabs 실패 시 gTTS fallback
            try:
                from tts.TTS import TTS
                tts = TTS(engine_type="gtts")
                import threading
                thread = threading.Thread(target=tts.speak, args=(text,))
                thread.start()
                print(f"🔊 TTS (gTTS fallback): '{text}'")
            except Exception as e2:
                print(f"TTS fallback 오류: {e2}")
    
    async def _start_voice_recognition(self, timeout_sec: float = 4.0):
        """
        자동 음성 인식 시작 (TTS 없이, 마이크 녹음 → STT → 시나리오 제출)
        """
        import httpx
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "http://localhost:8000/voice/listen-only",
                    params={"timeout_sec": timeout_sec},
                    timeout=2.0
                )
                result = response.json()
                print(f"🎤 음성 인식 시작: {result}")
                self._add_history("음성 인식 시작")
        except Exception as e:
            print(f"음성 인식 시작 실패: {e}")
    
    async def _start_voice_auth(self, timeout_sec: float = 5.0):
        """
        시나리오 전용 음성 인증 시작
        TTS("암구호! {질문}!") + 녹음 + STT + 시나리오 제출
        
        ⚠️ /voice/scenario-request-auth 사용 (보이스 패널과 독립)
        """
        import httpx
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "http://localhost:8000/voice/scenario-request-auth",  # 시나리오 전용 API
                    json={"timeout_sec": timeout_sec, "voice": "eric"},
                    timeout=5.0
                )
                result = response.json()
                print(f"🎤 [시나리오] 음성 인증 시작: {result}")
                self._add_history("음성 인증 시작")
        except Exception as e:
            print(f"[시나리오] 음성 인증 시작 실패: {e}")
    
    async def _reset_voice_state(self):
        """Voice 상태 리셋 (시나리오 리셋 시 호출)"""
        import httpx
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "http://localhost:8000/voice/reset",
                    timeout=2.0
                )
                result = response.json()
                print(f"🔄 Voice 상태 리셋: {result}")
        except Exception as e:
            print(f"Voice 상태 리셋 실패: {e}")

    async def _play_alert_buzzer(self, alert_type: str = "warning"):
        """
        경고 부저음 재생
        
        Args:
            alert_type: 
                "warning" - 짧은 경고음 (비프 3회)
                "critical" - 긴박한 경보음 (빠른 펄스 사이렌)
        """
        import threading
        import numpy as np
        import subprocess
        import tempfile
        import os
        
        def generate_and_play_buzzer():
            try:
                # 샘플레이트
                sample_rate = 44100
                volume = 0.25  # 음량 낮춤 (0.5 → 0.25)
                
                if alert_type == "warning":
                    # 짧은 경고음 (비프음 3회)
                    duration = 0.3  # 각 비프 길이
                    freq = 880  # Hz (A5 음)
                    
                    # 비프음 생성
                    t = np.linspace(0, duration, int(sample_rate * duration), False)
                    beep = np.sin(2 * np.pi * freq * t) * volume
                    
                    # 3번 반복 + 간격
                    silence = np.zeros(int(sample_rate * 0.15))
                    audio = np.concatenate([beep, silence, beep, silence, beep])
                    
                elif alert_type == "critical":
                    # 긴장감 있는 사이렌 (8초) - TTS와 함께 울리고 TTS 끝나고 2초 후 종료
                    duration = 8.0
                    t = np.linspace(0, duration, int(sample_rate * duration), False)
                    
                    # 주파수 변조 (빠른 사이렌 효과) - 초당 4회 스윕
                    freq_low, freq_high = 600, 1000
                    freq_mod = freq_low + (freq_high - freq_low) * (0.5 + 0.5 * np.sin(2 * np.pi * 4 * t))
                    
                    # 사이렌 생성
                    phase = np.cumsum(2 * np.pi * freq_mod / sample_rate)
                    audio = np.sin(phase) * volume
                    
                    # 마지막 1초 페이드 아웃
                    fade_len = int(sample_rate * 1.0)
                    audio[-fade_len:] *= np.linspace(1, 0, fade_len)
                else:
                    return
                
                # 16비트 정수로 변환
                audio = (audio * 32767).astype(np.int16)
                
                # 임시 WAV 파일 저장
                with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
                    temp_path = f.name
                    import wave
                    with wave.open(temp_path, 'w') as wav_file:
                        wav_file.setnchannels(1)
                        wav_file.setsampwidth(2)
                        wav_file.setframerate(sample_rate)
                        wav_file.writeframes(audio.tobytes())
                
                # aplay로 재생
                subprocess.run(['aplay', '-q', temp_path], check=True)
                
                # 임시 파일 삭제
                os.unlink(temp_path)
                
            except Exception as e:
                print(f"부저음 재생 오류: {e}")
        
        # 별도 스레드에서 실행
        thread = threading.Thread(target=generate_and_play_buzzer)
        thread.start()

    async def _play_enemy_critical_alert(self):
        """ENEMY_CRITICAL 전용 알림 (TTS + 경고음)"""
        # 1. 메인 TTS
        await self._play_tts("경고! 기밀 유출 의심! 비상 알림 발령!")
        await asyncio.sleep(2.5)  # TTS 완료 대기
        
        # 2. 경고 반복 + 부저음
        await self._play_alert_buzzer("warning")
        await asyncio.sleep(0.3)
        await self._play_tts("경고! 경고! 경고!")

    async def _play_enemy_engage_alert(self):
        """ENEMY_ENGAGE 전용 알림 (TTS + 사이렌)"""
        # 1. TTS 먼저 시작 (비동기로 재생됨)
        await self._play_tts("코드 레드 발령, 코드 레드 발령, 침입자 대응 조치할 것!")
        
        # 2. "코드 레드 발령" 첫 마디 끝날 때쯤 사이렌 시작 (~2.5초 후)
        await asyncio.sleep(2.5)
        await self._play_alert_buzzer("critical")
        
        # 3. 사이렌 끝난 후 서보 OFF (8초 사이렌 + 여유 1초)
        await asyncio.sleep(9)
        await self._control_device("servo", False)
        print("🔫 서보 OFF (사이렌 종료)")

    async def _execute_robot_motion(self, motion_id: str):
        """로봇 모션 실행 (파일 기반 명령 전달)"""
        import json
        import time as time_module
        
        # 모션 정의 (robot.py와 동기화!)
        MOTIONS = {
            "salute": {
                "name": "경례",
                "joints": [3.0, 0.0, 60.0, 120.0, 45.0, 0.0],  # robot.py와 동일
                "velocity": 45.0,
                "acceleration": 35.0,
            },
            "high_ready": {
                "name": "High Ready",
                "joints": [3.0, -20.0, 92.0, 86.0, 0.0, 0.0],  # robot.py와 동일
                "velocity": 50.0,
                "acceleration": 40.0,
            },
            "threat": {
                "name": "위협",
                "joints": [35.0, -20.0, 110.0, 50.0, 10.0, 0.0],  # robot.py와 동일
                "velocity": 40.0,
                "acceleration": 35.0,
            },
            "home": {
                "name": "홈",
                "joints": [0.0, 0.0, 90.0, 0.0, 90.0, 0.0],  # 원본 홈
                "velocity": 30.0,
                "acceleration": 25.0,
            },
        }
        
        if motion_id not in MOTIONS:
            print(f"알 수 없는 모션: {motion_id}")
            return
        
        motion = MOTIONS[motion_id]
        
        # ROS2 브릿지로 명령 전달
        command = {
            'type': 'robot_motion',
            'timestamp': time_module.time(),
            'data': {
                'motion_id': motion_id,
                'motion_name': motion['name'],
                'joints': motion['joints'],
                'velocity': motion['velocity'],
                'acceleration': motion['acceleration'],
            }
        }
        
        command_file = '/tmp/ros2_bridge_command.json'
        try:
            with open(command_file, 'w') as f:
                json.dump(command, f)
            print(f"🤖 로봇 모션 명령 전송: {motion['name']}")
            self._add_history(f"로봇 모션: {motion['name']}")
        except Exception as e:
            print(f"로봇 모션 명령 전송 실패: {e}")

    async def _send_tracking_stop(self):
        """추적 중지 명령 전송"""
        import time as time_module
        
        command = {
            'type': 'robot_command',
            'timestamp': time_module.time(),
            'data': {
                'command': 'stop'
            }
        }
        
        command_file = '/tmp/ros2_bridge_command.json'
        try:
            with open(command_file, 'w') as f:
                json.dump(command, f)
            print("⏹️ 추적 중지 명령 전송")
            self._add_history("추적 중지")
        except Exception as e:
            print(f"추적 중지 명령 전송 실패: {e}")


# 싱글톤 인스턴스
scenario_manager = ScenarioManager()


# ============================================
# API 엔드포인트
# ============================================

class IdentifyRequest(BaseModel):
    is_ally: bool

class PasswordRequest(BaseModel):
    password: str

class SetPasswordRequest(BaseModel):
    challenge: str  # 질문 암구호 (로봇이 물어보는 것)
    response: str = None  # 응답 암구호 (사용자가 답해야 하는 것)

class OcrResultRequest(BaseModel):
    armband_detected: bool  # 완장 감지 여부
    faction: str            # OCR 인식 결과 ("ALLY", "ENEMY", "UNKNOWN")
    confidence: float       # OCR 신뢰도 (0~1)


@router.get("/status")
async def get_status():
    """현재 시나리오 상태"""
    return scenario_manager.get_status()


@router.post("/detect")
async def face_detected():
    """얼굴 감지 이벤트 (face_tracking에서 호출)"""
    return await scenario_manager.on_face_detected()


@router.post("/identify")
async def identify_person(req: IdentifyRequest):
    """피아 식별"""
    return await scenario_manager.identify_person(req.is_ally)


@router.post("/password")
async def submit_password(req: PasswordRequest):
    """암구호 제출"""
    return await scenario_manager.submit_password(req.password)


@router.post("/reset")
async def reset_scenario():
    """시나리오 리셋"""
    return await scenario_manager.reset()


@router.post("/ocr")
async def process_ocr(req: OcrResultRequest):
    """
    OCR 결과 처리 (armband 모듈에서 호출)
    
    완장 감지 + OCR 결과를 받아서 자동 피아식별 처리
    - 연속 3회 같은 faction 감지 시 자동 식별
    - 완장 감지 O + OCR 실패 반복 시 TTS 안내
    """
    return await scenario_manager.process_ocr_result(
        armband_detected=req.armband_detected,
        faction=req.faction,
        confidence=req.confidence
    )


@router.get("/password")
async def get_password():
    """현재 암구호 조회 (문답식)"""
    return scenario_manager.get_password()


@router.post("/password/set")
async def set_password(req: SetPasswordRequest):
    """암구호 변경 (문답식: challenge/response)"""
    if not req.challenge.strip():
        return {"success": False, "message": "질문 암구호는 빈 값일 수 없습니다"}
    return scenario_manager.set_password(req.challenge, req.response)


# ============================================
# WebSocket - 실시간 상태 업데이트
# ============================================

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    scenario_manager.websockets.append(websocket)
    
    # 초기 상태 전송
    await websocket.send_json({
        "type": "init",
        **scenario_manager.get_status()
    })
    
    try:
        while True:
            # 클라이언트로부터 메시지 대기 (keep-alive)
            data = await websocket.receive_text()
            # ping/pong 처리
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        scenario_manager.websockets.remove(websocket)
