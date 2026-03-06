#!/usr/bin/env python3
"""
OnRobot RG2 Gripper Test Script
간단한 테스트로 그리퍼 상태 읽기/제어/ROS2 토픽 발행 확인
"""

import sys
import time

def test_modbus_connection():
    """Modbus TCP 연결 테스트"""
    print("\n" + "="*50)
    print("1. Modbus TCP 연결 테스트")
    print("="*50)
    
    from pymodbus.client.sync import ModbusTcpClient
    
    client = ModbusTcpClient('192.168.1.1', port=502)
    connected = client.connect()
    
    if connected:
        print(" 연결 성공!")
        
        # Read gripper state
        result = client.read_holding_registers(267, 1, unit=65)
        if not result.isError():
            width = result.registers[0] / 10.0
            print(f"   현재 그리퍼 폭: {width} mm")
        
        result = client.read_holding_registers(268, 1, unit=65)
        if not result.isError():
            grip = "감지됨" if result.registers[0] else "감지안됨"
            print(f"   그립 상태: {grip}")
        
        client.close()
        return True
    else:
        print(" 연결 실패!")
        return False


def test_gripper_movement():
    """그리퍼 열기/닫기 테스트"""
    print("\n" + "="*50)
    print("2. 그리퍼 열기/닫기 테스트")
    print("="*50)
    
    from pymodbus.client.sync import ModbusTcpClient
    
    client = ModbusTcpClient('192.168.1.1', port=502)
    client.connect()
    
    # Open gripper (80mm)
    print(" 그리퍼 열기 (80mm)...")
    client.write_register(0, 200, unit=65)  # Force: 20N
    client.write_register(1, 800, unit=65)  # Width: 80mm
    client.write_register(2, 1, unit=65)    # Command
    time.sleep(2)
    
    result = client.read_holding_registers(267, 1, unit=65)
    if not result.isError():
        print(f"   결과: {result.registers[0] / 10.0} mm")
    
    # Close gripper (10mm)
    print(" 그리퍼 닫기 (10mm)...")
    client.write_register(0, 200, unit=65)  # Force: 20N
    client.write_register(1, 100, unit=65)  # Width: 10mm
    client.write_register(2, 1, unit=65)    # Command
    time.sleep(2)
    
    result = client.read_holding_registers(267, 1, unit=65)
    if not result.isError():
        print(f"   결과: {result.registers[0] / 10.0} mm")
    
    client.close()
    print(" 테스트 완료!")
    return True


def test_ros2_node():
    """ROS2 노드 테스트 (5초간 실행)"""
    print("\n" + "="*50)
    print("3. ROS2 노드 테스트 (5초)")
    print("="*50)
    print("   ros2 topic echo /gripper_joint_states 로 확인 가능")
    
    import rclpy
    from rclpy.node import Node
    from sensor_msgs.msg import JointState
    from pymodbus.client.sync import ModbusTcpClient
    
    rclpy.init()
    
    class TestNode(Node):
        def __init__(self):
            super().__init__('gripper_test')
            self.pub = self.create_publisher(JointState, '/gripper_joint_states', 10)
            self.client = ModbusTcpClient('192.168.1.1', port=502)
            self.client.connect()
            self.timer = self.create_timer(0.1, self.publish_state)
            self.count = 0
            
        def publish_state(self):
            result = self.client.read_holding_registers(267, 1, unit=65)
            if not result.isError():
                width_mm = result.registers[0] / 10.0
                # Convert to joint angle (0-110mm -> 0-0.8 rad)
                angle = (width_mm / 110.0) * 0.8
                
                msg = JointState()
                msg.header.stamp = self.get_clock().now().to_msg()
                msg.name = ['gripper_finger_left_joint', 'gripper_finger_right_joint']
                msg.position = [angle, -angle]
                msg.velocity = [0.0, 0.0]
                msg.effort = [0.0, 0.0]
                self.pub.publish(msg)
                
                self.count += 1
                if self.count % 10 == 0:
                    print(f"   발행 중... width={width_mm:.1f}mm, angle={angle:.3f}rad")
    
    node = TestNode()
    
    start = time.time()
    while time.time() - start < 5:
        rclpy.spin_once(node, timeout_sec=0.1)
    
    node.client.close()
    node.destroy_node()
    rclpy.shutdown()
    
    print(" ROS2 노드 테스트 완료!")
    return True


def main():
    print("\n" + "="*60)
    print("   OnRobot RG2 Gripper RViz Sync - 테스트 스크립트")
    print("="*60)
    
    if len(sys.argv) > 1:
        test_num = sys.argv[1]
        if test_num == '1':
            test_modbus_connection()
        elif test_num == '2':
            test_gripper_movement()
        elif test_num == '3':
            test_ros2_node()
        else:
            print("사용법: python3 test_gripper.py [1|2|3|all]")
    else:
        # Run all tests
        test_modbus_connection()
        
        response = input("\n그리퍼 이동 테스트를 실행하시겠습니까? (y/N): ")
        if response.lower() == 'y':
            test_gripper_movement()
        
        response = input("\nROS2 노드 테스트를 실행하시겠습니까? (y/N): ")
        if response.lower() == 'y':
            test_ros2_node()
    
    print("\n" + "="*60)
    print("   테스트 완료!")
    print("="*60)


if __name__ == '__main__':
    main()
