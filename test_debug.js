/* Quantumult X Debug Script */
console.log("[DEBUG] Response body handler triggered");
console.log("[DEBUG] Request URL:", $request.url);
console.log("[DEBUG] Request method:", $request.method);
console.log("[DEBUG] Response status:", $response.status);
console.log("[DEBUG] Response headers:", JSON.stringify($response.headers));
console.log("[DEBUG] Response body length:", $response.body ? $response.body.length : "empty");

// Check for token in response
if ($response.body) {
    try {
        const payload = JSON.parse($response.body);
        if (payload.token) console.log("[DEBUG] Found token in response:", payload.token.slice(0, 20) + "...");
        else console.log("[DEBUG] No token found in response");
    } catch (e) {
        console.log("[DEBUG] Error parsing response:", e.message);
    }
}

$done($response);
