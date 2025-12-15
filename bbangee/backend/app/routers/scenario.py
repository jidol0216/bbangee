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
    
    def set_password(self, challenge: str, response: str = None) -> dict:
        """암구호 변경 (문답식)"""
        old_challenge = self.password_challenge
        old_response = self.password_response
        
        self.password_challenge = challenge.strip()
        if response:
            self.password_response = response.strip()
        
        self._add_history(f"암구호 변경: {old_challenge}/{old_response} → {self.password_challenge}/{self.password_response}")
        return {
            "success": True, 
            "challenge": self.password_challenge,
            "response": self.password_response
        }
    
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
        
        # TTS 실행 (별도 스레드)
        await self._play_tts("정지! 손 들어! 신원을 확인합니다.")
        
        # 브로드캐스트
        await self.broadcast({
            "type": "state_change",
            "state": self.state.value,
            "message": "접근자 감지! 피아식별 필요",
            "popup": {
                "show": True,
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
        
        self.person_type = PersonType.ALLY if is_ally else PersonType.ENEMY
        self.state = ScenarioState.PASSWORD_CHECK
        
        person_str = "아군" if is_ally else "적군"
        self._add_history(f"{person_str}으로 식별")
        
        # 아군이면: 추적 중지 → High Ready 자세로 전환
        if is_ally:
            await self._send_tracking_stop()  # 추적 중지
            await asyncio.sleep(0.5)  # 잠시 대기
            await self._execute_robot_motion("high_ready")
        
        # TTS - Challenge 암구호를 말함
        await self._play_tts(f"암구호! {self.password_challenge}!")
        
        # 브로드캐스트
        await self.broadcast({
            "type": "state_change",
            "state": self.state.value,
            "person_type": self.person_type.value,
            "message": f"{person_str} 식별됨 - 암구호 확인 중",
            "popup": {
                "show": True,
                "title": f"🔒 암구호: {self.password_challenge}!",
                "message": "응답 암구호를 입력하세요",
                "input": True
            }
        })
        
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
                await self._play_tts("확인되었습니다. 통과하세요.")
                result_msg = "✅ 아군 통과 승인"
                alert_level = "success"
                robot_motion = "salute"  # 경례 모션으로 시나리오 종료
            else:
                self.state = ScenarioState.ALLY_ALERT
                self._add_history("아군 암구호 오답 - 경고")
                await self._play_tts("암구호가 틀렸습니다. 움직이지 마세요.")
                result_msg = "⚠️ 아군 암구호 오답 - 경고 발령"
                alert_level = "warning"
                robot_motion = "high_ready"  # High Ready 유지한 상태로 종료
        else:  # ENEMY
            if is_correct:
                self.state = ScenarioState.ENEMY_CRITICAL
                self._add_history("적군 암구호 정답 - 기밀유출 의심")
                await self._play_tts("경고! 기밀 유출 의심! 비상 알림 발령!")
                result_msg = "🚨 적군이 암구호 정답 - 기밀유출!"
                alert_level = "critical"
            else:
                self.state = ScenarioState.ENEMY_ENGAGE
                self._add_history("적군 암구호 오답 - 대응")
                await self._play_tts("침입자 발견! 대응 조치!")
                result_msg = "🔴 적군 대응 - 침입자!"
                alert_level = "danger"
            
            # 적군: 추적 속도 증가 (더 빠르게 추적)
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
            "is_correct": is_correct
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
    
    async def reset(self) -> dict:
        """시나리오 리셋"""
        self.state = ScenarioState.IDLE
        self.person_type = PersonType.UNKNOWN
        self.detection_time = None
        self._add_history("시나리오 리셋")
        
        # 추적 속도 초기화
        await self._send_tracking_speed_reset()
        
        await self.broadcast({
            "type": "reset",
            "state": self.state.value,
            "message": "시나리오 초기화됨"
        })
        
        return {"success": True, "state": self.state.value}
    
    async def _play_tts(self, text: str):
        """TTS 재생 (비동기)"""
        try:
            from tts.TTS import TTS
            tts = TTS(engine_type="gtts")
            # 별도 스레드에서 실행
            import threading
            thread = threading.Thread(target=tts.speak, args=(text,))
            thread.start()
        except Exception as e:
            print(f"TTS 오류: {e}")

    async def _execute_robot_motion(self, motion_id: str):
        """로봇 모션 실행 (파일 기반 명령 전달)"""
        import json
        import time as time_module
        
        # 모션 정의 (robot.py와 동기화 필요!)
        MOTIONS = {
            "salute": {
                "name": "경례",
                "joints": [3.0, 0.0, 60.0, 120.0, 45.0, 0.0],  # J5: 45도
                "velocity": 25.0,
                "acceleration": 20.0,
            },
            "high_ready": {
                "name": "High Ready",
                "joints": [3.0, -20.0, 92.0, 86.0, 0.0, 0.0],  # 위를 바라봄
                "velocity": 30.0,
                "acceleration": 25.0,
            },
            "threat": {
                "name": "위협",
                "joints": [35.0, -20.0, 110.0, 50.0, 10.0, 0.0],
                "velocity": 40.0,
                "acceleration": 35.0,
            },
            "home": {
                "name": "홈",
                "joints": [0.0, 0.0, 90.0, 0.0, 90.0, 0.0],  # 홈 위치
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
