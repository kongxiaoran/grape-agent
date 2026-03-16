function qs(id) {
  return document.getElementById(id);
}

const ui = {
  rotateSession: qs("rotateSession"),
  sessionStatus: qs("sessionStatus"),
  templateSelect: qs("templateSelect"),
  toggleTemplateEdit: qs("toggleTemplateEdit"),
  templateEditor: qs("templateEditor"),
  templateName: qs("templateName"),
  createTemplate: qs("createTemplate"),
  updateTemplate: qs("updateTemplate"),
  deleteTemplate: qs("deleteTemplate"),
  logBasePath: qs("logBasePath"),
  outputFormat: qs("outputFormat"),
  customPrompt: qs("customPrompt"),
  promptFile: qs("promptFile"),
  promptStatus: qs("promptStatus"),
  userInput: qs("userInput"),
  askAgent: qs("askAgent"),
  agentOutput: qs("agentOutput"),
  ioStatus: qs("ioStatus")
};

const TEMPLATES_KEY = "prompt_templates_v1";
const ACTIVE_TEMPLATE_KEY = "prompt_active_template_id";
const LEGACY_KEYS = ["prompt_log_base_path", "prompt_output_format", "prompt_custom_text"];

let templatesState = {
  templates: [],
  activeId: null
};
let templateEditorVisible = false;

async function sendMessage(payload) {
  return await chrome.runtime.sendMessage(payload);
}

function toErrorText(value) {
  if (!value) return "unknown error";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function nowTs() {
  return Date.now();
}

function makeId() {
  return `tpl_${Math.random().toString(36).slice(2, 10)}`;
}

function getTemplateById(id) {
  return templatesState.templates.find((item) => item.id === id) || null;
}

function currentFields() {
  return {
    logBasePath: ui.logBasePath.value.trim(),
    outputFormat: ui.outputFormat.value.trim(),
    customPrompt: ui.customPrompt.value.trim()
  };
}

function applyTemplateToFields(template) {
  ui.logBasePath.value = template?.logBasePath || "";
  ui.outputFormat.value = template?.outputFormat || "";
  ui.customPrompt.value = template?.customPrompt || "";
  ui.templateName.value = template?.name || "";
}

function setTemplateEditorVisible(visible) {
  templateEditorVisible = Boolean(visible);
  ui.templateEditor.classList.toggle("hidden", !templateEditorVisible);
  ui.toggleTemplateEdit.textContent = templateEditorVisible ? "收起模板编辑" : "编辑模板";
}

function renderTemplateSelect() {
  ui.templateSelect.innerHTML = "";
  for (const item of templatesState.templates) {
    const opt = document.createElement("option");
    opt.value = item.id;
    opt.textContent = item.name || item.id;
    if (item.id === templatesState.activeId) {
      opt.selected = true;
    }
    ui.templateSelect.appendChild(opt);
  }
}

async function persistTemplates() {
  await chrome.storage.local.set({
    [TEMPLATES_KEY]: templatesState.templates,
    [ACTIVE_TEMPLATE_KEY]: templatesState.activeId
  });
}

async function migrateLegacyTemplateIfNeeded() {
  const stored = await chrome.storage.local.get([TEMPLATES_KEY, ACTIVE_TEMPLATE_KEY, ...LEGACY_KEYS]);
  const existingTemplates = Array.isArray(stored[TEMPLATES_KEY]) ? stored[TEMPLATES_KEY] : [];
  if (existingTemplates.length > 0) {
    templatesState.templates = existingTemplates;
    templatesState.activeId = stored[ACTIVE_TEMPLATE_KEY] || existingTemplates[0].id;
    return;
  }

  const legacy = {
    logBasePath: stored.prompt_log_base_path || "",
    outputFormat: stored.prompt_output_format || "",
    customPrompt: stored.prompt_custom_text || ""
  };
  const template = {
    id: makeId(),
    name: "默认模板",
    ...legacy,
    createdAt: nowTs(),
    updatedAt: nowTs()
  };
  templatesState.templates = [template];
  templatesState.activeId = template.id;
  await persistTemplates();
}

async function switchActiveTemplate(id) {
  const target = getTemplateById(id);
  if (!target) return;
  templatesState.activeId = target.id;
  await persistTemplates();
  renderTemplateSelect();
  applyTemplateToFields(target);
}

async function createTemplateFromCurrent() {
  const name = ui.templateName.value.trim() || `模板-${new Date().toLocaleString()}`;
  const fields = currentFields();
  const tpl = {
    id: makeId(),
    name,
    ...fields,
    createdAt: nowTs(),
    updatedAt: nowTs()
  };
  templatesState.templates.push(tpl);
  templatesState.activeId = tpl.id;
  await persistTemplates();
  renderTemplateSelect();
  applyTemplateToFields(tpl);
  ui.promptStatus.textContent = `已新建模板: ${tpl.name}`;
}

async function updateActiveTemplateFromCurrent() {
  const current = getTemplateById(templatesState.activeId);
  if (!current) {
    ui.promptStatus.textContent = "当前没有可更新模板";
    return;
  }
  const fields = currentFields();
  current.name = ui.templateName.value.trim() || current.name || "未命名模板";
  current.logBasePath = fields.logBasePath;
  current.outputFormat = fields.outputFormat;
  current.customPrompt = fields.customPrompt;
  current.updatedAt = nowTs();
  await persistTemplates();
  renderTemplateSelect();
  ui.promptStatus.textContent = `已保存模板: ${current.name}`;
}

async function deleteActiveTemplate() {
  if (templatesState.templates.length <= 1) {
    ui.promptStatus.textContent = "至少保留一个模板";
    return;
  }
  const id = templatesState.activeId;
  templatesState.templates = templatesState.templates.filter((item) => item.id !== id);
  templatesState.activeId = templatesState.templates[0]?.id || null;
  await persistTemplates();
  renderTemplateSelect();
  applyTemplateToFields(getTemplateById(templatesState.activeId));
  ui.promptStatus.textContent = "已删除当前模板";
}

function getActiveTemplateFields() {
  const tpl = getTemplateById(templatesState.activeId);
  return {
    logBasePath: tpl?.logBasePath || ui.logBasePath.value.trim(),
    outputFormat: tpl?.outputFormat || ui.outputFormat.value.trim(),
    customPrompt: tpl?.customPrompt || ui.customPrompt.value.trim()
  };
}

function renderSession(info) {
  const identity = info?.identity || {};
  ui.sessionStatus.textContent = [
    `bridge_session_id=${info?.bridgeSessionId || "-"}`,
    `session_key=${info?.sessionKey || "-"}`,
    `host=${identity.host || "-"}`,
    `scope=${identity.scope || "-"}`,
    `user=${identity.user || "-"}`,
    "模式: 基于用户粘贴日志分析（无自动采集）"
  ].join("\n");
}

function renderAgentOutput(resp) {
  const data = resp?.data || {};
  const identity = resp?.identity || {};
  const command = data.command || "";
  const risk = data.risk || "unknown";
  const reason = data.reason || "";
  const summary = data.summary || "";
  ui.agentOutput.value = [
    `会话: host=${identity.host || "-"} scope=${identity.scope || "-"} user=${identity.user || "-"}`,
    "分析模式: 基于用户输入日志",
    "",
    `summary: ${summary}`,
    `risk: ${risk}`,
    `reason: ${reason}`,
    "",
    "command:",
    command || "(empty)"
  ].join("\n");
}

async function ensureAutoSession() {
  const resp = await sendMessage({ type: "ensure_auto_session" });
  if (!resp.ok) {
    ui.sessionStatus.textContent = `自动会话失败: ${toErrorText(resp.error)}`;
    return;
  }
  renderSession(resp.data || {});
}

ui.rotateSession.addEventListener("click", async () => {
  const resp = await sendMessage({ type: "rotate_session" });
  if (!resp.ok) {
    ui.sessionStatus.textContent = `刷新会话失败: ${toErrorText(resp.error)}`;
    return;
  }
  renderSession(resp.data || {});
  ui.ioStatus.textContent = "会话已刷新";
});

ui.templateSelect.addEventListener("change", async () => {
  await switchActiveTemplate(ui.templateSelect.value);
});

ui.toggleTemplateEdit.addEventListener("click", async () => {
  setTemplateEditorVisible(!templateEditorVisible);
});

ui.createTemplate.addEventListener("click", async () => {
  await createTemplateFromCurrent();
  setTemplateEditorVisible(true);
});

ui.updateTemplate.addEventListener("click", async () => {
  await updateActiveTemplateFromCurrent();
});

ui.deleteTemplate.addEventListener("click", async () => {
  await deleteActiveTemplate();
});

ui.promptFile.addEventListener("change", async () => {
  const file = ui.promptFile.files?.[0];
  if (!file) return;
  try {
    const text = await file.text();
    ui.customPrompt.value = text;
    ui.promptStatus.textContent = `已载入 txt: ${file.name}`;
  } catch (error) {
    ui.promptStatus.textContent = `读取 txt 失败: ${toErrorText(error)}`;
  }
});

ui.askAgent.addEventListener("click", async () => {
  ui.ioStatus.textContent = "";
  const tpl = getActiveTemplateFields();
  const resp = await sendMessage({
    type: "ask_agent",
    logBasePath: tpl.logBasePath,
    outputFormat: tpl.outputFormat,
    customPrompt: tpl.customPrompt,
    userInput: ui.userInput.value.trim()
  });
  if (!resp.ok) {
    ui.ioStatus.textContent = `请求失败: ${toErrorText(resp.error)}`;
    return;
  }
  renderAgentOutput(resp);
  if (resp.auto_executed) {
    ui.ioStatus.textContent = `低风险命令已自动执行，trace_id=${resp.auto_execution.trace_id}`;
  } else {
    ui.ioStatus.textContent = "Agent 已返回";
  }
});

async function init() {
  await migrateLegacyTemplateIfNeeded();
  renderTemplateSelect();
  applyTemplateToFields(getTemplateById(templatesState.activeId));
  setTemplateEditorVisible(false);
  await ensureAutoSession();
}

init().catch((error) => {
  ui.sessionStatus.textContent = `初始化失败: ${toErrorText(error)}`;
});
