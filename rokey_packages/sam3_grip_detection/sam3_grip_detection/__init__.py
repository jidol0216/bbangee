# SAM3 Grip Detection Package
"""
SAM3 기반 권총 손잡이 3D 세그멘테이션 및 로봇 그래스핑 패키지

주요 기능:
- SAM3를 이용한 텍스트 프롬프트 기반 세그멘테이션
- Depth 이미지를 이용한 3D 포인트클라우드 생성
- PCA 기반 그립 방향 분석
- 두산 M0609 + RG2 그리퍼용 파지 위치 계산
"""

from .sam3_grip_node import Sam3GripNode
from .grip_pose_calculator import GripPoseCalculator

__version__ = '1.0.0'
__author__ = 'Rokey'
