/* Quantumult X: Firebase App Check -> HF 自动同步 */
const HF_PROXY_URL = "https://w902287-firebase-gemini-proxy.hf.space/admin/appcheck";
const HF_SECRET_URL = "https://huggingface.co/api/spaces/w902287/firebase-gemini-proxy/secrets";
const PREF_KEY = "firebase_gemini_hf_token";
const INLINE_TOKEN = "__PASTE_YOUR_HF_TOKEN_HERE__";
const HF_TOKEN = ($prefs.valueForKey(PREF_KEY) || INLINE_TOKEN || "").trim();
const originalBody = $response.body || "";
const done = () => $done({ body: originalBody });
const request = (url, body, method = "PUT") => $task.fetch({
  url, method,
  headers: { "Authorization": "Bearer " + HF_TOKEN, "Content-Type": "application/json" },
  body: JSON.stringify(body)
});

let payload;
try { payload = JSON.parse(originalBody); }
catch (e) { console.log("[AppCheck Sync] 响应不是 JSON"); done(); }

if (payload) {
  const token = payload.token || payload.attestationToken || "";
  if (!token) {
    console.log("[AppCheck Sync] 响应中没有 token"); done();
  } else if (!HF_TOKEN.startsWith("hf_")) {
    $notify("Firebase App Check", "尚未配置 HF Token", "请运行一次 set_hf_token_qx.js"); done();
  } else {
    // First hot-update the running container; then persist to the Space Secret.
    request(HF_PROXY_URL, { token }).then(hot => {
      if (hot.statusCode < 200 || hot.statusCode >= 300) throw new Error("Proxy HTTP " + hot.statusCode);
      return request(HF_SECRET_URL, { key: "FIREBASE_APP_CHECK", value: token }, "POST");
    }).then(secret => {
      if (secret.statusCode < 200 || secret.statusCode >= 300) throw new Error("HF Secret HTTP " + secret.statusCode);
      console.log("[AppCheck Sync] JWT hot-updated and persisted"); done();
    }).catch(err => {
      console.log("[AppCheck Sync] " + String(err));
      $notify("Firebase App Check", "同步失败", String(err)); done();
    });
  }
}
