#!/usr/bin/env python3
"""
Grasp Utilities Module
PCA 기반 그립 방향 분석 및 RG2 그리퍼용 파지 위치 계산

노트북 gun_grip_segmentation_ver2.ipynb의 extract_grasp_info() 함수 기반
"""

import numpy as np
from typing import Dict, Tuple, Optional, Any
from sklearn.decomposition import PCA


class GraspUtils:
    """그래스핑 유틸리티 클래스"""
    
    # OnRobot RG2 그리퍼 스펙
    RG2_MIN_WIDTH = 0.0      # mm
    RG2_MAX_WIDTH = 110.0    # mm
    RG2_GRIP_FORCE_MIN = 3   # N
    RG2_GRIP_FORCE_MAX = 40  # N
    
    def __init__(self,
                 gripper_max_width: float = 110.0,
                 gripper_min_width: float = 0.0,
                 safety_margin: float = 10.0):
        """
        Args:
            gripper_max_width: RG2 최대 열림 너비 (mm)
            gripper_min_width: RG2 최소 열림 너비 (mm)
            safety_margin: 안전 여유 너비 (mm)
        """
        self.gripper_max_width = gripper_max_width
        self.gripper_min_width = gripper_min_width
        self.safety_margin = safety_margin
    
    def extract_grasp_info_2d(self,
                             mask: np.ndarray,
                             box_coords: Tuple[int, int, int, int],
                             image_shape: Tuple[int, int]) -> Dict[str, Any]:
        """
        2D 마스크에서 그래스핑 정보 추출 (노트북 검증 코드 기반)
        
        Args:
            mask: 바이너리 마스크 (H, W)
            box_coords: (x1, y1, x2, y2)
            image_shape: (height, width)
            
        Returns:
            그래스핑 정보 딕셔너리
        """
        x1, y1, x2, y2 = box_coords
        height, width = image_shape
        
        # 마스크 픽셀 좌표
        if mask.dtype == np.float32 or mask.dtype == np.float64:
            mask_binary = mask > 0.5
        else:
            mask_binary = mask > 127
            
        mask_pixels = np.argwhere(mask_binary)
        
        if len(mask_pixels) < 10:
            return None
        
        # PCA로 주축 방향 계산
        pca = PCA(n_components=2)
        pca.fit(mask_pixels)
        
        # 주축 방향 (y, x 순서)
        main_axis = pca.components_[0]  # [dy, dx]
        
        # 방향 각도 (x축 기준, 도)
        angle = np.degrees(np.arctan2(main_axis[0], main_axis[1]))
        
        # 중심점
        center_y = (y1 + y2) / 2
        center_x = (x1 + x2) / 2
        
        # 마스크 중심
        mask_center = mask_pixels.mean(axis=0)  # [y, x]
        
        # 주축을 따라 그립 포인트 계산
        # PCA 기준 길이 계산
        projected = mask_pixels @ pca.components_[0]
        axis_length = projected.max() - projected.min()
        
        # 그립 포인트 (주축 양 끝)
        point1 = mask_center + (axis_length / 2) * main_axis
        point2 = mask_center - (axis_length / 2) * main_axis
        
        # 그립 너비 (수직 방향 폭)
        perpendicular_proj = mask_pixels @ pca.components_[1]
        grip_width_pixels = perpendicular_proj.max() - perpendicular_proj.min()
        
        # 권장 그립 위치 (중심에서 약간 아래)
        recommended_grip = (
            int(center_x),
            int(center_y + (y2 - y1) * 0.1)  # 10% 아래
        )
        
        # 마스크 면적
        mask_area = np.sum(mask_binary)
        
        # 가로세로 비율
        box_width = x2 - x1
        box_height = y2 - y1
        aspect_ratio = box_width / box_height if box_height > 0 else 1.0
        
        # 영역 비율
        area_ratio = mask_area / (width * height)
        
        return {
            'bbox': {'x1': int(x1), 'y1': int(y1), 'x2': int(x2), 'y2': int(y2)},
            'center': {'x': int(center_x), 'y': int(center_y)},
            'orientation_angle': float(angle),
            'grasp_points': {
                'point1': {'x': int(point1[1]), 'y': int(point1[0])},
                'point2': {'x': int(point2[1]), 'y': int(point2[0])}
            },
            'grasp_width_pixels': float(grip_width_pixels),
            'recommended_grip': {'x': recommended_grip[0], 'y': recommended_grip[1]},
            'mask_area': float(mask_area),
            'aspect_ratio': float(aspect_ratio),
            'area_ratio': float(area_ratio),
        }
    
    def calculate_grasp_pose_3d(self,
                               points_3d: np.ndarray) -> Optional[Dict[str, Any]]:
        """
        3D 포인트클라우드에서 그래스핑 포즈 계산
        
        Args:
            points_3d: (N, 3) 3D 좌표 배열
            
        Returns:
            그래스핑 포즈 정보
        """
        if len(points_3d) < 10:
            return None
        
        # PCA로 주축 방향 계산
        pca = PCA(n_components=3)
        pca.fit(points_3d)
        
        # 주축들
        main_axis = pca.components_[0]      # 그립의 긴 방향
        secondary_axis = pca.components_[1] # 수직 방향
        normal_axis = pca.components_[2]    # 법선 방향
        
        # 그립 중심점
        center_3d = points_3d.mean(axis=0)
        
        # 그립 너비 (secondary axis 방향 폭)
        perpendicular_proj = points_3d @ secondary_axis
        grip_width_m = perpendicular_proj.max() - perpendicular_proj.min()
        grip_width_mm = grip_width_m * 1000
        
        # 그립 길이 (main axis 방향)
        main_proj = points_3d @ main_axis
        grip_length_m = main_proj.max() - main_proj.min()
        
        # 그리퍼 호환성 확인
        gripper_compatible = (
            self.gripper_min_width <= grip_width_mm <= self.gripper_max_width
        )
        
        # 권장 그리퍼 열림 너비 (여유 포함)
        recommended_width = min(
            grip_width_mm + self.safety_margin,
            self.gripper_max_width
        )
        
        # 그래스핑 방향 계산
        # 접근 방향: 그립 표면의 법선 (또는 secondary × main)
        approach_vector = np.cross(main_axis, secondary_axis)
        approach_vector = approach_vector / np.linalg.norm(approach_vector)
        
        # 쿼터니언 계산
        quaternion = self._rotation_matrix_to_quaternion(
            main_axis, secondary_axis, approach_vector
        )
        
        return {
            'center_3d': {
                'x': float(center_3d[0]),
                'y': float(center_3d[1]),
                'z': float(center_3d[2])
            },
            'orientation': {
                'x': float(quaternion[0]),
                'y': float(quaternion[1]),
                'z': float(quaternion[2]),
                'w': float(quaternion[3])
            },
            'grip_width_mm': float(grip_width_mm),
            'grip_length_mm': float(grip_length_m * 1000),
            'recommended_gripper_width_mm': float(recommended_width),
            'gripper_compatible': bool(gripper_compatible),
            'main_axis': main_axis.tolist(),
            'approach_vector': approach_vector.tolist(),
        }
    
    def _rotation_matrix_to_quaternion(self,
                                       x_axis: np.ndarray,
                                       y_axis: np.ndarray,
                                       z_axis: np.ndarray) -> np.ndarray:
        """
        회전 행렬에서 쿼터니언 변환
        
        RG2 그리퍼 좌표계:
        - Z축: 그리퍼 접근 방향
        - X축: 손가락 사이 방향 (main_axis)
        - Y축: Z × X
        
        Args:
            x_axis, y_axis, z_axis: 정규화된 축 벡터
            
        Returns:
            쿼터니언 [x, y, z, w]
        """
        # 정규화
        x_axis = x_axis / np.linalg.norm(x_axis)
        z_axis = z_axis / np.linalg.norm(z_axis)
        y_axis = np.cross(z_axis, x_axis)
        y_axis = y_axis / np.linalg.norm(y_axis)
        
        # 회전 행렬
        R = np.column_stack([x_axis, y_axis, z_axis])
        
        # 쿼터니언 변환 (Shepperd's method)
        trace = np.trace(R)
        
        if trace > 0:
            s = 0.5 / np.sqrt(trace + 1.0)
            w = 0.25 / s
            x = (R[2, 1] - R[1, 2]) * s
            y = (R[0, 2] - R[2, 0]) * s
            z = (R[1, 0] - R[0, 1]) * s
        elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
            s = 2.0 * np.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2])
            w = (R[2, 1] - R[1, 2]) / s
            x = 0.25 * s
            y = (R[0, 1] + R[1, 0]) / s
            z = (R[0, 2] + R[2, 0]) / s
        elif R[1, 1] > R[2, 2]:
            s = 2.0 * np.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2])
            w = (R[0, 2] - R[2, 0]) / s
            x = (R[0, 1] + R[1, 0]) / s
            y = 0.25 * s
            z = (R[1, 2] + R[2, 1]) / s
        else:
            s = 2.0 * np.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1])
            w = (R[1, 0] - R[0, 1]) / s
            x = (R[0, 2] + R[2, 0]) / s
            y = (R[1, 2] + R[2, 1]) / s
            z = 0.25 * s
        
        return np.array([x, y, z, w])
    
    def create_grasp_info_json(self,
                              info_2d: Dict,
                              info_3d: Optional[Dict],
                              detection_score: float,
                              image_name: str = "") -> Dict:
        """
        통합 그래스핑 정보 JSON 생성
        
        Args:
            info_2d: 2D 그래스핑 정보
            info_3d: 3D 그래스핑 정보 (optional)
            detection_score: 검출 신뢰도
            image_name: 이미지 이름
            
        Returns:
            통합 정보 딕셔너리
        """
        from datetime import datetime
        
        result = {
            'timestamp': datetime.now().isoformat(),
            'image': image_name,
            'detection_score': float(detection_score),
            '2d_info': info_2d,
        }
        
        if info_3d:
            result['3d_info'] = info_3d
            result['gripper_compatible'] = info_3d.get('gripper_compatible', False)
            result['recommended_gripper_width_mm'] = info_3d.get(
                'recommended_gripper_width_mm', 0
            )
            
            # 신뢰도 레벨
            if detection_score > 0.7 and info_3d.get('gripper_compatible', False):
                result['confidence'] = 'high'
            elif detection_score > 0.5:
                result['confidence'] = 'medium'
            else:
                result['confidence'] = 'low'
        else:
            result['confidence'] = 'low'
        
        return result


def create_pose_stamped_msg(grasp_info_3d: Dict,
                           header) -> 'geometry_msgs.msg.PoseStamped':
    """
    geometry_msgs/PoseStamped 메시지 생성
    
    Args:
        grasp_info_3d: 3D 그래스핑 정보
        header: std_msgs/Header
        
    Returns:
        PoseStamped 메시지
    """
    from geometry_msgs.msg import PoseStamped, Pose, Point, Quaternion
    
    msg = PoseStamped()
    msg.header = header
    
    center = grasp_info_3d['center_3d']
    orientation = grasp_info_3d['orientation']
    
    msg.pose.position = Point(
        x=center['x'],
        y=center['y'],
        z=center['z']
    )
    
    msg.pose.orientation = Quaternion(
        x=orientation['x'],
        y=orientation['y'],
        z=orientation['z'],
        w=orientation['w']
    )
    
    return msg


def create_grasp_marker(grasp_info_3d: Dict,
                       header,
                       marker_id: int = 0) -> 'visualization_msgs.msg.Marker':
    """
    RViz 시각화용 마커 생성
    
    Args:
        grasp_info_3d: 3D 그래스핑 정보
        header: std_msgs/Header
        marker_id: 마커 ID
        
    Returns:
        Marker 메시지
    """
    from visualization_msgs.msg import Marker
    from geometry_msgs.msg import Point
    
    marker = Marker()
    marker.header = header
    marker.ns = "grasp_pose"
    marker.id = marker_id
    marker.type = Marker.ARROW
    marker.action = Marker.ADD
    
    center = grasp_info_3d['center_3d']
    approach = grasp_info_3d['approach_vector']
    
    # 화살표 시작점과 끝점
    start = Point(
        x=center['x'],
        y=center['y'],
        z=center['z']
    )
    
    arrow_length = 0.1  # 10cm
    end = Point(
        x=center['x'] + approach[0] * arrow_length,
        y=center['y'] + approach[1] * arrow_length,
        z=center['z'] + approach[2] * arrow_length
    )
    
    marker.points = [start, end]
    
    # 크기
    marker.scale.x = 0.01   # 화살표 두께
    marker.scale.y = 0.02   # 화살표 머리 두께
    marker.scale.z = 0.0
    
    # 색상 (그리퍼 호환성에 따라)
    if grasp_info_3d.get('gripper_compatible', False):
        marker.color.r = 0.0
        marker.color.g = 1.0
        marker.color.b = 0.0
    else:
        marker.color.r = 1.0
        marker.color.g = 0.5
        marker.color.b = 0.0
    marker.color.a = 1.0
    
    marker.lifetime.sec = 1
    
    return marker
