# Grape-Agent 发布 SOP（推送、打包、下载、配置）

## 1. 适用范围

本 SOP 用于以下场景：

1. 将当前本地代码推送到个人 GitHub 仓库。
2. 触发 GitHub Actions 构建 macOS / Windows 可执行文件。
3. 下载构建产物（artifacts）到本地。
4. 在 macOS / Windows 上手动配置 `settings.json` 并运行。

仓库基准：`https://github.com/kongxiaoran/grape-agent`

---

## 2. 前置条件

1. 本机已安装 `git`、`gh`、`uv`。
2. 已登录 GitHub CLI：

```bash
gh auth login
gh auth status
```

3. 当前项目目录：

```bash
cd /Users/kxr/learning/grape-agent
```

---

## 3. Git 远端与分支基线

建议远端约定：

- `origin`: 个人仓库（可写）
- `upstream`: 上游仓库（只读）

检查：

```bash
git remote -v
git branch --show-current
git status --short
```

推荐工作分支：`main`。

---

## 4. 推送代码到个人仓库

```bash
cd /Users/kxr/learning/grape-agent

git add -A
git commit -m "feat: update build and release flow"
git push origin main
```

如果出现未配置用户信息：

```bash
git config --global user.name "YourName"
git config --global user.email "you@example.com"
```

---

## 5. 触发打包（GitHub Actions）

## 5.1 推荐：PyInstaller（快，成功率高）

Workflow 文件：

- `.github/workflows/build-binaries-pyinstaller.yml`

触发（仅主程序 `grape-agent`）：

```bash
gh workflow run build-binaries-pyinstaller.yml \
  --repo kongxiaoran/grape-agent \
  -f target=grape-agent
```

查看状态：

```bash
gh run list --repo kongxiaoran/grape-agent --workflow build-binaries-pyinstaller.yml --limit 3
```

## 5.2 可选：Nuitka（慢，发布质量高）

Workflow 文件：

- `.github/workflows/build-binaries-nuitka.yml`

触发：

```bash
gh workflow run build-binaries-nuitka.yml \
  --repo kongxiaoran/grape-agent \
  -f target=grape-agent
```

说明：Nuitka 常见超长耗时，若交付优先，先用 PyInstaller 出包。

---

## 6. 下载构建产物（artifacts）

## 6.1 通过 GH CLI 下载（优先）

1. 先拿 run_id：

```bash
gh run list --repo kongxiaoran/grape-agent --limit 5
```

2. 下载该 run 的产物到本地目录：

```bash
mkdir -p /Users/kxr/learning/grape-agent/release/gha/<RUN_ID>
gh run download <RUN_ID> \
  --repo kongxiaoran/grape-agent \
  -D /Users/kxr/learning/grape-agent/release/gha/<RUN_ID>
```

3. 查看文件：

```bash
find /Users/kxr/learning/grape-agent/release/gha/<RUN_ID> -maxdepth 3 -type f
```

## 6.2 通过 Web 页面下载（CLI 下载慢时）

1. 打开 run 页面：

`https://github.com/kongxiaoran/grape-agent/actions`

2. 进入对应 run，下载 artifacts：

- `grape-agent-pyinstaller-macos-latest`
- `grape-agent-pyinstaller-windows-latest`

---

## 7. 运行前配置文件（最关键）

程序默认优先读取：

- macOS: `~/.grape-agent/config/settings.json`
- Windows: `%USERPROFILE%\.grape-agent\config\settings.json`

代码依据：

- `mini_agent/config.py`（`get_default_config_path`）
- `mini_agent/cli.py`（配置搜索路径提示）

## 7.1 macOS 配置

```bash
mkdir -p "$HOME/.grape-agent/config"
cat > "$HOME/.grape-agent/config/settings.json" <<'JSON'
{
  "api_key": "YOUR_REAL_API_KEY",
  "api_base": "https://api.minimax.io",
  "model": "MiniMax-M2.5",
  "provider": "anthropic"
}
JSON
```

## 7.2 Windows 配置（PowerShell）

```powershell
New-Item -ItemType Directory -Force "$HOME\.grape-agent\config" | Out-Null
@'
{
  "api_key": "YOUR_REAL_API_KEY",
  "api_base": "https://api.minimax.io",
  "model": "MiniMax-M2.5",
  "provider": "anthropic"
}
'@ | Set-Content -Path "$HOME\.grape-agent\config\settings.json" -Encoding UTF8
```

---

## 8. 启动验证

## 8.1 macOS

```bash
/absolute/path/to/grape-agent --help
/absolute/path/to/grape-agent
```

## 8.2 Windows

```powershell
.\grape-agent.exe --help
.\grape-agent.exe
```

---

## 9. 常见问题与处理

1. `❌ Error: Please configure a valid API Key`
- 原因：`~/.grape-agent/config/settings.json` 缺少或 `api_key` 为空。
- 处理：按第 7 节重建配置文件。

2. `E212: Can't open file for writing`
- 原因：目录不存在。
- 处理：先执行 `mkdir -p ~/.grape-agent/config` 再写文件。

3. Nuitka 日志里出现 `_bisect/_json` anti-bloat 警告
- 结论：警告，不是失败原因。
- 真正失败多为 `KeyboardInterrupt` / `The operation was canceled`（任务被取消或超时）。

4. `gh workflow run ... 404 not found on default branch`
- 原因：workflow 文件还没 push 到远端默认分支。
- 处理：先 `git push origin main`，再触发 workflow。

5. `Permission denied` 推不上仓库
- 原因：推到了无写权限仓库。
- 处理：确认 `origin` 指向 `kongxiaoran/grape-agent`。

---

## 10. 建议执行策略

1. 迭代阶段：优先 `PyInstaller` 快速出包。
2. 发布阶段：可并行跑 `Nuitka`，成功后作为高质量产物。
3. 出包后固定执行：
- 启动 smoke（`--help` + 实际启动）
- 配置检查（`~/.grape-agent/config/settings.json`）
- artifact 归档到 `release/gha/<RUN_ID>/`
