/* Quantumult X 一次性设置 HF Token
 * 使用方式：临时加入 task_local，执行一次后删除任务。
 */
const token = "__PASTE_YOUR_HF_TOKEN_HERE__";
if (!token.startsWith("hf_")) {
  $notify("Firebase App Check", "设置失败", "请先把脚本中的占位符替换为 HF Token");
} else {
  const ok = $prefs.setValueForKey(token, "firebase_gemini_hf_token");
  $notify("Firebase App Check", ok ? "HF Token 已保存" : "保存失败", ok ? "现在可以启用自动同步重写" : "请检查 Quantumult X 权限");
}
$done();
