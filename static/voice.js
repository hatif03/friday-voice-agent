/* Browser side of the AssemblyAI Voice Agent socket. Tools run on our server. */
const FridayVoice = {
  ws: null,
  audio: null,
  playTime: 0,
  sources: [],
  lastEvent: null,
  pending: [],
  userTranscript: "",
  transcriptId: "",
  capturing: false,
  stream: null,

  async primeAudio() {
    if (!this.audio || this.audio.state === "closed") {
      try {
        this.audio = new AudioContext({ sampleRate: 24000 });
      } catch (err) {
        this.audio = new AudioContext();
      }
    }
    if (this.audio.state === "suspended") await this.audio.resume();
  },

  async connect() {
    const response = await fetch("/api/voice/session");
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Could not start the voice session.");
    this.session = data.session;
    this.configure = data.configure || null;
    this.holdTools = new Set(data.hold_tools || []);
    await this.openSocket(data.ws_url);
  },

  openSocket(url) {
    return new Promise((resolve, reject) => {
      const ws = new WebSocket(url);
      this.ws = ws;
      ws.onopen = () => {
        ws.send(JSON.stringify(this.session));
      };
      ws.onerror = () => reject(new Error("Voice socket failed."));
      ws.onclose = () => {
        this.stopCapture();
        FridayApp.setVoice("Voice Agent disconnected.", false);
      };
      ws.onmessage = (event) => {
        const message = JSON.parse(event.data);
        this.onEvent(message);
        if (message.type === "session.ready") resolve();
        if (message.type === "session.error" && !this.ready) reject(new Error(message.error || message.message || "Session error"));
      };
    });
  },

  async onEvent(message) {
    const type = message.type;
    if (type === "session.ready") {
      this.ready = true;
      this.lastEvent = type;
      if (this.configure && this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify(this.configure));
        this.configure = null;
      }
      try {
        await this.startCapture();
      } catch (err) {
        FridayApp.setVoice("Microphone did not start.", false);
        FridayApp.showError(err.message || "Microphone did not start.");
        this.disconnect();
        return;
      }
      FridayApp.setVoice("Listening. Interrupt me any time.", true);
      return;
    }
    if (type === "transcript.user.delta") {
      this.userTranscript = message.text || "";
      FridayApp.caption("user", this.userTranscript);
      return;
    }
    if (type === "transcript.user") {
      this.userTranscript = message.text || "";
      this.transcriptId = message.item_id || String(Date.now());
      FridayApp.caption("user", this.userTranscript);
      FridayApp.trail({ step: "heard", detail: this.userTranscript });
      return;
    }
    if (type === "transcript.agent.delta" || type === "transcript.agent") {
      FridayApp.caption("agent", message.text || "");
      if (type === "transcript.agent") FridayApp.trail({ step: "said", detail: message.text || "" });
      if (message.interrupted) this.flushAudio();
      return;
    }
    if (type === "reply.audio") {
      this.enqueueAudio(message.data || message.audio);
      return;
    }
    if (type === "input.speech.started") {
      this.lastEvent = type;
      this.flushAudio();
      return;
    }
    if (type === "reply.started") {
      this.lastEvent = type;
      return;
    }
    if (type === "tool.call") {
      const hold = !this.holdTools || this.holdTools.size === 0 || this.holdTools.has(message.name);
      if (hold && this.statusLine(message.name)) this.speakStatus(message.name);
      const result = await this.runTool(message);
      const item = { call_id: message.call_id, result, is_error: !!result.is_error };
      if (hold) {
        this.sendResult(item);
      } else {
        this.pending.push(item);
        await this.flushTools();
      }
      return;
    }
    if (type === "reply.done") {
      this.lastEvent = type;
      if (message.status === "interrupted") {
        this.pending = [];
        this.flushAudio();
      } else {
        await this.flushTools();
      }
      return;
    }
    if (type === "session.error") {
      const text = message.message || message.error || "Voice session error.";
      FridayApp.showError(text);
      FridayApp.caption("agent", text);
    }
  },

  statusLine(name) {
    return {
      open_repository: "Opening that repository.",
      review_changes: "Reading the diff.",
      explain_architecture: "Drawing how the pieces fit.",
      scrub_history: "Reading the latest commits.",
      who_touched: "Looking up who wrote this.",
      explain_fix: "Following the fix.",
      read_thread: "Reading the thread.",
      scan_noise: "Checking for repeated issues.",
      scan_security: "Checking the files on the map.",
      ask_repository: "Looking at the files that match.",
    }[name] || "";
  },

  speakStatus(name) {
    const line = this.statusLine(name);
    if (!line) return;
    FridayApp.caption("agent", line);
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
    this.ws.send(JSON.stringify({
      type: "reply.create",
      instructions: `Say only this sentence, then wait for the tool result: ${line}`,
    }));
  },

  sendResult(tool) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
    this.ws.send(JSON.stringify({
      type: "tool.result",
      call_id: tool.call_id,
      result: JSON.stringify(tool.result.result || tool.result),
      is_error: tool.is_error,
    }));
  },

  async flushTools() {
    if (this.lastEvent !== "reply.done" || !this.pending.length || !this.ws) return;
    for (const tool of this.pending) this.sendResult(tool);
    this.pending = [];
  },

  async runTool(message) {
    FridayApp.activity(`Running ${message.name}`);
    let args = message.arguments || {};
    if (typeof args === "string") {
      try { args = JSON.parse(args); } catch (err) { args = {}; }
    }
    const response = await fetch("/api/voice/tool", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: message.name,
        arguments: args,
        user_transcript: this.userTranscript,
        transcript_id: this.transcriptId,
      }),
    });
    const data = await response.json();
    if (data.say) FridayApp.activity(data.say);
    (data.trace || []).forEach((step) => FridayApp.trail(step));
    FridayApp.applyCommands(data.ui_commands || []);
    if ((data.ui_commands || []).some((item) => item.type === "keyterms")) {
      const terms = data.ui_commands.find((item) => item.type === "keyterms").keyterms || [];
      this.updateKeyterms(terms);
    }
    return data;
  },

  updateKeyterms(terms) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
    this.ws.send(JSON.stringify({
      type: "session.update",
      session: { input: { keyterms: terms.slice(0, 100) } },
    }));
  },

  noteLevel(pcm) {
    let sum = 0;
    const step = 8;
    for (let i = 0; i < pcm.length; i += step) sum += Math.abs(pcm[i]);
    const level = sum / Math.max(1, pcm.length / step) / 32768;
    const now = performance.now();
    if (now - (this.lastLevel || 0) < 200) return;
    this.lastLevel = now;
    FridayApp.setLevel(level);
  },

  async startCapture() {
    await this.primeAudio();
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: false, autoGainControl: true },
      });
    } catch (err) {
      const denied = err && (err.name === "NotAllowedError" || err.name === "NotFoundError");
      throw new Error(denied ? "Microphone access was denied." : "Microphone did not start.");
    }
    try {
      await this.audio.audioWorklet.addModule("/static/pcm-worklet.js");
    } catch (err) {
      this.stopCapture();
      throw new Error("Could not start microphone capture.");
    }
    const source = this.audio.createMediaStreamSource(this.stream);
    const node = new AudioWorkletNode(this.audio, "pcm-capture");
    const inputRate = this.audio.sampleRate;
    let carry = new Float32Array(0);
    let pending = new Int16Array(0);
    const frame = 1200;
    node.port.onmessage = (event) => {
      if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
      const incoming = event.data;
      const merged = new Float32Array(carry.length + incoming.length);
      merged.set(carry);
      merged.set(incoming, carry.length);
      const ratio = inputRate / 24000;
      const outLength = Math.floor(merged.length / ratio);
      const usable = Math.floor(outLength * ratio);
      const pcm = new Int16Array(outLength);
      for (let i = 0; i < outLength; i++) {
        const sample = merged[Math.floor(i * ratio)] || 0;
        const clamped = Math.max(-1, Math.min(1, sample));
        pcm[i] = clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff;
      }
      carry = merged.slice(usable);
      if (!pcm.length) return;
      const joined = new Int16Array(pending.length + pcm.length);
      joined.set(pending);
      joined.set(pcm, pending.length);
      let offset = 0;
      while (joined.length - offset >= frame) {
        const slice = joined.subarray(offset, offset + frame);
        const bytes = new Uint8Array(slice.buffer, slice.byteOffset, slice.byteLength);
        let binary = "";
        for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
        this.ws.send(JSON.stringify({ type: "input.audio", audio: btoa(binary) }));
        this.noteLevel(slice);
        offset += frame;
      }
      pending = joined.slice(offset);
    };
    source.connect(node);
    this.captureNode = node;
    this.captureSource = source;
    this.capturing = true;
    FridayApp.setLevel(0);
  },

  enqueueAudio(b64) {
    if (!b64 || !this.audio) return;
    const binary = atob(b64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    const view = new DataView(bytes.buffer);
    const floats = new Float32Array(Math.floor(bytes.length / 2));
    for (let i = 0; i < floats.length; i++) floats[i] = view.getInt16(i * 2, true) / 0x8000;
    const buffer = this.audio.createBuffer(1, floats.length, 24000);
    buffer.copyToChannel(floats, 0);
    const src = this.audio.createBufferSource();
    src.buffer = buffer;
    src.connect(this.audio.destination);
    const now = this.audio.currentTime;
    if (this.playTime < now + 0.02) this.playTime = now + 0.05;
    src.start(this.playTime);
    this.playTime += buffer.duration;
    this.sources.push(src);
  },

  flushAudio() {
    this.sources.forEach((src) => { try { src.stop(); } catch (err) { /* already ended */ } });
    this.sources = [];
    this.playTime = 0;
  },

  stopCapture() {
    if (this.captureSource) {
      try { this.captureSource.disconnect(); } catch (err) { /* already stopped */ }
    }
    if (this.stream) this.stream.getTracks().forEach((track) => track.stop());
    this.stream = null;
    this.captureSource = null;
    this.captureNode = null;
    this.capturing = false;
    FridayApp.setLevel(null);
  },

  disconnect() {
    this.stopCapture();
    this.flushAudio();
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: "session.end" }));
      this.ws.close();
    }
    this.ws = null;
    this.ready = false;
  },
};
