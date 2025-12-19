#!/usr/bin/env python3
"""
OnRobot RG2 Gripper Controller

ROS2 서비스/토픽을 통해 그리퍼를 제어
Modbus TCP로 명령을 하드웨어에 전달
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32, Float32MultiArray
from std_srvs.srv import Trigger
from pymodbus.client.sync import ModbusTcpClient
import time


class GripperController(Node):
    """OnRobot RG2 그리퍼 제어 노드"""
    
    def __init__(self):
        super().__init__('gripper_controller')
        
        # Parameters
        self.declare_parameter('modbus_host', '192.168.1.1')
        self.declare_parameter('modbus_port', 502)
        self.declare_parameter('modbus_unit_id', 65)
        self.declare_parameter('default_force', 20.0)  # N
        self.declare_parameter('open_width', 110.0)    # mm (RG2 최대 110mm)
        self.declare_parameter('close_width', 0.0)     # mm
        
        # Get parameters
        self.modbus_host = self.get_parameter('modbus_host').value
        self.modbus_port = self.get_parameter('modbus_port').value
        self.modbus_unit_id = self.get_parameter('modbus_unit_id').value
        self.default_force = self.get_parameter('default_force').value
        self.open_width = self.get_parameter('open_width').value
        self.close_width = self.get_parameter('close_width').value
        
        # Modbus client
        self.client = None
        self.connected = False
        
        # Subscribers - 직관적인 토픽명 사용
        self.width_sub = self.create_subscription(
            Float32,
            '/gripper/width/command',   # 그리퍼 폭 명령
            self.width_command_callback,
            10
        )
        self.force_sub = self.create_subscription(
            Float32,
            '/gripper/force/command',   # 그리퍼 힘 명령
            self.force_command_callback,
            10
        )
        # Combined command: [width_mm, force_n] - race condition 방지
        self.combined_sub = self.create_subscription(
            Float32MultiArray,
            '/gripper/command',         # 폭+힘 동시 명령
            self.combined_command_callback,
            10
        )
        
        # Services
        self.open_srv = self.create_service(
            Trigger,
            '/gripper/open',
            self.open_gripper_callback
        )
        self.close_srv = self.create_service(
            Trigger,
            '/gripper/close',
            self.close_gripper_callback
        )
        
        # State
        self.current_force = self.default_force
        
        # Connect to Modbus
        self.connect_modbus()
        
        self.get_logger().info(
            f'Gripper Controller started - '
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
    
    def send_grip_command(self, width_mm: float, force_n: float) -> bool:
        """
        그리퍼 명령 전송
        
        Args:
            width_mm: 목표 폭 (0-110 mm)
            force_n: 목표 힘 (3-40 N)
        """
        if not self.connected:
            self.connect_modbus()
            if not self.connected:
                return False
        
        try:
            # Convert to register values
            force_reg = int(max(30, min(400, force_n * 10)))   # 0-400 (0.1N unit)
            width_reg = int(max(0, min(1100, width_mm * 10)))  # 0-1100 (0.1mm unit)
            
            # Write force (register 0)
            self.client.write_register(0, force_reg, unit=self.modbus_unit_id)
            # Write width (register 1)
            self.client.write_register(1, width_reg, unit=self.modbus_unit_id)
            # Write control command (register 2, value 1 = grip)
            self.client.write_register(2, 1, unit=self.modbus_unit_id)
            
            self.get_logger().info(
                f'Gripper command sent: width={width_mm}mm, force={force_n}N'
            )
            return True
            
        except Exception as e:
            self.get_logger().error(f'Modbus write error: {e}')
            self.connected = False
            return False
    
    def width_command_callback(self, msg: Float32):
        """폭 명령 콜백"""
        width_mm = msg.data
        self.send_grip_command(width_mm, self.current_force)
    
    def force_command_callback(self, msg: Float32):
        """힘 명령 콜백 (저장만 함)"""
        self.current_force = max(3.0, min(40.0, msg.data))
        self.get_logger().info(f'Force set to: {self.current_force}N')
    
    def combined_command_callback(self, msg: Float32MultiArray):
        """폭+힘 동시 명령 콜백 (race condition 방지)
        
        msg.data = [width_mm, force_n]
        """
        if len(msg.data) >= 2:
            width_mm = msg.data[0]
            force_n = max(3.0, min(40.0, msg.data[1]))
            self.current_force = force_n
            self.send_grip_command(width_mm, force_n)
            self.get_logger().info(f'Combined command: width={width_mm}mm, force={force_n}N')
        else:
            self.get_logger().warn('Combined command requires [width, force]')
    
    def open_gripper_callback(self, request, response):
        """그리퍼 열기 서비스"""
        success = self.send_grip_command(self.open_width, self.current_force)
        response.success = success
        response.message = 'Gripper opened' if success else 'Open failed'
        return response
    
    def close_gripper_callback(self, request, response):
        """그리퍼 닫기 서비스"""
        success = self.send_grip_command(self.close_width, self.current_force)
        response.success = success
        response.message = 'Gripper closed' if success else 'Close failed'
        return response
    
    def destroy_node(self):
        """노드 종료 시 Modbus 연결 해제"""
        if self.client:
            self.client.close()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = GripperController()
    
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
