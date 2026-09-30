const pptxgen = require("pptxgenjs");
const path = require("path");

const pres = new pptxgen();
pres.layout = "LAYOUT_16x9";
pres.author = "Friday Voice Agent";
pres.title = "Friday: Voice Repo Agent";

const C = {
  bg: "0F172A",
  accent: "38BDF8",
  text: "F8FAFC",
  muted: "94A3B8",
  card: "1E293B",
};

function slideTitle(title, subtitle) {
  const s = pres.addSlide();
  s.background = { color: C.bg };
  s.addText(title, {
    x: 0.6,
    y: 1.2,
    w: 8.8,
    h: 1.2,
    fontSize: 36,
    bold: true,
    color: C.text,
    isTextBox: true,
    margin: 0,
  });
  if (subtitle) {
    s.addText(subtitle, {
      x: 0.6,
      y: 2.5,
      w: 8.8,
      h: 0.8,
      fontSize: 18,
      color: C.muted,
      isTextBox: true,
      margin: 0,
    });
  }
}

function slideBullets(title, bullets) {
  const s = pres.addSlide();
  s.background = { color: C.bg };
  s.addText(title, {
    x: 0.6,
    y: 0.45,
    w: 8.8,
    h: 0.7,
    fontSize: 28,
    bold: true,
    color: C.accent,
    isTextBox: true,
    margin: 0,
  });
  const items = bullets.map((t, i) => ({
    text: t,
    options: {
      bullet: true,
      breakLine: i < bullets.length - 1,
      fontSize: 16,
      color: C.text,
      paraSpaceAfter: 8,
    },
  }));
  s.addText(items, {
    x: 0.75,
    y: 1.35,
    w: 8.5,
    h: 4.5,
    isTextBox: true,
    margin: 0,
  });
}

slideTitle("Friday", "Voice-first control for GitHub repositories");
slideTitle("The problem", "Repos are large; keyboards and tabs slow triage");

slideBullets("Solution", [
  "Speak or type natural questions about an open repo",
  "See a circle-pack map: entry points, core, hotspots",
  "Read commits, issues, PRs; stage writes with confirmation",
  "AssemblyAI Voice Agent for live conversation",
]);

slideBullets("User experience", [
  "Open localhost:5000/?repo=owner/name",
  "Explore the map; click files for metadata",
  "Hold mic or Ctrl — ask about landmarks, diffs, issues",
  "Draft issue/comment → separate turn: yes to post",
]);

slideBullets("Architecture — client", [
  "D3 circle pack + file sidebar",
  "Voice: WebSocket to AssemblyAI Voice Agent",
  "Single tool: friday_turn → server chat.turn",
  "Ask box + activity trace (command / jev / gateway)",
]);

slideBullets("Architecture — server", [
  "map_pipeline: tarball ingest, landmarks, imports",
  "chat.turn: direct parsers → optional Gateway → Jev → orchestrator",
  "agent.run_agent: 8-turn LLM Gateway loop (reference demo)",
  "github_tools: REST + staged confirm_write",
]);

slideBullets("Routing (reliability)", [
  "command: yes/no, titles, comment/issue parsers, map shortcuts",
  "gateway: multi-step GitHub (commits → issue)",
  "jev: confident single tool for map/explain/focus",
  "K2: tool name fallback when Jev < 0.9",
]);

slideBullets("AssemblyAI surfaces", [
  "Voice Agent — Universal STT + spoken replies",
  "Sync API — /api/run WAV fallback",
  "LLM Gateway — qwen3-next-80b-a3b tool calling",
  "Auth: Bearer (Voice) vs raw key (Sync) — see docs",
]);

slideBullets("GitHub safety", [
  "create_issue / add_comment only stage drafts",
  "confirm_write blocked on same transcript_id as draft",
  "OAuth session optional; tokens never in static/",
  "Refuses close/delete on issues and PRs",
]);

slideBullets("Optional intelligence", [
  "TypeSafe Jev — tool choice + review confidence",
  "Vertex Gemini — escalate low-confidence reviews",
  "IFM K2 Horizon — AGENT_LLM_PROVIDER=ifm",
  "review_gate — single verdict path for “safe to merge”",
]);

slideBullets("Testing", [
  "python test_friday.py — automated suite",
  "docs/TEST_QUESTIONS.md — 37 manual scenarios",
  "Voice vs Ask parity test in test_friday",
  "Regression: issue title follow-up after Jev create_issue",
]);

slideBullets("Configuration", [
  "ASSEMBLYAI_API_KEY, GITHUB_TOKEN / OAuth",
  "FRIDAY_GITHUB_GATEWAY=multi | all | off",
  "AGENT_LLM_PROVIDER=assemblyai | ifm",
  "GITHUB_REPO default repo on startup",
]);

slideBullets("Future / reliability tradeoffs", [
  "Drop Jev? Only if all turns use Gateway + expanded tools — slower",
  "Best hybrid: Jev for map; Gateway for GitHub; parsers for follow-ups",
  "FRIDAY_GITHUB_GATEWAY=all for tutorial-like GitHub behavior",
  "Reference: Hands-On-AI-Engineering/voice-github-agent",
]);

slideTitle("Thank you", "github.com/hatif03/friday-voice-agent");

const out = path.join(__dirname, "Friday-Voice-Agent.pptx");
pres.writeFile({ fileName: out }).then(() => {
  console.log("Wrote", out);
});
