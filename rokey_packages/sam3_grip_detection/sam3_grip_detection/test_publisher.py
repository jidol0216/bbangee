#!/usr/bin/env python3
"""
Test Publisher for Go Pick Node
고정 좌표를 발행하여 go_pick.py 노드를 테스트

발행 토픽:
    /grip/grasp_pose (geometry_msgs/PoseStamped) - 그립 위치 및 자세
    /grip/gripper_width (std_msgs/Float64) - 그리퍼 권장 너비
"""
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import PoseStamped
from std_msgs.msg import Float64, Header


class TestPublisher(Node):
    """테스트용 그립 좌표 발행 노드"""
    
    def __init__(self):
        super().__init__('test_publisher')
        
        # 파라미터 선언
        self.declare_parameter('x', 0.5)  # 미터
        self.declare_parameter('y', 0.0)  # 미터
        self.declare_parameter('z', 0.3)  # 미터
        self.declare_parameter('gripper_width', 60.0)  # mm
        self.declare_parameter('publish_rate', 1.0)  # Hz
        
        # 파라미터 로드
        self.x = self.get_parameter('x').value
        self.y = self.get_parameter('y').value
        self.z = self.get_parameter('z').value
        self.gripper_width = self.get_parameter('gripper_width').value
        self.publish_rate = self.get_parameter('publish_rate').value
        
        # Publisher
        self.pose_pub = self.create_publisher(PoseStamped, '/grip/grasp_pose', 10)
        self.width_pub = self.create_publisher(Float64, '/grip/gripper_width', 10)
        
        # 타이머 (주기적 발행)
        timer_period = 1.0 / self.publish_rate
        self.timer = self.create_timer(timer_period, self.publish_callback)
        
        self.get_logger().info("=" * 60)
        self.get_logger().info("🧪 Test Publisher for Go Pick")
        self.get_logger().info("=" * 60)
        self.get_logger().info("")
        self.get_logger().info(f"발행 좌표 (카메라 좌표계):")
        self.get_logger().info(f"  X: {self.x:.3f} m ({self.x*1000:.1f} mm)")
        self.get_logger().info(f"  Y: {self.y:.3f} m ({self.y*1000:.1f} mm)")
        self.get_logger().info(f"  Z: {self.z:.3f} m ({self.z*1000:.1f} mm)")
        self.get_logger().info(f"  Gripper Width: {self.gripper_width:.1f} mm")
        self.get_logger().info(f"  Publish Rate: {self.publish_rate:.1f} Hz")
        self.get_logger().info("")
        self.get_logger().info("발행 토픽:")
        self.get_logger().info("  /grip/grasp_pose")
        self.get_logger().info("  /grip/gripper_width")
        self.get_logger().info("")
        self.get_logger().info("확인 명령:")
        self.get_logger().info("  ros2 topic echo /grip/grasp_pose")
        self.get_logger().info("  ros2 topic echo /grip/gripper_width")
        self.get_logger().info("=" * 60)
    
    def publish_callback(self):
        """주기적으로 토픽 발행"""
        # 현재 시간
        now = self.get_clock().now().to_msg()
        
        # 1. PoseStamped 메시지 생성
        pose_msg = PoseStamped()
        pose_msg.header.stamp = now
        pose_msg.header.frame_id = "camera_color_optical_frame"
        
        # 위치 (미터)
        pose_msg.pose.position.x = self.x
        pose_msg.pose.position.y = self.y
        pose_msg.pose.position.z = self.z
        
        # 자세 (쿼터니언) - 기본값 (회전 없음)
        pose_msg.pose.orientation.x = 0.0
        pose_msg.pose.orientation.y = 0.0
        pose_msg.pose.orientation.z = 0.0
        pose_msg.pose.orientation.w = 1.0
        
        # 2. 그리퍼 너비 메시지 생성
        width_msg = Float64()
        width_msg.data = self.gripper_width
        
        # 3. 발행
        self.pose_pub.publish(pose_msg)
        self.width_pub.publish(width_msg)
        
        self.get_logger().info(
            f"📤 발행: ({self.x:.3f}, {self.y:.3f}, {self.z:.3f}) m, "
            f"width={self.gripper_width:.1f} mm",
            throttle_duration_sec=2.0
        )


def main(args=None):
    rclpy.init(args=args)
    
    node = TestPublisher()
    
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
