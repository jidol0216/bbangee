// src/components/ArmbandPanel.tsx
/**
 * 1차 피아식별 - Armband(완장) 감지 패널
 * 
 * - Raw: OBB 바운딩 박스가 표시된 원본 이미지
 * - ROI: 회전+crop된 완장 이미지
 * - OCR: 한글 텍스트 인식 (아군/적군)
 */

import React, { useState, useEffect } from "react";
import { API_BASE, api } from "../api/client";

const RAW_STREAM_URL = `${API_BASE}/armband/raw/stream`;
const RAW_FRAME_URL = `${API_BASE}/armband/raw/frame`;
const ROI_STREAM_URL = `${API_BASE}/armband/roi/stream`;
const ROI_FRAME_URL = `${API_BASE}/armband/roi/frame`;

interface DetectionInfo {
  detected: boolean;
  class?: string;
  confidence?: number;
  center?: number[];
  ocr_text?: string;
  ocr_confidence?: number;
  faction?: string;
}

interface OcrResult {
  text: string;
  confidence: number;
  faction: string;
}

interface ArmbandStatus {
  running: boolean;
  last_update: number;
  detection: DetectionInfo;
  ocr: OcrResult;
}

// 진영별 스타일
const FACTION_STYLES: Record<string, { label: string; class: string; icon: string }> = {
  "ALLY": { label: "아군", class: "ally", icon: "✓" },
  "ENEMY": { label: "적군", class: "enemy", icon: "✗" },
  "UNKNOWN": { label: "미확인", class: "unknown", icon: "?" },
  "ERROR": { label: "오류", class: "error", icon: "!" },
};

export default function ArmbandPanel() {
  const [status, setStatus] = useState<ArmbandStatus | null>(null);
  const [usePolling, setUsePolling] = useState(false);
  const [rawFrameUrl, setRawFrameUrl] = useState<string | null>(null);
  const [roiFrameUrl, setRoiFrameUrl] = useState<string | null>(null);
  const [streamKey, setStreamKey] = useState(0);

  // 상태 폴링
  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const res = await api.get("/armband/status");
        setStatus(res.data);
      } catch (err) {
        // 연결 실패
      }
    };

    fetchStatus();
    const interval = setInterval(fetchStatus, 500);
    return () => clearInterval(interval);
  }, []);

  // 폴링 모드
  useEffect(() => {
    if (!usePolling) return;

    const interval = setInterval(() => {
      const t = Date.now();
      setRawFrameUrl(`${RAW_FRAME_URL}?t=${t}`);
      setRoiFrameUrl(`${ROI_FRAME_URL}?t=${t}`);
    }, 100); // 10fps

    return () => clearInterval(interval);
  }, [usePolling]);

  const handleStreamError = () => {
    console.log("Armband stream error, switching to polling");
    setUsePolling(true);
  };

  const reconnect = () => {
    setUsePolling(false);
    setStreamKey(prev => prev + 1);
  };

  const detection = status?.detection;
  const ocr = status?.ocr;
  const isDetected = detection?.detected ?? false;
  const faction = ocr?.faction ?? "UNKNOWN";
  const factionStyle = FACTION_STYLES[faction] || FACTION_STYLES["UNKNOWN"];

  return (
    <div className="panel armband-panel">
      <div className="panel-header">
        <span className="panel-title">🎯 ARMBAND DETECT</span>
        <span 
          className={`panel-tag ${status?.running ? "online" : "offline"}`}
          onClick={reconnect}
          style={{ cursor: 'pointer' }}
        >
          {isDetected ? `${(detection?.confidence ?? 0) * 100 | 0}%` : "SCANNING"}
        </span>
      </div>

      <div className="panel-body armband-body">
        {/* 감지 상태 표시 */}
        <div className={`armband-status ${isDetected ? "detected" : "searching"}`}>
          {isDetected ? (
            <>
              <span className="status-icon">✓</span>
              <span className="status-text">완장 감지됨</span>
            </>
          ) : (
            <>
              <span className="status-icon scanning">◎</span>
              <span className="status-text">스캔 중...</span>
            </>
          )}
        </div>

        {/* 이미지 영역: Raw → 화살표 → ROI + OCR */}
        <div className="armband-images">
          {/* Raw 이미지 (OBB 박스) */}
          <div className="armband-img-container raw">
            <div className="img-label">RAW + OBB</div>
            {usePolling ? (
              <img 
                src={rawFrameUrl || ""} 
                alt="Raw Detection"
                className="armband-img"
                onError={() => {}}
              />
            ) : (
              <img 
                key={`raw-${streamKey}`}
                src={RAW_STREAM_URL}
                alt="Raw Stream"
                className="armband-img"
                onError={handleStreamError}
              />
            )}
          </div>

          {/* 화살표 */}
          <div className="armband-arrow">
            <svg viewBox="0 0 40 24" className="arrow-svg">
              <defs>
                <linearGradient id="arrowGrad" x1="0%" y1="0%" x2="100%" y2="0%">
                  <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.3" />
                  <stop offset="100%" stopColor="var(--accent)" stopOpacity="1" />
                </linearGradient>
              </defs>
              <path 
                d="M2 12 L28 12 M22 6 L28 12 L22 18" 
                stroke="url(#arrowGrad)" 
                strokeWidth="2.5" 
                fill="none"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            <span className="arrow-label">CROP</span>
          </div>

          {/* ROI 이미지 + OCR 결과 */}
          <div className="armband-warped-section">
            <div className="armband-img-container warped">
              <div className="img-label">ROI</div>
              {usePolling ? (
                <img 
                  src={roiFrameUrl || ""} 
                  alt="ROI"
                  className="armband-img warped-img"
                  onError={() => {}}
                />
              ) : (
                <img 
                  key={`roi-${streamKey}`}
                  src={ROI_STREAM_URL}
                  alt="ROI Stream"
                  className="armband-img warped-img"
                  onError={handleStreamError}
                />
              )}
            </div>

            {/* OCR 결과 텍스트 상자 */}
            <div className={`ocr-result-box ${factionStyle.class}`}>
              <div className="ocr-label">OCR 인식</div>
              <div className="ocr-content">
                {ocr && ocr.text ? (
                  <>
                    <span className="ocr-text">{ocr.text}</span>
                    <span className="ocr-faction">
                      <span className="faction-icon">{factionStyle.icon}</span>
                      <span className="faction-label">{factionStyle.label}</span>
                    </span>
                  </>
                ) : (
                  <span className="ocr-empty">텍스트 없음</span>
                )}
              </div>
              {ocr && ocr.confidence > 0 && (
                <div className="ocr-confidence">
                  신뢰도: {(ocr.confidence * 100).toFixed(1)}%
                </div>
              )}
            </div>
          </div>
        </div>

        {/* 감지 정보 */}
        {isDetected && detection && (
          <div className="armband-info">
            <span className="info-item">
              <span className="info-label">CLASS</span>
              <span className="info-value">{detection.class}</span>
            </span>
            <span className="info-item">
              <span className="info-label">CONF</span>
              <span className="info-value">{((detection.confidence ?? 0) * 100).toFixed(1)}%</span>
            </span>
            {ocr && ocr.text && (
              <span className={`info-item faction-badge ${factionStyle.class}`}>
                <span className="info-label">판정</span>
                <span className="info-value">{factionStyle.label}</span>
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
