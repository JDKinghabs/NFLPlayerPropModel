"""Static website: one self-contained index.html (+ the xlsx for download)."""
from __future__ import annotations

import json
import shutil
from html import escape
from pathlib import Path

import pandas as pd

from . import calibration as CAL
from . import config as C
from .td import TD_GROUPS
from .volume import TOUCH_LABEL, TOUCH_NAME, TOUCH_WORD

XLSX_NAME = "NFL_Props_latest.xlsx"
REPO_URL = "https://github.com/JDKinghabs/NFLPlayerPropModel"

CSS = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#14181f;--mute:#5b6573;--line:#e3e7ec;--accent:#1f4e78;
--good:#0b7a3b;--good-bg:#dff3e6;--bad:#b3261e;--bad-bg:#fbe3e1;--weak:#b5541a;--weak-bg:#fde8d8;
--strong:#1f5fa8;--strong-bg:#e1ecf8;--warn-bg:#fff4cf;--qb:#1f4e78;--rb:#2f6b2a;--wr:#8a4b08}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]):not([data-theme=dark]){color-scheme:dark;--bg:#0f1318;--card:#181e26;--ink:#e8ecf1;
--mute:#9aa6b4;--line:#2a323d;--accent:#7fb0e0;--good:#5fd391;--good-bg:#133c26;--bad:#ff8c84;--bad-bg:#4a1d1a;
--weak:#f2a56b;--weak-bg:#4a2d17;--strong:#8dbcf0;--strong-bg:#183049;--warn-bg:#3d3511;--qb:#7fb0e0;--rb:#86d17f;--wr:#f0b36a}}

:root[data-theme=dark]{color-scheme:dark;--bg:#0f1318;--card:#181e26;--ink:#e8ecf1;
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
.col.QB h2{background:#1f4e78}.col.RB h2{background:#2f6b2a}.col.WR h2{background:#8a4b08}.col.TE h2{background:#5b3a8a}
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

.tcap{font-size:11px;color:var(--mute);margin:2px 0 4px;text-transform:uppercase;letter-spacing:.04em}
.stats.touches div{background:var(--strong-bg)}.tnote{font-size:12px;color:var(--mute);margin:0 0 8px}
.linebox{display:flex;flex-wrap:wrap;align-items:center;gap:6px 10px;font-size:13px;color:var(--mute)}
.linebox input{width:104px;font:inherit;font-weight:650;padding:6px 8px;border:1px solid var(--line);border-radius:8px;background:var(--warn-bg);color:var(--ink)}
.pov{font-weight:650;color:var(--mute)}.pov.pos{color:var(--good)}.pov.neg{color:var(--bad)}
details.logbox{margin-top:8px;border-top:1px solid var(--line);padding-top:6px}
details.logbox summary{cursor:pointer;font-size:13px;font-weight:650;color:var(--accent);padding:4px 0}
.logrow{display:flex;flex-wrap:wrap;gap:8px;align-items:flex-end;margin-top:6px}
.logrow label{display:flex;flex-direction:column;font-size:11px;color:var(--mute);gap:2px}
.logrow input{width:74px;font:inherit;padding:6px 8px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--ink)}
.seg{display:flex}.seg button{font:inherit;font-weight:650;padding:7px 12px;border:1px solid var(--line);background:var(--card);color:var(--ink);cursor:pointer}
.seg button:first-child{border-radius:8px 0 0 8px}.seg button:last-child{border-radius:0 8px 8px 0;border-left:0}
.seg button[aria-pressed=true]{background:var(--accent);color:var(--bg);border-color:var(--accent)}
.btn,.logbtn,.btools button{font:inherit;font-weight:650;padding:7px 12px;border-radius:8px;border:1px solid var(--accent);background:var(--card);color:var(--accent);cursor:pointer}
.logbtn{background:var(--accent);color:var(--bg)}
.logmsg{font-size:12px;margin-top:6px;color:var(--mute);min-height:1em}
.sum{display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:8px;margin:0 0 12px}
.sum div{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:8px 10px}
.sum dt{font-size:11px;color:var(--mute)}.sum dd{margin:0;font-weight:700;font-size:17px}
.sum .pos{color:var(--good)}.sum .neg{color:var(--bad)}
.bet{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:10px 12px;margin:0 0 8px;display:grid;gap:3px}
.bet .row1{display:flex;gap:8px;align-items:center;flex-wrap:wrap;font-weight:650}
.badge{font-size:11px;font-weight:700;padding:2px 8px;border-radius:999px;background:var(--bg);border:1px solid var(--line);text-transform:uppercase}
.badge.win{background:var(--good-bg);color:var(--good);border-color:transparent}.badge.loss{background:var(--bad-bg);color:var(--bad);border-color:transparent}
.badge.void,.badge.push{background:var(--warn-bg);border-color:transparent}
.bet .small{font-size:12px;color:var(--mute)}
.mcheck{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:10px 12px;margin:0 0 12px}.mcheck h3{margin:0 0 4px;font-size:15px}
.mcheck table{border-collapse:collapse;font-size:13px;margin:6px 0;width:100%}.mcheck th,.mcheck td{text-align:left;padding:3px 8px 3px 0;border-bottom:1px solid var(--line)}.mcheck th{color:var(--mute);font-weight:600;font-size:12px}
.btools{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0 0}
.warnbox{background:var(--bad-bg);color:var(--bad);border-radius:8px;padding:8px 12px;font-size:13px;margin:0 0 12px}
.tdwk{font-size:13px;font-weight:700;color:var(--mute);margin:12px 0 6px;text-transform:uppercase;letter-spacing:.04em}
.tdrow{display:grid;grid-template-columns:2em 1fr auto;gap:4px 10px;align-items:center;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:8px 10px;margin:0 0 6px}
.tdrow .rk{color:var(--mute);font-weight:700;text-align:right}.tdrow .nm{font-weight:700}
.tdrow .gm{color:var(--mute);font-size:12px}
.tdrow .pt{text-align:right;line-height:1.05}.tdrow .pt b{font-size:22px}.tdrow .pt small{display:block;color:var(--mute);font-size:11px;margin-top:2px}
.tdrow .tdbox{grid-column:2/4;display:flex;flex-wrap:wrap;align-items:center;gap:4px 10px;font-size:12px;color:var(--mute)}
.tdrow .tdbox input::placeholder{color:var(--mute);opacity:.55;font-weight:400}
.tdrow .tdbox input{width:104px;font:inherit;font-weight:650;padding:4px 8px;border:1px solid var(--line);border-radius:8px;background:var(--warn-bg);color:var(--ink)}
details.more summary{cursor:pointer;font-size:13px;font-weight:650;color:var(--accent);padding:6px 0}
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
  inp.value=lget(sk); upd();
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
    out.textContent='Book implies '+Math.round(imp*100)+'% · edge '+(edge>0?'+':'')+(edge*100).toFixed(1)+' pts · EV '+(ev>0?'+':'')+ev.toFixed(2)+'u per 1u';
    out.className='tdedge pov '+(edge>0.02?'pos':edge<-0.02?'neg':'');
  }
  inp.value=lget(k); upd(); inp.addEventListener('input',function(){lset(k,inp.value);upd()});
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

var h=(location.hash||'').slice(1);
updateCount(); show(document.getElementById(h)&&/^p[1234]$/.test(h)?h:'p1');
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
    lab = TOUCH_LABEL[cat.key]
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
    return (f'<div class="tcap">Touches outlook ({TOUCH_NAME[cat.key]})</div>'
            f'<dl class="stats touches"><div><dt>Expected</dt><dd>{snap["t_exp"]:.1f}</dd></div>'
            f'<div><dt>Season avg</dt><dd>{_n(snap["t_cur"], 1)}</dd></div><div><dt>Last 3</dt><dd>{_n(snap["t_l3"], 1)}</dd></div>'
            f'<div><dt>{fourth[0]}</dt><dd>{escape(fourth[1])}</dd></div></dl>'
            + (f'<p class="tnote">{escape(note)}</p>' if note else ""))


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

LINE_BOX = ('<div class="linebox"><label class="line">Book line <input class="lineinp" type="text" '
            'inputmode="decimal" placeholder="enter line" aria-label="Sportsbook line"></label>'
            '<span class="pov"></span></div>')


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
                q_flag=bool(r.get("q_flag", False)), q_txt=r.get("q_txt", "") or "", q_p=_r(r.get("q_p"), 3), q_if=_r(r.get("q_if"), 1))
    return (
        f'<article class="card" data-snap="{_snap_attr(snap)}">'
        f'<div class="top"><div><span class="name">{escape(r["name"])}</span><span class="tm">{escape(r["team"])}</span></div>'
        f'<div class="proj"><b>{_n(r["proj"])}</b><small>proj yds</small></div></div>'
        f'<div class="game">{escape(_opp(r))} &middot; {escape(r["kick_txt"])}'
        f'{" &middot; " + escape(r["spr_tot"]) if r["spr_tot"] else ""}</div>'
        f'<div class="chips">{_rank_chip(r["opp_rank"], r["vs_lg"])}{_script_chip(snap)}{_tier_chip(snap)}{_inj_chip(r["inj"])}{_qb_chip(snap)}</div>'
        f'<dl class="stats"><div><dt>Season</dt><dd>{_n(r["total"])} (#{int(r["rank"])})</dd></div>'
        f'<div><dt>Per game</dt><dd>{_n(r["ypg"], 1)}</dd></div><div><dt>Last 3</dt><dd>{_n(r["l3"], 1)}</dd></div>'
        f'<div><dt>Games</dt><dd>{int(r["games"])}</dd></div></dl>'
        f'{_touch_block(snap, cat)}{_qb_note(snap, cat)}{LINE_BOX}{LOG_FORM}</article>')


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
                model=C.MODEL_VERSION)
    pchip = (f'<span class="chip out">Starter out</span>' if p >= 0.99
             else f'<span class="chip q">{p:.0%} chance starter is out</span>')
    priced_chip = '<span class="chip">likely priced in</span>' if priced else ""
    return (
        f'<article class="card{" priced" if priced else ""}" data-snap="{_snap_attr(snap)}">'
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
        f'{LINE_BOX}{LOG_FORM}</article>')


TD_SHOWN = 25          # rows per position and week shown up front; the rest sit under "Show all"


def _td_row(r, season) -> str:
    tt = f"team total {r['tt']:.1f}" if pd.notna(r["tt"]) else "no line yet"
    chips = _inj_chip(r["inj"]) + ('<span class="chip q">Starter out: role may be bigger</span>' if r["role_up"] else "")
    return (f'<article class="tdrow" data-p="{r["p_td"]:.4f}" data-k="{escape(str(r["player_id"]))}|{int(r["week"])}|{season}">'
            f'<span class="rk">{int(r["rank"])}</span>'
            f'<div><span class="nm">{escape(r["name"])}</span><span class="tm">{escape(r["team"])}</span>{chips}'
            f'<div class="gm">{escape(_opp(r))} &middot; {escape(r["kick_txt"])} &middot; {tt} &middot; {r["xtd"]:.2f} exp TD/G</div></div>'
            f'<div class="pt"><b>{r["p_td"]:.0%}</b><small>fair {escape(r["fair"])}</small></div>'
            f'<div class="tdbox"><label>Book odds <input class="tdodds" type="text" inputmode="numeric" placeholder="e.g. +120" '
            f'aria-label="Sportsbook odds for an anytime touchdown"></label><span class="tdedge pov"></span></div></article>')


def _td_columns(td: dict, season: int, note: str = "") -> str:
    out = []
    for k in TD_GROUPS:
        df = td.get(k)
        if df is None or df.empty:
            body = f'<div class="empty">{escape(note) if note else "No players for this slate yet."}</div>'
        else:
            parts = []
            for wk, g in df.groupby("week", sort=True):
                rows = [_td_row(r, season) for _, r in g.iterrows()]
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
    dl = f' &middot; <a href="{xlsx_name}">Download Excel</a>' if xlsx_name else ""
    ctx = {"season": res.season}
    p1 = _columns(res.elite, _elite_card, ctx).replace("{pfx}", "e")
    p2 = _columns(res.backups, _backup_card, ctx).replace("{pfx}", "b")
    p4 = _td_columns(getattr(res, "td", None) or {}, res.season, m.get("td_note", ""))
    cal = CAL.load() or {}
    calib_json = json.dumps({"elite": cal.get("elite", {}), "backup": cal.get("backup", {})}, separators=(",", ":"))
    meta_json = json.dumps({"built": _iso(m["generated"]), "season": res.season, "weeks": m["weeks"],
                            "model": m.get("model", C.MODEL_VERSION)})
    def _jsonscript(id_, text):                      # keep "</script>" out of inline JSON
        return f'<script type="application/json" id="{id_}">' + text.replace("</", "<\\/") + "</script>"
    data_scripts = _jsonscript("meta", meta_json) + _jsonscript("calib", calib_json)
    body = f"""<div class="wrap">
<h1>NFL Prop Model</h1>
<p class="sub">{res.season} season &middot; week{"s" if len(m["weeks"]) > 1 else ""} {escape(wk)} &middot; {m["games"]} games not yet kicked off &middot; stats through week {m["data_through_week"]} &middot; updated {escape(upd)}{dl}</p>
{note_html}
<div class="tabs" role="tablist">
<button class="tab" role="tab" data-p="p1" aria-selected="true">Elite vs weak D</button>
<button class="tab" role="tab" data-p="p2" aria-selected="false">Backups</button>
<button class="tab" role="tab" data-p="p4" aria-selected="false">Anytime TD</button>
<button class="tab" role="tab" data-p="p3" aria-selected="false">My bets<span id="bcount"></span></button></div>

<div class="panel" id="p1">
<p class="lede">The top {pool_text(m["top_n"])} by {res.season} yards, facing one of the {m["weak_n"]} defenses that allow the most yards to that position. <b>Proj</b> is a fair-value anchor, not a prediction. A few huge games pull averages up, so the typical RB or WR game lands below the projection and a line right at the projection usually leans Under. Type the sportsbook line in the box to see the model's chance of going Over (lean Over at 55%+, Under at 45% or less).</p>
{_chipnav("e")}<div class="cols">{p1}</div></div>

<div class="panel" id="p2" hidden>
<p class="lede">QB2, RB2+ and WR3+ on teams missing a starter who carries real volume. <b>Exp yds</b> is weighted by the chance the starter actually sits; <b>If out</b> assumes he does. Faded cards: the starter has already missed 3+ straight games, so the market has had time to adjust.</p>
{_chipnav("b")}<div class="cols">{p2}</div></div>

<div class="panel" id="p4" hidden>
<p class="lede">Chance each RB, WR and TE scores a rushing or receiving touchdown, ranked within each week, <b>if he plays</b> (most books void the bet when a player is inactive). It is built from where his rushes and targets start on the field, how much he is used, and the game's implied scoring. <b>Fair</b> is the American price at which the bet breaks even; type the book's price to see the edge. The top {TD_SHOWN} per position are shown; the Excel download has everyone. QBs are not modelled. A starter being out raises a backup's role, which the model does not know unless the card says so.</p>
{_chipnav("t", TD_GROUPS)}<div class="cols">{p4}</div></div>

<div class="panel" id="p3" hidden>
<p class="lede">Your bet log, kept on <b>this device only</b>. When you save a bet, the page freezes what the model knew right then: projection, matchup, injury status, the line, and when the data was built. Results come later from a separate file and only grade the bet, so they can never rewrite what the model said. Bets lock at kickoff: no adding, no deleting afterward. Stats usually post by Tuesday.</p>
<div class="warnbox" id="bwarn" hidden>Your browser is blocking storage, so bets can't be saved here. Try a normal (non-private) window.</div>
<div id="bsum"></div><div id="blist"></div>
<div class="btools"><button type="button" id="bexp">Export bets</button><label class="btn">Import bets<input type="file" id="bimp" accept="application/json" hidden></label></div>
</div>

<section class="trust"><h3>How much to trust this</h3><ul>
<li>Back-tested on 2023-25: against weak defenses QBs landed about 3% above their baseline and RBs about 10% above; against strong defenses QBs landed about 12% below and RBs 9% below. Receivers showed much less defense effect, especially outside the top 10 WRs. Books price the headline matchups too.</li>
<li>The Over/Under lean for elite players comes from how far past outcomes landed from the projection (hold-out checked: within roughly 2-7 points). Backups get no lean because those past results were too inconsistent.</li>
<li>The matchup edge is applied at full strength for QBs and the top of the RB and WR lists, and less or not at all further down: in past seasons the defense barely predicted how depth receivers (WR 11-25) did, so those cards say so.</li>
<li>Single-game yardage is noisy (typical miss: about 75 yds for QBs, 43 for RB/WR), so projections barely beat a plain season average on accuracy.</li>
<li>Backups: the model gets the size of the extra workload right (QB, RB, WR), is strong for QBs and modest for RBs, and can't reliably say which WR gets the extra targets.</li>
<li>Anytime TD: back-tested on 2022-25, the model's chances landed within about 3 points of what happened at every probability level (RB almost exactly). It beats a player's own TD history for RBs and WRs, modestly for TEs, and a single game is still mostly luck: even a 60% player misses 4 times in 10.</li>
<li>Late injuries and inactives aren't visible until the next report, so check the news before betting.</li>
<li>There are no sportsbook lines in the data. The lean only compares the model to the number you type, and a 55% lean still loses plenty at normal prices.</li></ul></section>
<footer>For research and entertainment only, not betting advice. Gamble responsibly and only if you are of legal age where you live.
Data: <a href="https://github.com/nflverse/nflverse-data">nflverse</a>. Method, back-tests and code: <a href="{REPO_URL}">GitHub</a>.</footer>
</div>"""
    if fragment:
        return f"<title>NFL Prop Model</title>\n<style>{CSS}</style>\n{body}\n{data_scripts}<script>{JS}</script>"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="icon" href="data:,">
<title>NFL Prop Model</title>
<meta name="description" content="QB passing, RB rushing and WR receiving yard research: elite players vs weak defenses, and backups stepping in for injured starters.">
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
