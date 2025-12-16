// src/api/client.ts
import axios from "axios";

// API URL: 항상 localhost 사용 (같은 PC에서만 접속)
export const API_BASE = "http://localhost:8000";
export const api = axios.create({
  baseURL: API_BASE,
});


