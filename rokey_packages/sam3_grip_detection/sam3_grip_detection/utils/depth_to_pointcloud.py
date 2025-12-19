#!/usr/bin/env python3
"""
Depth to PointCloud Module
Depth 이미지를 3D 포인트클라우드로 변환하는 모듈

핵심 변환 공식:
X = (u - cx) * Z / fx
Y = (v - cy) * Z / fy
"""

import numpy as np
from typing import Tuple, Optional
import struct


class DepthToPointCloud:
    """Depth 이미지를 3D 포인트클라우드로 변환하는 클래스"""
    
    def __init__(self,
                 fx: float = 615.0,
                 fy: float = 615.0,
                 cx: float = 320.0,
                 cy: float = 240.0,
                 min_depth: float = 0.1,
                 max_depth: float = 2.0):
        """
        Args:
            fx, fy: 카메라 초점 거리 (pixels)
            cx, cy: 카메라 광학 중심 (pixels)
            min_depth: 최소 유효 깊이 (m)
            max_depth: 최대 유효 깊이 (m)
        """
        self.fx = fx
        self.fy = fy
        self.cx = cx
        self.cy = cy
        self.min_depth = min_depth
        self.max_depth = max_depth
        
    def update_camera_info(self,
                          fx: float,
                          fy: float,
                          cx: float,
                          cy: float):
        """CameraInfo 메시지로부터 카메라 파라미터 업데이트"""
        self.fx = fx
        self.fy = fy
        self.cx = cx
        self.cy = cy
        
    def update_from_camera_info_msg(self, camera_info_msg):
        """sensor_msgs/CameraInfo 메시지로부터 업데이트"""
        # K 행렬: [fx, 0, cx, 0, fy, cy, 0, 0, 1]
        K = camera_info_msg.k
        self.fx = K[0]
        self.fy = K[4]
        self.cx = K[2]
        self.cy = K[5]
        
    def depth_to_3d_points(self,
                          depth_image: np.ndarray,
                          mask: Optional[np.ndarray] = None,
                          rgb_image: Optional[np.ndarray] = None,
                          depth_scale: float = 0.001) -> Tuple[np.ndarray, Optional[np.ndarray]]:
        """
        Depth 이미지를 3D 포인트로 변환
        
        Args:
            depth_image: Depth 이미지 (H, W), uint16 또는 float
            mask: 마스크 이미지 (H, W), 255가 관심 영역
            rgb_image: RGB 이미지 (H, W, 3), optional
            depth_scale: depth 값 -> meter 변환 비율 (기본 0.001 = mm->m)
            
        Returns:
            points_3d: (N, 3) 3D 좌표 배열 [X, Y, Z]
            rgb_values: (N, 3) RGB 값 배열 또는 None
        """
        height, width = depth_image.shape[:2]
        
        # 픽셀 좌표 그리드 생성
        u = np.arange(width)
        v = np.arange(height)
        u, v = np.meshgrid(u, v)
        
        # Depth를 미터로 변환
        Z = depth_image.astype(np.float32) * depth_scale
        
        # 유효 depth 필터링
        valid_depth = (Z > self.min_depth) & (Z < self.max_depth)
        
        # 마스크 적용
        if mask is not None:
            valid_mask = mask > 127
            valid = valid_depth & valid_mask
        else:
            valid = valid_depth
        
        # 유효 포인트가 없으면 빈 배열 반환
        if not np.any(valid):
            return np.zeros((0, 3)), None
        
        # 3D 변환 공식 적용
        Z_valid = Z[valid]
        u_valid = u[valid]
        v_valid = v[valid]
        
        X = (u_valid - self.cx) * Z_valid / self.fx
        Y = (v_valid - self.cy) * Z_valid / self.fy
        
        points_3d = np.column_stack([X, Y, Z_valid])
        
        # RGB 값 추출
        rgb_values = None
        if rgb_image is not None:
            if len(rgb_image.shape) == 3:
                rgb_values = rgb_image[valid]
            else:
                # Grayscale
                gray = rgb_image[valid]
                rgb_values = np.column_stack([gray, gray, gray])
        
        return points_3d, rgb_values
    
    def create_pointcloud2_data(self,
                               points_3d: np.ndarray,
                               rgb_values: Optional[np.ndarray] = None) -> Tuple[bytes, int]:
        """
        PointCloud2 메시지용 데이터 생성
        
        Args:
            points_3d: (N, 3) 3D 좌표
            rgb_values: (N, 3) RGB 값 (0-255)
            
        Returns:
            data: 바이너리 데이터
            point_count: 포인트 개수
        """
        if len(points_3d) == 0:
            return b'', 0
        
        point_count = len(points_3d)
        
        if rgb_values is not None:
            # XYZRGB 포맷 (16 bytes per point)
            data = bytearray()
            for i in range(point_count):
                x, y, z = points_3d[i]
                r, g, b = rgb_values[i].astype(np.uint8)
                
                # Pack XYZ as float32
                data.extend(struct.pack('fff', x, y, z))
                
                # Pack RGB as uint32 (RGBX format)
                rgb_packed = (int(r) << 16) | (int(g) << 8) | int(b)
                # Convert to float representation
                rgb_float = struct.unpack('f', struct.pack('I', rgb_packed))[0]
                data.extend(struct.pack('f', rgb_float))
            
            return bytes(data), point_count
        else:
            # XYZ 포맷만 (12 bytes per point)
            data = points_3d.astype(np.float32).tobytes()
            return data, point_count
    
    def downsample_voxel(self,
                        points_3d: np.ndarray,
                        rgb_values: Optional[np.ndarray] = None,
                        voxel_size: float = 0.003) -> Tuple[np.ndarray, Optional[np.ndarray]]:
        """
        복셀 다운샘플링
        
        Args:
            points_3d: (N, 3) 포인트
            rgb_values: (N, 3) RGB
            voxel_size: 복셀 크기 (m)
            
        Returns:
            다운샘플링된 포인트와 RGB
        """
        if len(points_3d) == 0:
            return points_3d, rgb_values
        
        # 복셀 인덱스 계산
        voxel_indices = np.floor(points_3d / voxel_size).astype(np.int32)
        
        # 유니크한 복셀 찾기
        _, unique_indices = np.unique(
            voxel_indices, axis=0, return_index=True
        )
        
        downsampled_points = points_3d[unique_indices]
        
        downsampled_rgb = None
        if rgb_values is not None:
            downsampled_rgb = rgb_values[unique_indices]
        
        return downsampled_points, downsampled_rgb


def create_pointcloud2_msg(points_3d: np.ndarray,
                          rgb_values: Optional[np.ndarray],
                          header,
                          is_bigendian: bool = False):
    """
    sensor_msgs/PointCloud2 메시지 생성 헬퍼 함수
    
    Args:
        points_3d: (N, 3) 3D 포인트
        rgb_values: (N, 3) RGB 값 또는 None
        header: std_msgs/Header
        is_bigendian: 엔디안 (기본 False)
        
    Returns:
        PointCloud2 메시지
    """
    from sensor_msgs.msg import PointCloud2, PointField
    
    msg = PointCloud2()
    msg.header = header
    msg.height = 1
    msg.width = len(points_3d)
    msg.is_bigendian = is_bigendian
    msg.is_dense = True
    
    if rgb_values is not None:
        # XYZRGB 포맷
        msg.point_step = 16
        msg.fields = [
            PointField(name='x', offset=0, datatype=PointField.FLOAT32, count=1),
            PointField(name='y', offset=4, datatype=PointField.FLOAT32, count=1),
            PointField(name='z', offset=8, datatype=PointField.FLOAT32, count=1),
            PointField(name='rgb', offset=12, datatype=PointField.FLOAT32, count=1),
        ]
        
        # 데이터 생성
        converter = DepthToPointCloud()
        data, _ = converter.create_pointcloud2_data(points_3d, rgb_values)
        msg.data = list(data)
    else:
        # XYZ 포맷만
        msg.point_step = 12
        msg.fields = [
            PointField(name='x', offset=0, datatype=PointField.FLOAT32, count=1),
            PointField(name='y', offset=4, datatype=PointField.FLOAT32, count=1),
            PointField(name='z', offset=8, datatype=PointField.FLOAT32, count=1),
        ]
        msg.data = list(points_3d.astype(np.float32).tobytes())
    
    msg.row_step = msg.point_step * msg.width
    
    return msg
