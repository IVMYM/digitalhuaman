const TOKEN_KEY = "dh_token";
const USER_KEY = "dh_username";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || "";
}

export function getUsername() {
  return localStorage.getItem(USER_KEY) || "";
}

export function setSession(token, username) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, username || "");
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let body = options.body;
  if (options.json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(options.json);
  }
  let response;
  try {
    response = await fetch(path, { method: options.method || "GET", headers, body });
  } catch {
    throw new Error("网络不通，后端可能没启动");
  }
  if (response.status === 401 && !path.startsWith("/api/auth/login")) {
    clearSession();
    if (location.pathname !== "/login") location.assign("/login");
    throw new Error("登录已失效");
  }
  const text = await response.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = { detail: text.slice(0, 300) };
    }
  }
  if (!response.ok) {
    let message = data?.detail || data?.error?.message || `请求失败（${response.status}）`;
    if (Array.isArray(message)) {
      message = message.map((item) => item.msg || JSON.stringify(item)).join("；");
    }
    throw new Error(typeof message === "string" ? message : "请求失败");
  }
  return data;
}

export function upload(path, file) {
  const body = new FormData();
  body.append("file", file);
  return api(path, { method: "POST", body });
}

export async function apiBlob(path) {
  const headers = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(path, { headers });
  if (!response.ok) throw new Error("文件读取失败");
  return response.blob();
}
