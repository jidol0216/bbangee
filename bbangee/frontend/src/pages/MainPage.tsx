// src/pages/MainPage.tsx
import React from "react";
import { useNavigate } from "react-router-dom";
import CameraPanel from "../components/CameraPanel";
import ServoControl from "../components/ServoControl";
import PersonnelPanel from "../components/PersonnelPanel";
import RobotPanel from "../components/RobotPanel";

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

      {/* 메인 콘텐츠 영역 */}
      <main className="main-layout">
        {/* 좌측: 카메라 + 서보 */}
        <section className="left-panel">
          <CameraPanel />
          <ServoControl />
        </section>

        {/* 중앙: 로봇 제어 패널 */}
        <section className="center-panel">
          <RobotPanel />
        </section>

        {/* 우측: 인적사항 패널 */}
        <section className="right-panel">
          <PersonnelPanel />
        </section>
      </main>
    </div>
  );
}
