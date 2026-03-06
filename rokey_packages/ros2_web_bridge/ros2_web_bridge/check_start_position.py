#!/usr/bin/env python3
"""
check_start_position.py - 웹 시작 위치의 직교좌표 확인

웹에서 사용하는 START_JOINTS를 직교좌표로 변환하여
go_coordinate_grip.py의 A2와 비교
"""

import rclpy
from rclpy.node import Node
import DR_init

ROBOT_ID = "dsr01"
ROBOT_MODEL = "m0609"

DR_init.__dsr__id = ROBOT_ID
DR_init.__dsr__model = ROBOT_MODEL

# 웹의 시작 위치 (조인트 각도, deg)
START_JOINTS = [3.0, -20.0, 92.0, 86.0, 0.0, 0.0]

# go_coordinate_grip.py의 A2 (직교좌표)
A2_POS = {
    'x': 599.032,
    'y': 28.656,
    'z': 525.622,
    'rx': 0.466,
    'ry': 90.482,
    'rz': -87.04,
}


def main():
    rclpy.init()
    node = rclpy.create_node('check_position', namespace=ROBOT_ID)
    DR_init.__dsr__node = node
    
    try:
        from DSR_ROBOT2 import fkin, get_current_posx
        from DR_common2 import posj
        
        print('=' * 60)
        print('웹 시작 위치 vs A2 좌표 비교')
        print('=' * 60)
        
        # Forward Kinematics로 START_JOINTS의 직교좌표 계산
        start_joints = posj(START_JOINTS)
        start_posx = fkin(start_joints)
        
        print(f'\n 웹 START_JOINTS (조인트 각도):')
        print(f'   {START_JOINTS}')
        
        print(f'\n 변환된 직교좌표 (fkin):')
        print(f'   X: {start_posx[0]:.3f} mm')
        print(f'   Y: {start_posx[1]:.3f} mm')
        print(f'   Z: {start_posx[2]:.3f} mm')
        print(f'   RX: {start_posx[3]:.3f} deg')
        print(f'   RY: {start_posx[4]:.3f} deg')
        print(f'   RZ: {start_posx[5]:.3f} deg')
        
        print(f'\n go_coordinate_grip.py A2 좌표:')
        print(f'   X: {A2_POS["x"]:.3f} mm')
        print(f'   Y: {A2_POS["y"]:.3f} mm')
        print(f'   Z: {A2_POS["z"]:.3f} mm')
        print(f'   RX: {A2_POS["rx"]:.3f} deg')
        print(f'   RY: {A2_POS["ry"]:.3f} deg')
        print(f'   RZ: {A2_POS["rz"]:.3f} deg')
        
        # 차이 계산
        diff_x = abs(start_posx[0] - A2_POS['x'])
        diff_y = abs(start_posx[1] - A2_POS['y'])
        diff_z = abs(start_posx[2] - A2_POS['z'])
        
        print(f'\n 위치 차이:')
        print(f'   ΔX: {diff_x:.3f} mm')
        print(f'   ΔY: {diff_y:.3f} mm')
        print(f'   ΔZ: {diff_z:.3f} mm')
        
        total_diff = (diff_x**2 + diff_y**2 + diff_z**2) ** 0.5
        print(f'   총 거리: {total_diff:.3f} mm')
        
        if total_diff < 10:
            print('\n 위치가 거의 같습니다! (차이 < 10mm)')
        elif total_diff < 50:
            print('\n 위치가 비슷합니다. (차이 < 50mm)')
        else:
            print('\n 위치가 다릅니다! A2 좌표 업데이트 필요')
        
        # 현재 로봇 위치도 출력
        print(f'\n 현재 로봇 위치:')
        current = get_current_posx()[0]
        print(f'   X: {current[0]:.3f}, Y: {current[1]:.3f}, Z: {current[2]:.3f}')
        print(f'   RX: {current[3]:.3f}, RY: {current[4]:.3f}, RZ: {current[5]:.3f}')
        
        print('=' * 60)
        
    except Exception as e:
        print(f' 에러: {e}')
        import traceback
        traceback.print_exc()
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
