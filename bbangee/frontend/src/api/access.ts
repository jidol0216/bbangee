// src/api/access.ts
import { api } from "./client";

export type AccessLog = {
  id: number;
  military_serial: string;
  in_time: string;
  out_time?: string | null;
};

// 전체 로그 불러오기
export async function fetchLogs(): Promise<AccessLog[]> {
  const res = await api.get<AccessLog[]>("/access/logs");
  return res.data;
}


// 특정 군번의 로그 가져오기
export async function fetchLogsBySerial(serial: string): Promise<AccessLog[]> {
    const res = await api.get(`/access/logs/${serial}`);
    return res.data;
}
//  군번으로 ENTRY 기록 생성
export async function recordIn(serial: string) {
  return api.post(`/access/${serial}/entry`);
}

//  군번으로 EXIT 기록 업데이트
export async function recordOut(serial: string) {
  return api.post(`/access/${serial}/exit`);
}
