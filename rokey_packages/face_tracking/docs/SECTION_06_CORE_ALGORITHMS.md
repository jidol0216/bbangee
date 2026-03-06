# 섹션 6: 핵심 알고리즘

---

##  섹션 개요

| 항목 | 내용 |
|------|------|
| **주제** | 시스템에 사용된 핵심 알고리즘 상세 설명 |
| **목표** | 수식, 이론, 구현 코드를 통한 알고리즘 이해 |
| **범위** | EKF, Joint Control, 좌표 변환, 노이즈 필터링 |

---

##  6.1 Extended Kalman Filter (EKF)

### 6.1.1 개요

> **목적**: 센서 노이즈 제거 및 상태(위치/속도/가속도) 추정

```
┌─────────────────────────────────────────────────────────────────┐
│                         EKF 역할                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  입력 (측정값)              EKF                출력 (추정값)     │
│  ─────────────         ─────────────         ─────────────      │
│                                                                 │
│  [x, y, z]    ─────▶   ┌───────────┐  ─────▶  [x, y, z]        │
│  (노이즈 있음)          │  9-state  │          (노이즈 제거)     │
│                        │   EKF     │                            │
│                        │           │  ─────▶  [vx, vy, vz]      │
│                        │           │          (속도 추정)        │
│                        │           │                            │
│                        │           │  ─────▶  [ax, ay, az]      │
│                        └───────────┘          (가속도 추정)      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 6.1.2 상태 벡터

**9차원 상태 벡터:**

$$
\mathbf{x} = \begin{bmatrix} x \\ y \\ z \\ v_x \\ v_y \\ v_z \\ a_x \\ a_y \\ a_z \end{bmatrix} \in \mathbb{R}^9
$$

| 상태 | 의미 | 단위 |
|------|------|------|
| $x, y, z$ | 3D 위치 | m |
| $v_x, v_y, v_z$ | 3D 속도 | m/s |
| $a_x, a_y, a_z$ | 3D 가속도 | m/s² |

### 6.1.3 상태 전이 모델

**운동 방정식 (등가속도 운동):**

$$
\begin{aligned}
x_{k+1} &= x_k + v_x \cdot \Delta t + \frac{1}{2} a_x \cdot \Delta t^2 \\
v_{x,k+1} &= v_{x,k} + a_x \cdot \Delta t \\
a_{x,k+1} &= a_{x,k}
\end{aligned}
$$

**상태 전이 행렬 F:**

$$
F = \begin{bmatrix}
I_3 & \Delta t \cdot I_3 & \frac{\Delta t^2}{2} \cdot I_3 \\
0_3 & I_3 & \Delta t \cdot I_3 \\
0_3 & 0_3 & I_3
\end{bmatrix} \in \mathbb{R}^{9 \times 9}
$$

여기서 $I_3$는 3×3 단위행렬, $0_3$는 3×3 영행렬

### 6.1.4 측정 모델

**측정 벡터:**

$$
\mathbf{z} = \begin{bmatrix} x_{meas} \\ y_{meas} \\ z_{meas} \end{bmatrix} \in \mathbb{R}^3
$$

**측정 행렬 H:**

$$
H = \begin{bmatrix}
I_3 & 0_3 & 0_3
\end{bmatrix} \in \mathbb{R}^{3 \times 9}
$$

### 6.1.5 EKF 알고리즘

**1. 예측 단계 (Prediction):**

$$
\begin{aligned}
\hat{\mathbf{x}}_{k|k-1} &= F \cdot \hat{\mathbf{x}}_{k-1|k-1} \\
P_{k|k-1} &= F \cdot P_{k-1|k-1} \cdot F^T + Q
\end{aligned}
$$

**2. 업데이트 단계 (Update):**

$$
\begin{aligned}
K_k &= P_{k|k-1} \cdot H^T \cdot (H \cdot P_{k|k-1} \cdot H^T + R)^{-1} \\
\hat{\mathbf{x}}_{k|k} &= \hat{\mathbf{x}}_{k|k-1} + K_k \cdot (\mathbf{z}_k - H \cdot \hat{\mathbf{x}}_{k|k-1}) \\
P_{k|k} &= (I - K_k \cdot H) \cdot P_{k|k-1}
\end{aligned}
$$

### 6.1.6 파라미터 튜닝

| 파라미터 | 값 | 의미 |
|----------|-----|------|
| $\Delta t$ | 0.033s | 샘플링 주기 (30Hz) |
| $Q$ | 0.1 | 프로세스 노이즈 (작을수록 예측 신뢰) |
| $R$ | 5.0 | 측정 노이즈 (클수록 측정 불신) |

```python
# EKF 초기화 코드
class EKF9State:
    def __init__(self, dt=0.033):
        self.dt = dt
        
        # 상태 벡터 [x, y, z, vx, vy, vz, ax, ay, az]
        self.x = np.zeros(9)
        
        # 공분산 행렬
        self.P = np.eye(9) * 1.0
        
        # 프로세스 노이즈
        self.Q = np.eye(9) * 0.1
        
        # 측정 노이즈
        self.R = np.eye(3) * 5.0
        
        # 상태 전이 행렬
        self.F = self._create_F_matrix()
        
        # 측정 행렬
        self.H = np.zeros((3, 9))
        self.H[0, 0] = self.H[1, 1] = self.H[2, 2] = 1.0
```

### 6.1.7 성능 결과

| 항목 | 적용 전 | 적용 후 | 개선율 |
|------|--------|---------|--------|
| 위치 노이즈 | ±10mm | ±3mm | **70% 감소** |
| 처리 시간 | - | ~0.15ms | - |
| 속도 추정 | 불가 | 가능 | - |

---

##  6.2 Joint-space P-Control

### 6.2.1 개요

> **목적**: 얼굴 방향으로 로봇 조준 (J1: 수평, J4: 수직)

```
┌─────────────────────────────────────────────────────────────────┐
│                    Joint-space 제어 개념                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│           얼굴 위치                  로봇 조인트                 │
│           ─────────                  ───────────                │
│                                                                 │
│           (x, y, z)      구면좌표      (J1, J4)                 │
│               │          ─────────        │                     │
│               │             │             │                     │
│               └─────────▶  변환  ────────▶│                     │
│                            │             │                     │
│                    ┌───────┴───────┐     │                     │
│                    │ azimuth (φ)   │─────▶ J1 (수평)           │
│                    │ elevation (θ) │─────▶ J4 (수직)           │
│                    └───────────────┘                           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 6.2.2 좌표 변환

**3D 직교좌표 → 구면좌표:**

$$
\begin{aligned}
\phi_{azimuth} &= \arctan2(y, x) \\
\theta_{elevation} &= \arctan2(z, \sqrt{x^2 + y^2})
\end{aligned}
$$

**조인트 목표 계산:**

$$
\begin{aligned}
J1_{target} &= J1_{start} + K_1 \cdot \phi_{azimuth} \\
J4_{target} &= J4_{start} + K_4 \cdot \theta_{elevation}
\end{aligned}
$$

### 6.2.3 P-제어 법칙

**오차 계산:**

$$
\begin{aligned}
e_{J1} &= J1_{target} - J1_{current} \\
e_{J4} &= J4_{target} - J4_{current}
\end{aligned}
$$

**속도 명령:**

$$
\begin{aligned}
\dot{J1} &= K_p \cdot e_{J1} \\
\dot{J4} &= K_p \cdot e_{J4}
\end{aligned}
$$

### 6.2.4 Dead Zone 적용

> **목적**: 미세 떨림 방지

$$
\dot{J}_i = \begin{cases}
K_p \cdot e_i & \text{if } |e_i| > \delta_{dead} \\
0 & \text{if } |e_i| \leq \delta_{dead}
\end{cases}
$$

```python
def apply_dead_zone(error, dead_zone=2.0):
    """Dead Zone 적용 (단위: degree)"""
    if abs(error) < dead_zone:
        return 0.0
    else:
        return error
```

### 6.2.5 속도 제한 (Saturation)

$$
\dot{J}_i = \text{clamp}(\dot{J}_i, -\dot{J}_{max}, +\dot{J}_{max})
$$

| 조인트 | 최대 속도 | 역할 |
|--------|----------|------|
| J1 | 30°/s | 수평 회전 |
| J4 | 40°/s | 수직 회전 |

### 6.2.6 구현 코드

```python
def compute_joint_velocities(face_pos, current_joints, start_joints):
    """얼굴 위치로부터 조인트 속도 계산"""
    x, y, z = face_pos
    
    # 1. 구면좌표 변환
    azimuth = math.atan2(y, x)
    distance_xy = math.sqrt(x**2 + y**2)
    elevation = math.atan2(z, distance_xy)
    
    # 2. 목표 조인트 계산 (라디안 → 도)
    target_j1 = start_joints[0] + math.degrees(azimuth) * K1_GAIN
    target_j4 = start_joints[3] + math.degrees(elevation) * K4_GAIN
    
    # 3. 오차 계산
    error_j1 = target_j1 - current_joints[0]
    error_j4 = target_j4 - current_joints[3]
    
    # 4. Dead Zone 적용
    error_j1 = apply_dead_zone(error_j1, DEAD_ZONE)
    error_j4 = apply_dead_zone(error_j4, DEAD_ZONE)
    
    # 5. P-제어 + 속도 제한
    vel_j1 = clamp(KP * error_j1, -MAX_VEL_J1, MAX_VEL_J1)
    vel_j4 = clamp(KP * error_j4, -MAX_VEL_J4, MAX_VEL_J4)
    
    return vel_j1, vel_j4
```

### 6.2.7 파라미터

| 파라미터 | 값 | 설명 |
|----------|-----|------|
| $K_p$ | 0.5 | 비례 게인 |
| $\delta_{dead}$ | 2° | Dead Zone |
| $\dot{J1}_{max}$ | 30°/s | J1 최대 속도 |
| $\dot{J4}_{max}$ | 40°/s | J4 최대 속도 |
| 제어 주기 | 20ms | 50Hz |

---

##  6.3 좌표 변환 (TF2)

### 6.3.1 변환 체인

```
camera_color_optical_frame
         │
         │ (카메라 외부 파라미터)
         ▼
    camera_link
         │
         │ (URDF 정의)
         ▼
   gripper_base_link
         │
         │ (URDF 정의)
         ▼
      tool0
         │
         │ (로봇 기구학)
         ▼
     base_link
```

### 6.3.2 동차 변환 행렬

**일반 형태:**

$$
T = \begin{bmatrix}
R_{3 \times 3} & t_{3 \times 1} \\
0_{1 \times 3} & 1
\end{bmatrix} \in SE(3)
$$

**점 변환:**

$$
\mathbf{p}_{base} = T_{base}^{camera} \cdot \mathbf{p}_{camera}
$$

### 6.3.3 카메라 좌표계 → 로봇 좌표계

```python
def transform_to_robot_frame(point_camera, tf_buffer):
    """카메라 프레임 → 로봇 베이스 프레임 변환"""
    
    # PointStamped 생성
    point_stamped = PointStamped()
    point_stamped.header.frame_id = 'camera_color_optical_frame'
    point_stamped.point.x = point_camera[0]
    point_stamped.point.y = point_camera[1]
    point_stamped.point.z = point_camera[2]
    
    # TF2 변환
    point_robot = tf_buffer.transform(
        point_stamped, 
        'base_link',
        timeout=Duration(seconds=0.01)
    )
    
    return [point_robot.point.x, 
            point_robot.point.y, 
            point_robot.point.z]
```

---

##  6.4 Depth 처리 알고리즘

### 6.4.1 Trimmed Mean

> **목적**: 이상치에 강건한 깊이 값 추정

**알고리즘:**

1. 얼굴 중심 주변 3×3 영역 샘플링
2. 유효값만 필터링 (0 < depth < 10000)
3. 정렬 후 상하위 20% 제거
4. 나머지 값들의 평균 계산

$$
\text{TrimmedMean}(X) = \frac{1}{n-2k} \sum_{i=k+1}^{n-k} x_{(i)}
$$

여기서 $x_{(i)}$는 정렬된 데이터, $k = \lfloor 0.2n \rfloor$

### 6.4.2 구현 코드

```python
def get_depth_trimmed_mean(depth_frame, cx, cy, window=1):
    """Trimmed Mean으로 깊이값 추출"""
    
    # 1. 3x3 영역 추출
    y_min, y_max = cy - window, cy + window + 1
    x_min, x_max = cx - window, cx + window + 1
    
    depth_region = depth_frame[y_min:y_max, x_min:x_max]
    
    # 2. 유효값 필터링
    valid_depths = depth_region[(depth_region > 0) & (depth_region < 10000)]
    
    if len(valid_depths) < 3:
        return None
    
    # 3. 정렬
    sorted_depths = np.sort(valid_depths)
    
    # 4. 상하위 20% 제거
    trim_count = max(1, len(sorted_depths) // 5)
    trimmed = sorted_depths[trim_count:-trim_count]
    
    # 5. 평균
    return float(np.mean(trimmed))
```

### 6.4.3 비교

| 방법 | 데이터 예시 | 결과 | 이상치 처리 |
|------|------------|------|------------|
| Mean | [580, 585, 590, 1200] | 739 |  |
| Median | [580, 585, 590, 1200] | 587 |  |
| **Trimmed Mean** | [580, 585, 590, 1200] | **585** |  (더 정확) |

---

##  6.5 ROI Tracking

### 6.5.1 개요

> **목적**: 이전 프레임 감지 위치 주변에서 우선 탐색 → 속도 향상

```
┌─────────────────────────────────────────────────────────────────┐
│                      ROI Tracking 개념                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   Frame N-1                        Frame N                      │
│   ─────────                        ─────────                    │
│                                                                 │
│   ┌─────────────────┐              ┌─────────────────┐         │
│   │                 │              │     ┌─────┐     │         │
│   │    ┌─────┐      │              │     │ ROI │     │         │
│   │    │   │      │   ─────▶     │     │   │     │         │
│   │    └─────┘      │   이전 위치   │     └─────┘     │         │
│   │                 │   기반 ROI    │                 │         │
│   └─────────────────┘              └─────────────────┘         │
│                                                                 │
│   전체 탐색 필요                    ROI 내부만 우선 탐색          │
│   (~5ms)                          (~2ms, ROI hit 시)           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 6.5.2 ROI 계산

$$
\begin{aligned}
x_{roi} &= x_{prev} - margin \\
y_{roi} &= y_{prev} - margin \\
w_{roi} &= w_{prev} + 2 \cdot margin \\
h_{roi} &= h_{prev} + 2 \cdot margin
\end{aligned}
$$

여기서 $margin$은 움직임 여유분 (기본값: 50px)

### 6.5.3 구현 코드

```python
class ROITracker:
    def __init__(self, margin=50):
        self.margin = margin
        self.last_bbox = None
        
    def get_roi(self, frame_shape):
        """이전 감지 기반 ROI 반환"""
        if self.last_bbox is None:
            return None  # 전체 프레임 탐색
            
        x, y, w, h = self.last_bbox
        H, W = frame_shape[:2]
        
        # ROI 계산 (경계 처리)
        x1 = max(0, x - self.margin)
        y1 = max(0, y - self.margin)
        x2 = min(W, x + w + self.margin)
        y2 = min(H, y + h + self.margin)
        
        return (x1, y1, x2 - x1, y2 - y1)
        
    def update(self, bbox):
        """감지 결과로 ROI 업데이트"""
        self.last_bbox = bbox
```

---

##  6.6 알고리즘 성능 요약

### 처리 시간 분석

| 알고리즘 | 처리 시간 | 주기 | CPU/GPU |
|----------|----------|------|---------|
| YOLOv8 추론 | ~5ms | 30Hz | GPU (TensorRT) |
| EKF 9-state | ~0.15ms | 30Hz | CPU |
| TF2 변환 | ~1ms | 30Hz | CPU |
| Joint Control | ~0.5ms | 50Hz | CPU |
| Depth 처리 | ~0.3ms | 30Hz | CPU |
| **Total E2E** | **~8ms** | - | - |

### End-to-End 지연

```
┌─────────────────────────────────────────────────────────────────┐
│                     E2E 지연 분석                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  카메라 캡처 ─▶ YOLO 추론 ─▶ TF2+EKF ─▶ Joint Ctrl ─▶ 로봇     │
│     ~2ms         ~5ms        ~1.5ms      ~0.5ms       ~2ms     │
│                                                                 │
│  ├──────────────────────────────────────────────────────────┤   │
│                        Total: ~8ms                              │
│                        (125 FPS 가능)                           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

> **작성자**: 태슬라 (헤드샷 트래킹 담당)  
> **최종 수정**: 2025-12-15  
> **상태**:  완료
