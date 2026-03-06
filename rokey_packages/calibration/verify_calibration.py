#!/usr/bin/env python3
"""
verify_calibration.py - 카메라-그리퍼 캘리브레이션 검증

사용법:
1. 체커보드를 로봇 베이스에서 알려진 위치에 놓음
2. 이 스크립트 실행
3. 카메라가 계산한 베이스 좌표와 실제 측정값 비교

검증 포인트:
- 체커보드 중심점의 베이스 좌표를 출력
- 실제로 줄자로 측정한 값과 비교
"""

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
import tf2_ros
from geometry_msgs.msg import PointStamped
import tf2_geometry_msgs

# 체커보드 설정
CHECKERBOARD_SIZE = (10, 7)  # 내부 코너 개수
SQUARE_SIZE = 25.0           # mm

# RealSense intrinsic (640x480)
CAMERA_MATRIX = np.array([
    [606.322265625, 0.0, 319.7293395996094],
    [0.0, 606.5263671875, 237.96226501464844],
    [0.0, 0.0, 1.0]
], dtype=np.float64)
DIST_COEFFS = np.zeros(5, dtype=np.float64)

# 카메라 토픽 (flipped 이미지 사용)
IMAGE_TOPIC = "/camera/flipped/color/image_raw"


class CalibrationVerifier(Node):
    def __init__(self):
        super().__init__('calibration_verifier')
        
        self.bridge = CvBridge()
        self.current_frame = None
        
        # TF2 설정
        self.tf_buffer = tf2_ros.Buffer()
        self.tf_listener = tf2_ros.TransformListener(self.tf_buffer, self)
        
        # QoS 설정
        qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=1
        )
        
        # 이미지 구독
        self.image_sub = self.create_subscription(
            Image, IMAGE_TOPIC, self.image_callback, qos
        )
        
        # 타이머 (30Hz)
        self.timer = self.create_timer(0.033, self.process_loop)
        
        self.get_logger().info("=" * 60)
        self.get_logger().info(" 캘리브레이션 검증 도구")
        self.get_logger().info("=" * 60)
        self.get_logger().info("체커보드를 카메라 앞에 놓으세요")
        self.get_logger().info("체커보드 중심의 베이스 좌표를 계산합니다")
        self.get_logger().info("[ESC] 종료")
        self.get_logger().info("=" * 60)
    
    def image_callback(self, msg):
        try:
            self.current_frame = self.bridge.imgmsg_to_cv2(msg, "bgr8")
        except Exception as e:
            self.get_logger().error(f"이미지 변환 실패: {e}")
    
    def find_checkerboard_center_camera(self, image):
        """체커보드 중심점의 카메라 좌표 계산 (mm)"""
        # 체커보드 3D 점 (타겟 좌표계, 중심이 원점)
        objp = np.zeros((CHECKERBOARD_SIZE[0] * CHECKERBOARD_SIZE[1], 3), np.float32)
        objp[:, :2] = np.mgrid[0:CHECKERBOARD_SIZE[0], 0:CHECKERBOARD_SIZE[1]].T.reshape(-1, 2) * SQUARE_SIZE
        # 중심을 원점으로 이동
        objp[:, 0] -= (CHECKERBOARD_SIZE[0] - 1) * SQUARE_SIZE / 2
        objp[:, 1] -= (CHECKERBOARD_SIZE[1] - 1) * SQUARE_SIZE / 2
        
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        found, corners = cv2.findChessboardCorners(
            gray, CHECKERBOARD_SIZE,
            flags=cv2.CALIB_CB_ADAPTIVE_THRESH + cv2.CALIB_CB_FAST_CHECK + cv2.CALIB_CB_NORMALIZE_IMAGE
        )
        
        if not found:
            return None, None, image
        
        # 서브픽셀 정밀도
        corners_sub = cv2.cornerSubPix(
            gray, corners, (11, 11), (-1, -1),
            (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
        )
        
        # solvePnP
        ret, rvec, tvec = cv2.solvePnP(objp, corners_sub, CAMERA_MATRIX, DIST_COEFFS)
        if not ret:
            return None, None, image
        
        # 체커보드 중심 (타겟 좌표계 원점 = 0,0,0) → 카메라 좌표계
        center_target = np.array([[0, 0, 0]], dtype=np.float64)
        center_camera, _ = cv2.projectPoints(center_target, rvec, tvec, CAMERA_MATRIX, DIST_COEFFS)
        
        # 카메라 좌표계에서 중심점 위치 (mm)
        # tvec은 타겟 원점의 카메라 좌표계 위치
        center_3d = tvec.flatten()  # [x, y, z] in mm
        
        # 시각화
        vis_img = image.copy()
        cv2.drawChessboardCorners(vis_img, CHECKERBOARD_SIZE, corners_sub, found)
        
        # 중심점 표시
        cx, cy = int(center_camera[0][0][0]), int(center_camera[0][0][1])
        cv2.circle(vis_img, (cx, cy), 10, (0, 0, 255), -1)
        cv2.putText(vis_img, "CENTER", (cx + 15, cy), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        
        return center_3d, (cx, cy), vis_img
    
    def transform_to_base(self, point_camera):
        """카메라 좌표 → 베이스 좌표 변환 (TF2 사용)"""
        try:
            # camera_color_optical_frame → base_link 변환
            transform = self.tf_buffer.lookup_transform(
                'base_link',  # target frame
                'camera_color_optical_frame',  # source frame
                rclpy.time.Time(),
                timeout=rclpy.duration.Duration(seconds=1.0)
            )
            
            # PointStamped 생성 (m 단위로 변환)
            point_stamped = PointStamped()
            point_stamped.header.frame_id = 'camera_color_optical_frame'
            point_stamped.point.x = point_camera[0] / 1000.0  # mm → m
            point_stamped.point.y = point_camera[1] / 1000.0
            point_stamped.point.z = point_camera[2] / 1000.0
            
            # 변환 적용
            point_base = tf2_geometry_msgs.do_transform_point(point_stamped, transform)
            
            # mm 단위로 반환
            return np.array([
                point_base.point.x * 1000,
                point_base.point.y * 1000,
                point_base.point.z * 1000
            ])
            
        except Exception as e:
            self.get_logger().warn(f"TF 변환 실패: {e}")
            return None
    
    def process_loop(self):
        if self.current_frame is None:
            # 대기 화면
            img = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(img, 'Waiting for camera...', (150, 240),
                       cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2)
            cv2.imshow("Calibration Verification", img)
        else:
            # 체커보드 검출
            center_camera, pixel_pos, vis_img = self.find_checkerboard_center_camera(self.current_frame)
            
            if center_camera is not None:
                # TF 변환
                center_base = self.transform_to_base(center_camera)
                
                # 화면에 정보 표시
                cv2.putText(vis_img, "=== CHECKERBOARD CENTER ===", (10, 30),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                
                cv2.putText(vis_img, f"Camera Frame (mm):", (10, 60),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
                cv2.putText(vis_img, f"  X={center_camera[0]:.1f}, Y={center_camera[1]:.1f}, Z={center_camera[2]:.1f}",
                           (10, 85), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
                
                if center_base is not None:
                    cv2.putText(vis_img, f"Base Frame (mm):", (10, 120),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                    cv2.putText(vis_img, f"  X={center_base[0]:.1f}, Y={center_base[1]:.1f}, Z={center_base[2]:.1f}",
                               (10, 145), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                    
                    # 콘솔에도 출력
                    self.get_logger().info(
                        f" 베이스 좌표: X={center_base[0]:.1f}mm, Y={center_base[1]:.1f}mm, Z={center_base[2]:.1f}mm"
                    )
                else:
                    cv2.putText(vis_img, "Base Frame: TF not available", (10, 120),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
                
                cv2.putText(vis_img, "Compare with actual measurement!", (10, vis_img.shape[0] - 40),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            else:
                cv2.putText(vis_img, "Checkerboard not detected", (10, 30),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                vis_img = self.current_frame.copy()
            
            cv2.putText(vis_img, "[ESC] Exit", (10, vis_img.shape[0] - 10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
            cv2.imshow("Calibration Verification", vis_img)
        
        key = cv2.waitKey(1) & 0xFF
        if key == 27:  # ESC
            self.get_logger().info("종료합니다.")
            cv2.destroyAllWindows()
            rclpy.shutdown()


def main(args=None):
    rclpy.init(args=args)
    node = CalibrationVerifier()
    
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        cv2.destroyAllWindows()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
