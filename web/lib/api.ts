export const API = process.env.NEXT_PUBLIC_PA_ENGINE_URL || "/engine";

export class ApiError extends Error {
  status: number;
  code?: string;

  constructor(message: string, status = 0, code?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

export function isNotFound(err: unknown): boolean {
  if (err instanceof ApiError) return err.status === 404;
  if (err && typeof err === "object" && "status" in err && (err as { status?: number }).status === 404) {
    return true;
  }
  if (err instanceof Error) {
    return /No request with that id|No policy with that id|Request failed \(404\)/i.test(err.message);
  }
  return false;
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  let response: Response;
  try {
    response = await fetch(`${API}${path}`, { ...init, headers });
  } catch {
    throw new ApiError("The prior authorization engine is not reachable. Start it, then retry.");
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new ApiError(
      data?.error?.message || `Request failed (${response.status})`,
      response.status,
      data?.error?.code,
    );
  }
  return data as T;
}

export function fileUrl(path: string) {
  return `${API}${path}`;
}
