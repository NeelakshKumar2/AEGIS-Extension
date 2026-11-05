import jinja2
from jinja2 import Environment, DictLoader, FileSystemLoader, select_autoescape, meta, nodes
from jinja2.sandbox import SandboxedEnvironment
tpls = {
 "base.html": "<html>{% block body %}{% endblock %}</html>",
 "page.html": """{% extends 'base.html' %}{% block body %}{% for u in users|sort(attribute='n') %}
 {{ loop.index }} {{ u.n|upper|e }} {% if u.a > 3 %}old{% elif u.a > 1 %}mid{% else %}new{% endif %}
 {% endfor %}{% include 'inc.html' %}{% set x = [1,2,3]|map('string')|join(',') %}{{ x }}
 {% macro m(a, b=2) %}{{ a }}-{{ b }}{% endmacro %}{{ m(1) }}{{ m(1, b=3) }}
 {{ "%s"|format(3) }} {{ users|length }} {{ users|selectattr('a','gt',1)|list|length }} {{ 'a b'|title }}
 {% with z = 5 %}{{ z * 2 }}{% endwith %}{{ users|groupby('a')|list|length }}{{ {'a': 1}|dictsort }}{% endblock %}""",
 "inc.html": "inc {% if users %}{{ users[0].n }}{% endif %} {{ none_var | default('d') }}{# c #}",
}
env = Environment(loader=DictLoader(tpls), autoescape=select_autoescape(["html"]), trim_blocks=True)
env.filters["twice"] = lambda s: s * 2
t = env.get_template("page.html")
t.render(users=[{"n": "bo", "a": 5}, {"n": "al", "a": 2}, {"n": "cy", "a": 0}])
env.from_string("{{ 'x'|twice }}{{ range(3)|list }}{{ 1 if true else 2 }}{{ [1,2][0] }}").render()
ast = env.parse(tpls["page.html"]); meta.find_undeclared_variables(ast); list(meta.find_referenced_templates(ast))
try: env.from_string("{{ a.b.c }}").render(a=None)
except Exception: pass
try: env.from_string("{% for %}").render()
except jinja2.TemplateSyntaxError: pass
jinja2.Template("{{ x|int + 1 }}", undefined=jinja2.StrictUndefined).render(x="3")
SandboxedEnvironment().from_string("{{ [1,2]|sum }}{{ x.__class__ }}").render(x=1)
env.get_template("inc.html").module
jinja2.Environment(extensions=["jinja2.ext.do"]).from_string("{% do 1 %}ok").render()
