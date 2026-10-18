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
  const data = await r.json();
  if (!r.ok)
    throw new Error(
      typeof data.detail === "object"
        ? `${data.detail.code}: ${data.detail.explanation} ${data.detail.action}`
        : data.detail || "Request failed",
    );
  return data;
}
