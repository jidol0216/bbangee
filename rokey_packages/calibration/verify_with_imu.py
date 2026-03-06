#!/usr/bin/env python3
"""
IMU를 활용한 카메라 방향 검증
RealSense D435i의 내장 IMU로 카메라 orientation 확인
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from sensor_msgs.msg import Imu
import numpy as np
import tf2_ros
from geometry_msgs.msg import TransformStamped
import math


class IMUVerifier(Node):
    def __init__(self):
        super().__init__('imu_verifier')
        
        # QoS for RealSense IMU (Best Effort)
        qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=10
        )
        
        # IMU subscriber
        self.imu_sub = self.create_subscription(
            Imu,
            '/camera/camera/imu',  # RealSense IMU topic
            self.imu_callback,
            qos
        )
        
        # TF buffer
        self.tf_buffer = tf2_ros.Buffer()
        self.tf_listener = tf2_ros.TransformListener(self.tf_buffer, self)
        
        self.accel_samples = []
        self.gyro_samples = []
        self.sample_count = 0
        self.max_samples = 100
        
        self.get_logger().info(" IMU Verifier 시작...")
        self.get_logger().info("   카메라를 정지 상태로 유지하세요")
        
    def imu_callback(self, msg: Imu):
        # 가속도 데이터 수집 (정지 시 중력만 측정됨)
        accel = np.array([
            msg.linear_acceleration.x,
            msg.linear_acceleration.y,
            msg.linear_acceleration.z
        ])
        
        gyro = np.array([
            msg.angular_velocity.x,
            msg.angular_velocity.y,
            msg.angular_velocity.z
        ])
        
        self.accel_samples.append(accel)
        self.gyro_samples.append(gyro)
        self.sample_count += 1
        
        if self.sample_count >= self.max_samples:
            self.analyze_imu_data()
            self.sample_count = 0
            self.accel_samples = []
            self.gyro_samples = []
    
    def analyze_imu_data(self):
        """IMU 데이터 분석"""
        accel_mean = np.mean(self.accel_samples, axis=0)
        accel_std = np.std(self.accel_samples, axis=0)
        gyro_mean = np.mean(self.gyro_samples, axis=0)
        
        # 중력 크기 (정지 시 ~9.8 m/s²)
        gravity_magnitude = np.linalg.norm(accel_mean)
        
        # 중력 방향 벡터 (정규화)
        gravity_direction = accel_mean / gravity_magnitude
        
        self.get_logger().info("=" * 50)
        self.get_logger().info(" IMU 분석 결과 (100 샘플 평균)")
        self.get_logger().info("=" * 50)
        
        # 가속도 (중력)
        self.get_logger().info(f" 가속도 (IMU 프레임):")
        self.get_logger().info(f"   X: {accel_mean[0]:+.3f} m/s² (±{accel_std[0]:.3f})")
        self.get_logger().info(f"   Y: {accel_mean[1]:+.3f} m/s² (±{accel_std[1]:.3f})")
        self.get_logger().info(f"   Z: {accel_mean[2]:+.3f} m/s² (±{accel_std[2]:.3f})")
        self.get_logger().info(f"   크기: {gravity_magnitude:.3f} m/s² (예상: 9.81)")
        
        # 자이로 (정지 시 ~0)
        gyro_magnitude = np.linalg.norm(gyro_mean)
        self.get_logger().info(f" 각속도:")
        self.get_logger().info(f"   크기: {gyro_magnitude:.4f} rad/s (정지: ~0)")
        
        # 카메라 방향 추정
        self.get_logger().info("")
        self.get_logger().info(" 카메라 방향 분석:")
        
        # IMU 프레임에서 어느 축이 중력(아래)을 향하는지
        max_axis = np.argmax(np.abs(accel_mean))
        axis_names = ['X', 'Y', 'Z']
        sign = '+' if accel_mean[max_axis] > 0 else '-'
        
        self.get_logger().info(f"   중력 방향: {sign}{axis_names[max_axis]} 축")
        
        # 카메라 자세 추정 (Roll, Pitch)
        # IMU 프레임 기준
        pitch = math.atan2(-accel_mean[0], math.sqrt(accel_mean[1]**2 + accel_mean[2]**2))
        roll = math.atan2(accel_mean[1], accel_mean[2])
        
        self.get_logger().info(f"   Roll:  {math.degrees(roll):+.1f}°")
        self.get_logger().info(f"   Pitch: {math.degrees(pitch):+.1f}°")
        
        # TF에서 카메라 프레임 확인
        self.check_camera_tf()
        
    def check_camera_tf(self):
        """TF 트리에서 카메라 위치 확인"""
        try:
            # base_link → camera_link 변환 확인
            tf = self.tf_buffer.lookup_transform(
                'base_link',
                'camera_link',
                rclpy.time.Time(),
                timeout=rclpy.duration.Duration(seconds=1.0)
            )
            
            t = tf.transform.translation
            r = tf.transform.rotation
            
            self.get_logger().info("")
            self.get_logger().info(" TF: base_link → camera_link")
            self.get_logger().info(f"   위치: X={t.x*1000:.1f}mm, Y={t.y*1000:.1f}mm, Z={t.z*1000:.1f}mm")
            
            # Quaternion to Euler
            from transforms3d.euler import quat2euler
            # transforms3d uses w,x,y,z order
            euler = quat2euler([r.w, r.x, r.y, r.z])
            self.get_logger().info(f"   회전: R={math.degrees(euler[0]):.1f}°, P={math.degrees(euler[1]):.1f}°, Y={math.degrees(euler[2]):.1f}°")
            
        except Exception as e:
            self.get_logger().warn(f"   TF 조회 실패: {e}")


def main():
    rclpy.init()
    node = IMUVerifier()
    
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
