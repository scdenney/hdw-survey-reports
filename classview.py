"""Class view: a projectable, standalone HTML page built from one survey's rows.

Counts only, never free text. Cells below MIN_CELL are shown as "<5" and the
whole page says so when fewer than MIN_CELL people answered, as the consent
notice promises. Items step through like slides (arrow keys, space, click);
an item with a ``reveal`` label in surveys.json highlights that answer on the
second press so the room can guess first.
"""

from __future__ import annotations

import html
import json
from collections import Counter

import report

MIN_CELL = 5
BLUE = "#2C4A9E"      # series A / default bar   (validated pair, light surface)
ORANGE = "#F46E32"    # series B / reveal
INK = "#001158"       # titles
SURFACE = "#fcfcfb"


def _bars(table: list[tuple[str, int, float]], reveal: str | None,
          color: str = BLUE) -> str:
    total = sum(n for _, n, _ in table)
    out = []
    for label, n, pct in table:
        suppressed = 0 < n < MIN_CELL
        width = 4.0 if suppressed else (max(pct, 1.5) if n else 0)
        shown = "&lt;5" if suppressed else f"{n} · {pct:.0f}%"
        cls = "bar" + (" reveal" if reveal and label == reveal else "")
        out.append(
            f'<div class="row"><div class="label">{html.escape(label)}</div>'
            f'<div class="track"><div class="{cls}" style="width:{width:.1f}%;--c:{color}"></div>'
            f'<span class="val">{shown}</span></div></div>')
    return f'<div class="bars" data-total="{total}">' + "".join(out) + "</div>"


def _slide(title: str, body: str, n: int, headline: str | None = None,
           has_reveal: bool = False) -> str:
    head = f'<p class="headline">{html.escape(headline)}</p>' if headline else ""
    return (f'<section class="slide" data-reveal="{int(has_reveal)}">'
            f'<h2>{html.escape(title)}</h2>{head}{body}'
            f'<p class="n">{n} answered</p></section>')


def render_class_html(survey: dict, rows: list[dict[str, str]], fetched_at: str) -> str:
    n = len(rows)
    slides = [f'<section class="slide title"><h1>{html.escape(survey["title"])}</h1>'
              f'<p class="n">{n} of you answered · {html.escape(fetched_at)}</p>'
              f'<p class="hint">→ to continue</p></section>']
    if n < MIN_CELL:
        slides.append('<section class="slide"><h2>Not enough responses yet</h2>'
                      f'<p class="n">Results appear once at least {MIN_CELL} people have answered.</p></section>')
    else:
        for item in survey.get("items", []):
            tag, title = item["tag"], item.get("title", item["tag"])
            headline, reveal = item.get("headline"), item.get("reveal")
            if item.get("matrix"):
                cols = report.matrix_columns(rows, tag)
                row_labels, col_labels = item.get("rows", []), item.get("labels", [])
                parts = []
                for index, col in enumerate(cols):
                    statement = row_labels[index] if index < len(row_labels) else col
                    counter = Counter(report._values(rows, col))
                    total = sum(counter.values())
                    table = [(l, counter.get(l, 0), (100.0 * counter.get(l, 0) / total) if total else 0.0)
                             for l in col_labels]
                    parts.append(f'<h3>{html.escape(statement)}</h3>' + _bars(table, None))
                slides.append(_slide(title, "".join(parts), n, headline))
                continue
            table = report.count_table(rows, tag, item.get("labels", []), multi=item.get("multi", False))
            answered = sum(t[1] for t in table)
            slides.append(_slide(title, _bars(table, reveal), answered, headline, bool(reveal)))
        field = survey.get("condition_field")
        for arm in survey.get("arms", []):
            conds = list(arm["columns"].keys())
            table = report.arm_table(rows, arm, field)
            legend = "".join(f'<span class="key"><i style="--c:{c}"></i>{html.escape(cond.replace("_", " "))}</span>'
                             for cond, c in zip(conds, (BLUE, ORANGE)))
            rowsh = []
            for label, cells in table:
                bars = ""
                for cond, c in zip(conds, (BLUE, ORANGE)):
                    cn, cp = cells[cond]
                    suppressed = 0 < cn < MIN_CELL
                    shown = "&lt;5" if suppressed else f"{cp:.0f}%"
                    width = 4.0 if suppressed else (max(cp, 1.5) if cn else 0)
                    bars += (f'<div class="track"><div class="bar" style="width:{width:.1f}%;--c:{c}"></div>'
                             f'<span class="val">{shown}</span></div>')
                rowsh.append(f'<div class="row"><div class="label">{html.escape(label)}</div>'
                             f'<div class="pair">{bars}</div></div>')
            body = f'<div class="legend">{legend}</div><div class="bars">{"".join(rowsh)}</div>'
            slides.append(_slide(arm["title"], body, n, arm.get("headline")))
    slides.append('<section class="slide title"><h1>Thank you</h1></section>')

    css = f"""
:root{{--ink:{INK};--surface:{SURFACE};--muted:#5b6170;--grid:#e6e6e3}}
*{{box-sizing:border-box}}html,body{{margin:0;height:100%;background:var(--surface);
font-family:Merriweather,Georgia,serif;color:#1d2230}}
.slide{{display:none;height:100vh;overflow:hidden;padding:4vh 8vw;flex-direction:column;justify-content:center}}
.slide.active{{display:flex}}
h1{{color:var(--ink);font-size:5.2vw;margin:0 0 .4em;line-height:1.1}}
h2{{color:var(--ink);font-size:3vw;margin:0 0 .5em;line-height:1.15}}
h3{{font-size:1.8vw;margin:1.2em 0 .3em;color:var(--muted);font-weight:normal}}
.headline{{font-size:2.2vw;color:{ORANGE};margin:0 0 .8em;font-family:Fira Sans,Helvetica,Arial,sans-serif}}
.row{{display:grid;grid-template-columns:38% 1fr;gap:1.2vw;align-items:center;margin:.55em 0;font-size:1.9vw;
font-family:Fira Sans,Helvetica,Arial,sans-serif}}
.label{{line-height:1.2}}
.track{{position:relative;height:2.3vw;background:var(--grid);border-radius:4px}}
.bar{{height:100%;background:var(--c);border-radius:0 4px 4px 0;transition:width .5s}}
.bar.reveal{{background:{ORANGE}}}
.slide[data-reveal="1"]:not(.revealed) .bar.reveal{{background:var(--c)}}
.val{{position:absolute;left:100%;top:0;margin-left:.6vw;line-height:2.3vw;color:var(--muted);white-space:nowrap}}
.track{{width:calc(100% - 9vw)}}
.pair{{display:grid;gap:.3vw}}.pair .track{{height:1.4vw}}.pair .val{{line-height:1.4vw}}
.row:has(.pair){{margin:.3em 0;font-size:1.6vw}}
.legend{{display:flex;gap:2vw;font-size:1.6vw;margin-bottom:.6em;font-family:Fira Sans,Helvetica,Arial,sans-serif}}
.key i{{display:inline-block;width:1.2vw;height:1.2vw;background:var(--c);border-radius:3px;margin-right:.5vw;vertical-align:middle}}
.n{{color:var(--muted);font-size:1.5vw;margin-top:1.4em;font-family:Fira Sans,Helvetica,Arial,sans-serif}}
.hint{{color:var(--muted);font-size:1.3vw}}
.counter{{position:fixed;right:1.5vw;bottom:1vw;color:var(--muted);font-size:1.1vw;font-family:Fira Sans,Helvetica,Arial,sans-serif}}
"""
    js = """
const s=[...document.querySelectorAll('.slide')];let i=0;const c=document.querySelector('.counter');
function show(k){s[i].classList.remove('active');i=Math.max(0,Math.min(s.length-1,k));s[i].classList.add('active');c.textContent=(i+1)+' / '+s.length;}
function next(){const cur=s[i];if(cur.dataset.reveal==='1'&&!cur.classList.contains('revealed')){cur.classList.add('revealed');return;}show(i+1);}
function prev(){show(i-1);}
document.addEventListener('keydown',e=>{if(['ArrowRight','ArrowDown',' ','PageDown'].includes(e.key)){e.preventDefault();next();}
if(['ArrowLeft','ArrowUp','PageUp'].includes(e.key)){e.preventDefault();prev();}});
document.addEventListener('click',e=>{(e.clientX>window.innerWidth/4)?next():prev();});
show(0);
"""
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<title>{html.escape(survey["title"])} – class view</title>'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><style>{css}</style></head>'
            f'<body>{"".join(slides)}<div class="counter"></div><script>{js}</script></body></html>')
