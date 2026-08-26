export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export const WS_BASE =
  process.env.NEXT_PUBLIC_WS_BASE_URL ?? "ws://localhost:8000";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** FastAPI 는 에러를 {"detail": "..."} JSON 으로 내려준다 — 파싱 실패 시에만 원본 텍스트로 폴백. */
async function extractErrorMessage(res: Response): Promise<string> {
  const raw = await res.text();
  if (!raw) return res.statusText;
  try {
    const parsed = JSON.parse(raw) as { detail?: unknown };
    if (typeof parsed.detail === "string") return parsed.detail;
  } catch {
    // JSON 이 아니면 원본 텍스트를 그대로 사용
  }
  return raw;
}

export async function fetcher<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) {
    throw new ApiError(await extractErrorMessage(res), res.status);
  }
  return res.json() as Promise<T>;
}

export async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new ApiError(await extractErrorMessage(res), res.status);
  }
  return res.json() as Promise<T>;
}

export async function del(path: string): Promise<void> {
  const res = await fetch(`${API_BASE}${path}`, { method: "DELETE" });
  if (!res.ok) {
    throw new ApiError(await extractErrorMessage(res), res.status);
  }
}
