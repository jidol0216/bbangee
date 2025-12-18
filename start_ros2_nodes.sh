#!/bin/bash
# ==========================================
# ROS2 노드만 실행 (웹 서버 제외)
# ==========================================

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

declare -a PIDS=()
declare -a NAMES=()

cleanup() {
    echo ""
    echo -e "${RED}========================================${NC}"
    echo -e "${RED}  ROS2 노드 종료 중...${NC}"
    echo -e "${RED}========================================${NC}"
    
    for i in "${!PIDS[@]}"; do
        if kill -0 ${PIDS[$i]} 2>/dev/null; then
            echo -e "${YELLOW}종료: ${NAMES[$i]} (PID: ${PIDS[$i]})${NC}"
            kill ${PIDS[$i]} 2>/dev/null
        fi
    done
    
    pkill -f "face_detection_node" 2>/dev/null
    pkill -f "face_tracking_node" 2>/dev/null
    pkill -f "joint_tracking_node" 2>/dev/null
    pkill -f "bridge_node" 2>/dev/null
    pkill -f "robot_controller" 2>/dev/null
    pkill -f "camera_streamer" 2>/dev/null
    pkill -f "collision_recovery" 2>/dev/null
    pkill -f "image_flip_node" 2>/dev/null
    
    echo -e "${GREEN}✅ 종료 완료!${NC}"
    exit 0
}

trap cleanup SIGINT SIGTERM EXIT

source /opt/ros/humble/setup.bash
source /home/rokey/ros2_ws/install/setup.bash

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  🤖 ROS2 노드 시작 (웹 제외)${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${YELLOW}⚠️  로봇/카메라는 이미 실행되어 있어야 합니다!${NC}"
echo ""

# Image Flip
echo -e "${CYAN}[1/7] Image Flip 시작...${NC}"
ros2 run camera_utils image_flip_node > /tmp/ros2_flip.log 2>&1 &
PIDS+=($!)
NAMES+=("Image Flip")
sleep 1

# Face Detection
echo -e "${CYAN}[2/7] Face Detection 시작...${NC}"
ros2 run face_tracking face_detection_node > /tmp/ros2_detection.log 2>&1 &
PIDS+=($!)
NAMES+=("Face Detection")
sleep 1

# Face Tracking
echo -e "${CYAN}[3/7] Face Tracking 시작...${NC}"
ros2 run face_tracking face_tracking_node > /tmp/ros2_tracking.log 2>&1 &
PIDS+=($!)
NAMES+=("Face Tracking")
sleep 1

# Joint Tracking
echo -e "${CYAN}[4/8] Joint Tracking 시작...${NC}"
ros2 run face_tracking joint_tracking_node > /tmp/ros2_joint.log 2>&1 &
PIDS+=($!)
NAMES+=("Joint Tracking")
sleep 1

# Bridge Node
echo -e "${CYAN}[5/8] Bridge Node 시작...${NC}"
ros2 run ros2_web_bridge bridge_node > /tmp/ros2_bridge.log 2>&1 &
PIDS+=($!)
NAMES+=("Bridge Node")
sleep 1

# Robot Controller
echo -e "${CYAN}[6/8] Robot Controller 시작...${NC}"
ros2 run ros2_web_bridge robot_controller > /tmp/ros2_controller.log 2>&1 &
PIDS+=($!)
NAMES+=("Robot Controller")
sleep 1

# Camera Streamer
echo -e "${CYAN}[7/8] Camera Streamer 시작...${NC}"
ros2 run ros2_web_bridge camera_streamer > /tmp/ros2_streamer.log 2>&1 &
PIDS+=($!)
NAMES+=("Camera Streamer")
sleep 1

# Collision Recovery
echo -e "${CYAN}[8/8] Collision Recovery 시작...${NC}"
ros2 run ros2_web_bridge collision_recovery > /tmp/ros2_collision.log 2>&1 &
PIDS+=($!)
NAMES+=("Collision Recovery")
sleep 1

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  ✅ ROS2 노드 실행 완료!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${YELLOW}  ⏹️  Ctrl+C 를 누르면 종료됩니다${NC}"
echo ""

while true; do
    sleep 5
done
