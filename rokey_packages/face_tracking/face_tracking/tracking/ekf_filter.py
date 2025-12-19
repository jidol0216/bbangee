#!/usr/bin/env python3
"""
Extended Kalman Filter for Face Tracking

얼굴 위치 추적을 위한 확장 칼만 필터
등가속도 모델(Constant Acceleration Model) 기반

상태 벡터 (9-state):
    x = [x, y, z, vx, vy, vz, ax, ay, az]^T

상태 전이 방정식:
    x_k = F * x_{k-1} + w_{k-1}
    
    여기서 F = | I   dt*I   0.5*dt²*I |
              | 0    I      dt*I      |
              | 0    0      I         |

측정 방정식:
    z_k = H * x_k + v_k
    
    여기서 H = [I  0  0] (위치만 측정)

Reference:
    Bar-Shalom, Y., Li, X. R., & Kirubarajan, T. (2001).
    Estimation with Applications to Tracking and Navigation.
"""
import numpy as np
from typing import Optional, Dict, List
from filterpy.kalman import KalmanFilter


class EKFFilter:
    """
    얼굴 위치 추적용 확장 칼만 필터
    
    등가속도 모델을 사용하여 위치, 속도, 가속도를 추정합니다.
    """
    
    def __init__(self, dt: float = 0.033, dim: int = 3):
        """
        초기화
        
        Args:
            dt: 샘플링 시간 (default: 30Hz = 0.033s)
            dim: 측정 차원 (2=2D 픽셀, 3=3D 위치)
        """
        self.dt = dt
        self.dim = dim
        
        # 상태 차원: dim * 3 (위치, 속도, 가속도)
        dim_x = dim * 3
        dim_z = dim
        
        self.kf = KalmanFilter(dim_x=dim_x, dim_z=dim_z)
        
        # 상태 전이 행렬 F 설정
        self._setup_state_transition_matrix()
        
        # 관측 행렬 H 설정
        self._setup_observation_matrix()
        
        # 노이즈 공분산 설정
        self._setup_noise_covariance()
        
        # 초기 상태
        self.kf.x = np.zeros(dim_x)
        self.kf.P *= 100.0  # 초기 불확실성
        
        self.initialized = False
    
    def _setup_state_transition_matrix(self):
        """
        상태 전이 행렬 F 설정
        
        등가속도 모델:
            p_k = p_{k-1} + v_{k-1}*dt + 0.5*a_{k-1}*dt²
            v_k = v_{k-1} + a_{k-1}*dt
            a_k = a_{k-1}
        """
        dt = self.dt
        
        if self.dim == 2:
            # 2D: [x, y, vx, vy, ax, ay]
            self.kf.F = np.array([
                [1, 0, dt, 0,  0.5*dt**2, 0        ],
                [0, 1, 0,  dt, 0,         0.5*dt**2],
                [0, 0, 1,  0,  dt,        0        ],
                [0, 0, 0,  1,  0,         dt       ],
                [0, 0, 0,  0,  1,         0        ],
                [0, 0, 0,  0,  0,         1        ]
            ])
        else:
            # 3D: [x, y, z, vx, vy, vz, ax, ay, az]
            self.kf.F = np.array([
                [1, 0, 0, dt, 0,  0,  0.5*dt**2, 0,         0        ],
                [0, 1, 0, 0,  dt, 0,  0,         0.5*dt**2, 0        ],
                [0, 0, 1, 0,  0,  dt, 0,         0,         0.5*dt**2],
                [0, 0, 0, 1,  0,  0,  dt,        0,         0        ],
                [0, 0, 0, 0,  1,  0,  0,         dt,        0        ],
                [0, 0, 0, 0,  0,  1,  0,         0,         dt       ],
                [0, 0, 0, 0,  0,  0,  1,         0,         0        ],
                [0, 0, 0, 0,  0,  0,  0,         1,         0        ],
                [0, 0, 0, 0,  0,  0,  0,         0,         1        ]
            ])
    
    def _setup_observation_matrix(self):
        """
        관측 행렬 H 설정
        
        위치만 직접 측정 가능: z = [x, y, z]
        """
        dim_x = self.dim * 3
        
        if self.dim == 2:
            self.kf.H = np.array([
                [1, 0, 0, 0, 0, 0],
                [0, 1, 0, 0, 0, 0]
            ])
        else:
            self.kf.H = np.array([
                [1, 0, 0, 0, 0, 0, 0, 0, 0],
                [0, 1, 0, 0, 0, 0, 0, 0, 0],
                [0, 0, 1, 0, 0, 0, 0, 0, 0]
            ])
    
    def _setup_noise_covariance(self):
        """
        노이즈 공분산 설정
        
        Q: 프로세스 노이즈 (시스템 불확실성)
        R: 측정 노이즈 (센서 불확실성)
        
        튜닝 가이드:
            - Q 증가 → 모델 신뢰↓, 측정 신뢰↑ → 반응 빠름, 노이즈 증가
            - R 증가 → 측정 신뢰↓, 모델 신뢰↑ → 부드러움, 반응 느림
        """
        dim_x = self.dim * 3
        
        # 프로세스 노이즈 Q
        q = 0.1
        self.kf.Q = np.eye(dim_x) * q
        # 가속도 노이즈는 더 큼 (예측 어려움)
        if self.dim == 3:
            self.kf.Q[6:9, 6:9] *= 2.0
        else:
            self.kf.Q[4:6, 4:6] *= 2.0
        
        # 측정 노이즈 R
        # 낮을수록 센서 신뢰 → 반응 빠름
        # 높을수록 예측 신뢰 → 부드러움
        if self.dim == 3:
            r = 5.0  # mm 단위
        else:
            r = 2.0  # pixel 단위
        self.kf.R = np.eye(self.dim) * r
    
    def initialize(self, initial_position: List[float]):
        """
        첫 측정값으로 필터 초기화
        
        Args:
            initial_position: [x, y] or [x, y, z]
        """
        self.kf.x[:self.dim] = initial_position
        self.kf.x[self.dim:] = 0  # 속도, 가속도는 0으로 시작
        self.initialized = True
    
    def predict(self):
        """
        예측 단계 (Time Update)
        
        x̂⁻_k = F * x̂_{k-1}
        P⁻_k = F * P_{k-1} * F^T + Q
        """
        self.kf.predict()
    
    def update(self, measurement: List[float]):
        """
        업데이트 단계 (Measurement Update)
        
        K_k = P⁻_k * H^T * (H * P⁻_k * H^T + R)^{-1}
        x̂_k = x̂⁻_k + K_k * (z_k - H * x̂⁻_k)
        P_k = (I - K_k * H) * P⁻_k
        
        Args:
            measurement: [x, y, z] 측정값 (mm)
        """
        if not self.initialized:
            self.initialize(measurement)
            return
        
        self.kf.update(measurement)
    
    def predict_trajectory(self, n_steps: int) -> np.ndarray:
        """
        미래 N 스텝 궤적 예측
        
        Args:
            n_steps: 예측할 스텝 수
        
        Returns:
            trajectory: (n_steps, dim) - 예측 위치들
        """
        trajectory = []
        state = self.kf.x.copy()
        F = self.kf.F.copy()
        
        for _ in range(n_steps):
            state = F @ state
            trajectory.append(state[:self.dim].copy())
        
        return np.array(trajectory)
    
    def get_state(self) -> Dict[str, np.ndarray]:
        """현재 추정 상태 반환"""
        return {
            'position': self.kf.x[:self.dim].copy(),
            'velocity': self.kf.x[self.dim:self.dim*2].copy(),
            'acceleration': self.kf.x[self.dim*2:self.dim*3].copy()
        }
    
    def get_position(self) -> np.ndarray:
        """현재 추정 위치"""
        return self.kf.x[:self.dim].copy()
    
    def get_velocity(self) -> np.ndarray:
        """현재 추정 속도"""
        return self.kf.x[self.dim:self.dim*2].copy()
    
    def get_acceleration(self) -> np.ndarray:
        """현재 추정 가속도"""
        return self.kf.x[self.dim*2:self.dim*3].copy()
    
    def reset(self):
        """필터 리셋"""
        dim_x = self.dim * 3
        self.kf.x = np.zeros(dim_x)
        self.kf.P = np.eye(dim_x) * 100.0
        self.initialized = False
