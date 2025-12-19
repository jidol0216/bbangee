# 🤖 실시간 얼굴 추적 로봇 시스템
## Doosan M0609 + RealSense D435i + ROS2
### Rokey Bootcamp Col2 Team

---

# 📋 발표 목차

1. **전체 시나리오** - 군 위병소 자동화 시스템
2. **프로젝트 소개** - 무엇을 만들었나?
3. **문제 정의** - 왜 어려운가?
4. **개발 히스토리** - 어떻게 해결했나? (Day 1~4)
5. **MPC → Joint 전환** - 왜 제어 방식을 바꿨나?
6. **시스템 아키텍처** - 전체 구조
7. **기술 선택 비교** - 왜 이 기술을 선택했나?
8. **핵심 알고리즘 (이론)** - EKF, Joint Control 수학적 배경
9. **결과 및 성과** - 무엇을 달성했나?
10. **미완성 모듈 & 향후 계획**

---

# 🎯 전체 시나리오: 군 위병소 자동화 시스템 (ver1)

## 📍 배경
- **장소**: 군 부대 위병소
- **상황**: 로봇팔이 초병 역할 수행
- **목표**: 자동화된 경계 및 피아식별 시스템

## 🔄 전체 시퀀스

```
┌─────────────────────────────────────────────────────────────────────┐
│ STEP 1: 권총 파지 (SAM3 팀)                                          │
│   → 아무렇게 올려진 권총을 SAM3 기반 그리퍼로 파지                      │
│   → Segment Anything Model 3 활용                                    │
└─────────────────────────────────────────────────────────────────────┘
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│ STEP 2: 사격 위치 이동                                               │
│   → 사로(射路)에 권총 고정                                            │
│   → 다시 파지 후 준비 자세                                            │
└─────────────────────────────────────────────────────────────────────┘
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│ STEP 3: 사주 경계 ★ 현재 구현 완료                                   │
│   → 헤드샷 트래킹 (YOLOv8-face + EKF + Joint Control)                │
│   → 레이저 포인터 활성화 (가장 가까운 사람 우선)                        │
│   → 실시간 30fps 감지, ~15ms E2E 지연                                │
└─────────────────────────────────────────────────────────────────────┘
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│ STEP 4: 피아 식별                                                    │
│   → 아군/적군 학습 데이터 기반 클래스 구분                              │
│   → YOLOv8 Classification 또는 Face Recognition                     │
└─────────────────────────────────────────────────────────────────────┘
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│ STEP 5: 암구호 판정 & 대응                                           │
│   → STT로 암구호 수신 → TTS로 응답                                    │
│   → 판정 결과에 따른 분기 처리                                        │
└─────────────────────────────────────────────────────────────────────┘
```

## 🔀 피아식별 분기 로직

```
                        ┌─────────────────┐
                        │   피아 식별 결과  │
                        └────────┬────────┘
                                 │
            ┌────────────────────┴────────────────────┐
            ▼                                         ▼
    ┌───────────────┐                        ┌───────────────┐
    │    👤 아군     │                        │    💀 적군     │
    └───────┬───────┘                        └───────┬───────┘
            │                                        │
            ▼                                        ▼
    "암구호를 말하라"                          "암구호를 말하라"
            │                                        │
      ┌─────┴─────┐                            ┌─────┴─────┐
      ▼           ▼                            ▼           ▼
   ✅ 정답     ❌ 오답                      ✅ 정답     ❌ 오답
      │           │                            │           │
      ▼           ▼                            ▼           ▼
   🔊 "통과"   📸 웹캠 캡처              📸 웹캠 캡처   🔫 헤드샷
   음성출력    + 웹 UI 알림              + 웹 UI 경고    발사!
```

---

# 1️⃣ 프로젝트 소개

## 🎯 목표
> **"로봇이 사람 얼굴을 실시간으로 추적하며 바라본다"**

## 🎬 데모
```
[여기에 데모 GIF/영상 삽입]

로봇이 사람이 움직이는 방향을 따라
자연스럽게 시선을 이동하는 모습
```

## 💡 핵심 가치
| 항목 | 설명 | 측정값 |
|------|------|--------|
| **실시간성** | 고속 감지 & 빠른 반응 | 30fps 감지, ~8ms E2E 지연 |
| **안정성** | EKF 기반 노이즈 제거 | ~70% 노이즈 감소 (코드 주석 기준) |
| **단순성** | IK 없이 조인트 직접 제어 | 2축만 제어 (J1, J4) |

---

# 2️⃣ 문제 정의

## ❓ 얼굴 추적이 왜 어려운가?

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   얼굴 감지   │ ──▶ │  3D 위치 추정  │ ──▶ │   로봇 제어   │
│  (2D 이미지)  │     │  (깊이 정보)   │     │ (6축 매니퓰레이터)│
└──────────────┘     └──────────────┘     └──────────────┘
       ↓                    ↓                    ↓
   🔴 노이즈 多          🔴 좌표계 복잡         🔴 특이점 문제
   🔴 조명 변화          🔴 깊이 오차           🔴 IK 계산 복잡
   🔴 측면 얼굴          🔴 동기화 문제         🔴 반응 지연
```

## 🎯 우리가 풀고자 한 문제

1. **빠른 감지**: 실시간 30fps 이상
2. **정확한 추정**: 3D 위치 오차 최소화
3. **부드러운 제어**: 떨림 없는 로봇 동작
4. **안전한 동작**: 특이점/충돌 방지

## 📐 좌표계 변환 문제 (이론)

### 카메라 좌표계 vs 로봇 좌표계
```
카메라 좌표계 (RealSense):     로봇 좌표계 (Doosan):
       Z (앞)                         Z (위)
        ↑                              ↑
        │                              │
        │                              │
        └───→ X (오른쪽)              └───→ X (앞)
       ╱                              ╱
      Y (아래)                       Y (왼쪽)
```

### Homogeneous 변환 행렬

카메라 좌표계의 점을 로봇 base 좌표계로 변환:

$$
^{base}T_{camera} = ^{base}T_{link6} \cdot ^{link6}T_{gripper} \cdot ^{gripper}T_{camera}
$$

$$
^{base}P_{face} = ^{base}T_{camera} \cdot ^{camera}P_{face}
$$

여기서 $^{A}T_{B}$는 좌표계 B에서 좌표계 A로의 4x4 동차 변환 행렬

---

# 3️⃣ 개발 히스토리

## 📅 전체 타임라인

```
Dec 8 (Day 1)  ──▶  Dec 9 (Day 2)  ──▶  Dec 10 (Day 3)  ──▶  Dec 12-13 (Day 4)
    │                   │                    │                      │
    ▼                   ▼                    ▼                      ▼
┌─────────┐      ┌───────────┐      ┌────────────────┐      ┌─────────────────┐
│ 환경 구축 │      │ YOLO 학습  │      │ MediaPipe+MPC  │      │ YOLOv8+EKF+Joint│
│ 캘리브레이션│      │ CNN 이론   │      │ 얼굴추적 v1    │      │ 최종 시스템      │
└─────────┘      └───────────┘      └────────────────┘      └─────────────────┘
```

### 🔧 기술 스택 발전
```
감지: Haar Cascade ───▶ MediaPipe ───▶ YOLOv8 + TensorRT
      (Day 3 초기)      (Day 3)        (Day 4)
      
추적: 없음 ───▶ Moving Average ───▶ EKF 9-state
                 (Day 3)            (Day 4)
                 
제어: 없음 ───▶ MPC/Cartesian ───▶ Joint-space Direct
                (Day 3 시도)        (Day 4 최종)
```

---

## 📅 Day 1: 환경 구축 및 캘리브레이션 (Dec 8)

### 📝 작업 내용

| 작업 | 상세 | 결과 |
|------|------|------|
| **카메라 설정** | RealSense D435i 런치 | ✅ 30Hz RGB+Depth (Intel 스펙) |
| **Modbus 통신** | OnRobot RG2 그리퍼 | ✅ 열기/닫기 제어 |
| **캘리브레이션** | Eye-on-Hand | ✅ T_gripper2camera.npy |
| **URDF 작성** | 로봇+그리퍼+카메라 | ✅ TF 트리 완성 |

### 📐 Hand-Eye Calibration (이론)

Eye-on-Hand 문제의 수학적 정의:

$$
AX = XB
$$

여기서:
- $A$: 로봇 엔드이펙터의 상대 이동 (known)
- $B$: 카메라가 관측한 캘리브레이션 타겟의 상대 이동 (known)
- $X$: 그리퍼 → 카메라 변환 (unknown, 구하고자 하는 것)

### 💡 배운 점
```
카메라와 로봇 좌표계가 다르다!
  카메라: X-오른쪽, Y-아래, Z-앞
  로봇:   X-앞, Y-왼쪽, Z-위

  → TF2로 자동 변환 필요
```

---

## 📅 Day 2: 딥러닝 기초 및 YOLO 학습 (Dec 9)

### 📝 학습 내용

```
┌──────────────────────────────────────────────────────────┐
│ 📚 이론                                                   │
├──────────────────────────────────────────────────────────┤
│ • CNN 구조: Conv → Pool → FC                             │
│ • Object Detection: R-CNN → YOLO 발전 과정               │
│ • YOLO 원리: Single-shot detection, Grid division        │
└──────────────────────────────────────────────────────────┘
```

### 📐 YOLO 아키텍처 (이론)

**Bounding Box Prediction:**

$$
b_x = \sigma(t_x) + c_x, \quad b_y = \sigma(t_y) + c_y
$$

$$
b_w = p_w \cdot e^{t_w}, \quad b_h = p_h \cdot e^{t_h}
$$

여기서:
- $(t_x, t_y, t_w, t_h)$: 네트워크 출력 (raw prediction)
- $(c_x, c_y)$: Grid cell의 좌상단 좌표
- $(p_w, p_h)$: Anchor box 크기
- $\sigma$: Sigmoid 함수

**Confidence Score:**

$$
\text{Conf} = P(\text{Object}) \times \text{IoU}_{pred}^{truth}
$$

**Loss Function (간략화):**

$$
L = \lambda_{coord} L_{coord} + \lambda_{obj} L_{obj} + \lambda_{noobj} L_{noobj} + \lambda_{class} L_{class}
$$

### 💡 인사이트
> "얼굴 검출에는 일반 YOLO보다 **얼굴 특화 모델**이 필요하다"
> → YOLOv8n-face 모델 발견 (WiderFace 데이터셋 학습)

---

## 📅 Day 3: 실시간 추적 시스템 v1 (Dec 10)

### 🔴 문제 1: Haar Cascade 정확도 부족

```
시도: OpenCV Haar Cascade
결과: 측면 얼굴 감지 불가, 조명 민감

해결: MediaPipe Face Detection 교체
```

### 🔴 문제 2: face_tracking_node 병목

```
현상: Detection 30Hz → Tracking 2-4Hz (87% 손실!)
     📊 day3/README.md 로그 기반 실측

원인 분석:
  ❌ 타이머 주기 0.1초 (10Hz)
  ❌ Depth 5x5 영역 Median 계산
  ❌ TF2 타임아웃 0.1초 블로킹

해결:
  ✅ 타이머 0.033초 (30Hz)
  ✅ Depth 3x3 영역 Trimmed Mean
  ✅ TF2 타임아웃 0.01초

결과: 2-4Hz → 30.3Hz (약 10배 향상!)
     📊 day3/README.md:177-181 측정 기록
```

### 🔴 문제 3: MPC 제어기 구현 시도

MPC (Model Predictive Control) 비용 함수:

$$
J = \sum_{k=0}^{N} \left[ Q \cdot ||x_k - x_{ref}||^2 + R \cdot ||u_k||^2 + S \cdot ||\Delta u_k||^2 \right]
$$

```
파라미터 (day3/README.md 기준):
  N = 10 (예측 호라이즌)
  Q = 100 (추적 오차 가중치)
  R = 1 (제어 입력 가중치)
  S = 10 (부드러움 가중치)
  
문제: IK 계산 + 특이점 → Day 4에서 Joint-space로 전환
```

### 📊 Day 3 성과

| 항목 | 이전 | 개선 후 | 근거 |
|------|------|---------|------|
| Tracking Hz | 2-4Hz | 30.3Hz | day3/README.md 실측 |
| 카메라 FPS | 설정값 | 29.97-30.11Hz | day3/README.md:177-181 실측 |

---

## 📅 Day 4: 최종 시스템 완성 (Dec 12-13)

### ⚡ Phase 1: YOLO + TensorRT 최적화

```
🚀 변경사항:
  - YOLOv8n-face 도입 (6MB 경량 모델)
  - ONNX → TensorRT 엔진 변환
  - FP16 Half Precision 추론

📊 성능 (CHANGELOG_2025-12-13.md 실측 기준):
  - TensorRT YOLO: ~5ms
  - 자체 EKF: ~0.15ms
  - Joint Control: ~0.5ms
  - Total E2E: ~8ms (~125fps 이론치)
```

### ⚡ Phase 2: MPC/Cartesian 제어 시도 → 실패

```
시도: movel() 기반 직선 이동 제어

문제:
  ❌ IK 계산 지연 → 실시간성 저하
  ❌ 특이점(Singularity) 근처에서 불안정
  ❌ 복잡한 제약 조건 처리 필요

→ 제어 전략 재검토 결정!
```

### ⚡ Phase 3: Joint-space 직접 제어 (최종 해결책)

```
💡 핵심 인사이트:
  "얼굴 추적은 결국 '방향 추적' 문제다"
  → 위치가 아닌 방향만 맞추면 된다!
  → 조인트 각도로 직접 제어하면 IK 불필요!

🎯 제어 전략:
  J1: 수평 방향 (베이스 회전) - 메인
  J4: 수직 방향 (손목 피치) - 서브
  J2, J3, J5, J6: 고정 (팔 자세 유지)
```

### ⚡ Phase 4: 9-state EKF 구현

```
효과 (PACKAGE_STRUCTURE.md 실측 기준):
  ✅ 노이즈 ~70% 감소 (코드 주석)
  ✅ 처리 시간: ~0.15ms/frame
  ✅ CPU 사용률: ~4.5%
```

---

# 4️⃣ MPC → Joint-space 전환

## 🚨 MPC 제어기의 문제점

### 문제 1: Inverse Kinematics (IK) 지연

```
MPC (Model Predictive Control) 파이프라인:

  목표 위치 (x,y,z) → IK 계산 → 관절각 (θ1...θ6) → 로봇 이동
                         ↓
                    ⏱️ 계산 시간 병목
```

### 📐 6-DOF IK 문제 (이론)

로봇 기구학의 Forward Kinematics:

$$
^{0}T_6 = \prod_{i=1}^{6} \, ^{i-1}T_i(\theta_i)
$$

Inverse Kinematics는 다음을 만족하는 $\theta_1, ..., \theta_6$를 찾는 문제:

$$
^{0}T_6(\theta_1, ..., \theta_6) = T_{desired}
$$

**문제점:**
- 6개 비선형 방정식 시스템
- 해가 없거나 (unreachable), 무한개 (redundant)
- **특이점(Singularity)** 근처에서 해 불안정

### 문제 2: 특이점 (Singularity)

```
┌─────────────────────────────────────────────────────────────┐
│ 특이점 (Singularity) 조건:                                   │
│                                                             │
│   det(J) = 0  또는  det(J) ≈ 0                              │
│                                                             │
│   J = Jacobian 행렬 (관절 속도 → 말단 속도 변환)              │
│                                                             │
│ 현상:                                                        │
│   • J가 특이(singular)하면 역행렬 계산 불가                   │
│   • 작은 말단 이동에 큰 관절 속도 필요                        │
│   • 로봇이 멈추거나 급격한 동작                               │
└─────────────────────────────────────────────────────────────┘
```

### 📐 Jacobian 행렬 (이론)

말단 속도와 관절 속도의 관계:

$$
\dot{x} = J(\theta) \cdot \dot{\theta}
$$

여기서:
- $\dot{x} \in \mathbb{R}^6$: 말단 속도 (선속도 + 각속도)
- $\dot{\theta} \in \mathbb{R}^6$: 관절 속도
- $J(\theta) \in \mathbb{R}^{6 \times 6}$: Jacobian 행렬

**특이점 근처:**

$$
\dot{\theta} = J^{-1}(\theta) \cdot \dot{x}
$$

$\det(J) \to 0$ 이면 $||J^{-1}|| \to \infty$ → 관절 속도 폭발!

---

## 💡 발상의 전환: 위치 추적 → 방향 추적

```
┌─────────────────────────────────────────────────────────────────┐
│ 기존 MPC 접근 (위치 추적)                                        │
│                                                                 │
│   "로봇 End-Effector를 얼굴 위치(x,y,z)로 이동시켜라"            │
│   → 6축 IK 계산 필요 → 특이점 위험 → 복잡함                      │
└─────────────────────────────────────────────────────────────────┘
                                ▼
                          🔄 발상 전환!
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│ 새로운 Joint 접근 (방향 추적)                                    │
│                                                                 │
│   "로봇이 얼굴 방향만 바라보면 된다!"                             │
│   → 2축만 제어 (J1: 수평, J4: 수직)                             │
│   → IK 불필요 → 특이점 없음 → 단순함                            │
└─────────────────────────────────────────────────────────────────┘
```

### 🎯 핵심 인사이트

> "로봇팔 끝에 레이저 포인터가 달려있다고 생각하면,  
>  레이저가 얼굴을 가리키기만 하면 됨!"

---

## 📊 MPC vs Joint-space 비교

| 항목 | MPC (Day 3) | Joint-space (Day 4) |
|------|-------------|---------------------|
| **IK 계산** | 필요 (6축) | 불필요 |
| **특이점 위험** | 있음 (치명적) | 없음 |
| **제어 주기** | ~10Hz (추정) | 50Hz (코드 설정) |
| **구현 복잡도** | 높음 | 낮음 |
| **안정성** | 불안정 | 매우 안정 |
| **코드 라인** | ~300줄 (추정) | ~100줄 |

### 📐 성능 비교 (CHANGELOG_2025-12-13.md 실측 기준)

| 항목 | Cartesian Space | Joint Space |
|------|-----------------|-------------|
| 응답 속도 | ~50ms | ~20ms |
| 제어 주파수 | 30Hz | 50Hz |

---

# 5️⃣ 시스템 아키텍처

## 🏗️ 전체 파이프라인

```
┌─────────────────────────────────────────────────────────────────────┐
│                         RealSense D435i                              │
│                      (RGB 640x480 + Depth)                           │
│                    스펙: 30Hz, Intel 공식                            │
└───────────────────────────────┬─────────────────────────────────────┘
                                │ 30Hz
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     Face Detection Node                              │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐    │
│  │   CLAHE    │→│  YOLOv8    │→│    ROI     │→│  Confidence │    │
│  │ 전처리     │  │  -face     │  │  Tracking  │  │  Filtering  │    │
│  └────────────┘  └────────────┘  └────────────┘  └────────────┘    │
│                  TensorRT FP16: ~5ms (CHANGELOG 실측)                │
└───────────────────────────────┬─────────────────────────────────────┘
                                │ /face_detection/faces
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     Face Tracking Node                               │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐    │
│  │   Depth    │→│    TF2     │→│    EKF     │→│   Marker    │    │
│  │ Extraction │  │ Transform  │  │  9-state   │  │  Publish    │    │
│  └────────────┘  └────────────┘  └────────────┘  └────────────┘    │
│              EKF: ~0.15ms, TF2+EKF: ~2ms (CHANGELOG 실측)            │
└───────────────────────────────┬─────────────────────────────────────┘
                                │ /face_tracking/marker_robot
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Joint Tracking Node                               │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐    │
│  │   Angle    │→│   Dead     │→│  Velocity  │→│  Jog Multi  │    │
│  │ Calculation│  │   Zone     │  │  Control   │  │   Axis      │    │
│  └────────────┘  └────────────┘  └────────────┘  └────────────┘    │
│              제어 주기: 50Hz (코드 설정), ~0.5ms (CHANGELOG 실측)     │
└───────────────────────────────┬─────────────────────────────────────┘
                                │ /dsr01m0609/jog_multi
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       Doosan M0609                                   │
│                    실시간 얼굴 추적 동작                               │
└─────────────────────────────────────────────────────────────────────┘
```

### 📊 처리 시간 분석 (CHANGELOG_2025-12-13.md 실측 기준)

| 컴포넌트 | 시간 | CPU % |
|----------|------|-------|
| TensorRT YOLO | ~5ms | 150% |
| Face Tracking (TF2+EKF) | ~2ms | 60% |
| Joint Control | ~0.5ms | 15% |
| 자체 EKF | ~0.15ms | 4.5% |
| **Total E2E** | **~8ms** | ~230% |

---

## 📡 ROS2 토픽 구조

```
┌─────────────────────────────────────────────────────────────────┐
│ 구독 (Subscribe)                                                 │
├─────────────────────────────────────────────────────────────────┤
│ /camera/camera/color/image_raw          → Detection Node        │
│ /camera/camera/aligned_depth_to_color   → Tracking Node         │
│ /face_detection/faces                   → Tracking Node         │
│ /face_tracking/marker_robot             → Joint Control Node    │
│ /dsr01/joint_states                     → Joint Control Node    │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ 발행 (Publish)                                                   │
├─────────────────────────────────────────────────────────────────┤
│ /face_detection/image                   ← Detection Node        │
│ /face_detection/faces                   ← Detection Node        │
│ /face_tracking/marker_robot             ← Tracking Node         │
│ /face_tracking/marker_camera            ← Tracking Node         │
│ /dsr01m0609/jog_multi                   ← Joint Control Node    │
└─────────────────────────────────────────────────────────────────┘
```

---

# 6️⃣ 기술 선택 비교

## 🔍 얼굴 감지 기술 비교

| 기술 | 속도 | GPU | 선택 | 비고 |
|------|------|-----|------|------|
| **Haar Cascade** | 30fps | ❌ | ❌ | Day3 초기 시도, 측면 얼굴 약함 |
| **dlib HOG** | 10fps | ❌ | ❌ | 느림 |
| **MediaPipe** | 60fps | △ | △ | Day3 사용, Google 공식 |
| **YOLOv8-face** | 30fps+ | ✅ | ✅ | **최종 선택** |
| **RetinaFace** | 20fps | ✅ | ❌ | 오버킬 |

> **참고**: 정확도 수치는 WiderFace 벤치마크 기준이며, 실제 환경 정확도는 별도 측정 필요

### 💡 YOLOv8-face 선택 이유
```
1. 속도: TensorRT로 ~5ms (CHANGELOG 실측)
2. 경량: 6MB (임베디드 가능)
3. 통합: Ultralytics 프레임워크
4. 학습: WiderFace 데이터셋 사전학습
```

---

## 🔍 추적 필터 비교

| 필터 | 예측 | 계산량 | 선택 |
|------|------|--------|------|
| **Moving Average** | ❌ | O(1) | ❌ |
| **Low-pass Filter** | ❌ | O(1) | ❌ |
| **Kalman (6-state)** | 속도만 | O(n²) | △ |
| **EKF (9-state)** | 가속도 | O(n²) | ✅ **최종 선택** |
| **Particle Filter** | 비선형 | O(N·n) | ❌ 연산량 |

### 💡 9-state EKF 선택 이유
```
1. 가속도 예측: 빠른 움직임 대응
2. 처리 시간: ~0.15ms (CHANGELOG 실측)
3. CPU 사용률: ~4.5% (PACKAGE_STRUCTURE 실측)
```

---

## 🔍 로봇 제어 방식 비교

| 방식 | IK 필요 | 특이점 | 제어 주기 | 선택 |
|------|---------|--------|-----------|------|
| **Cartesian movel()** | ✅ | 위험 | ~30Hz | ❌ |
| **MoveIt** | ✅ | 안전 | ~10Hz | ❌ |
| **Joint-space Jog** | ❌ | 없음 | 50Hz | ✅ **최종 선택** |

### 💡 Joint-space 제어 선택 이유
```
핵심 인사이트:
  "얼굴 추적 = 방향 추적 문제"
  
  → 로봇이 특정 위치로 갈 필요 없음
  → 얼굴 방향만 바라보면 됨
  → J1(수평) + J4(수직) 직접 제어로 충분!
```

---

# 7️⃣ 핵심 알고리즘 (이론)

## 🧮 Extended Kalman Filter (9-state)

### 상태 벡터 정의

$$
\mathbf{x} = \begin{bmatrix} x \\ y \\ z \\ v_x \\ v_y \\ v_z \\ a_x \\ a_y \\ a_z \end{bmatrix} \in \mathbb{R}^9
$$

- 위치: $(x, y, z)$ - 3D 공간 좌표
- 속도: $(v_x, v_y, v_z)$ - 각 축 방향 속도
- 가속도: $(a_x, a_y, a_z)$ - 각 축 방향 가속도

### 상태 전이 방정식 (등가속도 운동 모델)

물리학의 등가속도 운동 공식을 이산화:

$$
p_k = p_{k-1} + v_{k-1} \cdot \Delta t + \frac{1}{2} a_{k-1} \cdot \Delta t^2
$$

$$
v_k = v_{k-1} + a_{k-1} \cdot \Delta t
$$

$$
a_k = a_{k-1} \quad \text{(가속도 일정 가정)}
$$

### 상태 전이 행렬 $F$

$$
F = \begin{bmatrix}
I_3 & \Delta t \cdot I_3 & \frac{\Delta t^2}{2} \cdot I_3 \\
0_3 & I_3 & \Delta t \cdot I_3 \\
0_3 & 0_3 & I_3
\end{bmatrix} \in \mathbb{R}^{9 \times 9}
$$

여기서 $I_3$는 3×3 단위행렬, $0_3$는 3×3 영행렬

### 측정 행렬 $H$

카메라에서 위치만 측정 가능:

$$
H = \begin{bmatrix} I_3 & 0_3 & 0_3 \end{bmatrix} \in \mathbb{R}^{3 \times 9}
$$

### Kalman Filter 알고리즘

**Predict Step (예측):**

$$
\hat{\mathbf{x}}_k^- = F \cdot \hat{\mathbf{x}}_{k-1}
$$

$$
P_k^- = F \cdot P_{k-1} \cdot F^T + Q
$$

**Update Step (갱신):**

$$
K_k = P_k^- \cdot H^T \cdot (H \cdot P_k^- \cdot H^T + R)^{-1}
$$

$$
\hat{\mathbf{x}}_k = \hat{\mathbf{x}}_k^- + K_k \cdot (\mathbf{z}_k - H \cdot \hat{\mathbf{x}}_k^-)
$$

$$
P_k = (I - K_k \cdot H) \cdot P_k^-
$$

여기서:
- $Q$: 프로세스 노이즈 공분산 (모델 불확실성)
- $R$: 측정 노이즈 공분산 (센서 불확실성)
- $K_k$: 칼만 게인 (예측 vs 측정 신뢰도 균형)

### 노이즈 공분산 설정 (ekf_filter.py 기준)

```python
process_noise = 0.5      # 작을수록 예측 신뢰 ↑
measurement_noise = 0.8  # 클수록 측정 불신 ↑
```

---

## 🎮 Joint-space 제어 알고리즘

### 제어 목표

카메라 좌표계에서 얼굴이 중앙(0, 0)에 오도록 로봇 제어

### 📐 기하학적 분석

얼굴 위치 $P_{face} = (x, y, z)$ (로봇 base 좌표계 기준)

**수평 각도 (J1 제어):**

$$
\theta_{horizontal} = \arctan2(y, x)
$$

**수직 각도 (J4 제어):**

$$
\theta_{vertical} = \arctan2(z - z_{ee}, \sqrt{x^2 + y^2})
$$

여기서 $z_{ee}$는 엔드이펙터 높이

### 비례 제어 (P-Control)

$$
\dot{\theta}_{J1} = K_p \cdot e_{horizontal}
$$

$$
\dot{\theta}_{J4} = K_p \cdot e_{vertical}
$$

### Dead Zone (불감대)

작은 오차에 대한 떨림 방지:

$$
\dot{\theta} = \begin{cases}
K_p \cdot e & \text{if } |e| > \theta_{dead} \\
0 & \text{otherwise}
\end{cases}
$$

### 속도 제한 (Saturation)

$$
\dot{\theta}_{cmd} = \text{clip}(\dot{\theta}, -\dot{\theta}_{max}, \dot{\theta}_{max})
$$

### 파라미터 (joint_tracking_node.py 코드 기준)

| 파라미터 | 값 | 설명 |
|----------|-----|------|
| $K_p$ | 0.5 | 비례 게인 |
| $\theta_{dead}$ | 2° | 불감대 |
| $\dot{\theta}_{max,J1}$ | 30°/s | J1 최대 속도 |
| $\dot{\theta}_{max,J4}$ | 40°/s | J4 최대 속도 |
| 제어 주기 | 50Hz (20ms) | 코드 설정 (dt=0.02) |

---

## 📐 3D 깊이 추정 (Depth Estimation)

### Pinhole Camera Model

픽셀 좌표 $(u, v)$와 깊이 $d$로부터 3D 좌표 복원:

$$
X = \frac{(u - c_x) \cdot d}{f_x}
$$

$$
Y = \frac{(v - c_y) \cdot d}{f_y}
$$

$$
Z = d
$$

여기서:
- $(c_x, c_y)$: 주점 (principal point)
- $(f_x, f_y)$: 초점 거리 (픽셀 단위)

### 행렬 형태

$$
\begin{bmatrix} X \\ Y \\ Z \\ 1 \end{bmatrix} = 
\begin{bmatrix}
1/f_x & 0 & -c_x/f_x & 0 \\
0 & 1/f_y & -c_y/f_y & 0 \\
0 & 0 & 1 & 0 \\
0 & 0 & 0 & 1
\end{bmatrix}
\begin{bmatrix} u \cdot d \\ v \cdot d \\ d \\ 1 \end{bmatrix}
$$

### RealSense D435i Intrinsics (일반적인 640x480 값)

```
fx ≈ 615.0, fy ≈ 615.0
cx ≈ 320.0, cy ≈ 240.0
```

---

# 8️⃣ 결과 및 성과

## 📊 측정 데이터 출처 정리

| 항목 | 값 | 출처 | 신뢰도 |
|------|-----|------|--------|
| **카메라 FPS** | 29.97-30.11 Hz | day3/README.md:177-181 | ✅ 실측 |
| **Tracking Hz** | 2-4Hz → 30.3Hz | day3/README.md | ✅ 실측 |
| **TensorRT 추론** | ~5ms | CHANGELOG_2025-12-13.md | ✅ 실측 |
| **EKF 처리시간** | ~0.15ms | CHANGELOG_2025-12-13.md | ✅ 실측 |
| **Joint Control** | ~0.5ms | CHANGELOG_2025-12-13.md | ✅ 실측 |
| **Total E2E** | ~8ms | CHANGELOG_2025-12-13.md | ✅ 계산 |
| **제어 주기** | 50Hz | 코드 설정 (dt=0.02) | ✅ 코드 |
| **노이즈 감소** | ~70% | PACKAGE_STRUCTURE.md 주석 | ⚠️ 추정 |

## 📈 Day 1 → Day 4 발전

```
Day 1    Day 2    Day 3    Day 4
  │        │        │        │
  ▼        ▼        ▼        ▼
┌────┐  ┌────┐  ┌────┐  ┌────┐
│ 0% │  │20% │  │60% │  │100%│  ◀ 시스템 완성도
└────┘  └────┘  └────┘  └────┘
```

| 발전 단계 | 변경 내용 | 측정 가능 개선 |
|-----------|----------|----------------|
| Day 1 | 환경 구축 | - |
| Day 2 | 이론 학습 | - |
| Day 3 | MediaPipe + MPC | Tracking 2-4Hz → 30.3Hz (실측) |
| Day 4 | YOLOv8 + EKF + Joint | E2E ~8ms 달성 (실측) |

## ✅ 정성적 성과

```
✅ 조명 변화에도 안정적 감지 (CLAHE 전처리)
✅ 빠른 머리 움직임도 부드럽게 추적 (EKF 예측)
✅ 특이점 문제 없이 연속 동작 (Joint-space)
✅ 지터링/떨림 최소화 (Dead Zone)
```

---

# 9️⃣ 미완성 모듈 & 향후 계획

## 📦 전체 시스템 완성도

| 모듈 | 담당 | 상태 | 패키지 |
|------|------|------|--------|
| **헤드샷 트래킹** | 태슬라 | ✅ 완료 | face_tracking |
| **SAM3 파지** | 성우 | 🔄 진행중 | sam3_grip_detection |
| **피아 식별** | 경훈 | 🔄 진행중 | (TBD) |
| **음성 암구호** | 지원 | 🔄 진행중 | (TBD) |
| **웹 UI** | TBD | ⏳ 대기 | (TBD) |
| **시스템 통합** | All | ⏳ 대기 | (TBD) |

## 🔧 미완성 모듈 상세

### 📌 SAM3 기반 파지 (sam3_grip_detection)
```
• Segment Anything Model 3 활용
• 권총 그립 포인트 자동 인식
• OnRobot RG2 그리퍼 연동
• 위치: /home/rokey/ros2_ws/src/sam3_grip_detection
```

### 📌 피아 식별 모듈
```
• 아군/적군 이미지 학습 데이터 구축
• YOLOv8 Classification 또는 Face Recognition
• 헤드샷 트래킹 결과와 연동
```

### 📌 음성 암구호 시스템
```
• STT: 음성 → 텍스트 (Whisper 등)
• TTS: 텍스트 → 음성 (gTTS, pyttsx3 등)
• 암구호 판정 로직 구현
```

## 🔗 통합 시퀀스 다이어그램

```
┌───────────────────────────────────────────────────────────────────┐
│                     미구현 (SAM3 팀 담당)                          │
│  ┌─────────┐    ┌─────────────┐    ┌─────────────┐               │
│  │ 권총 감지│ → │ SAM3 그립   │ → │ 파지 & 사로 │               │
│  │         │    │ 포인트 인식 │    │ 이동        │               │
│  └─────────┘    └─────────────┘    └─────────────┘               │
└───────────────────────────────────────────────────────────────────┘
                                ▼
┌───────────────────────────────────────────────────────────────────┐
│                     ✅ 구현 완료 (태슬라)                          │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐           │
│  │ 얼굴 감지   │ → │ EKF 추적    │ → │ Joint 제어  │           │
│  │ YOLOv8-face │    │ 9-state     │    │ J1+J4       │           │
│  └─────────────┘    └─────────────┘    └─────────────┘           │
└───────────────────────────────────────────────────────────────────┘
                                ▼
┌───────────────────────────────────────────────────────────────────┐
│                     미구현 (경훈 + 지원 담당)                      │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐           │
│  │ 피아 식별   │ → │ 암구호 판정 │ → │ 발사/경고   │           │
│  │ 아군/적군   │    │ STT + TTS   │    │ 웹 UI       │           │
│  └─────────────┘    └─────────────┘    └─────────────┘           │
└───────────────────────────────────────────────────────────────────┘
```

## 🚀 향후 통합 계획

```
📅 Week 1: 개별 모듈 완성
   • SAM3 파지: 권총 그립 인식 완성
   • 피아 식별: 학습 데이터 & 모델 구축
   • 음성: STT/TTS 파이프라인 구현

📅 Week 2: 시스템 통합
   • ROS2 Topic/Service 인터페이스 정의
   • 모듈간 통신 테스트
   • 전체 시퀀스 연결 (State Machine)

📅 Week 3: 테스트 & 데모
   • 시나리오 테스트 (정상/예외 케이스)
   • 예외 상황 처리 (얼굴 미감지, 음성 인식 실패 등)
   • 최종 데모 준비
```

---

# 📚 기술 스택 요약

```
┌─────────────────────────────────────────────────────────────────┐
│ Hardware                                                         │
├─────────────────────────────────────────────────────────────────┤
│ • Doosan M0609 (6-DOF Manipulator)                              │
│ • Intel RealSense D435i (RGB-D Camera, 30Hz 스펙)               │
│ • OnRobot RG2 (Gripper)                                         │
│ • NVIDIA RTX 4060 (GPU)                                         │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ Software                                                         │
├─────────────────────────────────────────────────────────────────┤
│ • ROS2 Humble (Framework)                                        │
│ • Python 3.10 (Language)                                         │
│ • YOLOv8n-face + TensorRT FP16 (Detection, ~5ms 실측)           │
│ • Extended Kalman Filter (Tracking, ~0.15ms 실측)               │
│ • TF2 (Coordinate Transform)                                     │
│ • OpenCV, NumPy, FilterPy (Libraries)                           │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ Algorithms                                                       │
├─────────────────────────────────────────────────────────────────┤
│ • 9-state EKF (Constant Acceleration Model)                      │
│ • Joint-space Direct Control (No IK, J1+J4)                     │
│ • ROI-based Fast Tracking                                        │
│ • Confidence History Filtering                                   │
└─────────────────────────────────────────────────────────────────┘
```

---

# 🙏 감사합니다

## 📎 참고 자료

- GitHub: https://github.com/taesla/rokey_c_1_collabo2
- Branch: ros-face-tracking

## 👥 팀원

- Rokey Bootcamp Col2 Team

---

# 📑 부록 A: Git 커밋 히스토리

```
a57bd75 Dec 13 Pre-refactoring backup
b6ef2b0 Dec 13 feat: Joint-space face tracking with EKF
0025ec6 Dec 12 v1.2.1: 반응속도 튜닝 + J4 활성화
b05e2d2 Dec 12 v1.2.0: YOLOv8 + TensorRT 최적화
7c5ff23 Dec 12 v1.1.0: 안전구역 클램핑 + 부드러운 제어
cadc69d Dec 12 v1.0.0: RGB 투영 라인 + 조준선
d375ac2 Dec 12 feat: Cartesian Space Velocity Control
7908574 Dec 12 feat: EKF 통합
d7fe89f Dec 10 Day3: 카메라 30Hz 검증
9bb575c Dec 10 Day3: MediaPipe + MPC 시스템
1338774 Dec 09 Day2: YOLO 학습/추론
91d9562 Dec 08 Day1: Hand-Eye Calibration
ef3effc Dec 08 Day1: OnRobot RG2 gripper setup
```

---

# 📑 부록 B: 팩트 체크 요약

## ✅ 실측/검증된 데이터 (높은 신뢰도)

| 항목 | 값 | 출처 |
|------|-----|------|
| 카메라 FPS | 29.97-30.11 Hz | day3/README.md:177-181 |
| Tracking 개선 | 2-4Hz → 30.3Hz | day3/README.md |
| TensorRT YOLO | ~5ms | CHANGELOG_2025-12-13.md |
| 자체 EKF | ~0.15ms | CHANGELOG_2025-12-13.md |
| Joint Control | ~0.5ms | CHANGELOG_2025-12-13.md |
| Total E2E | ~8ms | CHANGELOG_2025-12-13.md (계산) |
| 제어 주기 | 50Hz | joint_tracking_node.py (dt=0.02) |
| 추적 타이머 | 100Hz | face_tracking_node.py |

## ⚠️ 추정/참고 데이터 (별도 실측 권장)

| 항목 | 값 | 근거 |
|------|-----|------|
| YOLOv8-face 정확도 | - | WiderFace 벤치마크 참고, 별도 실측 필요 |
| EKF 노이즈 감소 | ~70% | PACKAGE_STRUCTURE.md 코드 주석 |
| Haar Cascade 정확도 | - | 일반적 성능 참고, 별도 실측 필요 |
| MediaPipe 정확도 | - | Google 공식 문서 참고, 별도 실측 필요 |

## 📐 이론적/스펙 기준 수치

| 항목 | 근거 |
|------|------|
| RealSense D435i 30Hz | Intel 공식 스펙 |
| EKF 수학적 모델 | 표준 Kalman Filter 이론 |
| Jacobian/특이점 | 로봇 기구학 이론 |

---

# 📑 부록 C: 수식 정리

## Kalman Filter 핵심 수식

| 수식 | 설명 |
|------|------|
| $\hat{\mathbf{x}}_k^- = F \cdot \hat{\mathbf{x}}_{k-1}$ | 상태 예측 |
| $P_k^- = F P_{k-1} F^T + Q$ | 공분산 예측 |
| $K_k = P_k^- H^T (H P_k^- H^T + R)^{-1}$ | 칼만 게인 |
| $\hat{\mathbf{x}}_k = \hat{\mathbf{x}}_k^- + K_k (\mathbf{z}_k - H \hat{\mathbf{x}}_k^-)$ | 상태 갱신 |

## 좌표 변환 수식

| 수식 | 설명 |
|------|------|
| $^{base}P = ^{base}T_{camera} \cdot ^{camera}P$ | 카메라 → 로봇 좌표 변환 |
| $X = (u - c_x) \cdot d / f_x$ | 픽셀 → 3D X 좌표 |
| $\theta = \arctan2(y, x)$ | 수평 방향 각도 |

## 제어 수식

| 수식 | 설명 |
|------|------|
| $\dot{\theta} = K_p \cdot e$ | 비례 제어 |
| $\dot{\theta}_{cmd} = \text{clip}(\dot{\theta}, \pm\dot{\theta}_{max})$ | 속도 제한 |
