#!/usr/bin/env python3
"""
SAM3 Wrapper Module
SAM3 모델을 로드하고 텍스트 프롬프트 기반 세그멘테이션을 수행하는 래퍼 클래스

노트북 gun_grip_segmentation_ver2.ipynb에서 검증된 코드 기반
"""

import sys
from pathlib import Path
import numpy as np
from typing import Optional, Dict, List, Tuple, Any

try:
    import torch
    from PIL import Image
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    print("Warning: PyTorch not available")


class Sam3Wrapper:
    """SAM3 모델 래퍼 클래스"""
    
    # 검증된 텍스트 프롬프트 리스트 (성공률 순)
    TEXT_PROMPTS = [
        "grip",                    # 39.2% 성공률
        "handgun grip",            # 36.5%
        "dark gun handle",         # 9.5%
        "gun grip",                # 6.8%
        "black pistol grip",       # 4.1%
        "handle",                  # 2.7%
        "vertical grip",           # 1.4%
        "pistol grip",
        "gun handle",
        "black handle",
        "lower part of gun",
        "bottom handle",
        "handle at bottom",
        "part to hold",
        "holding area",
        "grip area",
        "curved handle"
    ]
    
    # Fast 모드용 상위 프롬프트 (상위 3개만)
    FAST_TEXT_PROMPTS = [
        "grip",
        "handgun grip", 
        "gun grip",
    ]
    
    # Ultra-fast 모드용 (단일 프롬프트)
    ULTRA_FAST_PROMPTS = [
        "grip",
    ]
    
    # 자동 포인트 그리드 (이미지 비율 기준)
    POINT_GRID_RATIOS = [
        (0.5, 0.7), (0.4, 0.7), (0.6, 0.7),
        (0.5, 0.5), (0.4, 0.5), (0.6, 0.5),
        (0.3, 0.8), (0.7, 0.8),
        (0.5, 0.3),
    ]
    
    # Fast 모드용 포인트 (상위 3개만)
    FAST_POINT_GRID_RATIOS = [
        (0.5, 0.7), (0.5, 0.5), (0.4, 0.7),
    ]
    
    # Ultra-fast 모드용 포인트 (단일)
    ULTRA_FAST_POINT_RATIOS = [
        (0.5, 0.7),
    ]
    
    def __init__(self, 
                 sam3_path: str = None,
                 hf_token: str = None,
                 device: str = None):
        """
        Args:
            sam3_path: SAM3 라이브러리 경로 (기본: ~/Desktop/2day/sam3/sam3)
            hf_token: HuggingFace 토큰
            device: 'cuda' 또는 'cpu'
        """
        self.model = None
        self.processor = None
        self.device = device or ('cuda' if torch.cuda.is_available() else 'cpu')
        self.is_loaded = False
        
        # SAM3 경로 설정
        if sam3_path is None:
            sam3_path = str(Path.home() / 'Desktop' / '2day' / 'sam3' / 'sam3')
        
        self.sam3_path = sam3_path
        self.hf_token = hf_token
        
    def load_model(self) -> bool:
        """SAM3 모델 로드"""
        if not TORCH_AVAILABLE:
            print("Error: PyTorch is required for SAM3")
            return False
            
        try:
            # SAM3 경로 추가
            if self.sam3_path not in sys.path:
                sys.path.insert(0, self.sam3_path)
                print(f"Added SAM3 path: {self.sam3_path}")
            
            # HuggingFace 로그인
            if self.hf_token:
                from huggingface_hub import login
                login(token=self.hf_token)
                print("HuggingFace login successful")
            
            # 모델 로드
            from sam3.model_builder import build_sam3_image_model
            from sam3.model.sam3_image_processor import Sam3Processor
            
            print("Loading SAM3 model... (this may take a few minutes)")
            self.model = build_sam3_image_model()
            self.processor = Sam3Processor(self.model)
            
            self.is_loaded = True
            print(f"SAM3 model loaded successfully on {self.device}")
            return True
            
        except Exception as e:
            print(f"Error loading SAM3 model: {e}")
            return False
    
    def find_gun_grip(self, 
                      image: Image.Image,
                      confidence_threshold: float = 0.2,
                      fast_mode: bool = True,
                      ultra_fast: bool = False,
                      resize_for_speed: bool = True,
                      early_exit_score: float = 0.7) -> Optional[Dict[str, Any]]:
        """
        총 그립을 찾는 최적화된 함수
        
        노트북에서 검증된 알고리즘:
        1. 텍스트 프롬프트로 검색
        2. 자동 포인트 그리드 검색
        3. 크기/위치/신뢰도 기반 필터링
        4. 종합 점수로 최적 선택
        
        Args:
            image: PIL Image
            confidence_threshold: 최소 신뢰도 (기본 0.2)
            fast_mode: True면 상위 프롬프트만 사용 (기본 True)
            ultra_fast: True면 단일 프롬프트만 사용 (기본 False)
            resize_for_speed: True면 작은 이미지로 처리 (기본 True)
            early_exit_score: 이 점수 이상이면 즉시 반환 (기본 0.7)
            
        Returns:
            검출 결과 dict 또는 None
        """
        if not self.is_loaded:
            print("Error: Model not loaded. Call load_model() first.")
            return None
        
        # 원본 크기 저장
        original_size = image.size  # (width, height)
        
        # 이미지 리사이즈 (속도 최적화)
        if resize_for_speed and max(image.size) > 320:
            scale = 320 / max(image.size)
            new_size = (int(image.size[0] * scale), int(image.size[1] * scale))
            image = image.resize(new_size, Image.BILINEAR)
        
        img_array = np.array(image)
        height, width = img_array.shape[:2]
        
        # 이미지 설정
        inference_state = self.processor.set_image(image)
        
        all_candidates = []
        best_candidate = None
        
        # 모드에 따른 프롬프트/포인트 선택
        if ultra_fast:
            prompts_to_use = self.ULTRA_FAST_PROMPTS
            points_to_use = self.ULTRA_FAST_POINT_RATIOS
        elif fast_mode:
            prompts_to_use = self.FAST_TEXT_PROMPTS
            points_to_use = self.FAST_POINT_GRID_RATIOS
        else:
            prompts_to_use = self.TEXT_PROMPTS
            points_to_use = self.POINT_GRID_RATIOS
        
        # === 1단계: 텍스트 프롬프트 ===
        for prompt in prompts_to_use:
            try:
                output = self.processor.set_text_prompt(
                    state=inference_state, 
                    prompt=prompt
                )
                if len(output["masks"]) > 0:
                    for idx in range(len(output["masks"])):
                        candidate = self._extract_candidate(
                            output["masks"][idx], 
                            output["boxes"][idx],
                            output["scores"][idx], 
                            prompt, 
                            width, height,
                            confidence_threshold
                        )
                        if candidate:
                            # 종합 점수 계산
                            candidate['total_score'] = self._calculate_total_score(
                                candidate, width, height
                            )
                            all_candidates.append(candidate)
                            
                            # Early exit: 충분히 좋은 결과면 즉시 반환
                            if candidate['total_score'] >= early_exit_score:
                                candidate['original_size'] = original_size
                                candidate['processed_size'] = (width, height)
                                return candidate
            except Exception:
                continue
        
        # === 2단계: 자동 포인트 그리드 (텍스트에서 못 찾은 경우만) ===
        if not all_candidates:
            for ratio_x, ratio_y in points_to_use:
                point_x = int(width * ratio_x)
                point_y = int(height * ratio_y)
                try:
                    output = self.processor.set_point_prompt(
                        state=inference_state,
                        points=[[point_x, point_y]],
                        labels=[1]
                    )
                    if len(output["masks"]) > 0:
                        candidate = self._extract_candidate(
                            output["masks"][0], 
                            output["boxes"][0],
                            output["scores"][0], 
                            f"point({point_x},{point_y})",
                            width, height,
                            confidence_threshold
                        )
                        if candidate:
                            candidate['total_score'] = self._calculate_total_score(
                                candidate, width, height
                            )
                            all_candidates.append(candidate)
                            
                            # Early exit
                            if candidate['total_score'] >= early_exit_score:
                                candidate['original_size'] = original_size
                                candidate['processed_size'] = (width, height)
                                return candidate
                except Exception:
                    continue
        
        # === 3단계: 최적 후보 선택 ===
        if not all_candidates:
            return None
        
        # 중복 제거 (IoU > 0.5)
        unique_candidates = self._remove_duplicates(all_candidates)
        
        # 최고 점수 반환
        best = max(unique_candidates, key=lambda x: x['total_score'])
        best['original_size'] = original_size
        best['processed_size'] = (width, height)
        return best
    
    def _extract_candidate(self,
                          mask: 'torch.Tensor',
                          box: 'torch.Tensor', 
                          score: 'torch.Tensor',
                          prompt: str,
                          width: int,
                          height: int,
                          confidence_threshold: float) -> Optional[Dict[str, Any]]:
        """후보 추출 및 필터링"""
        try:
            # CPU 변환
            mask_np = mask.cpu().numpy() if torch.is_tensor(mask) else mask
            if mask_np.ndim == 3:
                mask_np = mask_np.squeeze(0)
            
            box_cpu = box.cpu().numpy() if torch.is_tensor(box) else box
            x1, y1, x2, y2 = box_cpu
            score_val = score.item() if torch.is_tensor(score) else score
            
            # 크기 및 비율 계산
            box_width = x2 - x1
            box_height = y2 - y1
            area_ratio = (box_width * box_height) / (width * height)
            aspect_ratio = box_width / box_height if box_height > 0 else 0
            
            center_x = (x1 + x2) / 2
            center_y = (y1 + y2) / 2
            
            # 필터링: 크기(3~50%), 위치(상단20%제외), 비율(0.2~5), 신뢰도
            is_valid = (
                0.03 < area_ratio < 0.5 and
                center_y > height * 0.2 and
                0.2 < aspect_ratio < 5.0 and
                score_val > confidence_threshold
            )
            
            if is_valid:
                return {
                    'prompt': prompt,
                    'mask': mask,
                    'mask_np': mask_np,
                    'box': box,
                    'score': score_val,
                    'area_ratio': area_ratio,
                    'center': (int(center_x), int(center_y)),
                    'aspect_ratio': aspect_ratio,
                    'box_coords': (int(x1), int(y1), int(x2), int(y2))
                }
        except Exception:
            pass
        return None
    
    def _calculate_total_score(self,
                              candidate: Dict,
                              width: int,
                              height: int) -> float:
        """
        종합 점수 계산
        - 신뢰도(50%) + 크기(30%) + 위치(20%)
        """
        # 크기 점수: 20% 영역이 최적
        size_score = 1.0 - min(abs(candidate['area_ratio'] - 0.20) / 0.20, 1.0)
        
        # 위치 점수
        center_x_norm = candidate['center'][0] / width
        center_y_norm = candidate['center'][1] / height
        
        x_score = 1.0 - min(abs(center_x_norm - 0.5) / 0.5, 1.0)
        
        if 0.5 <= center_y_norm <= 0.8:
            y_score = 1.0
        elif center_y_norm < 0.5:
            y_score = center_y_norm / 0.5
        else:
            y_score = max(0, 1.0 - (center_y_norm - 0.8) / 0.2)
        
        position_score = (x_score + y_score) / 2
        
        # 종합 점수
        return (
            candidate['score'] * 0.5 + 
            size_score * 0.3 + 
            position_score * 0.2
        )
    
    def _remove_duplicates(self,
                          candidates: List[Dict],
                          iou_threshold: float = 0.5) -> List[Dict]:
        """IoU 기반 중복 제거"""
        if len(candidates) <= 1:
            return candidates
        
        # 점수로 정렬
        sorted_candidates = sorted(candidates, key=lambda x: x['score'], reverse=True)
        unique = []
        
        for cand in sorted_candidates:
            is_duplicate = False
            for u in unique:
                iou = self._calculate_iou(cand['box_coords'], u['box_coords'])
                if iou > iou_threshold:
                    is_duplicate = True
                    break
            if not is_duplicate:
                unique.append(cand)
        
        return unique
    
    def _calculate_iou(self,
                      box1: Tuple[int, int, int, int],
                      box2: Tuple[int, int, int, int]) -> float:
        """IoU 계산"""
        x1 = max(box1[0], box2[0])
        y1 = max(box1[1], box2[1])
        x2 = min(box1[2], box2[2])
        y2 = min(box1[3], box2[3])
        
        if x2 <= x1 or y2 <= y1:
            return 0.0
        
        intersection = (x2 - x1) * (y2 - y1)
        area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
        area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
        union = area1 + area2 - intersection
        
        return intersection / union if union > 0 else 0.0
    
    def get_mask_image(self,
                      result: Dict,
                      image_shape: Tuple[int, int]) -> np.ndarray:
        """마스크를 uint8 이미지로 변환"""
        mask_np = result.get('mask_np')
        if mask_np is None:
            mask = result['mask']
            mask_np = mask.cpu().numpy() if torch.is_tensor(mask) else mask
            if mask_np.ndim == 3:
                mask_np = mask_np.squeeze(0)
        
        # 크기 맞추기
        if mask_np.shape != image_shape:
            import cv2
            mask_np = cv2.resize(
                mask_np.astype(np.float32), 
                (image_shape[1], image_shape[0])
            )
        
        return (mask_np > 0.5).astype(np.uint8) * 255
