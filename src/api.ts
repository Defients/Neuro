export async function api<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(
    "/api" + path,
    body === undefined
      ? undefined
      : {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-NSS-Local": "1" },
          body: JSON.stringify(body),
        },
  );
  const text = await r.text();
  let data: any = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }
  if (!r.ok || data === null)
    throw new Error(
      data && typeof data.detail === "object" && data.detail !== null
        ? `${data.detail.code}: ${data.detail.explanation} ${data.detail.action}`
        : data?.detail ||
            `Request to /api${path} failed (${r.status}, ${
              text ? "non-JSON" : "empty"
            } response). Is the backend running?`,
    );
  return data;
}
