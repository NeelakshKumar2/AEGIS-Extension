from werkzeug.wrappers import Request, Response
from werkzeug.routing import Map, Rule
from werkzeug.test import Client, EnvironBuilder
from werkzeug.exceptions import HTTPException, NotFound
from werkzeug.datastructures import MultiDict, Headers, CombinedMultiDict
from werkzeug import utils, urls, security, http
m = Map([Rule("/", endpoint="i"), Rule("/u/<int:n>", endpoint="u"), Rule("/p/<path:p>", endpoint="p")])
@Request.application
def app(req):
    ad = m.bind_to_environ(req.environ)
    try:
        ep, args = ad.match()
    except HTTPException as e:
        return e
    return Response(f"{ep}{args}{req.args.get('a')}{req.form}{req.cookies}", mimetype="text/plain")
c = Client(app)
for p in ("/", "/u/3", "/p/a/b", "/zz", "/?a=1&a=2"):
    c.get(p)
c.post("/", data={"a": "1"}); c.post("/", json={"a": 1}); c.get("/", headers={"Cookie": "a=b"})
Headers([("A", "1")]).get("a"); MultiDict({"a": [1, 2]}).getlist("a")
security.generate_password_hash("x"); security.check_password_hash(security.generate_password_hash("x"), "x")
utils.secure_filename("a b/../c.txt"); utils.escape("<"); http.parse_options_header("a; b=c"); http.parse_date("Wed, 21 Oct 2015 07:28:00 GMT")
http.dump_cookie("a", "b"); http.parse_cookie("a=b"); urls.url_parse("http://a/b?c=1") if hasattr(urls, "url_parse") else None
EnvironBuilder(path="/x", method="POST", data={"a": "1"}).get_environ()
