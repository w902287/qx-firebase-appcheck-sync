/* Quantumult X 一次性设置 HF Token
 * Token 从任务脚本 URL 的 # 片段读取，不会发送给 GitHub。
 */
let source = ($environment && $environment.sourcePath) || "";
let fragment = source.includes("#") ? source.split("#").slice(1).join("#") : "";
let token = "";
try { token = decodeURIComponent(fragment).trim(); } catch (e) { token = fragment.trim(); }
if (!token.startsWith("hf_")) {
  $notify("Firebase App Check", "设置失败", "任务 URL 中没有有效的 HF Token");
} else {
  const ok = $prefs.setValueForKey(token, "firebase_gemini_hf_token");
  $notify("Firebase App Check", ok ? "HF Token 已保存" : "保存失败", ok ? "请删除这条一次性任务并启用自动同步模块" : "请检查 Quantumult X 权限");
}
$done();
