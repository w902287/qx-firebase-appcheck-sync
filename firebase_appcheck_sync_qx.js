/* Quantumult X: Firebase App Check -> HF 自动同步 */
const HF_URL = "https://w902287-firebase-gemini-proxy.hf.space/admin/appcheck";
const HF_TOKEN = "__PASTE_YOUR_HF_TOKEN_HERE__";
const originalBody = $response.body || "";

function done() { $done({ body: originalBody }); }

let payload;
try {
  payload = JSON.parse(originalBody);
} catch (e) {
  console.log("[AppCheck Sync] 响应不是 JSON: " + e);
  done();
}

if (payload) {
  const token = payload.token || payload.attestationToken || "";
  if (!token) {
    console.log("[AppCheck Sync] 响应中没有 token");
    done();
  } else if (!HF_TOKEN.startsWith("hf_")) {
    console.log("[AppCheck Sync] 请先在脚本中填写 HF_TOKEN");
    $notify("Firebase App Check", "尚未配置 HF Token", "请编辑同步脚本中的 HF_TOKEN");
    done();
  } else {
    $task.fetch({
      url: HF_URL,
      method: "PUT",
      headers: {
        "Authorization": "Bearer " + HF_TOKEN,
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ token })
    }).then(resp => {
      const ok = resp.statusCode >= 200 && resp.statusCode < 300;
      console.log("[AppCheck Sync] HF HTTP " + resp.statusCode);
      if (ok) $notify("Firebase App Check", "同步成功", "新的 JWT 已上传到 Gemini Proxy");
      else $notify("Firebase App Check", "同步失败", "HF HTTP " + resp.statusCode);
      done();
    }, err => {
      console.log("[AppCheck Sync] 上传失败: " + JSON.stringify(err));
      $notify("Firebase App Check", "同步失败", String(err));
      done();
    });
  }
}
