#!/usr/bin/env python3
"""
Joint State Merger Node

로봇 조인트와 그리퍼 조인트를 합쳐서 RViz에 전달
직관적인 토픽 구조:
  - 입력: /dsr01/joint_states (로봇 6축)
  - 입력: /gripper/joint_states (그리퍼 2축)  
  - 출력: /dsr01/joint_states (그리퍼 조인트만 추가 발행)
"""

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState
from rclpy.qos import QoSProfile, ReliabilityPolicy


class JointStateMerger(Node):
    """그리퍼 조인트 상태를 RViz용으로 발행하는 노드"""
    
    def __init__(self):
        super().__init__('joint_state_merger')
        
        # Parameters
        self.declare_parameter('gripper_joint_states_topic', '/gripper/joint_states')
        self.declare_parameter('output_joint_states_topic', '/dsr01/joint_states')
        
        # Get parameters
        gripper_topic = self.get_parameter('gripper_joint_states_topic').value
        output_topic = self.get_parameter('output_joint_states_topic').value
        
        # Subscriber - 그리퍼 조인트 상태
        self.gripper_sub = self.create_subscription(
            JointState,
            gripper_topic,
            self.gripper_callback,
            10
        )
        
        # Publisher - RViz용 (그리퍼 조인트만 발행)
        # robot_state_publisher가 로봇 조인트 + 그리퍼 조인트 모두 받아서 TF 생성
        self.joint_states_pub = self.create_publisher(
            JointState,
            output_topic,
            10
        )
        
        self.get_logger().info(
            f'Joint State Merger started:\n'
            f'  Gripper input: {gripper_topic}\n'
            f'  Output:        {output_topic}'
        )
    
    def gripper_callback(self, msg: JointState):
        """그리퍼 조인트 상태를 발행"""
        self.joint_states_pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = JointStateMerger()
    
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
