// src/components/CameraPanel.tsx
import React from "react";
import { API_BASE } from "../api/client";
const CAMERA_STREAM_URL = `${API_BASE}/stream`; // 나중에 실제 엔드포인트로 변경

export default function CameraPanel() {
  return (
    <div className="panel camera-panel">
      <div className="panel-header">
        <span className="panel-title">LIVE FEED - D435i</span>
        <span className="panel-tag">VIDEO · IMU</span>
      </div>
      <div className="panel-body camera-body">
        {/* 실제 스트림이 준비되기 전까지는 플레이스홀더 */}
        {/* 스트림 준비되면 아래 img src만 교체 */}
        <div className="camera-placeholder">
          <div className="camera-grid-overlay" />
          <div className="camera-text">
            CAMERA STREAM ONLINE CHANNEL
            <br />
            <span>Source: Intel RealSense D435i</span>
          </div>
        </div>
        {/* 예: <img src={CAMERA_STREAM_URL} className="camera-video" /> */}
      </div>
    </div>
  );
}
