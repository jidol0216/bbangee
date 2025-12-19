#!/usr/bin/env python3
"""
Test SAM3 Detection
SAM3 그립 검출 테스트
"""

import pytest
import numpy as np
from PIL import Image


class TestSam3Wrapper:
    """SAM3 래퍼 테스트"""
    
    def test_import(self):
        """모듈 임포트 테스트"""
        from sam3_grip_detection.utils.sam3_wrapper import Sam3Wrapper
        assert Sam3Wrapper is not None
    
    def test_text_prompts(self):
        """텍스트 프롬프트 리스트 확인"""
        from sam3_grip_detection.utils.sam3_wrapper import Sam3Wrapper
        wrapper = Sam3Wrapper()
        assert len(wrapper.TEXT_PROMPTS) >= 10
        assert "grip" in wrapper.TEXT_PROMPTS


class TestDepthToPointCloud:
    """Depth-3D 변환 테스트"""
    
    def test_import(self):
        """모듈 임포트 테스트"""
        from sam3_grip_detection.utils.depth_to_pointcloud import DepthToPointCloud
        assert DepthToPointCloud is not None
    
    def test_conversion(self):
        """3D 변환 테스트"""
        from sam3_grip_detection.utils.depth_to_pointcloud import DepthToPointCloud
        
        converter = DepthToPointCloud(
            fx=615.0, fy=615.0, cx=320.0, cy=240.0
        )
        
        # 테스트 depth 이미지 (640x480)
        depth = np.ones((480, 640), dtype=np.uint16) * 1000  # 1m
        
        # 중앙 영역만 마스크
        mask = np.zeros((480, 640), dtype=np.uint8)
        mask[200:280, 280:360] = 255
        
        points, _ = converter.depth_to_3d_points(depth, mask)
        
        assert len(points) > 0
        assert points.shape[1] == 3  # X, Y, Z
    
    def test_voxel_downsample(self):
        """다운샘플링 테스트"""
        from sam3_grip_detection.utils.depth_to_pointcloud import DepthToPointCloud
        
        converter = DepthToPointCloud()
        
        # 랜덤 포인트
        points = np.random.rand(10000, 3)
        
        downsampled, _ = converter.downsample_voxel(points, voxel_size=0.1)
        
        assert len(downsampled) < len(points)


class TestGraspUtils:
    """그래스핑 유틸리티 테스트"""
    
    def test_import(self):
        """모듈 임포트 테스트"""
        from sam3_grip_detection.utils.grasp_utils import GraspUtils
        assert GraspUtils is not None
    
    def test_grasp_pose_3d(self):
        """3D 그래스핑 포즈 계산 테스트"""
        from sam3_grip_detection.utils.grasp_utils import GraspUtils
        
        grasp = GraspUtils()
        
        # 원기둥 형태의 포인트 (그립 모양)
        theta = np.linspace(0, 2*np.pi, 100)
        z = np.linspace(0, 0.1, 50)
        theta, z = np.meshgrid(theta, z)
        theta = theta.flatten()
        z = z.flatten()
        
        r = 0.02  # 반지름 2cm
        x = r * np.cos(theta)
        y = r * np.sin(theta)
        
        points = np.column_stack([x, y, z])
        
        result = grasp.calculate_grasp_pose_3d(points)
        
        assert result is not None
        assert 'center_3d' in result
        assert 'orientation' in result
        assert 'grip_width_mm' in result
        assert 'gripper_compatible' in result
    
    def test_quaternion_conversion(self):
        """쿼터니언 변환 테스트"""
        from sam3_grip_detection.utils.grasp_utils import GraspUtils
        
        grasp = GraspUtils()
        
        # 단위 축
        x = np.array([1, 0, 0])
        y = np.array([0, 1, 0])
        z = np.array([0, 0, 1])
        
        q = grasp._rotation_matrix_to_quaternion(x, y, z)
        
        # 항등 회전은 [0, 0, 0, 1]
        assert len(q) == 4
        assert abs(q[3]) > 0.99  # w ≈ 1


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
