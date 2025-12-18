// src/pages/MainPage.tsx
import React from "react";
import { useNavigate } from "react-router-dom";
import CameraPanel from "../components/CameraPanel";
import ServoControl from "../components/ServoControl";
import GripperControl from "../components/GripperControl";
import PersonnelPanel from "../components/PersonnelPanel";
import RobotPanel from "../components/RobotPanel";
import VoicePanel from "../components/VoicePanel";
import ScenarioPanel from "../components/ScenarioPanel";
import CollisionPanel from "../components/CollisionPanel";
import ArmbandPanel from "../components/ArmbandPanel";

type Props = {
  onLogout: () => void;
};

export default function MainPage({ onLogout }: Props) {
  const navigate = useNavigate();

  return (
    <div className="app-root">
      {/* 상단 바 */}
      <header className="top-bar">
        <div className="top-bar-left">
          <div className="top-title">CHECKPOINT - M0609 DEFENSE NODE</div>
          <div className="top-subtitle">
            Intel RealSense D435i · IMU · Servo Control · Access Log
          </div>
        </div>
        <div className="top-bar-right">
          <button
            className="btn-ghost"
            onClick={() => navigate("/admin")}
          >
            ADMIN PANEL
          </button>
          <button
            className="btn-danger"
            onClick={() => {
              onLogout();
              navigate("/login");
            }}
          >
            LOG OUT
          </button>
        </div>
      </header>

      {/* 메인 콘텐츠 영역 - 2행 레이아웃 */}
      <main className="main-layout-compact">
        {/* 상단 행: 카메라 | Armband | 로봇제어 | 시나리오 */}
        <section className="top-row">
          <div className="camera-section">
            <CameraPanel />
          </div>
          <div className="armband-section">
            <ArmbandPanel />
          </div>
          <div className="robot-section">
            <RobotPanel />
          </div>
          <div className="scenario-section">
            <ScenarioPanel />
          </div>
        </section>

        {/* 하단 행: 서보 | 그리퍼 | 음성+충돌 | 인적사항 */}
        <section className="bottom-row">
          <div className="servo-section">
            <ServoControl />
          </div>
          <div className="gripper-section">
            <GripperControl />
          </div>
          <div className="voice-collision-section">
            <VoicePanel />
            <CollisionPanel />
          </div>
          <div className="personnel-section">
            <PersonnelPanel />
          </div>
        </section>
      </main>
    </div>
  );
}
