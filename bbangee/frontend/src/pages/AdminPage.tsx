// src/pages/AdminPage.tsx
import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { createPerson, fetchPeople, deletePerson } from "../api/people";
import type { Person } from "../api/people";

type Props = {
  onLogout: () => void;
};

export default function AdminPage({ onLogout }: Props) {
  const navigate = useNavigate();
  const [people, setPeople] = useState<Person[]>([]);
  const [file, setFile] = useState<File | null>(null);

  const [form, setForm] = useState({
    military_serial: "",
    name: "",
    department: "",
    rank: "",
  });

  /**  DB 데이터 load */
  const load = async () => {
    const data = await fetchPeople();
    setPeople(data);
  };

  useEffect(() => {
    load();
  }, []);

  /**  등록 핸들러 */
  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();

    const formData = new FormData();
    formData.append("military_serial", form.military_serial);
    formData.append("name", form.name);
    formData.append("department", form.department);
    formData.append("rank", form.rank);
    if (file) formData.append("picture", file);

    await createPerson(formData);

    // clear input fields
    setForm({ military_serial: "", name: "", department: "", rank: "" });
    setFile(null);

    await load();
  };

  /**  삭제 핸들러 */
  const handleDelete = async (serial: string) => {
    if (!window.confirm(`정말 ${serial} 인원을 삭제할까요?`)) return;

    await deletePerson(serial);
    await load();
  };

  return (
    <div className="admin-root">
      <header className="top-bar">
        <div className="top-bar-left">
          <div className="top-title">ADMIN - PERSONNEL REGISTRY</div>
          <div className="top-subtitle">
            등록 인원 관리 · 병번 기준 조회 · 출입 로그 연동
          </div>
        </div>
        <div className="top-bar-right">
          <button className="btn-ghost" onClick={() => navigate("/main")}>
            BACK TO MAIN
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

      <main className="admin-main">
        {/* 등록 폼 */}
        <section className="admin-form-panel">
          <h2>신규 인원 등록</h2>
          <form className="admin-form" onSubmit={handleCreate}>
            <label>
              군번
              <input
                value={form.military_serial}
                onChange={(e) =>
                  setForm({ ...form, military_serial: e.target.value })
                }
              />
            </label>

            <label>
              이름
              <input
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
            </label>

            <label>
              부서
              <input
                value={form.department}
                onChange={(e) =>
                  setForm({ ...form, department: e.target.value })
                }
              />
            </label>

            <label>
              계급
              <input
                value={form.rank}
                onChange={(e) => setForm({ ...form, rank: e.target.value })}
              />
            </label>

            <label>
              얼굴 사진
              <input
                type="file"
                accept="image/*"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
            </label>

            <button className="btn-primary" type="submit">
              인원 등록
            </button>
          </form>
        </section>

        {/* 인원 테이블 */}
        <section className="admin-table-panel">
          <h2>등록 인원 목록</h2>
          <table className="admin-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>사진</th>
                <th>군번</th>
                <th>이름</th>
                <th>부서</th>
                <th>계급</th>
                <th>등록일시</th>
                <th>관리</th>
              </tr>
            </thead>

            <tbody>
              {people.map((p) => (
                <tr key={p.id}>
                  <td>{p.id}</td>

                  {/* 사진 표시 */}
                  <td>
  {p.picture ? (
    <img
      src={`data:image/jpeg;base64,${p.picture}`}
      alt="face"
      style={{
        width: "45px",
        height: "45px",
        borderRadius: "50%",
        objectFit: "cover",
      }}
    />
  ) : (
    "-"
  )}
</td>

                  <td>{p.military_serial}</td>
                  <td>{p.name}</td>
                  <td>{p.department}</td>
                  <td>{p.rank}</td>
                  <td>{new Date(p.created_at).toLocaleString()}</td>
                  <td>
                    <button
                      className="btn-danger"
                      onClick={() => handleDelete(p.military_serial)}
                    >
                      삭제
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </main>
    </div>
  );
}
