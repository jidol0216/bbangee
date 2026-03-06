#!/usr/bin/env python3
"""
data_recording_ros2.py - Hand-Eye 캘리브레이션 데이터 수집

사용법:
  1. 로봇 드라이버 실행
  2. RealSense 카메라 실행
  3. python3 data_recording_ros2.py
  4. 로봇을 MANUAL 모드로 전환
  5. 체커보드가 보이는 다양한 위치로 로봇 이동
  6. [q] 키로 저장, [ESC]로 종료
"""

import os
import cv2
import json
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from sensor_msgs.msg import Image
from cv_bridge import CvBridge

# 서비스
from dsr_msgs2.srv import GetCurrentPosx

# 로봇 설정
ROBOT_ID = "dsr01"
ROBOT_MODEL = "m0609"

#  카메라 180도 회전 장착 → flipped 이미지 사용
IMAGE_TOPIC = "/camera/flipped/color/image_raw"


class DataRecordingNode(Node):
    def __init__(self):
        super().__init__('data_recording_node')
        
        # CV Bridge 초기화
        self.bridge = CvBridge()
        self.current_frame = None
        
        # QoS 설정
        qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=1
        )
        
        # RealSense 이미지 토픽 구독 (flipped 이미지!)
        self.image_sub = self.create_subscription(
            Image,
            IMAGE_TOPIC,
            self.image_callback,
            qos
        )
        self.get_logger().info(f' 이미지 토픽: {IMAGE_TOPIC}')
        
        # 로봇 위치 서비스 클라이언트
        self.get_posx_client = self.create_client(
            GetCurrentPosx,
            f'/{ROBOT_ID}/aux_control/get_current_posx'
        )
        
        # 데이터 저장 경로 설정
        self.source_path = "./data"
        os.makedirs(self.source_path, exist_ok=True)
        
        # 저장 데이터
        self.write_data = {"poses": [], "file_name": []}
        
        # 기존 데이터 로드 (이어서 저장)
        json_path = f"{self.source_path}/calibrate_data.json"
        if os.path.exists(json_path):
            with open(json_path, 'r') as f:
                self.write_data = json.load(f)
            self.get_logger().info(f' 기존 데이터 로드: {len(self.write_data["poses"])}장')
        
        # 타이머로 OpenCV 창 업데이트 (30Hz)
        self.timer = self.create_timer(0.033, self.display_loop)
        
        self.get_logger().info("=" * 50)
        self.get_logger().info(" Hand-Eye 캘리브레이션 데이터 수집")
        self.get_logger().info("=" * 50)
        self.get_logger().info("  [q] 이미지 저장")
        self.get_logger().info("  [ESC] 종료")
        self.get_logger().info("  [r] 데이터 초기화")
        self.get_logger().info("=" * 50)
        self.get_logger().info(" 체커보드를 고정하고 로봇을 다양한 위치로 이동하세요")
        self.get_logger().info(" 최소 30장, 권장 50장 이상 수집")
    
    def image_callback(self, msg):
        """ROS2 이미지 메시지를 OpenCV 이미지로 변환"""
        try:
            self.current_frame = self.bridge.imgmsg_to_cv2(msg, "bgr8")
        except Exception as e:
            self.get_logger().error(f"이미지 변환 실패: {e}")
    
    def get_robot_pose(self):
        """subprocess로 로봇 현재 위치 가져오기 (안정적 방식)"""
        import subprocess
        import ast
        
        try:
            # ros2 service call 명령어 실행
            cmd = [
                'ros2', 'service', 'call',
                f'/{ROBOT_ID}/aux_control/get_current_posx',
                'dsr_msgs2/srv/GetCurrentPosx',
                '{ref: 0}'
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=3.0)
            
            if result.returncode != 0:
                self.get_logger().warn(f'서비스 호출 실패: {result.stderr}')
                return None
            
            # 출력에서 위치 데이터 파싱
            output = result.stdout
            
            # task_pos_info에서 data 추출
            if 'data=' in output:
                # "data=[x, y, z, rx, ry, rz]" 형식 파싱
                import re
                match = re.search(r'data=\[([-\d.,\s]+)\]', output)
                if match:
                    data_str = match.group(1)
                    values = [float(x.strip()) for x in data_str.split(',')]
                    return values[:6]  # x, y, z, rx, ry, rz
            
            self.get_logger().warn('위치 데이터 파싱 실패')
            return None
            
        except subprocess.TimeoutExpired:
            self.get_logger().warn('서비스 호출 타임아웃')
            return None
        except Exception as e:
            self.get_logger().error(f'서비스 호출 오류: {e}')
            return None
    
    def display_loop(self):
        """OpenCV 창 업데이트 및 키 입력 처리"""
        if self.current_frame is None:
            # 대기 화면
            import numpy as np
            img = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(img, 'Waiting for camera...', (150, 240),
                       cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2)
            cv2.imshow("Calibration Data Recording", img)
        else:
            # 상태 표시
            img = self.current_frame.copy()
            count = len(self.write_data['poses'])
            cv2.putText(img, f'Saved: {count} images', (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)
            cv2.putText(img, '[q] Save | [r] Reset | [ESC] Exit', (10, img.shape[0] - 10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
            cv2.imshow("Calibration Data Recording", img)
        
        key = cv2.waitKey(1) & 0xFF
        
        if key == 27:  # ESC
            self.get_logger().info("종료합니다.")
            cv2.destroyAllWindows()
            rclpy.shutdown()
            
        elif key == ord("q"):
            self.save_data()
            
        elif key == ord("r"):
            self.reset_data()
    
    def save_data(self):
        """현재 프레임과 로봇 위치 저장"""
        if self.current_frame is None:
            self.get_logger().warn("프레임이 없습니다!")
            return
        
        # 로봇 위치 가져오기
        pos = self.get_robot_pose()
        
        if pos is not None:
            file_name = f"{pos[0]:.2f}_{pos[1]:.2f}_{pos[2]:.2f}.jpg"
            self.get_logger().info(f"로봇 위치: [{pos[0]:.1f}, {pos[1]:.1f}, {pos[2]:.1f}, {pos[3]:.1f}, {pos[4]:.1f}, {pos[5]:.1f}]")
        else:
            import time
            timestamp = int(time.time() * 1000)
            file_name = f"img_{timestamp}.jpg"
            pos = [0, 0, 0, 0, 0, 0]
            self.get_logger().warn(" 로봇 위치 수신 안됨 - 이 데이터는 캘리브레이션에 사용할 수 없습니다!")
            return  # 로봇 위치 없으면 저장 안함
        
        # 이미지 저장
        file_path = f"{self.source_path}/{file_name}"
        cv2.imwrite(file_path, self.current_frame)
        
        # 데이터 추가
        self.write_data["file_name"].append(file_name)
        self.write_data["poses"].append(pos)
        
        # JSON 저장
        with open(f"{self.source_path}/calibrate_data.json", "w") as json_file:
            json.dump(self.write_data, json_file, indent=4)
        
        self.get_logger().info(f" 저장 완료 [{len(self.write_data['poses'])}장]: {file_name}")
    
    def reset_data(self):
        """데이터 초기화"""
        self.write_data = {"poses": [], "file_name": []}
        json_path = f"{self.source_path}/calibrate_data.json"
        if os.path.exists(json_path):
            os.remove(json_path)
        # 이미지 파일들도 삭제
        for f in os.listdir(self.source_path):
            if f.endswith('.jpg'):
                os.remove(f"{self.source_path}/{f}")
        self.get_logger().info(" 데이터 초기화 완료")


def main(args=None):
    rclpy.init(args=args)
    
    node = DataRecordingNode()
    
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
