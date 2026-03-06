#!/usr/bin/env python3
"""
handeye_calibration.py - Eye-on-Hand 캘리브레이션

=============================================================================
이론적 배경 (Eye-in-Hand / Eye-on-Hand)
=============================================================================

카메라가 로봇 그리퍼에 부착된 경우 (Eye-on-Hand):
- 체커보드(타겟)는 고정
- 로봇이 움직이면서 다양한 각도로 체커보드를 관찰

좌표계:
- Base (b): 로봇 베이스 좌표계
- Gripper (g): 그리퍼(end-effector) 좌표계
- Camera (c): 카메라 좌표계
- Target (t): 체커보드 좌표계 (고정)

찾고자 하는 것: T_gripper2camera (^g T_c)
  → 카메라 좌표계에서 그리퍼 좌표계로의 변환
  → P_gripper = T_gripper2camera @ P_camera

=============================================================================
OpenCV calibrateHandEye 함수
=============================================================================

입력:
- R_gripper2base, t_gripper2base: ^b T_g (그리퍼 좌표 → 베이스 좌표)
  → 로봇 FK에서 얻은 T_base2gripper를 그대로 사용
  
- R_target2cam, t_target2cam: ^c T_t (타겟 좌표 → 카메라 좌표)
  → solvePnP는 T_cam2target을 반환하므로 역변환 필요!

출력:
- R_cam2gripper, t_cam2gripper: ^g T_c (카메라 좌표 → 그리퍼 좌표)
  → 이것이 우리가 원하는 T_gripper2camera!

=============================================================================
"""

import cv2
import numpy as np
import json
import os
from scipy.spatial.transform import Rotation

# 체커보드 설정
CHECKERBOARD_SIZE = (10, 7)  # 내부 코너 개수 (cols, rows)
SQUARE_SIZE = 25.0           # mm 단위

# RealSense D435 카메라 intrinsic (640x480)
# ros2 topic echo /camera/flipped/camera_info 에서 확인
REALSENSE_INTRINSIC = np.array([
    [606.322265625, 0.0, 319.7293395996094],
    [0.0, 606.5263671875, 237.96226501464844],
    [0.0, 0.0, 1.0]
], dtype=np.float64)

# RealSense는 이미 보정된 이미지를 제공 (distortion = 0)
REALSENSE_DIST_COEFFS = np.zeros(5, dtype=np.float64)


def get_robot_pose_matrix(x, y, z, rx, ry, rz):
    """
    로봇 posx → T_base2gripper (4x4 변환행렬)
    
    Doosan 로봇의 posx는 베이스 좌표계에서 그리퍼의 위치/자세를 나타냄.
    이는 곧 ^b T_g (gripper → base 변환) = T_base2gripper
    
    OpenCV calibrateHandEye의 R_gripper2base 입력으로 그대로 사용 가능.
    """
    # Doosan 로봇은 ZYZ Euler angle 사용
    R = Rotation.from_euler('ZYZ', [rx, ry, rz], degrees=True).as_matrix()
    T = np.eye(4)
    T[:3, :3] = R
    T[:3, 3] = [x, y, z]
    return T


def find_checkerboard_pose(image, board_size, square_size, camera_matrix, dist_coeffs):
    """
    이미지에서 체커보드를 검출하고 T_target2cam (타겟→카메라) 변환을 구함.
    
    solvePnP는 T_cam2target (카메라→타겟)을 반환하므로,
    OpenCV calibrateHandEye 입력에 맞게 역변환하여 T_target2cam을 반환.
    """
    # 체커보드 3D 점 (타겟 좌표계)
    objp = np.zeros((board_size[0] * board_size[1], 3), np.float32)
    objp[:, :2] = np.mgrid[0:board_size[0], 0:board_size[1]].T.reshape(-1, 2) * square_size

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    found, corners = cv2.findChessboardCorners(
        gray,
        board_size,
        flags=cv2.CALIB_CB_ADAPTIVE_THRESH + cv2.CALIB_CB_FAST_CHECK + cv2.CALIB_CB_NORMALIZE_IMAGE,
    )
    if not found:
        return None, None

    # 서브픽셀 정밀도로 코너 보정
    corners_sub = cv2.cornerSubPix(
        gray, corners, (11, 11), (-1, -1),
        criteria=(cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001),
    )

    # solvePnP: 타겟 좌표계 → 카메라 좌표계 변환을 구함
    # 반환값: rvec, tvec는 T_cam2target (P_camera = R @ P_target + t)
    retval, rvec, tvec = cv2.solvePnP(objp, corners_sub, camera_matrix, dist_coeffs)
    if not retval:
        return None, None

    R_cam2target, _ = cv2.Rodrigues(rvec)
    
    # T_cam2target 구성
    T_cam2target = np.eye(4)
    T_cam2target[:3, :3] = R_cam2target
    T_cam2target[:3, 3] = tvec.flatten()
    
    # T_target2cam = T_cam2target의 역변환
    # OpenCV calibrateHandEye는 T_target2cam (^c T_t)을 입력으로 받음
    T_target2cam = np.linalg.inv(T_cam2target)
    
    R_target2cam = T_target2cam[:3, :3]
    t_target2cam = T_target2cam[:3, 3]

    return R_target2cam, t_target2cam


def calibrate_camera_from_chessboard(image_paths, board_size, square_size):
    """
    체커보드 이미지들에서 카메라 내부 파라미터(intrinsic)를 추정
    """
    objp = np.zeros((board_size[0] * board_size[1], 3), np.float32)
    objp[:, :2] = np.mgrid[0:board_size[0], 0:board_size[1]].T.reshape(-1, 2) * square_size

    obj_points = []
    img_points = []
    image_shape = None

    for fname in image_paths:
        img = cv2.imread(fname)
        if img is None:
            print(f"   이미지 로드 실패: {fname}")
            continue
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        if image_shape is None:
            image_shape = gray.shape[::-1]

        ret, corners = cv2.findChessboardCorners(gray, board_size, None)
        if ret:
            corners_sub = cv2.cornerSubPix(
                gray, corners, (11, 11), (-1, -1),
                (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001),
            )
            obj_points.append(objp)
            img_points.append(corners_sub)
        else:
            print(f"   체커보드 검출 실패: {fname}")

    if len(obj_points) < 3:
        print(" 체커보드 검출된 이미지가 3장 미만입니다!")
        return None, None, None, None

    print(f"   체커보드 검출 성공: {len(obj_points)}장")

    ret, camera_matrix, dist_coeffs, rvecs, tvecs = cv2.calibrateCamera(
        obj_points, img_points, image_shape, None, None
    )

    if not ret:
        print(" 카메라 캘리브레이션 실패!")
        return None, None, None, None

    return camera_matrix, dist_coeffs, rvecs, tvecs


def main():
    print("=" * 60)
    print(" Eye-on-Hand Calibration")
    print("=" * 60)
    
    # 데이터 로드
    data_path = "data/calibrate_data.json"
    if not os.path.exists(data_path):
        print(f" 데이터 파일 없음: {data_path}")
        print("   먼저 data_recording_ros2.py로 데이터를 수집하세요.")
        return
    
    data = json.load(open(data_path))
    robot_poses = np.array(data["poses"])
    image_paths = ["data/" + d for d in data["file_name"]]
    
    print(f"\n 데이터 로드: {len(robot_poses)}장")
    print(f"   체커보드: {CHECKERBOARD_SIZE[0]}x{CHECKERBOARD_SIZE[1]}, {SQUARE_SIZE}mm")
    
    # 1. RealSense 카메라 intrinsic 사용 (체커보드로 재계산하지 않음)
    print("\n 1단계: RealSense 카메라 intrinsic 사용")
    camera_matrix = REALSENSE_INTRINSIC.copy()
    dist_coeffs = REALSENSE_DIST_COEFFS.copy()
    
    print(f"   fx={camera_matrix[0,0]:.1f}, fy={camera_matrix[1,1]:.1f}")
    print(f"   cx={camera_matrix[0,2]:.1f}, cy={camera_matrix[1,2]:.1f}")
    print(f"   distortion: {dist_coeffs.tolist()}")
    
    # 2. Hand-Eye 데이터 수집
    print("\n 2단계: Hand-Eye 변환 데이터 수집...")
    R_gripper2base_list = []
    t_gripper2base_list = []
    R_target2cam_list = []
    t_target2cam_list = []
    
    valid_count = 0
    for idx, (img_path, pose) in enumerate(zip(image_paths, robot_poses)):
        # 로봇 포즈: T_base2gripper (이것이 OpenCV의 R_gripper2base 입력)
        T_base2gripper = get_robot_pose_matrix(*pose)
        
        # 이미지 로딩
        image = cv2.imread(img_path)
        if image is None:
            continue
        
        # 체커보드 검출: T_target2cam (OpenCV의 R_target2cam 입력)
        R_target2cam, t_target2cam = find_checkerboard_pose(
            image, CHECKERBOARD_SIZE, SQUARE_SIZE, camera_matrix, dist_coeffs
        )
        if R_target2cam is None:
            print(f"   [{idx+1}] 체커보드 검출 실패: {img_path}")
            continue
        
        # OpenCV 입력 형식에 맞게 저장
        R_gripper2base_list.append(T_base2gripper[:3, :3])
        t_gripper2base_list.append(T_base2gripper[:3, 3].reshape(3, 1))
        R_target2cam_list.append(R_target2cam)
        t_target2cam_list.append(t_target2cam.reshape(3, 1))
        valid_count += 1
    
    print(f"   유효 데이터: {valid_count}장")
    
    if valid_count < 3:
        print(" 유효 데이터가 3장 미만입니다! 최소 3장 필요.")
        return
    
    if valid_count < 15:
        print(f" 데이터가 적습니다. 30장 이상 권장 (현재 {valid_count}장)")
    
    # 3. Hand-Eye 캘리브레이션
    print("\n 3단계: Hand-Eye 캘리브레이션 계산...")
    print("   방법: CALIB_HAND_EYE_PARK")
    
    R_cam2gripper, t_cam2gripper = cv2.calibrateHandEye(
        R_gripper2base_list,
        t_gripper2base_list,
        R_target2cam_list,
        t_target2cam_list,
        method=cv2.CALIB_HAND_EYE_PARK,
    )
    
    # Rotation determinant 확인 및 수정
    det = np.linalg.det(R_cam2gripper)
    if det < 0:
        print(f"    Rotation determinant = {det:.4f} (반사 포함)")
        print(f"    SVD로 가장 가까운 proper rotation matrix로 변환...")
        # SVD를 사용하여 가장 가까운 proper rotation matrix로 변환
        U, S, Vt = np.linalg.svd(R_cam2gripper)
        R_cam2gripper = U @ Vt
        # 여전히 det < 0이면 마지막 열 부호 변경
        if np.linalg.det(R_cam2gripper) < 0:
            U[:, -1] *= -1
            R_cam2gripper = U @ Vt
        print(f"    수정된 determinant = {np.linalg.det(R_cam2gripper):.6f}")
    
    # T_gripper2camera 구성 (= T_cam2gripper = ^g T_c)
    # 이 행렬은 카메라 좌표를 그리퍼 좌표로 변환: P_gripper = T @ P_camera
    T_gripper2camera = np.eye(4)
    T_gripper2camera[:3, :3] = R_cam2gripper
    T_gripper2camera[:3, 3] = t_cam2gripper.flatten()
    
    # 4. 결과 출력 및 검증
    print("\n" + "=" * 60)
    print(" 캘리브레이션 결과")
    print("=" * 60)
    
    t = T_gripper2camera[:3, 3]
    print(f"\n T_gripper2camera (카메라→그리퍼 변환)")
    print(f"   Translation:")
    print(f"     X = {t[0]:.2f} mm")
    print(f"     Y = {t[1]:.2f} mm")
    print(f"     Z = {t[2]:.2f} mm")
    print(f"     거리 = {np.linalg.norm(t):.2f} mm")
    
    # 5. 유효성 검사
    print(f"\n 유효성 검사:")
    
    # Rotation matrix 검증
    det = np.linalg.det(R_cam2gripper)
    print(f"   Rotation determinant: {det:.6f} (정상: ~1.0)")
    
    is_orthogonal = np.allclose(R_cam2gripper @ R_cam2gripper.T, np.eye(3), atol=1e-5)
    print(f"   Rotation orthogonality: {' 정상' if is_orthogonal else ' 비정상'}")
    
    # 거리 검증 (Eye-on-Hand: 보통 50-300mm)
    dist = np.linalg.norm(t)
    if 30 < dist < 500:
        print(f"   거리 범위:  합리적 ({dist:.1f}mm)")
    else:
        print(f"   거리 범위:  확인 필요 ({dist:.1f}mm)")
    
    # 6. 저장
    output_path = "T_gripper2camera.npy"
    np.save(output_path, T_gripper2camera)
    print(f"\n 저장 완료: {os.path.abspath(output_path)}")
    
    # 기존 캘리브레이션 위치에도 복사
    target_path = "/home/rokey/ros2_ws/src/archive/face_tracking_pkg/day1/2_calibration/T_gripper2camera.npy"
    try:
        np.save(target_path, T_gripper2camera)
        print(f" 복사 완료: {target_path}")
    except Exception as e:
        print(f" 복사 실패: {e}")
    
    print("\n" + "=" * 60)
    print(" 캘리브레이션 완료!")
    print("=" * 60)
    
    # 전체 행렬 출력
    print("\n Full T_gripper2camera matrix:")
    print(T_gripper2camera)
    
    # 사용법 안내
    print("\n" + "=" * 60)
    print(" 사용법")
    print("=" * 60)
    print("""
카메라 좌표 → 로봇 베이스 좌표 변환:

  T_base2gripper = get_current_posx()  # 로봇 현재 위치
  T_base2camera = T_base2gripper @ T_gripper2camera
  P_base = T_base2camera @ P_camera
""")


if __name__ == "__main__":
    main()
