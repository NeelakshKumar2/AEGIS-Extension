import click
from click.testing import CliRunner

@click.group()
@click.option("--debug/--no-debug", default=False)
@click.pass_context
def cli(ctx, debug):
    ctx.obj = {"debug": debug}

@cli.command()
@click.option("--name", "-n", default="w", help="who", show_default=True)
@click.option("--count", type=click.IntRange(1, 5), default=1)
@click.argument("items", nargs=-1)
@click.pass_context
def hello(ctx, name, count, items):
    for _ in range(count):
        click.echo(f"hi {name} {items}")
    click.secho("done", fg="green")

@cli.command()
@click.option("--mode", type=click.Choice(["a", "b"]), prompt=True)
@click.option("--flag", is_flag=True)
@click.option("--path", type=click.Path(exists=False))
@click.option("--f", type=float, default=1.5)
def other(mode, flag, path, f):
    click.echo(mode)

@cli.group()
def sub(): pass

@sub.command()
@click.argument("x", type=int)
def add(x): click.echo(x + 1)

@cli.command()
def boom(): raise click.ClickException("bad")

r = CliRunner()
for args in (["--help"], ["hello", "--help"], ["hello", "-n", "z", "--count", "2", "a", "b"],
             ["other", "--mode", "a", "--flag"], ["other", "--mode", "zzz"], ["sub", "add", "3"],
             ["sub", "add", "x"], ["boom"], ["nope"], ["--debug", "hello"], ["other", "--help"], ["sub", "--help"]):
    r.invoke(cli, args)
r.invoke(cli, ["other"], input="b\n")
click.format_filename("a/b"); click.style("x", bold=True); click.unstyle("\x1b[1mx\x1b[0m")
click.utils.make_default_short_help("hello world. more", 20)
with r.isolated_filesystem():
    r.invoke(cli, ["other", "--mode", "a", "--path", "."])
