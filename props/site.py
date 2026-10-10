"""Static website: one self-contained index.html (+ the xlsx for download).

Tabs: Top plays (the board, props/picks.py) | Yardage | Backups | Anytime TD | My bets.  Dark only, by design.
"""
from __future__ import annotations

import json
import shutil
from html import escape
from pathlib import Path

import pandas as pd

from . import calibration as CAL
from . import config as C
from . import odds as O
from . import picks as P
from .td import TD_GROUPS
from .volume import TOUCH_LABEL, TOUCH_NAME, TOUCH_WORD

XLSX_NAME = "NFL_Props_latest.xlsx"
REPO_URL = "https://github.com/JDKinghabs/NFLPlayerPropModel"
BOOK = P.BOOK_NAME.get(C.ODDS_BOOK, C.ODDS_BOOK)       # "DraftKings"

CSS = """
:root{color-scheme:dark;--bg:#0f1115;--surface:#171a21;--surface-2:#1d2129;--surface-3:#262b35;--line:#252a33;--line-2:#333a47;
--text:#e7e9ee;--muted:#9aa3b2;--faint:#6b7385;--pos:#22c55e;--pos-bg:rgba(34,197,94,.13);--neg:#f43f5e;--neg-bg:rgba(244,63,94,.13);
--warn:#f5b041;--warn-bg:rgba(245,176,65,.13);--info:#60a5fa;--r:12px}
*{box-sizing:border-box}
html{background:var(--bg);-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;font-variant-numeric:tabular-nums}
a{color:var(--info)}
.wrap{max-width:1280px;margin:0 auto;padding:0 16px 32px}

/* header */
.topbar{position:sticky;top:0;z-index:5;background:rgba(15,17,21,.94);backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);
border-bottom:1px solid var(--line);margin:0 -16px 16px;padding:12px 16px 0}
.brandrow{display:flex;justify-content:space-between;align-items:center;gap:10px 16px;flex-wrap:wrap}
.brand{font-weight:800;font-size:19px;letter-spacing:-.01em}.brand span{color:var(--pos)}
.sub{color:var(--muted);font-size:12.5px;margin:1px 0 0}
.hright{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.pill{display:inline-flex;align-items:center;gap:7px;font-size:12px;font-weight:650;padding:5px 11px;border-radius:999px;
background:var(--surface-2);border:1px solid var(--line);color:var(--muted)}
.pill::before{content:"";width:7px;height:7px;border-radius:50%;background:var(--faint)}
.pill.ok{color:var(--text)}.pill.ok::before{background:var(--pos)}.pill.warn::before{background:var(--warn)}
.dl{font-size:12px;font-weight:650;color:var(--muted);text-decoration:none;border:1px solid var(--line);padding:5px 11px;border-radius:999px}
.dl:hover{color:var(--text);border-color:var(--line-2)}
.tabs{display:flex;gap:2px;margin:10px 0 0;overflow-x:auto;scrollbar-width:none}.tabs::-webkit-scrollbar{display:none}
.tab{appearance:none;border:0;background:none;color:var(--muted);font:inherit;font-weight:650;font-size:14px;padding:10px 12px 11px;
cursor:pointer;border-bottom:2px solid transparent;white-space:nowrap}
.tab:hover{color:var(--text)}.tab[aria-selected=true]{color:var(--text);border-bottom-color:var(--pos)}
.note{background:var(--warn-bg);color:#f3d9a6;border-radius:8px;padding:7px 12px;font-size:12.5px;margin:0 0 10px}
.lede{color:var(--muted);font-size:13px;margin:0 0 12px;max-width:860px}.lede b{color:var(--text)}

/* top plays board */
.board{max-width:900px}
.boardhead{display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:6px 12px;margin:4px 0 12px}
.boardhead h2{margin:0;font-size:21px;letter-spacing:-.01em}.boardhead .count{color:var(--muted);font-size:13px}
.pick{display:grid;grid-template-columns:40px 1fr auto;gap:2px 14px;background:var(--surface);border:1px solid var(--line);
border-radius:var(--r);padding:14px 16px;margin:0 0 10px}
.pick:hover{border-color:var(--line-2)}
.grade{grid-row:1/3;width:40px;height:40px;border-radius:10px;display:grid;place-items:center;font-weight:800;font-size:18px}
.grade.A{background:var(--pos);color:#052e14}.grade.B{color:var(--pos);border:1.5px solid var(--pos)}
.pwho{font-weight:700;font-size:16px;line-height:1.25}.pwhen{color:var(--muted);font-size:12.5px}
.pev{text-align:right;font-weight:800;color:var(--pos);font-size:16px;line-height:1.2}
.pev small{display:block;color:var(--faint);font-weight:600;font-size:10.5px;text-transform:uppercase;letter-spacing:.04em}
.pbet{grid-column:2/4;display:flex;align-items:baseline;gap:4px 10px;flex-wrap:wrap;margin-top:6px}
.pside{font-weight:800;font-size:21px;letter-spacing:.01em}.pside.over,.pside.yes{color:var(--pos)}.pside.under{color:var(--neg)}
.pmkt{color:var(--muted);font-size:13px;font-weight:600}.pprice{font-weight:800;font-size:15px}.pbook{color:var(--faint);font-size:12px}
.pbar{grid-column:2/4;display:flex;flex-wrap:wrap;align-items:center;gap:6px 12px;margin:8px 0 2px;font-size:12.5px;color:var(--muted)}
.pbar b{color:var(--text)}.pbar .edge{color:var(--pos);font-weight:750}
.bar{position:relative;flex:1 1 160px;max-width:280px;height:6px;background:var(--surface-3);border-radius:99px}
.bar i{position:absolute;left:0;top:0;bottom:0;border-radius:99px;background:var(--pos)}
.bar u{position:absolute;top:-4px;width:2px;height:14px;background:var(--text);border-radius:2px;text-decoration:none}
.pwhy{grid-column:2/4;color:var(--muted);font-size:12.5px;margin-top:4px}
.pfoot{grid-column:2/4;display:flex;flex-wrap:wrap;gap:4px 14px;align-items:center;margin-top:8px;font-size:12.5px}
.plink{color:var(--info);text-decoration:none;font-weight:650}.plink:hover{text-decoration:underline}
.watch{margin-top:26px}.watch h3{font-size:15px;margin:0 0 2px}.watch>p{margin:0 0 10px;color:var(--muted);font-size:12.5px}
.wrow{display:grid;grid-template-columns:1fr auto;gap:2px 14px;align-items:center;padding:10px 14px;background:var(--surface);
border:1px solid var(--line);border-radius:10px;margin:0 0 6px;font-size:13.5px}
.wrow .wt{font-weight:700}.wrow .wtgt{text-align:right;font-weight:750;white-space:nowrap}.wsub{color:var(--muted);font-size:12px}
.wtgt .pos,.pov.pos,.edge.pos{color:var(--pos)}.wtgt .neg,.pov.neg,.edge.neg{color:var(--neg)}
details.howgrade,details.about{margin:22px 0 0;background:var(--surface);border:1px solid var(--line);border-radius:var(--r);padding:2px 16px}
details.howgrade summary,details.about summary{cursor:pointer;font-weight:650;padding:10px 0;font-size:14px}
details.howgrade p,details.about ul{color:var(--muted);font-size:13px;margin:0 0 12px}details.about li{margin:5px 0}

/* research columns + cards */
.cols{display:grid;grid-template-columns:1fr;gap:18px}
@media(min-width:1000px){.cols{grid-template-columns:repeat(3,1fr);align-items:start}}
.col h2{font-size:12px;font-weight:750;text-transform:uppercase;letter-spacing:.07em;color:var(--muted);margin:0 0 8px;padding:0 2px}
.chipnav{display:flex;gap:8px;margin:2px 0 12px}@media(min-width:1000px){.chipnav{display:none}}
.chipnav a{padding:5px 12px;border:1px solid var(--line);border-radius:999px;color:var(--text);text-decoration:none;font-weight:650;
background:var(--surface);font-size:13px}
.filter{display:inline-flex;align-items:center;gap:8px;font-size:13px;color:var(--muted);cursor:pointer;user-select:none;margin:0 0 12px}
.filter input{accent-color:var(--pos);width:16px;height:16px}
.weakonly #p1 .card[data-weak="0"]{display:none}
.card{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);padding:12px 14px;margin:0 0 10px}
.card.priced{opacity:.62}
.top{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}
.name{font-weight:700;font-size:15.5px}.tm{color:var(--muted);font-weight:650;font-size:12px;margin-left:6px}
.proj{text-align:right;line-height:1}.proj b{font-size:24px;font-weight:800}
.proj small{display:block;color:var(--faint);font-size:10.5px;margin-top:3px;text-transform:uppercase;letter-spacing:.04em}
.game{color:var(--muted);font-size:12.5px;margin:2px 0 8px}
.chips{display:flex;flex-wrap:wrap;gap:5px;margin:0 0 8px}
.chip{font-size:11.5px;font-weight:650;padding:2px 8px;border-radius:6px;background:var(--surface-2);color:var(--muted);border:1px solid var(--line)}
.chip.weak{color:var(--pos);background:var(--pos-bg);border-color:transparent}
.chip.strong,.chip.out{color:var(--neg);background:var(--neg-bg);border-color:transparent}
.chip.q{color:var(--warn);background:var(--warn-bg);border-color:transparent}
.chip.toppick{color:#052e14;background:var(--pos);border-color:transparent}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin:0 0 8px}
.stats div{background:var(--surface-2);border-radius:8px;padding:5px 8px}
.stats dt{font-size:10px;color:var(--faint);text-transform:uppercase;letter-spacing:.05em}.stats dd{margin:0;font-weight:700;font-size:13px}
.starter{font-size:12.5px;margin:0 0 8px;color:var(--text)}.starter span{color:var(--muted)}
.tcap{font-size:10.5px;color:var(--faint);margin:4px 0 4px;text-transform:uppercase;letter-spacing:.05em}
.tnote{font-size:12px;color:var(--muted);margin:0 0 8px}
details.more>summary,details.logbox>summary{cursor:pointer;font-size:12.5px;font-weight:650;color:var(--info);padding:4px 0}
details.more{margin:0 0 4px}
.linebox{display:flex;flex-wrap:wrap;align-items:center;gap:6px 10px;font-size:12.5px;color:var(--muted);border-top:1px solid var(--line);
padding-top:9px;margin-top:6px}
.line{display:flex;align-items:center;gap:8px}
.linebox input,.tdbox input,.logrow input{width:96px;font:inherit;font-weight:650;padding:6px 8px;border:1px solid var(--line-2);border-radius:8px;
background:var(--surface-2);color:var(--text)}
input::placeholder{color:var(--faint);font-weight:400}
input:focus,button:focus-visible,summary:focus-visible{outline:2px solid var(--info);outline-offset:1px}
.dk{color:var(--faint);font-size:11.5px;font-weight:650}
.pov{font-weight:650;color:var(--muted)}
.edge{font-weight:700}
.empty{color:var(--muted);padding:14px;border:1px dashed var(--line-2);border-radius:var(--r);font-size:13.5px;background:var(--surface)}
.flash{animation:flash 1.8s ease}@keyframes flash{0%,40%{box-shadow:0 0 0 2px var(--pos)}100%{box-shadow:0 0 0 0 transparent}}

/* anytime TD rows */
.tdwk{font-size:11px;font-weight:750;color:var(--faint);margin:12px 0 6px;text-transform:uppercase;letter-spacing:.07em}
.tdrow{display:grid;grid-template-columns:2em 1fr auto;gap:4px 10px;align-items:center;background:var(--surface);border:1px solid var(--line);
border-radius:10px;padding:8px 10px;margin:0 0 6px}
.tdrow .rk{color:var(--faint);font-weight:700;text-align:right}.tdrow .nm{font-weight:700}.tdrow .gm{color:var(--muted);font-size:12px}
.tdrow .pt{text-align:right;line-height:1.05}.tdrow .pt b{font-size:20px}.tdrow .pt small{display:block;color:var(--faint);font-size:11px;margin-top:2px}
.tdrow .tdbox{grid-column:2/4;display:flex;flex-wrap:wrap;align-items:center;gap:4px 10px;font-size:12px;color:var(--muted)}
.tdrow .chip{margin-left:6px}

/* bet log */
details.logbox{margin-top:8px;border-top:1px solid var(--line);padding-top:6px}
.logrow{display:flex;flex-wrap:wrap;gap:8px;align-items:flex-end;margin-top:6px}
.logrow label{display:flex;flex-direction:column;font-size:11px;color:var(--muted);gap:2px}
.logrow input{width:74px}
.seg{display:flex}.seg button{font:inherit;font-weight:650;padding:7px 12px;border:1px solid var(--line-2);background:var(--surface-2);color:var(--text);cursor:pointer}
.seg button:first-child{border-radius:8px 0 0 8px}.seg button:last-child{border-radius:0 8px 8px 0;border-left:0}
.seg button[aria-pressed=true]{background:var(--pos);color:#052e14;border-color:var(--pos)}
.btn,.logbtn,.btools button,.del{font:inherit;font-weight:650;padding:7px 12px;border-radius:8px;border:1px solid var(--line-2);background:var(--surface-2);color:var(--text);cursor:pointer}
.logbtn{background:var(--pos);border-color:var(--pos);color:#052e14}
.logmsg{font-size:12px;margin-top:6px;color:var(--muted);min-height:1em}
.sum{display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:8px;margin:0 0 12px}
.sum div{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:8px 10px}
.sum dt{font-size:10.5px;color:var(--faint);text-transform:uppercase;letter-spacing:.05em}.sum dd{margin:0;font-weight:750;font-size:17px}
.sum .pos{color:var(--pos)}.sum .neg{color:var(--neg)}
.bet{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);padding:10px 12px;margin:0 0 8px;display:grid;gap:3px}
.bet .row1{display:flex;gap:8px;align-items:center;flex-wrap:wrap;font-weight:650}
.badge{font-size:11px;font-weight:750;padding:2px 8px;border-radius:999px;background:var(--surface-2);border:1px solid var(--line);text-transform:uppercase}
.badge.win{background:var(--pos-bg);color:var(--pos);border-color:transparent}.badge.loss{background:var(--neg-bg);color:var(--neg);border-color:transparent}
.badge.void,.badge.push{background:var(--warn-bg);color:var(--warn);border-color:transparent}
.bet .small,.small{font-size:12px;color:var(--muted)}
.mcheck{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);padding:10px 12px;margin:0 0 12px}.mcheck h3{margin:0 0 4px;font-size:15px}
.mcheck table{border-collapse:collapse;font-size:13px;margin:6px 0;width:100%}
.mcheck th,.mcheck td{text-align:left;padding:3px 8px 3px 0;border-bottom:1px solid var(--line)}.mcheck th{color:var(--muted);font-weight:600;font-size:12px}
.btools{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0 0}
.warnbox{background:var(--neg-bg);color:var(--neg);border-radius:8px;padding:8px 12px;font-size:13px;margin:0 0 12px}
footer{color:var(--faint);font-size:12px;margin:18px 0 8px}footer a{color:var(--muted)}
[hidden]{display:none!important}
"""

JS = r"""
(function(){
'use strict';
var $=function(s,r){return (r||document).querySelector(s)};
var $$=function(s,r){return Array.prototype.slice.call((r||document).querySelectorAll(s))};
var META=JSON.parse($('#meta').textContent), CAL=null;
try{CAL=JSON.parse($('#calib').textContent)}catch(e){}
var KEY='nflprops.bets.v1', LEAN_HI=0.55, LEAN_LO=0.45, memBets=[], storageOK=true;
var CATNAME={QB:'QB passing',RB:'RB rushing',WR:'WR receiving'};

function readBets(){try{var v=localStorage.getItem(KEY);return v?JSON.parse(v):[]}catch(e){storageOK=false;return memBets}}
function writeBets(a){memBets=a;try{localStorage.setItem(KEY,JSON.stringify(a))}catch(e){storageOK=false}}
function lget(k){try{return localStorage.getItem(k)||''}catch(e){return ''}}
function lset(k,v){try{v===''?localStorage.removeItem(k):localStorage.setItem(k,v)}catch(e){}}
function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]})}
function fmtTime(iso){var d=new Date(iso);return isNaN(d)?'':d.toLocaleString([], {weekday:'short',hour:'numeric',minute:'2-digit'})}
function fmtU(x){return (x>0?'+':'')+x.toFixed(2)+'u'}

/* ---- probability of going Over (mirror of props/calibration.py) ---- */
function cdf(p,r,x){
  var n=r.length;
  if(x<=r[0]) return r[0]>0 ? p[0]*x/r[0] : p[0];
  if(x>=r[n-1]) return p[n-1]+(1-p[n-1])*Math.min(1,(x-r[n-1])/r[n-1]);
  for(var i=0;i<n-1;i++){ if(r[i]<=x && x<r[i+1]) return p[i]+(p[i+1]-p[i])*(x-r[i])/(r[i+1]-r[i]); }
  return p[n-1];
}
function pOver(sheet,cat,proj,line){
  if(sheet!=='elite'||!CAL||!CAL.elite||!CAL.elite[cat]||!(proj>0)||line==null) return null;
  var q=CAL.elite[cat]; return Math.min(0.98,Math.max(0.02,1-cdf(q.p,q.r,line/proj)));
}
function leanOf(p){return p==null?null:(p>=LEAN_HI?'Over':(p<=LEAN_LO?'Under':'Pass'))}
function rangeTxt(snap){var q=CAL&&CAL.backup&&CAL.backup[snap.cat]; if(!q) return ''; return Math.round(q.r[0]*snap.proj)+' to '+Math.round(q.r[q.r.length-1]*snap.proj)}
window.__props={pOver:pOver,cdf:cdf,leanOf:leanOf};

/* ---- tabs ---- */
var tabs=$$('.tab'), panels=$$('.panel'), resPromise=null, RES=undefined;
function show(id){
  tabs.forEach(function(t){t.setAttribute('aria-selected',t.getAttribute('data-p')===id)});
  panels.forEach(function(p){p.hidden=p.id!==id});
  try{history.replaceState(null,'','#'+id)}catch(e){}
  if(id==='p3') renderBets();
}
tabs.forEach(function(t){t.addEventListener('click',function(){show(t.getAttribute('data-p'))})});

/* ---- cards: line -> lean, and the bet logger ---- */
$$('article.card').forEach(function(card){
  var snap=JSON.parse(card.getAttribute('data-snap')), inp=$('.lineinp',card), pov=$('.pov',card), msg=$('.logmsg',card);
  var sk='line:'+[snap.sheet,snap.cat,snap.pid,snap.week].join('|'), side=null;
  function line(){var v=parseFloat(inp.value);return isNaN(v)?null:v}
  function upd(){
    if(snap.sheet==='backup'){
      pov.textContent='No lean for backups: past results were too inconsistent. 80% of past cases landed between '+rangeTxt(snap)+' yds.';
      return;
    }
    var L=line(), p=pOver(snap.sheet,snap.cat,snap.proj,L), ln=leanOf(p);
    if(p==null){pov.textContent='';pov.className='pov';return}
    pov.textContent='Model: '+Math.round(p*100)+'% Over / '+Math.round((1-p)*100)+'% Under · lean '+ln;
    pov.className='pov '+(ln==='Over'?'pos':ln==='Under'?'neg':'');
  }
  inp.value=lget(sk)||(snap.dk_line!=null?String(snap.dk_line):''); upd();      // the book's line, unless you typed one
  inp.addEventListener('input',function(){lset(sk,inp.value);upd()});
  $$('.seg button',card).forEach(function(b){b.addEventListener('click',function(){
    side=b.getAttribute('data-side');
    $$('.seg button',card).forEach(function(o){o.setAttribute('aria-pressed',o===b)});
  })});
  $('.logbtn',card).addEventListener('click',function(){
    var L=line(), odds=parseFloat($('.odds',card).value), stake=parseFloat($('.stake',card).value);
    if(L==null) return void(msg.textContent='Enter the book line first.');
    if(!side) return void(msg.textContent='Pick Over or Under.');
    if(isNaN(odds)||Math.abs(odds)<100) return void(msg.textContent='Odds should look like -110 or +120.');
    if(!(stake>0)) return void(msg.textContent='Units must be more than 0.');
    if(Date.now()>=Date.parse(snap.kickoff)) return void(msg.textContent='This game has started. Bets lock at kickoff.');
    var bets=readBets(), dup=bets.some(function(b){return b.pid===snap.pid&&b.week===snap.week&&b.cat===snap.cat&&b.season===snap.season&&b.side===side&&b.line===L});
    if(dup) return void(msg.textContent='You already logged this exact bet.');
    var p=pOver(snap.sheet,snap.cat,snap.proj,L);
    bets.push({id:Date.now().toString(36)+Math.random().toString(36).slice(2,7), enteredAt:new Date().toISOString(), builtAt:META.built,
      season:snap.season, week:snap.week, team:snap.team, pid:snap.pid, name:snap.name, cat:snap.cat, sheet:snap.sheet, kickoff:snap.kickoff,
      side:side, line:L, odds:odds, stake:stake, pOver:p, lean:leanOf(p), model:snap.model||'v1', snap:snap});
    writeBets(bets); updateCount();
    msg.textContent=storageOK?'Saved. Open the "My bets" tab to see it. Snapshot frozen at '+fmtTime(new Date().toISOString())+'.':'Could not save: your browser is blocking storage.';
  });
});

/* ---- anytime-TD rows: type the book's American price to see the edge over the model's probability ---- */
$$('.tdrow').forEach(function(row){
  var p=parseFloat(row.getAttribute('data-p')), inp=$('.tdodds',row), out=$('.tdedge',row), k='tdodds:'+row.getAttribute('data-k');
  function upd(){
    var o=parseFloat(inp.value);
    if(isNaN(o)||Math.abs(o)<100){out.textContent='';out.className='tdedge pov';return}
    var imp=o>0?100/(o+100):-o/(-o+100), ev=p*(o>0?o/100:100/-o)-(1-p), edge=p-imp;
    out.textContent='Book implies '+Math.round(imp*100)+'% · edge '+(edge>0?'+':'')+(edge*100).toFixed(1)+' pts · EV '+(ev>0?'+':'')+ev.toFixed(2)+'u';
    out.className='tdedge pov '+(edge>0.02?'pos':edge<-0.02?'neg':'');
  }
  inp.value=lget(k)||row.getAttribute('data-dk')||''; upd(); inp.addEventListener('input',function(){lset(k,inp.value);upd()});
});

/* ---- results + grading (results never touch a saved snapshot) ---- */
function loadResults(){
  if(resPromise) return resPromise;
  resPromise=fetch('results.json',{cache:'no-cache'}).then(function(r){if(!r.ok) throw new Error(r.status);return r.json()})
    .then(function(j){j._fin={};j.final.forEach(function(k){j._fin[k]=1});RES=j;return j}).catch(function(){RES=null;return null});
  return resPromise;
}
function toWin(odds,stake){return stake*(odds>0?odds/100:100/Math.abs(odds))}
function grade(b,R){
  if(!R) return {s:'pending',note:'Results file unavailable here.'};
  if(R.season!==b.season||!R._fin[b.season+'|'+b.week+'|'+b.team]) return {s:'pending'};
  var a=R.y[b.season+'|'+b.week+'|'+b.pid+'|'+b.cat];
  if(a===undefined) return {s:'void',profit:0};
  if(a===b.line) return {s:'push',actual:a,profit:0};
  var won=(b.side==='Over')===(a>b.line);
  return {s:won?'win':'loss',actual:a,profit:won?toWin(b.odds,b.stake):-b.stake};
}
window.__props.grade=grade; window.__props.readBets=readBets;

function summarize(rows){
  var st={w:0,l:0,p:0,v:0,pend:0,profit:0,staked:0,err:0,abs:0,n:0,fw:0,fl:0,aw:0,al:0,byCat:{}};
  rows.forEach(function(x){
    var g=x.g, b=x.b;
    if(g.s==='pending'){st.pend++;return}
    if(g.s==='void'){st.v++;return}
    if(g.s==='win')st.w++; else if(g.s==='loss')st.l++; else st.p++;
    st.profit+=g.profit; if(g.s!=='push') st.staked+=b.stake;
    var c=st.byCat[b.cat]||(st.byCat[b.cat]={w:0,l:0,profit:0,err:0,n:0}); 
    if(g.s==='win')c.w++; if(g.s==='loss')c.l++; c.profit+=g.profit;
    if(b.snap&&b.snap.proj>0){var e=g.actual-b.snap.proj; st.err+=e; st.abs+=Math.abs(e); st.n++; c.err+=e; c.n++}
    if(b.lean&&b.lean!=='Pass'&&g.s!=='push'){
      var followed=b.side===b.lean;
      if(followed){g.s==='win'?st.fw++:st.fl++} else {g.s==='win'?st.aw++:st.al++}
    }
  });
  return st;
}
function modelCheck(rows,R){
  var done=rows.filter(function(x){return x.g.actual!==undefined&&x.b.snap&&x.b.snap.proj>0});
  if(done.length<5) return '';
  var cats={}; done.forEach(function(x){var c=cats[x.b.cat]||(cats[x.b.cat]={n:0,s:0}); c.n++; c.s+=x.g.actual/x.b.snap.proj-1});
  var h='<div class="mcheck"><h3>Model check</h3><p class="small">Is the model running high or low on the players you actually bet on? (actual yards vs the frozen projection)</p><table><tr><th>Position</th><th>Bets</th><th>Actual vs projection</th></tr>';
  Object.keys(cats).forEach(function(k){var c=cats[k],m=c.s/c.n;h+='<tr><td>'+CATNAME[k]+'</td><td>'+c.n+'</td><td>'+(m>0?'+':'')+(m*100).toFixed(0)+'%</td></tr>'});
  h+='</table>';
  var tc={}; rows.forEach(function(x){var b=x.b,sn=b.snap||{}; if(!(sn.t_exp>0)||!R||!R.t||x.g.s==='pending'||x.g.s==='void') return;
    var a=R.t[b.season+'|'+b.week+'|'+b.pid+'|'+b.cat]; if(a===undefined) return; var c=tc[b.cat]||(tc[b.cat]={n:0,s:0}); c.n++; c.s+=a/sn.t_exp-1});
  var tk=Object.keys(tc);
  if(tk.length){h+='<p class="small">Touches (attempts / touches / targets) vs the forecast:</p><table><tr><th>Position</th><th>Bets</th><th>Actual vs expected touches</th></tr>';
    tk.forEach(function(k){var c=tc[k],m=c.s/c.n;h+='<tr><td>'+CATNAME[k]+'</td><td>'+c.n+'</td><td>'+(m>0?'+':'')+(m*100).toFixed(0)+'%</td></tr>'});h+='</table>'}
  var cal=done.filter(function(x){return x.b.pOver!=null&&x.g.s!=='push'});
  if(cal.length>=10){
    var B=[[0,.35,'under 35%'],[.35,.45,'35-45%'],[.45,.55,'45-55%'],[.55,.65,'55-65%'],[.65,1.01,'65%+']];
    h+='<p class="small">When the model said a given chance of Over, how often did it happen?</p><table><tr><th>Model P(over)</th><th>Bets</th><th>Said</th><th>Happened</th></tr>';
    B.forEach(function(r){var g=cal.filter(function(x){return x.b.pOver>=r[0]&&x.b.pOver<r[1]});
      if(!g.length) return; var said=g.reduce(function(a,x){return a+x.b.pOver},0)/g.length, hit=g.filter(function(x){return x.g.actual>x.b.line}).length/g.length;
      h+='<tr><td>'+r[2]+'</td><td>'+g.length+'</td><td>'+Math.round(said*100)+'%</td><td>'+Math.round(hit*100)+'%</td></tr>'});
    h+='</table>';
  }
  return h+'<p class="small">Small samples swing wildly. Export your bets and run research/review_bets.py for a version with error bars before changing anything.</p></div>';
}
function tile(label,val,cls){return '<div><dt>'+label+'</dt><dd class="'+(cls||'')+'">'+val+'</dd></div>'}
function renderBets(){
  var box=$('#blist'), sum=$('#bsum');
  loadResults().then(function(R){
    var bets=readBets().slice().sort(function(a,b){return a.enteredAt<b.enteredAt?1:-1});
    $('#bwarn').hidden=storageOK;
    var rows=bets.map(function(b){return {b:b,g:grade(b,R)}});
    var st=summarize(rows), settled=st.w+st.l+st.p;
    var roi=st.staked>0?st.profit/st.staked*100:0;
    var h='<dl class="sum">'+tile('Record (W-L-P)',st.w+'-'+st.l+'-'+st.p)+tile('Units',fmtU(st.profit),st.profit>0?'pos':st.profit<0?'neg':'')+
      tile('ROI',settled?roi.toFixed(1)+'%':'-',roi>0?'pos':roi<0?'neg':'')+tile('Pending / void',st.pend+' / '+st.v);
    if(st.n) h+=tile('Model bias',(st.err/st.n>0?'+':'')+(st.err/st.n).toFixed(0)+' yds')+tile('Model avg miss',(st.abs/st.n).toFixed(0)+' yds');
    var fo=st.fw+st.fl, ag=st.aw+st.al;
    if(fo) h+=tile('Followed lean',st.fw+'-'+st.fl);
    if(ag) h+=tile('Went against lean',st.aw+'-'+st.al);
    h+='</dl>';
    if(settled<30) h+='<p class="small" style="color:var(--mute);font-size:12px">'+settled+' settled bets so far. Anything under about 100 is mostly luck, so treat these numbers as a diary, not a verdict.</p>';
    sum.innerHTML=bets.length?h+modelCheck(rows,R):'';
    if(!bets.length){box.innerHTML='<div class="empty">No bets logged yet. On the other tabs, enter a book line on any card, open "Log a bet", pick a side and save. Bets lock at kickoff.</div>';updateCount();return}
    box.innerHTML=rows.map(function(x){
      var b=x.b,g=x.g,sn=b.snap||{}, locked=Date.now()>=Date.parse(b.kickoff);
      var res=g.s==='pending'?(g.note||'Waiting for results (nflverse posts stats after the games, usually by Tuesday).'):
        g.s==='void'?'No stat line recorded for this player in the final data: treated as void (check your book if he was active).':
        g.actual+' yds vs line '+b.line+' → '+fmtU(g.profit);
      var model=(sn.proj!=null?'proj '+Math.round(sn.proj):'')+(b.pOver!=null?' · P(over) '+Math.round(b.pOver*100)+'% · lean '+b.lean:' · no lean')+
        (sn.opp_rank?' · opp D #'+sn.opp_rank:'')+(sn.inj?' · '+esc(sn.inj):'')+(sn.starters_out?' · out: '+esc(sn.starters_out):'');
      return '<article class="bet"><div class="row1"><span class="badge '+g.s+'">'+g.s+'</span><span>'+esc(b.name)+' ('+esc(b.team)+')</span>'+
        '<span class="small">'+CATNAME[b.cat]+' · wk '+b.week+'</span></div>'+
        '<div>'+esc(b.side)+' '+b.line+' @ '+(b.odds>0?'+':'')+b.odds+' · '+b.stake+'u</div>'+
        '<div class="small">Model when you logged it: '+model+'</div>'+
        '<div class="small">'+res+'</div>'+
        '<div class="small">Logged '+fmtTime(b.enteredAt)+' from data built '+fmtTime(b.builtAt)+' (model '+esc(b.model||'v1')+'); kickoff '+fmtTime(b.kickoff)+
        (locked?' (locked)':'')+'</div>'+
        (locked?'':'<div><button type="button" class="del" data-id="'+esc(b.id)+'">Delete</button></div>')+'</article>';
    }).join('');
    $$('.del',box).forEach(function(btn){btn.addEventListener('click',function(){
      if(btn.getAttribute('data-arm')!=='1'){btn.setAttribute('data-arm','1');btn.textContent='Tap again to delete';return}
      writeBets(readBets().filter(function(b){return b.id!==btn.getAttribute('data-id')}));renderBets();
    })});
    updateCount();
  });
}
function updateCount(){var n=readBets().length;$('#bcount').textContent=n?' ('+n+')':''}

$('#bexp').addEventListener('click',function(){
  var blob=new Blob([JSON.stringify(readBets(),null,1)],{type:'application/json'}), a=document.createElement('a');
  a.href=URL.createObjectURL(blob); a.download='nfl-prop-bets.json'; document.body.appendChild(a); a.click(); a.remove();
});
$('#bimp').addEventListener('change',function(ev){
  var f=ev.target.files[0]; if(!f) return;
  var rd=new FileReader(); rd.onload=function(){
    try{var inc=JSON.parse(rd.result), cur=readBets(), have={}; cur.forEach(function(b){have[b.id]=1});
      inc.forEach(function(b){if(b&&b.id&&b.pid&&b.kickoff&&!have[b.id]) cur.push(b)}); writeBets(cur); renderBets();
    }catch(e){alert('That file is not a bet export from this site.')}
  }; rd.readAsText(f); ev.target.value='';
});

/* ---- Top plays: jump to the full card ---- */
$$('[data-goto]').forEach(function(a){a.addEventListener('click',function(ev){
  ev.preventDefault(); show(a.getAttribute('data-tab'));
  var el=document.getElementById(a.getAttribute('data-goto')); if(!el) return;
  var d=el.closest('details'); if(d) d.open=true;
  el.scrollIntoView({block:'center'}); el.classList.add('flash'); setTimeout(function(){el.classList.remove('flash')},1800);
})});
/* ---- Yardage tab: weak-defense filter, remembered on this device ---- */
var wf=$('#weakonly');
if(wf){wf.checked=lget('weakonly')==='1'; document.body.classList.toggle('weakonly',wf.checked);
  wf.addEventListener('change',function(){document.body.classList.toggle('weakonly',wf.checked);lset('weakonly',wf.checked?'1':'')})}

var h=(location.hash||'').slice(1);
updateCount(); show(document.getElementById(h)&&/^p[0-4]$/.test(h)?h:'p0');
})();
"""


def _n(x, d=0):
    return "" if pd.isna(x) else f"{x:,.{d}f}"


def _opp(row) -> str:
    t = row["opp_txt"]
    return f"at {t[1:]}" if t.startswith("@") else f"vs {t}"


def _et(iso) -> str:
    """'Tue 9:11p' in Eastern time, from an ISO timestamp."""
    if not iso:
        return ""
    t = pd.Timestamp(iso).tz_convert("America/New_York")
    return f"{t.strftime('%a')} {t.hour % 12 or 12}:{t.minute:02d}{'a' if t.hour < 12 else 'p'}"


def _rank_chip(rank, vs_lg) -> str:
    if pd.isna(rank):
        return ""
    rank = int(rank)
    cls = "weak" if rank <= C.WEAK_DEF_N else "strong" if rank >= 33 - C.WEAK_DEF_N else ""
    word = "weak D" if cls == "weak" else "strong D" if cls == "strong" else "D"
    return f'<span class="chip {cls}">Opp {word} #{rank} &middot; {vs_lg:+.0%} vs avg</span>'


def _script_chip(snap) -> str:
    g = snap.get("gs_ctx") or 0
    return f'<span class="chip">Game script {g:+.0%}</span>' if abs(g) >= 0.02 else ""


def _tier_chip(snap) -> str:
    if snap.get("beta") == 0:
        return '<span class="chip">Matchup not predictive at this rank</span>'
    return ""


def _inj_chip(label) -> str:
    if not label:
        return ""
    cls = "out" if label.startswith(("OUT", "DOUBT")) else "q"
    return f'<span class="chip {cls}">{escape(label)}</span>'


def _py(x):
    """JSON-safe plain Python value (numpy scalars, NaN -> None)."""
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return None
    if hasattr(x, "item"):
        x = x.item()
    if isinstance(x, float) and pd.isna(x):
        return None
    return x


def _iso(ts) -> str:
    return pd.Timestamp(ts).tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")


def _r(x, nd):
    """round() that tolerates missing/NaN."""
    return None if x is None or pd.isna(x) else round(float(x), nd)


def _touch_block(snap: dict, cat) -> str:
    """Touches outlook: expected attempts / touches / targets, plus the defense or workload driver."""
    if snap.get("t_exp") is None:
        return ""
    fvol, flag = snap.get("t_fvol"), snap.get("t_flag")
    if cat.key == "QB":
        fourth = ("Opp. faces", f"{(fvol - 1):+.0%} att") if fvol is not None else ("Opp. faces", "-")
    else:
        fourth = ("Teammates out", f"{snap['t_vac']:.0%} of pool") if flag else ("Teammates out", "none")
    note = ""
    if cat.key == "QB" and fvol is not None and abs(fvol - 1) >= 0.03:
        word = "more" if fvol > 1 else "fewer"
        note = (f"The opposing defense faces {abs(fvol - 1):.0%} {word} pass attempts than average. In past seasons QB attempts "
                f"rose and fell with that (included in the expectation).")
    elif flag:
        w = C.TOUCH_WORKLOAD[cat.key]
        extra = f" About {snap['t_if']:.1f} {TOUCH_WORD[cat.key]} if it holds." if snap.get("t_if") else ""
        note = (f"Workload flag: {snap['t_out']}. In {w['n']} similar games (2023-25) {TOUCH_WORD[cat.key]} ran about {w['bump']:+.0%} "
                f"vs baseline.{extra} Shown for information only; it is not in the expected number.")
    return (f'<details class="more"><summary>Touches outlook</summary><div class="tcap">Touches outlook ({TOUCH_NAME[cat.key]})</div>'
            f'<dl class="stats touches"><div><dt>Expected</dt><dd>{snap["t_exp"]:.1f}</dd></div>'
            f'<div><dt>Season avg</dt><dd>{_n(snap["t_cur"], 1)}</dd></div><div><dt>Last 3</dt><dd>{_n(snap["t_l3"], 1)}</dd></div>'
            f'<div><dt>{fourth[0]}</dt><dd>{escape(fourth[1])}</dd></div></dl>'
            + (f'<p class="tnote">{escape(note)}</p>' if note else "") + "</details>")


def _qb_chip(snap: dict) -> str:
    if not snap.get("q_flag"):
        return ""
    cls = "out" if (snap.get("q_p") or 0) >= 0.99 else "q"
    return f'<span class="chip {cls}">QB: {escape(snap["q_txt"])}</span>'


def _qb_note(snap: dict, cat) -> str:
    """QB-out flag: the receiver's starting QB may miss his first game.  Information only, not in the projection."""
    e = C.QB_OUT_EFFECT.get(cat.key)
    if not snap.get("q_flag") or not e:
        return ""
    sits = "is out" if (snap.get("q_p") or 0) >= 0.99 else "sits"
    return (f'<p class="tnote">QB flag: {escape(snap["q_txt"])}. In a starting QB\'s first missed game ({e["n"]} team-games, 2022-25) '
            f'top WRs ran about {e["yards"]:+.0%} in receiving yards and {e["targets"]:+.0%} in targets vs baseline. '
            f'About {snap["q_if"]:.0f} yds if he {sits}. Shown for information only; it is not in the projection.</p>')


def _snap_attr(d: dict) -> str:
    return escape(json.dumps({k: _py(v) for k, v in d.items()}, separators=(",", ":")), quote=True)


LOG_FORM = (
    '<details class="logbox"><summary>Log a bet</summary>'
    '<div class="logrow"><div class="seg" role="group" aria-label="Side">'
    '<button type="button" data-side="Over" aria-pressed="false">Over</button>'
    '<button type="button" data-side="Under" aria-pressed="false">Under</button></div>'
    '<label>Odds<input class="odds" type="text" inputmode="numeric" value="-110"></label>'
    '<label>Units<input class="stake" type="text" inputmode="decimal" value="1"></label>'
    '<button type="button" class="logbtn">Save bet</button></div>'
    '<div class="logmsg" aria-live="polite"></div></details>')


def _book_line(ctx: dict, pid, market: str, kickoff) -> dict:
    """The book's line for a card (pre-fills the line box), as snapshot fields."""
    ln = O.line_for(ctx.get("lines") or {}, pid, market, kickoff)
    if not ln or ln.get("point") is None:
        return dict(dk_line=None, dk_over=None, dk_under=None)
    return dict(dk_line=ln["point"], dk_over=ln.get("over"), dk_under=ln.get("under"))


def _line_box(snap: dict) -> str:
    dk = ""
    if snap.get("dk_line") is not None:
        o, u = snap.get("dk_over"), snap.get("dk_under")
        prices = f" &middot; O {o:+d} / U {u:+d}" if o is not None and u is not None else ""
        dk = f'<span class="dk">{BOOK} {snap["dk_line"]:g}{prices}</span>'
    return ('<div class="linebox"><label class="line">Book line <input class="lineinp" type="text" inputmode="decimal" '
            f'placeholder="enter line" aria-label="Sportsbook line"></label>{dk}<span class="pov"></span></div>')


def _pick_chip(ctx: dict, pid, market: str) -> str:
    p = (ctx.get("picked") or {}).get((pid, market))
    if not p:
        return ""
    bet = f'{p["side"]} {p["line"]:g}' if p.get("line") is not None else p["side"]
    return f'<span class="chip toppick">Top play {p["grade"]} &middot; {escape(bet)}</span>'


def _card_id(kind: str, market: str, pid, week) -> str:
    return escape(f"{kind}-{market}-{pid}-{int(week)}")


def _elite_card(r, cat, ctx) -> str:
    snap = dict(sheet="elite", cat=cat.key, pid=r["player_id"], name=r["name"], team=r["team"], opp=r["opp_txt"],
                week=int(r["week"]), season=ctx["season"], kickoff=_iso(r["kickoff"]), proj=round(float(r["proj"]), 2),
                opp_rank=int(r["opp_rank"]), opp_vs_lg=round(float(r["vs_lg"]), 4), inj=r["inj"], rank=int(r["rank"]),
                total=r["total"], ypg=round(float(r["ypg"]), 1), l3=round(float(r["l3"]), 1), games=int(r["games"]),
                spr_tot=r["spr_tot"], model=C.MODEL_VERSION, gs_ctx=round(float(r.get("gs_ctx", 0) or 0), 4),
                beta=round(float(r.get("beta", C.MATCHUP_BETA)), 2), t_label=TOUCH_LABEL[cat.key],
                t_exp=_r(r.get("t_exp"), 2), t_base=_r(r.get("t_base"), 2), t_cur=_r(r.get("t_cur"), 2), t_l3=_r(r.get("t_l3"), 2),
                t_fvol=_r(r.get("t_fvol"), 3), t_vac=_r(r.get("t_vac"), 3), t_flag=bool(r.get("t_flag", False)),
                t_if=_r(r.get("t_if"), 2), t_out=r.get("t_out", "") or "",
                q_flag=bool(r.get("q_flag", False)), q_txt=r.get("q_txt", "") or "", q_p=_r(r.get("q_p"), 3), q_if=_r(r.get("q_if"), 1),
                **_book_line(ctx, r["player_id"], cat.key, r["kickoff"]))
    weak = int(int(r["opp_rank"]) <= ctx.get("weak_n", C.WEAK_DEF_N))
    return (
        f'<article class="card" id="{_card_id("c", cat.key, r["player_id"], r["week"])}" data-weak="{weak}" data-snap="{_snap_attr(snap)}">'
        f'<div class="top"><div><span class="name">{escape(r["name"])}</span><span class="tm">{escape(r["team"])}</span></div>'
        f'<div class="proj"><b>{_n(r["proj"])}</b><small>proj yds</small></div></div>'
        f'<div class="game">{escape(_opp(r))} &middot; {escape(r["kick_txt"])}'
        f'{" &middot; " + escape(r["spr_tot"]) if r["spr_tot"] else ""}</div>'
        f'<div class="chips">{_pick_chip(ctx, r["player_id"], cat.key)}{_rank_chip(r["opp_rank"], r["vs_lg"])}{_script_chip(snap)}'
        f'{_tier_chip(snap)}{_inj_chip(r["inj"])}{_qb_chip(snap)}</div>'
        f'<dl class="stats"><div><dt>Season</dt><dd>{_n(r["total"])} (#{int(r["rank"])})</dd></div>'
        f'<div><dt>Per game</dt><dd>{_n(r["ypg"], 1)}</dd></div><div><dt>Last 3</dt><dd>{_n(r["l3"], 1)}</dd></div>'
        f'<div><dt>Games</dt><dd>{int(r["games"])}</dd></div></dl>'
        f'{_qb_note(snap, cat)}{_touch_block(snap, cat)}{_line_box(snap)}{LOG_FORM}</article>')


def _backup_card(r, cat, ctx) -> str:
    v = cat.vol_short
    priced = r["streak"] >= C.ESTABLISHED_AFTER
    p = r["p_out"]
    snap = dict(sheet="backup", cat=cat.key, pid=r["player_id"], name=r["name"], team=r["team"], opp=r["opp_txt"],
                week=int(r["week"]), season=ctx["season"], kickoff=_iso(r["kickoff"]), proj=round(float(r["proj_exp"]), 2),
                proj_if_out=round(float(r["proj_if_out"]), 2), p_out=round(float(p), 3), starters_out=r["starters_out"],
                role=r["role"], streak=int(r["streak"]), base_vol=round(float(r["base_vol"]), 2),
                proj_vol=round(float(r["proj_vol"]), 2), last_vol=round(float(r["last_vol"]), 1), ypv=round(float(r["ypv"]), 3),
                opp_rank=int(r["opp_rank"]), opp_vs_lg=round(float(r["opp_vs_lg"]), 4), inj=r["inj"], spr_tot=r["spr_tot"],
                model=C.MODEL_VERSION, **_book_line(ctx, r["player_id"], cat.key, r["kickoff"]))
    pchip = (f'<span class="chip out">Starter out</span>' if p >= 0.99
             else f'<span class="chip q">{p:.0%} chance starter is out</span>')
    priced_chip = '<span class="chip">likely priced in</span>' if priced else ""
    return (
        f'<article class="card{" priced" if priced else ""}" id="{_card_id("b", cat.key, r["player_id"], r["week"])}" '
        f'data-snap="{_snap_attr(snap)}">'
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
        f'{_line_box(snap)}{LOG_FORM}</article>')


TD_SHOWN = 25          # rows per position and week shown up front; the rest sit under "Show all"


def _td_row(r, season, lines=None, picked=None) -> str:
    tt = f"team total {r['tt']:.1f}" if pd.notna(r["tt"]) else "no line yet"
    chips = (_pick_chip({"picked": picked}, r["player_id"], "TD") + _inj_chip(r["inj"])
             + ('<span class="chip q">Starter out: role may be bigger</span>' if r["role_up"] else ""))
    ln = O.line_for(lines or {}, r["player_id"], "TD", r.get("kickoff"))
    dk, dk_attr = "", ""
    if ln and ln.get("yes") is not None:
        edge = r["p_td"] - P.implied(ln["yes"])
        dk = (f'<span class="dk">{BOOK} {ln["yes"]:+d}</span>'
              f'<span class="edge {"pos" if edge > 0 else "neg"}">edge {edge * 100:+.1f} pts</span>')
        dk_attr = f' data-dk="{ln["yes"]:+d}"'
    return (f'<article class="tdrow" id="{_card_id("t", "TD", r["player_id"], r["week"])}" data-p="{r["p_td"]:.4f}"{dk_attr} '
            f'data-k="{escape(str(r["player_id"]))}|{int(r["week"])}|{season}">'
            f'<span class="rk">{int(r["rank"])}</span>'
            f'<div><span class="nm">{escape(r["name"])}</span><span class="tm">{escape(r["team"])}</span>{chips}'
            f'<div class="gm">{escape(_opp(r))} &middot; {escape(r["kick_txt"])} &middot; {tt} &middot; {r["xtd"]:.2f} exp TD/G</div></div>'
            f'<div class="pt"><b>{r["p_td"]:.0%}</b><small>fair {escape(r["fair"])}</small></div>'
            f'<div class="tdbox">{dk}<label>Book odds <input class="tdodds" type="text" inputmode="numeric" placeholder="e.g. +120" '
            f'aria-label="Sportsbook odds for an anytime touchdown"></label><span class="tdedge pov"></span></div></article>')


def _td_columns(td: dict, season: int, note: str = "", lines=None, picked=None) -> str:
    out = []
    for k in TD_GROUPS:
        df = td.get(k)
        if df is None or df.empty:
            body = f'<div class="empty">{escape(note) if note else "No players for this slate yet."}</div>'
        else:
            parts = []
            for wk, g in df.groupby("week", sort=True):
                rows = [_td_row(r, season, lines, picked) for _, r in g.iterrows()]
                head = f'<div class="tdwk">Week {int(wk)}</div>'
                rest = (f'<details class="more"><summary>Show all {len(rows)}</summary>{"".join(rows[TD_SHOWN:])}</details>'
                        if len(rows) > TD_SHOWN else "")
                parts.append(head + "".join(rows[:TD_SHOWN]) + rest)
            body = "".join(parts)
        out.append(f'<section class="col {k}" id="t-{k}"><h2>{k} &middot; Anytime TD</h2>{body}</section>')
    return "".join(out)


def _columns(frames: dict, card, ctx: dict) -> str:
    out = []
    for k, cat in C.CATS.items():
        df = frames.get(k)
        title = cat.title.replace(" - ", " &middot; ")
        if df is None or df.empty:
            body = '<div class="empty">No qualifying players for this slate.</div>'
        else:
            body = "".join(card(r, cat, ctx) for _, r in df.iterrows())
        out.append(f'<section class="col {k}" id="{{pfx}}-{k}"><h2>{title}</h2>{body}</section>')
    return "".join(out)


def _chipnav(pfx: str, keys=None) -> str:
    return '<nav class="chipnav">' + "".join(
        f'<a href="#{pfx}-{k}">{k}</a>' for k in (keys or C.CATS)) + "</nav>"


def pool_text(top_n) -> str:
    """'10 QBs, 15 RBs and 25 WRs' (top_n may be a dict per position or a single int)."""
    n = top_n if isinstance(top_n, dict) else {k: top_n for k in C.CATS}
    return f'{n["QB"]} QBs, {n["RB"]} RBs and {n["WR"]} WRs'


# ---- Top plays board -----------------------------------------------------------------------------------------------
def _pick_card(p: dict) -> str:
    side_cls = {"Over": "over", "Under": "under", "Yes": "yes"}.get(p["side"], "")
    bet = f'{p["side"].upper()} {p["line"]:g}' if p.get("line") is not None else p["side"].upper()
    goto, tab = ((_card_id("t", "TD", p["pid"], p["week"]), "p4") if p["kind"] == "td"
                 else (_card_id("c", p["market"], p["pid"], p["week"]), "p1"))
    when = f" &middot; line updated {escape(_et(p['updated']))}" if p.get("updated") else ""
    return (
        f'<article class="pick" data-pick="{escape(str(p["pid"]))}">'
        f'<div class="grade {p["grade"]}" title="Grade {p["grade"]}">{p["grade"]}</div>'
        f'<div><div class="pwho">{escape(p["name"])}<span class="tm">{escape(p["team"])}</span> {_inj_chip(p.get("inj"))}</div>'
        f'<div class="pwhen">{escape(_opp(p))} &middot; {escape(p["kick_txt"])}</div></div>'
        f'<div class="pev">{p["ev"]:+.2f}u<small>EV per 1u</small></div>'
        f'<div class="pbet"><span class="pside {side_cls}">{escape(bet)}</span><span class="pmkt">{escape(p["label"])}</span>'
        f'<span class="pprice">{p["price"]:+d}</span><span class="pbook">{escape(p["book"])}</span></div>'
        f'<div class="pbar"><span class="bar" aria-hidden="true"><i style="width:{p["p"] * 100:.0f}%"></i>'
        f'<u style="left:{p["implied"] * 100:.0f}%"></u></span>'
        f'<span>Model <b>{p["p"]:.0%}</b> &middot; book {p["implied"]:.0%} &middot; <span class="edge">edge {p["edge"] * 100:+.1f} pts</span></span></div>'
        f'<div class="pwhy">{" &middot; ".join(escape(x) for x in p["reasons"])}</div>'
        f'<div class="pfoot"><a class="plink" href="#{goto}" data-goto="{goto}" data-tab="{tab}">Open full card &rsaquo;</a>'
        f'<span class="dk">fair {escape(p["fair"])}{when}</span></div></article>')


def _watch_row(w: dict) -> str:
    reasons = " &middot; ".join(escape(x) for x in w.get("reasons", []))
    if w["kind"] == "yards":
        tg = []
        if w.get("over_at") is not None:
            tg.append(f'<span class="pos">Over &le; {w["over_at"]:g}</span>')
        if w.get("under_at") is not None:
            tg.append(f'<span class="neg">Under &ge; {w["under_at"]:g}</span>')
        right, sub = " &middot; ".join(tg), f'fair line {w["fair_line"]:g} &middot; {reasons}'
    else:
        right = f'<span class="pos">Yes at {w["yes_at"]:+d} or better</span>' if w.get("yes_at") is not None else ""
        sub = f'model {w["p"]:.0%} (fair {escape(w["fair"])}) &middot; {reasons}'
    return (f'<div class="wrow"><div><span class="wt">{escape(w["name"])}</span><span class="tm">{escape(w["team"])}</span> '
            f'<span class="pmkt">{escape(w["label"])}</span><div class="wsub">{escape(_opp(w))} &middot; {escape(w["kick_txt"])} '
            f'&middot; {sub}</div></div><div class="wtgt">{right}</div></div>')


def _board(res) -> str:
    picks, watch, om = getattr(res, "picks", None) or [], getattr(res, "watch", None) or [], res.meta.get("odds") or {}
    n_a = sum(p["grade"] == "A" for p in picks)
    head = (f'<div class="boardhead"><h2>Top plays</h2><span class="count">{len(picks)} play{"s" if len(picks) != 1 else ""}'
            f' &middot; {n_a} A &middot; {len(picks) - n_a} B</span></div>')
    if picks:
        body = "".join(_pick_card(p) for p in picks)
    elif om.get("book_lines"):
        body = (f'<div class="empty">No play clears the bar against the current {BOOK} prices. That is the model declining to '
                f'guess, not a fault: every player is still on the other tabs.</div>')
    else:
        body = (f'<div class="empty">No {BOOK} lines yet. They are pulled on game days (Sunday 7am ET for Sunday\'s games, '
                f'Thursday and Monday mornings for the night games). Until then the watchlist below has the numbers to look for.</div>')
    wl = ""
    if watch:
        wl = (f'<section class="watch"><h3>Watchlist</h3><p>No {BOOK} line for these games yet. Bet only at these numbers or better '
              f'(-110 for yardage); fair = the model\'s 50/50 line or price.</p>{"".join(_watch_row(w) for w in watch)}</section>')
    e = C.PICK_EDGE
    how = (f'<details class="howgrade"><summary>How picks are graded</summary><p>Each pick compares the model\'s chance with the '
           f'chance {BOOK}\'s price implies (vig included), so a positive edge is a positive-EV bet. <b>B</b> needs an edge of '
           f'{e["RB"][1] * 100:.0f} points for RB/WR yards, {e["QB"][1] * 100:.0f} for QB yards and {e["TD"][1] * 100:.1f} for anytime TDs; '
           f'<b>A</b> needs {e["RB"][0] * 100:.0f} / {e["QB"][0] * 100:.0f} / {e["TD"][0] * 100:.0f}. Those sit at about 1x and 1.6x each '
           f'market\'s calibration error, so a B is roughly the smallest edge the model can tell apart from noise. They are assumptions '
           f'until the scorecard has a season of results. No TD pick below a {C.PICK_TD_MIN_P:.0%} chance (longshots magnify small errors), '
           f'at most one pick per player and {C.PICK_PER_GAME} per game, and never an Over on a WR whose QB may miss. Prices move: '
           f'check the number before you bet.</p></details>')
    return f'<div class="board">{head}{body}{wl}{how}</div>'


def render(res, xlsx_name: str | None = XLSX_NAME, fragment: bool = False) -> str:
    """Full HTML page, or (fragment=True) just title + style + body + script for hosts that supply the skeleton."""
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
    dl = f'<a class="dl" href="{xlsx_name}">Download Excel</a>' if xlsx_name else ""
    om = m.get("odds") or {}
    pill = (f'<span class="pill ok">{BOOK} lines &middot; {escape(_et(om["pulled"]))}</span>' if om.get("book_lines") and om.get("pulled")
            else f'<span class="pill warn">No {BOOK} lines yet</span>')
    picked = {(p["pid"], p["market"]): p for p in getattr(res, "picks", None) or []}
    ctx = {"season": res.season, "lines": getattr(res, "lines", None) or {}, "picked": picked,
           "weak_n": m.get("weak_n", C.WEAK_DEF_N)}
    p1 = _columns(getattr(res, "elite_all", None) or res.elite, _elite_card, ctx).replace("{pfx}", "e")
    p2 = _columns(res.backups, _backup_card, ctx).replace("{pfx}", "b")
    p4 = _td_columns(getattr(res, "td", None) or {}, res.season, m.get("td_note", ""), ctx["lines"], picked)
    cal = CAL.load() or {}
    calib_json = json.dumps({"elite": cal.get("elite", {}), "backup": cal.get("backup", {})}, separators=(",", ":"))
    meta_json = json.dumps({"built": _iso(m["generated"]), "season": res.season, "weeks": m["weeks"],
                            "model": m.get("model", C.MODEL_VERSION)})
    def _jsonscript(id_, text):                      # keep "</script>" out of inline JSON
        return f'<script type="application/json" id="{id_}">' + text.replace("</", "<\\/") + "</script>"
    data_scripts = _jsonscript("meta", meta_json) + _jsonscript("calib", calib_json)
    body = f"""<div class="wrap">
<header class="topbar"><div class="brandrow"><div><div class="brand">NFL Prop <span>Model</span></div>
<p class="sub">{res.season} &middot; week{"s" if len(m["weeks"]) > 1 else ""} {escape(wk)} &middot; {m["games"]} games not yet kicked off &middot; stats through week {m["data_through_week"]} &middot; updated {escape(upd)}</p></div>
<div class="hright">{pill}{dl}</div></div>
<nav class="tabs" role="tablist">
<button class="tab" role="tab" data-p="p0" aria-selected="true">Top plays</button>
<button class="tab" role="tab" data-p="p1" aria-selected="false">Yardage</button>
<button class="tab" role="tab" data-p="p2" aria-selected="false">Backups</button>
<button class="tab" role="tab" data-p="p4" aria-selected="false">Anytime TD</button>
<button class="tab" role="tab" data-p="p3" aria-selected="false">My bets<span id="bcount"></span></button></nav></header>
{note_html}
<div class="panel" id="p0">{_board(res)}</div>

<div class="panel" id="p1" hidden>
<p class="lede">The top {pool_text(m["top_n"])} by {res.season} yards, against every defense. <b>Proj</b> is a fair-value anchor; when a {BOOK} line has been pulled it is filled in and the card shows the model's chance of going Over (lean at 55% / 45%). Typical RB and WR games land below the projection, so a line right at it usually leans Under.</p>
<label class="filter"><input type="checkbox" id="weakonly"> Weak defenses only (the {m["weak_n"]} allowing the most yards to the position)</label>
{_chipnav("e")}<div class="cols">{p1}</div></div>

<div class="panel" id="p2" hidden>
<p class="lede">QB2, RB2+ and WR3+ on teams missing a starter who carries real volume. <b>Exp yds</b> is weighted by the chance the starter sits; <b>If out</b> assumes he does. Faded cards: the starter has missed 3+ straight games, so the market has had time to adjust. Backups get no lean.</p>
{_chipnav("b")}<div class="cols">{p2}</div></div>

<div class="panel" id="p4" hidden>
<p class="lede">Chance each RB, WR and TE scores a rushing or receiving touchdown, ranked within each week, <b>if he plays</b> (books void the bet when a player is inactive). <b>Fair</b> is the American price at which the bet breaks even; the {BOOK} price and the edge show when lines have been pulled. Top {TD_SHOWN} per position up front; the Excel has everyone. QBs and fullbacks are not modelled.</p>
{_chipnav("t", TD_GROUPS)}<div class="cols">{p4}</div></div>

<div class="panel" id="p3" hidden>
<p class="lede">Your bet log, kept on <b>this device only</b>. When you save a bet, the page freezes what the model knew right then: projection, matchup, injury status, the line, and when the data was built. Results come later from a separate file and only grade the bet, so they can never rewrite what the model said. Bets lock at kickoff: no adding, no deleting afterward. Stats usually post by Tuesday.</p>
<div class="warnbox" id="bwarn" hidden>Your browser is blocking storage, so bets can't be saved here. Try a normal (non-private) window.</div>
<div id="bsum"></div><div id="blist"></div>
<div class="btools"><button type="button" id="bexp">Export bets</button><label class="btn">Import bets<input type="file" id="bimp" accept="application/json" hidden></label></div>
</div>

<details class="about"><summary>How this works, and how much to trust it</summary><ul>
<li>Top plays compare the model's chance with {BOOK}'s price. Grades are set near each market's calibration error (see "How picks are graded"); they are assumptions until the scorecard has a season of graded picks.</li>
<li>Back-tested on 2023-25: against weak defenses QBs landed about 3% above their baseline and RBs about 10% above; against strong defenses QBs landed about 12% below and RBs 9% below. Receivers showed much less defense effect, especially outside the top 10 WRs.</li>
<li>The Over/Under chances come from how far past outcomes landed from the projection (hold-out checked: within roughly 2-7 points; QBs up to 10). Backups get no lean because those results were too inconsistent.</li>
<li>Anytime TD: back-tested on 2022-25, the model's chances landed within about 3 points of what happened at every probability level. A single game is still mostly luck: even a 60% player misses 4 times in 10.</li>
<li>Single-game yardage is noisy (typical miss: about 75 yds for QBs, 43 for RB/WR), so projections barely beat a plain season average on accuracy; the edge, when there is one, comes from the price.</li>
<li>Late injuries and inactives aren't visible until the next report, so check the news before betting.</li></ul></details>
<footer>For research and entertainment only, not betting advice. Gamble responsibly and only if you are of legal age where you live.
Data: <a href="https://github.com/nflverse/nflverse-data">nflverse</a> and The Odds API. Method, back-tests and code: <a href="{REPO_URL}">GitHub</a>.</footer>
</div>"""
    if fragment:
        return f"<title>NFL Prop Model</title>\n<style>{CSS}</style>\n{body}\n{data_scripts}<script>{JS}</script>"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark"><meta name="theme-color" content="#0f1115">
<link rel="icon" href="data:,">
<title>NFL Prop Model</title>
<meta name="description" content="Top NFL player-prop plays graded against DraftKings prices, plus yardage, backup and anytime-TD research.">
<style>{CSS}</style></head><body>{body}{data_scripts}<script>{JS}</script></body></html>"""


def write_site(res, out_dir: Path, xlsx_path: Path | None = None) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    has_xlsx = xlsx_path is not None and Path(xlsx_path).exists()
    if has_xlsx and Path(xlsx_path).resolve() != (out_dir / XLSX_NAME).resolve():   # may already be in place
        shutil.copyfile(xlsx_path, out_dir / XLSX_NAME)
    (out_dir / "index.html").write_text(render(res, XLSX_NAME if has_xlsx else None), encoding="utf-8")
    (out_dir / "results.json").write_text(json.dumps(res.results or {"season": res.season, "final": [], "y": {}, "t": {}, "td": {}},
                                                       separators=(",", ":")), encoding="utf-8")
    (out_dir / ".nojekyll").write_text("")
    return out_dir / "index.html"
