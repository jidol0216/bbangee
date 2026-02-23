"""
중앙 설정 모듈
===============
모든 하드코딩된 설정값을 환경변수 / .env 파일로 관리

사용법:
    from app.services.config import settings
    settings.ESP32_IP
    settings.ELEVENLABS_API_KEY
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ============================================
# ESP32
# ============================================
ESP32_IP: str = os.getenv("ESP32_IP", "192.168.10.46")
ESP32_BASE_URL: str = f"http://{ESP32_IP}"

# ============================================
# ElevenLabs TTS
# ============================================
ELEVENLABS_API_KEY: str = os.getenv("ELEVENLABS_API_KEY", "")

ELEVENLABS_VOICE_IDS: dict[str, str] = {
    "eric": "cjVigY5qzO86Huf0OWal",
    "chris": "iP95p4xoKVk53GoZ742B",
    "sarah": "EXAVITQu4vr4xnSDxMaL",
    "jessica": "cgSgspJ2msm6clMCkdW9",
}
DEFAULT_VOICE_ID: str = ELEVENLABS_VOICE_IDS["eric"]

# ============================================
# 오디오 / 마이크
# ============================================
MIC_DEVICE_INDEX: int = int(os.getenv("MIC_DEVICE_INDEX", "4"))
MIC_SAMPLE_RATE: int = int(os.getenv("MIC_SAMPLE_RATE", "48000"))
TTS_VOLUME_BOOST_DB: float = float(os.getenv("TTS_VOLUME_BOOST_DB", "10.0"))

# ============================================
# ROS2 브릿지 IPC 파일 경로
# ============================================
ROS2_STATE_FILE: str = "/tmp/ros2_bridge_state.json"
ROS2_COMMAND_FILE: str = "/tmp/ros2_bridge_command.json"
ROS2_CAMERA_FRAME: str = "/tmp/ros2_camera_frame.jpg"
ROS2_AUTO_MODE_FILE: str = "/tmp/ros2_auto_mode.json"
COLLISION_STATE_FILE: str = "/tmp/collision_recovery_state.json"
COLLISION_COMMAND_FILE: str = "/tmp/collision_recovery_command.json"
GRIPPER_STATE_FILE: str = "/tmp/gripper_state.json"
GRIPPER_COMMAND_FILE: str = "/tmp/gripper_command.json"
VOICE_STATE_FILE: str = "/tmp/voice_auth_state.json"

# ============================================
# YOLO / Armband 모델
# ============================================
ARMBAND_MODEL_PATH: str = os.getenv(
    "ARMBAND_MODEL_PATH",
    "/home/rokey/ros2_ws/src/obb/runs/obb/armband_v1/weights/best.pt",
)
ARMBAND_COLOR_TOPIC: str = "/camera/flipped/color/image_raw"
ARMBAND_CONFIDENCE_THRESHOLD: float = 0.5
ARMBAND_WARPED_SIZE: tuple[int, int] = (150, 150)
ARMBAND_ALLY_KEYWORDS: list[str] = ["아군"]
ARMBAND_ENEMY_KEYWORDS: list[str] = ["적군"]

# ============================================
# 암구호 기본값
# ============================================
DEFAULT_PASSWORD_CHALLENGE: str = "로키"
DEFAULT_PASSWORD_RESPONSE: str = "협동"

# ============================================
# CORS
# ============================================
CORS_ORIGINS: list[str] = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    os.getenv("CORS_EXTRA_ORIGIN", "http://192.168.10.50:5173"),
]

# ============================================
# 권총 거치대 기본값
# ============================================
PISTOL_POSITION: dict = {
    "x": 478.290,
    "y": 17.860,
    "z": 193.650,
    "rx": 84.22,
    "ry": -131.07,
    "rz": 78.75,
}
PISTOL_Z_LIFT_OFFSET: int = 400
PISTOL_GRIP_SETTINGS: dict = {
    "open_width": 110,
    "close_width": 0,
    "force": 400,
}
PISTOL_MOTION_SETTINGS: dict = {
    "velocity": 60,
    "acceleration": 60,
}
