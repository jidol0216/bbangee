// src/components/RobotPanel.tsx
import React, { useState, useEffect } from "react";
import { api } from "../api/client";

interface RobotState {
  connected: boolean;
  mode: string;
  joint_positions: number[];
  status: string;
}

interface FaceTrackingState {
  enabled: boolean;
  face_detected: boolean;
  face_position: { x: number; y: number; z: number };
}

interface JointTrackingState {
  state: string;  // IDLE, TRACKING, RETURN_HOME
  control_source: string;  // terminal 또는 web
  control_mode: number;  // 1 또는 2
  control_allowed: boolean;
}

interface SystemState {
  bringup_running: boolean;
  camera_running: boolean;
  detection_running: boolean;
  tracking_running: boolean;
  joint_tracking_running: boolean;
}

interface ROS2Status {
  bridge_running: boolean;
  state: {
    robot: RobotState;
    face_tracking: FaceTrackingState;
    joint_tracking: JointTrackingState;
    system: SystemState;
  };
}

export default function RobotPanel() {
  const [status, setStatus] = useState<ROS2Status | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isHomePosition, setIsHomePosition] = useState(true); // 현재 위치 상태 (home/ready 토글)

  // 상태 조회
  const fetchStatus = async () => {
    try {
      const res = await api.get("/ros2/status");
      setStatus(res.data);
      setError(null);
    } catch (err) {
      setError("ROS2 상태 조회 실패");
    }
  };

  // 주기적 상태 조회 (2초마다)
  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 2000);
    return () => clearInterval(interval);
  }, []);

  // 로봇 명령 전송
  const sendCommand = async (command: string) => {
    setLoading(true);
    try {
      await api.post("/ros2/robot/command", { command });
      await fetchStatus();
    } catch (err) {
      setError("명령 전송 실패");
    }
    setLoading(false);
  };

  // 로봇 이동 완료 대기 (폴링)
  const waitForMovementComplete = async (maxWaitSec: number = 10): Promise<boolean> => {
    const startTime = Date.now();
    const pollInterval = 500; // 0.5초마다 체크
    
    // 잠시 대기 후 폴링 시작 (명령이 처리되기 시작할 시간)
    await new Promise(resolve => setTimeout(resolve, 500));
    
    while ((Date.now() - startTime) / 1000 < maxWaitSec) {
      try {
        const res = await api.get("/ros2/robot");
        // 로봇이 idle 상태가 되면 이동 완료
        if (res.data?.status === "idle" || res.data?.status === "standby") {
          return true;
        }
      } catch (err) {
        // 에러 무시하고 계속 폴링
      }
      await new Promise(resolve => setTimeout(resolve, pollInterval));
    }
    return false; // 타임아웃
  };

  // 홈/시작 위치 토글
  const togglePosition = async () => {
    const newCommand = isHomePosition ? "ready" : "home";
    setLoading(true);
    try {
      await api.post("/ros2/robot/command", { command: newCommand });
      
      // 로봇 이동 완료 대기
      await waitForMovementComplete(10);
      
      setIsHomePosition(!isHomePosition);
      await fetchStatus();
    } catch (err) {
      setError("위치 변경 실패");
    }
    setLoading(false);
  };

  const robot = status?.state?.robot;
  const tracking = status?.state?.face_tracking;
  const jointTracking = status?.state?.joint_tracking;
  const system = status?.state?.system;
  
  // TRACKING 중이면 웹 제어 비활성화
  const controlAllowed = jointTracking?.control_allowed !== false;

  return (
    <div className="panel robot-panel">
      <div className="panel-header">
        <span className="panel-title">ROBOT CONTROL</span>
        <span className={`panel-tag ${status?.bridge_running ? "online" : "offline"}`}>
          {status?.bridge_running ? "ONLINE" : "OFFLINE"}
        </span>
      </div>
      
      <div className="panel-body">
        {error && <div className="error-message">{error}</div>}
        
        {/* 시스템 상태 */}
        <div className="status-section">
          <h4>시스템 상태</h4>
          <div className="status-grid">
            <StatusIndicator 
              label="Bringup" 
              active={system?.bringup_running} 
            />
            <StatusIndicator 
              label="Camera" 
              active={system?.camera_running} 
            />
            <StatusIndicator 
              label="Detection" 
              active={system?.detection_running} 
            />
            <StatusIndicator 
              label="Tracking" 
              active={system?.tracking_running} 
            />
            <StatusIndicator 
              label="Joint" 
              active={system?.joint_tracking_running} 
            />
          </div>
        </div>

        {/* 로봇 상태 */}
        <div className="status-section">
          <h4>로봇 상태</h4>
          <div className="robot-info">
            <div className="info-row">
              <span>연결:</span>
              <span className={robot?.connected ? "connected" : "disconnected"}>
                {robot?.connected ? "연결됨" : "연결 안됨"}
              </span>
            </div>
            <div className="info-row">
              <span>상태:</span>
              <span>{robot?.status || "unknown"}</span>
            </div>
          </div>
          
          {/* 관절 각도 */}
          {robot?.joint_positions && (
            <div className="joint-display">
              <h5>관절 각도 (deg)</h5>
              <div className="joint-grid">
                {robot.joint_positions.map((pos, i) => (
                  <div key={i} className="joint-item">
                    <span className="joint-label">J{i + 1}</span>
                    <span className="joint-value">
                      {pos.toFixed(1)}°
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* 얼굴 트래킹 상태 */}
        <div className="status-section">
          <h4>얼굴 트래킹</h4>
          <div className="tracking-info">
            <div className="info-row">
              <span>활성화:</span>
              <span className={tracking?.enabled ? "enabled" : "disabled"}>
                {tracking?.enabled ? "ON" : "OFF"}
              </span>
            </div>
            <div className="info-row">
              <span>얼굴 감지:</span>
              <span className={tracking?.face_detected ? "detected" : ""}>
                {tracking?.face_detected ? "감지됨" : "없음"}
              </span>
            </div>
            {tracking?.face_detected && (
              <div className="face-position">
                <span>위치: </span>
                X: {tracking.face_position.x.toFixed(2)}, 
                Y: {tracking.face_position.y.toFixed(2)}, 
                Z: {tracking.face_position.z.toFixed(2)}
              </div>
            )}
          </div>
        </div>

        {/* Joint Tracking 제어 */}
        <div className="control-section">
          <h4>
            제어권: {jointTracking?.control_source === 'web' ? '🌐 웹' : '🖥️ 터미널'}
            {jointTracking?.state === 'TRACKING' && <span className="tracking-active"> (추적중)</span>}
          </h4>
          
          {/* 제어권 버튼 */}
          <div className="control-buttons" style={{marginBottom: '8px'}}>
            <button 
              className={`btn ${jointTracking?.control_source === 'web' ? "btn-success" : "btn-secondary"}`}
              onClick={() => sendCommand("take_control")}
              disabled={loading}
              title="웹에서 제어권 가져오기"
            >
              🌐 웹 제어
            </button>
          </div>

          {/* 기능 버튼 (웹 제어권일 때만 활성화) */}
          <div className="control-buttons">
            <button 
              className={`btn ${jointTracking?.state === 'TRACKING' ? "btn-danger" : "btn-primary"}`}
              onClick={() => sendCommand(jointTracking?.state === 'TRACKING' ? "stop" : "start")}
              disabled={loading || !controlAllowed}
              title={jointTracking?.state === 'TRACKING' ? "추적 중지" : "추적 시작"}
            >
              {jointTracking?.state === 'TRACKING' ? "⏹️ 중지" : "🎯 시작"}
            </button>
            <button 
              className="btn btn-secondary"
              onClick={() => sendCommand("home")}
              disabled={loading || !controlAllowed}
              title="홈 위치로 이동"
            >
              🏠 홈
            </button>
            <button 
              className="btn btn-secondary"
              onClick={() => sendCommand("ready")}
              disabled={loading || !controlAllowed}
              title="시작 위치로 이동"
            >
              📍 준비
            </button>
          </div>
          
          {/* 제어 모드 */}
          <div className="control-buttons" style={{marginTop: '8px'}}>
            <button 
              className={`btn btn-sm ${jointTracking?.control_mode === 1 ? "btn-primary" : "btn-outline"}`}
              onClick={() => sendCommand("mode1")}
              disabled={loading || !controlAllowed}
              title="직접 제어 모드"
            >
              모드1
            </button>
            <button 
              className={`btn btn-sm ${jointTracking?.control_mode === 2 ? "btn-primary" : "btn-outline"}`}
              onClick={() => sendCommand("mode2")}
              disabled={loading || !controlAllowed}
              title="최적 제어 모드"
            >
              모드2
            </button>
          </div>
          
          {!controlAllowed && jointTracking?.control_source !== 'web' && (
            <div className="control-hint">
              ⚠️ 웹 제어권을 가져와야 제어할 수 있습니다
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// 상태 표시 컴포넌트
function StatusIndicator({ label, active }: { label: string; active?: boolean }) {
  return (
    <div className={`status-indicator ${active ? "active" : "inactive"}`}>
      <span className="indicator-dot"></span>
      <span className="indicator-label">{label}</span>
    </div>
  );
}
