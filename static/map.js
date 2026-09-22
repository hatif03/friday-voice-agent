/* Circle-pack fingerprint. Folders are districts. Leaves are files. */
const FridayMap = {
  data: null,
  positions: new Map(),
  sizeMode: "bytes",
  showHeat: false,
  showLabels: true,
  showImports: true,
  pinned: null,
  selected: null,
  highlight: null,
  folderFocus: null,
  expanded: new Set(),

  mount(payload) {
    this.data = payload;
    this.highlight = null;
    this.pinned = null;
    this.expanded = new Set();
    this.folderFocus = null;
    this.selected = null;
    const empty = document.getElementById("map-empty");
    if (empty) empty.remove();
    const svg = document.getElementById("map-svg");
    svg.hidden = false;
    this.draw();
    requestAnimationFrame(() => {
      if (this.data) this.draw();
    });
    this.stats();
    this.legend();
  },

  clearHighlight() {
    this.highlight = null;
    if (this.data) this.draw();
  },

  draw() {
    const host = document.getElementById("map-host");
    const width = host.clientWidth || 800;
    const height = host.clientHeight || 640;
    const svg = d3.select("#map-svg");
    svg.attr("viewBox", `0 0 ${width} ${height}`).attr("xmlns", "http://www.w3.org/2000/svg");
    svg.selectAll("*").remove();
    const root = d3.hierarchy(this.data.tree).sum((d) => {
      if (d.children) return 0;
      const name = `${d.path || ""} ${d.name || ""}`.toLowerCase();
      const bulky = /package-lock\.json|yarn\.lock|pnpm-lock|cargo\.lock|composer\.lock|\.min\.(js|css)/.test(name);
      let value = this.sizeMode === "loc" ? Math.max(d.loc || 1, 1) : Math.max(d.size || 1, 1);
      if (bulky) value = Math.min(value, 600);
      return Math.pow(value, 0.42);
    });
    d3.pack().size([width, height]).padding(7)(root);
    this.positions = new Map();
    root.each((node) => {
      if (node.data.path) this.positions.set(node.data.path, node);
    });
    const g = svg.append("g");
    const zoom = d3.zoom().scaleExtent([0.4, 8]).on("zoom", (event) => g.attr("transform", event.transform));
    svg.call(zoom);
    this.zoom = zoom;
    this.svg = svg;
    this.g = g;

    const nodes = g.selectAll("g.node")
      .data(root.descendants().filter((d) => d.depth > 0))
      .join("g")
      .attr("class", (d) => this.nodeClass(d))
      .attr("transform", (d) => `translate(${d.x},${d.y})`)
      .on("click", (event, d) => {
        event.stopPropagation();
        if (d.data.folder) this.enterFolder(d.data.path);
        else if (d.data.path) {
          this.selected = d.data.path;
          this.pinned = this.showImports ? d.data.path : null;
          this.paintEdges();
          this.pulse(d.data.path);
          this.reveal(d.data.path);
          this.renderTree();
          FridayApp.inspect(d.data.path);
          FridayApp.trail({ step: "focus", detail: d.data.path });
          this.markSelected();
        }
      })
      .on("dblclick", (event, d) => {
        event.stopPropagation();
        if (d.data.folder) this.enterFolder(d.data.path);
      })
      .on("mousemove", (event, d) => this.tooltip(event, d))
      .on("mouseenter", (_event, d) => this.hover(d))
      .on("mouseleave", () => {
        this.hideTooltip();
        this.paintEdges();
      });

    svg.on("click", () => this.stepOut());

    nodes.append("circle")
      .attr("r", (d) => d.r)
      .attr("fill", (d) => d.data.folder ? "none" : (d.data.color || "#9aa3b5"))
      .attr("fill-opacity", (d) => d.data.folder ? 1 : this.opacity(d))
      .attr("stroke", (d) => d.data.folder ? "rgba(41,8,25,0.28)" : this.stroke(d.data))
      .attr("stroke-width", (d) => {
        if (d.data.folder) return 1;
        const mark = d.data.landmark || {};
        if (mark.entry || mark.core || mark.hotspot) return 1.5;
        return 0;
      });

    if (this.showLabels) this.rimLabels(nodes);
    this.edgeLayer = g.insert("g", ":first-child").attr("class", "edges");
    this.paintEdges();
    this.markSelected();
  },

  rimLabels(nodes) {
    let serial = 0;
    nodes.filter((d) => d.data.folder && d.r > 36).each(function label(d) {
      const id = `rim-label-${serial}`;
      serial += 1;
      const radius = Math.max(8, d.r - 1);
      const host = d3.select(this);
      host.append("path")
        .attr("id", id)
        .attr("class", "rim-path")
        .attr("fill", "none")
        .attr("d", `M 0 ${radius} A ${radius} ${radius} 0 0 1 0 ${-radius} A ${radius} ${radius} 0 0 1 0 ${radius}`);
      host.append("text")
        .attr("class", "node-label")
        .attr("text-anchor", "middle")
        .style("font-size", d.r > 90 ? "14px" : "12px")
        .append("textPath")
        .attr("href", `#${id}`)
        .attr("startOffset", "50%")
        .text(d.data.name);
    });
  },

  nodeClass(d) {
    const classes = ["node"];
    if (d.data.path && (d.data.path === this.selected || d.data.path === this.pulsePath)) classes.push("is-selected");
    if (d.data.path && d.data.path === this.pulsePath) classes.push("is-pulse");
    if (this.highlight && d.data.path && this.highlight.has(d.data.path)) classes.push("is-match");
    return classes.join(" ");
  },

  opacity(d) {
    if (this.pulsePath) {
      const hit = d.data.path === this.pulsePath;
      if (d.data.folder) return hit ? 0.28 : 0.07;
      return hit ? 0.95 : 0.16;
    }
    if (d.data.folder) return 0.16;
    const dim = this.highlight && this.highlight.size && !(d.data.path && this.highlight.has(d.data.path));
    if (dim) return 0.12;
    if (!this.showHeat) return 0.9;
    const heat = d.data.heat || 0;
    return heat ? Math.min(1, 0.35 + heat * 0.2) : 0.22;
  },

  stroke(data) {
    const mark = data.landmark || {};
    if (mark.entry) return "#22d3ee";
    if (mark.core) return "#12141a";
    if (mark.hotspot) return "#ff832b";
    return "rgba(18,20,26,0.15)";
  },

  hover(node) {
    if (this.pinned || !this.showImports) return;
    this.drawEdges(node.data.path);
  },

  paintEdges() {
    if (!this.edgeLayer) return;
    this.edgeLayer.selectAll("line").remove();
    if (this.pinned && this.showImports) this.drawEdges(this.pinned);
  },

  drawEdges(path) {
    if (!path || !this.data || !this.edgeLayer) return;
    const file = this.data.files[path];
    if (!file) return;
    const links = [...(file.imports || []), ...(file.imported_by || [])];
    const here = this.positions.get(path);
    if (!here) return;
    const lines = links.map((other) => {
      const target = this.positions.get(other);
      if (!target) return null;
      return { x1: here.x, y1: here.y, x2: target.x, y2: target.y };
    }).filter(Boolean);
    this.edgeLayer.selectAll("line").data(lines).join("line")
      .attr("x1", (d) => d.x1).attr("y1", (d) => d.y1)
      .attr("x2", (d) => d.x2).attr("y2", (d) => d.y2)
      .attr("stroke", "#0d7a5f").attr("stroke-opacity", 0.75).attr("stroke-width", 1.2);
  },

  tooltip(event, node) {
    const tip = document.getElementById("map-tooltip");
    if (!tip || !node.data.path) return;
    const file = (this.data.files || {})[node.data.path];
    const mark = file && file.landmark ? Object.entries(file.landmark).filter(([, on]) => on).map(([name]) => name).join(", ") : "";
    tip.hidden = false;
    tip.innerHTML = "";
    const title = document.createElement("strong");
    title.textContent = node.data.path;
    tip.appendChild(title);
    const line = document.createElement("div");
    const loc = file ? file.loc : node.data.loc || 0;
    const kind = file ? file.kind : (node.data.folder ? "folder" : "file");
    line.textContent = `${loc} lines · ${kind}${mark ? " · " + mark : ""}`;
    tip.appendChild(line);
    const host = document.getElementById("map-host");
    const rect = host.getBoundingClientRect();
    tip.style.left = `${event.clientX - rect.left + 12}px`;
    tip.style.top = `${event.clientY - rect.top + 12}px`;
  },

  hideTooltip() {
    const tip = document.getElementById("map-tooltip");
    if (tip) tip.hidden = true;
  },

  markSelected() {
    if (!this.g) return;
    this.g.selectAll("g.node")
      .attr("class", (d) => this.nodeClass(d))
      .select("circle")
      .attr("fill-opacity", (d) => this.opacity(d));
  },

  flyTo(path, inspect) {
    const node = this.positions.get(path);
    if (!node || !this.svg) return;
    const host = document.getElementById("map-host");
    const width = host.clientWidth || 800;
    const height = host.clientHeight || 640;
    const scale = Math.max(1.2, Math.min(6, 90 / Math.max(node.r, 8)));
    const transform = d3.zoomIdentity.translate(width / 2, height / 2).scale(scale).translate(-node.x, -node.y);
    this.svg.transition().duration(600).call(this.zoom.transform, transform);
    this.selected = path;
    this.markSelected();
    if (inspect && !node.data.folder) FridayApp.inspect(path);
  },

  focus(path) {
    this.reveal(path);
    this.pulse(path);
    this.flyTo(path, true);
    this.renderTree();
    FridayApp.trail({ step: "focus", detail: path });
  },

  reveal(path) {
    const parts = (path || "").split("/").slice(0, -1);
    for (let index = 1; index <= parts.length; index += 1) {
      this.expanded.add(parts.slice(0, index).join("/"));
    }
  },

  toggleFolder(path) {
    if (this.expanded.has(path)) this.expanded.delete(path);
    else this.expanded.add(path);
    this.renderTree();
  },

  enterFolder(path) {
    if (!path) return;
    this.folderFocus = path;
    this.expanded.add(path);
    this.reveal(path);
    this.pulse(path);
    this.flyTo(path, false);
    this.renderTree();
    this.renderCrumb();
  },

  stepOut() {
    if (!this.folderFocus) {
      this.resetZoom();
      this.renderCrumb();
      return;
    }
    const parts = this.folderFocus.split("/");
    parts.pop();
    this.folderFocus = parts.join("/") || null;
    if (this.folderFocus) this.flyTo(this.folderFocus, false);
    else this.resetZoom();
    this.renderTree();
    this.renderCrumb();
  },

  pulse(path) {
    this.pulsePath = path;
    this.markSelected();
    clearTimeout(this.pulseTimer);
    this.pulseTimer = setTimeout(() => {
      if (this.pulsePath === path) this.pulsePath = null;
      this.markSelected();
    }, 1400);
  },

  renderCrumb() {
    const el = document.getElementById("map-crumb");
    if (!el || !this.data) return;
    el.replaceChildren();
    const parts = [{ label: this.data.repo || this.data.slug, path: "" }];
    if (this.folderFocus) {
      const bits = this.folderFocus.split("/");
      bits.forEach((bit, index) => {
        parts.push({ label: bit, path: bits.slice(0, index + 1).join("/") });
      });
    }
    parts.forEach((part, index) => {
      if (index) {
        const sep = document.createElement("span");
        sep.textContent = " / ";
        el.appendChild(sep);
      }
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = part.label;
      button.addEventListener("click", () => {
        if (!part.path) {
          this.folderFocus = null;
          this.resetZoom();
          this.renderTree();
          this.renderCrumb();
        } else {
          this.folderFocus = part.path;
          this.flyTo(part.path, false);
          this.renderTree();
          this.renderCrumb();
        }
      });
      el.appendChild(button);
    });
  },

  zoomBy(factor) {
    if (!this.svg || !this.zoom) return;
    this.svg.transition().duration(200).call(this.zoom.scaleBy, factor);
  },

  resetZoom() {
    if (!this.svg || !this.zoom) return;
    this.folderFocus = null;
    this.svg.transition().duration(400).call(this.zoom.transform, d3.zoomIdentity);
    this.renderTree();
    this.renderCrumb();
  },

  search(query) {
    const needle = (query || "").trim().toLowerCase();
    if (!needle || !this.data) {
      this.highlight = null;
      if (this.data) this.draw();
      return 0;
    }
    const hits = Object.keys(this.data.files).filter((path) => path.toLowerCase().includes(needle));
    this.highlight = new Set(hits);
    this.draw();
    if (hits.length === 1) {
      this.pulse(hits[0]);
      this.flyTo(hits[0], false);
    } else if (hits[0]) this.pulse(hits[0]);
    return hits.length;
  },

  highlightPaths(paths) {
    const list = paths || [];
    this.highlight = new Set(list);
    this.showHeat = false;
    this.draw();
    if (list[0]) {
      this.pulse(list[0]);
      this.flyTo(list[0], false);
    }
  },

  stats() {
    const s = this.data.stats || {};
    const el = document.getElementById("stats");
    if (el) {
      el.replaceChildren();
      const dl = document.createElement("dl");
      dl.className = "stat-list";
      [
        ["Files", s.files || 0],
        ["Lines", s.loc || 0],
        ["Folders", s.folders || 0],
        ["Imports", s.edges || 0],
      ].forEach(([label, value]) => {
        const wrap = document.createElement("div");
        const dt = document.createElement("dt");
        dt.textContent = label;
        const dd = document.createElement("dd");
        dd.textContent = Number(value).toLocaleString();
        wrap.appendChild(dt);
        wrap.appendChild(dd);
        dl.appendChild(wrap);
      });
      const authors = document.createElement("div");
      const dt = document.createElement("dt");
      dt.textContent = "Authors";
      const dd = document.createElement("dd");
      dd.id = "stat-authors";
      dd.textContent = "—";
      authors.appendChild(dt);
      authors.appendChild(dd);
      dl.appendChild(authors);
      el.appendChild(dl);
    }
    const mix = document.getElementById("lang-mix");
    const names = document.getElementById("lang-names");
    if (!mix) return;
    mix.replaceChildren();
    if (names) names.replaceChildren();
    const colors = ["#6473F2", "#FFC312", "#22a6b3", "#0d7a5f", "#d64550", "#9aa3b5"];
    (s.languages || []).forEach((lang, index) => {
      const bar = document.createElement("span");
      bar.style.width = `${Math.max(2, lang.share * 100)}%`;
      bar.style.background = colors[index % colors.length];
      bar.title = `${lang.name} ${lang.count}`;
      mix.appendChild(bar);
      if (names && index < 4) {
        const bit = document.createElement("span");
        bit.textContent = index ? ` · ${lang.name}` : lang.name;
        names.appendChild(bit);
      }
    });
  },

  legend() {
    const el = document.getElementById("legend");
    if (!el) return;
    el.replaceChildren();
    [
      ["#9aa3b5", "Radius", "How large the file is."],
      ["#6473F2", "Colour", "The folder and the language."],
      ["#22d3ee", "Entry ring", "A place the program starts."],
      ["#12141a", "Core ring", "Imported by many files."],
      ["#ff832b", "Hotspot ring", "A long file that changes often."],
      ["#0d7a5f", "Import arc", "Click a file to pin what it links to."],
    ].forEach(([color, label, detail]) => {
      const li = document.createElement("li");
      const swatch = document.createElement("span");
      swatch.style.cssText = `display:inline-block;width:10px;height:10px;border-radius:50%;background:${color};margin-top:4px;flex:none`;
      const text = document.createElement("span");
      text.innerHTML = `<strong>${label}</strong><small>${detail}</small>`;
      li.appendChild(swatch);
      li.appendChild(text);
      el.appendChild(li);
    });
    this.renderTree();
    this.renderCrumb();
  },

  fileCount(node) {
    if (!node.children) return node.folder ? 0 : 1;
    return node.children.reduce((sum, child) => sum + this.fileCount(child), 0);
  },

  renderTree() {
    const folders = document.getElementById("folder-list");
    if (!folders || !this.data) return;
    folders.replaceChildren();
    const walk = (nodes, parent, depth) => {
      const ordered = nodes.slice().sort((left, right) => {
        if (!!left.folder !== !!right.folder) return left.folder ? -1 : 1;
        return String(left.name || "").localeCompare(String(right.name || ""));
      });
      ordered.slice(0, 200).forEach((node) => {
        const li = document.createElement("li");
        li.className = "tree-item";
        const row = document.createElement("div");
        row.className = `tree-row${node.folder ? " is-folder" : " is-file"}`;
        if (node.path && node.path === this.selected) row.classList.add("is-current");
        if (node.folder && node.path === this.folderFocus) row.classList.add("is-current");
        row.style.paddingLeft = `${depth * 12}px`;

        if (node.folder) {
          const twist = document.createElement("button");
          twist.type = "button";
          twist.className = "tree-twist";
          const open = this.expanded.has(node.path);
          twist.setAttribute("aria-expanded", open ? "true" : "false");
          twist.setAttribute("aria-label", open ? `Collapse ${node.name}` : `Expand ${node.name}`);
          twist.innerHTML = '<svg class="tree-chevron" viewBox="0 0 16 16" aria-hidden="true"><path d="M6 4l4 4-4 4" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>';
          twist.addEventListener("click", (event) => {
            event.stopPropagation();
            this.toggleFolder(node.path);
          });
          row.appendChild(twist);
        } else {
          const spacer = document.createElement("span");
          spacer.className = "tree-twist tree-spacer";
          spacer.setAttribute("aria-hidden", "true");
          row.appendChild(spacer);
        }

        const label = document.createElement("button");
        label.type = "button";
        label.className = "tree-label";
        const glyph = document.createElement("span");
        glyph.className = node.folder ? "tree-glyph is-folder" : "tree-glyph is-file";
        glyph.setAttribute("aria-hidden", "true");
        const name = document.createElement("span");
        name.className = "tree-name";
        name.textContent = node.name;
        label.appendChild(glyph);
        label.appendChild(name);
        label.addEventListener("click", () => {
          if (node.folder) this.enterFolder(node.path);
          else this.focus(node.path);
        });
        row.appendChild(label);
        if (node.folder) {
          const count = document.createElement("span");
          count.className = "tree-count";
          count.textContent = String(this.fileCount(node));
          row.appendChild(count);
        }
        li.appendChild(row);
        parent.appendChild(li);
        if (node.folder && node.children && this.expanded.has(node.path)) {
          const nested = document.createElement("ul");
          nested.className = "tree-children";
          li.appendChild(nested);
          walk(node.children, nested, depth + 1);
        }
      });
    };
    walk((this.data.tree && this.data.tree.children) || [], folders, 0);
  },
};
