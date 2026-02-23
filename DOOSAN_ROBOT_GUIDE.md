# 두산 로봇 제어 학습 가이드

## 📋 목차
1. [환경 설정](#1-환경-설정)
2. [두산 패키지 구조 이해](#2-두산-패키지-구조-이해)
3. [기본 로봇 연결](#3-기본-로봇-연결)
4. [로봇 제어 기초](#4-로봇-제어-기초)
5. [고급 제어](#5-고급-제어)

---

## 1. 환경 설정

### 1.1 ROS2 Humble 설치 확인
```bash
source /opt/ros/humble/setup.bash
ros2 --version
```

### 1.2 두산 패키지 위치 확인
```bash
cd ~/ros2_ws/src/DoosanBootcampCol2
ls -la
```

**주요 패키지**:
- `dsr_bringup2`: 로봇 실행 런치 파일
- `dsr_controller2`: 로봇 컨트롤러
- `dsr_hardware2`: 하드웨어 인터페이스
- `dsr_msgs2`: 메시지 정의
- `dsr_description2`: URDF/모델 파일

### 1.3 패키지 빌드
```bash
cd ~/ros2_ws
source /opt/ros/humble/setup.bash
colcon build --packages-select dsr_bringup2 dsr_controller2 dsr_hardware2 dsr_msgs2 --symlink-install
source install/setup.bash
```

---

## 2. 두산 패키지 구조 이해

### 2.1 dsr_bringup2 살펴보기
```bash
cd ~/ros2_ws/src/DoosanBootcampCol2/dsr_bringup2
tree -L 2
```

**주요 디렉토리**:
- `launch/`: 로봇 실행 런치 파일들
- `config/`: 설정 파일들
- `rviz/`: RViz 시각화 설정

**중요 런치 파일**:
```bash
# 기본 로봇 드라이버
ls -lh launch/dsr_bringup2.launch.py

# RViz 포함 실행
ls -lh launch/dsr_bringup2_rviz.launch.py

# Gazebo 시뮬레이션
ls -lh launch/dsr_bringup2_gazebo.launch.py
```

### 2.2 런치 파일 분석
```bash
# 런치 파일 내용 확인
cat launch/dsr_bringup2_rviz.launch.py | head -100
```

**주요 파라미터**:
- `name`: 로봇 네임스페이스 (기본: dsr01)
- `model`: 로봇 모델 (m0609, m1013, a0509 등)
- `host`: 로봇 IP 주소
- `port`: 로봇 포트 (기본: 12345)
- `mode`: 실행 모드 (real/virtual)

### 2.3 하드웨어 인터페이스 살펴보기
```bash
cd ~/ros2_ws/src/DoosanBootcampCol2/dsr_hardware2
cat include/dsr_hardware2/dsr_hw_interface2.h | grep -A 5 "class DRHWInterface"
```

---

## 3. 기본 로봇 연결

### 3.1 네트워크 설정 확인
```bash
# 로봇과 같은 네트워크 대역 설정
ip addr show | grep "192.168.1"

# 로봇 네트워크가 192.168.1.x라면
sudo ip addr add 192.168.1.50/24 dev enxc84d442343d5

# 로봇 연결 테스트
ping -c 3 192.168.1.100
```

### 3.2 ROS2 도메인 설정
```bash
# ROS2 통신을 위한 도메인 ID 설정
export ROS_DOMAIN_ID=64
export ROS_LOCALHOST_ONLY=0
```

### 3.3 기본 로봇 드라이버 실행
```bash
# 터미널 1: 로봇 드라이버 실행
source /opt/ros/humble/setup.bash
source ~/ros2_ws/install/setup.bash
export ROS_DOMAIN_ID=64

ros2 launch dsr_bringup2 dsr_bringup2_rviz.launch.py \
    name:=dsr01 \
    model:=m0609 \
    host:=192.168.1.100 \
    port:=12345 \
    mode:=real
```

**로그 확인 포인트**:
- "OPEN CONNECTION" → 로봇 연결 성공
- "Access control granted" → 제어 권한 획득
- "Successful initialization of hardware" → 초기화 완료
- "current state: STANDBY" → 대기 상태

---

## 4. 로봇 제어 기초

### 4.1 ROS2 토픽 확인
```bash
# 터미널 2에서 실행
source /opt/ros/humble/setup.bash
source ~/ros2_ws/install/setup.bash
export ROS_DOMAIN_ID=64

# 로봇 관련 토픽 확인
ros2 topic list | grep dsr01

# 주요 토픽:
# /dsr01/joint_states - 관절 상태
# /dsr01/dsr_controller2/joint_command - 관절 명령
# /dsr01/tcp_pose - TCP 위치
```

### 4.2 관절 상태 모니터링
```bash
# 관절 위치 실시간 확인
ros2 topic echo /dsr01/joint_states

# 출력:
# name: [joint1, joint2, joint3, joint4, joint5, joint6]
# position: [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
# velocity: [...]
# effort: [...]
```

### 4.3 간단한 제어 명령 보내기
```bash
# 관절 명령 토픽 타입 확인
ros2 topic info /dsr01/dsr_controller2/joint_command

# Python으로 간단한 제어
python3 << 'EOF'
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState

rclpy.init()
node = Node('simple_controller')
pub = node.create_publisher(JointState, '/dsr01/dsr_controller2/joint_command', 10)

# 홈 포지션으로 이동 (모든 관절 0도)
msg = JointState()
msg.name = ['joint1', 'joint2', 'joint3', 'joint4', 'joint5', 'joint6']
msg.position = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]

for i in range(5):
    pub.publish(msg)
    rclpy.spin_once(node, timeout_sec=0.1)

node.destroy_node()
rclpy.shutdown()
EOF
```

---

## 5. 고급 제어

### 5.1 Python 제어 스크립트 만들기
```bash
# 새 파일 생성
mkdir -p ~/doosan_practice
cd ~/doosan_practice
```

**simple_control.py** 파일 생성:
```python
#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState
import time
import math

class DoosanController(Node):
    def __init__(self):
        super().__init__('doosan_controller')
        
        # Publisher for joint commands
        self.cmd_pub = self.create_publisher(
            JointState, 
            '/dsr01/dsr_controller2/joint_command', 
            10
        )
        
        # Subscriber for joint states
        self.state_sub = self.create_subscription(
            JointState,
            '/dsr01/joint_states',
            self.state_callback,
            10
        )
        
        self.current_position = [0.0] * 6
        
    def state_callback(self, msg):
        """현재 관절 상태 저장"""
        self.current_position = list(msg.position)
        
    def move_joints(self, positions, duration=2.0):
        """관절을 지정된 위치로 이동"""
        msg = JointState()
        msg.name = ['joint1', 'joint2', 'joint3', 'joint4', 'joint5', 'joint6']
        msg.position = positions
        
        start_time = time.time()
        while time.time() - start_time < duration:
            self.cmd_pub.publish(msg)
            rclpy.spin_once(self, timeout_sec=0.01)
            time.sleep(0.01)
            
    def home_position(self):
        """홈 포지션으로 이동"""
        self.get_logger().info('Moving to home position...')
        self.move_joints([0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        
    def wave_motion(self):
        """손 흔드는 동작"""
        self.get_logger().info('Waving...')
        
        # Joint 6을 좌우로 흔들기
        for i in range(3):
            self.move_joints([0.0, 0.0, 0.0, 0.0, 0.0, 45.0], 1.0)
            self.move_joints([0.0, 0.0, 0.0, 0.0, 0.0, -45.0], 1.0)
        
        self.home_position()

def main():
    rclpy.init()
    controller = DoosanController()
    
    try:
        # 홈 포지션으로 이동
        controller.home_position()
        time.sleep(1)
        
        # 손 흔들기
        controller.wave_motion()
        
    except KeyboardInterrupt:
        pass
    finally:
        controller.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
```

### 5.2 스크립트 실행
```bash
chmod +x simple_control.py

# ROS2 환경 설정 후 실행
source /opt/ros/humble/setup.bash
source ~/ros2_ws/install/setup.bash
export ROS_DOMAIN_ID=64

python3 simple_control.py
```

### 5.3 두산 DRCF 명령어 사용
```bash
# dsr_msgs2 메시지 확인
ros2 interface list | grep dsr_msgs2

# 주요 서비스:
# - MovejCmd: 관절 공간 이동
# - MovelCmd: 직교 공간 이동
# - SetDigitalOutput: 디지털 출력 제어
```

### 5.4 서비스 호출 예제
```bash
# 서비스 목록 확인
ros2 service list | grep dsr01

# 서비스 타입 확인
ros2 service type /dsr01/stop

# 로봇 정지
ros2 service call /dsr01/stop std_srvs/srv/Trigger
```

---

## 📚 참고 자료

### 패키지 문서
```bash
# 두산 로보틱스 GitHub
# https://github.com/doosan-robotics/doosan-robot2

# ROS2 Control 문서
# https://control.ros.org/
```

### 추가 학습 파일
```bash
# dsr_example 패키지 확인
cd ~/ros2_ws/src/DoosanBootcampCol2/dsr_example
ls -la
```

---

## 🔧 트러블슈팅

### 문제 1: 로봇 연결 실패
```bash
# 네트워크 확인
ping 192.168.1.100

# 방화벽 확인
sudo ufw status

# 로봇 TP에서 외부 제어 허용 확인
```

### 문제 2: "Access control denied"
- 로봇 TP(티치 펜던트)에서 외부 제어 모드 활성화
- 다른 프로그램이 로봇을 제어하고 있지 않은지 확인

### 문제 3: ros2_control_node 오류
```bash
# 로그 확인
ros2 node list
ros2 node info /dsr01/controller_manager

# 재시작
pkill -f ros2_control
# 로봇 드라이버 재실행
```

---

## 다음 단계

1. ✅ 기본 연결 및 제어 이해
2. ⬜ DRCF 명령어 학습
3. ⬜ 궤적 계획 (Trajectory Planning)
4. ⬜ 비전 시스템 연동
5. ⬜ 그리퍼 제어
6. ⬜ 시나리오 프로그래밍

---

**작성일**: 2025-12-20  
**환경**: ROS2 Humble, Ubuntu 22.04  
**로봇**: Doosan M0609
