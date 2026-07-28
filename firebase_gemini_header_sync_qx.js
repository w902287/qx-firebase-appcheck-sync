/* Firebase Gemini Request Header App Check Sync */
const HF_URL = "https://w902287-firebase-gemini-proxy.hf.space/admin/appcheck";
const PREF_KEY = "firebase_gemini_hf_token";
const INLINE_TOKEN = "hf_eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCJ9.eyJhcHBJZCI6IjE6NzkwMzk4NDM4MzcwOmlvczo3ZmVhNGUzOTU5YzZmMjFhZTYwN2JiIiwiZXhwIjoxNzg1NzQ3NzE4LCJmaWQiOiJlTzNZYUpYdVNFaEpxVUlaYll3cTdKIiwicHJvamVjdE51bWJlciI6NzkwMzk4NDM4MzcwfQ.AB2LPV8wRAIgSjVb_sTBdjzB39_Xt-l4YMZ8JZn0OalJTeereaROJnMCIBUdSYTEBaLgNBaTqRBqv7wxvjX_HDm-P1ZKUdX-nQfT";
const HF_TOKEN = ($prefs.valueForKey(PREF_KEY) || INLINE_TOKEN || "").trim();

const done = () => $done($request);

if (!HF_TOKEN.startsWith("hf_")) {
    $notify("Firebase App Check", "HF Token 未配置", "请先运行一次性 HF Token 设置任务");
    return done();
}

const token = $request.headers['X-Firebase-AppCheck'];
if (!token) {
    return done();
}

const sync = () => $task.fetch({
    url: HF_URL,
    method: "PUT",
    headers: {
        "Authorization": `Bearer ${HF_TOKEN}`,
        "Content-Type": "application/json"
    },
    body: JSON.stringify({ token })
});

sync().then(response => {
    if (response.statusCode < 200 || response.statusCode >= 300) {
        $notify("Firebase App Check", "同步失败", `HTTP ${response.statusCode}`);
    } else {
        $notify("Firebase App Check", "同步成功", "新 Token 已上传到 HF Proxy");
    }
    done();
}).catch(error => {
    $notify("Firebase App Check", "同步失败", `${error.name}: ${error.message}`);
    done();
});
