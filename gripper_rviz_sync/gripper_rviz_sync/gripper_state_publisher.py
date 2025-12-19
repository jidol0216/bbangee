#!/usr/bin/env python3
"""
OnRobot RG2 Gripper State Publisher

Modbus TCP로 실제 그리퍼 상태를 읽어서 ROS2 joint_states로 발행
RViz에서 그리퍼 시각화가 실제 하드웨어와 동기화됨
"""

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState
from std_msgs.msg import Float32, Bool
from pymodbus.client.sync import ModbusTcpClient
import math
import time


class GripperStatePublisher(Node):
    """OnRobot RG2 그리퍼 상태를 ROS2로 발행하는 노드"""
    
    def __init__(self):
        super().__init__('gripper_state_publisher')
        
        # Parameters
        self.declare_parameter('modbus_host', '192.168.1.1')
        self.declare_parameter('modbus_port', 502)
        self.declare_parameter('modbus_unit_id', 65)
        self.declare_parameter('publish_rate', 30.0)
        # 실제 URDF 조인트 이름 사용 (onrobot_description 패키지)
        self.declare_parameter('main_joint_name', 'gripper_joint')
        self.declare_parameter('mirror_joint_name', 'gripper_mirror_joint')
        self.declare_parameter('max_width_mm', 110.0)
        self.declare_parameter('joint_max_angle', 1.3)  # URDF limit: 0~1.3 rad
        
        # Get parameters
        self.modbus_host = self.get_parameter('modbus_host').value
        self.modbus_port = self.get_parameter('modbus_port').value
        self.modbus_unit_id = self.get_parameter('modbus_unit_id').value
        self.publish_rate = self.get_parameter('publish_rate').value
        self.main_joint = self.get_parameter('main_joint_name').value
        self.mirror_joint = self.get_parameter('mirror_joint_name').value
        self.max_width_mm = self.get_parameter('max_width_mm').value
        self.joint_max_angle = self.get_parameter('joint_max_angle').value
        
        # Modbus client
        self.client = None
        self.connected = False
        
        # Publishers - 직관적인 토픽명 사용
        self.joint_pub = self.create_publisher(
            JointState, 
            '/gripper/joint_states',   # 그리퍼 조인트 상태
            10
        )
        self.width_pub = self.create_publisher(
            Float32,
            '/gripper/width/current',   # 현재 그리퍼 폭
            10
        )
        self.grip_pub = self.create_publisher(
            Bool,
            '/gripper/grip_detected',   # 물체 감지 여부
            10
        )
        
        # State
        self.current_width = 0.0
        self.grip_detected = False
        
        # Connect to Modbus
        self.connect_modbus()
        
        # 시작 시 현재 그리퍼 상태를 즉시 읽어서 발행 (RViz 초기 동기화)
        if self.connected:
            self.read_gripper_state()
            self.publish_state()
            self.get_logger().info(
                f'Initial gripper state: width={self.current_width:.1f}mm, '
                f'grip_detected={self.grip_detected}'
            )
        
        # Timer for publishing
        self.timer = self.create_timer(
            1.0 / self.publish_rate,
            self.publish_state
        )
        
        self.get_logger().info(
            f'Gripper State Publisher started - '
            f'Modbus: {self.modbus_host}:{self.modbus_port}'
        )
    
    def connect_modbus(self):
        """Modbus TCP 연결"""
        try:
            self.client = ModbusTcpClient(
                self.modbus_host, 
                port=self.modbus_port
            )
            self.connected = self.client.connect()
            if self.connected:
                self.get_logger().info('Modbus TCP connected successfully')
            else:
                self.get_logger().error('Modbus TCP connection failed')
        except Exception as e:
            self.get_logger().error(f'Modbus connection error: {e}')
            self.connected = False
    
    def read_gripper_state(self):
        """Modbus로 그리퍼 상태 읽기"""
        if not self.connected:
            self.connect_modbus()
            if not self.connected:
                return False
        
        try:
            # Read current width (register 267, unit 0.1mm)
            result = self.client.read_holding_registers(
                267, 1, unit=self.modbus_unit_id
            )
            if not result.isError():
                self.current_width = result.registers[0] / 10.0  # mm
            
            # Read grip detected (register 268)
            result = self.client.read_holding_registers(
                268, 1, unit=self.modbus_unit_id
            )
            if not result.isError():
                self.grip_detected = bool(result.registers[0])
            
            return True
            
        except Exception as e:
            self.get_logger().warn(f'Modbus read error: {e}')
            self.connected = False
            return False
    
    def width_to_joint_angle(self, width_mm: float) -> float:
        """
        그리퍼 폭(mm)을 조인트 각도(rad)로 변환
        
        OnRobot RG2 그리퍼 (onrobot_description URDF 기준):
        - 조인트 각도 0.0 rad = 완전 열림 (URDF 기본 상태)
        - 조인트 각도 1.3 rad = 완전 닫힘
        
        실제 그리퍼: 0mm = 닫힘, 110mm = 열림
        URDF: 0 rad = 열림, 1.3 rad = 닫힘
        
        따라서 반전 매핑 필요!
        """
        # 폭을 0~1로 정규화 (0mm=0, 110mm=1)
        normalized = max(0.0, min(1.0, width_mm / self.max_width_mm))
        # 반전: 0mm(닫힘) → 1.3rad, 110mm(열림) → 0rad
        angle = (1.0 - normalized) * self.joint_max_angle
        return angle
    
    def publish_state(self):
        """그리퍼 상태를 ROS2 토픽으로 발행"""
        # Read from hardware
        if not self.read_gripper_state():
            return
        
        # Calculate joint angle
        joint_angle = self.width_to_joint_angle(self.current_width)
        
        # Publish JointState
        joint_msg = JointState()
        joint_msg.header.stamp = self.get_clock().now().to_msg()
        # 실제 URDF 조인트 이름 사용
        joint_msg.name = [self.main_joint, self.mirror_joint]
        # gripper_joint과 gripper_mirror_joint은 같은 방향으로 움직임
        joint_msg.position = [joint_angle, joint_angle]
        joint_msg.velocity = [0.0, 0.0]
        joint_msg.effort = [0.0, 0.0]
        self.joint_pub.publish(joint_msg)
        
        # Publish width
        width_msg = Float32()
        width_msg.data = self.current_width
        self.width_pub.publish(width_msg)
        
        # Publish grip detected
        grip_msg = Bool()
        grip_msg.data = self.grip_detected
        self.grip_pub.publish(grip_msg)
        
        # 웹 API용 상태 파일 저장
        self._save_state_to_file()
    
    def _save_state_to_file(self):
        """웹 API가 빠르게 읽을 수 있도록 파일에 상태 저장"""
        import json
        import time
        try:
            state = {
                'width': self.current_width,
                'grip_detected': self.grip_detected,
                'connected': self.connected,
                'timestamp': time.time()
            }
            with open('/tmp/gripper_state.json', 'w') as f:
                json.dump(state, f)
        except Exception as e:
            pass  # 파일 저장 실패해도 무시
    
    def destroy_node(self):
        """노드 종료 시 Modbus 연결 해제"""
        if self.client:
            self.client.close()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = GripperStatePublisher()
    
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
