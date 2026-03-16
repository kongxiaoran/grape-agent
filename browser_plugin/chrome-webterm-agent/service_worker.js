const DEFAULT_BRIDGE_URL = "http://127.0.0.1:8766";
const DEFAULT_BRIDGE_TOKEN = "change-me-webterm-bridge-token";
const CAPTURE_DISABLED = true;

const state = {
  bridgeUrl: DEFAULT_BRIDGE_URL,
  token: "",
  activeTabId: null,
  bridgeSessionId: null,
  sessionKey: null,
  lastSuggestion: null,
  autoExecuteLowRisk: false
};

let stateLoaded = false;
const contentReadyByTab = new Map();

async function loadState() {
  const stored = await chrome.storage.local.get([
    "bridgeUrl",
    "token",
    "bridgeSessionId",
    "sessionKey",
    "autoExecuteLowRisk",
    "autoSessionIdentity"
  ]);
  state.bridgeUrl = stored.bridgeUrl || DEFAULT_BRIDGE_URL;
  state.token = stored.token || DEFAULT_BRIDGE_TOKEN;
  state.bridgeSessionId = stored.bridgeSessionId || null;
  state.sessionKey = stored.sessionKey || null;
  // New sidepanel flow does not expose auto-exec toggle; keep disabled by default.
  state.autoExecuteLowRisk = false;
  if (stored.autoExecuteLowRisk) {
    await chrome.storage.local.set({ autoExecuteLowRisk: false });
  }
  stateLoaded = true;
}

async function ensureStateLoaded() {
  if (!stateLoaded) {
    await loadState();
  }
}

function authHeaders() {
  return {
    "Content-Type": "application/json",
    "Authorization": `Bearer ${state.token}`
  };
}

function stringifyError(error) {
  if (error instanceof Error) return error.message || String(error);
  if (typeof error === "object" && error !== null) {
    try {
      return JSON.stringify(error);
    } catch {
      return String(error);
    }
  }
  return String(error);
}

function buildPreview(text, maxChars = 2400) {
  const raw = String(text || "").replace(/\r/g, "");
  if (!raw) return "";
  if (raw.length <= maxChars) return raw;
  const headSize = Math.floor(maxChars * 0.35);
  const tailSize = maxChars - headSize;
  return `${raw.slice(0, headSize)}\n\n...<snip>...\n\n${raw.slice(-tailSize)}`;
}

function randomToken(size = 6) {
  return Math.random().toString(36).slice(2, 2 + size);
}

function disabledSnapshot() {
  return {
    ingestedChars: 0,
    hasOutputRoot: false,
    hasWsBuffer: false,
    hasTermBuffer: false,
    terminalCount: 0,
    preview: "",
    source: "disabled"
  };
}

async function getOrCreateAutoIdentity(forceNew = false) {
  if (!forceNew) {
    const stored = await chrome.storage.local.get(["autoSessionIdentity"]);
    const existing = stored.autoSessionIdentity;
    if (existing && existing.host && existing.scope && existing.user) {
      return existing;
    }
  }
  const suffix = randomToken(8);
  const identity = {
    host: `host-${suffix}.local`,
    scope: `scope-${suffix}`,
    user: `user-${suffix}`
  };
  await chrome.storage.local.set({ autoSessionIdentity: identity });
  return identity;
}

async function callBridge(path, method = "GET", body = null) {
  const url = `${state.bridgeUrl}${path}`;
  const resp = await fetch(url, {
    method,
    headers: authHeaders(),
    body: body ? JSON.stringify(body) : undefined
  });
  const json = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    const detail = typeof json.detail === "string"
      ? json.detail
      : (json.detail ? JSON.stringify(json.detail) : "");
    throw new Error(detail || `Bridge ${resp.status}`);
  }
  return json;
}

async function detectActiveTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab && typeof tab.id === "number") {
    state.activeTabId = tab.id;
  }
  return state.activeTabId;
}

async function sendTabMessage(tabId, payload) {
  return await chrome.tabs.sendMessage(tabId, payload);
}

async function installWsTapInMainWorld(tabId) {
  await chrome.scripting.executeScript({
    target: { tabId, allFrames: true },
    world: "MAIN",
    func: () => {
      if (window.__MINI_AGENT_WS_TAP__) return;
      window.__MINI_AGENT_WS_TAP__ = true;

      const MAX_BUFFER_CHARS = 160000;
      const captureState = window.__MINI_AGENT_CAPTURE_STATE__ || {
        wsBuffer: "",
        termBuffer: "",
        terminals: [],
        terminalMeta: [],
        wsRecvFrames: 0,
        wsRecvBytes: 0,
        guacOps: {},
        lastUpdatedAt: Date.now()
      };
      window.__MINI_AGENT_CAPTURE_STATE__ = captureState;

      const stripAnsi = (text) => String(text || "")
        .replace(/\u001b\[[0-9;?]*[A-Za-z]/g, "")
        .replace(/\u001b\][^\u0007]*(\u0007|\u001b\\)/g, "")
        .replace(/\u001b[@-_]/g, "");

      const normalize = (text) => stripAnsi(text)
        .replace(/\r/g, "\n")
        .replace(/[^\x09\x0A\x0D\x20-\x7E]/g, " ")
        .replace(/\n{3,}/g, "\n\n")
        .trim();

      const emitWs = (text) => {
        if (!text) return;
        try {
          window.dispatchEvent(new CustomEvent("grape-agent-ws-output", { detail: { text: String(text) } }));
        } catch {
          // ignored
        }
      };

      const emitTerm = (text) => {
        if (!text) return;
        try {
          window.dispatchEvent(new CustomEvent("grape-agent-term-output", { detail: { text: String(text) } }));
        } catch {
          // ignored
        }
      };

      const decode = (payload) => {
        if (payload == null) return "";
        if (typeof payload === "string") return payload;
        if (payload instanceof ArrayBuffer) {
          try {
            return new TextDecoder("utf-8").decode(payload);
          } catch {
            return "";
          }
        }
        if (ArrayBuffer.isView(payload)) {
          try {
            return new TextDecoder("utf-8").decode(payload);
          } catch {
            return "";
          }
        }
        if (payload instanceof Blob) {
          payload.text().then(emitWs).catch(() => {});
          return "";
        }
        try {
          return String(payload);
        } catch {
          return "";
        }
      };

      const estimatePayloadSize = (payload) => {
        try {
          if (payload == null) return 0;
          if (typeof payload === "string") return payload.length;
          if (payload instanceof ArrayBuffer) return payload.byteLength || 0;
          if (ArrayBuffer.isView(payload)) return payload.byteLength || 0;
          if (payload instanceof Blob) return payload.size || 0;
          return String(payload).length;
        } catch {
          return 0;
        }
      };

      const parseGuacOpcodes = (text, maxOps = 40) => {
        const src = String(text || "");
        const ops = [];
        let i = 0;

        const readElement = () => {
          let num = "";
          while (i < src.length && /[0-9]/.test(src[i])) {
            num += src[i];
            i += 1;
          }
          if (!num || src[i] !== ".") return null;
          i += 1;
          const n = Number(num);
          if (!Number.isFinite(n) || n < 0) return null;
          const val = src.slice(i, i + n);
          i += n;
          return val;
        };

        while (i < src.length && ops.length < maxOps) {
          const first = readElement();
          if (first == null) break;
          ops.push(first);
          while (i < src.length && src[i] !== ";") {
            if (src[i] === ",") {
              i += 1;
              readElement();
              continue;
            }
            i += 1;
          }
          if (src[i] === ";") i += 1;
        }
        return ops;
      };

      const isLikelyNoise = (text) => {
        const s = String(text || "").trim();
        if (!s) return true;
        if (/^\d+\.,\d+\.(ping|pong|noop|heartbeat)\b/i.test(s)) return true;
        if (/^(ping|pong|heartbeat|keepalive)$/i.test(s)) return true;
        if (/^[0-9.,;:_-]+$/.test(s) && s.length < 120) return true;
        if (/ping/i.test(s) && s.length < 160 && !/\n/.test(s)) return true;
        return false;
      };

      const appendBuffer = (key, text) => {
        const cleaned = normalize(text);
        if (!cleaned) return;
        if (isLikelyNoise(cleaned)) return;
        captureState[key] = `${captureState[key]}\n${cleaned}`.trim();
        if (captureState[key].length > MAX_BUFFER_CHARS) {
          captureState[key] = captureState[key].slice(-MAX_BUFFER_CHARS);
        }
        captureState.lastUpdatedAt = Date.now();
      };

      const isDocumentLike = (obj) => {
        try {
          if (!obj) return false;
          if (obj === window || obj === document) return true;
          const ctor = String(obj?.constructor?.name || "");
          if (ctor === "HTMLDocument" || ctor === "Document" || ctor === "Window") return true;
          if (typeof obj?.querySelector === "function" && typeof obj?.createElement === "function") return true;
          return false;
        } catch {
          return false;
        }
      };

      const isTerminalLike = (obj) => {
        if (!obj || typeof obj !== "object") return false;
        if (isDocumentLike(obj)) return false;

        const hasWrite = typeof obj.write === "function";
        const hasWriteln = typeof obj.writeln === "function";
        if (!hasWrite && !hasWriteln) return false;

        const ctor = String(obj?.constructor?.name || "");
        if (/terminal|xterm/i.test(ctor)) return true;

        const hasBuffer = Boolean(obj?.buffer?.active || obj?._core?.buffer || obj?._core?._bufferService?.buffer);
        const hasTerminalApi = (
          typeof obj?.loadAddon === "function" ||
          typeof obj?.onData === "function" ||
          typeof obj?.paste === "function" ||
          typeof obj?.reset === "function" ||
          typeof obj?.selectAll === "function"
        );
        const hasRowsCols = (typeof obj?.rows === "number" && typeof obj?.cols === "number");
        const hasOpenFocus = (typeof obj?.open === "function" && typeof obj?.focus === "function");
        return Boolean(hasBuffer || hasTerminalApi || hasRowsCols || hasOpenFocus);
      };

      const registerTerminal = (term) => {
        if (!term || typeof term !== "object") return;
        if (!isTerminalLike(term)) return;
        if (!Array.isArray(captureState.terminals)) {
          captureState.terminals = [];
        }
        if (!Array.isArray(captureState.terminalMeta)) {
          captureState.terminalMeta = [];
        }
        if (captureState.terminals.includes(term)) return;
        captureState.terminals.push(term);
        try {
          const meta = {
            ctor: String(term?.constructor?.name || ""),
            has_write: typeof term?.write === "function",
            has_writeln: typeof term?.writeln === "function",
            has_select_all: typeof term?.selectAll === "function",
            has_get_selection: typeof term?.getSelection === "function",
            has_buffer_active: Boolean(term?.buffer?.active),
            has_core: Boolean(term?._core),
            has_open: typeof term?.open === "function",
            has_rows_cols: (typeof term?.rows === "number" && typeof term?.cols === "number"),
            has_on_data: typeof term?.onData === "function",
            has_load_addon: typeof term?.loadAddon === "function"
          };
          captureState.terminalMeta.push(meta);
          if (captureState.terminalMeta.length > 8) {
            captureState.terminalMeta = captureState.terminalMeta.slice(-8);
          }
        } catch {
          // ignored
        }
      };

      const tapMessageData = (data, direction) => {
        if (direction !== "recv") return;
        captureState.wsRecvFrames += 1;
        captureState.wsRecvBytes += estimatePayloadSize(data);
        captureState.lastUpdatedAt = Date.now();

        const out = decode(data);
        if (!out) return;
        const opcodes = parseGuacOpcodes(out, 20);
        for (const op of opcodes) {
          const key = String(op || "").trim();
          if (!key) continue;
          captureState.guacOps[key] = Number(captureState.guacOps[key] || 0) + 1;
        }

        if (isLikelyNoise(out)) return;
        appendBuffer("wsBuffer", out);
        emitWs(out);
      };

      const rawSend = WebSocket.prototype.send;
      WebSocket.prototype.send = function (data) {
        try {
          tapMessageData(data, "send");
        } catch {
          // ignored
        }
        return rawSend.apply(this, arguments);
      };

      const rawDispatchEvent = WebSocket.prototype.dispatchEvent;
      WebSocket.prototype.dispatchEvent = function (event) {
        try {
          if (event && event.type === "message") {
            tapMessageData(event.data, "recv");
          }
        } catch {
          // ignored
        }
        return rawDispatchEvent.apply(this, arguments);
      };

      const hookTerminalInstance = (term) => {
        if (!term || typeof term !== "object") return;
        if (!isTerminalLike(term)) return;
        if (term.__MINI_AGENT_TERM_HOOKED__) return;
        const hasWrite = typeof term?.write === "function";
        const hasWriteln = typeof term?.writeln === "function";
        if (!hasWrite && !hasWriteln) return;
        registerTerminal(term);

        if (hasWrite) {
          const rawWrite = term.write.bind(term);
          term.write = function (data, ...args) {
            try {
              appendBuffer("termBuffer", data);
              emitTerm(data);
            } catch {
              // ignored
            }
            return rawWrite(data, ...args);
          };
        }

        if (hasWriteln) {
          const rawWriteln = term.writeln.bind(term);
          term.writeln = function (data, ...args) {
            try {
              appendBuffer("termBuffer", data);
              emitTerm(data);
            } catch {
              // ignored
            }
            return rawWriteln(data, ...args);
          };
        }

        Object.defineProperty(term, "__MINI_AGENT_TERM_HOOKED__", {
          value: true,
          configurable: false,
          enumerable: false,
          writable: false
        });
      };

      const hookTerminalPrototype = (Ctor) => {
        if (!Ctor || !Ctor.prototype) return;
        if (Ctor.prototype.__MINI_AGENT_TERM_PROTO_HOOKED__) return;
        if (!/terminal|xterm/i.test(String(Ctor?.name || ""))) return;
        if (typeof Ctor.prototype.write === "function") {
          const rawWrite = Ctor.prototype.write;
          Ctor.prototype.write = function (data, ...args) {
            try {
              appendBuffer("termBuffer", data);
              emitTerm(data);
            } catch {
              // ignored
            }
            return rawWrite.call(this, data, ...args);
          };
        }
        if (typeof Ctor.prototype.writeln === "function") {
          const rawWriteln = Ctor.prototype.writeln;
          Ctor.prototype.writeln = function (data, ...args) {
            try {
              appendBuffer("termBuffer", data);
              emitTerm(data);
            } catch {
              // ignored
            }
            return rawWriteln.call(this, data, ...args);
          };
        }
        Object.defineProperty(Ctor.prototype, "__MINI_AGENT_TERM_PROTO_HOOKED__", {
          value: true,
          configurable: false,
          enumerable: false,
          writable: false
        });
      };

      const tryHookKnownConstructors = () => {
        const candidates = [
          window.Terminal,
          window.XTerm,
          window.XtermTerminal,
          window.xterm && window.xterm.Terminal
        ];
        for (const Ctor of candidates) {
          try {
            hookTerminalPrototype(Ctor);
          } catch {
            // ignored
          }
        }
      };

      const scanGlobalsForTerminals = () => {
        const keys = Object.getOwnPropertyNames(window).filter((k) => /term|xterm|terminal|ssh|pty|console/i.test(k));
        for (const key of keys) {
          let value = null;
          try {
            value = window[key];
          } catch {
            continue;
          }
          if (!value || typeof value !== "object") continue;
          try {
            hookTerminalInstance(value);
          } catch {
            // ignored
          }
          // common nested container patterns
          const nestedKeys = ["terminal", "term", "xterm", "_terminal", "instance", "client", "viewer"];
          for (const nestedKey of nestedKeys) {
            try {
              hookTerminalInstance(value[nestedKey]);
            } catch {
              // ignored
            }
          }
        }
      };

      const scanDomTerminals = () => {
        const roots = document.querySelectorAll(".xterm, .xterm-rows, .xterm-screen, .xterm-accessibility");
        for (const root of roots) {
          const directCandidates = [root.__xterm, root._xterm, root.terminal, root.term];
          for (const candidate of directCandidates) {
            try {
              hookTerminalInstance(candidate);
            } catch {
              // ignored
            }
          }

          const findTerminalInObject = (obj, depth = 0, visited = new WeakSet()) => {
            if (!obj || typeof obj !== "object") return null;
            if (visited.has(obj)) return null;
            visited.add(obj);
            if (isTerminalLike(obj)) return obj;
            if (depth >= 4) return null;
            const keys = Object.keys(obj).slice(0, 40);
            for (const k of keys) {
              let v = null;
              try {
                v = obj[k];
              } catch {
                continue;
              }
              if (!v || typeof v !== "object") continue;
              if (!/term|xterm|terminal|ssh|pty|client|viewer|instance|session|console/i.test(String(k))) {
                continue;
              }
              const hit = findTerminalInObject(v, depth + 1, visited);
              if (hit) return hit;
            }
            return null;
          };

          const reactKeys = Object.getOwnPropertyNames(root).filter((k) => k.startsWith("__reactFiber$") || k.startsWith("__reactProps$"));
          for (const rk of reactKeys) {
            let carrier = null;
            try {
              carrier = root[rk];
            } catch {
              continue;
            }
            const hit = findTerminalInObject(carrier, 0);
            if (hit) {
              try {
                hookTerminalInstance(hit);
              } catch {
                // ignored
              }
            }
          }
        }
      };

      const extractTermText = (term, maxLines) => {
        const lines = [];
        const pushLine = (line) => {
          const s = normalize(line);
          if (s) lines.push(s);
        };

        try {
          if (term?.buffer?.active?.length && typeof term.buffer.active.getLine === "function") {
            const total = term.buffer.active.length;
            const start = Math.max(0, total - maxLines);
            for (let i = start; i < total; i += 1) {
              const line = term.buffer.active.getLine(i);
              if (!line || typeof line.translateToString !== "function") continue;
              pushLine(line.translateToString(true));
            }
            return lines.join("\n");
          }
        } catch {
          // ignored
        }

        try {
          const linesObj = term?._core?.buffer?.lines || term?._core?._bufferService?.buffer?.lines;
          if (linesObj && typeof linesObj.get === "function") {
            const total = Number(linesObj.length || 0);
            const start = Math.max(0, total - maxLines);
            for (let i = start; i < total; i += 1) {
              const line = linesObj.get(i);
              if (!line || typeof line.translateToString !== "function") continue;
              pushLine(line.translateToString(true));
            }
            return lines.join("\n");
          }
        } catch {
          // ignored
        }

        // xterm public API fallback: select visible content then read selection
        try {
          if (typeof term?.selectAll === "function" && typeof term?.getSelection === "function") {
            term.selectAll();
            const selected = normalize(term.getSelection?.() || "");
            if (typeof term?.clearSelection === "function") {
              term.clearSelection();
            }
            if (selected) {
              return selected
                .split("\n")
                .slice(-maxLines)
                .join("\n");
            }
          }
        } catch {
          // ignored
        }

        // Common wrapper fields
        try {
          const wrapperCandidates = [
            term?.terminal,
            term?.term,
            term?.xterm,
            term?._terminal,
            term?.instance
          ];
          for (const candidate of wrapperCandidates) {
            if (!candidate || candidate === term) continue;
            const nested = extractTermText(candidate, maxLines);
            if (nested) return nested;
          }
        } catch {
          // ignored
        }

        return "";
      };

      window.__MINI_AGENT_GET_CAPTURE__ = (maxLines = 300, maxChars = 24000) => {
        const terminalTexts = [];
        for (const term of captureState.terminals || []) {
          try {
            const text = extractTermText(term, maxLines);
            if (text) terminalTexts.push(text);
          } catch {
            // ignored
          }
        }
        const termFromInstances = terminalTexts.sort((a, b) => b.length - a.length)[0] || "";
        const termMerged = normalize(`${termFromInstances}\n${captureState.termBuffer || ""}`);
        const wsMerged = normalize(captureState.wsBuffer || "");
        const trimChars = (s) => (s.length > maxChars ? s.slice(-maxChars) : s);
        return {
          termText: trimChars(termMerged),
          wsText: trimChars(wsMerged),
          termChars: termMerged.length,
          wsChars: wsMerged.length,
          terminalCount: Array.isArray(captureState.terminals) ? captureState.terminals.length : 0,
          terminalMeta: Array.isArray(captureState.terminalMeta) ? captureState.terminalMeta.slice(-5) : [],
          wsRecvFrames: Number(captureState.wsRecvFrames || 0),
          wsRecvBytes: Number(captureState.wsRecvBytes || 0),
          guacOps: captureState.guacOps || {},
          updatedAt: Number(captureState.lastUpdatedAt || 0)
        };
      };

      tryHookKnownConstructors();
      scanGlobalsForTerminals();
      scanDomTerminals();
      setInterval(() => {
        tryHookKnownConstructors();
        scanGlobalsForTerminals();
        scanDomTerminals();
      }, 1500);
    }
  });
}

async function ensureContentReady(tabId) {
  try {
    await installWsTapInMainWorld(tabId);
  } catch {
    // ignored: some pages disallow main world hook
  }

  try {
    const ping = await sendTabMessage(tabId, { type: "ping_content" });
    if (ping && ping.ok) {
      contentReadyByTab.set(tabId, { at: Date.now(), hasOutputRoot: Boolean(ping.has_output_root) });
      return ping;
    }
  } catch {
    // ignored, try dynamic injection once
  }

  try {
    await chrome.scripting.executeScript({
      target: { tabId, allFrames: true },
      files: ["content_script.js"]
    });
  } catch {
    // ignored; next ping will surface failure
  }

  const ping = await sendTabMessage(tabId, { type: "ping_content" });
  if (!ping || !ping.ok) {
    throw new Error("content script not ready on current tab");
  }
  contentReadyByTab.set(tabId, { at: Date.now(), hasOutputRoot: Boolean(ping.has_output_root) });
  return ping;
}

async function captureSnapshotFromTabViaScripting(tabId, maxLines = 280, maxChars = 22000) {
  const results = await chrome.scripting.executeScript({
    target: { tabId, allFrames: true },
    world: "MAIN",
    func: (inMaxLines, inMaxChars) => {
      const selectors = [".xterm-rows", ".xterm-accessibility", ".xterm-accessibility-tree", ".terminal-output", ".terminal", "pre", "code"];
      const normalize = (text) =>
        String(text || "")
          .replace(/\r/g, "")
          .split("\n")
          .map((line) => line.replace(/\u00a0/g, " ").trimEnd())
          .filter((line) => line.trim().length > 0)
          .slice(-inMaxLines)
          .join("\n");

      let domBest = "";
      let hasRoot = false;
      for (const selector of selectors) {
        const nodes = document.querySelectorAll(selector);
        for (const node of nodes) {
          const text = normalize(node.innerText || node.textContent || "");
          if (text.length > domBest.length) {
            domBest = text;
            hasRoot = true;
          }
        }
      }

      const getter = window.__MINI_AGENT_GET_CAPTURE__;
      const capture = (typeof getter === "function")
        ? getter(inMaxLines + 40, inMaxChars + 6000)
        : { termText: "", wsText: "", termChars: 0, wsChars: 0, terminalCount: 0 };
      const termText = normalize(capture.termText || "");
      const wsText = normalize(capture.wsText || "");

      let text = domBest;
      let source = "dom_or_unknown";
      if (termText.length >= wsText.length && termText.length >= domBest.length && termText.length > 0) {
        text = termText;
        source = "xterm_write";
      } else if (wsText.length >= domBest.length && wsText.length > 0) {
        text = wsText;
        source = "ws_protocol";
      }

      const normalized = text.length > inMaxChars ? text.slice(-inMaxChars) : text;
      return {
        text: normalized,
        has_output_root: hasRoot,
        has_term_buffer: termText.length > 0 || Number(capture.termChars || 0) > 0,
        has_ws_buffer: wsText.length > 0 || Number(capture.wsChars || 0) > 0,
        terminal_count: Number(capture.terminalCount || 0),
        source
      };
    },
    args: [maxLines, maxChars]
  });

  let best = {
    text: "",
    has_output_root: false,
    has_term_buffer: false,
    has_ws_buffer: false,
    source: "dom_or_unknown",
    terminal_count: 0
  };
  for (const item of results || []) {
    const result = item?.result || {};
    const text = String(result.text || "");
    if (text.length > best.text.length) {
      best = {
        text,
        has_output_root: Boolean(result.has_output_root),
        has_term_buffer: Boolean(result.has_term_buffer),
        has_ws_buffer: Boolean(result.has_ws_buffer),
        source: String(result.source || "dom_or_unknown"),
        terminal_count: Number(result.terminal_count || 0)
      };
    }
  }
  return best;
}

async function debugCaptureFrames(tabId) {
  const results = await chrome.scripting.executeScript({
    target: { tabId, allFrames: true },
    world: "MAIN",
    func: () => {
      const selectors = [".xterm-rows", ".xterm-accessibility", ".xterm-accessibility-tree", ".terminal-output", ".terminal", "pre", "code"];
      let domBest = "";
      for (const selector of selectors) {
        const nodes = document.querySelectorAll(selector);
        for (const node of nodes) {
          const text = String(node.innerText || node.textContent || "");
          if (text.length > domBest.length) {
            domBest = text;
          }
        }
      }
      const st = window.__MINI_AGENT_CAPTURE_STATE__ || {};
      const getter = window.__MINI_AGENT_GET_CAPTURE__;
      const cap = (typeof getter === "function")
        ? getter(200, 12000)
        : {
            termChars: 0,
            wsChars: 0,
            terminalCount: 0,
            terminalMeta: [],
            wsRecvFrames: 0,
            wsRecvBytes: 0,
            guacOps: {}
          };
      const guacOps = cap.guacOps || {};
      const topOps = Object.entries(guacOps)
        .sort((a, b) => Number(b[1]) - Number(a[1]))
        .slice(0, 8)
        .map(([k, v]) => `${k}:${v}`)
        .join(",");
      const terminalMeta = Array.isArray(cap.terminalMeta) ? cap.terminalMeta : [];
      const metaShort = terminalMeta
        .map((m) => `${m.ctor || "?"}(buf=${m.has_buffer_active ? 1 : 0},sel=${m.has_select_all ? 1 : 0}/${m.has_get_selection ? 1 : 0},core=${m.has_core ? 1 : 0})`)
        .join(" | ");
      return {
        href: location.href,
        title: document.title,
        term_chars: String(st.termBuffer || "").length,
        ws_chars: String(st.wsBuffer || "").length,
        term_snapshot_chars: Number(cap.termChars || 0),
        ws_snapshot_chars: Number(cap.wsChars || 0),
        terminal_count: Number(cap.terminalCount || 0),
        ws_recv_frames: Number(cap.wsRecvFrames || 0),
        ws_recv_bytes: Number(cap.wsRecvBytes || 0),
        guac_top_ops: topOps,
        terminal_meta: metaShort,
        dom_chars: domBest.length,
        has_xterm: Boolean(document.querySelector(".xterm, .xterm-rows, .xterm-accessibility")),
        updated_at: Number(st.lastUpdatedAt || 0)
      };
    }
  });

  return (results || []).map((item) => ({
    frame_id: item.frameId,
    ...item.result
  }));
}

async function injectCommandViaScripting(tabId, command) {
  const results = await chrome.scripting.executeScript({
    target: { tabId, allFrames: true },
    func: (wrapped) => {
      const selectors = [
        "textarea.xterm-helper-textarea",
        ".xterm-helper-textarea",
        "textarea[aria-label='Terminal input']",
        "textarea[data-testid='terminal-input']",
        "textarea"
      ];
      const cleaned = String(wrapped || "").trim();
      if (!cleaned) {
        return { ok: false, error: "empty command", has_input: false };
      }
      let input = null;
      for (const selector of selectors) {
        const found = document.querySelector(selector);
        if (found) {
          input = found;
          break;
        }
      }
      if (!input) {
        return { ok: false, error: "terminal input not found", has_input: false };
      }

      try {
        const payload = cleaned.endsWith("\n") ? cleaned : `${cleaned}\n`;
        input.focus();
        const proto = Object.getPrototypeOf(input);
        const desc = Object.getOwnPropertyDescriptor(proto, "value");
        if (desc && typeof desc.set === "function") {
          desc.set.call(input, payload);
        } else {
          input.value = payload;
        }
        input.dispatchEvent(new Event("input", { bubbles: true }));
        input.dispatchEvent(new Event("change", { bubbles: true }));
        input.dispatchEvent(
          new KeyboardEvent("keydown", {
            key: "Enter",
            code: "Enter",
            bubbles: true
          })
        );
        input.dispatchEvent(
          new KeyboardEvent("keyup", {
            key: "Enter",
            code: "Enter",
            bubbles: true
          })
        );
        return { ok: true, has_input: true };
      } catch (error) {
        return { ok: false, error: String(error), has_input: true };
      }
    },
    args: [command]
  });

  for (const item of results || []) {
    if (item?.result?.ok) {
      return;
    }
  }
  const detail = (results || [])
    .map((item) => item?.result?.error)
    .filter(Boolean)
    .join("; ");
  throw new Error(detail || "inject command failed");
}

async function ingestSnapshotFromActiveTab(reason = "manual") {
  if (!state.bridgeSessionId) return { ingestedChars: 0, hasOutputRoot: false };
  const tabId = await detectActiveTab();
  if (!tabId) return { ingestedChars: 0, hasOutputRoot: false };

  let snapshot = {
    text: "",
    has_output_root: false,
    has_ws_buffer: false,
    has_term_buffer: false,
    source: "dom_or_unknown"
  };
  try {
    await ensureContentReady(tabId);
    snapshot = await captureSnapshotFromTabViaScripting(tabId, 280, 22000);
  } catch {
    try {
      const fromContent = await sendTabMessage(tabId, {
        type: "capture_snapshot",
        maxLines: 280,
        maxChars: 22000
      });
      if (fromContent && fromContent.ok) {
        snapshot = {
          ...snapshot,
          ...fromContent,
          source: fromContent.has_term_buffer
            ? "xterm_write"
            : (fromContent.has_ws_buffer ? "ws_protocol" : "dom_or_unknown")
        };
      }
    } catch {
      // keep empty snapshot
    }
  }

  const text = String(snapshot.text || "").trim();
  if (!text) {
    return {
      ingestedChars: 0,
      hasOutputRoot: Boolean(snapshot.has_output_root),
      hasWsBuffer: Boolean(snapshot.has_ws_buffer),
      hasTermBuffer: Boolean(snapshot.has_term_buffer),
      terminalCount: Number(snapshot.terminal_count || 0),
      preview: "",
      source: String(snapshot.source || "dom_or_unknown")
    };
  }

  await callBridge(`/v1/session/${state.bridgeSessionId}/ingest`, "POST", {
    text,
    stream: "snapshot",
    metadata: { reason }
  });
  return {
    ingestedChars: text.length,
    hasOutputRoot: Boolean(snapshot.has_output_root),
    hasWsBuffer: Boolean(snapshot.has_ws_buffer),
    hasTermBuffer: Boolean(snapshot.has_term_buffer),
    terminalCount: Number(snapshot.terminal_count || 0),
    preview: buildPreview(text),
    source: String(snapshot.source || "dom_or_unknown")
  };
}

async function openSession(payload) {
  const data = await callBridge("/v1/session/open", "POST", payload);
  state.bridgeSessionId = data.bridge_session_id;
  state.sessionKey = data.session_key;
  await chrome.storage.local.set({
    bridgeSessionId: state.bridgeSessionId,
    sessionKey: state.sessionKey
  });
  return data;
}

async function reopenSessionWithIdentity(identity) {
  if (state.bridgeSessionId) {
    try {
      await callBridge(`/v1/session/${state.bridgeSessionId}`, "DELETE");
    } catch {
      // ignored
    }
    state.bridgeSessionId = null;
    state.sessionKey = null;
    await chrome.storage.local.set({ bridgeSessionId: null, sessionKey: null });
  }
  return await openSession({
    host: identity.host,
    scope: identity.scope,
    user: identity.user,
    agent_id: null,
    reuse_existing: false
  });
}

async function ensureAutoSession(forceNew = false) {
  await ensureStateLoaded();

  if (forceNew && state.bridgeSessionId) {
    try {
      await callBridge(`/v1/session/${state.bridgeSessionId}`, "DELETE");
    } catch {
      // ignored
    }
    state.bridgeSessionId = null;
    state.sessionKey = null;
    await chrome.storage.local.set({ bridgeSessionId: null, sessionKey: null });
  }

  if (!forceNew && state.bridgeSessionId) {
    try {
      const stateResp = await callBridge(`/v1/session/${state.bridgeSessionId}/state`, "GET");
      const identity = await getOrCreateAutoIdentity(false);
      const bufferedLines = Number(stateResp?.session?.buffered_lines || 0);
      if (CAPTURE_DISABLED && bufferedLines > 0) {
        const data = await reopenSessionWithIdentity(identity);
        const snapshot = disabledSnapshot();
        return { reused: false, identity, data, snapshot, resetBufferedLines: bufferedLines };
      }
      const snapshot = disabledSnapshot();
      return { reused: true, identity, snapshot };
    } catch {
      state.bridgeSessionId = null;
      state.sessionKey = null;
      await chrome.storage.local.set({ bridgeSessionId: null, sessionKey: null });
    }
  }

  const identity = await getOrCreateAutoIdentity(forceNew);
  const data = await openSession({
    host: identity.host,
    scope: identity.scope,
    user: identity.user,
    agent_id: null,
    reuse_existing: !forceNew
  });
  const snapshot = disabledSnapshot();
  return { reused: false, identity, data, snapshot };
}

function composeQuestion(payload) {
  const customPrompt = String(payload?.customPrompt || "").trim();
  const logBasePath = String(payload?.logBasePath || "").trim();
  const outputFormat = String(payload?.outputFormat || "").trim();
  const userInput = String(payload?.userInput || "").trim();
  const now = new Date();
  const cnDate = new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(now);
  const [yyyy, mm, dd] = cnDate.split("/");
  const todayYYYYMMDD = `${yyyy}${mm}${dd}`;
  const todayYYMMDD = `${yyyy.slice(-2)}${mm}${dd}`;
  const blocks = [];
  blocks.push(
    "【任务模式】用户会把日志片段/报错信息直接粘贴到输入中。请直接分析这些内容并给出排查判断。"
  );
  blocks.push(
    "【输出要求】先给分析结论与判断依据；如果需要继续排查，再给1条最有价值的只读命令，并放在最后。若无需命令，command留空。"
  );
  blocks.push(
    "【时间上下文（北京时间）】" +
    `今天=${yyyy}-${mm}-${dd}，日期候选=${todayYYYYMMDD}/${todayYYMMDD}。` +
    "如果用户说“今天”，命令必须使用这一天，或用 `D1=$(date +%Y%m%d); D2=$(date +%y%m%d)` 动态取值；" +
    "禁止套用示例中的历史日期。"
  );
  if (customPrompt) {
    blocks.push("【提示】补充提示词里的日期样例仅作格式示例，不代表今天。");
    blocks.push(`【补充提示词】\n${customPrompt}`);
  }
  if (logBasePath) {
    blocks.push("【约束】已给定日志基础路径时，优先在该路径下检索，避免全局扫描。");
    blocks.push(`【日志基础路径】\n${logBasePath}`);
  }
  if (outputFormat) {
    blocks.push(`【输出格式要求】\n${outputFormat}`);
  }
  if (userInput) {
    blocks.push(`【用户问题】\n${userInput}`);
  } else {
    blocks.push("【用户问题】\n请给出下一条排障建议命令，并说明理由。");
  }
  return blocks.join("\n\n");
}

async function executePreparedCommand(command) {
  if (!state.bridgeSessionId) {
    throw new Error("bridge session not open");
  }
  const prepared = await callBridge(`/v1/session/${state.bridgeSessionId}/execute`, "POST", {
    command: command || "",
    wrap_markers: true
  });
  const tabId = await detectActiveTab();
  if (!tabId) {
    throw new Error("no active tab");
  }
  try {
    await injectCommandViaScripting(tabId, prepared.wrapped_command);
  } catch {
    // fallback to content-script injection
    await ensureContentReady(tabId);
    const injected = await sendTabMessage(tabId, {
      type: "inject_command",
      command: prepared.wrapped_command
    });
    if (injected && injected.ok === false) {
      throw new Error(injected.error || "inject failed");
    }
  }
  return prepared;
}

chrome.runtime.onInstalled.addListener(async () => {
  await ensureStateLoaded();
  await chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });
});

chrome.runtime.onStartup.addListener(async () => {
  await ensureStateLoaded();
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  (async () => {
    await ensureStateLoaded();

    if (!message || !message.type) {
      sendResponse({ ok: false, error: "invalid message" });
      return;
    }

    if (message.type === "set_bridge_config") {
      state.bridgeUrl = message.bridgeUrl || DEFAULT_BRIDGE_URL;
      state.token = message.token || "";
      await chrome.storage.local.set({ bridgeUrl: state.bridgeUrl, token: state.token });
      sendResponse({ ok: true });
      return;
    }

    if (message.type === "set_runtime_options") {
      state.autoExecuteLowRisk = Boolean(message.autoExecuteLowRisk);
      await chrome.storage.local.set({ autoExecuteLowRisk: state.autoExecuteLowRisk });
      sendResponse({ ok: true });
      return;
    }

    if (message.type === "ensure_auto_session") {
      const info = await ensureAutoSession(false);
      sendResponse({
        ok: true,
        data: {
          bridgeSessionId: state.bridgeSessionId,
          sessionKey: state.sessionKey,
          identity: info.identity,
          snapshot: info.snapshot,
          reused: info.reused
        }
      });
      return;
    }

    if (message.type === "rotate_session") {
      const info = await ensureAutoSession(true);
      sendResponse({
        ok: true,
        data: {
          bridgeSessionId: state.bridgeSessionId,
          sessionKey: state.sessionKey,
          identity: info.identity,
          snapshot: info.snapshot
        }
      });
      return;
    }

    if (message.type === "ask_agent") {
      const sessionInfo = await ensureAutoSession(false);
      const snapshot = CAPTURE_DISABLED ? disabledSnapshot() : sessionInfo.snapshot;

      const data = await callBridge(`/v1/session/${state.bridgeSessionId}/suggest`, "POST", {
        question: composeQuestion(message)
      });

      let autoExecution = null;
      let autoExecutionError = "";
      if (state.autoExecuteLowRisk && data.risk === "low" && data.command) {
        try {
          autoExecution = await executePreparedCommand(data.command);
        } catch (error) {
          autoExecutionError = stringifyError(error);
        }
      }
      sendResponse({
        ok: true,
        data,
        snapshot,
        identity: sessionInfo.identity,
        auto_executed: Boolean(autoExecution),
        auto_execution: autoExecution,
        auto_execution_error: autoExecutionError
      });
      return;
    }

    if (message.type === "content_ready") {
      const senderTabId = _sender?.tab?.id;
      if (typeof senderTabId === "number") {
        contentReadyByTab.set(senderTabId, {
          at: Date.now(),
          hasOutputRoot: true,
          url: message.url || "",
          title: message.title || ""
        });
      }
      sendResponse({ ok: true });
      return;
    }

    if (message.type === "open_session") {
      const tabId = await detectActiveTab();
      if (tabId) {
        try {
          await ensureContentReady(tabId);
        } catch {
          // allow opening bridge session even when terminal page is not ready yet
        }
      }
      const data = await openSession({
        host: message.host,
        scope: message.scope || "default",
        user: message.user || "unknown",
        agent_id: message.agentId || null,
        reuse_existing: true
      });
      let snapshot = { ingestedChars: 0, hasOutputRoot: false };
      try {
        snapshot = await ingestSnapshotFromActiveTab("open-session");
      } catch {
        // no hard fail; allow session open even before terminal ready
      }
      sendResponse({ ok: true, data, snapshot });
      return;
    }

    if (message.type === "ingest_output") {
      if (!state.bridgeSessionId) {
        sendResponse({ ok: false, error: "bridge session not open" });
        return;
      }
      await callBridge(`/v1/session/${state.bridgeSessionId}/ingest`, "POST", {
        text: message.text || "",
        stream: message.stream || "stdout",
        metadata: message.metadata || {}
      });
      sendResponse({ ok: true });
      return;
    }

    if (message.type === "request_suggestion") {
      if (!state.bridgeSessionId) {
        await loadState();
      }
      if (!state.bridgeSessionId) {
        sendResponse({ ok: false, error: "bridge session not open" });
        return;
      }

      let snapshot = { ingestedChars: 0, hasOutputRoot: false };
      try {
        snapshot = await ingestSnapshotFromActiveTab("pre-suggest");
      } catch {
        // best effort; do not block suggest
      }

      const data = await callBridge(`/v1/session/${state.bridgeSessionId}/suggest`, "POST", {
        question: message.question || ""
      });
      state.lastSuggestion = data;
      let autoExecution = null;
      if (state.autoExecuteLowRisk && data.risk === "low" && data.command) {
        autoExecution = await executePreparedCommand(data.command);
      }
      sendResponse({
        ok: true,
        data,
        snapshot,
        auto_executed: Boolean(autoExecution),
        auto_execution: autoExecution
      });
      return;
    }

    if (message.type === "execute_command") {
      if (!state.bridgeSessionId) {
        await loadState();
      }
      if (!state.bridgeSessionId) {
        sendResponse({ ok: false, error: "bridge session not open" });
        return;
      }
      const prepared = await executePreparedCommand(message.command || "");
      sendResponse({ ok: true, data: prepared });
      return;
    }

    if (message.type === "capture_now") {
      if (!state.bridgeSessionId) {
        sendResponse({ ok: false, error: "bridge session not open" });
        return;
      }
      const snapshot = await ingestSnapshotFromActiveTab("manual-capture");
      sendResponse({ ok: true, data: snapshot });
      return;
    }

    if (message.type === "bridge_state") {
      const stored = await chrome.storage.local.get(["autoSessionIdentity"]);
      sendResponse({
        ok: true,
        data: {
          bridgeUrl: state.bridgeUrl,
          bridgeSessionId: state.bridgeSessionId,
          sessionKey: state.sessionKey,
          autoExecuteLowRisk: state.autoExecuteLowRisk,
          autoSessionIdentity: stored.autoSessionIdentity || null
        }
      });
      return;
    }

    if (message.type === "session_state") {
      if (!state.bridgeSessionId) {
        sendResponse({ ok: false, error: "bridge session not open" });
        return;
      }
      const sessionState = await callBridge(`/v1/session/${state.bridgeSessionId}/state`, "GET");
      const preview = String(sessionState?.session?.recent_output_preview || "");
      sendResponse({
        ok: true,
        data: sessionState,
        preview: buildPreview(preview, 2600)
      });
      return;
    }

    if (message.type === "debug_capture_frames") {
      const tabId = await detectActiveTab();
      if (!tabId) {
        sendResponse({ ok: false, error: "no active tab" });
        return;
      }
      try {
        await ensureContentReady(tabId);
      } catch {
        // continue best-effort
      }
      const frames = await debugCaptureFrames(tabId);
      sendResponse({ ok: true, data: { frames } });
      return;
    }

    sendResponse({ ok: false, error: `unknown message type: ${message.type}` });
  })().catch((error) => {
    sendResponse({ ok: false, error: stringifyError(error) });
  });

  return true;
});
