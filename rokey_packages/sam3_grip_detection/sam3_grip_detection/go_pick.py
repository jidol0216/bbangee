# go_pick.py - 토픽 좌표 구독 → 로봇 좌표 변환 → Pick 실행

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from geometry_msgs.msg import PoseStamped
from std_msgs.msg import Float64
import DR_init
import numpy as np
from scipy.spatial.transform import Rotation
import time

# Robot settings
ROBOT_ID = "dsr01"
ROBOT_MODEL = "m0609"
VELOCITY, ACC = 60, 60

# Gripper settings
GRIPPER_NAME = "rg2"
TOOLCHANGER_IP = "192.168.1.1"
TOOLCHANGER_PORT = "502"

# Calibration file (Eye-on-Hand: T_gripper2camera)
CALIBRATION_FILE = "/home/rokey/ros2_ws/src/archive/face_tracking_pkg/day1/2_calibration/T_gripper2camera.npy"

# Z 오프셋 설정
Z_APPROACH_OFFSET = 50   # 접근 높이 (mm)
Z_PICK_OFFSET = 10       # 잡을 때 더 내려가는 높이 (mm)

DR_init.__dsr__id = ROBOT_ID
DR_init.__dsr__model = ROBOT_MODEL


def posx_to_matrix(posx):
    """로봇 posx [x,y,z,rx,ry,rz] → 4x4 변환행렬"""
    x, y, z, rx, ry, rz = posx
    R = Rotation.from_euler('ZYZ', [rx, ry, rz], degrees=True).as_matrix()
    T = np.eye(4)
    T[:3, :3] = R
    T[:3, 3] = [x, y, z]
    return T


# 전역 변수
topic_data = {
    'x': 0.0, 'y': 0.0, 'z': 0.0,
    'gripper_width': 50.0,
    'received': False,
    'new_data': False
}


def main(args=None):
    global topic_data
    
    rclpy.init(args=args)
    node = rclpy.create_node("go_pick_node", namespace=ROBOT_ID)
    DR_init.__dsr__node = node

    try:
        from DSR_ROBOT2 import (
            set_tool,
            set_tcp,
            movel,
            movej,
            mwait,
            get_current_posx,
        )
        from DR_common2 import posx, posj
        from pick_and_place_text.onrobot import RG

    except ImportError as e:
        print(f"Error importing: {e}", flush=True)
        return

    # 캘리브레이션 로드
    try:
        T_gripper2camera = np.load(CALIBRATION_FILE)
        T_camera2gripper = np.linalg.inv(T_gripper2camera)
        print(f"캘리브레이션 로드 완료: {CALIBRATION_FILE}", flush=True)
    except Exception as e:
        print(f"캘리브레이션 로드 실패: {e}", flush=True)
        return

    # 그리퍼 초기화
    gripper = RG(GRIPPER_NAME, TOOLCHANGER_IP, TOOLCHANGER_PORT)
    print("그리퍼 초기화 완료!", flush=True)

    # Tool/TCP 설정 (주석 처리 - 이미 설정되어 있으면 생략)
    # set_tool("Tool Weight_2FG")
    # set_tcp("2FG_TCP")
    print("Tool/TCP 설정 생략 (기존 설정 사용)", flush=True)

    # QoS
    qos = QoSProfile(
        reliability=ReliabilityPolicy.BEST_EFFORT,
        history=HistoryPolicy.KEEP_LAST,
        depth=1
    )

    def pose_callback(msg):
        global topic_data
        topic_data['x'] = msg.pose.position.x * 1000  # m → mm
        topic_data['y'] = msg.pose.position.y * 1000
        topic_data['z'] = msg.pose.position.z * 1000
        topic_data['received'] = True
        topic_data['new_data'] = True

    def width_callback(msg):
        global topic_data
        topic_data['gripper_width'] = msg.data

    # 구독자
    pose_sub = node.create_subscription(PoseStamped, '/grip/grasp_pose', pose_callback, qos)
    width_sub = node.create_subscription(Float64, '/grip/gripper_width', width_callback, 10)

    print("=" * 60, flush=True)
    print("=== go_pick - 토픽 좌표 수신 대기 중 ===", flush=True)
    print("/grip/grasp_pose 토픽을 기다리는 중...", flush=True)
    print("토픽이 오면 자동으로 Pick 실행!", flush=True)
    print("Ctrl+C로 종료", flush=True)
    print("=" * 60, flush=True)

    try:
        while rclpy.ok():
            # 토픽 한번 처리 (spin_once)
            rclpy.spin_once(node, timeout_sec=0.1)
            
            # 새 토픽 데이터가 오면 Pick 실행
            if topic_data['new_data']:
                topic_data['new_data'] = False  # 플래그 리셋
                
                print(f"\n[토픽 수신] 카메라 좌표: X={topic_data['x']:.1f}, Y={topic_data['y']:.1f}, Z={topic_data['z']:.1f} mm", flush=True)
                print("\n" + "=" * 50, flush=True)
                print("새 좌표 수신! Pick 시작...", flush=True)
                
                # 현재 로봇 자세 가져오기
                robot_posx, _ = get_current_posx()
                T_base2gripper = posx_to_matrix(robot_posx)
                
                # 카메라 좌표 → 로봇 베이스 좌표 변환
                P_camera = np.array([
                    topic_data['x'],
                    topic_data['y'],
                    topic_data['z'],
                    1.0
                ])
                P_gripper = T_camera2gripper @ P_camera
                P_base = T_base2gripper @ P_gripper
                
                target_x, target_y, target_z = P_base[0], P_base[1], P_base[2]
                
                # 현재 자세의 rx, ry, rz 유지
                rx, ry, rz = robot_posx[3], robot_posx[4], robot_posx[5]
                
                print(f"[카메라 좌표] X={topic_data['x']:.1f}, Y={topic_data['y']:.1f}, Z={topic_data['z']:.1f}", flush=True)
                print(f"[로봇 좌표]  X={target_x:.1f}, Y={target_y:.1f}, Z={target_z:.1f}", flush=True)
                
                # === Pick 시퀀스 ===
                
                # 1. 그리퍼 열기
                print("\n1. 그리퍼 열기...", flush=True)
                gripper.open_gripper()
                time.sleep(1.0)
                
                # 2. 접근 위치로 이동 (위에서)
                approach_z = target_z + Z_APPROACH_OFFSET
                approach_pos = posx([target_x, target_y, approach_z, rx, ry, rz])
                print(f"2. 접근 위치로 이동... Z={approach_z:.1f}", flush=True)
                movel(approach_pos, vel=VELOCITY, acc=ACC)
                mwait()
                
                # 3. 내려가기 (잡기 위치)
                pick_z = target_z - Z_PICK_OFFSET
                pick_pos = posx([target_x, target_y, pick_z, rx, ry, rz])
                print(f"3. 내려가기... Z={pick_z:.1f}", flush=True)
                movel(pick_pos, vel=30, acc=30)
                mwait()
                
                # 4. 그리퍼 닫기
                print("4. 그리퍼 닫기...", flush=True)
                gripper.close_gripper()
                time.sleep(2.0)
                
                # 5. 들어올리기
                print("5. 들어올리기...", flush=True)
                movel(approach_pos, vel=30, acc=30)
                mwait()
                
                # 6. 그리퍼 열기 (놓기)
                print("6. 그리퍼 열기...", flush=True)
                gripper.open_gripper()
                time.sleep(2.0)
                
                print("\nPick 완료!", flush=True)
                print("=" * 50, flush=True)
                print("\n다음 토픽 대기 중...", flush=True)

    except KeyboardInterrupt:
        print("\n종료...", flush=True)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
