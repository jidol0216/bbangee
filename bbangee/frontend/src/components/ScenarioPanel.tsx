// src/components/ScenarioPanel.tsx
// 시나리오 상태 머신 UI - 분기형 인터랙티브 플로우차트

import { useState, useEffect, useRef, useCallback } from "react";
import { api } from "../api/client";

type ScenarioState = 
  | "IDLE" | "DETECTED" | "PASSWORD_CHECK" 
  | "ALLY_PASS" | "ALLY_ALERT" | "ENEMY_CRITICAL" | "ENEMY_ENGAGE";

type PersonType = "UNKNOWN" | "ALLY" | "ENEMY";

interface ScenarioStatus {
  state: ScenarioState;
  person_type: PersonType;
  history: { time: string; state: string; event: string }[];
}

const STATE_INFO: Record<ScenarioState, { label: string; icon: string; color: string }> = {
  IDLE: { label: "초기 경계", icon: "🛡️", color: "#4a9eff" },
  DETECTED: { label: "접근자 감지", icon: "👁️", color: "#ffa500" },
  PASSWORD_CHECK: { label: "암구호 확인", icon: "🔒", color: "#9370db" },
  ALLY_PASS: { label: "아군 통과", icon: "✅", color: "#37ff9f" },
  ALLY_ALERT: { label: "아군 경고", icon: "⚠️", color: "#ff9500" },
  ENEMY_CRITICAL: { label: "기밀유출!", icon: "🚨", color: "#ff0000" },
  ENEMY_ENGAGE: { label: "적대 대응", icon: "🔴", color: "#ff4444" },
};

export default function ScenarioPanel() {
  const [status, setStatus] = useState<ScenarioStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [popup, setPopup] = useState<{ show: boolean; title: string; type: string } | null>(null);
  const [passwordInput, setPasswordInput] = useState("");
  const [newChallenge, setNewChallenge] = useState("");
  const [newResponse, setNewResponse] = useState("");
  const [currentChallenge, setCurrentChallenge] = useState("로키");
  const [currentResponse, setCurrentResponse] = useState("협동");
  const [motionLoading, setMotionLoading] = useState(false);
  const [passwordResult, setPasswordResult] = useState<{ correct: boolean; message: string } | null>(null);
  const [voiceStatus, setVoiceStatus] = useState<{ status: string; recognized_text: string } | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await api.get("/scenario/status");
      setStatus(res.data);
      if (res.data.password_challenge) {
        setCurrentChallenge(res.data.password_challenge);
      }
      if (res.data.password_response) {
        setCurrentResponse(res.data.password_response);
      }
      // 음성 인식 상태도 가져오기
      const voiceRes = await api.get("/voice/status");
      setVoiceStatus(voiceRes.data);
    } catch (err) {
      console.error(err);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    const ws = new WebSocket(`ws://${window.location.hostname}:8000/scenario/ws`);
    wsRef.current = ws;
    ws.onmessage = (e) => {
      const data = JSON.parse(e.data);
      console.log("[ScenarioPanel] WS received:", data);
      fetchStatus();
      if (data.popup?.show) {
        setPopup({ show: true, title: data.popup.title, type: data.popup.buttons ? "identify" : "password" });
      }
      if (data.type === "scenario_result") {
        // 암구호 결과 UI 업데이트 (보이스/웹 모두 적용)
        console.log("[ScenarioPanel] Setting password result:", data.is_correct, data.message);
        const spokenPassword = data.spoken_password || "";
        setPasswordResult({
          correct: data.is_correct,
          message: data.is_correct 
            ? `✅ 정답! "${spokenPassword}" 암구호 인증 성공` 
            : `❌ 오답! "${spokenPassword}" 암구호 인증 실패`
        });
        setPopup({ show: true, title: data.message, type: "result" });
      }
    };
    const ping = setInterval(() => ws.readyState === WebSocket.OPEN && ws.send("ping"), 30000);
    return () => { clearInterval(ping); ws.close(); };
  }, [fetchStatus]);

  // 상태가 DETECTED일 때 자동으로 피아식별 팝업 표시 (비활성화)
  // useEffect(() => {
  //   if (status?.state === "DETECTED" && !popup?.show) {
  //     setPopup({ show: true, title: "⚠️ 접근자 감지", type: "identify" });
  //   }
  // }, [status?.state]);

  const handleDetect = async () => { setLoading(true); await api.post("/scenario/detect").catch(()=>{}); setLoading(false); };
  const handleIdentify = async (ally: boolean) => { setPopup(null); setLoading(true); await api.post("/scenario/identify", { is_ally: ally }).catch(()=>{}); setLoading(false); setPasswordResult(null); };
  const handlePassword = async () => {
    setPopup(null);
    setLoading(true);
    try {
      const res = await api.post("/scenario/password", { password: passwordInput });
      if (res.data) {
        setPasswordResult({
          correct: res.data.is_correct,
          message: res.data.is_correct ? `✅ 정답! "${passwordInput}"` : `❌ 오답! "${passwordInput}" (정답: "${currentResponse}")`
        });
      }
    } catch (e) { /* ignore */ }
    setPasswordInput("");
    setLoading(false);
  };
  const handleReset = async () => { setPopup(null); setLoading(true); await api.post("/scenario/reset").catch(()=>{}); setLoading(false); setPasswordResult(null); };
  
  // 암구호 설정 (문답식)
  const handleSetPassword = async () => {
    if (!newChallenge.trim()) return;
    try {
      const res = await api.post("/scenario/password/set", { 
        challenge: newChallenge,
        response: newResponse || null
      });
      if (res.data.success) {
        setCurrentChallenge(res.data.challenge);
        if (res.data.response) setCurrentResponse(res.data.response);
        setNewChallenge("");
        setNewResponse("");
      }
    } catch (err) {
      console.error(err);
    }
  };

  // 로봇 모션
  const handleMotion = async (motion: string) => {
    setMotionLoading(true);
    try {
      await api.post("/robot/motion", { motion });
    } catch (err) {
      console.error(err);
    }
    setMotionLoading(false);
  };

  const s = status?.state || "IDLE";
  const p = status?.person_type || "UNKNOWN";
  const info = STATE_INFO[s as ScenarioState];

  const isActive = (state: string) => s === state;
  const isPassed = (state: string) => {
    const order = ["IDLE", "DETECTED", "PASSWORD_CHECK"];
    return order.indexOf(s) > order.indexOf(state) && order.includes(state);
  };

  return (
    <div className="panel scenario-panel">
      <div className="panel-header">
        <span className="panel-title">📋 SCENARIO</span>
        <span className="panel-tag" style={{ background: info.color, color: "#000" }}>{info.icon} {info.label}</span>
      </div>

      <div className="panel-body scenario-body">
        {/* 분기형 트리 플로우차트 */}
        <div className="tree-flow">
          {/* 시작 노드 */}
          <div className={`tree-node start ${isActive("IDLE") ? "active" : isPassed("IDLE") ? "passed" : ""}`}
               onClick={s === "IDLE" && !loading ? handleDetect : undefined}>
            <span className="node-icon">🛡️</span>
            <span className="node-label">초기 경계 (Low Ready)</span>
            {s === "IDLE" && <span className="node-action">▶ 클릭: 감지 시뮬레이션</span>}
          </div>

          <div className="tree-line vertical" />

          {/* 감지 노드 */}
          <div className={`tree-node detect ${isActive("DETECTED") ? "active" : isPassed("DETECTED") ? "passed" : ""}`}>
            <span className="node-icon">👁️</span>
            <span className="node-label">접근자 감지</span>
            <span className="node-sub">"정지! 손들어! 암구호!"</span>
          </div>

          <div className="tree-line vertical" />

          {/* 분기점 */}
          <div className="tree-branch-point">
            <span>피아식별</span>
          </div>

          {/* 분기 영역 */}
          <div className="tree-branches">
            {/* 아군 분기 */}
            <div className={`branch ally ${p === "ALLY" ? "selected" : ""}`}>
              <div className="branch-line left" />
              <div className={`tree-node small ${s === "DETECTED" ? "clickable" : ""} ${p === "ALLY" ? "active" : ""}`}
                   onClick={s === "DETECTED" ? () => handleIdentify(true) : undefined}>
                <span>👤</span>
                <span>아군 추정</span>
              </div>
              <div className="branch-line down" />
              <div className={`tree-node small ${isActive("PASSWORD_CHECK") && p === "ALLY" ? "active" : ""}`}>
                <span>🔒</span>
                <span>암구호 확인</span>
              </div>
              <div className="branch-results">
                <div className={`result-box success ${isActive("ALLY_PASS") ? "active" : ""}`}>
                  <span>✅ 통과 승인</span>
                  <span className="result-detail">경례, 차단봉 개방</span>
                </div>
                <div className={`result-box warning ${isActive("ALLY_ALERT") ? "active" : ""}`}>
                  <span>⚠️ 경고</span>
                  <span className="result-detail">정조준, UI 알림</span>
                </div>
              </div>
            </div>

            {/* 적군 분기 */}
            <div className={`branch enemy ${p === "ENEMY" ? "selected" : ""}`}>
              <div className="branch-line right" />
              <div className={`tree-node small ${s === "DETECTED" ? "clickable" : ""} ${p === "ENEMY" ? "active" : ""}`}
                   onClick={s === "DETECTED" ? () => handleIdentify(false) : undefined}>
                <span>🎭</span>
                <span>적군 추정</span>
              </div>
              <div className="branch-line down" />
              <div className={`tree-node small ${isActive("PASSWORD_CHECK") && p === "ENEMY" ? "active" : ""}`}>
                <span>🔒</span>
                <span>암구호 확인</span>
              </div>
              <div className="branch-results">
                <div className={`result-box critical ${isActive("ENEMY_CRITICAL") ? "active" : ""}`}>
                  <span>🚨 기밀유출</span>
                  <span className="result-detail">심각 경고, 비상</span>
                </div>
                <div className={`result-box danger ${isActive("ENEMY_ENGAGE") ? "active" : ""}`}>
                  <span>🔴 대응</span>
                  <span className="result-detail">비비탄 발사</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* 암구호 문답 현황 (PASSWORD_CHECK 상태일 때 표시) */}
        {s === "PASSWORD_CHECK" && (
          <div className="password-exchange-box">
            <div className="password-exchange-title">🎤 암구호 문답 현황</div>
            <div className="password-exchange-row">
              <div className="exchange-item question">
                <span className="exchange-label">🤖 질문 (로봇)</span>
                <span className="exchange-value">"{currentChallenge}"</span>
              </div>
              <span className="exchange-arrow">→</span>
              <div className="exchange-item answer">
                <span className="exchange-label">👤 응답 (접근자)</span>
                <span className={`exchange-value ${voiceStatus?.recognized_text ? "filled" : "waiting"}`}>
                  {voiceStatus?.status === "LISTENING" ? (
                    <span className="listening-indicator">🎤 녹음 중...</span>
                  ) : voiceStatus?.status === "PROCESSING" ? (
                    <span className="processing-indicator">🔄 인식 중...</span>
                  ) : voiceStatus?.recognized_text ? (
                    `"${voiceStatus.recognized_text}"`
                  ) : (
                    <span className="waiting-text">대기 중...</span>
                  )}
                </span>
              </div>
            </div>
          </div>
        )}

        {/* 암구호 결과 표시 */}
        {passwordResult && (
          <div className={`password-result ${passwordResult.correct ? "correct" : "wrong"}`}>
            <span className="result-icon">{passwordResult.correct ? "✅" : "❌"}</span>
            <span className="result-text">{passwordResult.message}</span>
          </div>
        )}

        {/* 암구호 입력 */}
        {s === "PASSWORD_CHECK" && (
          <div className="password-box">
            <input value={passwordInput} onChange={(e) => setPasswordInput(e.target.value)}
                   placeholder={`응답 암구호 입력 (정답: "${currentResponse}")`} autoFocus
                   onKeyDown={(e) => e.key === "Enter" && handlePassword()} />
            <button className="btn btn-success" onClick={handlePassword} disabled={!passwordInput.trim()}>제출</button>
          </div>
        )}

        {/* 암구호 설정 (문답식) */}
        <div className="password-settings">
          <div className="password-settings-title">🔐 암구호 설정 (문답식)</div>
          <div className="password-settings-row">
            <input
              value={newChallenge}
              onChange={(e) => setNewChallenge(e.target.value)}
              placeholder="질문 (예: 로키)"
              style={{ flex: 1 }}
            />
            <input
              value={newResponse}
              onChange={(e) => setNewResponse(e.target.value)}
              placeholder="응답 (예: 협동)"
              style={{ flex: 1 }}
              onKeyDown={(e) => e.key === "Enter" && handleSetPassword()}
            />
            <button className="btn btn-sm btn-success" onClick={handleSetPassword} disabled={!newChallenge.trim()}>
              변경
            </button>
          </div>
          <div className="password-current">
            질문: <strong>"{currentChallenge}"</strong> → 응답: <strong>"{currentResponse}"</strong>
          </div>
        </div>

        {/* 로봇 모션 테스트 */}
        <div className="action-buttons">
          <button 
            className="btn btn-action btn-salute" 
            onClick={() => handleMotion("salute")}
            disabled={motionLoading}
          >
            🫡 경례 모션
          </button>
          <button 
            className="btn btn-action btn-highready" 
            onClick={() => handleMotion("high_ready")}
            disabled={motionLoading}
          >
            🛡️ High Ready
          </button>
        </div>

        {/* 리셋 - 항상 표시, IDLE일 때만 비활성화 */}
        <button 
          className="btn btn-secondary btn-full" 
          onClick={handleReset} 
          disabled={loading || s === "IDLE"}
        >
          🔄 시나리오 리셋 {s !== "IDLE" && `(현재: ${s})`}
        </button>

        {/* 로그 */}
        <div className="scenario-log">
          <div className="log-title">이벤트 로그</div>
          {status?.history.slice().reverse().slice(0, 3).map((h, i) => (
            <div key={i} className="log-item">
              <span className="log-time">{new Date(h.time).toLocaleTimeString()}</span>
              <span>{h.event}</span>
            </div>
          ))}
        </div>
      </div>

      {/* 팝업 */}
      {popup?.show && (
        <div className="popup-overlay" onClick={() => popup.type === "result" && setPopup(null)}>
          <div className="popup-box" onClick={(e) => e.stopPropagation()}>
            <div className="popup-title">{popup.title}</div>
            {popup.type === "identify" && (
              <div className="popup-btns">
                <button className="btn btn-primary" onClick={() => handleIdentify(true)}>👤 아군</button>
                <button className="btn btn-danger" onClick={() => handleIdentify(false)}>🎭 적군</button>
              </div>
            )}
            {popup.type === "password" && (
              <div className="popup-input">
                <input value={passwordInput} onChange={(e) => setPasswordInput(e.target.value)}
                       placeholder="암구호 입력..." autoFocus onKeyDown={(e) => e.key === "Enter" && handlePassword()} />
                <button className="btn btn-success" onClick={handlePassword}>제출</button>
              </div>
            )}
            {popup.type === "result" && <button className="btn btn-secondary" onClick={() => setPopup(null)}>확인</button>}
          </div>
        </div>
      )}
    </div>
  );
}
