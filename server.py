#!/usr/bin/env python3
import asyncio, json, os, time, uuid
from aiohttp import web, ClientSession, ClientTimeout
from appcheck_manager import AppCheckTokenManager

HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8771"))
PROJECT = os.getenv("FIREBASE_PROJECT_ID", "to-do-speak-ai")
APP_ID = os.getenv("FIREBASE_APP_ID", "1:790398438370:ios:7fea4e3959c6f21ae607bb")
BUNDLE_ID = os.getenv("FIREBASE_BUNDLE_ID", "wabywab.To-Do-Speak-AI")
UPSTREAM = "https://firebasevertexai.googleapis.com"
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gemini-flash-lite-latest")
MODEL_MAP = {
    # Rolling aliases (verified 2026-07-28).
    "gemini-flash-lite": "gemini-flash-lite-latest",       # -> 3.5 Flash Lite
    "gemini-flash-lite-latest": "gemini-flash-lite-latest",
    "gemini-flash": "gemini-flash-latest",                 # -> 3.6 Flash
    "gemini-flash-latest": "gemini-flash-latest",
    # Fixed, independent model IDs. Never collapse these into latest aliases.
    "gemini-3.6-flash": "gemini-3.6-flash",
    "gemini-3.5-flash": "gemini-3.5-flash",
    "gemini-3.5-flash-lite": "gemini-3.5-flash-lite",
    "gemini-3-flash-preview": "gemini-3-flash-preview",
    "gemini-2.5-flash": "gemini-2.5-flash",
    "gemini-2.5-flash-lite": "gemini-2.5-flash-lite",
}
SIG_CACHE = {}
CALL_NAME_CACHE = {}
DYNAMIC_MODELS = set(filter(None, (x.strip() for x in os.getenv("EXTRA_MODELS", "").split(","))))

def configured_api_key():
    return os.getenv("FIREBASE_GEMINI_API_KEY","") or os.getenv("FIREBASE_API_KEY","")

APP_CHECK = AppCheckTokenManager(PROJECT, APP_ID, configured_api_key)

def secret(req, header, *envs):
    value = req.headers.get(header, "")
    if value: return value
    for name in envs:
        value = os.getenv(name, "")
        if value: return value
    return ""

def require_local_auth(req):
    expected = os.getenv("PROXY_API_KEY", "")
    if not expected: return
    supplied = req.headers.get("Authorization", "")
    if supplied.startswith("Bearer "): supplied = supplied[7:]
    if supplied != expected: raise web.HTTPUnauthorized(text=json.dumps({"error":{"message":"Invalid proxy API key"}}), content_type="application/json")

async def upstream_headers(req, force_refresh=False):
    key = secret(req, "x-goog-api-key", "FIREBASE_GEMINI_API_KEY", "FIREBASE_API_KEY")
    if not key:
        raise web.HTTPServiceUnavailable(text=json.dumps({"error":{"message":"Missing FIREBASE_GEMINI_API_KEY; alternatively forward x-goog-api-key"}}), content_type="application/json")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "x-goog-api-key": key,
        "x-goog-api-client": "gl-python/3 firebase-gemini-proxy/2.1",
        "X-Firebase-AppId": os.getenv("FIREBASE_APP_ID", APP_ID),
        "x-ios-bundle-identifier": os.getenv("FIREBASE_BUNDLE_ID", BUNDLE_ID),
    }
    token = req.headers.get("X-Firebase-AppCheck", "")
    if not token:
        try: token = await APP_CHECK.get(force=force_refresh)
        except RuntimeError as e:
            raise web.HTTPServiceUnavailable(text=json.dumps({"error":{"message":str(e)}}), content_type="application/json")
    headers["X-Firebase-AppCheck"] = token
    return headers

def part_text(content):
    if isinstance(content, str): return content
    if not isinstance(content, list): return str(content or "")
    out = []
    for p in content:
        if p.get("type") == "text": out.append(p.get("text", ""))
        elif p.get("type") == "image_url":
            url = p.get("image_url", {}).get("url", "")
            if url.startswith("data:") and ";base64," in url:
                head, data = url.split(",", 1)
                out.append({"inlineData":{"mimeType":head[5:].split(";")[0],"data":data}})
            elif url: out.append({"fileData":{"mimeType":"image/*","fileUri":url}})
    if all(isinstance(x, str) for x in out): return "\n".join(out)
    parts = []
    for x in out: parts.append({"text":x} if isinstance(x, str) else x)
    return parts

def openai_to_gemini(data):
    system, contents = [], []
    for msg in data.get("messages", []):
        role = msg.get("role", "user")
        if role in ("system", "developer"):
            system.append(part_text(msg.get("content", "")))
            continue
        if role == "tool":
            tool_id = msg.get("tool_call_id", "")
            name = msg.get("name") or CALL_NAME_CACHE.get(tool_id) or "tool"
            raw = msg.get("content", "")
            try: result = json.loads(raw) if isinstance(raw, str) else raw
            except Exception: result = {"result": raw}
            contents.append({"role":"user","parts":[{"functionResponse":{"name":name,"response":result if isinstance(result,dict) else {"result":result}}}]})
            continue
        parts = []
        text = part_text(msg.get("content", ""))
        if isinstance(text, list): parts.extend(text)
        elif text:
            text_part = {"text": text}
            if msg.get("thought_signature"): text_part["thoughtSignature"] = msg["thought_signature"]
            parts.append(text_part)
        for tc in msg.get("tool_calls", []) or []:
            fn = tc.get("function", {})
            try: args = json.loads(fn.get("arguments", "{}"))
            except Exception: args = {"raw":fn.get("arguments", "")}
            p = {"functionCall":{"name":fn.get("name", "tool"),"args":args}}
            sig = (msg.get("thought_signatures") or {}).get(tc.get("id")) if isinstance(msg.get("thought_signatures"),dict) else None
            sig = sig or SIG_CACHE.get(tc.get("id"), (None,0))[0]
            if sig: p["thoughtSignature"] = sig
            parts.append(p)
        contents.append({"role":"model" if role=="assistant" else "user","parts":parts or [{"text":""}]})
    body = {"contents": contents}
    if system: body["systemInstruction"] = {"parts":[{"text":"\n\n".join(str(x) for x in system)}]}
    cfg = {}
    for src,dst in (("temperature","temperature"),("top_p","topP"),("top_k","topK"),("max_tokens","maxOutputTokens"),("stop","stopSequences")):
        if src in data and data[src] is not None: cfg[dst] = data[src]
    if "thinking_budget" in data or "include_thoughts" in data:
        cfg["thinkingConfig"] = {"includeThoughts": bool(data.get("include_thoughts", False))}
        if "thinking_budget" in data: cfg["thinkingConfig"]["thinkingBudget"] = int(data["thinking_budget"])
    rf = data.get("response_format", {}) or {}
    if rf.get("type") in ("json_object", "json_schema"):
        cfg["responseMimeType"] = "application/json"
        schema = rf.get("json_schema", {}).get("schema")
        if schema: cfg["responseSchema"] = schema
    if cfg: body["generationConfig"] = cfg
    tools = []
    for t in data.get("tools", []) or []:
        if t.get("type") == "function":
            f=t.get("function",{}); tools.append({"name":f.get("name"),"description":f.get("description", ""),"parameters":f.get("parameters",{"type":"object"})})
    if tools: body["tools"] = [{"functionDeclarations":tools}]
    return body

def gemini_to_openai(raw, requested_model):
    cand = (raw.get("candidates") or [{}])[0]
    parts = cand.get("content",{}).get("parts",[]) or []
    texts, calls, sigs = [], [], {}
    for i,p in enumerate(parts):
        if "text" in p: texts.append(p["text"])
        if "functionCall" in p:
            fc=p["functionCall"]; cid="call_"+uuid.uuid4().hex[:24]
            call_name=fc.get("name","tool")
            calls.append({"id":cid,"type":"function","function":{"name":call_name,"arguments":json.dumps(fc.get("args",{}),ensure_ascii=False,separators=(",",":"))}})
            CALL_NAME_CACHE[cid]=call_name
            if p.get("thoughtSignature"):
                sigs[cid]=p["thoughtSignature"]; SIG_CACHE[cid]=(p["thoughtSignature"],time.time())
    message={"role":"assistant","content":"".join(texts) if texts else None}
    text_sig = next((p.get("thoughtSignature") for p in parts if p.get("text") is not None and p.get("thoughtSignature")), None)
    if text_sig: message["thought_signature"] = text_sig
    if calls: message["tool_calls"]=calls
    if sigs: message["thought_signatures"]=sigs
    usage=raw.get("usageMetadata",{})
    return {
        "id":"chatcmpl-"+raw.get("responseId",uuid.uuid4().hex),
        "object":"chat.completion","created":int(time.time()),
        "model":raw.get("modelVersion",requested_model),
        "choices":[{"index":0,"message":message,"finish_reason":"tool_calls" if calls else "stop"}],
        "usage":{"prompt_tokens":usage.get("promptTokenCount",0),"completion_tokens":usage.get("candidatesTokenCount",0),"total_tokens":usage.get("totalTokenCount",0)}
    }

async def call_upstream(req, model, body):
    url=f"{UPSTREAM}/v1beta/projects/{PROJECT}/models/{model}:generateContent"
    async with ClientSession(timeout=ClientTimeout(total=180)) as s:
        for attempt in range(2):
            headers=await upstream_headers(req,force_refresh=attempt>0)
            async with s.post(url,headers=headers,json=body) as r:
                text=await r.text()
                try: payload=json.loads(text)
                except Exception: payload={"error":{"message":text or f"Upstream HTTP {r.status}"}}
                appcheck_error = r.status == 401 and "App Check" in json.dumps(payload,ensure_ascii=False)
                if not appcheck_error or attempt: return r.status,payload
    return 500,{"error":{"message":"Unexpected retry state"}}

async def chat(req):
    require_local_auth(req)
    data=await req.json()
    requested=data.get("model",DEFAULT_MODEL)
    model=MODEL_MAP.get(requested,requested)
    status,raw=await call_upstream(req,model,openai_to_gemini(data))
    if status >= 400: return web.json_response(raw,status=status)
    result=gemini_to_openai(raw,requested)
    DYNAMIC_MODELS.add(requested)
    if raw.get("modelVersion"): DYNAMIC_MODELS.add(raw["modelVersion"])
    if not data.get("stream"): return web.json_response(result)
    choice=result["choices"][0]; delta=dict(choice["message"])
    if delta.get("tool_calls"):
        delta["tool_calls"]=[{"index":i,**tc} for i,tc in enumerate(delta["tool_calls"])]
    response=web.StreamResponse(status=200,headers={"Content-Type":"text/event-stream","Cache-Control":"no-cache","Connection":"keep-alive"})
    await response.prepare(req)
    chunk={"id":result["id"],"object":"chat.completion.chunk","created":result["created"],"model":result["model"],"choices":[{"index":0,"delta":delta,"finish_reason":None}]}
    await response.write(("data: "+json.dumps(chunk,ensure_ascii=False)+"\n\n").encode())
    end={"id":result["id"],"object":"chat.completion.chunk","created":result["created"],"model":result["model"],"choices":[{"index":0,"delta":{},"finish_reason":choice["finish_reason"]}]}
    await response.write(("data: "+json.dumps(end)+"\n\ndata: [DONE]\n\n").encode()); await response.write_eof()
    return response

async def models(req):
    require_local_auth(req)
    ids=sorted(set(MODEL_MAP)|DYNAMIC_MODELS)
    return web.json_response({"object":"list","data":[{"id":x,"object":"model","created":0,"owned_by":"firebase","dynamic":x in DYNAMIC_MODELS} for x in ids]})

async def model_register(req):
    require_local_auth(req)
    data=await req.json()
    incoming=data.get("models",[]) if isinstance(data,dict) else []
    if isinstance(incoming,str): incoming=[incoming]
    added=[]
    for model in incoming:
        model=str(model).strip()
        if model and len(model)<=128:
            DYNAMIC_MODELS.add(model); added.append(model)
    return web.json_response({"ok":True,"added":added,"models":sorted(set(MODEL_MAP)|DYNAMIC_MODELS),"persist_hint":"Set HF Space variable EXTRA_MODELS to a comma-separated list to survive restarts."})

async def raw_proxy(req):
    require_local_auth(req)
    tail=req.match_info["tail"]
    url=f"{UPSTREAM}/{tail}"
    if req.query_string: url += "?"+req.query_string
    body=await req.read()
    async with ClientSession(timeout=ClientTimeout(total=180)) as s:
        for attempt in range(2):
            headers=await upstream_headers(req,force_refresh=attempt>0)
            async with s.request(req.method,url,headers=headers,data=body) as r:
                raw=await r.read()
                if r.status == 401 and b"App Check" in raw and not attempt: continue
                return web.Response(status=r.status,body=raw,content_type=r.content_type)

async def health(req):
    return web.json_response({"status":"ok","version":"2.1.0","project":PROJECT,"default_model":DEFAULT_MODEL,"credentials_configured":bool(configured_api_key()),"app_check":APP_CHECK.status()})

async def credential_status(req):
    require_local_auth(req)
    return web.json_response(APP_CHECK.status())

async def credential_install(req):
    require_local_auth(req)
    data=await req.json()
    try: exp=APP_CHECK.install(data.get("token",""))
    except ValueError as e: return web.json_response({"error":{"message":str(e)}},status=400)
    return web.json_response({"ok":True,"expires_at":exp or None,"source":"token_file"})

async def credential_refresh(req):
    require_local_auth(req)
    try: await APP_CHECK.get(force=True)
    except RuntimeError as e: return web.json_response({"error":{"message":str(e)}},status=503)
    return web.json_response({"ok":True,**APP_CHECK.status()})

app=web.Application(client_max_size=64*1024*1024)
app.add_routes([web.get("/health",health),web.get("/v1/models",models),web.post("/admin/models",model_register),web.post("/v1/chat/completions",chat),web.get("/admin/appcheck",credential_status),web.put("/admin/appcheck",credential_install),web.post("/admin/appcheck/refresh",credential_refresh),web.route("*","/firebase/{tail:.*}",raw_proxy)])
if __name__ == "__main__": web.run_app(app,host=HOST,port=PORT,print=None)
