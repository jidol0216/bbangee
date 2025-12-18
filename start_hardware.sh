#!/bin/bash
# ==========================================
# 하드웨어 실행 (로봇 + 카메라)
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
    echo -e "${RED}  하드웨어 종료 중...${NC}"
    echo -e "${RED}========================================${NC}"
    
    for i in "${!PIDS[@]}"; do
        if kill -0 ${PIDS[$i]} 2>/dev/null; then
            echo -e "${YELLOW}종료: ${NAMES[$i]} (PID: ${PIDS[$i]})${NC}"
            kill ${PIDS[$i]} 2>/dev/null
        fi
    done
    
    pkill -f "ros2_control_node" 2>/dev/null
    pkill -f "run_emulator" 2>/dev/null
    pkill -f "robot_state_publisher" 2>/dev/null
    pkill -f "realsense2_camera" 2>/dev/null
    pkill -f "gripper_state_publisher" 2>/dev/null
    pkill -f "gripper_controller" 2>/dev/null
    pkill -f "joint_state_merger" 2>/dev/null
    
    echo -e "${GREEN}✅ 종료 완료!${NC}"
    exit 0
}

trap cleanup SIGINT SIGTERM EXIT

source /opt/ros/humble/setup.bash
source /home/rokey/ros2_ws/install/setup.bash

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  🔧 하드웨어 시작 (로봇 + 카메라)${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# 파라미터
ROBOT_IP=${1:-192.168.1.100}
ROBOT_MODE=${2:-real}
GRIPPER_IP=${3:-192.168.1.1}  # OnRobot Compute Box IP

echo -e "  로봇 IP: $ROBOT_IP"
echo -e "  모드: $ROBOT_MODE"
echo -e "  그리퍼 IP: $GRIPPER_IP"
echo ""

# 두산 로봇 + 그리퍼 + 카메라 URDF
echo -e "${CYAN}[1/3] 두산 로봇 드라이버 시작 (그리퍼+카메라 URDF 포함)...${NC}"
ros2 launch gripper_camera_description dsr_bringup2_with_gripper.launch.py \
    name:=dsr01 model:=m0609 host:=$ROBOT_IP port:=12345 mode:=$ROBOT_MODE \
    > /tmp/ros2_bringup.log 2>&1 &
PIDS+=($!)
NAMES+=("Doosan Bringup with Gripper")
echo "  → PID: ${PIDS[-1]}"
sleep 3

# 그리퍼 RViz 동기화 (Modbus 통신)
echo -e "${CYAN}[2/3] 그리퍼 RViz 동기화 시작...${NC}"
ros2 launch gripper_rviz_sync gripper_sync.launch.py \
    modbus_host:=$GRIPPER_IP modbus_port:=502 \
    > /tmp/ros2_gripper.log 2>&1 &
PIDS+=($!)
NAMES+=("Gripper RViz Sync")
echo "  → PID: ${PIDS[-1]}"
sleep 2

# RealSense 카메라
echo -e "${CYAN}[3/3] RealSense 카메라 시작...${NC}"
ros2 launch realsense2_camera rs_launch.py \
    enable_depth:=true enable_color:=true \
    enable_infra1:=false enable_infra2:=false \
    align_depth.enable:=true pointcloud.enable:=true \
    spatial_filter.enable:=false temporal_filter.enable:=false \
    decimation_filter.enable:=false hole_filling_filter.enable:=false \
    depth_module.depth_profile:=640x480x30 rgb_camera.color_profile:=640x480x30 \
    > /tmp/ros2_camera.log 2>&1 &
PIDS+=($!)
NAMES+=("RealSense Camera")
echo "  → PID: ${PIDS[-1]}"
sleep 3

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  ✅ 하드웨어 실행 완료!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "  📋 로그 확인:"
echo -e "     tail -f /tmp/ros2_bringup.log   # 로봇"
echo -e "     tail -f /tmp/ros2_camera.log    # 카메라"
echo ""
echo -e "${YELLOW}  ⏹️  Ctrl+C 를 누르면 종료됩니다${NC}"
echo ""

while true; do
    sleep 5
done
