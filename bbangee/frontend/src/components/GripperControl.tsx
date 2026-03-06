// src/components/GripperControl.tsx
import React, { useState, useEffect, useCallback } from "react";
import { api } from "../api/client";

interface GripperStatus {
  width: number;
  force: number;
  grip_detected: boolean;
  connected: boolean;
}

export default function GripperControl() {
  const [status, setStatus] = useState<GripperStatus>({
    width: 0,
    force: 20,
    grip_detected: false,
    connected: false
  });
  const [loading, setLoading] = useState(false);

  // 상태 조회
  const fetchStatus = useCallback(async () => {
    try {
      const res = await api.get("/gripper/status");
      setStatus({
        width: res.data.width,
        force: res.data.force,
        grip_detected: res.data.grip_detected,
        connected: res.data.connected
      });
    } catch (e) {
      setStatus(prev => ({ ...prev, connected: false }));
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 2000);
    return () => clearInterval(interval);
  }, [fetchStatus]);

  // 열기/닫기 (ROS2 파라미터로 설정된 값 사용: open_width=110mm, close_width=0mm, default_force=20N)
  const handleAction = async (action: "open" | "close") => {
    setLoading(true);
    try {
      await api.post("/gripper/action", { action });
      setTimeout(fetchStatus, 500);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  // 프리셋
  const handlePreset = async (preset: string) => {
    setLoading(true);
    try {
      await api.post(`/gripper/preset/${preset}`);
      setTimeout(fetchStatus, 500);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  // 권총 파지/거치
  const handlePistol = async (action: "grip" | "holster") => {
    setLoading(true);
    try {
      await api.post(`/pistol/${action}`);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="panel gripper-panel">
      <div className="panel-header">
        <span className="panel-title">GRIPPER</span>
        <span className="panel-tag">RG2</span>
      </div>

      <div className="panel-body">
        {/* 연결 상태 */}
        <div style={{
          padding: '8px 12px',
          marginBottom: '12px',
          borderRadius: '6px',
          background: status.connected 
            ? 'rgba(55, 255, 159, 0.1)' 
            : 'rgba(255, 107, 107, 0.1)',
          border: `1px solid ${status.connected ? '#37ff9f' : '#ff6b6b'}`,
          display: 'flex',
          alignItems: 'center',
          gap: '8px'
        }}>
          <span style={{
            width: '10px',
            height: '10px',
            borderRadius: '50%',
            background: status.connected ? '#37ff9f' : '#ff6b6b',
            boxShadow: status.connected 
              ? '0 0 8px #37ff9f' 
              : '0 0 8px #ff6b6b'
          }} />
          <span style={{fontSize: '12px', color: status.connected ? '#37ff9f' : '#ff6b6b'}}>
            {status.connected ? '연결됨' : '연결 안됨'}
          </span>
          {status.grip_detected && (
            <span style={{
              marginLeft: 'auto',
              fontSize: '11px',
              color: '#ffa500',
              background: 'rgba(255,165,0,0.1)',
              padding: '2px 8px',
              borderRadius: '4px'
            }}>
               물체 감지
            </span>
          )}
        </div>

        {/* 현재 상태 - 컴팩트 */}
        <div style={{
          display: 'flex',
          justifyContent: 'space-around',
          marginBottom: '12px',
          padding: '8px',
          background: 'rgba(255,255,255,0.03)',
          borderRadius: '6px'
        }}>
          <div style={{textAlign: 'center'}}>
            <div style={{fontSize: '10px', color: '#666'}}>폭</div>
            <div style={{fontSize: '16px', fontWeight: 'bold', color: '#4a9eff'}}>
              {status.width.toFixed(0)}<span style={{fontSize: '10px', color: '#666'}}>mm</span>
            </div>
          </div>
          <div style={{width: '1px', background: 'rgba(255,255,255,0.1)'}} />
          <div style={{textAlign: 'center'}}>
            <div style={{fontSize: '10px', color: '#666'}}>힘</div>
            <div style={{fontSize: '16px', fontWeight: 'bold', color: '#ff6b6b'}}>
              {status.force.toFixed(0)}<span style={{fontSize: '10px', color: '#666'}}>N</span>
            </div>
          </div>
        </div>

        {/* 열기/닫기 버튼 */}
        <div style={{display: 'flex', gap: '8px', marginBottom: '12px'}}>
          <button
            className="btn btn-primary"
            onClick={() => handleAction("open")}
            disabled={loading || !status.connected}
            style={{flex: 1, padding: '10px'}}
          >
             열기
          </button>
          <button
            className="btn btn-danger"
            onClick={() => handleAction("close")}
            disabled={loading || !status.connected}
            style={{flex: 1, padding: '10px'}}
          >
             닫기
          </button>
        </div>

        {/* 권총 파지/거치 버튼 */}
        <div style={{fontSize: '11px', color: '#666', marginBottom: '6px'}}> 권총 제어</div>
        <div style={{display: 'flex', gap: '8px', marginBottom: '12px'}}>
          <button
            className="btn"
            onClick={() => handlePistol("grip")}
            disabled={loading}
            style={{
              flex: 1, 
              padding: '12px',
              background: 'linear-gradient(135deg, #ff6b6b 0%, #ee5a5a 100%)',
              border: 'none',
              fontWeight: 'bold'
            }}
          >
             권총 파지
          </button>
          <button
            className="btn"
            onClick={() => handlePistol("holster")}
            disabled={loading}
            style={{
              flex: 1, 
              padding: '12px',
              background: 'linear-gradient(135deg, #4a9eff 0%, #3a8eef 100%)',
              border: 'none',
              fontWeight: 'bold'
            }}
          >
             권총 거치
          </button>
        </div>

        {/* 프리셋 버튼 - 2x3 그리드 */}
        <div style={{fontSize: '11px', color: '#666', marginBottom: '6px'}}>프리셋</div>
        <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px'}}>
          <button
            className="btn btn-sm btn-outline"
            onClick={() => handlePreset("full_open")}
            disabled={loading || !status.connected}
            style={{fontSize: '11px', padding: '6px'}}
          >
            전체 열기
          </button>
          <button
            className="btn btn-sm btn-outline"
            onClick={() => handlePreset("half_open")}
            disabled={loading || !status.connected}
            style={{fontSize: '11px', padding: '6px'}}
          >
            절반 열기
          </button>
          <button
            className="btn btn-sm btn-outline"
            onClick={() => handlePreset("gentle_close")}
            disabled={loading || !status.connected}
            style={{fontSize: '11px', padding: '6px'}}
          >
            약하게 잡기
          </button>
          <button
            className="btn btn-sm btn-outline"
            onClick={() => handlePreset("firm_close")}
            disabled={loading || !status.connected}
            style={{fontSize: '11px', padding: '6px'}}
          >
            강하게 잡기
          </button>
          <button
            className="btn btn-sm btn-outline"
            onClick={() => handlePreset("pick_small")}
            disabled={loading || !status.connected}
            style={{fontSize: '11px', padding: '6px'}}
          >
            작은 물체
          </button>
          <button
            className="btn btn-sm btn-outline"
            onClick={() => handlePreset("pick_large")}
            disabled={loading || !status.connected}
            style={{fontSize: '11px', padding: '6px'}}
          >
            큰 물체
          </button>
        </div>
      </div>
    </div>
  );
}
