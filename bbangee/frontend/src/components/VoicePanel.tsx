// src/components/VoicePanel.tsx
import { useState, useRef } from "react";
import { api } from "../api/client";

interface Voice {
  id: string;
  name: string;
  description: string;
}

// 정답 암구호 (실제 환경에서는 서버에서 관리)
const CORRECT_PASSWORD = "충성";

const VOICES: Voice[] = [
  { id: "alloy", name: "Alloy", description: "중성적" },
  { id: "echo", name: "Echo", description: "남성적" },
  { id: "fable", name: "Fable", description: "영국식" },
  { id: "onyx", name: "Onyx", description: "깊은 남성" },
  { id: "nova", name: "Nova", description: "여성적" },
  { id: "shimmer", name: "Shimmer", description: "밝은 여성" },
];

export default function VoicePanel() {
  const [text, setText] = useState("");
  const [voice, setVoice] = useState("nova");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  
  // 암구호 입력 관련 상태
  const [passwordInput, setPasswordInput] = useState("");
  const [passwordMode, setPasswordMode] = useState(false); // 암구호 입력 대기 모드

  // 서버 스피커로 재생 (로봇 옆 스피커)
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

  // 웹 브라우저에서 재생
  const speakOnBrowser = async (message: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.post(
        "/voice/tts",
        { text: message, voice },
        { responseType: "blob" }
      );
      
      // Blob으로 오디오 재생
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

  // 암구호 질문 시작 (TTS 재생 + 입력 모드 활성화)
  const startPasswordChallenge = async () => {
    setLoading(true);
    setPasswordInput("");
    try {
      await api.post("/voice/ask-password");
      setPasswordMode(true); // 입력 모드 활성화
    } catch (err) {
      setError("암구호 질문 재생 실패");
    }
    setLoading(false);
  };

  // 암구호 제출
  const submitPassword = async () => {
    setLoading(true);
    const isCorrect = passwordInput.trim() === CORRECT_PASSWORD;
    try {
      await api.post(`/voice/password-result?correct=${isCorrect}`);
      setPasswordMode(false);
      setPasswordInput("");
    } catch (err) {
      setError("응답 재생 실패");
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

  return (
    <div className="panel voice-panel">
      <div className="panel-header">
        <span className="panel-title">🔊 VOICE</span>
        <span className="panel-tag online">TTS</span>
      </div>

      <div className="panel-body">
        {error && <div className="error-message">{error}</div>}

        {/* 음성 선택 */}
        <div className="voice-select">
          <label>음성 선택:</label>
          <select value={voice} onChange={(e) => setVoice(e.target.value)}>
            {VOICES.map((v) => (
              <option key={v.id} value={v.id}>
                {v.name} ({v.description})
              </option>
            ))}
          </select>
        </div>

        {/* 암구호 시나리오 버튼 */}
        <div className="voice-scenario">
          <label>🎖️ 암구호 시나리오:</label>
          
          {/* 암구호 질문 시작 버튼 */}
          <button
            className="btn btn-warning btn-block"
            onClick={startPasswordChallenge}
            disabled={loading || passwordMode}
          >
            🔒 암구호 질문 시작
          </button>

          {/* 암구호 입력 필드 (질문 후 활성화) */}
          {passwordMode && (
            <div className="password-input-section">
              <input
                type="text"
                value={passwordInput}
                onChange={(e) => setPasswordInput(e.target.value)}
                placeholder="암구호를 입력하세요..."
                className="password-input"
                autoFocus
                onKeyDown={(e) => e.key === "Enter" && submitPassword()}
              />
              <div className="password-actions">
                <button
                  className="btn btn-success"
                  onClick={submitPassword}
                  disabled={loading || !passwordInput.trim()}
                >
                  ✅ 제출
                </button>
                <button
                  className="btn btn-secondary"
                  onClick={() => { setPasswordMode(false); setPasswordInput(""); }}
                  disabled={loading}
                >
                  ❌ 취소
                </button>
              </div>
              <small className="password-hint">정답: "{CORRECT_PASSWORD}"</small>
            </div>
          )}

          {/* 아군/적군 강제 판정 (테스트용) */}
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
        </div>

        {/* 커스텀 텍스트 입력 */}
        <div className="voice-custom">
          <label>직접 입력:</label>
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
