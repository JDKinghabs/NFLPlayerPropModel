"""Static website: one self-contained index.html (+ the xlsx for download)."""
from __future__ import annotations

import shutil
from html import escape
from pathlib import Path

import pandas as pd

from . import config as C

XLSX_NAME = "NFL_Props_latest.xlsx"
REPO_URL = "https://github.com/JDKinghabs/NFLPlayerPropModel"

CSS = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#14181f;--mute:#5b6573;--line:#e3e7ec;--accent:#1f4e78;
--good:#0b7a3b;--good-bg:#dff3e6;--bad:#b3261e;--bad-bg:#fbe3e1;--weak:#b5541a;--weak-bg:#fde8d8;
--strong:#1f5fa8;--strong-bg:#e1ecf8;--warn-bg:#fff4cf;--qb:#1f4e78;--rb:#2f6b2a;--wr:#8a4b08}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]):not([data-theme=dark]){--bg:#0f1318;--card:#181e26;--ink:#e8ecf1;
--mute:#9aa6b4;--line:#2a323d;--accent:#7fb0e0;--good:#5fd391;--good-bg:#133c26;--bad:#ff8c84;--bad-bg:#4a1d1a;
--weak:#f2a56b;--weak-bg:#4a2d17;--strong:#8dbcf0;--strong-bg:#183049;--warn-bg:#3d3511;--qb:#7fb0e0;--rb:#86d17f;--wr:#f0b36a}}

:root[data-theme=dark]{--bg:#0f1318;--card:#181e26;--ink:#e8ecf1;
--mute:#9aa6b4;--line:#2a323d;--accent:#7fb0e0;--good:#5fd391;--good-bg:#133c26;--bad:#ff8c84;--bad-bg:#4a1d1a;
--weak:#f2a56b;--weak-bg:#4a2d17;--strong:#8dbcf0;--strong-bg:#183049;--warn-bg:#3d3511;--qb:#7fb0e0;--rb:#86d17f;--wr:#f0b36a}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
.wrap{max-width:1400px;margin:0 auto;padding:16px}
h1{font-size:22px;margin:0 0 4px}.sub{color:var(--mute);font-size:13px;margin:0}
.note{background:var(--warn-bg);border-radius:8px;padding:8px 12px;font-size:13px;margin:12px 0 0}
.tabs{display:flex;gap:8px;margin:16px 0 4px;flex-wrap:wrap}
.tab{border:1px solid var(--line);background:var(--card);color:var(--ink);padding:9px 14px;border-radius:999px;
font:inherit;font-weight:600;cursor:pointer}.tab[aria-selected=true]{background:var(--accent);color:var(--bg);border-color:var(--accent)}
.lede{color:var(--mute);font-size:13px;margin:8px 0 12px;max-width:900px}
.cols{display:grid;grid-template-columns:1fr;gap:20px}
@media(min-width:1000px){.cols{grid-template-columns:repeat(3,1fr);align-items:start}}
.col h2{font-size:15px;margin:0 0 8px;padding:8px 12px;border-radius:8px;color:#fff}
.col.QB h2{background:#1f4e78}.col.RB h2{background:#2f6b2a}.col.WR h2{background:#8a4b08}
.chipnav{display:flex;gap:8px;margin:4px 0 12px}@media(min-width:1000px){.chipnav{display:none}}
.chipnav a{padding:6px 12px;border:1px solid var(--line);border-radius:999px;color:var(--ink);text-decoration:none;
font-weight:600;background:var(--card);font-size:13px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px;margin:0 0 10px}
.card.priced{opacity:.72}
.top{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}
.name{font-weight:700;font-size:16px}.tm{color:var(--mute);font-weight:600;font-size:12px;margin-left:4px}
.proj{text-align:right;line-height:1}.proj b{font-size:26px}.proj small{display:block;color:var(--mute);font-size:11px;margin-top:2px}
.game{color:var(--mute);font-size:13px;margin:2px 0 8px}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:8px}
.chip{font-size:12px;padding:2px 8px;border-radius:999px;background:var(--bg);border:1px solid var(--line)}
.chip.weak{background:var(--weak-bg);color:var(--weak);border-color:transparent;font-weight:600}
.chip.strong{background:var(--strong-bg);color:var(--strong);border-color:transparent;font-weight:600}
.chip.out{background:var(--bad-bg);color:var(--bad);border-color:transparent;font-weight:600}
.chip.q{background:var(--warn-bg);border-color:transparent}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin:0 0 8px}
.stats div{background:var(--bg);border-radius:8px;padding:6px 8px}
.stats dt{font-size:11px;color:var(--mute)}.stats dd{margin:0;font-weight:650;font-size:13px}
.starter{font-size:13px;margin:0 0 8px}.starter span{color:var(--mute)}
.line{display:flex;align-items:center;gap:8px;font-size:13px;color:var(--mute)}
.line input{width:104px;font:inherit;font-weight:650;padding:6px 8px;border:1px solid var(--line);border-radius:8px;
background:var(--warn-bg);color:var(--ink)}
.edge{font-weight:700}.edge.pos{color:var(--good)}.edge.neg{color:var(--bad)}
.empty{color:var(--mute);font-style:italic;padding:12px;border:1px dashed var(--line);border-radius:12px}
.trust{margin:28px 0 0;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.trust h3{margin:0 0 6px;font-size:15px}.trust ul{margin:0;padding-left:18px;color:var(--mute);font-size:13px}.trust li{margin:4px 0}
footer{color:var(--mute);font-size:12px;margin:18px 0 8px}footer a{color:var(--accent)}
[hidden]{display:none!important}
"""

JS = """
(function(){
  var tabs=document.querySelectorAll('.tab'), panels=document.querySelectorAll('.panel');
  function show(id){tabs.forEach(function(t){t.setAttribute('aria-selected',t.dataset.p===id)});
    panels.forEach(function(p){p.hidden=p.id!==id});try{history.replaceState(null,'','#'+id)}catch(e){}}
  tabs.forEach(function(t){t.addEventListener('click',function(){show(t.dataset.p)})});
  var h=(location.hash||'').slice(1);show(document.getElementById(h)&&h.indexOf('p')===0?h:'p1');
  function store(k,v){try{v===''?localStorage.removeItem(k):localStorage.setItem(k,v)}catch(e){}}
  function load(k){try{return localStorage.getItem(k)||''}catch(e){return ''}}
  document.querySelectorAll('input[data-proj]').forEach(function(inp){
    var out=inp.parentNode.querySelector('.edge'), proj=parseFloat(inp.dataset.proj), key='line:'+inp.dataset.key;
    function upd(){var v=parseFloat(inp.value);if(isNaN(v)){out.textContent='';out.className='edge';return}
      var e=proj-v;out.textContent=(e>0?'+':'')+e.toFixed(1)+(e>0?' model above line':' model below line');
      out.className='edge '+(e>0?'pos':'neg')}
    inp.value=load(key);upd();
    inp.addEventListener('input',function(){store(key,inp.value);upd()});
  });
})();
"""


def _n(x, d=0):
    return "" if pd.isna(x) else f"{x:,.{d}f}"


def _opp(row) -> str:
    t = row["opp_txt"]
    return f"at {t[1:]}" if t.startswith("@") else f"vs {t}"


def _rank_chip(rank, vs_lg) -> str:
    if pd.isna(rank):
        return ""
    rank = int(rank)
    cls = "weak" if rank <= C.WEAK_DEF_N else "strong" if rank >= 33 - C.WEAK_DEF_N else ""
    word = "weak D" if cls == "weak" else "strong D" if cls == "strong" else "D"
    return f'<span class="chip {cls}">Opp {word} #{rank} &middot; {vs_lg:+.0%} vs avg</span>'


def _inj_chip(label) -> str:
    if not label:
        return ""
    cls = "out" if label.startswith(("OUT", "DOUBT")) else "q"
    return f'<span class="chip {cls}">{escape(label)}</span>'


def _line_box(proj, key) -> str:
    return (f'<label class="line">Book line <input type="text" inputmode="decimal" placeholder="enter line" '
            f'data-proj="{proj:.2f}" data-key="{escape(key)}" aria-label="Sportsbook line"> <span class="edge"></span></label>')


def _elite_card(r, cat) -> str:
    key = f"e|{cat.key}|{r['name']}|{r['week']}"
    return (
        '<article class="card">'
        f'<div class="top"><div><span class="name">{escape(r["name"])}</span><span class="tm">{escape(r["team"])}</span></div>'
        f'<div class="proj"><b>{_n(r["proj"])}</b><small>proj yds</small></div></div>'
        f'<div class="game">{escape(_opp(r))} &middot; {escape(r["kick_txt"])}'
        f'{" &middot; " + escape(r["spr_tot"]) if r["spr_tot"] else ""}</div>'
        f'<div class="chips">{_rank_chip(r["opp_rank"], r["vs_lg"])}{_inj_chip(r["inj"])}</div>'
        f'<dl class="stats"><div><dt>Season</dt><dd>{_n(r["total"])} (#{int(r["rank"])})</dd></div>'
        f'<div><dt>Per game</dt><dd>{_n(r["ypg"], 1)}</dd></div><div><dt>Last 3</dt><dd>{_n(r["l3"], 1)}</dd></div>'
        f'<div><dt>Games</dt><dd>{int(r["games"])}</dd></div></dl>'
        f'{_line_box(r["proj"], key)}</article>')


def _backup_card(r, cat) -> str:
    key = f"b|{cat.key}|{r['name']}|{r['week']}"
    v = cat.vol_short
    priced = r["streak"] >= C.ESTABLISHED_AFTER
    p = r["p_out"]
    pchip = (f'<span class="chip out">Starter out</span>' if p >= 0.99
             else f'<span class="chip q">{p:.0%} chance starter is out</span>')
    priced_chip = '<span class="chip">likely priced in</span>' if priced else ""
    return (
        f'<article class="card{" priced" if priced else ""}">'
        f'<div class="top"><div><span class="name">{escape(r["name"])}</span><span class="tm">{escape(r["team"])} &middot; {escape(r["role"])}</span></div>'
        f'<div class="proj"><b>{_n(r["proj_exp"])}</b><small>exp yds</small></div></div>'
        f'<div class="game">{escape(_opp(r))} &middot; {escape(r["kick_txt"])}'
        f'{" &middot; " + escape(r["spr_tot"]) if r["spr_tot"] else ""}</div>'
        f'<p class="starter"><span>Out:</span> {escape(r["starters_out"])}</p>'
        f'<div class="chips">{pchip}{priced_chip}{_rank_chip(r["opp_rank"], r["opp_vs_lg"])}{_inj_chip(r["inj"])}</div>'
        f'<dl class="stats"><div><dt>{v}/G now</dt><dd>{_n(r["base_vol"], 1)}</dd></div>'
        f'<div><dt>{v}/G proj</dt><dd>{_n(r["proj_vol"], 1)}</dd></div>'
        f'<div><dt>Last game</dt><dd>{_n(r["last_vol"])}</dd></div>'
        f'<div><dt>If out</dt><dd>{_n(r["proj_if_out"])} yds</dd></div></dl>'
        f'{_line_box(r["proj_exp"], key)}</article>')


def _columns(frames: dict, card) -> str:
    out = []
    for k, cat in C.CATS.items():
        df = frames.get(k)
        title = cat.title.replace(" - ", " &middot; ")
        if df is None or df.empty:
            body = '<div class="empty">No qualifying players for this slate.</div>'
        else:
            body = "".join(card(r, cat) for _, r in df.iterrows())
        out.append(f'<section class="col {k}" id="{{pfx}}-{k}"><h2>{title}</h2>{body}</section>')
    return "".join(out)


def _chipnav(pfx: str) -> str:
    return '<nav class="chipnav">' + "".join(
        f'<a href="#{pfx}-{k}">{k}</a>' for k in C.CATS) + "</nav>"


def render(res, xlsx_name: str | None = XLSX_NAME) -> str:
    m = res.meta
    wk = ", ".join(map(str, m["weeks"]))
    upd = m["generated"].strftime("%a %b %d, %I:%M %p ET").replace(" 0", " ")
    notes = []
    for w, (rep, stale) in m["injury_reports"].items():
        if stale:
            notes.append(f"Week {w} injury reports aren't out yet, so week {rep}'s statuses are carried forward at "
                         f"historical odds. Expect changes Wednesday-Friday.")
        elif rep is None:
            notes.append(f"Week {w} injury reports aren't out yet, so those games carry no injury flags.")
    note_html = "".join(f'<div class="note">{escape(n)}</div>' for n in notes)
    dl = f' &middot; <a href="{xlsx_name}">Download Excel</a>' if xlsx_name else ""
    p1 = _columns(res.elite, _elite_card).replace("{pfx}", "e")
    p2 = _columns(res.backups, _backup_card).replace("{pfx}", "b")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>NFL Prop Model</title>
<meta name="description" content="QB passing, RB rushing and WR receiving yard research: elite players vs weak defenses, and backups stepping in for injured starters.">
<style>{CSS}</style></head><body><div class="wrap">
<h1>NFL Prop Model</h1>
<p class="sub">{res.season} season &middot; week{"s" if len(m["weeks"]) > 1 else ""} {escape(wk)} &middot; {m["games"]} games not yet kicked off &middot; stats through week {m["data_through_week"]} &middot; updated {escape(upd)}{dl}</p>
{note_html}
<div class="tabs" role="tablist">
<button class="tab" role="tab" data-p="p1" aria-selected="true">Elite vs weak D</button>
<button class="tab" role="tab" data-p="p2" aria-selected="false">Backups</button></div>

<div class="panel" id="p1">
<p class="lede">Top {m["top_n"]} at each position by {res.season} yards, facing one of the {m["weak_n"]} defenses that allow the most yards to that position. <b>Proj</b> is a fair-value anchor, not a prediction: type the sportsbook line in the box to see the gap.</p>
{_chipnav("e")}<div class="cols">{p1}</div></div>

<div class="panel" id="p2" hidden>
<p class="lede">QB2, RB2+ and WR3+ on teams missing a starter who carries real volume. <b>Exp yds</b> is weighted by the chance the starter actually sits; <b>If out</b> assumes he does. Faded cards: the starter has already missed 3+ straight games, so the market has had time to adjust.</p>
{_chipnav("b")}<div class="cols">{p2}</div></div>

<section class="trust"><h3>How much to trust this</h3><ul>
<li>Back-tested on 2023-25: elite players beat their baseline by about 1-8% against weak defenses and fall 8-12% short against strong ones. The effect is real, but books price the headline matchups too.</li>
<li>Single-game yardage is noisy (typical miss: about 75 yds for QBs, 43 for RB/WR), so projections barely beat a plain season average on accuracy.</li>
<li>Backups: the model gets the size of the extra workload right (QB, RB, WR), is strong for QBs and modest for RBs, and can't reliably say which WR gets the extra targets.</li>
<li>Late injuries and inactives aren't visible until the next report, so check the news before betting.</li>
<li>There are no sportsbook lines in the data. The edge box only compares the model to the number you type.</li></ul></section>
<footer>For research and entertainment only, not betting advice. Gamble responsibly and only if you are of legal age where you live.
Data: <a href="https://github.com/nflverse/nflverse-data">nflverse</a>. Method, back-tests and code: <a href="{REPO_URL}">GitHub</a>.</footer>
</div><script>{JS}</script></body></html>"""


def write_site(res, out_dir: Path, xlsx_path: Path | None = None) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    has_xlsx = xlsx_path is not None and Path(xlsx_path).exists()
    if has_xlsx:
        shutil.copyfile(xlsx_path, out_dir / XLSX_NAME)
    (out_dir / "index.html").write_text(render(res, XLSX_NAME if has_xlsx else None), encoding="utf-8")
    (out_dir / ".nojekyll").write_text("")
    return out_dir / "index.html"
