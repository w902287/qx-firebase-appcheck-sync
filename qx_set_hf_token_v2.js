/* Quantumult X 一次性 HF Token 设置 v2；仅用于 event-interaction */
const source = (typeof $environment !== "undefined" && $environment.sourcePath) ? $environment.sourcePath : "";
const fragment = source.indexOf("#") >= 0 ? source.substring(source.indexOf("#") + 1) : "";
let token = "";
try { token = decodeURIComponent(fragment).trim(); } catch (_) { token = fragment.trim(); }
if (token.startsWith("hf_")) {
  const ok = $prefs.setValueForKey(token, "firebase_gemini_hf_token");
  $notify("Firebase App Check", ok ? "HF Token 已保存" : "保存失败", ok ? "现在删除此一次性任务" : "无法写入 $prefs");
} else {
  $notify("Firebase App Check", "设置失败", "没有从任务 URL 片段读取到 HF Token");
}
$done();
