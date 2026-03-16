const OUTPUT_SELECTORS = [
  ".xterm-rows",
  ".xterm-accessibility",
  ".xterm-accessibility-tree",
  ".terminal-output",
  ".terminal",
  "pre",
  "code"
];

const INPUT_SELECTORS = [
  "textarea.xterm-helper-textarea",
  ".xterm-helper-textarea",
  "textarea[aria-label='Terminal input']",
  "textarea[data-testid='terminal-input']",
  "textarea"
];

const MAX_WS_BUFFER_CHARS = 120000;
const MAX_TERM_BUFFER_CHARS = 120000;

let outputObserver = null;
let observedRoot = null;
let lastIncrementalDigest = "";
let lastSnapshotDigest = "";
let wsOutputBuffer = "";
let termOutputBuffer = "";

function stripAnsi(text) {
  return String(text || "")
    .replace(/\u001b\[[0-9;?]*[A-Za-z]/g, "")
    .replace(/\u001b\][^\u0007]*(\u0007|\u001b\\)/g, "")
    .replace(/\u001b[@-_]/g, "");
}

function normalizeTerminalText(text) {
  return stripAnsi(text)
    .replace(/\r/g, "\n")
    .replace(/[^\x09\x0A\x0D\x20-\x7E]/g, " ")
    .replace(/\n{3,}/g, "\n\n");
}

function isLikelyProtocolNoise(text) {
  const s = String(text || "").trim();
  if (!s) return true;
  if (/^\[stdin]/i.test(s)) return true;
  if (/^\d+\.,\d+\.(ping|pong|noop|heartbeat)\b/i.test(s)) return true;
  if (/^(ping|pong|heartbeat|keepalive)$/i.test(s)) return true;
  if (/^[0-9.,;:_-]+$/.test(s) && s.length < 120) return true;
  if (/ping/i.test(s) && s.length < 160 && !/\n/.test(s)) return true;
  return false;
}

function digestText(text) {
  return `${text.length}:${text.slice(-120)}`;
}

function postToBackground(payload) {
  try {
    chrome.runtime.sendMessage(payload, () => {
      void chrome.runtime.lastError;
    });
  } catch {
    // ignored: background may be reloading
  }
}

function pickBestOutputRoot() {
  let bestNode = null;
  let bestScore = 0;
  for (const selector of OUTPUT_SELECTORS) {
    const nodes = document.querySelectorAll(selector);
    for (const node of nodes) {
      const text = (node.innerText || node.textContent || "").trim();
      const score = text.length;
      if (score > bestScore) {
        bestNode = node;
        bestScore = score;
      }
    }
  }
  return bestNode;
}

function normalizeSnapshot(text, maxLines = 240, maxChars = 20000) {
  const lines = normalizeTerminalText(text)
    .split("\n")
    .map((line) => line.replace(/\u00a0/g, " ").trimEnd())
    .filter((line) => line.trim().length > 0);
  const tail = lines.slice(-maxLines).join("\n");
  if (tail.length <= maxChars) return tail;
  return tail.slice(-maxChars);
}

function collectSnapshot(maxLines = 240, maxChars = 20000) {
  const root = pickBestOutputRoot();
  const domText = root ? normalizeSnapshot(root.innerText || root.textContent || "", maxLines, maxChars) : "";
  const wsText = normalizeSnapshot(wsOutputBuffer, maxLines, maxChars);
  const termText = normalizeSnapshot(termOutputBuffer, maxLines, maxChars);

  if (termText.length >= wsText.length && termText.length >= domText.length) {
    return termText;
  }
  if (wsText.length > domText.length) {
    return wsText;
  }
  if (!domText) {
    return wsText || termText;
  }
  if (!wsText && !termText) {
    return domText;
  }
  return normalizeSnapshot(`${termText}\n${wsText}\n${domText}`, maxLines, maxChars);
}

function sendIncrementalOutput(text) {
  const cleaned = normalizeTerminalText(text).trim();
  if (!cleaned) return;
  const digest = digestText(cleaned);
  if (digest === lastIncrementalDigest) return;
  lastIncrementalDigest = digest;
  postToBackground({
    type: "ingest_output",
    text: cleaned,
    stream: "stdout"
  });
}

function sendSnapshotIfChanged(reason = "periodic") {
  const snapshot = collectSnapshot();
  if (!snapshot) return;
  const digest = digestText(snapshot);
  if (digest === lastSnapshotDigest) return;
  lastSnapshotDigest = digest;
  postToBackground({
    type: "ingest_output",
    text: snapshot,
    stream: "snapshot",
    metadata: { reason }
  });
}

function appendWsOutput(text) {
  const cleaned = normalizeTerminalText(text).trim();
  if (!cleaned) return;
  if (isLikelyProtocolNoise(cleaned)) return;
  wsOutputBuffer = `${wsOutputBuffer}\n${cleaned}`.trim();
  if (wsOutputBuffer.length > MAX_WS_BUFFER_CHARS) {
    wsOutputBuffer = wsOutputBuffer.slice(-MAX_WS_BUFFER_CHARS);
  }
  sendIncrementalOutput(cleaned);
  sendSnapshotIfChanged("ws");
}

function appendTermOutput(text) {
  const cleaned = normalizeTerminalText(text).trim();
  if (!cleaned) return;
  if (isLikelyProtocolNoise(cleaned)) return;
  termOutputBuffer = `${termOutputBuffer}\n${cleaned}`.trim();
  if (termOutputBuffer.length > MAX_TERM_BUFFER_CHARS) {
    termOutputBuffer = termOutputBuffer.slice(-MAX_TERM_BUFFER_CHARS);
  }
  sendIncrementalOutput(cleaned);
  sendSnapshotIfChanged("xterm-write");
}

function attachOutputObserver() {
  const root = pickBestOutputRoot();
  if (!root || root === observedRoot) return;

  if (outputObserver) {
    outputObserver.disconnect();
  }

  observedRoot = root;
  outputObserver = new MutationObserver((mutations) => {
    const batch = [];
    for (const mutation of mutations) {
      if (mutation.type === "characterData") {
        const text = mutation.target?.textContent || "";
        if (text.trim()) batch.push(text);
      }
      for (const node of mutation.addedNodes) {
        if (node.nodeType !== Node.ELEMENT_NODE && node.nodeType !== Node.TEXT_NODE) continue;
        const text = node.textContent || "";
        if (text.trim()) batch.push(text);
      }
    }
    if (batch.length) {
      sendIncrementalOutput(batch.join("\n"));
      sendSnapshotIfChanged("mutation");
    }
  });

  outputObserver.observe(root, { childList: true, subtree: true, characterData: true });
  sendSnapshotIfChanged("observer-attached");
}

function getTerminalInput() {
  for (const selector of INPUT_SELECTORS) {
    const el = document.querySelector(selector);
    if (el) return el;
  }
  return null;
}

function setNativeValue(el, value) {
  const proto = Object.getPrototypeOf(el);
  const desc = Object.getOwnPropertyDescriptor(proto, "value");
  if (desc && typeof desc.set === "function") {
    desc.set.call(el, value);
    return;
  }
  el.value = value;
}

function injectCommand(command) {
  const cleaned = String(command || "").trim();
  if (!cleaned) {
    throw new Error("empty command");
  }

  const input = getTerminalInput();
  if (!input) {
    throw new Error("terminal input not found");
  }

  const payload = cleaned.endsWith("\n") ? cleaned : `${cleaned}\n`;
  input.focus();
  setNativeValue(input, payload);
  try {
    input.dispatchEvent(
      new InputEvent("input", {
        bubbles: true,
        data: payload,
        inputType: "insertText"
      })
    );
  } catch {
    input.dispatchEvent(new Event("input", { bubbles: true }));
  }
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
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (!message || !message.type) return;

  if (message.type === "inject_command") {
    try {
      injectCommand(message.command || "");
      sendResponse({ ok: true });
    } catch (error) {
      sendResponse({ ok: false, error: String(error) });
    }
    return true;
  }

  if (message.type === "capture_snapshot") {
    try {
      const text = collectSnapshot(message.maxLines || 240, message.maxChars || 20000);
      sendResponse({
        ok: true,
        has_output_root: Boolean(pickBestOutputRoot()),
        has_ws_buffer: wsOutputBuffer.length > 0,
        has_term_buffer: termOutputBuffer.length > 0,
        text
      });
    } catch (error) {
      sendResponse({ ok: false, error: String(error) });
    }
    return true;
  }

  if (message.type === "ping_content") {
    sendResponse({
      ok: true,
      has_output_root: Boolean(pickBestOutputRoot()),
      has_input: Boolean(getTerminalInput()),
      has_ws_buffer: wsOutputBuffer.length > 0,
      has_term_buffer: termOutputBuffer.length > 0
    });
    return true;
  }
});

window.addEventListener("grape-agent-ws-output", (event) => {
  const detail = event?.detail || {};
  const text = detail.text || "";
  appendWsOutput(text);
});

window.addEventListener("grape-agent-term-output", (event) => {
  const detail = event?.detail || {};
  const text = detail.text || "";
  appendTermOutput(text);
});

attachOutputObserver();
setInterval(attachOutputObserver, 1200);
setInterval(() => sendSnapshotIfChanged("periodic"), 1800);
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) {
    attachOutputObserver();
    sendSnapshotIfChanged("visible");
  }
});

postToBackground({
  type: "content_ready",
  url: location.href,
  title: document.title
});
