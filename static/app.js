const FridayApp = {
  map: null,

  history: null,
  trailItems: [],
  playTimer: null,

  init() {
    mermaid.initialize({ startOnLoad: false, securityLevel: "strict", theme: "default" });
    document.getElementById("repo-form").addEventListener("submit", (event) => {
      event.preventDefault();
      this.openRepo(document.getElementById("repo-input").value.trim());
    });
    document.getElementById("back-btn").addEventListener("click", () => {
      history.pushState({}, "", "/");
      this.showLanding();
    });
    document.getElementById("github-btn").addEventListener("click", () => this.connectGithub());
    document.getElementById("github-cancel").addEventListener("click", () => {
      document.getElementById("github-dialog").close();
    });
    document.querySelectorAll(".side-tab").forEach((button) => {
      button.addEventListener("click", () => this.showTab(button.dataset.tab));
    });
    document.getElementById("inspector-close").addEventListener("click", () => this.closeInspector());
    document.getElementById("arch-btn").addEventListener("click", () => this.architecture());
    document.getElementById("png-btn").addEventListener("click", () => this.exportPng());
    document.querySelectorAll(".voice-btn").forEach((button) => {
      button.addEventListener("click", () => this.toggleVoice());
    });
    document.getElementById("record-btn").addEventListener("click", () => this.toggleRecord());
    document.getElementById("disconnect-btn").addEventListener("click", () => this.disconnectToken());
    document.getElementById("zoom-in").addEventListener("click", () => FridayMap.zoomBy(1.3));
    document.getElementById("zoom-out").addEventListener("click", () => FridayMap.zoomBy(0.75));
    document.getElementById("zoom-reset").addEventListener("click", () => FridayMap.resetZoom());
    document.getElementById("toggle-labels").addEventListener("click", () => {
      FridayMap.showLabels = !FridayMap.showLabels;
      if (FridayMap.data) FridayMap.draw();
    });
    document.getElementById("toggle-imports").addEventListener("click", (event) => {
      FridayMap.showImports = !FridayMap.showImports;
      event.currentTarget.setAttribute("aria-pressed", FridayMap.showImports ? "true" : "false");
      FridayMap.paintEdges();
    });
    document.getElementById("toggle-heat").addEventListener("click", (event) => {
      FridayMap.showHeat = !FridayMap.showHeat;
      event.currentTarget.setAttribute("aria-pressed", FridayMap.showHeat ? "true" : "false");
      if (FridayMap.data) FridayMap.draw();
    });
    document.getElementById("toggle-loc").addEventListener("click", (event) => {
      FridayMap.sizeMode = FridayMap.sizeMode === "loc" ? "bytes" : "loc";
      event.currentTarget.setAttribute("aria-pressed", FridayMap.sizeMode === "loc" ? "true" : "false");
      if (FridayMap.data) FridayMap.draw();
    });
    document.getElementById("ask-input").addEventListener("input", (event) => {
      const count = FridayMap.search(event.target.value);
      const note = document.getElementById("search-count");
      if (note) note.textContent = event.target.value.trim() ? `${count} match${count === 1 ? "" : "es"}` : "";
    });
    document.getElementById("ask-form").addEventListener("submit", (event) => {
      event.preventDefault();
      this.ask(document.getElementById("ask-input").value);
    });
    document.getElementById("thinking-toggle").addEventListener("click", (event) => {
      const body = document.getElementById("thinking-body");
      const open = body.hidden;
      body.hidden = !open;
      event.currentTarget.setAttribute("aria-expanded", open ? "true" : "false");
    });
    document.getElementById("check-btn").addEventListener("click", () => this.checkSecurity());
    document.getElementById("timeline-range").addEventListener("input", (event) => this.scrub(Number(event.target.value)));
    document.getElementById("timeline-play").addEventListener("click", () => this.playTimeline());
    document.addEventListener("keydown", (event) => {
      if (event.target.closest("input, textarea")) return;
      if (event.key === "Escape") this.closeInspector();
      if (document.body.dataset.view !== "map") return;
      if (event.key === "+" || event.key === "=") FridayMap.zoomBy(1.25);
      if (event.key === "-" || event.key === "_") FridayMap.zoomBy(0.8);
      if (event.key === "0") FridayMap.resetZoom();
    });
    this.githubStatus();
    const params = new URLSearchParams(location.search);
    const githubFlag = params.get("github");
    if (githubFlag === "connected") this.activity("Signed in with GitHub.");
    if (githubFlag === "failed") this.showError("GitHub sign-in did not finish. Start it again from Connect GitHub.");
    if (githubFlag) {
      params.delete("github");
      const cleaned = params.toString();
      history.replaceState({}, "", cleaned ? `/?${cleaned}` : "/");
    }
    const repo = params.get("repo");
    if (repo) this.openRepo(repo);
    window.addEventListener("popstate", () => {
      const next = new URLSearchParams(location.search).get("repo");
      if (next) this.openRepo(next);
      else this.showLanding();
    });
  },

  showLanding() {
    document.body.dataset.view = "home";
    document.getElementById("landing").hidden = false;
    document.getElementById("workspace").hidden = true;
    document.getElementById("ask-form").hidden = true;
    document.getElementById("thinking").hidden = true;
    document.getElementById("repo-input").value = "";
    document.getElementById("error-banner").hidden = true;
  },

  showTab(name) {
    document.querySelectorAll(".side-tab").forEach((button) => {
      button.setAttribute("aria-selected", button.dataset.tab === name ? "true" : "false");
    });
    document.getElementById("tab-file").hidden = name !== "file";
    document.getElementById("tab-activity").hidden = name !== "activity";
    document.getElementById("tab-trail").hidden = name !== "trail";
  },

  setBusy(on, label) {
    document.body.classList.toggle("is-loading", on);
    const openButton = document.querySelector("#repo-form button[type='submit']");
    if (openButton) openButton.textContent = on ? "Opening…" : "Open";
    const skeleton = document.getElementById("map-skeleton");
    const svg = document.getElementById("map-svg");
    if (!on) {
      if (skeleton) skeleton.hidden = true;
      if (svg && this.map) svg.hidden = false;
      return;
    }
    document.body.dataset.view = "map";
    document.getElementById("landing").hidden = true;
    document.getElementById("workspace").hidden = false;
    document.getElementById("repo-crumb").textContent = label || "Opening…";
    if (skeleton) skeleton.hidden = false;
    if (svg) svg.hidden = true;
    const stats = document.getElementById("stats");
    stats.replaceChildren();
    const row = document.createElement("div");
    row.className = "stat-list";
    for (let i = 0; i < 4; i += 1) {
      const block = document.createElement("span");
      block.className = "skeleton-line";
      block.style.cssText = "width:64px;height:28px";
      row.appendChild(block);
    }
    stats.appendChild(row);
    const legend = document.getElementById("legend");
    legend.replaceChildren();
    for (let i = 0; i < 4; i += 1) {
      const line = document.createElement("li");
      const bar = document.createElement("span");
      bar.className = "skeleton-line";
      bar.style.cssText = "width:100%;height:14px";
      line.appendChild(bar);
      legend.appendChild(line);
    }
  },

  async openRepo(repo) {
    if (!repo) return;
    this.hideError();
    this.setBusy(true, repo);
    const response = await fetch(`/api/map?repo=${encodeURIComponent(repo)}`);
    const data = await response.json();
    if (!response.ok) {
      this.setBusy(false);
      if (!this.map) this.showLanding();
      const message = data.detail || "Could not open that repository.";
      this.showError(message);
      if (String(message).includes("403") || String(message).includes("Connect GitHub")) {
        document.getElementById("github-dialog").showModal();
      }
      return;
    }
    this.map = data;
    document.body.dataset.view = "map";
    document.getElementById("landing").hidden = true;
    document.getElementById("workspace").hidden = false;
    document.getElementById("repo-crumb").textContent = data.slug;
    FridayMap.mount(data);
    document.getElementById("ask-form").hidden = false;
    this.trail({ step: "open", detail: `Opened ${data.slug}` });
    this.setBusy(false);
    document.getElementById("repo-input").value = data.slug;
    const url = new URL(location.href);
    const hadRepo = url.searchParams.has("repo");
    url.searchParams.set("repo", data.slug);
    if (hadRepo) history.replaceState({}, "", url);
    else history.pushState({}, "", url);
    this.activity(`Opened ${data.slug}. ${data.stats.files} files, ${data.stats.edges} imports.`);
    if (data.focus_path) FridayMap.focus(data.focus_path);
    if (data.pull_number) this.reviewPull(data.pull_number);
    this.loadHistory();
    if (FridayVoice.ws && FridayVoice.ws.readyState === WebSocket.OPEN) {
      FridayVoice.updateKeyterms(data.keyterms || []);
    }
  },

  inspect(path) {
    if (!this.map) return;
    const file = this.map.files[path];
    if (!file) return;
    this.showTab("file");
    document.getElementById("inspector-close").hidden = false;
    document.getElementById("inspector-empty").hidden = true;
    const body = document.getElementById("inspector-body");
    body.hidden = false;
    body.replaceChildren();
    const head = document.createElement("header");
    head.className = "inspect-head";
    const name = document.createElement("h3");
    name.textContent = file.path.split("/").pop();
    const title = document.createElement("p");
    title.className = "file-path";
    title.textContent = file.path;
    head.appendChild(name);
    head.appendChild(title);
    body.appendChild(head);
    const facts = document.createElement("dl");
    facts.className = "inspect-facts";
    [
      ["Lines", String(file.loc || 0)],
      ["Size", `${file.size || 0} bytes`],
      ["Language", file.language || "file"],
      ["Kind", file.kind || "file"],
    ].forEach(([label, value]) => {
      const item = document.createElement("div");
      const dt = document.createElement("dt");
      dt.textContent = label;
      const dd = document.createElement("dd");
      dd.textContent = value;
      item.appendChild(dt);
      item.appendChild(dd);
      facts.appendChild(item);
    });
    body.appendChild(facts);
    const marks = Object.entries(file.landmark || {}).filter(([, on]) => on).map(([mark]) => mark);
    if (file.heat) marks.push(`heat ${file.heat}`);
    if (marks.length) {
      const meta = document.createElement("div");
      meta.className = "meta";
      marks.forEach((mark) => meta.appendChild(this.pill(mark)));
      body.appendChild(meta);
    }
    const actions = document.createElement("div");
    actions.className = "inspect-actions";
    const locate = document.createElement("button");
    locate.type = "button";
    locate.className = "ghost";
    locate.textContent = "Locate";
    locate.addEventListener("click", () => FridayMap.focus(file.path));
    const link = document.createElement("a");
    link.className = "ghost";
    link.href = file.url;
    link.target = "_blank";
    link.rel = "noreferrer";
    link.textContent = "GitHub";
    actions.appendChild(locate);
    actions.appendChild(link);
    body.appendChild(actions);
    const imports = file.imports || [];
    const imported = file.imported_by || [];
    if (!imports.length && !imported.length) {
      const note = document.createElement("p");
      note.className = "muted";
      note.textContent = "No import links for this file.";
      body.appendChild(note);
      const folder = file.path.split("/").slice(0, -1).join("/");
      const siblings = Object.keys(this.map.files)
        .filter((item) => item !== file.path && item.split("/").slice(0, -1).join("/") === folder)
        .slice(0, 8);
      body.appendChild(this.list("Same folder", siblings));
      const busy = [...(this.map.edges || [])]
        .map((edge) => edge.target)
        .filter((item, index, list) => item && item !== file.path && list.indexOf(item) === index)
        .slice(0, 6);
      body.appendChild(this.list("Busiest links", busy));
    } else {
      body.appendChild(this.list("Imports", imports));
      body.appendChild(this.list("Imported by", imported));
    }
    const authors = document.createElement("div");
    authors.id = "author-list";
    body.appendChild(authors);
    this.loadAuthors(file.path, authors);
  },

  closeInspector() {
    document.getElementById("inspector-body").hidden = true;
    document.getElementById("inspector-empty").hidden = false;
    document.getElementById("inspector-close").hidden = true;
  },

  async loadAuthors(path, host) {
    const response = await fetch("/api/voice/tool", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: "who_touched", arguments: { path }, transcript_id: "ui", user_transcript: "" }),
    });
    const data = await response.json();
    if (!response.ok) return;
    const people = ((data.result || {}).authors) || [];
    host.replaceChildren();
    const section = document.createElement("section");
    section.className = "inspect-section";
    const heading = document.createElement("h3");
    heading.textContent = "Authors";
    section.appendChild(heading);
    const ul = document.createElement("ul");
    ul.className = "fact-list";
    people.slice(0, 8).forEach((person) => {
      const li = document.createElement("li");
      const who = document.createElement("span");
      who.textContent = person.name;
      const count = document.createElement("span");
      count.className = "tree-count";
      count.textContent = String(person.count);
      li.appendChild(who);
      li.appendChild(count);
      ul.appendChild(li);
    });
    if (!people.length) {
      const li = document.createElement("li");
      li.className = "muted";
      li.textContent = "No commits on this path.";
      ul.appendChild(li);
    }
    section.appendChild(ul);
    host.appendChild(section);
  },

  pill(text) {
    const span = document.createElement("span");
    span.className = "pill";
    span.textContent = text;
    return span;
  },

  list(title, paths) {
    const wrap = document.createElement("section");
    wrap.className = "inspect-section";
    const heading = document.createElement("h3");
    heading.textContent = title;
    wrap.appendChild(heading);
    const ul = document.createElement("ul");
    ul.className = "fact-list";
    (paths || []).slice(0, 12).forEach((path) => {
      const li = document.createElement("li");
      const button = document.createElement("button");
      button.type = "button";
      button.className = "path-link";
      button.textContent = path.split("/").pop();
      button.title = path;
      button.addEventListener("click", () => FridayMap.focus(path));
      li.appendChild(button);
      ul.appendChild(li);
    });
    if (!(paths || []).length) {
      const li = document.createElement("li");
      li.className = "muted";
      li.textContent = "None in view";
      ul.appendChild(li);
    }
    wrap.appendChild(ul);
    return wrap;
  },

  applyCommands(commands) {
    commands.forEach((command) => {
      if (command.type === "load_map" && command.repo) this.openRepo(command.repo);
      if (command.type === "focus" && command.path) FridayMap.focus(command.path);
      if (command.type === "layer") {
        if (command.layer === "heat") {
          FridayMap.showHeat = !!command.enabled;
          document.getElementById("toggle-heat").setAttribute("aria-pressed", command.enabled ? "true" : "false");
        }
        if (command.layer === "loc") {
          FridayMap.sizeMode = command.enabled ? "loc" : "bytes";
          document.getElementById("toggle-loc").setAttribute("aria-pressed", command.enabled ? "true" : "false");
        }
        if (command.layer === "edges") FridayMap.showImports = !!command.enabled;
        if (FridayMap.data) FridayMap.draw();
      }
      if (command.type === "heat_paths" && this.map) {
        (command.paths || []).forEach((path) => {
          if (this.map.files[path]) this.map.files[path].heat = Math.max(this.map.files[path].heat || 0, 1);
        });
        FridayMap.showHeat = true;
        document.getElementById("toggle-heat").setAttribute("aria-pressed", "true");
        FridayMap.draw();
      }
      if (command.type === "history") this.showHistory(command.history, command.paths);
      if (command.type === "highlight") FridayMap.highlightPaths(command.paths || []);
      if (command.type === "thread") this.showThread(command.thread);
      if (command.type === "noise") this.showNoise(command.noise);
      if (command.type === "authors" && command.authors) this.activity(command.authors.say || "");
      if (command.type === "fix") this.activity((command.fix || {}).say || "");
      if (command.type === "judgment") this.showJudgment(command.judgment);
      if (command.type === "architecture") this.showArchitecture(command.mermaid, command.summary);
      if (command.type === "security") this.showSecurity(command.security);
      if (command.type === "ask") this.showThinking((command.ask || {}).steps || [], (command.ask || {}).say, (command.ask || {}).paths);
    });
  },

  showJudgment(judgment) {
    const panel = document.getElementById("judgment");
    const body = document.getElementById("judgment-body");
    panel.hidden = false;
    document.getElementById("activity-empty").hidden = true;
    this.showTab("activity");
    body.replaceChildren();
    const gate = judgment.gate || {};
    const title = document.createElement("p");
    title.textContent = judgment.title || "Review";
    body.appendChild(title);
    const tone = document.createElement("p");
    tone.textContent = gate.cleared ? "Cleared the bar" : "Not calling this safe";
    tone.style.color = gate.tone === "danger" ? "var(--danger)" : gate.tone === "ok" ? "var(--ok)" : "var(--warn)";
    body.appendChild(tone);
    const say = document.createElement("p");
    say.textContent = gate.say || "";
    body.appendChild(say);
    const jev = (judgment.jev || {}).answers || {};
    const list = document.createElement("ul");
    list.className = "links";
    ["risk", "verdict", "review_depth", "needs_security", "merge_blocker", "blast_radius"].forEach((key) => {
      const answer = jev[key];
      if (!answer) return;
      const li = document.createElement("li");
      const value = answer.choice || answer.score || (answer.noul != null ? `${Math.round(answer.noul * 100)}%` : "");
      li.textContent = `${key}: ${value}`;
      list.appendChild(li);
    });
    body.appendChild(list);
  },

  async architecture() {
    const repo = (this.map && this.map.slug) || document.getElementById("repo-input").value.trim();
    if (!repo) {
      this.showError("Open a repository first.");
      return;
    }
    document.getElementById("arch-btn").disabled = true;
    const response = await fetch("/api/architecture", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ repo }),
    });
    const data = await response.json();
    document.getElementById("arch-btn").disabled = false;
    if (!response.ok) {
      this.showError(data.detail || "Architecture request failed.");
      return;
    }
    const diagram = (data.ui_commands || []).find((item) => item.type === "architecture");
    if (diagram) this.showArchitecture(diagram.mermaid, diagram.summary);
    else this.showError(data.say || "No diagram came back.");
  },

  async showArchitecture(source, summary) {
    const panel = document.getElementById("architecture");
    panel.hidden = false;
    document.getElementById("activity-empty").hidden = true;
    this.showTab("activity");
    document.getElementById("architecture-summary").textContent = summary || "";
    const host = document.getElementById("mermaid-host");
    host.innerHTML = "";
    try {
      const { svg } = await mermaid.render(`arch-${Date.now()}`, source || "flowchart LR\n  empty[No nodes]");
      host.innerHTML = svg;
    } catch (err) {
      host.textContent = "The diagram did not render.";
    }
  },

  exportPng() {
    const svg = document.getElementById("map-svg");
    if (svg.hidden) return;
    const xml = new XMLSerializer().serializeToString(svg);
    const blob = new Blob([xml], { type: "image/svg+xml" });
    const url = URL.createObjectURL(blob);
    const image = new Image();
    image.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = 1600;
      canvas.height = 1000;
      const ctx = canvas.getContext("2d");
      ctx.fillStyle = getComputedStyle(document.body).backgroundColor;
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(image, 0, 0, canvas.width, canvas.height - 48);
      ctx.fillStyle = getComputedStyle(document.body).color;
      ctx.font = "20px IBM Plex Sans, sans-serif";
      ctx.fillText((this.map && this.map.slug) || "Friday", 24, canvas.height - 18);
      const link = document.createElement("a");
      link.href = canvas.toDataURL("image/png");
      link.download = `${(this.map && this.map.repo) || "friday"}-fingerprint.png`;
      link.click();
      URL.revokeObjectURL(url);
    };
    image.src = url;
  },

  async connectGithub() {
    const status = this.github || await this.githubStatus();
    const setup = document.getElementById("github-setup");
    const account = document.getElementById("github-account");
    if (status.connected) {
      setup.hidden = true;
      account.hidden = false;
      document.getElementById("github-dialog").showModal();
      this.loadRepoLibrary();
      return;
    }
    if (!status.oauth) {
      setup.hidden = false;
      account.hidden = true;
      document.getElementById("github-dialog").showModal();
      return;
    }
    window.location.href = "/api/github/oauth/start";
  },

  async loadRepoLibrary() {
    const library = document.getElementById("repo-library");
    const list = document.getElementById("repo-library-list");
    library.hidden = false;
    list.replaceChildren();
    for (let i = 0; i < 4; i += 1) {
      const li = document.createElement("li");
      const bar = document.createElement("span");
      bar.className = "skeleton-line";
      bar.style.cssText = "width:100%;height:42px;border-radius:12px";
      li.appendChild(bar);
      list.appendChild(li);
    }
    const response = await fetch("/api/github/repos");
    const data = await response.json();
    if (!response.ok) return;
    library.hidden = false;
    list.replaceChildren();
    (data.repos || []).forEach((repo) => {
      const li = document.createElement("li");
      const button = document.createElement("button");
      button.type = "button";
      const name = document.createElement("span");
      name.textContent = repo.full_name;
      const meta = document.createElement("small");
      meta.textContent = repo.private ? "Private" : "Public";
      button.appendChild(name);
      button.appendChild(meta);
      button.addEventListener("click", () => {
        document.getElementById("github-dialog").close();
        this.openRepo(repo.full_name);
      });
      li.appendChild(button);
      list.appendChild(li);
    });
    if (!(data.repos || []).length) {
      const li = document.createElement("li");
      li.textContent = "No repositories came back for this account.";
      list.appendChild(li);
    }
  },

  setGithubButton(login) {
    const button = document.getElementById("github-btn");
    const label = button.querySelector("span");
    if (label) label.textContent = login ? `GitHub · ${login}` : "Connect GitHub";
  },

  async disconnectToken() {
    const response = await fetch("/api/github/disconnect", { method: "POST" });
    const data = await response.json();
    document.getElementById("token-status").textContent = data.connected
      ? "Session token cleared. An environment token is still in use."
      : "Disconnected.";
    if (!data.connected) {
      this.setGithubButton(null);
      document.getElementById("repo-library").hidden = true;
      document.getElementById("github-dialog").close();
      if (this.github) {
        this.github.connected = false;
        this.github.login = null;
      }
    }
  },

  async githubStatus() {
    const response = await fetch("/api/github/status");
    const data = await response.json();
    this.github = data;
    const setup = document.getElementById("github-setup");
    const account = document.getElementById("github-account");
    if (data.login) {
      document.getElementById("token-status").textContent = `Signed in as ${data.login}. The token stays on this server.`;
      this.setGithubButton(data.login);
      setup.hidden = true;
      account.hidden = false;
      this.loadRepoLibrary();
    } else if (data.connected) {
      document.getElementById("token-status").textContent = "A server token is already set.";
      this.setGithubButton("connected");
      setup.hidden = true;
      account.hidden = false;
      this.loadRepoLibrary();
    } else {
      setup.hidden = false;
      account.hidden = true;
    }
    return data;
  },

  async reviewPull(number) {
    this.activity(`Reviewing pull request ${number}.`);
    const response = await fetch("/api/voice/tool", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: "review_changes",
        arguments: { pr_number: number },
        transcript_id: "ui-pull",
        user_transcript: "",
      }),
    });
    const data = await response.json();
    if (data.say) this.activity(data.say);
    (data.trace || []).forEach((step) => this.trail(step));
    this.applyCommands(data.ui_commands || []);
  },

  async loadHistory() {
    const response = await fetch("/api/history?count=30");
    const data = await response.json();
    if (!response.ok) return;
    this.showHistory(data, []);
  },

  showHistory(payload, paths) {
    this.history = payload;
    const box = document.getElementById("timeline");
    const range = document.getElementById("timeline-range");
    const commits = payload.commits || [];
    box.hidden = !commits.length;
    range.max = Math.max(0, commits.length - 1);
    range.value = 0;
    const stats = document.getElementById("stats");
    const authors = document.getElementById("stat-authors");
    if (authors && payload.contributors != null) authors.textContent = String(payload.contributors);
    if (paths && paths.length) FridayMap.highlightPaths(paths);
    else FridayMap.clearHighlight();
    this.describeCommit(Number(range.value));
    this.seedActivity(payload);
  },

  seedActivity(payload) {
    const host = document.getElementById("activity-body");
    const empty = document.getElementById("activity-empty");
    if (!host) return;
    const commits = (payload.commits || []).slice(0, 8);
    host.replaceChildren();
    if (payload.contributors != null) {
      const note = document.createElement("p");
      note.className = "window-note";
      note.textContent = `${payload.contributors} authors in this window.`;
      host.appendChild(note);
    }
    commits.forEach((commit) => host.appendChild(this.commitCard(commit)));
    if (empty) empty.hidden = commits.length > 0;
  },

  commitCard(commit) {
    const card = document.createElement("article");
    card.className = "commit-card";
    const top = document.createElement("div");
    top.className = "commit-top";
    const hash = document.createElement("code");
    hash.textContent = commit.short || "";
    const author = document.createElement("span");
    author.textContent = commit.author || "";
    top.appendChild(hash);
    top.appendChild(author);
    const message = document.createElement("p");
    message.className = "commit-message";
    message.textContent = commit.message || "";
    card.appendChild(top);
    card.appendChild(message);
    const files = (commit.files || []).slice(0, 6);
    if (files.length) {
      const list = document.createElement("ul");
      list.className = "file-chips";
      files.forEach((path) => {
        const li = document.createElement("li");
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = path.split("/").pop();
        button.title = path;
        button.addEventListener("click", () => {
          if (this.map && this.map.files[path]) FridayMap.focus(path);
        });
        li.appendChild(button);
        list.appendChild(li);
      });
      card.appendChild(list);
    }
    return card;
  },

  async ask(question) {
    const text = (question || "").trim();
    if (!text || !this.map) return;
    this.trail({ step: "search", detail: text });
    this.activity("Looking at the files that match.");
    const response = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: text }),
    });
    const data = await response.json();
    if (!response.ok) {
      this.showError(data.detail || "The question did not finish.");
      return;
    }
    this.showThinking(data.steps || [], data.say, data.paths || []);
  },

  showThinking(steps, say, paths) {
    const box = document.getElementById("thinking");
    const toggle = document.getElementById("thinking-toggle");
    const body = document.getElementById("thinking-body");
    box.hidden = false;
    const latest = steps[steps.length - 1];
    toggle.textContent = latest ? `${latest.step}: ${latest.detail || ""}` : "Done";
    body.hidden = true;
    body.replaceChildren();
    steps.forEach((step) => {
      const line = document.createElement("p");
      line.textContent = `${step.step}: ${step.detail || ""}`;
      body.appendChild(line);
      this.trail(step);
    });
    document.getElementById("thinking-answer").textContent = say || "";
    if (say) this.activity(say);
    if (paths && paths.length) FridayMap.highlightPaths(paths);
  },

  async checkSecurity() {
    if (!this.map) return;
    this.activity("Checking the files on the map.");
    const response = await fetch("/api/security", { method: "POST" });
    const data = await response.json();
    if (!response.ok) {
      this.showError(data.detail || "The check did not finish.");
      return;
    }
    this.showSecurity(data);
    this.trail({ step: "security", detail: data.say || "" });
  },

  showSecurity(data) {
    if (!data) return;
    this.showTab("activity");
    const host = document.getElementById("activity-body");
    const block = document.createElement("section");
    block.className = "inspect-section finding-block";
    const title = document.createElement("h3");
    title.textContent = "Check";
    const say = document.createElement("p");
    say.textContent = data.say || "Security check finished.";
    block.appendChild(title);
    block.appendChild(say);
    const list = document.createElement("ul");
    list.className = "fact-list";
    (data.findings || []).forEach((item) => {
      const li = document.createElement("li");
      const kind = document.createElement("span");
      kind.className = "pill";
      kind.textContent = item.kind || "finding";
      const button = document.createElement("button");
      button.type = "button";
      button.className = "path-link";
      button.textContent = item.path || item.title;
      if (item.path && this.map && this.map.files[item.path]) {
        button.addEventListener("click", () => FridayMap.focus(item.path));
      }
      li.appendChild(kind);
      li.appendChild(button);
      list.appendChild(li);
    });
    if ((data.findings || []).length) block.appendChild(list);
    if (host) host.prepend(block);
    const empty = document.getElementById("activity-empty");
    if (empty) empty.hidden = true;
    FridayMap.highlightPaths(data.paths || []);
    if (data.say) this.activity(data.say);
  },

  describeCommit(index) {
    const commits = (this.history && this.history.commits) || [];
    const commit = commits[index];
    const label = document.getElementById("timeline-label");
    if (!commit) {
      label.textContent = "Recent commits";
      return;
    }
    label.textContent = `${commit.short} · ${commit.author} · ${commit.message}`;
  },

  scrub(index) {
    this.describeCommit(index);
    const commits = (this.history && this.history.commits) || [];
    const commit = commits[index];
    if (commit && commit.files && commit.files.length) FridayMap.highlightPaths(commit.files);
    else FridayMap.clearHighlight();
  },

  playTimeline() {
    const commits = ((this.history && this.history.commits) || []).slice(0, 10);
    if (!commits.length) return;
    let index = 0;
    clearInterval(this.playTimer);
    this.playTimer = setInterval(() => {
      if (index >= commits.length) {
        clearInterval(this.playTimer);
        return;
      }
      document.getElementById("timeline-range").value = index;
      this.scrub(index);
      index += 1;
    }, 900);
  },

  showThread(payload) {
    const panel = document.getElementById("thread");
    const body = document.getElementById("thread-body");
    panel.hidden = false;
    document.getElementById("activity-empty").hidden = true;
    this.showTab("activity");
    body.replaceChildren();
    const title = document.createElement("p");
    title.textContent = payload.title || "Thread";
    body.appendChild(title);
    (payload.thread || []).forEach((post) => {
      const article = document.createElement("article");
      article.className = "thread-post";
      const who = document.createElement("p");
      who.className = "muted";
      who.textContent = `${post.author} · ${post.date || ""} · ${post.kind}`;
      const text = document.createElement("p");
      text.textContent = post.body || "";
      article.appendChild(who);
      article.appendChild(text);
      body.appendChild(article);
    });
  },

  showNoise(payload) {
    const panel = document.getElementById("noise");
    const body = document.getElementById("noise-body");
    panel.hidden = false;
    document.getElementById("activity-empty").hidden = true;
    this.showTab("activity");
    body.replaceChildren();
    const note = document.createElement("p");
    note.textContent = payload.say || "";
    body.appendChild(note);
    const ul = document.createElement("ul");
    ul.className = "links";
    (payload.candidates || []).forEach((item) => {
      const li = document.createElement("li");
      const noul = item.spam_noul == null ? "" : ` · Jev ${Math.round(item.spam_noul * 100)}%`;
      li.textContent = `${item.login} · ${item.count}${noul} · ${(item.reasons || []).join(", ")}`;
      ul.appendChild(li);
    });
    body.appendChild(ul);
  },

  trail(step) {
    if (!step) return;
    this.trailItems.push(step);
    const summary = document.getElementById("trail-summary");
    const label = step.detail || step.name || step.step || "step";
    summary.textContent = String(label).slice(0, 140);
    const body = document.getElementById("trail-body");
    const details = document.createElement("details");
    details.className = "trail-step";
    const line = document.createElement("summary");
    const kind = document.createElement("span");
    kind.className = "pill";
    kind.textContent = step.step || step.name || "step";
    const text = document.createElement("span");
    text.textContent = String(step.detail || label).slice(0, 110);
    line.appendChild(kind);
    line.appendChild(text);
    const pre = document.createElement("pre");
    pre.textContent = JSON.stringify(step, null, 2);
    details.appendChild(line);
    details.appendChild(pre);
    body.prepend(details);
  },

  async toggleVoice() {
    const buttons = document.querySelectorAll(".voice-btn");
    if (FridayVoice.ready) {
      FridayVoice.disconnect();
      this.setVoice("Say a repository, or paste a GitHub link.", false);
      return;
    }
    buttons.forEach((button) => { button.disabled = true; });
    this.setVoice("Connecting to the Voice Agent…", false);
    try {
      await FridayVoice.primeAudio();
      await FridayVoice.connect();
    } catch (err) {
      this.showError(err.message || "Voice connection failed. The text fallback still works.");
      this.setVoice("Voice Agent is not connected.", false);
    } finally {
      buttons.forEach((button) => { button.disabled = false; });
    }
  },

  setLevel(level) {
    const meter = document.getElementById("mic-level");
    if (!meter) return;
    const bar = meter.querySelector("i");
    if (level == null) {
      meter.hidden = true;
      if (bar) bar.style.width = "0";
      return;
    }
    meter.hidden = false;
    if (bar) bar.style.width = `${Math.max(4, Math.min(100, Math.round(level * 400)))}%`;
  },

  setVoice(text, on) {
    const status = document.getElementById("voice-status");
    const meter = document.getElementById("mic-level");
    status.textContent = text;
    if (meter) status.appendChild(meter);
    document.querySelectorAll(".voice-btn").forEach((button) => {
      button.setAttribute("aria-pressed", on ? "true" : "false");
      button.setAttribute("aria-label", on ? "Stop" : "Listen");
    });
  },

  caption(who, text) {
    document.getElementById(who === "user" ? "user-caption" : "agent-caption").textContent = text;
  },

  activity(text) {
    document.getElementById("activity-line").textContent = text;
  },

  showError(message) {
    const banner = document.getElementById("error-banner");
    banner.hidden = false;
    banner.textContent = message;
  },

  hideError() {
    const banner = document.getElementById("error-banner");
    banner.hidden = true;
    banner.textContent = "";
  },

  toggleRecord() {
    if (this.recording) this.stopRecord();
    else this.startRecord();
  },

  async startRecord() {
    this.chunks = [];
    try {
      this.mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (err) {
      this.showError("Microphone access was denied.");
      return;
    }
    this.recorder = new MediaRecorder(this.mediaStream);
    this.recorder.ondataavailable = (event) => { if (event.data.size) this.chunks.push(event.data); };
    this.recorder.onstop = () => this.finishRecord();
    this.recorder.start();
    this.recording = true;
    document.getElementById("status-line").textContent = "Recording — click again to stop";
  },

  stopRecord() {
    if (this.recorder && this.recorder.state !== "inactive") this.recorder.stop();
    if (this.mediaStream) this.mediaStream.getTracks().forEach((track) => track.stop());
    this.recording = false;
  },

  async finishRecord() {
    document.getElementById("status-line").textContent = "Transcribing with Sync…";
    const blob = new Blob(this.chunks, { type: (this.recorder && this.recorder.mimeType) || "audio/webm" });
    const ctx = new AudioContext();
    const decoded = await ctx.decodeAudioData(await blob.arrayBuffer());
    ctx.close();
    const wav = this.encodeWav(decoded);
    const form = new FormData();
    form.append("audio", wav, "instruction.wav");
    const response = await fetch("/api/run", { method: "POST", body: form });
    const data = await response.json();
    document.getElementById("status-line").textContent = "Uses Sync transcription if the live socket is down.";
    const out = document.getElementById("fallback-summary");
    if (!response.ok) {
      this.showError(data.error || "Fallback failed.");
      return;
    }
    out.textContent = `${data.transcript}\n\n${data.summary || ""}`;
  },

  encodeWav(audioBuffer) {
    const samples = audioBuffer.getChannelData(0);
    const dataSize = samples.length * 2;
    const buffer = new ArrayBuffer(44 + dataSize);
    const view = new DataView(buffer);
    const write = (offset, text) => { for (let i = 0; i < text.length; i++) view.setUint8(offset + i, text.charCodeAt(i)); };
    write(0, "RIFF");
    view.setUint32(4, 36 + dataSize, true);
    write(8, "WAVE");
    write(12, "fmt ");
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, 1, true);
    view.setUint32(24, audioBuffer.sampleRate, true);
    view.setUint32(28, audioBuffer.sampleRate * 2, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    write(36, "data");
    view.setUint32(40, dataSize, true);
    let offset = 44;
    for (let i = 0; i < samples.length; i++) {
      const clamped = Math.max(-1, Math.min(1, samples[i]));
      view.setInt16(offset, clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff, true);
      offset += 2;
    }
    return new Blob([buffer], { type: "audio/wav" });
  },
};

document.addEventListener("DOMContentLoaded", () => FridayApp.init());
