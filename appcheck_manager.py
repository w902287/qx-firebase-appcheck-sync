#!/usr/bin/env python3
import asyncio, base64, json, os, shlex, time
from aiohttp import ClientSession, ClientTimeout

class AppCheckTokenManager:
    def __init__(self, project, app_id, api_key_getter):
        self.project=project; self.app_id=app_id; self.api_key_getter=api_key_getter
        self.token=""; self.exp=0; self.source="none"; self.lock=asyncio.Lock()
        self.base=os.path.dirname(os.path.abspath(__file__))
        self.token_file=os.getenv("FIREBASE_APP_CHECK_TOKEN_FILE",os.path.join(self.base,"appcheck.token"))
        self.cache_file=os.path.join(self.base,".appcheck-cache.json")

    @staticmethod
    def jwt_exp(token):
        try:
            p=token.split('.')[1]; p += '='*((4-len(p)%4)%4)
            return int(json.loads(base64.urlsafe_b64decode(p))["exp"])
        except Exception: return 0

    def _accept(self, token, source):
        token=(token or "").strip()
        if not token: return False
        self.token=token; self.exp=self.jwt_exp(token); self.source=source
        return True

    def _read_file(self, path, source):
        try:
            raw=open(path).read().strip()
            if raw.startswith('{'): raw=json.loads(raw).get("token","")
            return self._accept(raw,source)
        except Exception: return False

    def _load_existing(self):
        # Token file is reread every request, so an interceptor can rotate it live.
        if os.path.exists(self.token_file):
            try:
                mtime=os.path.getmtime(self.token_file)
                if mtime >= getattr(self,"file_mtime",0):
                    self.file_mtime=mtime; self._read_file(self.token_file,"token_file")
            except Exception: pass
        env=os.getenv("FIREBASE_APP_CHECK","")
        if env and (not self.token or self.source=="env"): self._accept(env,"env")
        if not self.token: self._read_file(self.cache_file,"cache")

    def valid(self, margin=300):
        return bool(self.token) and (self.exp==0 or self.exp > time.time()+margin)

    async def _exchange_debug(self):
        debug=os.getenv("FIREBASE_APP_CHECK_DEBUG_TOKEN","").strip()
        key=self.api_key_getter()
        if not debug or not key: return False
        url=f"https://firebaseappcheck.googleapis.com/v1/projects/{self.project}/apps/{self.app_id}:exchangeDebugToken?key={key}"
        async with ClientSession(timeout=ClientTimeout(total=30)) as s:
            async with s.post(url,json={"debug_token":debug,"limited_use":False}) as r:
                data=await r.json(content_type=None)
                if r.status >= 400: raise RuntimeError(data.get("error",{}).get("message",f"App Check exchange HTTP {r.status}"))
        token=data.get("token","")
        if not self._accept(token,"debug_exchange"): raise RuntimeError("App Check exchange returned no token")
        self._save_cache(); return True

    async def _run_command(self):
        cmd=os.getenv("FIREBASE_APP_CHECK_REFRESH_COMMAND","").strip()
        if not cmd: return False
        proc=await asyncio.create_subprocess_shell(cmd,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        out,err=await asyncio.wait_for(proc.communicate(),timeout=60)
        if proc.returncode: raise RuntimeError("App Check refresh command failed")
        raw=out.decode().strip()
        if raw.startswith('{'):
            data=json.loads(raw); raw=data.get("token","")
            if not raw and self._read_file(self.token_file,"token_file"): return True
        if not self._accept(raw,"refresh_command"): raise RuntimeError("Refresh command returned no token")
        self._save_cache(); return True

    def _save_cache(self):
        tmp=self.cache_file+".tmp"
        with open(tmp,"w") as f: json.dump({"token":self.token},f)
        os.chmod(tmp,0o600); os.replace(tmp,self.cache_file)

    async def get(self, force=False):
        async with self.lock:
            self._load_existing()
            if not force and self.valid(): return self.token
            errors=[]
            for fn in (self._exchange_debug,self._run_command):
                try:
                    if await fn(): return self.token
                except Exception as e: errors.append(str(e))
            self._load_existing()
            if self.valid(0): return self.token
            if self.token: raise RuntimeError("App Check token expired and no refresh method succeeded")
            raise RuntimeError("No App Check token; configure debug exchange, token file, or refresh command")

    def install(self, token):
        if not self._accept(token,"token_file"): raise ValueError("Empty token")
        tmp=self.token_file+".tmp"
        with open(tmp,"w") as f: f.write(self.token+"\n")
        os.chmod(tmp,0o600); os.replace(tmp,self.token_file)
        self.file_mtime=os.path.getmtime(self.token_file)
        return self.exp

    def status(self):
        self._load_existing()
        return {"source":self.source,"configured":bool(self.token),"valid":self.valid(0),"expires_at":self.exp or None,"seconds_remaining":max(0,int(self.exp-time.time())) if self.exp else None,"auto_refresh":bool(os.getenv("FIREBASE_APP_CHECK_DEBUG_TOKEN") or os.getenv("FIREBASE_APP_CHECK_REFRESH_COMMAND"))}
