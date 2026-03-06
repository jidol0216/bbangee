# OnRobot RG2 Gripper RViz Synchronization

> **실제 그리퍼 상태를 RViz에서 실시간으로 시각화하는 ROS2 패키지**

Doosan M0609 로봇에 장착된 OnRobot RG2 그리퍼의 실제 동작 상태를 Modbus TCP 통신으로 읽어와 RViz URDF 모델과 동기화합니다.

---

##  목차

1. [개요](#1-개요)
2. [시스템 아키텍처](#2-시스템-아키텍처)
3. [하드웨어 분석 및 설계 근거](#3-하드웨어-분석-및-설계-근거)
4. [통신 프로토콜 설계](#4-통신-프로토콜-설계)
5. [URDF 조인트 매핑](#5-urdf-조인트-매핑)
6. [ROS2 토픽 구조](#6-ros2-토픽-구조)
7. [설치 및 사용법](#7-설치-및-사용법)
8. [트러블슈팅](#8-트러블슈팅)
9. [참고 자료](#9-참고-자료)

---

## 1. 개요

### 1.1 문제 정의

기존 RViz 시각화에서 그리퍼는 항상 **고정된 상태(열린 상태)**로 표시되어, 실제 로봇 작업 시 그리퍼의 현재 상태를 시각적으로 확인할 수 없었습니다.

**목표:**
- 실제 그리퍼가 닫히면 → RViz에서도 닫힘
- 실제 그리퍼가 열리면 → RViz에서도 열림
- 실시간 동기화 (30Hz)

### 1.2 해결 방안 탐색

그리퍼 상태를 ROS2에서 읽어오는 방법을 조사한 결과, 두 가지 옵션이 있었습니다:

| 연결 방식 | 장점 | 단점 |
|-----------|------|------|
| **Tool Flange I/O** | 간단한 배선 | ON/OFF만 가능, **위치 피드백 불가** |
| **Modbus TCP (LAN)** | 위치 제어 + **피드백 가능** | Compute Box 필요 |

**결론:** Modbus TCP를 통한 위치 피드백 방식 선택

---

## 2. 시스템 아키텍처

```
┌─────────────────────────────────────────────────────────────────────┐
│                        실제 하드웨어                                  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────┐         LAN          ┌──────────────────────┐    │
│  │  Doosan      │◄───────────────────►│  OnRobot             │    │
│  │  M0609       │   192.168.1.100     │  Compute Box         │    │
│  │  Controller  │                      │  192.168.1.1:502     │    │
│  └──────────────┘                      └──────────┬───────────┘    │
│                                                   │                │
│                                         ┌─────────▼─────────┐      │
│                                         │  OnRobot RG2      │      │
│                                         │  Gripper          │      │
│                                         └───────────────────┘      │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ Modbus TCP
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        ROS2 노드 구조                                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │  gripper_state_publisher                                    │    │
│  │  ├─ Modbus TCP 연결 (pymodbus)                              │    │
│  │  ├─ 현재 폭(mm) 읽기 → Register 267                         │    │
│  │  ├─ 폭 → 조인트 각도 변환                                    │    │
│  │  └─ /gripper/joint_states 발행                              │    │
│  └────────────────────────────────────────────────────────────┘    │
│                           │                                         │
│                           ▼                                         │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │  joint_state_merger                                         │    │
│  │  └─ /dsr01/joint_states로 그리퍼 조인트 발행                 │    │
│  └────────────────────────────────────────────────────────────┘    │
│                           │                                         │
│                           ▼                                         │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │  robot_state_publisher (기존)                               │    │
│  │  ├─ 로봇 6축 + 그리퍼 2축 조인트 수신                        │    │
│  │  └─ TF 변환 발행 → RViz                                     │    │
│  └────────────────────────────────────────────────────────────┘    │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                           RViz2                                      │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  RobotModel                                                  │   │
│  │  ├─ /dsr01/joint_states 구독                                 │   │
│  │  ├─ URDF 조인트 위치 업데이트                                 │   │
│  │  └─ 로봇 + 그리퍼 실시간 시각화                               │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3. 하드웨어 분석 및 설계 근거

### 3.1 OnRobot Compute Box 분석

OnRobot WebClient 대시보드 (`http://192.168.1.1`)를 통해 다음 정보를 확인했습니다:

**Device Info:**
| 항목 | 값 |
|------|-----|
| 모델 | RG2 |
| Serial Number | 1000037065 |
| Firmware | 1.0.6#766B45AE |
| Compute Box | CBV35610 (Firmware 150) |

**Network Settings:**
| 항목 | 값 |
|------|-----|
| IP Address | 192.168.1.1 |
| Subnet Mask | 255.255.255.0 |
| Digital I/O Mode | PNP |
| DHCP Server | Enabled |

**실시간 상태 (Monitor and Control 탭):**
- Current width: 실시간 폭 표시 (0~110mm)
- Grip detected: 물체 감지 상태
- Force 설정: 3~40N
- Width 설정: 0~101mm (Fingertip offset 포함)

### 3.2 Doosan 컨트롤러 네트워크 분석

**Doosan Robotics 설치 매뉴얼 (V2.8)**에서 확인한 네트워크 구성:

```
컨트롤러 네트워크 포트:
├─ WAN: 외부 인터넷 망 연결
├─ LAN1~3: TCP/IP, Modbus 프로토콜 주변기기 연결
│          IP 대역: 192.168.137.xxx
└─ LAN4: 내부 제어기용 (사용 금지)
```

**I/O 인터페이스 매뉴얼**에서 확인한 Tool Flange I/O 제한:
- M8 8핀 커넥터 2개 (X1, X2)
- 디지털 입출력만 지원 (ON/OFF)
- **위치 피드백 불가** → Modbus TCP 선택의 근거

### 3.3 Modbus TCP 프로토콜 선택 근거

**OnRobot RG2 Modbus Register Map** (GitHub: ian-chuang/OnRobot-RG2FT-ROS 참고):

| Register | 기능 | 범위 | 단위 |
|----------|------|------|------|
| 0 (Write) | Target Force | 0-400 | 0.1N |
| 1 (Write) | Target Width | 0-1100 | 0.1mm |
| 2 (Write) | Control | 1 = Grip | - |
| 267 (Read) | **Current Width** | 0-1100 | 0.1mm |
| 268 (Read) | Grip Detected | 0/1 | - |
| 258 (Read) | Device Type | 45 (RG2) | - |

**연결 설정:**
- Host: 192.168.1.1
- Port: 502 (Modbus TCP 표준)
- Unit ID: 65 (OnRobot 기본값)

### 3.4 실제 Modbus 통신 테스트

```python
from pymodbus.client.sync import ModbusTcpClient

client = ModbusTcpClient('192.168.1.1', port=502)
client.connect()

# 현재 폭 읽기
result = client.read_holding_registers(267, 1, unit=65)
width_mm = result.registers[0] / 10.0  # 0.1mm → mm
print(f"현재 그리퍼 폭: {width_mm} mm")  # 출력: 11.0 mm

# 그리퍼 열기 (80mm)
client.write_register(0, 200, unit=65)  # Force: 20N
client.write_register(1, 800, unit=65)  # Width: 80mm
client.write_register(2, 1, unit=65)    # Command: Grip
```

**테스트 결과:**
-  Modbus 연결 성공
-  그리퍼 폭 읽기 성공 (실시간)
-  그리퍼 제어 성공 (열기/닫기)

---

## 4. 통신 프로토콜 설계

### 4.1 데이터 흐름

```
OnRobot RG2          Modbus TCP          ROS2 Node           RViz
    │                    │                    │                │
    │◄───Read Reg 267────│                    │                │
    │────Width (0.1mm)──►│                    │                │
    │                    │────width_mm───────►│                │
    │                    │                    │──joint_angle──►│
    │                    │                    │                │
    │◄──Write Reg 0,1,2──│◄───width_cmd───────│                │
    │                    │                    │                │
```

### 4.2 폭 → 조인트 각도 변환

**문제:** 
- 실제 그리퍼: 0mm = 닫힘, 110mm = 열림
- URDF 조인트: 0 rad = 열림, 1.3 rad = 닫힘 (반대!)

**해결 (반전 매핑):**
```python
def width_to_joint_angle(self, width_mm: float) -> float:
    # 0~110mm → 0~1로 정규화
    normalized = width_mm / 110.0
    
    # 반전: 0mm(닫힘) → 1.3rad, 110mm(열림) → 0rad
    angle = (1.0 - normalized) * 1.3
    
    return angle
```

| 실제 그리퍼 | 정규화 | 조인트 각도 | RViz 상태 |
|-------------|--------|-------------|-----------|
| 0mm (닫힘) | 0.0 | 1.3 rad | 닫힘 |
| 55mm | 0.5 | 0.65 rad | 중간 |
| 110mm (열림) | 1.0 | 0.0 rad | 열림 |

---

## 5. URDF 조인트 매핑

### 5.1 기존 URDF 분석

**onrobot_description** 패키지의 URDF 구조:

```xml
<!-- 메인 그리퍼 조인트 (revolute) -->
<joint name="gripper_joint" type="revolute">
  <limit lower="0.0" upper="1.3" effort="..." velocity="..."/>
</joint>

<!-- 미러 조인트 (반대쪽 손가락) -->
<joint name="gripper_mirror_joint" type="revolute">
  <mimic joint="gripper_joint" multiplier="1"/>
</joint>
```

**핵심 발견:**
- 조인트 타입: `revolute` (움직임 가능) 
- 조인트 이름: `gripper_joint`, `gripper_mirror_joint`
- 조인트 limit: 0.0 ~ 1.3 rad

### 5.2 조인트 이름 매핑

초기에 잘못된 조인트 이름을 사용하여 동기화가 안 되었습니다:

| 시도 | 조인트 이름 | 결과 |
|------|-------------|------|
|  1차 | `gripper_finger_left_joint` | URDF에 없음 |
|  최종 | `gripper_joint`, `gripper_mirror_joint` | 동작 |

**확인 방법:**
```bash
ros2 param get /dsr01/robot_state_publisher robot_description | grep -o '"gripper[^"]*joint"'
```

---

## 6. ROS2 토픽 구조

### 6.1 발행 토픽

| 토픽 | 타입 | 설명 | 발행 주기 |
|------|------|------|-----------|
| `/gripper/joint_states` | `sensor_msgs/JointState` | 그리퍼 조인트 상태 | 30Hz |
| `/gripper/width/current` | `std_msgs/Float32` | 현재 폭 (mm) | 30Hz |
| `/gripper/grip_detected` | `std_msgs/Bool` | 물체 감지 | 30Hz |

### 6.2 구독 토픽

| 토픽 | 타입 | 설명 |
|------|------|------|
| `/gripper/width/command` | `std_msgs/Float32` | 목표 폭 명령 (mm) |
| `/gripper/force/command` | `std_msgs/Float32` | 목표 힘 명령 (N) |

### 6.3 서비스

| 서비스 | 타입 | 설명 |
|--------|------|------|
| `/gripper/open` | `std_srvs/Trigger` | 그리퍼 열기 (80mm) |
| `/gripper/close` | `std_srvs/Trigger` | 그리퍼 닫기 (0mm) |

### 6.4 토픽 흐름 다이어그램

```
gripper_state_publisher
        │
        ├──► /gripper/joint_states ──► joint_state_merger ──► /dsr01/joint_states
        │                                                            │
        ├──► /gripper/width/current                                  ▼
        │                                                    robot_state_publisher
        └──► /gripper/grip_detected                                  │
                                                                     ▼
gripper_controller                                              RViz (TF)
        │
        ├──◄ /gripper/width/command
        ├──◄ /gripper/force/command
        ├──◄ /gripper/open (service)
        └──◄ /gripper/close (service)
```

---

## 7. 설치 및 사용법

### 7.1 의존성

```bash
# pymodbus 설치
pip3 install pymodbus
```

### 7.2 빌드

```bash
cd ~/ros2_ws
colcon build --packages-select gripper_rviz_sync
source install/setup.bash
```

### 7.3 실행

**터미널 1: 로봇 + RViz**
```bash
ros2 launch gripper_camera_description dsr_bringup2_with_gripper.launch.py \
    mode:=real host:=192.168.1.100 port:=12345 model:=m0609
```

**터미널 2: 그리퍼 동기화**
```bash
ros2 launch gripper_rviz_sync gripper_sync.launch.py
```

### 7.4 그리퍼 제어

```bash
# 그리퍼 열기
ros2 service call /gripper/open std_srvs/srv/Trigger

# 그리퍼 닫기
ros2 service call /gripper/close std_srvs/srv/Trigger

# 특정 폭으로 이동 (50mm)
ros2 topic pub --once /gripper/width/command std_msgs/msg/Float32 "data: 50.0"

# 힘 설정 (25N)
ros2 topic pub --once /gripper/force/command std_msgs/msg/Float32 "data: 25.0"

# 현재 폭 확인
ros2 topic echo /gripper/width/current
```

### 7.5 연결 테스트

```bash
# Modbus 연결 테스트
python3 ~/ros2_ws/src/gripper_rviz_sync/test_gripper.py 1

# 그리퍼 이동 테스트
python3 ~/ros2_ws/src/gripper_rviz_sync/test_gripper.py 2

# ROS2 토픽 발행 테스트
python3 ~/ros2_ws/src/gripper_rviz_sync/test_gripper.py 3
```

---

## 8. 트러블슈팅

### 8.1 RViz에서 그리퍼가 움직이지 않음

**원인 1: 조인트 이름 불일치**
```bash
# URDF의 조인트 이름 확인
ros2 param get /dsr01/robot_state_publisher robot_description | grep -o '"gripper[^"]*joint"'
```

**원인 2: 조인트 타입이 fixed**
- URDF에서 조인트 타입이 `fixed`이면 움직이지 않음
- `onrobot_description` 패키지는 `revolute` 타입 사용 (OK)

### 8.2 그리퍼 방향이 반대로 움직임

**원인:** 실제 그리퍼와 URDF의 방향이 반대

**해결:** `gripper_state_publisher.py`에서 반전 매핑 적용
```python
angle = (1.0 - normalized) * self.joint_max_angle
```

### 8.3 RViz에서 그리퍼가 튀는 현상

**원인:** 동일 토픽에 여러 publisher가 발행
```bash
ros2 topic info /dsr01/joint_states
# Publisher count: 2 이상이면 문제
```

**해결:** 런치 파일을 하나만 실행

### 8.4 Modbus 연결 실패

```bash
# ping 테스트
ping 192.168.1.1

# 네트워크 인터페이스 확인
ip addr | grep 192.168.1
```

**해결:** PC IP를 192.168.1.x 대역으로 설정

---

## 9. 참고 자료

### 9.1 공식 문서

| 문서 | 내용 |
|------|------|
| Doosan Robotics 설치 매뉴얼 V2.8 | 네트워크 구성, I/O 인터페이스 |
| Doosan Robotics 프로그래밍 매뉴얼 V2.8 | Modbus TCP Slave 설정 |
| OnRobot WebClient (192.168.1.1) | 그리퍼 상태 모니터링, 네트워크 설정 |

### 9.2 GitHub 레포지토리

| 레포지토리 | 참고 내용 |
|------------|-----------|
| [ian-chuang/OnRobot-RG2FT-ROS](https://github.com/ian-chuang/OnRobot-RG2FT-ROS) | Modbus 레지스터 맵 |
| [inria-paris-robotics-lab/onrobot_ros](https://github.com/inria-paris-robotics-lab/onrobot_ros) | URDF 구조, 조인트 이름 |

### 9.3 분석한 핵심 정보

**OnRobot Compute Box WebClient 캡처:**
- Device Info: RG2, S/N 1000037065, FW 1.0.6
- Network: 192.168.1.1, Subnet 255.255.255.0
- Current width: 실시간 표시 (Modbus 피드백 가능 확인)
- WebLogic: I/O 기반 제어 프로그램 (우리는 Modbus 직접 사용)

**Doosan I/O 인터페이스 PDF:**
- Tool Flange: M8 8핀, 디지털 I/O만 지원
- 네트워크: M-series는 WAN 1개 + LAN 3개
- Modbus/TCP: Master(UI) / Slave(BG) 지원

---

##  파일 구조

```
gripper_rviz_sync/
├── package.xml
├── CMakeLists.txt
├── README.md
├── test_gripper.py              # 연결/제어 테스트 스크립트
├── config/
│   └── gripper_config.yaml      # 설정 파일
├── gripper_rviz_sync/
│   ├── __init__.py
│   ├── gripper_state_publisher.py   # Modbus → ROS2 조인트 상태
│   ├── gripper_controller.py        # ROS2 → Modbus 제어
│   └── joint_state_merger.py        # 그리퍼 조인트 발행
├── launch/
│   └── gripper_sync.launch.py   # 전체 시스템 런치
└── urdf/
    └── onrobot_rg2_movable.urdf.xacro  # (참고용) 움직이는 URDF
```

---

##  License

MIT License

##  Contributors

- ROKEY Bootcamp Team

---

*Last Updated: 2025-12-16*
