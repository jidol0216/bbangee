// bbangee/frontend/src/api/voice.ts
import { API_BASE } from "./client";


export async function speakClassify(isAlly: boolean) {
  await fetch(`${API_BASE}/voice/classify`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ is_ally: isAlly }),
  });
}
