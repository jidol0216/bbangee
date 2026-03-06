// src/components/ServoControl.tsx
import React, { useState, useEffect, useCallback } from "react";
import { api } from "../api/client";

// ESP32 연결 상태 타입
interface ESP32Status {
  connected: boolean;
  latency_ms?: number;
  error?: string;
  ip: string;
  fail_count: number;
}

export default function ServoControl() {
  const [state, setState] = useState<"idle" | "on" | "off">("idle");
  const [laserState, setLaserState] = useState<"off" | "on">("off");
  const [loading, setLoading] = useState(false);
  const [loadingLaser, setLoadingLaser] = useState(false);
  
  // 자동 모드 상태
  const [laserAuto, setLaserAuto] = useState(false);
  const [servoAuto, setServoAuto] = useState(false);
  const [timeout, setTimeout] = useState(1.0);
  const [loadingAuto, setLoadingAuto] = useState(false);
  
  // ESP32 연결 상태
  const [esp32Status, setEsp32Status] = useState<ESP32Status>({
    connected: false,
    ip: "192.168.10.50",
    fail_count: 0
  });
  const [checkingConnection, setCheckingConnection] = useState(false);
  const [resetting, setResetting] = useState(false);
  
  // ESP32 연결 상태 확인
  const checkEsp32Connection = useCallback(async () => {
    try {
      const res = await api.get("/device/esp32/status");
      setEsp32Status({
        connected: res.data.connected,
        latency_ms: res.data.latency_ms,
        error: res.data.error,
        ip: res.data.ip,
        fail_count: res.data.fail_count
      });
    } catch (e) {
      setEsp32Status(prev => ({
        ...prev,
        connected: false,
        error: "Backend unreachable",
        fail_count: prev.fail_count + 1
      }));
    }
  }, []);
  
  // ESP32 리셋 (연결 재시도 + 초기화)
  const resetEsp32 = async () => {
    setResetting(true);
    try {
      const res = await api.post("/device/esp32/reset");
      if (res.data.status === "ok") {
        setState("off");
        setLaserState("off");
      }
      await checkEsp32Connection();
    } catch (e) {
      console.error("ESP32 reset failed:", e);
    } finally {
      setResetting(false);
    }
  };
  
  // 자동 모드 상태 조회
  const fetchAutoMode = async () => {
    try {
      const res = await api.get("/device/auto");
      setLaserAuto(res.data.laser_auto);
      setServoAuto(res.data.servo_auto);
      setTimeout(res.data.timeout);
      // 실시간 상태도 반영
      if (res.data.laser_state) setLaserState("on");
      else if (laserAuto) setLaserState("off");
      if (res.data.servo_state) setState("on");
      else if (servoAuto) setState("off");
    } catch (e) {
      console.error(e);
    }
  };
  
  // 자동 모드 토글
  const toggleAutoMode = async (device: "laser" | "servo") => {
    setLoadingAuto(true);
    try {
      const newValue = device === "laser" ? !laserAuto : !servoAuto;
      await api.post("/device/auto", {
        [device]: newValue
      });
      if (device === "laser") setLaserAuto(newValue);
      else setServoAuto(newValue);
    } catch (e) {
      console.error(e);
    } finally {
      setLoadingAuto(false);
    }
  };
  
  // 초기 로드 + 주기적 갱신
  useEffect(() => {
    fetchAutoMode();
    checkEsp32Connection();  // 초기 연결 확인
    
    const interval = setInterval(fetchAutoMode, 2000);  // 2초마다 갱신
    const connectionInterval = setInterval(checkEsp32Connection, 5000);  // 5초마다 연결 확인
    
    return () => {
      clearInterval(interval);
      clearInterval(connectionInterval);
    };
  }, [checkEsp32Connection]);

  const sendCommand = async (target: "on" | "off") => {
    setLoading(true);
    try {
      await api.post("/device/servo", { target });
      setState(target);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  // ===========================
  //  레이저 제어
  // ===========================
  const sendLaserCommand = async (target: "on" | "off") => {
    setLoadingLaser(true);
    try {
      await api.post("/device/laser", { target }); //  laser 엔드포인트
      setLaserState(target);
    } catch (e) {
      console.error(e);
    } finally {
      setLoadingLaser(false);
    }
  };
  return (
    <div className="panel servo-panel">
      <div className="panel-header">
        <span className="panel-title">SERVO CONTROL</span>
        <span className="panel-tag">WEAPON MOUNT</span>
      </div>

      <div className="panel-body servo-body">
        {/* ===== ESP32 연결 상태 ===== */}
        <div style={{
          padding: '8px 12px',
          marginBottom: '12px',
          borderRadius: '6px',
          background: esp32Status.connected 
            ? 'rgba(55, 255, 159, 0.1)' 
            : 'rgba(255, 107, 107, 0.1)',
          border: `1px solid ${esp32Status.connected ? '#37ff9f' : '#ff6b6b'}`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '8px'
        }}>
          <div style={{display: 'flex', alignItems: 'center', gap: '8px'}}>
            <span style={{
              width: '10px',
              height: '10px',
              borderRadius: '50%',
              background: esp32Status.connected ? '#37ff9f' : '#ff6b6b',
              boxShadow: esp32Status.connected 
                ? '0 0 8px #37ff9f' 
                : '0 0 8px #ff6b6b',
              animation: esp32Status.connected ? 'none' : 'blink 1s infinite'
            }} />
            <span style={{fontSize: '12px', color: esp32Status.connected ? '#37ff9f' : '#ff6b6b'}}>
              {esp32Status.connected 
                ? `ESP32 연결됨 (${esp32Status.latency_ms}ms)` 
                : `ESP32 연결 끊김`}
            </span>
            <span style={{fontSize: '10px', color: '#666'}}>
              {esp32Status.ip}
            </span>
          </div>
          <button
            onClick={resetEsp32}
            disabled={resetting}
            style={{
              padding: '4px 10px',
              fontSize: '11px',
              background: esp32Status.connected ? '#333' : '#ff6b6b',
              color: '#fff',
              border: 'none',
              borderRadius: '4px',
              cursor: resetting ? 'wait' : 'pointer',
              opacity: resetting ? 0.6 : 1
            }}
            title="ESP32 연결 재시도 및 초기화"
          >
            {resetting ? '⏳' : ''} {esp32Status.connected ? '리셋' : '재연결'}
          </button>
        </div>
        
        {/* 연결 실패 경고 */}
        {!esp32Status.connected && esp32Status.fail_count > 3 && (
          <div style={{
            padding: '8px',
            marginBottom: '12px',
            background: 'rgba(255, 165, 0, 0.1)',
            borderRadius: '4px',
            fontSize: '11px',
            color: '#ffa500'
          }}>
             ESP32 연결 실패 {esp32Status.fail_count}회<br/>
            <span style={{fontSize: '10px', color: '#888'}}>
              아두이노 전원을 확인하거나 재부팅해주세요
            </span>
          </div>
        )}
        
        {/* ===== 서보 섹션 ===== */}
        <div className="servo-status">
          서보 상태:{" "}
          <span className={`servo-state servo-state-${state}`}>
            {state.toUpperCase()}
          </span>
          {servoAuto && <span style={{marginLeft: 8, color: '#37ff9f', fontSize: 11}}> AUTO</span>}
        </div>
        <div className="servo-buttons">
          <button
            className="btn-primary"
            disabled={loading || servoAuto || !esp32Status.connected}
            onClick={() => sendCommand("on")}
            title={!esp32Status.connected ? "ESP32 연결 필요" : servoAuto ? "자동 모드에서는 수동 제어 불가" : ""}
          >
            ARM - SERVO ON
          </button>
          <button
            className="btn-danger"
            disabled={loading || servoAuto || !esp32Status.connected}
            onClick={() => sendCommand("off")}
            title={!esp32Status.connected ? "ESP32 연결 필요" : servoAuto ? "자동 모드에서는 수동 제어 불가" : ""}
          >
            SAFE - SERVO OFF
          </button>
        </div>
        {/* 서보 자동 모드 토글 */}
        <div style={{marginTop: 8}}>
          <label style={{display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer'}}>
            <input
              type="checkbox"
              checked={servoAuto}
              onChange={() => toggleAutoMode("servo")}
              disabled={loadingAuto}
              style={{width: 16, height: 16}}
            />
            <span style={{fontSize: 12, color: servoAuto ? '#37ff9f' : '#888'}}>
               얼굴 감지 → 서보 자동 ON/OFF
            </span>
          </label>
        </div>
        
        <hr style={{ margin: "16px 0", opacity: 0.2 }} />
        
        {/* ===== 레이저 섹션 ===== */}
        <div className="servo-status">
          레이저 상태:{" "}
          <span className={`servo-state servo-state-${laserState}`}>
            {laserState.toUpperCase()}
          </span>
          {laserAuto && <span style={{marginLeft: 8, color: '#ff6b6b', fontSize: 11}}> AUTO</span>}
        </div>
        <div className="servo-buttons">
          <button
            className="btn-primary"
            disabled={loadingLaser || laserAuto || !esp32Status.connected}
            onClick={() => sendLaserCommand("on")}
            title={!esp32Status.connected ? "ESP32 연결 필요" : laserAuto ? "자동 모드에서는 수동 제어 불가" : ""}
          >
            LASER ON
          </button>
          <button
            className="btn-danger"
            disabled={loadingLaser || laserAuto || !esp32Status.connected}
            onClick={() => sendLaserCommand("off")}
            title={!esp32Status.connected ? "ESP32 연결 필요" : laserAuto ? "자동 모드에서는 수동 제어 불가" : ""}
          >
            LASER OFF
          </button>
        </div>
        {/* 레이저 자동 모드 토글 */}
        <div style={{marginTop: 8}}>
          <label style={{display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer'}}>
            <input
              type="checkbox"
              checked={laserAuto}
              onChange={() => toggleAutoMode("laser")}
              disabled={loadingAuto}
              style={{width: 16, height: 16}}
            />
            <span style={{fontSize: 12, color: laserAuto ? '#ff6b6b' : '#888'}}>
               얼굴 감지 → 레이저 자동 ON/OFF
            </span>
          </label>
        </div>
        
        {/* 자동 모드 안내 */}
        {(laserAuto || servoAuto) && (
          <div style={{marginTop: 12, padding: 8, background: 'rgba(255,255,255,0.05)', borderRadius: 6, fontSize: 11, color: '#aaa'}}>
             자동 모드: 얼굴 감지 시 ON, {timeout}초 미감지 시 OFF
          </div>
        )}
        
      </div>
    </div>
  );
}
