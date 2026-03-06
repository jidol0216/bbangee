# 섹션 3: 개발 히스토리 (Trial & Error)

---

##  섹션 개요

| 항목 | 내용 |
|------|------|
| **주제** | 개발 과정의 시행착오 및 해결 과정 |
| **목표** | 어떤 문제를 만났고, 어떻게 해결했는지 기록 |
| **기간** | Day 1 ~ Day 5 (2025-12-08 ~ 2025-12-13) |

---

##  개발 타임라인

```
┌─────────────────────────────────────────────────────────────────┐
│                    개발 히스토리 타임라인                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Day 1 (12/08)    Day 2 (12/09)    Day 3 (12/10)              │
│     │                │                │                        │
│     ▼                ▼                ▼                        │
│  ┌──────┐        ┌──────┐        ┌──────┐                     │
│  │환경  │        │URDF  │        │얼굴  │                     │
│  │구축  │   →    │구성  │   →    │추적  │                     │
│  └──────┘        └──────┘        └──────┘                     │
│                                                                 │
│  Day 4 (12/11~12)  Day 5 (12/13)                              │
│     │                │                                         │
│     ▼                ▼                                         │
│  ┌──────┐        ┌──────┐                                     │
│  │EKF & │        │Joint │                                     │
│  │MPC   │   →    │Space │                                     │
│  └──────┘        └──────┘                                     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

#  Day 1: 환경 구축 (2025-12-08)

## 3.1 Day 1 개요

| 항목 | 내용 |
|------|------|
| **목표** | RGB-D 카메라, 그리퍼, Calibration 환경 구축 |
| **결과** |  기본 환경 구축 완료 |

---

##  작업 내용

### RealSense D435i 설정
```bash
# 카메라 런치
ros2 launch realsense2_camera rs_launch.py align_depth.enable:=true

# 주요 토픽
/camera/camera/color/image_raw           # Color 이미지 (30Hz)
/camera/camera/depth/image_rect_raw      # Depth 이미지 (30Hz)
/camera/camera/aligned_depth_to_color/image_raw  # 정렬된 Depth
```

### OnRobot RG2 그리퍼 설정
- Modbus 통신 설정 완료
- 파지력/스트로크 테스트

### Hand-Eye Calibration & TF 변환

> **왜 TF 변환과 좌표계가 중요한가?**

```
┌─────────────────────────────────────────────────────────────────┐
│              좌표계 변환의 중요성                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  카메라가 "얼굴이 (0.3, 0.1, 0.5)m에 있다"고 감지               │
│                  ↓                                              │
│  이 좌표는 카메라 기준! 로봇 기준이 아님!                        │
│                  ↓                                              │
│  로봇이 이해하려면 → 로봇 base_link 기준 좌표로 변환 필요        │
│                                                                 │
│  카메라 좌표계        →    변환 행렬    →    로봇 좌표계         │
│  (camera_link)           (TF2)            (base_link)          │
│     Z↑                                       Z↑                │
│     │  X→                                    │  Y→             │
│     Y↓                                       X↗                │
│                                                                 │
│   변환 없이: 로봇이 엉뚱한 곳 조준                             │
│   변환 적용: 정확한 위치 조준                                  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### TF2 변환 구현

```python
# face_tracking_node.py 에서의 TF2 좌표 변환
def transform_to_robot_frame(self, point_camera):
    """카메라 좌표 → 로봇 base_link 좌표 변환"""
    
    # 1. PointStamped 메시지 생성 (카메라 프레임 기준)
    point_stamped = PointStamped()
    point_stamped.header.frame_id = "camera_color_optical_frame"
    point_stamped.header.stamp = self.get_clock().now().to_msg()
    point_stamped.point.x = point_camera[0]
    point_stamped.point.y = point_camera[1]
    point_stamped.point.z = point_camera[2]
    
    # 2. TF2 버퍼에서 변환 조회 및 적용
    try:
        # camera_color_optical_frame → base_link 변환
        transformed = self.tf_buffer.transform(
            point_stamped,
            "base_link",          # 목표 프레임
            timeout=Duration(seconds=0.01)
        )
        return [transformed.point.x, 
                transformed.point.y, 
                transformed.point.z]
    except TransformException as e:
        self.get_logger().warn(f"TF 변환 실패: {e}")
        return None
```

### TF Tree 구성

```
world
  └── base_link (로봇 베이스)
        └── link1 → link2 → ... → link6 (로봇 관절)
              └── tool0 (엔드이펙터)
                    └── gripper_base_link
                          └── camera_link
                                └── camera_color_optical_frame (카메라 광학 프레임)
```

---

##  이슈 &  해결

### 이슈 #1: ROS_DOMAIN_ID 충돌
```
 문제: 다른 팀과 토픽 충돌
 해결: ROS_DOMAIN_ID 설정 (.bashrc에 추가)
   export ROS_DOMAIN_ID=30
```

### 이슈 #2: Depth 정렬 문제
```
 문제: Color/Depth 픽셀 불일치
 해결: align_depth.enable:=true 옵션 사용
```

### 이슈 #3: TF 변환 타임아웃
```
 문제: TF2 변환 시 0.1초 블로킹으로 속도 저하
 해결: 타임아웃 0.01초로 단축 + 캐싱
```

---

#  Day 2: URDF 구성 (2025-12-09)

## 3.2 Day 2 개요

| 항목 | 내용 |
|------|------|
| **목표** | 로봇 + 그리퍼 + 카메라 URDF 통합 |
| **결과** |  통합 URDF 완성 |

---

##  작업 내용

### URDF 통합
```
doosan_m0609
    └── tool0 (end-effector)
         └── gripper_base_link
              └── camera_link
                   └── camera_color_optical_frame
```

### TF Tree 구성
```
base_link → link1 → ... → link6 → tool0 → gripper → camera
```

---

##  이슈 &  해결

### 이슈 #1: TF 변환 오류
```
 문제: camera_link → base_link 변환 실패
 해결: URDF에 카메라 프레임 추가
   <joint name="camera_joint" type="fixed">
     <parent link="gripper_base_link"/>
     <child link="camera_link"/>
     <origin xyz="0.05 0 0.1" rpy="0 0.5 0"/>
   </joint>
```

---

#  Day 3: 얼굴 추적 시스템 (2025-12-10)

## 3.3 Day 3 개요

| 항목 | 내용 |
|------|------|
| **목표** | 실시간 얼굴 추적 시스템 구축 |
| **결과** |  30Hz 얼굴 추적 달성 |

---

##  Phase 1: 얼굴 감지 성능 개선 여정

> **목표**: 실시간 + 정확한 얼굴 감지

###  Step 1: Haar Cascade (기초 모델)

**시도한 이유**: OpenCV 기본 제공, 구현 간단

```python
# 최초 시도: Haar Cascade
face_cascade = cv2.CascadeClassifier('haarcascade_frontalface.xml')
gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
faces = face_cascade.detectMultiScale(gray, 1.3, 5)
```

**결과**:  실패

| 문제점 | 설명 |
|--------|------|
| 낮은 정확도 | 60-70% (조명 민감) |
| 측면 감지 불가 | 정면만 감지 |
| 느린 속도 | 30Hz에서 불안정 |
| 오탐지 많음 | 배경 물체를 얼굴로 인식 |

---

###  Step 2: MediaPipe Face Detection

**시도한 이유**: Google 제공, 정확도 높음, 경량화

```python
# 개선 시도: MediaPipe
import mediapipe as mp
mp_face = mp.solutions.face_detection
face_detection = mp_face.FaceDetection(model_selection=1)  # 5m 거리 모델
results = face_detection.process(rgb_image)
```

**결과**:  부분 성공

| 항목 | Haar Cascade | MediaPipe | 개선 |
|------|-------------|-----------|------|
| 정확도 | 60-70% | 90%+ | +30%p |
| FPS | 30Hz (불안정) | 60Hz+ | 2배 |
| 감지 거리 | 1m | 5m | 5배 |
| 측면 감지 |  |  | - |

**남은 아쉬움**:
- 먼 거리(5m+)에서 정확도 저하
- 작은 얼굴 검출 불안정
- 바운딩 박스 정밀도 부족

---

###  Step 3: YOLOv8-face

**시도한 이유**: 얼굴 특화 모델, 높은 정확도

```python
# 최종 선택: YOLOv8-face
from ultralytics import YOLO
model = YOLO('yolov8n-face.pt')
results = model(frame, conf=0.5)
```

**결과**:  성공, 하지만 새로운 문제 발생

| 항목 | MediaPipe | YOLOv8-face | 비고 |
|------|-----------|-------------|------|
| 정확도 | 90%+ | **95%+** | 향상 |
| 작은 얼굴 | 불안정 | **안정** | 향상 |
| 먼 거리 | 불안정 | **안정** | 향상 |
| **추론 속도** | **2ms** | **50ms** |  느림! |

---

###  Step 4: TensorRT FP16 최적화 (최종)

**문제**: YOLOv8 CPU/CUDA 추론이 50ms로 너무 느림

**해결**: TensorRT 엔진 변환 + FP16 최적화

```python
# TensorRT 엔진 변환 (1회)
model = YOLO('yolov8n-face.pt')
model.export(format='engine', half=True)  # FP16

# 추론 시 TensorRT 엔진 사용
model = YOLO('yolov8n-face.engine')
results = model(frame)  # ~5ms!
```

**최종 결과**:  성공

| 항목 | YOLOv8 (CUDA) | YOLOv8 (TensorRT) | 개선 |
|------|---------------|-------------------|------|
| 추론 속도 | ~50ms | **~5ms** | **10배** |
| 정확도 | 95%+ | 95%+ (동일) | - |
| GPU 메모리 | 2GB | 1GB | 절반 |

###  얼굴 감지 진화 요약

```
Haar Cascade   MediaPipe    YOLOv8-face   YOLOv8+TensorRT
    │              │             │              │
    ▼              ▼             ▼              ▼
  60-70%    →    90%+     →    95%+     →    95%+
  불안정    →    안정     →    느림     →    5ms!
                                              
[정확도 부족] [거리 한계] [속도 부족]  [최종 해결!]
```

---

##  Phase 2: 로봇 제어 문제 해결

###  문제: DSR 스레딩 데드락

> **데드락(Deadlock)이란?**
> 두 개 이상의 프로세스/스레드가 서로의 작업이 끝나기를 무한히 기다리는 상태.
> A가 B를 기다리고, B가 A를 기다리면 둘 다 영원히 멈춤.

```
 발생 상황:
┌──────────────────────────────────────────────────────────────┐
│  ROS2 Executor        DSR 내부 스레드                        │
│       │                     │                                │
│       │  로봇 명령 호출 →   │                                │
│       │     (대기...)       │ ← 응답 준비 중                 │
│       │                     │    (Executor 필요!)            │
│       │  ← 응답 대기        │                                │
│       │                     │                                │
│       ▼                     ▼                                │
│   [서로 무한 대기 - DEADLOCK!]                               │
└──────────────────────────────────────────────────────────────┘

 해결:
┌──────────────────────────────────────────────────────────────┐
│  SingleThreadedExecutor 사용                                 │
│       │                                                      │
│       │  순차적 처리 → 데드락 방지                           │
│       ▼                                                      │
│   [정상 동작]                                                │
└──────────────────────────────────────────────────────────────┘
```

```python
# 변경 전: 데드락 발생
executor = MultiThreadedExecutor()

# 변경 후: 데드락 해결
executor = SingleThreadedExecutor()
rclpy.spin(node, executor)
```

###  문제: 관절 인덱스 오류

```
오류: J5 상하 움직임이 J1으로 작동
원인: 관절 인덱스 잘못 매핑 (0-based vs 1-based)
```

###  해결: 인덱스 수정

```python
# 변경 전 (잘못된 매핑)
J1 = joints[0]  # 수평
J5 = joints[4]  # 상하 (잘못됨!)

# 변경 후 (올바른 매핑)
J1 = joints[0]  # 수평 (베이스 회전)
J4 = joints[3]  # 상하 (손목 피치) ← J5가 아니라 J4!
```

---

#  Day 4: EKF & MPC 구현 (2025-12-11~12)

## 3.4 Day 4 개요

| 항목 | 내용 |
|------|------|
| **목표** | 노이즈 필터링(EKF) + 예측 제어(MPC) |
| **결과** |  EKF 완성,  MPC 복잡도 이슈 |

---

##  Phase 1: 노이즈 문제와 EKF

### 문제: 센서 노이즈

```
RealSense Depth 노이즈:
- 정적 물체도 ±5~10mm 변동
- 로봇이 미세하게 떨림
- 추적 불안정
```

### 처음 시도한 방법들

| 방법 | 결과 | 문제점 |
|------|------|--------|
| 이동평균 (Moving Average) |  실패 | 지연 발생, 빠른 움직임 추적 불가 |
| 저역통과 필터 (LPF) |  부분 성공 | 반응 속도 저하 |
| Median 필터 |  부분 성공 | 속도 추정 불가 |

**공통 한계**: 노이즈는 줄지만, **미래 위치 예측 불가**

---

### EKF (Extended Kalman Filter)란?

> **칼만 필터**: 노이즈가 섞인 측정값에서 "진짜 상태"를 추정하는 알고리즘
> **EKF**: 비선형 시스템에 적용 가능한 확장 버전

```
┌─────────────────────────────────────────────────────────────────┐
│                    EKF의 핵심 아이디어                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  "측정값만 믿지 말고, 예측과 측정을 적절히 섞어라"              │
│                                                                 │
│  ┌─────────────┐      ┌─────────────┐      ┌─────────────┐     │
│  │   예측      │  +   │   측정      │  =   │  최적 추정  │     │
│  │ (물리 모델) │      │ (센서 값)   │      │ (노이즈 제거)│     │
│  └─────────────┘      └─────────────┘      └─────────────┘     │
│                                                                 │
│  예시:                                                          │
│  - 예측: "공이 시속 10m로 움직이니까 1초 후 10m 앞에 있을 것"   │
│  - 측정: "센서가 9.5m라고 하네? (노이즈 있음)"                  │
│  - 추정: "둘 다 고려하면 약 9.8m가 진짜일 것"                  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### EKF의 2단계 동작

```
┌─────────────────────────────────────────────────────────────────┐
│                     EKF 동작 원리                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   1단계: PREDICT (예측)                                       │
│  ─────────────────────────                                      │
│  "지금 위치와 속도를 알면, 다음 순간 어디 있을지 예측"          │
│                                                                 │
│     x(t+1) = x(t) + v(t)·dt + 0.5·a(t)·dt²                    │
│                                                                 │
│   2단계: UPDATE (갱신)                                        │
│  ────────────────────                                           │
│  "실제 측정값이 들어오면, 예측과 비교해서 보정"                 │
│                                                                 │
│     추정값 = 예측값 + K·(측정값 - 예측값)                      │
│                        ↑                                        │
│                   칼만 이득 (예측/측정 신뢰도 비율)             │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

###  해결: 9-state EKF 구현

```python
# 상태 벡터 (9차원) - 위치/속도/가속도 동시 추정
x = [x, y, z,      # 위치 (m)
     vx, vy, vz,   # 속도 (m/s)  ← 노이즈 필터링
     ax, ay, az]   # 가속도 (m/s²) ← 미래 예측 가능!

# EKF 파라미터
dt = 0.033  # 30Hz
Q = 0.1     # Process noise (작을수록 예측 신뢰)
R = 5.0     # Measurement noise (클수록 측정 불신)
```

###  EKF 효과

| 항목 | 적용 전 | 적용 후 | 개선 |
|------|--------|---------|------|
| 위치 노이즈 | ±10mm | ±3mm | 70% 감소 |
| 속도 추정 | 불가 | 가능 | - |
| 예측 가능 |  |  | - |
| 얼굴 소실 시 | 추적 종료 | 3초간 예측 유지 | - |

---

##  Phase 2: MPC 시도 & 한계

### MPC 설계

```python
# 최적화 문제 (QP)
minimize: Σ[||r-target||²_Q + ||u||²_R + ||Δu||²_S]
subject to:
    - 관절 한계: j_min ≤ j ≤ j_max
    - 속도 제한: |v| ≤ v_max
    - 가속도 제한: |a| ≤ a_max

파라미터:
- N=10: 예측 호라이즌
- Solver: OSQP
```

###  MPC 한계 발견

| 문제 | 설명 |
|------|------|
| 계산 시간 | ~20ms (30Hz 한계 초과) |
| 복잡도 | IK 필요, 특이점 문제 |
| 튜닝 어려움 | Q, R, S 파라미터 조정 난해 |

###  결론: 더 단순한 접근 필요

```
MPC (Cartesian Space) → 복잡, 느림
         ↓
Joint Space 직접 제어 → 단순, 빠름!
```

---

#  Day 5: Joint-Space 제어 (2025-12-13)

## 3.5 Day 5 개요

| 항목 | 내용 |
|------|------|
| **목표** | MPC → Joint-Space 전환 |
| **결과** |  50Hz 실시간 추적 달성 |

---

##  로봇 제어 기본 개념

### TCP 제어 vs 관절각 제어

> **TCP (Tool Center Point)**: 로봇 끝단(End-Effector)의 위치와 방향
> **관절각**: 각 로봇 관절의 회전 각도

```
┌─────────────────────────────────────────────────────────────────┐
│              TCP 제어 vs 관절각 제어 비교                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   TCP 제어 (Cartesian Space)                                  │
│  ─────────────────────────────                                  │
│  "로봇 끝단을 (X, Y, Z) 위치로 이동시켜"                        │
│                                                                 │
│  예시: movel([0.3, 0.1, 0.5, 0, 3.14, 0])  # X,Y,Z,Rx,Ry,Rz    │
│                                                                 │
│  장점:                                                          │
│  • 직관적 (사람이 이해하기 쉬움)                                │
│  • 직선 경로 보장                                               │
│                                                                 │
│  단점:                                                          │
│  • IK(역기구학) 계산 필요 (~50ms)                               │
│  • 특이점(Singularity) 문제                                     │
│  • 해가 없거나 여러 개일 수 있음                                │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   관절각 제어 (Joint Space)                                   │
│  ────────────────────────────                                   │
│  "각 관절을 [θ1, θ2, θ3, θ4, θ5, θ6]°로 이동시켜"              │
│                                                                 │
│  예시: movej([0, -45, 90, 0, 45, 0])  # 각 관절 각도            │
│                                                                 │
│  장점:                                                          │
│  • IK 불필요 (계산 빠름)                                        │
│  • 특이점 없음 (항상 도달 가능)                                 │
│  • 직접 제어 (중간 변환 없음)                                   │
│                                                                 │
│  단점:                                                          │
│  • 끝단 궤적이 직선이 아닐 수 있음                              │
│  • 사람이 직관적으로 이해하기 어려움                            │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 공통점과 차이점 정리

| 항목 | TCP 제어 (Cartesian) | 관절각 제어 (Joint) |
|------|---------------------|-------------------|
| **입력** | 3D 좌표 + 방향 (6 DOF) | 각 관절 각도 (N개) |
| **출력** | 관절 각도 (IK 계산 후) | 직접 관절 각도 |
| **IK 필요** |  필요 |  불필요 |
| **특이점** |  발생 가능 |  없음 |
| **계산 시간** | ~50ms | <1ms |
| **경로** | 직선 (Cartesian) | 곡선 (Joint) |
| **사용 예** | 용접, 조립 등 정밀 작업 | 빠른 이동, 회피 동작 |

---

##  Cartesian Space vs Joint Space 개념

> **출처**: ScienceDirect - "Modeling, Identification and Control of Robots" (2002), W Khalil, E Dombre
>
> **Joint Space (Configuration Space)**: 로봇의 모든 관절 변수 q∈ℜᴺ로 표현되는 공간. 차원 N은 자유도(DOF)와 같음.
>
> **Task Space (Cartesian Space)**: 엔드이펙터의 위치와 방향이 표현되는 공간. ℜ³×SO(3)로 표현되며, 최대 6 DOF.

```
┌─────────────────────────────────────────────────────────────────┐
│              Cartesian Space vs Joint Space                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   Cartesian Space (Task Space / 작업 공간)                    │
│  ───────────────────────────────────────────                    │
│  • 엔드이펙터(끝단)의 위치/방향을 나타내는 공간                  │
│  • 좌표: (X, Y, Z) 위치 + (Rx, Ry, Rz) 회전                     │
│  • 사람이 직관적으로 이해 가능                                   │
│  • 로봇 작업 정의에 사용 (용접점, 조립 위치 등)                  │
│                                                                 │
│      Z↑                                                         │
│       │  Y                                                      │
│       │ /                                                       │
│       │/___→ X                                                  │
│      O          ← 3D 직교 좌표계                                │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   Joint Space (Configuration Space / 관절 공간)               │
│  ──────────────────────────────────────────────                 │
│  • 각 관절의 각도/변위를 나타내는 공간                          │
│  • 좌표: [θ1, θ2, θ3, θ4, θ5, θ6]                              │
│  • 6축 로봇 → 6차원 공간                                        │
│  • 로봇 내부 제어에 사용                                        │
│                                                                 │
│    θ1      θ2      θ3      θ4      θ5      θ6                  │
│     ↺       ↺       ↺       ↺       ↺       ↺                  │
│     │───────│───────│───────│───────│───────│                  │
│    base                                    tool                 │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

##  특이점(Singularity) 문제

> **출처**: Universal Robots 공식 문서 - "What is a Singularity?"
>
> **특이점**: Cartesian Space에서 정의된 목표 위치로 이동 시, 역기구학(IK) 계산이 
> 불가능하거나 무한대의 관절 속도가 필요한 로봇 자세.

```
┌─────────────────────────────────────────────────────────────────┐
│                    특이점(Singularity) 이해                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   특이점이란?                                                  │
│  ──────────────                                                 │
│  로봇이 특정 자세에서 일부 방향으로 움직일 수 없거나,            │
│  매우 작은 끝단 이동에 엄청 빠른 관절 회전이 필요한 상태         │
│                                                                 │
│  비유: 팔을 완전히 펴면 팔꿈치 회전으로                         │
│        손을 좌우로 움직일 수 없는 것과 비슷                      │
│                                                                 │
│  UR 로봇의 주요 특이점:                                         │
│  ─────────────────────                                          │
│  1. Wrist Alignment: 손목 관절들이 일직선으로 정렬될 때          │
│  2. Overhead: 로봇 팔이 베이스 바로 위/아래에 있을 때            │
│  3. Reach Limit: 작업 영역 경계에서                             │
│                                                                 │
│   중요한 점:                                                   │
│  ─────────────                                                  │
│  • 특이점은 Cartesian Space 제어에서만 문제됨                   │
│  • Joint Space 제어는 특이점의 영향을 받지 않음                 │
│    (관절 각도를 직접 지정하므로 IK 계산이 불필요)               │
│                                                                 │
│  "MoveJ with joint angles option does not require kinematic     │
│   conversion and is not affected by Singularities"              │
│   - Universal Robots 공식 문서                                  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

##  핵심 전환: Cartesian → Joint Space

###  이전 방식 (Cartesian Space)

```
문제점:
1. IK(역기구학) 계산 필요 (~50ms)
2. 특이점(Singularity) 문제 - 일부 자세에서 이동 불가
3. 복잡한 경로 계획
4. 전신 움직임 (6관절 모두 이동)

[3D 좌표] → [IK 계산] → [6개 관절 각도] → [로봇]
              ↑
           병목! (~50ms)
           + 특이점 위험
```

###  새로운 방식 (Joint Space)

```
해결책:
1. IK 불필요 - 단순 삼각함수
2. 특이점 없음 - 직접 각도 제어 (관절 한계만 존재)
3. 빠른 응답 - <1ms 계산
4. 2개 관절만 사용 (J1 + J4)

[3D 좌표] → [구면좌표 변환] → [J1, J4 각도] → [로봇]
              ↑
           빠름! (<1ms)
           + 특이점 없음
```

### 핵심 알고리즘

```python
# 3D 위치 → 구면 좌표 → 관절 각도 변환
def compute_joint_targets(face_pos):
    x, y, z = face_pos
    
    # 수평 각도 (J1) - 베이스 회전
    azimuth = math.atan2(y, x)
    
    # 수직 각도 (J4) - 손목 피치
    distance_xy = math.sqrt(x**2 + y**2)
    elevation = math.atan2(z, distance_xy)
    
    # 시작 위치 + 오차 기반 목표 계산
    target_j1 = start_j1 + azimuth * gain_j1
    target_j4 = start_j4 + elevation * gain_j4
    
    return target_j1, target_j4
```

---

##  이슈 & 해결

### 이슈 #1: 로봇이 홈으로 이동

```
 문제: 추적 시작 시 로봇이 갑자기 홈 위치로 이동
 원인: 상대 각도 계산 (current_joints + error)
 해결: 절대 각도 계산 (start_joints + error)

# 변경 전 (잘못됨)
target = current_joints[0] + error  # 현재 위치 기준

# 변경 후 (올바름)
target = start_joints[0] + error    # 시작 위치 기준
```

### 이슈 #2: J4가 갑자기 0으로 점프

```
 문제: 추적 중 J4 값이 갑자기 0으로 변경
 원인: Joint state 센서 노이즈 (간헐적 무효 데이터)
 해결: 노이즈 필터 추가

def joint_state_callback(self, msg):
    j3, j4 = msg.position[2], msg.position[3]
    
    # 무효 상태 필터링
    if abs(j3) < 0.01 and abs(j4) < 0.01:
        return  # 무시
    
    # 급격한 점프 필터링
    if abs(j4 - self.current_j4) > 50.0:
        return  # 무시
    
    self.current_joints = msg.position
```

### 이슈 #3: robot_control_node 충돌

```
 문제: joint_tracking_node와 robot_control_node가 동시 실행 시 충돌
 원인: 둘 다 같은 EKF 토픽 사용
 해결: joint_tracking_node에 자체 EKF 내장

# 이전 (의존성 있음)
face_tracking → robot_control (EKF) → joint_tracking
                     ↑
                  충돌 발생!

# 이후 (자체 내장)
face_tracking → joint_tracking (자체 EKF)
                     ↓
                  독립 동작!
```

---

##  최종 성능 비교

### 제어 방식 비교

| 항목 | Cartesian (MPC) | Joint Space | 개선 |
|------|-----------------|-------------|------|
| IK 필요 |  필요 |  불필요 | - |
| 계산 시간 | ~50ms | **<1ms** | **50배** |
| 특이점 |  있음 |  없음 | - |
| 제어 주파수 | 20-30Hz | **50Hz** | **2배** |
| 정확도 | ±10mm | **±5mm** | **2배** |

### 처리 시간 분석

| 컴포넌트 | 시간 | 비고 |
|----------|------|------|
| TensorRT YOLO | 5ms | FP16 최적화 |
| Face Tracking | 2ms | TF2 + 좌표변환 |
| 자체 EKF | 0.15ms | 9-state |
| Joint Control | 0.5ms | 삼각함수 |
| **Total E2E** | **~8ms** | **125 FPS 가능** |

---

##  핵심 교훈 (Lessons Learned)

### 1. 단순함의 가치

```
복잡한 해결책 (MPC + IK)
  vs
단순한 해결책 (Joint Space)

→ 단순한 방법이 10배 빠르고, 더 안정적!
```

### 2. 병목 지점 파악의 중요성

```
성능 문제 발생 시:
1. 각 컴포넌트 개별 측정
2. 병목 지점 정확히 파악
3. 해당 부분만 집중 최적화

face_tracking 2-4Hz 병목 → 원인 분석 → 30Hz 달성
```

### 3. 점진적 개선

```
Day 1: 환경 구축
Day 2: URDF 통합
Day 3: 기본 추적 (30Hz)
Day 4: EKF 필터링
Day 5: Joint Space (50Hz)

→ 매일 한 단계씩 개선
```

---

##  참고 문서

| 문서 | 위치 |
|------|------|
| Day 1 Summary | `archive/face_tracking_pkg/day1/Day1_Summary.md` |
| Day 3 README | `archive/face_tracking_pkg/day3/README.md` |
| Day 4 EKF Guide | `archive/face_tracking_pkg/day4/EKF_TEST_GUIDE.md` |
| CHANGELOG | `archive/face_tracking_pkg/CHANGELOG_2025-12-13.md` |

---

> **작성자**: 태슬라 (헤드샷 트래킹 담당)  
> **최종 수정**: 2025-12-15  
> **상태**:  완료
