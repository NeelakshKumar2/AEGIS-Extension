import json, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import requests
from requests.auth import HTTPBasicAuth
from requests.structures import CaseInsensitiveDict

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, code=200, body=b"{}", headers=None):
        self.send_response(code)
        for k, v in (headers or {}).items(): self.send_header(k, v)
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        if self.path.startswith("/redirect"): return self._send(302, b"", {"Location": "/json"})
        if self.path.startswith("/cookie"): return self._send(200, b"{}", {"Set-Cookie": "a=b; Path=/"})
        if self.path.startswith("/auth"):
            ok = "Authorization" in self.headers
            return self._send(200 if ok else 401, json.dumps({"auth": ok}).encode())
        if self.path.startswith("/link"): return self._send(200, b"x", {"Link": '<http://x/2>; rel="next"'})
        self._send(200, json.dumps({"path": self.path, "ua": self.headers.get("User-Agent")}).encode(),
                   {"Content-Type": "application/json"})
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0)); data = self.rfile.read(n)
        self._send(200, json.dumps({"len": len(data)}).encode(), {"Content-Type": "application/json"})
    do_PUT = do_POST

srv = HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{srv.server_port}"
r = requests.get(base + "/json", params={"a": 1, "b": [1, 2]}, headers={"X-T": "1"})
r.json(); r.raise_for_status(); r.text; r.content; r.encoding; r.apparent_encoding; r.elapsed; r.ok
requests.post(base + "/p", json={"k": "v"}).json()
requests.post(base + "/p", data={"k": "v"}, files={"f": ("a.txt", b"abc")})
requests.put(base + "/p", data=b"zz")
requests.head(base + "/json"); requests.options(base + "/json"); requests.delete(base + "/json")
s = requests.Session()
s.headers.update({"X-S": "1"})
s.get(base + "/cookie"); s.cookies.get_dict(); s.get(base + "/redirect").history
s.get(base + "/auth", auth=HTTPBasicAuth("u", "p")); s.auth = ("u", "p"); s.get(base + "/auth")
r = s.get(base + "/json", stream=True); list(r.iter_content(8)); r.close()
r = s.get(base + "/json"); list(r.iter_lines())
s.get(base + "/link").links
s.mount("http://", requests.adapters.HTTPAdapter(max_retries=1, pool_connections=2))
s.hooks["response"].append(lambda resp, **kw: resp)
s.get(base + "/json")
req = requests.Request("GET", base + "/json", params={"q": "z"}); p = s.prepare_request(req)
p.copy(); s.send(p); p.url; p.headers
try: requests.get("http://127.0.0.1:1/", timeout=0.5)
except requests.exceptions.RequestException: pass
try: requests.get(base + "/json", timeout=(2, 2)); requests.get("not a url")
except requests.exceptions.RequestException: pass
d = CaseInsensitiveDict({"A": 1}); d["a"]; d.copy(); list(d.items())
u = requests.utils
u.get_encoding_from_headers({"content-type": "text/html; charset=utf-8"}); u.guess_json_utf(b"{}")
u.requote_uri("http://a/b c"); u.parse_header_links('<a>; rel="x"'); u.dict_from_cookiejar(s.cookies)
u.get_environ_proxies("http://a.com", no_proxy=None); u.to_key_val_list({"a": 1}); u.default_headers()
requests.codes.ok; requests.codes["not_found"]
requests.utils.super_len(b"abc"); requests.utils.unquote_unreserved("a%20b"); u.select_proxy("http://a", {})
s.close()
