import flask
from flask import Flask, request, jsonify, render_template_string, redirect, url_for, abort, session, g, Blueprint, make_response
app = Flask(__name__); app.secret_key = "x"
bp = Blueprint("bp", __name__, url_prefix="/bp")
@bp.route("/hi/<name>")
def hi(name): return f"hi {name}"
app.register_blueprint(bp)
@app.before_request
def br(): g.v = 1
@app.after_request
def ar(resp): resp.headers["X"] = "1"; return resp
@app.route("/")
def index(): session["a"] = 1; return render_template_string("<p>{{ v }}</p>", v=request.args.get("v", "x"))
@app.route("/json", methods=["GET", "POST"])
def js(): return jsonify(ok=True, data=request.get_json(silent=True))
@app.route("/r")
def r(): return redirect(url_for("index"))
@app.route("/e")
def e(): abort(404)
@app.errorhandler(404)
def nf(err): return make_response("nf", 404)
@app.route("/u/<int:i>")
def u(i): return str(i)
@app.get("/g")
def gg(): return {"a": [1, 2]}
c = app.test_client()
for p in ("/", "/?v=2", "/json", "/r", "/e", "/u/3", "/u/x", "/bp/hi/z", "/g", "/nope"):
    c.get(p)
c.post("/json", json={"a": 1}); c.post("/json", data="zz")
with app.test_request_context("/x?y=1"):
    flask.request.args; flask.url_for("index"); flask.g.get("v")
app.url_map; app.config.from_mapping(A=1); app.config["A"]
cli = app.test_cli_runner(); cli.invoke(args=["routes"])
