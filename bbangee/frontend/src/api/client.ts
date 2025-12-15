// src/api/client.ts
import axios from "axios";
export const API_BASE =import.meta.env.VITE_API_BASE_URL;
export const api = axios.create({
  baseURL: API_BASE,
});


