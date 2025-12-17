// src/components/VoicePanel.tsx
/**
 * Voice Authentication Panel for CoBotSentry
 * ============================================
 * 
 * ROS2 voice_auth 노드와 연동되는 음성 인증 웹 UI.
 * 
 * 기능:
 * 1. 암구호 인증 테스트 - /request-auth API 호출
 * 2. 암구호 설정 변경 - /passphrase API 호출
 * 3. 실시간 상태 표시 - /status API 폴링
 * 4. ElevenLabs TTS - /speak, /tts API 호출
 */
import { useState, useRef, useEffect, useCallback } from "react";
import { api } from "../api/client";

interface Voice {
  id: string;
  name: string;
  description: string;
}

interface VoiceAuthStatus {
  enabled: boolean;
  status: string;  // IDLE, LISTENING, PROCESSING, SUCCESS, FAILED, ERROR
  question: string;
  answer: string;
  recognized_text: string;
  last_result: boolean | null;
  voice_auth_running: boolean;
}

const VOICES: Voice[] = [
  { id: "eric", name: "Eric", description: "남성 (기본)" },
  { id: "chris", name: "Chris", description: "남성 - 친근한" },
  { id: "sarah", name: "Sarah", description: "여성 - 차분한" },
  { id: "jessica", name: "Jessica", description: "여성 - 밝은" },
];

// 상태별 스타일 클래스
const STATUS_STYLES: Record<string, { class: string; icon: string; text: string }> = {
  IDLE: { class: "idle", icon: "⏸️", text: "대기 중" },
  LISTENING: { class: "listening", icon: "🎤", text: "녹음 중..." },
  PROCESSING: { class: "processing", icon: "🔄", text: "인식 중..." },
  SUCCESS: { class: "success", icon: "✅", text: "인증 성공!" },
  FAILED: { class: "failed", icon: "❌", text: "인증 실패" },
  ERROR: { class: "error", icon: "⚠️", text: "오류 발생" },
};

export default function VoicePanel() {
  const [text, setText] = useState("");
  const [voice, setVoice] = useState("adam");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  
  // 암구호 관련 상태
  const [authStatus, setAuthStatus] = useState<VoiceAuthStatus | null>(null);
  const [newQuestion, setNewQuestion] = useState("");
  const [newAnswer, setNewAnswer] = useState("");
  const [authLoading, setAuthLoading] = useState(false);

  // 상태 폴링 (1초마다)
  const fetchStatus = useCallback(async () => {
    try {
      const res = await api.get("/voice/status");
      setAuthStatus(res.data);
    } catch (err) {
      // 폴링 에러는 무시
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 1000);
    return () => clearInterval(interval);
  }, [fetchStatus]);

  // 암구호 인증 테스트 시작
  const startAuthTest = async () => {
    setAuthLoading(true);
    setError(null);
    try {
      const res = await api.post("/voice/request-auth", { timeout_sec: 3.5, voice });
      if (!res.data.success) {
        setError(res.data.error || "인증 요청 실패");
      }
      // 상태는 폴링으로 자동 업데이트
    } catch (err) {
      setError("서버 연결 실패 - voice_auth_node가 실행 중인지 확인하세요");
    }
    setAuthLoading(false);
  };

  // 암구호 설정 변경
  const updatePassphrase = async () => {
    if (!newQuestion.trim() || !newAnswer.trim()) {
      setError("질문과 답변을 모두 입력하세요");
      return;
    }
    
    setLoading(true);
    setError(null);
    try {
      const res = await api.post("/voice/passphrase", {
        question: newQuestion.trim(),
        answer: newAnswer.trim()
      });
      
      if (res.data.success) {
        setNewQuestion("");
        setNewAnswer("");
        fetchStatus();  // 상태 갱신
      } else {
        setError("암구호 설정 실패");
      }
    } catch (err) {
      setError("서버 연결 실패");
    }
    setLoading(false);
  };

  // 서버 스피커로 재생 (ElevenLabs)
  const speakOnServer = async (message: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.post("/voice/speak", { text: message, voice });
      if (!res.data.success) {
        setError(res.data.error || "재생 실패");
      }
    } catch (err) {
      setError("서버 연결 실패");
    }
    setLoading(false);
  };

  // 웹 브라우저에서 재생 (ElevenLabs)
  const speakOnBrowser = async (message: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.post(
        "/voice/tts",
        { text: message, voice },
        { responseType: "blob" }
      );
      
      const audioBlob = new Blob([res.data], { type: "audio/mpeg" });
      const audioUrl = URL.createObjectURL(audioBlob);
      
      if (audioRef.current) {
        audioRef.current.src = audioUrl;
        audioRef.current.play();
      }
    } catch (err) {
      setError("TTS 변환 실패");
    }
    setLoading(false);
  };

  // 아군/적군 강제 판정 (테스트용)
  const forceDecision = async (isAlly: boolean) => {
    setLoading(true);
    try {
      if (isAlly) {
        await api.post("/voice/welcome");
      } else {
        await api.post("/voice/access-denied");
      }
    } catch (err) {
      setError("재생 실패");
    }
    setLoading(false);
  };

  const statusInfo = STATUS_STYLES[authStatus?.status || "IDLE"];

  return (
    <div className="panel voice-panel">
      <div className="panel-header">
        <span className="panel-title">🔊 VOICE</span>
        <span className={`panel-tag ${authStatus?.voice_auth_running ? "online" : "offline"}`}>
          {authStatus?.voice_auth_running ? "ROS2 연결됨" : "ROS2 대기"}
        </span>
      </div>

      <div className="panel-body">
        {error && <div className="error-message">{error}</div>}

        {/* 실시간 인증 상태 */}
        <div className={`auth-status-box ${statusInfo.class}`}>
          <div className="status-header">
            <span className="status-icon">{statusInfo.icon}</span>
            <span className="status-text">{statusInfo.text}</span>
          </div>
          {authStatus?.recognized_text && (
            <div className="recognized-text">
              📝 인식: "{authStatus.recognized_text}"
            </div>
          )}
          {authStatus?.last_result !== null && authStatus?.last_result !== undefined && (
            <div className={`last-result ${authStatus?.last_result ? "success" : "failed"}`}>
              {authStatus?.last_result ? "✅ 마지막 인증: 성공" : "❌ 마지막 인증: 실패"}
            </div>
          )}
        </div>

        {/* 현재 암구호 표시 */}
        <div className="current-passphrase">
          <div className="passphrase-label">🔐 현재 암구호</div>
          <div className="passphrase-pair">
            <span className="question">질문: <strong>"{authStatus?.question || '까마귀'}"</strong></span>
            <span className="arrow">→</span>
            <span className="answer">답변: <strong>"{authStatus?.answer || '백두산'}"</strong></span>
          </div>
        </div>

        {/* 암구호 인증 테스트 */}
        <div className="voice-scenario">
          <label>🎖️ 암구호 인증 테스트:</label>
          <button
            className={`btn btn-warning btn-block ${authLoading ? "loading" : ""}`}
            onClick={startAuthTest}
            disabled={authLoading || authStatus?.status === "LISTENING" || authStatus?.status === "PROCESSING"}
          >
            {authLoading ? "🔄 인증 진행 중..." : "🔒 암구호 테스트 시작"}
          </button>
          <small className="help-text">
            TTS로 질문 → 마이크 녹음 (3.5초) → STT 인식 → 판정
          </small>
        </div>

        {/* 암구호 설정 변경 */}
        <div className="passphrase-settings">
          <label>🔧 암구호 변경:</label>
          <div className="passphrase-inputs">
            <input
              type="text"
              value={newQuestion}
              onChange={(e) => setNewQuestion(e.target.value)}
              placeholder="질문 (예: 까마귀)"
              className="passphrase-input"
            />
            <span className="arrow-text">→</span>
            <input
              type="text"
              value={newAnswer}
              onChange={(e) => setNewAnswer(e.target.value)}
              placeholder="답변 (예: 백두산)"
              className="passphrase-input"
              onKeyDown={(e) => e.key === "Enter" && updatePassphrase()}
            />
            <button
              className="btn btn-sm btn-success"
              onClick={updatePassphrase}
              disabled={loading || !newQuestion.trim() || !newAnswer.trim()}
            >
              변경
            </button>
          </div>
        </div>

        {/* 음성 선택 */}
        <div className="voice-select">
          <label>🎙️ ElevenLabs 음성:</label>
          <select value={voice} onChange={(e) => setVoice(e.target.value)}>
            {VOICES.map((v) => (
              <option key={v.id} value={v.id}>
                {v.name} ({v.description})
              </option>
            ))}
          </select>
        </div>

        {/* 테스트용 강제 판정 */}
        <div className="force-decision">
          <label>🧪 테스트용 강제 판정:</label>
          <div className="decision-buttons">
            <button
              className="btn btn-primary"
              onClick={() => forceDecision(true)}
              disabled={loading}
            >
              👋 아군으로 처리
            </button>
            <button
              className="btn btn-danger"
              onClick={() => forceDecision(false)}
              disabled={loading}
            >
              🚫 적군으로 처리
            </button>
          </div>
        </div>

        {/* 커스텀 텍스트 입력 */}
        <div className="voice-custom">
          <label>💬 직접 입력:</label>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="음성으로 변환할 텍스트를 입력하세요..."
            rows={2}
          />
          <div className="voice-actions">
            <button
              className="btn btn-primary"
              onClick={() => speakOnServer(text)}
              disabled={loading || !text.trim()}
              title="서버(로봇 옆) 스피커로 재생"
            >
              🔈 서버 재생
            </button>
            <button
              className="btn btn-secondary"
              onClick={() => speakOnBrowser(text)}
              disabled={loading || !text.trim()}
              title="웹 브라우저에서 재생"
            >
              🎧 브라우저 재생
            </button>
          </div>
        </div>

        {/* 숨겨진 오디오 플레이어 */}
        <audio ref={audioRef} style={{ display: "none" }} />
        
        {loading && <div className="voice-loading">🔄 처리 중...</div>}
      </div>
    </div>
  );
}
