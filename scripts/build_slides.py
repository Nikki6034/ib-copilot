"""Build a self-contained slides.html (reveal.js via CDN, base64 screenshots).
Run: python scripts/build_slides.py  (writes slides.html in the project root)."""
import base64, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHOTS = ROOT / "docs" / "screenshots"
REPO = "https://github.com/Nikki6034/ib-copilot"


def b64(name):
    return "data:image/jpeg;base64," + base64.b64encode((SHOTS / f"{name}.jpg").read_bytes()).decode()


S = {n: b64(n) for n in ["dashboard", "chatprep", "interview", "plan", "tokenomics", "safety", "quiz", "deal"]}

HTML = f'''<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<title>IB Copilot — Slides</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/reveal.js@4.6.1/dist/reveal.css">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/reveal.js@4.6.1/dist/theme/white.css">
<style>
:root{{--navy:#13294b;--blue:#1f4e8c;--accent:#2f6fb0}}
.reveal{{font-family:-apple-system,"Segoe UI",Arial,sans-serif;color:#1a2230}}
.reveal h1,.reveal h2,.reveal h3{{font-family:Georgia,serif;color:var(--navy);text-transform:none;letter-spacing:-.01em}}
.reveal h1{{font-size:2.0em}} .reveal h2{{font-size:1.4em}}
.reveal section{{text-align:left}}
.reveal .center{{text-align:center}}
.reveal ul{{font-size:.78em}} .reveal p{{font-size:.82em}}
.reveal table{{font-size:.6em}}
.reveal .muted{{color:#667085}}
.reveal .pill{{background:#e8f0f9;color:var(--blue);border-radius:999px;padding:3px 12px;font-size:.5em;font-weight:600}}
.reveal img.shot{{border:1px solid #e5e9f0;border-radius:8px;max-height:430px;box-shadow:0 4px 16px rgba(16,32,60,.12)}}
.reveal .two{{display:flex;gap:18px;align-items:center}}
.reveal .big{{font-size:1.3em;color:var(--blue);font-weight:700}}
.reveal .foot{{position:fixed;bottom:12px;left:20px;font-size:12px;color:#8aa0bf}}
.reveal section small{{font-size:.6em;color:#667085}}
</style></head><body><div class="reveal"><div class="slides">

<section class="center">
  <h1>IB Copilot</h1>
  <p class="big">Your AI recruiting copilot for IB — FIG &amp; M&amp;A</p>
  <p class="muted">Grounded interview practice, deal prep, and banker follow-ups — in one connected workflow.</p>
  <p><small>Nikita Krishnan · {REPO}</small></p>
</section>

<section>
  <h2>The problem</h2>
  <ul>
    <li>MBA IB recruiting is a second full-time job — <b>28 recruiting events</b> in one October (Citi, Moelis, JPM, Goldman, BCG…).</li>
    <li>Prep is scattered: hundreds of pages of technical guides, behavioral stories, live deals, and a banker contact list.</li>
    <li>A single coffee chat takes <b>20–30 min</b> to prep by hand — and there are dozens.</li>
    <li>Generic AI isn't grounded in <i>your</i> material and can't be trusted on technical facts.</li>
  </ul>
</section>

<section>
  <h2>What's different</h2>
  <table>
  <tr><th>Tool</th><th>Gap</th></tr>
  <tr><td>ChatGPT / Perplexity</td><td>Not grounded in your guides, no citations, no memory of your calendar/performance</td></tr>
  <tr><td>BIWS / Wall Street Prep</td><td>Great static courses — no grading, personalization, or networking workflow</td></tr>
  <tr><td>Wall Street Oasis</td><td>Generic question banks, not adaptive</td></tr>
  </table>
  <p>IB Copilot <b>connects</b> calendar → chat prep → grounded practice → readiness score → 7-day plan → deal drills, with <b>citations</b> on every answer.</p>
</section>

<section class="center">
  <h2>How the agents work</h2>
  <p class="muted">Orchestrator + 4 specialized agents, each with its own tools; RAG + SQLite + gpt-6-luna (Portkey).</p>
  <img class="shot" src="{S['dashboard']}" style="max-height:400px">
</section>

<section>
  <h2 class="center">One-click chat prep</h2>
  <div class="center"><img class="shot" src="{S['chatprep']}"></div>
  <p class="center muted">A calendar event → tailored questions to ask + likely questions back + opener. (Agent D)</p>
</section>

<section>
  <h2 class="center">Practice + a plan that adapts</h2>
  <div class="two"><img class="shot" src="{S['interview']}" style="max-height:380px"><img class="shot" src="{S['plan']}" style="max-height:380px"></div>
  <p class="center muted">Measured delivery vs. rubric scoring · a 7-day plan from your real performance &amp; events.</p>
</section>

<section>
  <h2 class="center">Cost to run</h2>
  <div class="two"><img class="shot" src="{S['tokenomics']}" style="max-height:360px">
  <ul><li>Measured over 28 runs: <b>$0.000411 / run</b>.</li><li><b>$0.16 / user / month</b> (20 runs/day).</li><li><b>10,000 users ≈ $1,644 / month</b>.</li><li>Cheap by design: lexical RAG, bounded tokens, caching.</li></ul></div>
</section>

<section>
  <h2 class="center">Safety — tested, not just claimed</h2>
  <div class="center"><img class="shot" src="{S['safety']}"></div>
  <p class="center muted">Prompt-injection test: <b>3/3 attacks blocked, no key leaked.</b> Docs are untrusted data; no action runs without the user.</p>
</section>

<section>
  <h2>Impact</h2>
  <ul>
    <li>Chat prep in <b>~10 s</b> vs. <b>20–30 min</b> by hand → <b>~7–10 hrs saved</b> across a month of chats.</li>
    <li>Every technical answer is <b>grounded + cited</b> — trustworthy before an interview.</li>
    <li>A <b>measured readiness score</b> + plan turns "I feel behind" into concrete next steps.</li>
    <li>At ~$0.16/user/mo, a career office could serve a <b>whole cohort</b> cheaply.</li>
  </ul>
  <small>Evidence: the builder is the target user, running it on a real October recruiting calendar.</small>
</section>

<section>
  <h2>Limitations &amp; next steps</h2>
  <ul>
    <li>Lexical retrieval (no embeddings on the course key) → add semantic search next.</li>
    <li>Outlook is local-only (.ics/PDF + .eml drafts) → optional least-privilege Graph next.</li>
    <li>Single-user local app → multi-user + hosting for a career office.</li>
  </ul>
  <p class="center big">{REPO}</p>
</section>

</div></div>
<div class="foot">IB Copilot · Nikita Krishnan</div>
<script src="https://cdn.jsdelivr.net/npm/reveal.js@4.6.1/dist/reveal.js"></script>
<script>Reveal.initialize({{hash:true,slideNumber:true,width:1100,height:700,margin:0.06}});</script>
</body></html>'''

(ROOT / "slides.html").write_text(HTML, encoding="utf-8")
print("wrote slides.html", len((ROOT / "slides.html").read_text()), "bytes")
