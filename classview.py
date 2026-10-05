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

# Fixed page text by class language; a survey entry with "lang": "nl" (the
# Wednesday cohort) gets the Dutch strings. Item text comes from surveys.json.
STRINGS = {
    "en": {"answered": "{n} answered", "of_you": "{n} of you answered · {at}",
           "continue": "→ to continue", "too_few": "Not enough responses yet",
           "too_few_note": "Results appear once at least {m} people have answered.",
           "no_words": "Words appear once two students use them.", "thanks": "Thank you",
           "other": "Other", "multi": None,
           "coverage": "{a} of {n} answered · {b} left it blank · {d} words used by only one student are not shown",
           "topic_share": "main topic for {s}% of answers",
           "topic_none": "Too few answers, or too few shared words, for a topic model."},
    "nl": {"answered": "{n} beantwoord", "of_you": "{n} van jullie hebben geantwoord · {at}",
           "continue": "→ om verder te gaan", "too_few": "Nog niet genoeg antwoorden",
           "too_few_note": "Resultaten verschijnen zodra minstens {m} mensen hebben geantwoord.",
           "no_words": "Woorden verschijnen zodra twee studenten ze gebruiken.", "thanks": "Bedankt",
           "other": "Overig",
           "coverage": "{a} van de {n} antwoordden · {b} lieten het leeg · {d} woorden die maar één student gebruikte, staan er niet in",
           "topic_share": "hoofdonderwerp van {s}% van de antwoorden",
           "topic_none": "Te weinig antwoorden, of te weinig gedeelde woorden, voor een topicmodel.",
           "multi": ("% van de studenten die antwoordden. Je kon meer dan één antwoord "
                     "kiezen, dus de percentages tellen op tot meer dan 100.")},
}
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
           has_reveal: bool = False, s: dict = STRINGS["en"]) -> str:
    head = f'<p class="headline">{html.escape(headline)}</p>' if headline else ""
    return (f'<section class="slide" data-reveal="{int(has_reveal)}">'
            f'<h2>{html.escape(title)}</h2>{head}{body}'
            f'<p class="n">{s["answered"].format(n=n)}</p></section>')


def render_class_html(survey: dict, rows: list[dict[str, str]], fetched_at: str) -> str:
    n = len(rows)
    s = STRINGS.get(survey.get("lang", "en"), STRINGS["en"])
    multi_note = s["multi"] or report.MULTI_NOTE
    slides = [f'<section class="slide title"><h1>{html.escape(survey["title"])}</h1>'
              f'<p class="n">{html.escape(s["of_you"].format(n=n, at=fetched_at))}</p>'
              f'<p class="hint">{s["continue"]}</p></section>']
    if n < MIN_CELL:
        slides.append(f'<section class="slide"><h2>{s["too_few"]}</h2>'
                      f'<p class="n">{s["too_few_note"].format(m=MIN_CELL)}</p></section>')
    else:
        def group_slide(group: dict) -> None:
            table, answered = report.text_groups(rows, group["tag"], group["groups"], s["other"])
            stop = tuple(group.get("stopwords", []))
            words = report.word_counts(rows, group["tag"], group.get("min_word", 2), stop)
            top = max((c for _, c in words), default=1)
            cloud = "".join(
                f'<span class="w" style="font-size:{1.1 + 1.9 * c / top:.2f}vw">{html.escape(w)}</span>'
                for w, c in words)
            body = (f'<div class="split">{_bars(table, None)}'
                    f'<div class="cloud">{cloud or s["no_words"]}</div></div>')
            if group.get("coverage"):
                a, b, d = report.text_coverage(rows, group["tag"], group.get("min_word", 2), stop)
                body += f'<p class="note">{html.escape(s["coverage"].format(a=a, n=len(rows), b=b, d=d))}</p>'
            slides.append(_slide(group["title"], body, answered, group.get("headline"), s=s))
            if group.get("topics"):
                topics, used = report.topic_model(rows, group["tag"], group["topics"].get("k", 3),
                                                  extra_stop=stop)
                cards = "".join(
                    f'<div class="topic"><div class="tw">{html.escape(" · ".join(w))}</div>'
                    f'<div class="ts">{html.escape(s["topic_share"].format(s=round(sh)))}</div></div>'
                    for w, sh in topics) or f'<p class="n">{s["topic_none"]}</p>'
                slides.append(_slide(group["topics"]["title"], f'<div class="topics">{cards}</div>',
                                     used, group["topics"].get("headline"), s=s))

        # A text group with "after": <tag> follows that item, as on the survey.
        placed = {g["after"]: g for g in survey.get("text_groups", []) if g.get("after")}
        previous = "start"  # "after": "start" places a group before the first item
        for item in survey.get("items", []):
            if previous in placed:
                group_slide(placed[previous])
            tag, title = item["tag"], item.get("title", item["tag"])
            previous = tag
            headline, reveal = item.get("headline"), item.get("reveal")
            if item.get("matrix"):
                cols = report.matrix_columns(rows, tag)
                row_labels, col_labels = item.get("rows", []), item.get("labels", [])
                # One stacked bar per statement so five statements fit one screen.
                colors = (BLUE, ORANGE) + (INK,) * max(0, len(col_labels) - 2)
                legend = "".join(f'<span class="key"><i style="--c:{c}"></i>{html.escape(l)}</span>'
                                 for l, c in zip(col_labels, colors))
                parts = []
                for index, col in enumerate(cols):
                    statement = row_labels[index] if index < len(row_labels) else col
                    counter = Counter(report._values(rows, col))
                    total = sum(counter.values())
                    segs = ""
                    for label, c in zip(col_labels, colors):
                        cn = counter.get(label, 0)
                        cp = (100.0 * cn / total) if total else 0.0
                        shown = "&lt;5" if 0 < cn < MIN_CELL else f"{cp:.0f}%"
                        segs += (f'<div class="seg" style="width:{cp:.1f}%;--c:{c}">'
                                 f'{shown if cn else ""}</div>')
                    parts.append(f'<div class="row"><div class="label">{html.escape(statement)}</div>'
                                 f'<div class="stack">{segs}</div></div>')
                body = f'<div class="legend">{legend}</div><div class="bars">{"".join(parts)}</div>'
                slides.append(_slide(title, body, n, headline, s=s))
                continue
            multi = item.get("multi", False)
            table = report.count_table(rows, tag, item.get("labels", []), multi=multi)
            if multi:
                answered = sum(1 for row in rows if report._values([row], tag, True))
                body = _bars(table, reveal) + f'<p class="note">{html.escape(multi_note)}</p>'
            else:
                answered = sum(t[1] for t in table)
                body = _bars(table, reveal)
            slides.append(_slide(title, body, answered, headline, bool(reveal), s=s))
        if previous in placed:
            group_slide(placed[previous])
        for group in survey.get("text_groups", []):
            if not group.get("after"):
                group_slide(group)
        field = survey.get("condition_field")
        for arm in survey.get("arms", []):
            conds = list(arm["columns"].keys())
            table = report.arm_table(rows, arm, field)
            arm_n = Counter(row.get(field, "") for row in rows)
            legend = "".join(f'<span class="key"><i style="--c:{c}"></i>{html.escape(cond.replace("_", " "))}'
                             f' (n={arm_n.get(cond, 0)})</span>'
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
            slides.append(_slide(arm["title"], body, n, arm.get("headline"), s=s))
    slides.append(f'<section class="slide title"><h1>{s["thanks"]}</h1></section>')

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
.stack{{display:flex;height:2.6vw;border-radius:4px;overflow:hidden;background:var(--grid)}}
.seg{{background:var(--c);color:#fff;font-size:1.3vw;line-height:2.6vw;padding-left:.5vw;white-space:nowrap;overflow:hidden}}
.row:has(.stack){{grid-template-columns:45% 1fr;font-size:1.6vw;margin:.45em 0}}
.legend{{display:flex;gap:2vw;font-size:1.6vw;margin-bottom:.6em;font-family:Fira Sans,Helvetica,Arial,sans-serif}}
.key i{{display:inline-block;width:1.2vw;height:1.2vw;background:var(--c);border-radius:3px;margin-right:.5vw;vertical-align:middle}}
.n{{color:var(--muted);font-size:1.5vw;margin-top:1.4em;font-family:Fira Sans,Helvetica,Arial,sans-serif}}
.hint{{color:var(--muted);font-size:1.3vw}}
.note{{color:var(--muted);font-size:1.4vw;margin:.8em 0 0;font-family:Fira Sans,Helvetica,Arial,sans-serif}}
.split{{display:grid;grid-template-columns:58% 1fr;gap:3vw;align-items:center}}
.split .row{{font-size:1.45vw;margin:.28em 0;grid-template-columns:42% 1fr}}
.split .track{{height:1.7vw;width:calc(100% - 7vw)}}.split .val{{line-height:1.7vw}}
.cloud{{line-height:1.45;text-align:center;font-family:Fira Sans,Helvetica,Arial,sans-serif;color:var(--ink)}}
.cloud .w{{display:inline-block;margin:0 .6vw}}
.topics{{display:grid;gap:1.2vw}}
.topic{{background:#eef1f8;border-left:.5vw solid {ORANGE};padding:1vw 1.4vw;border-radius:4px;font-family:Fira Sans,Helvetica,Arial,sans-serif}}
.tw{{font-size:2.2vw;color:var(--ink)}}.ts{{font-size:1.4vw;color:var(--muted);margin-top:.3em}}
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
