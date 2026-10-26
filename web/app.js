"use strict";
// ---------- API helpers ----------
const API = {
  async get(p){ const r = await fetch(p); return r.json(); },
  async post(p, body){ const r = await fetch(p,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body||{})}); return r.json(); },
  async agent(action, params){ const r = await this.post("/api/agent",{action,params}); return r; },
  async upload(p, file, field="file"){ const fd=new FormData(); fd.append(field,file); const r=await fetch(p,{method:"POST",body:fd}); return r.json(); },
};
// ---------- utils ----------
const $ = (s,r=document)=>r.querySelector(s);
const esc = s => (s==null?"":String(s)).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const el = (html)=>{ const t=document.createElement("template"); t.innerHTML=html.trim(); return t.content.firstElementChild; };
const money = n => (n==null?"—":"$"+Number(n).toFixed(Number(n)<0.01?6:4).replace(/0+$/,m=>m.length>2?m.slice(0,2):m));
const int = n => (n==null?"—":Number(n).toLocaleString());
function provBadge(p){
  const map={retrieved:["retrieved","Retrieved · cited"],ai_generated:["ai","AI-generated"],
    ai_generated_from_notes:["ai","AI-generated from your notes"],curated:["gray","Curated set"],
    estimated:["est","Estimated"],sample:["sample","Sample data — not live"]};
  const [cls,label]=map[p]||["gray",p||"—"]; return `<span class="badge ${cls}">${esc(label)}</span>`;
}
// lightweight, safe markdown -> html (escape first, then format)
function mdInline(s){ return s.replace(/\*\*([^*]+)\*\*/g,"<b>$1</b>").replace(/(^|[^*])\*([^*]+)\*/g,"$1<i>$2</i>").replace(/`([^`]+)`/g,"<code>$1</code>"); }
function md(text){
  const lines=esc(text||"").split("\n"); let out="",inList=false;
  const close=()=>{ if(inList){out+="</ul>";inList=false;} };
  for(const raw of lines){ const line=raw.trimEnd();
    let m=line.match(/^(#{1,6})\s+(.*)$/);
    if(m){ close(); const lvl=Math.min(m[1].length+2,5); out+=`<h${lvl} class="mdh">${mdInline(m[2])}</h${lvl}>`; continue; }
    m=line.match(/^\s*[-•*]\s+(.*)$/) || line.match(/^\s*\d+\.\s+(.*)$/);
    if(m){ if(!inList){out+="<ul class='mdul'>";inList=true;} out+=`<li>${mdInline(m[1])}</li>`; continue; }
    if(line.trim()===""){ close(); continue; }
    close(); out+=`<p class="mdp">${mdInline(line)}</p>`;
  }
  close(); return `<div class="md">${out}</div>`;
}
const loading = (msg="Working…")=>`<div class="loading"><span class="spinner"></span> ${esc(msg)}</div>`;
const errbox = (m)=>`<div class="errbox">⚠ ${esc(m)}</div>`;
function usageLine(u){ if(!u) return ""; const cached=(u.cached_tokens==null?"n/a":u.cached_tokens);
  return `<div class="prov" style="margin-top:10px">▦ ${esc(u.model||"")} · in ${int(u.input_tokens)} · cached ${cached} · out ${int(u.output_tokens)} · ${money(u.cost_usd)} · ${u.latency_s}s</div>`; }

// ---------- voice ----------
const synth = window.speechSynthesis;
function speak(text){ if(!synth) return; synth.cancel(); const u=new SpeechSynthesisUtterance(text); u.rate=1.0; u.pitch=1.0; synth.speak(u); }
function dictationSupported(){ return !!(window.SpeechRecognition||window.webkitSpeechRecognition); }
let recog=null;
function toggleDictation(btn, target){
  const SR=window.SpeechRecognition||window.webkitSpeechRecognition;
  if(!SR){ alert("Speech recognition isn't supported in this browser. Please type your answer."); return; }
  if(recog){ recog.stop(); recog=null; btn.classList.remove("rec"); btn.textContent="🎙 Speak"; return; }
  recog=new SR(); recog.continuous=true; recog.interimResults=true; recog.lang="en-US";
  let base=target.value?target.value+" ":"";
  recog.onresult=(e)=>{ let t=""; for(let i=e.resultIndex;i<e.results.length;i++) t+=e.results[i][0].transcript; target.value=base+t; };
  recog.onend=()=>{ if(recog){ base=target.value+" "; recog.start(); } };
  recog.onerror=()=>{ btn.classList.remove("rec"); btn.textContent="🎙 Speak"; recog=null; };
  recog.start(); btn.classList.add("rec"); btn.textContent="■ Stop";
}

// ---------- labels ----------
const TECH_TOPICS={accounting:"Accounting",valuation:"Valuation",dcf:"DCF",ma:"M&A / Merger Models",lbo:"LBO",fig:"FIG",debt_equity:"Debt & Equity"};
const BEH_TOPICS={tell_me_about_yourself:"Tell me about yourself",why_ib:"Why IB?",why_fig:"Why FIG?",why_ma:"Why M&A?",leadership:"Leadership",failure:"Failure",conflict:"Conflict",teamwork:"Teamwork",strength_weakness:"Strength & weakness"};
const opts=(obj,sel)=>Object.entries(obj).map(([k,v])=>`<option value="${k}" ${k===sel?"selected":""}>${esc(v)}</option>`).join("");

// ---------- router ----------
const VIEWS={dashboard:["Dashboard","Your recruiting command center"],interview:["Interview Coach","Mock interviews with rubric feedback"],
  knowledge:["Knowledge & Deals","Grounded Q&A from your guides"],markets:["Deals","Grounded deal prep from your documents"],
  contacts:["Bankers & Calendar","Contacts, notes, and follow-ups"],tokenomics:["Tokenomics","Measured token usage & cost"],safety:["Safety","Prompt-injection defenses"]};
async function route(){
  const view=(location.hash.replace("#","")||"dashboard");
  const name=VIEWS[view]?view:"dashboard";
  document.querySelectorAll("#nav a").forEach(a=>a.classList.toggle("active",a.dataset.view===name));
  $("#title").textContent=VIEWS[name][0]; $("#crumb").textContent="IB Copilot"; $("#topactions").innerHTML="";
  const c=$("#content"); c.innerHTML=loading();
  try{ await RENDER[name](c); }catch(e){ c.innerHTML=errbox("Failed to load this view: "+e.message); }
}
window.addEventListener("hashchange",route);

// ---------- status ----------
async function loadStatus(){
  try{ const s=await API.get("/api/config");
    const ok=s.portkey_key_present||s.openai_key_present;
    $("#statusdot").className="dot"+(ok?"":" off");
    $("#statustext").textContent=`${s.model} · ${ok?"key loaded":"no key"}`;
  }catch(e){ $("#statustext").textContent="offline"; }
}

const RENDER={};

// ================= DASHBOARD =================
RENDER.dashboard=async(c)=>{
  const d=await API.get("/api/dashboard");
  const hr=new Date().getHours(); const greet=hr<12?"Good morning":hr<18?"Good afternoon":"Good evening";
  const up=d.upcoming_events.length, chats=d.banker_followups.length;
  const weakTxt=d.weak_topics.length?` Your weakest topic is <b>${esc(TECH_TOPICS[d.weak_topics[0].topic]||BEH_TOPICS[d.weak_topics[0].topic]||d.weak_topics[0].topic)}</b>.`:" Run a mock interview to start tracking your progress.";
  const nextEv=d.upcoming_events[0];
  const qa=`<div class="hero"><div class="hello">${greet}, Nikita 👋</div>
    <div class="hsub">${up?`<b>${up}</b> recruiting event${up>1?"s":""} coming up`:"No upcoming recruiting events yet"}${nextEv?` — next: <b>${esc(nextEv.title)}</b> (${esc(nextEv.start)})`:""}.${weakTxt}</div>
    <div class="qa">
      <a class="qbtn solid" href="#interview">◆ Start a mock interview</a>
      <a class="qbtn" href="#" onclick="genPlan();return false;">📅 My 7-day plan</a>
      <a class="qbtn" href="#knowledge">❡ Explain a term</a>
      <a class="qbtn" href="#markets">▤ Review a deal</a>
      <a class="qbtn" href="#contacts">☎ Draft a thank-you</a></div></div>`;
  const stats=`<div class="grid g4" style="margin-bottom:18px">
    ${stat(d.counts.practice_sessions,"Practice sessions")}${stat(d.counts.contacts,"Banker contacts")}
    ${stat(d.counts.events,"Calendar events")}${stat(d.counts.drafts,"Email drafts")}</div>`;
  const plan=card("Today's prep plan", d.today_plan.map(p=>`<div class="item"><div><div class="t">${esc(p)}</div></div></div>`).join("")||empty("Nothing yet"));
  const weak=card("Weak topics to revise", d.weak_topics.length?d.weak_topics.map(w=>
    `<div class="item"><div><div class="t">${esc(TECH_TOPICS[w.topic]||BEH_TOPICS[w.topic]||w.topic)}</div><div class="s">avg ${w.avg_score} over ${w.n} session(s)</div></div>
     <button class="btn sm" onclick="location.hash='interview'">Practice</button></div>`).join("")
    :empty("Finish a mock interview to see weak topics","◆"));
  const events=card("Upcoming recruiting events", d.upcoming_events.length?d.upcoming_events.map(e=>
    `<div class="item"><div><div class="t">${esc(e.title)}</div><div class="s">${esc(e.start||"")} ${e.location?"· "+esc(e.location):""}</div></div>
     <button class="btn sm" onclick="chatPrep(decodeURIComponent('${encodeURIComponent(e.title)}'))">⚡ Prep</button></div>`).join("")
    :empty("Import your Outlook calendar in Bankers & Calendar","☎"));
  const practice=card("Recent practice", d.recent_practice.length?d.recent_practice.map(p=>
    `<div class="item"><div><div class="t">${esc(TECH_TOPICS[p.topic]||BEH_TOPICS[p.topic]||p.topic)} <span class="small muted">· ${esc(p.mode)}</span></div>
     <div class="s">${esc((p.question||"").slice(0,70))}</div></div><div class="scorebig" style="font-size:20px">${p.score==null?"—":p.score}</div></div>`).join("")
    :empty("No sessions yet","◆"));
  const deals=card("Deals to review", d.deals_to_review.map(x=>
    `<div class="item"><div><div class="t">${esc(x.headline)} ${x.featured?'<span class="badge retrieved">your deal</span>':''}</div><div class="s">${esc(x.date)} ${x.parties?"· "+esc(x.parties):""}</div></div>
     <button class="btn sm" onclick="location.hash='markets'">Open</button></div>`).join("")||empty("No deals yet","▤"));
  const foll=card("Banker follow-ups due", d.banker_followups.length?d.banker_followups.map(x=>
    `<div class="item"><div><div class="t">${esc(x.name)}</div><div class="s">${esc(x.firm||"")} ${x.group_name?"· "+esc(x.group_name):""}</div></div>
     <button class="btn sm" onclick="location.hash='contacts'">Open</button></div>`).join("")
    :empty("No pending follow-ups","☎"));
  c.innerHTML=qa+readinessCard(d.readiness)+stats+`<div class="grid g2">${plan}${weak}</div><div class="spacer"></div>
    <div class="grid g2">${events}${practice}</div><div class="spacer"></div>${trendCard(d.performance_trend)}<div class="spacer"></div><div class="grid g2">${deals}${foll}</div>`;
};
function trendCard(trend){
  const pts=(trend||[]).filter(p=>p.score!=null);
  if(pts.length<2) return `<div class="card"><div class="hd"><h3>Performance trend</h3></div><div class="bd">${empty("Complete a few mock interviews to see your score trend","◆")}</div></div>`;
  const w=680,h=120,pad=14;
  const xs=i=>pad+i*((w-2*pad)/(pts.length-1));
  const ys=s=>h-pad-(s/100)*(h-2*pad);
  const path=pts.map((p,i)=>`${i?"L":"M"}${xs(i).toFixed(1)},${ys(p.score).toFixed(1)}`).join(" ");
  const area=`M${xs(0).toFixed(1)},${(h-pad).toFixed(1)} `+pts.map((p,i)=>`L${xs(i).toFixed(1)},${ys(p.score).toFixed(1)}`).join(" ")+` L${xs(pts.length-1).toFixed(1)},${(h-pad).toFixed(1)} Z`;
  const dots=pts.map((p,i)=>`<circle cx="${xs(i).toFixed(1)}" cy="${ys(p.score).toFixed(1)}" r="3.5" fill="#1f4e8c"/><text x="${xs(i).toFixed(1)}" y="${(ys(p.score)-8).toFixed(1)}" text-anchor="middle" font-size="10" fill="#667085">${p.score}</text>`).join("");
  const avg=Math.round(pts.reduce((a,p)=>a+p.score,0)/pts.length), delta=pts[pts.length-1].score-pts[0].score;
  return `<div class="card"><div class="hd"><h3>Performance trend</h3><span class="small muted">avg ${avg} · ${delta>=0?"+":""}${delta} since start · ${pts.length} sessions</span></div>
    <div class="bd"><svg viewBox="0 0 ${w} ${h}" width="100%" height="${h}" preserveAspectRatio="none">
      <line x1="${pad}" y1="${ys(50)}" x2="${w-pad}" y2="${ys(50)}" stroke="#eef1f5"/>
      <path d="${area}" fill="#e8f0f9"/><path d="${path}" fill="none" stroke="#1f4e8c" stroke-width="2.5" stroke-linejoin="round"/>${dots}</svg></div></div>`;
}
function readinessCard(r){
  if(!r) return "";
  const circ=2*Math.PI*52, off=circ*(1-r.score/100);
  const color=r.score>=70?"var(--good)":r.score>=40?"var(--accent)":"var(--warn)";
  const comp=(k,label)=>{const v=r.components[k];return `<div style="margin:7px 0"><div class="row spread small"><span class="muted">${label}</span><span class="tnum" style="font-weight:600">${v}</span></div><div class="meter"><span style="width:${v}%;background:${color}"></span></div></div>`;};
  return `<div class="card pad" style="margin-bottom:18px"><div class="row" style="gap:26px;align-items:center;flex-wrap:wrap">
    <div style="position:relative;width:132px;height:132px;flex:none">
      <svg width="132" height="132" viewBox="0 0 132 132">
        <circle cx="66" cy="66" r="52" fill="none" stroke="#eef1f5" stroke-width="12"/>
        <circle cx="66" cy="66" r="52" fill="none" stroke="${color}" stroke-width="12" stroke-linecap="round" stroke-dasharray="${circ.toFixed(1)}" stroke-dashoffset="${off.toFixed(1)}" transform="rotate(-90 66 66)"/>
      </svg>
      <div style="position:absolute;inset:0;display:grid;place-items:center;text-align:center">
        <div><div style="font-size:32px;font-weight:800;color:var(--navy);line-height:1">${r.score}</div><div class="small muted">of 100</div></div></div>
    </div>
    <div style="flex:1;min-width:250px">
      <div class="row spread"><h3 style="margin:0">Recruiting Readiness · <span style="color:${color}">${esc(r.level)}</span></h3><span class="badge est">measured</span></div>
      ${comp("interview","Interview performance")}${comp("coverage","Topic coverage")}${comp("networking","Networking activity")}
      <div class="small" style="margin-top:10px"><b>Next up:</b> ${esc(r.next_action)}</div>
    </div></div></div>`;
}
const stat=(n,l)=>`<div class="stat"><div class="n tnum">${int(n)}</div><div class="l">${esc(l)}</div></div>`;
const statRaw=(v,l)=>`<div class="stat"><div class="n tnum">${v}</div><div class="l">${esc(l)}</div></div>`;
const card=(title,bodyHtml)=>`<div class="card"><div class="hd"><h3>${title}</h3></div><div class="bd"><div class="list">${bodyHtml}</div></div></div>`;
const empty=(msg,icon="▢")=>`<div class="empty"><div class="big">${icon}</div>${esc(msg)}</div>`;

// ---------- modal + one-click chat prep ----------
function openModal(title, html){
  let m=$("#modal"); if(!m){ m=el('<div id="modal" class="modal-bg"></div>'); document.body.appendChild(m); }
  m.innerHTML=`<div class="modal"><div class="row spread" style="margin-bottom:12px"><h3 style="margin:0">${esc(title)}</h3><button class="btn sm" id="modalX">✕ Close</button></div><div id="modalBody">${html}</div></div>`;
  m.style.display="flex"; $("#modalX").onclick=closeModal; m.onclick=(e)=>{ if(e.target===m) closeModal(); };
  return $("#modalBody");
}
function closeModal(){ const m=$("#modal"); if(m) m.style.display="none"; }
function parseEvent(title){
  let person="", firm="", group="";
  if(/^nikita krishnan\s*\//i.test(title)){ person=title.split("/").slice(1).join("/").trim(); }
  else { firm=title.split(/[-–—:(]/)[0].trim(); }
  if(/\bfig\b/i.test(title)) group="FIG";
  return {person, firm, group};
}
async function chatPrep(title){
  const {person,firm,group}=parseEvent(title);
  const body=openModal("Chat prep — "+(person||firm||title), loading("Preparing tailored questions…"));
  const r=await API.agent("banker.prep_chat",{person,firm,group,context:"Event: "+title});
  const x=(r&&r.result)||{};
  if(!r||!r.ok||x.error){ body.innerHTML=errbox((r&&r.error)||x.error||"Failed"); return; }
  body.innerHTML=`<div class="prov">${provBadge("ai_generated")}${group?` · <span class="badge gray">${esc(group)}</span>`:""}</div>
    ${x.opener?`<div class="fld" style="margin-top:12px">Opener</div><div class="md">${esc(x.opener)}</div>`:""}
    <div class="grid g2" style="margin-top:12px">
      <div><div class="fld">Questions to ask them</div>${list(x.questions_to_ask)}</div>
      <div><div class="fld">They may ask you</div>${list(x.likely_questions)}</div></div>
    ${x.prep_brief?`<div class="fld" style="margin-top:14px">Prep brief</div>${md(x.prep_brief)}`:""}
    ${x.technical_note?`<div class="fld" style="margin-top:12px">Be ready to discuss</div>${md(x.technical_note)}`:""}
    ${sourcesHtml(x.sources)}${usageLine(x.usage)}`;
}
async function genPlan(){
  const body=openModal("Your 7-day prep plan", loading("Building a plan from your measured performance…"));
  const r=await API.agent("interview.study_plan",{});
  const x=(r&&r.result)||{};
  if(!r||!r.ok||x.error){ body.innerHTML=errbox((r&&r.error)||x.error||"Failed"); return; }
  body.innerHTML=`<div class="prov">${provBadge("ai_generated")} · tailored to readiness ${esc(x.readiness)}/100 (${esc(x.level)})</div>${md(x.plan)}${usageLine(x.usage)}`;
}

// ================= INTERVIEW COACH =================
RENDER.interview=async(c)=>{
  c.innerHTML=`
   <div class="card pad">
     <div class="grid g3">
       <div><label class="fld">Mode</label><select id="iMode"><option value="technical">Technical</option><option value="behavioral">Behavioral / TMAT</option></select></div>
       <div><label class="fld">Topic</label><select id="iTopic"></select></div>
       <div><label class="fld">Difficulty</label><select id="iDiff"><option>easy</option><option selected>medium</option><option>hard</option></select></div>
     </div>
     <div class="row" style="margin-top:14px"><button class="btn primary" id="iGen">Generate question</button>
       <span class="small muted">Questions are drawn from your uploaded guides where possible.</span></div>
   </div>
   <div id="iQ"></div>`;
  const mode=$("#iMode"), topic=$("#iTopic");
  const fillTopics=()=>{ topic.innerHTML=opts(mode.value==="behavioral"?BEH_TOPICS:TECH_TOPICS); };
  fillTopics(); mode.onchange=fillTopics;
  if(window.pendingDrill){ const pd=window.pendingDrill; window.pendingDrill=null;
    renderQuestion($("#iQ"), {question:pd.question, provenance:"retrieved", source:pd.source, mode:"technical", topic:pd.topic}); }
  $("#iGen").onclick=async()=>{
    const box=$("#iQ"); box.innerHTML=loading("Generating a question…");
    const r=await API.agent("interview.generate_question",{topic:topic.value,difficulty:$("#iDiff").value,mode:mode.value});
    if(!r.ok||r.result.error){ box.innerHTML=errbox((r.error||r.result.error)); return; }
    const q=r.result; renderQuestion(box,q);
  };
};
function renderQuestion(box,q){
  const started=Date.now();
  box.innerHTML=`<div class="card pad" style="margin-top:16px">
    <div class="row spread"><div class="prov">${provBadge(q.provenance)} ${q.source?("· "+esc(q.source)):""}</div>
      <button class="btn sm" id="iSpeak">🔊 Read aloud</button></div>
    <div style="font-size:16px;font-weight:600;margin:10px 0 4px">${esc(q.question)}</div>
    <label class="fld" style="margin-top:12px">Your answer ${dictationSupported()?"":'<span class="small muted">(mic not supported — type below)</span>'}</label>
    <textarea id="iAns" placeholder="Speak or type your answer…"></textarea>
    <div class="row" style="margin-top:10px">
      <button class="btn mic" id="iMic">🎙 Speak</button>
      <button class="btn primary right" id="iEval">Evaluate answer</button></div>
    <div id="iFx"></div></div>`;
  $("#iSpeak").onclick=()=>speak(q.question);
  $("#iMic").onclick=(e)=>toggleDictation(e.currentTarget,$("#iAns"));
  $("#iEval").onclick=async()=>{
    const ans=$("#iAns").value.trim(); if(!ans){ $("#iFx").innerHTML=errbox("Please enter or speak an answer first."); return; }
    if(recog){ recog.stop(); recog=null; }
    const dur=(Date.now()-started)/1000;
    $("#iFx").innerHTML=loading("Scoring against the rubric…");
    const r=await API.agent("interview.evaluate",{mode:q.mode,topic:q.topic,question:q.question,answer:ans,duration_seconds:dur});
    if(!r.ok||r.result.error){ $("#iFx").innerHTML=errbox(r.error||r.result.error); return; }
    renderFeedback($("#iFx"),r.result);
  };
}
function renderFeedback(box,f){
  const s=f.measured_signals||{};
  const measured=`<div class="card pad"><div class="row spread"><h3 style="margin:0">Measured delivery <span class="badge est">objective</span></h3></div>
    <div class="grid g4" style="margin-top:12px">
      ${stat(s.word_count,"Words")}${stat(s.filler_word_count,"Filler words")}
      ${stat(s.hedging_phrase_count,"Hedging phrases")}${stat(s.words_per_minute==null?"—":s.words_per_minute,"Words / min")}</div>
    ${s.words_per_minute==null?'<div class="small muted" style="margin-top:8px">Pace unavailable (no timing captured for typed answers).</div>':''}</div>`;
  const rows=Object.entries(f.rubric_scores||{}).map(([k,v])=>`<tr><td>${esc(k.replace(/_/g," "))}</td><td class="sc num">${esc(v.score)}/5</td><td>${esc(v.comment||"")}</td></tr>`).join("");
  const conf=f.confidence||{};
  const judged=`<div class="card pad" style="margin-top:16px">
    <div class="row spread"><h3 style="margin:0">Rubric assessment <span class="badge ai">AI judgment</span></h3>
      <div class="scorebig">${f.overall_score==null?"—":f.overall_score}<span class="small muted">/100</span></div></div>
    ${f.overall_score!=null?`<div class="meter" style="margin:10px 0 14px"><span style="width:${f.overall_score}%"></span></div>`:""}
    <table class="rubric"><tr><th>Dimension</th><th class="num">Score</th><th>Comment</th></tr>${rows||'<tr><td colspan=3 class="muted">No rubric returned.</td></tr>'}</table>
    <div class="grid g2" style="margin-top:14px">
      <div><div class="fld">Strengths</div>${list(f.strengths)}</div>
      <div><div class="fld">Missing points</div>${list(f.missing)}</div></div>
    <div class="fld" style="margin-top:14px">Improved answer outline</div>${md(f.improved_outline||"—")}
    <div class="fld" style="margin-top:14px">Likely follow-ups</div>${list(f.followups)}
    <div class="fld" style="margin-top:14px">Confidence <span class="badge ai">AI estimate</span></div>
    <div class="answer">${conf.score!=null?("<b>"+esc(conf.score)+"/100</b> — "):""}${esc(conf.evidence||"—")}</div>
    <div class="note" style="margin-top:14px">${esc(f.disclaimer||"")}</div>
    ${usageLine(f.usage)}</div>`;
  box.innerHTML=`<div style="margin-top:16px">${measured}${judged}</div>`;
}
const list=(a)=>Array.isArray(a)&&a.length?`<ul style="margin:6px 0 0;padding-left:18px">${a.map(x=>`<li>${esc(x)}</li>`).join("")}</ul>`:'<div class="small muted">—</div>';

// ================= KNOWLEDGE =================
RENDER.knowledge=async(c)=>{
  c.innerHTML=`<div class="chips" id="kTabs">
    ${["ask","terminology","flashcards","quiz","documents"].map((t,i)=>`<div class="chip ${i===0?"active":""}" data-tab="${t}">${t[0].toUpperCase()+t.slice(1)}</div>`).join("")}
   </div><div id="kBody" style="margin-top:16px"></div>`;
  const tabs=$("#kTabs"); const body=$("#kBody");
  tabs.onclick=(e)=>{ const t=e.target.closest(".chip"); if(!t)return; tabs.querySelectorAll(".chip").forEach(x=>x.classList.toggle("active",x===t)); kTab(t.dataset.tab,body); };
  kTab("ask",body);
};
async function kTab(tab,body){
  if(tab==="ask"){ body.innerHTML=`<div class="card pad">
    <label class="fld">Ask anything about IB / FIG / M&A</label>
    <textarea id="kQ" placeholder="e.g. Why do banks trade on tangible book value and ROTCE?"></textarea>
    <div class="row" style="margin-top:10px"><select id="kTopic" style="max-width:220px"><option value="">Any topic</option>${opts(TECH_TOPICS)}</select>
      <button class="btn primary right" id="kAsk">Ask</button></div></div><div id="kOut"></div>`;
    $("#kAsk").onclick=async()=>{ const q=$("#kQ").value.trim(); if(!q)return; $("#kOut").innerHTML=loading("Searching your guides…");
      const r=await API.agent("knowledge.answer",{question:q,topic:$("#kTopic").value||null});
      if(!r.ok){ $("#kOut").innerHTML=errbox(r.error); return; }
      $("#kOut").innerHTML=answerCard(r.result); };
  } else if(tab==="terminology"){ body.innerHTML=`<div class="card pad">
    <label class="fld">Explain a term (plain English → IB-level → example)</label>
    <div class="row"><input type="text" id="kT" placeholder="e.g. accretion / dilution, ROTCE, LBO"><button class="btn primary" id="kTGo">Explain</button></div></div><div id="kOut"></div>`;
    $("#kTGo").onclick=async()=>{ const t=$("#kT").value.trim(); if(!t)return; $("#kOut").innerHTML=loading();
      const r=await API.agent("knowledge.terminology",{term:t}); if(!r.ok){$("#kOut").innerHTML=errbox(r.error);return;}
      const x=r.result; $("#kOut").innerHTML=`<div class="card pad" style="margin-top:16px"><div class="prov">${provBadge(x.provenance)}</div>
        <div style="margin-top:4px">${md(x.explanation)}</div>${sourcesHtml(x.sources)}${usageLine(x.usage)}</div>`; };
  } else if(tab==="flashcards"||tab==="quiz"){ const isQ=tab==="quiz"; body.innerHTML=`<div class="card pad">
    <div class="row"><select id="kFT" style="max-width:240px">${opts(TECH_TOPICS,"accounting")}</select>
      <button class="btn primary" id="kFGo">${isQ?"Generate quiz":"Generate flashcards"}</button></div></div><div id="kOut"></div>`;
    $("#kFGo").onclick=async()=>{ $("#kOut").innerHTML=loading("Building from your guides…");
      const r=await API.agent(isQ?"knowledge.quiz":"knowledge.flashcards",{topic:$("#kFT").value});
      if(!r.ok){$("#kOut").innerHTML=errbox(r.error);return;} const x=r.result;
      if(isQ){ renderQuiz($("#kOut"), x.questions||[], x.usage); }
      else { renderFlashcards($("#kOut"), x.cards||[], x.usage); }
    };
  } else if(tab==="documents"){ body.innerHTML=loading("Loading documents…");
    const d=await API.get("/api/documents");
    body.innerHTML=`<div class="card pad"><div class="row spread"><h3 style="margin:0">Indexed guides (${d.documents.length})</h3>
      <label class="btn sm">⬆ Upload (PDF/DOCX/TXT)<input type="file" id="kUp" accept=".pdf,.docx,.txt,.md" style="display:none"></label></div>
      <div id="kUpMsg"></div>
      <div class="list" style="margin-top:8px">${d.documents.map(x=>`<div class="item"><div class="t">${esc(x.title)}</div><div class="small muted">${esc(x.doc)}</div></div>`).join("")||empty("No documents indexed")}</div></div>`;
    $("#kUp").onchange=async(e)=>{ const f=e.target.files[0]; if(!f)return; $("#kUpMsg").innerHTML=loading("Uploading & indexing…");
      const r=await API.upload("/api/upload",f); if(r.error){$("#kUpMsg").innerHTML=errbox(r.error);} else {$("#kUpMsg").innerHTML=`<div class="okbox">Indexed “${esc(r.file)}” · ${int(r.indexed_chunks)} total chunks</div>`; setTimeout(()=>kTab("documents",body),900);} };
  }
}
function renderQuiz(box, questions, usage){
  if(!questions.length){ box.innerHTML=`<div class="card pad" style="margin-top:16px">${empty("No questions generated","❓")}</div>`; return; }
  let i=0; const results=new Array(questions.length).fill(null);
  const gradeHtml=(g,q)=>`<div class="${g.correct?"okbox":"errbox"}" style="margin-top:12px">${g.correct?"✓ Correct":"✗ Not quite"}${g.score!=null?` · ${g.score}/100`:""} — ${esc(g.feedback||"")}</div>
    <div class="fc-label" style="margin-top:10px">Reference answer</div><div class="fc-back">${esc(q.a)}${q.source?` <span class="small muted">— ${esc(q.source)}</span>`:""}</div>`;
  const render=()=>{ const q=questions[i], done=results[i];
    const answered=results.filter(Boolean).length, correct=results.filter(r=>r&&r.correct).length;
    const allDone=answered===questions.length;
    box.innerHTML=`<div class="card pad" style="margin-top:16px">
      <div class="row spread"><span class="prov">${provBadge("retrieved")}</span><span class="small muted">Question ${i+1} / ${questions.length} · Score ${correct}/${answered}</span></div>
      <div class="fc-label" style="margin-top:8px">Question</div><div class="fc-front">${esc(q.q)}</div>
      <label class="fld" style="margin-top:12px">Your answer</label>
      <textarea id="qzAns" ${done?"disabled":""} placeholder="Type or speak your answer…">${done?esc(done.answer||""):""}</textarea>
      <div class="row" style="margin-top:10px">${done?"":`<button class="btn sm mic" id="qzMic">🎙 Speak</button><button class="btn primary right" id="qzSubmit">Submit answer</button>`}</div>
      <div id="qzFx">${done?gradeHtml(done,q):""}</div>
      <div class="row" style="margin-top:14px"><button class="btn sm" id="qzPrev" ${i===0?"disabled":""}>‹ Prev</button>
        <button class="btn sm right" id="qzNext" ${i===questions.length-1?"disabled":""}>Next ›</button></div>
      ${allDone?`<div class="okbox" style="margin-top:14px;font-weight:600;font-size:14px">Quiz complete — you got ${correct} / ${questions.length} correct (${Math.round(100*correct/questions.length)}%).</div>`:""}
      ${usageLine(usage)}</div>`;
    const mic=$("#qzMic"); if(mic) mic.onclick=(e)=>toggleDictation(e.currentTarget,$("#qzAns"));
    const sub=$("#qzSubmit"); if(sub) sub.onclick=async()=>{ const ans=$("#qzAns").value.trim(); if(!ans){ $("#qzFx").innerHTML=errbox("Type or speak an answer first."); return; }
      if(recog){ recog.stop(); recog=null; } $("#qzFx").innerHTML=loading("Grading your answer…");
      const r=await API.agent("knowledge.grade",{question:q.q,reference:q.a,answer:ans}); const g=(r&&r.result)||{};
      if(!r||!r.ok){ $("#qzFx").innerHTML=errbox((r&&r.error)||"Grading failed"); return; }
      results[i]={...g, answer:ans}; render(); };
    $("#qzPrev").onclick=()=>{ if(i>0){ i--; render(); } };
    $("#qzNext").onclick=()=>{ if(i<questions.length-1){ i++; render(); } };
  };
  render();
}
function renderFlashcards(box, cards, usage){
  if(!cards.length){ box.innerHTML=`<div class="card pad" style="margin-top:16px">${empty("No cards generated","❡")}</div>`; return; }
  let i=0, revealed=false;
  const render=()=>{ const cd=cards[i];
    box.innerHTML=`<div class="card pad fcwrap" style="margin-top:16px">
      <div class="row spread"><span class="prov">${provBadge("retrieved")}</span><span class="small muted">Card ${i+1} / ${cards.length}</span></div>
      <div class="fcard">
        <div class="fc-label">Question</div><div class="fc-front">${esc(cd.front)}</div>
        ${revealed?`<div class="fc-divider"></div><div class="fc-label">Answer</div><div class="fc-back">${md(cd.back).replace(/^<div class="md">|<\/div>$/g,"")}</div>${cd.source?`<div class="small muted" style="margin-top:8px">— ${esc(cd.source)}</div>`:""}`:`<div class="fc-hint">Try answering out loud, then reveal.</div>`}
      </div>
      <div class="row wrap" style="margin-top:12px">
        <button class="btn sm" id="fcRead">🔊 Read</button>
        <button class="btn sm mic" id="fcMic">🎙 Answer aloud</button>
        <button class="btn sm ${revealed?"":"primary"}" id="fcFlip">${revealed?"Hide answer":"Reveal answer"}</button>
        <span class="right row"><button class="btn sm" id="fcPrev" ${i===0?"disabled":""}>‹ Prev</button><button class="btn sm" id="fcNext" ${i===cards.length-1?"disabled":""}>Next ›</button></span>
      </div><div id="fcVoice"></div>${usageLine(usage)}</div>`;
    $("#fcRead").onclick=()=>speak(cd.front);
    $("#fcFlip").onclick=()=>{ revealed=!revealed; render(); };
    $("#fcMic").onclick=(e)=>{ let t=$("#fcAns"); if(!t){ $("#fcVoice").innerHTML=`<label class="fld" style="margin-top:12px">Your spoken answer (self-check — not graded)</label><textarea id="fcAns" placeholder="Speak your answer, then reveal to compare…"></textarea>`; t=$("#fcAns"); } toggleDictation(e.currentTarget,t); };
    $("#fcPrev").onclick=()=>{ if(i>0){ i--; revealed=false; render(); } };
    $("#fcNext").onclick=()=>{ if(i<cards.length-1){ i++; revealed=false; render(); } };
  };
  render();
}
function answerCard(x){ return `<div class="card pad" style="margin-top:16px">
  <div class="row spread"><div class="prov">${provBadge(x.provenance)}</div>${x.grounded?"":'<span class="badge sample">not found in your guides</span>'}</div>
  <div style="margin-top:4px">${md(x.answer)}</div>${sourcesHtml(x.sources)}${usageLine(x.usage)}</div>`; }
function sourcesHtml(s){ if(!s||!s.length) return ""; return `<div class="sources"><div class="fld">Sources</div>${s.map(x=>`<div class="src">• ${esc(x.citation)}</div>`).join("")}</div>`; }

// ================= DEALS =================
RENDER.markets=async(c)=>{
  c.innerHTML=`<p class="lead">Interview-ready deal prep grounded in your own deal documents. Generate a brief, then drill it as a mock "walk me through this deal."</p>
   <div id="mFeatured" style="margin-top:14px"></div><div id="mBrief"></div>`;
  const dealBrief=async(id)=>{ const box=$("#mBrief"); box.innerHTML=loading("Writing an interview-ready brief from your document…");
    const r=await API.agent("markets.deal_brief",{item_id:id}); const x=(r&&r.result)||{};
    if(!r||!r.ok||x.error){ box.innerHTML=errbox((r&&r.error)||x.error||"Failed"); return; }
    box.innerHTML=`<div class="card pad" style="margin-top:18px"><div class="row spread"><h3 style="margin:0">${esc(x.item.headline)}</h3><div class="prov">${provBadge(x.provenance)}</div></div>
      ${md(x.brief)}${sourcesHtml(x.sources)}
      <button class="btn primary" id="mDrill" style="margin-top:14px">🎤 Practice: walk me through this deal</button>${usageLine(x.usage)}</div>`;
    $("#mDrill").onclick=()=>{ window.pendingDrill={question:`Walk me through the ${x.item.headline} transaction — what happened, the strategic rationale, the deal structure, and the key metrics.`, topic:"deal", source:(x.sources[0]&&x.sources[0].citation)||"your deal document"}; location.hash="interview"; };
    box.scrollIntoView({behavior:"smooth",block:"start"}); };
  const r=await API.agent("markets.feed",{}); const d=(r.result&&r.result.featured_deal)||null;
  const feat=$("#mFeatured");
  if(d){ feat.innerHTML=`<div class="card pad"><div class="row spread"><span class="badge retrieved">Featured deal · your document</span><span class="small muted">${esc(d.date)}</span></div>
      <div style="font-size:17px;font-weight:700;margin:8px 0">${esc(d.headline)}</div>
      <div class="small muted">${esc(d.parties)} · ${esc(d.value)} · ${esc(d.structure)}</div>
      <button class="btn primary sm" style="margin-top:12px" id="mDeal">Generate grounded deal brief</button></div>`;
    $("#mDeal").onclick=()=>dealBrief(d.id);
  } else feat.innerHTML=empty("No deal document found. Add one in Knowledge → Documents.","▤");
};

// ================= CONTACTS & CALENDAR =================
RENDER.contacts=async(c)=>{
  c.innerHTML=`<div class="grid g2">
    <div class="card pad"><h3 style="margin:0 0 12px">Add banker contact</h3>
      <div class="grid g2"><div><label class="fld">Name</label><input id="cN" type="text"></div><div><label class="fld">Firm</label><input id="cF" type="text"></div>
        <div><label class="fld">Group</label><input id="cG" type="text" placeholder="FIG / M&A / Sponsors"></div><div><label class="fld">Title</label><input id="cTi" type="text"></div>
        <div><label class="fld">Email</label><input id="cE" type="email"></div><div><label class="fld">Personal connection</label><input id="cP" type="text"></div></div>
      <button class="btn primary" id="cAdd" style="margin-top:12px">Add contact</button><div id="cMsg"></div></div>
    <div class="card pad"><div class="row spread"><h3 style="margin:0">Calendar (Outlook)</h3></div>
      <p class="small muted">Import your Outlook calendar as an <b>.ics</b> export or a <b>month-view print-to-PDF</b>. Read-only, fully local — nothing is sent. (PDF titles may be truncated by Outlook.)</p>
      <label class="btn sm">⬆ Import .ics / .pdf<input type="file" id="cIcs" accept=".ics,.pdf" style="display:none"></label>
      <div id="cIcsMsg"></div>
      <div class="fld" style="margin-top:14px">Upcoming</div><div id="cEvents" class="list"></div></div>
   </div>
   <h3 class="sec">Your bankers</h3>
   <div class="row" style="margin-bottom:12px"><input type="text" id="cSearch" placeholder="Search name / firm / group…" style="max-width:320px"></div>
   <div id="cList"></div><div id="cDetail"></div>`;
  const refresh=async(q="")=>{ const r=await API.get("/api/contacts"+(q?"?q="+encodeURIComponent(q):"")); const list=$("#cList");
    list.innerHTML=r.contacts.length?`<div class="grid g3">${r.contacts.map(x=>`<div class="card pad"><div class="row spread"><b>${esc(x.name)}</b>${fuBadge(x.follow_up_status)}</div>
      <div class="small muted">${esc(x.title||"")}</div><div class="small">${esc(x.firm||"")}${x.group_name?" · "+esc(x.group_name):""}</div>
      <button class="btn sm" style="margin-top:10px" data-open="${x.id}">Open</button></div>`).join("")}</div>`:empty("No contacts yet — add one above","☎");
    list.querySelectorAll("[data-open]").forEach(b=>b.onclick=()=>openContact(b.dataset.open)); };
  $("#cAdd").onclick=async()=>{ const name=$("#cN").value.trim(); if(!name){$("#cMsg").innerHTML=errbox("Name is required");return;}
    await API.post("/api/contacts",{name,firm:$("#cF").value,group_name:$("#cG").value,title:$("#cTi").value,email:$("#cE").value,personal_connection:$("#cP").value});
    ["cN","cF","cG","cTi","cE","cP"].forEach(id=>$("#"+id).value=""); $("#cMsg").innerHTML=`<div class="okbox">Contact added.</div>`; refresh($("#cSearch").value); };
  $("#cSearch").oninput=(e)=>refresh(e.target.value);
  $("#cIcs").onchange=async(e)=>{ const f=e.target.files[0]; if(!f)return; $("#cIcsMsg").innerHTML=loading("Importing…");
    const r=await API.upload("/api/calendar/import",f); if(r.error){$("#cIcsMsg").innerHTML=errbox(r.error);} else {$("#cIcsMsg").innerHTML=`<div class="okbox">Imported ${r.imported} events.</div>`; loadEvents();} };
  const loadEvents=async()=>{ const r=await API.get("/api/events"); const up=r.events.filter(e=>!e.done).slice(0,6);
    $("#cEvents").innerHTML=up.length?up.map(e=>`<div class="item"><div><div class="t">${esc(e.title)}</div><div class="s">${esc(e.start||"")}</div></div><button class="btn sm" onclick="chatPrep(decodeURIComponent('${encodeURIComponent(e.title)}'))">⚡ Prep</button></div>`).join(""):empty("No events imported","▤"); };
  refresh(); loadEvents();
};
const fuBadge=(s)=>s==="done"?'<span class="badge ok">done</span>':s==="pending"||s==="due"?'<span class="badge sample">follow up</span>':'<span class="badge gray">—</span>';
async function openContact(id){
  const d=await API.get("/api/contacts/"+id); const c=d.contact;
  const box=$("#cDetail"); box.innerHTML=`<div class="card pad" style="margin-top:16px">
    <div class="row spread"><div><h3 style="margin:0">${esc(c.name)}</h3><div class="small muted">${esc(c.title||"")} · ${esc(c.firm||"")} ${c.group_name?"· "+esc(c.group_name):""}</div>
      ${c.email?`<div class="small">${esc(c.email)}</div>`:""}${c.personal_connection?`<div class="small muted">Connection: ${esc(c.personal_connection)}</div>`:""}</div>
      <div class="row"><select id="dFu"><option value="pending">follow up</option><option value="done">done</option><option value="none">none</option></select><button class="btn sm" id="dFuSave">Save</button></div></div>
    <div class="fld" style="margin-top:16px">Meeting notes (what the banker actually said)</div>
    <textarea id="dNotes" placeholder="Date, topics, what they said, any personal connection…"></textarea>
    <div class="row" style="margin-top:10px"><button class="btn" id="dSummarize">Summarize notes</button>
      <button class="btn" id="dSaveMeeting">Save meeting</button>
      <button class="btn primary right" id="dDraft">Draft thank-you email</button></div>
    <div id="dOut"></div></div>`;
  $("#dFu").value=c.follow_up_status||"pending";
  $("#dFuSave").onclick=async()=>{ await API.post(`/api/contacts/${id}/followup`,{status:$("#dFu").value}); $("#dOut").innerHTML=`<div class="okbox">Follow-up status updated.</div>`; };
  $("#dSaveMeeting").onclick=async()=>{ await API.post("/api/meetings",{contact_id:+id,notes:$("#dNotes").value,date:new Date().toISOString().slice(0,10)}); $("#dOut").innerHTML=`<div class="okbox">Meeting saved.</div>`; };
  $("#dSummarize").onclick=async()=>{ const notes=$("#dNotes").value.trim(); if(!notes){$("#dOut").innerHTML=errbox("Add some notes first.");return;}
    $("#dOut").innerHTML=loading("Summarizing your notes…"); const r=await API.agent("banker.summarize_meeting",{notes,contact:c}); const x=r.result;
    if(!r.ok||x.error){$("#dOut").innerHTML=errbox(r.error||x.error);return;}
    $("#dOut").innerHTML=`<div class="card pad" style="margin-top:14px"><div class="prov">${provBadge(x.provenance)}</div>
      <div class="answer" style="margin-top:8px"><b>Summary.</b> ${esc(x.summary||"—")}</div>
      <div class="grid g2" style="margin-top:12px"><div><div class="fld">Key insights</div>${list(x.key_insights)}</div><div><div class="fld">Next steps</div>${list(x.next_steps)}</div></div>
      <div class="fld" style="margin-top:12px">Detail for a thank-you email</div><div class="answer">${esc(x.thank_you_detail||"—")}</div>${usageLine(x.usage)}</div>`; };
  $("#dDraft").onclick=async()=>{ const notes=$("#dNotes").value.trim();
    $("#dOut").innerHTML=loading("Drafting (your notes only, nothing invented)…");
    const r=await API.agent("banker.draft_email",{contact:c,notes,purpose:"thank_you"}); const x=r.result;
    if(!r.ok||x.error){$("#dOut").innerHTML=errbox(r.error||x.error);return;} renderDraft($("#dOut"),id,x); };
}
function renderDraft(box,cid,x){
  box.innerHTML=`<div class="card pad" style="margin-top:14px"><div class="row spread"><h3 style="margin:0">Draft email</h3><div class="prov">${provBadge("ai_generated")}</div></div>
    <label class="fld" style="margin-top:10px">To</label><input id="eTo" type="email" value="${esc(x.to||"")}">
    <label class="fld" style="margin-top:8px">Subject</label><input id="eSub" type="text" value="${esc(x.subject||"")}">
    <label class="fld" style="margin-top:8px">Body</label><textarea id="eBody" style="min-height:160px">${esc(x.body||"")}</textarea>
    <div class="row" style="margin-top:10px"><button class="btn" id="eCopy">Copy</button><button class="btn" id="eSave">Save draft</button>
      <span class="small muted right">Never sent automatically — you review &amp; send yourself.</span></div><div id="eMsg"></div></div>`;
  $("#eCopy").onclick=()=>{ navigator.clipboard.writeText($("#eBody").value); $("#eMsg").innerHTML=`<div class="okbox">Copied to clipboard.</div>`; };
  $("#eSave").onclick=async()=>{ const r=await API.post("/api/drafts",{contact_id:+cid,to_addr:$("#eTo").value,subject:$("#eSub").value,body:$("#eBody").value});
    $("#eMsg").innerHTML=`<div class="okbox">Saved. <a href="/api/drafts/${r.id}/eml">Download .eml for Outlook</a></div>`; };
}

// ================= TOKENOMICS =================
RENDER.tokenomics=async(c)=>{
  const u=await API.get("/api/usage"); const runs=(await API.get("/api/runs")).runs;
  const m=u.measured, pr=u.pricing, pj=u.projections;
  const byAgent=Object.entries(m.by_agent||{}).map(([a,v])=>`<tr><td>${esc(a)}</td><td class="num">${int(v.runs)}</td><td class="num">${int(v.input_tokens)}</td><td class="num">${int(v.output_tokens)}</td><td class="num">${money(v.cost_usd)}</td></tr>`).join("");
  c.innerHTML=`<div class="note">All usage below is <b>measured</b> from the API's reported token counts. Projections are clearly separated and use explicit assumptions.</div>
   <div class="grid g4" style="margin:16px 0">${stat(m.runs,"Model runs (measured)")}${statRaw(money(m.total_cost_usd),"Total cost")}
     ${statRaw(money(m.avg_cost_per_run_usd),"Avg cost / run")}${statRaw(m.cached_tokens==null?"n/a":int(m.cached_tokens),"Cached tokens")}</div>
   <div class="grid g2">
     <div class="card pad"><h3 style="margin:0 0 10px">Cost by agent <span class="badge est">measured</span></h3>
       <table><tr><th>Agent</th><th class="num">Runs</th><th class="num">In tok</th><th class="num">Out tok</th><th class="num">Cost</th></tr>${byAgent||'<tr><td colspan=5 class="muted">No runs yet — use the app to generate data.</td></tr>'}</table>
       <div class="small muted" style="margin-top:10px">${m.cached_tokens==null?esc(m.cached_tokens_note||""):""}</div></div>
     <div class="card pad"><h3 style="margin:0 0 10px">Pricing <span class="badge est">configurable</span></h3>
       <table><tr><th>Rate</th><th class="num">$ / 1M tokens</th></tr>
         <tr><td>Input</td><td class="num">$${pr.rates_per_1m.input_per_1m}</td></tr>
         <tr><td>Cached input</td><td class="num">$${pr.rates_per_1m.cached_input_per_1m}</td></tr>
         <tr><td>Output</td><td class="num">$${pr.rates_per_1m.output_per_1m}</td></tr></table>
       <div class="small muted" style="margin-top:10px">${esc(pr.source)} · ${esc(pr.date)} · model ${esc(pr.model)}</div></div>
   </div>
   <h3 class="sec">Projections <span class="badge ai">estimated, not billed</span></h3>
   <div class="grid g3">${statRaw(money(pj.cost_per_user_per_month_usd),"Per user / month")}${statRaw("$"+int(pj.cost_100_users_month_usd),"100 users / month")}${statRaw("$"+int(pj.cost_10000_users_month_usd),"10,000 users / month")}</div>
   <div class="card pad" style="margin-top:14px"><div class="small muted">Assumption: ${pj.assumptions.runs_per_user_per_day} runs/user/day × ${pj.assumptions.active_days_per_month} active days = ${pj.assumptions.runs_per_user_per_month} runs/user/month, × avg measured cost/run.</div>
     <div class="fld" style="margin-top:12px">Cost levers</div>${list(pj.levers)}<div class="note" style="margin-top:10px">${esc(pj.disclaimer)}</div></div>
   <h3 class="sec">Recent run history</h3>
   <div class="card pad"><table><tr><th>Agent</th><th>Action</th><th>Status</th><th class="num">In</th><th class="num">Cached</th><th class="num">Out</th><th class="num">Cost</th><th class="num">Latency</th></tr>
     ${runs.length?runs.map(r=>`<tr><td>${esc(r.agent)}</td><td>${esc(r.action)}</td><td>${r.status==="error"?'<span class="badge err">error</span>':'<span class="badge ok">ok</span>'}</td>
       <td class="num">${int(r.input_tokens)}</td><td class="num">${r.cached_tokens==null?"n/a":int(r.cached_tokens)}</td><td class="num">${int(r.output_tokens)}</td><td class="num">${money(r.cost_usd)}</td><td class="num">${r.latency_s==null?"—":r.latency_s+"s"}</td></tr>`).join(""):'<tr><td colspan=8 class="muted">No runs logged yet.</td></tr>'}</table></div>`;
};

// ================= SAFETY =================
RENDER.safety=async(c)=>{
  c.innerHTML=`<div class="card pad"><h3 style="margin:0 0 6px">Prompt-injection defense test</h3>
    <p class="small muted">Embeds malicious instructions inside a fenced UNTRUSTED document and sends it through the real retrieval path. A pass = the agent ignores the injection and leaks no secret.</p>
    <button class="btn primary" id="sRun">Run safety test</button><div id="sOut" style="margin-top:14px"></div></div>
    <div class="card pad" style="margin-top:16px"><h3 style="margin:0 0 8px">Defenses in place</h3>
      <ul style="margin:0;padding-left:18px;font-size:13.5px">
        <li>Uploaded docs, retrieved text, news, and notes are treated as <b>data</b>, fenced as UNTRUSTED.</li>
        <li>System preamble forbids obeying in-document instructions or revealing keys/config.</li>
        <li>Agents are restricted to an explicit tool allowlist; arguments are validated by the orchestrator.</li>
        <li>No external action (email/calendar) is ever executed — drafts only, user approves.</li>
        <li>Bounded agent steps, retries, timeout, and a configurable daily run limit cap cost.</li>
        <li>Upload type/size validation; secrets kept out of logs and never sent to the browser.</li></ul></div>`;
  $("#sRun").onclick=async()=>{ const out=$("#sOut"); out.innerHTML=loading("Running attacks through the agent…");
    const r=await API.post("/api/safety/test",{});
    out.innerHTML=`<div class="${r.all_blocked?"okbox":"errbox"}">${r.all_blocked?"✓":"✗"} ${r.passed}/${r.total} attacks blocked.</div>
      <table style="margin-top:12px"><tr><th>Attack</th><th>Result</th><th>Model reply (excerpt)</th></tr>
      ${r.results.map(x=>`<tr><td>${esc(x.attack)}</td><td>${x.blocked?'<span class="badge ok">blocked</span>':'<span class="badge err">FAILED</span>'}</td><td class="small muted">${esc(x.model_reply_excerpt)}</td></tr>`).join("")}</table>
      <div class="small muted" style="margin-top:10px">${esc(r.method)}</div>`; };
};

// ---------- boot ----------
loadStatus(); route();
