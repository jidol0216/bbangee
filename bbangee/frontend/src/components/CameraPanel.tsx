// src/components/CameraPanel.tsx
import React, { useState, useEffect, useRef } from "react";
import { API_BASE } from "../api/client";

const CAMERA_STREAM_URL = `${API_BASE}/ros2/camera/stream`;
const CAMERA_FRAME_URL = `${API_BASE}/ros2/camera/frame`;

export default function CameraPanel() {
  const [usePolling, setUsePolling] = useState(false);
  const [frameUrl, setFrameUrl] = useState<string | null>(null);
  const [streamKey, setStreamKey] = useState(0);
  const imgRef = useRef<HTMLImageElement>(null);

  // 폴링 모드: 개별 프레임 요청 (MJPEG 실패 시 폴백)
  useEffect(() => {
    if (!usePolling) return;

    const interval = setInterval(() => {
      setFrameUrl(`${CAMERA_FRAME_URL}?t=${Date.now()}`);
    }, 100); // 10fps

    return () => clearInterval(interval);
  }, [usePolling]);

  // MJPEG 스트림 에러 핸들러
  const handleStreamError = () => {
    console.log("MJPEG stream error, switching to polling mode");
    setUsePolling(true);
  };

  // MJPEG 스트림 로드 성공
  const handleStreamLoad = () => {
    setUsePolling(false);
  };

  // 스트림 재연결
  const reconnectStream = () => {
    setUsePolling(false);
    setStreamKey(prev => prev + 1);
  };

  return (
    <div className="panel camera-panel">
      <div className="panel-header">
        <span className="panel-title">LIVE FEED - D435i</span>
        <span className="panel-tag" onClick={reconnectStream} style={{cursor: 'pointer'}}>
          {usePolling ? "POLLING" : "STREAM"} · CLICK TO REFRESH
        </span>
      </div>
      <div className="panel-body camera-body">
        {usePolling ? (
          // 폴링 모드
          <img 
            src={frameUrl || ""}
            alt="Camera Frame"
            className="camera-video"
            style={{ width: '100%', height: '100%', objectFit: 'contain' }}
            onError={() => {}}
          />
        ) : (
          // MJPEG 스트림 모드
          <img 
            key={streamKey}
            ref={imgRef}
            src={CAMERA_STREAM_URL} 
            alt="Camera Stream"
            className="camera-video"
            onError={handleStreamError}
            onLoad={handleStreamLoad}
            style={{ width: '100%', height: '100%', objectFit: 'contain' }}
          />
        )}
      </div>
    </div>
  );
}
