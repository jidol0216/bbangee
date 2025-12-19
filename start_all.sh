#!/bin/bash
# ==========================================
# 전체 시스템 실행 스크립트
# Ctrl+C로 종료하면 자동으로 모든 프로세스 정리
# ==========================================

# 색상 정의
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# PID 저장용 배열
declare -a PIDS=()
declare -a NAMES=()

# 종료 시 정리 함수
cleanup() {
    echo ""
    echo -e "${RED}========================================${NC}"
    echo -e "${RED}  전체 시스템 종료 중...${NC}"
    echo -e "${RED}========================================${NC}"
    
    # 모든 프로세스 종료
    for i in "${!PIDS[@]}"; do
        if kill -0 ${PIDS[$i]} 2>/dev/null; then
            echo -e "${YELLOW}종료: ${NAMES[$i]} (PID: ${PIDS[$i]})${NC}"
            kill ${PIDS[$i]} 2>/dev/null
        fi
    done
    
    # 추가 정리
    pkill -f "ros2_control_node" 2>/dev/null
    pkill -f "run_emulator" 2>/dev/null
    pkill -f "robot_state_publisher" 2>/dev/null
    pkill -f "face_detection_node" 2>/dev/null
    pkill -f "face_tracking_node" 2>/dev/null
    pkill -f "joint_tracking_node" 2>/dev/null
    pkill -f "bridge_node" 2>/dev/null
    pkill -f "robot_controller" 2>/dev/null
    pkill -f "camera_streamer" 2>/dev/null
    pkill -f "collision_recovery" 2>/dev/null
    pkill -f "image_flip_node" 2>/dev/null
    pkill -f "voice_auth_node" 2>/dev/null
    pkill -f "uvicorn app.main:app" 2>/dev/null
    pkill -f "vite" 2>/dev/null
    pkill -f "realsense2_camera" 2>/dev/null
    pkill -f "gripper_state_publisher" 2>/dev/null
    pkill -f "gripper_controller" 2>/dev/null
    pkill -f "joint_state_merger" 2>/dev/null
    
    sleep 1
    echo -e "${GREEN}✅ 모든 프로세스 종료 완료!${NC}"
    exit 0
}

# Ctrl+C 및 종료 시그널 처리
trap cleanup SIGINT SIGTERM EXIT

# ROS2 환경 설정
source /opt/ros/humble/setup.bash
source /home/rokey/ros2_ws/install/setup.bash

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  🤖 전체 시스템 시작${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# ==========================================
# 0. 기존 프로세스 정리 (포트 충돌 방지)
# ==========================================
echo -e "${YELLOW}[0/7] 기존 프로세스 정리...${NC}"
pkill -f "uvicorn.*main:app" 2>/dev/null
pkill -f "vite" 2>/dev/null
sleep 1

# ==========================================
# 1. 두산 로봇 드라이버 + 그리퍼/카메라 URDF
# ==========================================
echo -e "${CYAN}[1/7] 두산 로봇 드라이버 시작 (그리퍼+카메라 URDF 포함)...${NC}"
ros2 launch gripper_camera_description dsr_bringup2_with_gripper.launch.py \
    name:=dsr01 model:=m0609 host:=192.168.1.100 port:=12345 mode:=real \
    > /tmp/ros2_bringup.log 2>&1 &
PIDS+=($!)
NAMES+=("Doosan Bringup with Gripper")
echo "  → PID: ${PIDS[-1]}"
sleep 3

# ==========================================
# 2. 그리퍼 RViz 동기화 (Modbus)
# ==========================================
echo -e "${CYAN}[2/7] 그리퍼 RViz 동기화 시작...${NC}"
ros2 launch gripper_rviz_sync gripper_sync.launch.py \
    modbus_host:=192.168.1.1 modbus_port:=502 \
    > /tmp/ros2_gripper.log 2>&1 &
PIDS+=($!)
NAMES+=("Gripper RViz Sync")
echo "  → PID: ${PIDS[-1]}"
sleep 2

# ==========================================
# 3. RealSense 카메라
# ==========================================
echo -e "${CYAN}[3/7] RealSense 카메라 시작...${NC}"
ros2 launch realsense2_camera rs_launch.py \
    enable_depth:=true enable_color:=true \
    enable_infra1:=false enable_infra2:=false \
    enable_gyro:=true enable_accel:=true unite_imu_method:=2 \
    align_depth.enable:=true pointcloud.enable:=true \
    spatial_filter.enable:=false temporal_filter.enable:=false \
    decimation_filter.enable:=false hole_filling_filter.enable:=false \
    depth_module.depth_profile:=640x480x30 rgb_camera.color_profile:=640x480x30 \
    > /tmp/ros2_camera.log 2>&1 &
PIDS+=($!)
NAMES+=("RealSense Camera")
echo "  → PID: ${PIDS[-1]}"
sleep 3

# ==========================================
# 4. Image Flip + Face Tracking 노드들
# ==========================================
echo -e "${CYAN}[4/7] Face Tracking 노드들 시작...${NC}"

# Image Flip
ros2 run camera_utils image_flip_node > /tmp/ros2_flip.log 2>&1 &
PIDS+=($!)
NAMES+=("Image Flip")
echo "  → Image Flip PID: ${PIDS[-1]}"
sleep 1

# Face Detection
ros2 run face_tracking face_detection_node > /tmp/ros2_detection.log 2>&1 &
PIDS+=($!)
NAMES+=("Face Detection")
echo "  → Face Detection PID: ${PIDS[-1]}"
sleep 1

# Face Tracking
ros2 run face_tracking face_tracking_node > /tmp/ros2_tracking.log 2>&1 &
PIDS+=($!)
NAMES+=("Face Tracking")
echo "  → Face Tracking PID: ${PIDS[-1]}"
sleep 1

# Joint Tracking
ros2 run face_tracking joint_tracking_node > /tmp/ros2_joint.log 2>&1 &
PIDS+=($!)
NAMES+=("Joint Tracking")
echo "  → Joint Tracking PID: ${PIDS[-1]}"
sleep 1

# ==========================================
# 5. ROS2 Web Bridge 노드들
# ==========================================
echo -e "${CYAN}[5/8] ROS2 Web Bridge 노드들 시작...${NC}"

ros2 run ros2_web_bridge bridge_node > /tmp/ros2_bridge.log 2>&1 &
PIDS+=($!)
NAMES+=("Bridge Node")
echo "  → Bridge Node PID: ${PIDS[-1]}"
sleep 1

ros2 run ros2_web_bridge robot_controller > /tmp/ros2_controller.log 2>&1 &
PIDS+=($!)
NAMES+=("Robot Controller")
echo "  → Robot Controller PID: ${PIDS[-1]}"
sleep 1

ros2 run ros2_web_bridge camera_streamer > /tmp/ros2_streamer.log 2>&1 &
PIDS+=($!)
NAMES+=("Camera Streamer")
echo "  → Camera Streamer PID: ${PIDS[-1]}"
sleep 1

ros2 run ros2_web_bridge collision_recovery > /tmp/ros2_collision.log 2>&1 &
PIDS+=($!)
NAMES+=("Collision Recovery")
echo "  → Collision Recovery PID: ${PIDS[-1]}"
sleep 1

# ==========================================
# 6. Voice Auth 노드 (비활성화 - 웹 백엔드에서 ElevenLabs로 처리)
# ==========================================
echo -e "${CYAN}[6/8] Voice Auth 노드 (비활성화됨 - 웹 백엔드 사용)${NC}"

# ros2 run voice_auth voice_auth_node > /tmp/ros2_voice.log 2>&1 &
# PIDS+=($!)
# NAMES+=("Voice Auth")
# echo "  → Voice Auth PID: ${PIDS[-1]}"
sleep 1

# ==========================================
# 7. 웹 서버 (백엔드 + 프론트엔드)
# ==========================================
echo -e "${CYAN}[7/8] 웹 서버 시작...${NC}"

# 백엔드
cd /home/rokey/ros2_ws/src/bbangee/bbangee/backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/backend.log 2>&1 &
PIDS+=($!)
NAMES+=("Backend (FastAPI)")
echo "  → Backend PID: ${PIDS[-1]}"
sleep 1

# 프론트엔드
cd /home/rokey/ros2_ws/src/bbangee/bbangee/frontend
npm run dev -- --host 0.0.0.0 > /tmp/frontend.log 2>&1 &
PIDS+=($!)
NAMES+=("Frontend (Vite)")
echo "  → Frontend PID: ${PIDS[-1]}"
sleep 2

# ==========================================
# 7. 완료!
# ==========================================
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  ✅ 전체 시스템 실행 완료!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "  🤖 로봇:       Doosan M0609 (192.168.1.100)"
echo -e "  📷 카메라:     RealSense D435"
echo -e "  🌐 프론트엔드: ${BLUE}http://localhost:5173${NC}"
echo -e "  📡 백엔드 API: ${BLUE}http://localhost:8000${NC}"
echo ""
echo -e "  📋 로그 확인:"
echo -e "     tail -f /tmp/ros2_bringup.log      # 로봇 드라이버"
echo -e "     tail -f /tmp/ros2_camera.log       # 카메라"
echo -e "     tail -f /tmp/ros2_detection.log    # 얼굴 검출"
echo -e "     tail -f /tmp/ros2_tracking.log     # 추적"
echo -e "     tail -f /tmp/ros2_bridge.log       # 웹 브릿지"
echo -e "     tail -f /tmp/backend.log           # 백엔드"
echo -e "     tail -f /tmp/frontend.log          # 프론트엔드"
echo ""
echo -e "${YELLOW}  ⏹️  Ctrl+C 를 누르면 모든 프로세스가 자동 종료됩니다${NC}"
echo ""

# 프로세스 모니터링
while true; do
    sleep 5
    # 중요 프로세스 상태 체크
    DEAD_COUNT=0
    for i in "${!PIDS[@]}"; do
        if ! kill -0 ${PIDS[$i]} 2>/dev/null; then
            DEAD_COUNT=$((DEAD_COUNT + 1))
        fi
    done
    
    # 절반 이상 죽으면 경고
    if [ $DEAD_COUNT -gt $((${#PIDS[@]} / 2)) ]; then
        echo -e "${RED}⚠️ 다수의 프로세스가 종료되었습니다. 시스템을 재시작하세요.${NC}"
        break
    fi
done

cleanup
