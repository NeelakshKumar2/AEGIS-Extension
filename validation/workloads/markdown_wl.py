import markdown
src = """# Title
Some *emph* and **strong** and `code` text with [link](http://a.b "t") and ![img](a.png).

* item one
* item two
    * nested

1. a
2. b

> quote
> more

    indented code

```python
print(1)
```

| a | b |
|---|---|
| 1 | 2 |

Term
:   Def

Footnote[^1]

[^1]: note

<div>html</div>

---
"""
for exts in ([], ["tables", "fenced_code", "footnotes", "def_list", "toc", "attr_list", "abbr", "admonition", "sane_lists", "smarty", "meta", "nl2br", "md_in_html"]):
    md = markdown.Markdown(extensions=exts)
    md.convert(src); md.reset(); md.convert("plain *x*")
markdown.markdown("a  \nb", output_format="xhtml"); markdown.markdown("<b>x</b> &amp; < >")
