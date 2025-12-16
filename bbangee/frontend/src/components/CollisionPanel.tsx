// src/components/CollisionPanel.tsx
import { useState, useEffect } from "react";
import { api } from "../api/client";

interface CollisionState {
  robot_state: string;
  robot_state_code: number;
  is_safe_stop: boolean;
  is_recovering: boolean;
  last_action: string;
  log: string[];
  timestamp: number;
}

interface CollisionStatus {
  node_running: boolean;
  state: CollisionState;
}

export default function CollisionPanel() {
  const [status, setStatus] = useState<CollisionStatus | null>(null);
  const [loading, setLoading] = useState(false);

  // 상태 조회
  const fetchStatus = async () => {
    try {
      const res = await api.get("/ros2/collision/status");
      setStatus(res.data);
    } catch (err) {
      // 조용히 실패
    }
  };

  // 주기적 상태 조회 (1초마다)
  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 1000);
    return () => clearInterval(interval);
  }, []);

  // 명령 전송
  const sendCommand = async (command: string) => {
    setLoading(true);
    try {
      await api.post("/ros2/collision/command", { command });
      await fetchStatus();
    } catch (err) {
      // 조용히 실패
    }
    setLoading(false);
  };

  const state = status?.state;
  const nodeRunning = status?.node_running ?? false;

  // 상태에 따른 클래스
  const getStateClass = () => {
    if (!state) return "state-unknown";
    if (state.is_safe_stop) return "state-warning";
    if (state.is_recovering) return "state-recovering";
    if (state.robot_state === "STANDBY") return "state-ok";
    if (state.robot_state === "MOVING") return "state-moving";
    return "state-unknown";
  };

  return (
    <div className="panel collision-panel-compact">
      <div className="panel-header">
        <span className="panel-title">🛡️ 충돌복구</span>
        <span className={`panel-tag ${nodeRunning ? 'online' : 'offline'}`}>
          {nodeRunning ? 'ON' : 'OFF'}
        </span>
      </div>

      <div className="panel-body collision-body-compact">
        {/* 상태 + 복구 버튼 한 줄 */}
        <div className="collision-row">
          <span className={`collision-state-badge ${getStateClass()}`}>
            {state?.robot_state || 'UNKNOWN'}
          </span>
          <button
            className="btn-collision-sm btn-recovery"
            onClick={() => sendCommand('auto_recovery')}
            disabled={loading || state?.is_recovering}
            title="자동 복구 실행"
          >
            {state?.is_recovering ? '🔄' : '🔧'} 복구
          </button>
        </div>

        {/* 충돌 테스트 버튼 */}
        <div className="collision-test-row">
          <span className="test-label">테스트:</span>
          <button
            className="btn-collision-sm btn-test-slow"
            onClick={() => {
              if (confirm('바닥으로 천천히 이동 → 충돌 → 자동복구 → 홈 복귀')) {
                sendCommand('move_down_slow');
              }
            }}
            disabled={loading || state?.is_recovering}
            title="느린 충돌 테스트"
          >
            🐢
          </button>
          <button
            className="btn-collision-sm btn-test-fast"
            onClick={() => {
              if (confirm('바닥으로 빠르게 이동 → 충돌 → 자동복구 → 홈 복귀')) {
                sendCommand('move_down_fast');
              }
            }}
            disabled={loading || state?.is_recovering}
            title="빠른 충돌 테스트"
          >
            🐇
          </button>
        </div>

        {/* 최근 로그 3줄 */}
        <div className="collision-log-compact">
          {state?.log && state.log.length > 0 
            ? state.log.slice(-3).map((line, i) => (
                <div key={i} className="log-line">{line}</div>
              ))
            : <div className="log-empty">-</div>}
        </div>
      </div>
    </div>
  );
}
