# Grape-Agent 跨平台打包指南（macOS + Windows）

## 1. 结论先说（最小改动 + 可发布）

在“不改动大量项目代码”的前提下，本项目最合适的方案是：

- 打包工具：`Nuitka`（主方案）
- 产物形态：`--onefile` 单文件可执行
- 构建方式：分平台构建（mac 打 mac；Windows 打 Windows）

### 1.1 工具对比（为什么切到 Nuitka）

| 方案 | 改动成本 | 跨平台实践 | 对当前 CLI 项目适配 |
|---|---|---|---|
| Nuitka | 中 | 需分平台构建 | 适配好，发布质量更高 |
| PyInstaller | 低 | 需分平台构建 | 适合快速验证 |
| Briefcase | 高 | 面向 GUI App | 不适合当前终端为主项目 |

结论：当前仓库优先走 **Nuitka**；保留 **PyInstaller** 作为应急兜底。

## 2. 当前项目要打哪些可执行文件

根据 `pyproject.toml` 的脚本入口：

- `grape-agent = mini_agent.cli:main`
- `grape-agent-feishu = mini_agent.feishu.server_ws:main`
- `grape-agent-webterm-bridge = mini_agent.webterm_bridge.server:main`

建议生成 3 个二进制：

1. `grape-agent`（主 CLI）
2. `grape-agent-feishu`（飞书长连接服务）
3. `grape-agent-webterm-bridge`（Webterm Bridge 服务）

## 3. 打包前准备

```bash
cd /Users/kxr/learning/Mini-Agent
uv sync
uv run python -V
uv run --with nuitka python -m nuitka --version
```

配置文件建议放用户目录，避免升级时覆盖：

- macOS: `~/.grape/settings.json`
- Windows: `%USERPROFILE%\\.grape\\settings.json`

## 4. macOS 本地打包（Nuitka）

```bash
cd /Users/kxr/learning/Mini-Agent
rm -rf build dist

uv run --with nuitka python -m nuitka \
  --onefile \
  --assume-yes-for-downloads \
  --follow-imports \
  --include-package=mini_agent \
  --include-package-data=mini_agent \
  --output-dir=dist \
  --output-filename=grape-agent \
  mini_agent/cli.py

uv run --with nuitka python -m nuitka \
  --onefile \
  --assume-yes-for-downloads \
  --follow-imports \
  --include-package=mini_agent \
  --include-package-data=mini_agent \
  --output-dir=dist \
  --output-filename=grape-agent-feishu \
  mini_agent/feishu/server_ws.py

uv run --with nuitka python -m nuitka \
  --onefile \
  --assume-yes-for-downloads \
  --follow-imports \
  --include-package=mini_agent \
  --include-package-data=mini_agent \
  --output-dir=dist \
  --output-filename=grape-agent-webterm-bridge \
  mini_agent/webterm_bridge/server.py

./dist/grape-agent --help
./dist/grape-agent-feishu --help
./dist/grape-agent-webterm-bridge --help
```

产物：

- `dist/grape-agent`
- `dist/grape-agent-feishu`
- `dist/grape-agent-webterm-bridge`

## 5. Windows 打包（本机或远程，Nuitka）

PowerShell：

```powershell
cd C:\path\to\Mini-Agent
uv sync

uv run --with nuitka python -m nuitka `
  --onefile `
  --assume-yes-for-downloads `
  --follow-imports `
  --include-package=mini_agent `
  --include-package-data=mini_agent `
  --output-dir=dist `
  --output-filename=grape-agent.exe `
  mini_agent\cli.py

uv run --with nuitka python -m nuitka `
  --onefile `
  --assume-yes-for-downloads `
  --follow-imports `
  --include-package=mini_agent `
  --include-package-data=mini_agent `
  --output-dir=dist `
  --output-filename=grape-agent-feishu.exe `
  mini_agent\feishu\server_ws.py

uv run --with nuitka python -m nuitka `
  --onefile `
  --assume-yes-for-downloads `
  --follow-imports `
  --include-package=mini_agent `
  --include-package-data=mini_agent `
  --output-dir=dist `
  --output-filename=grape-agent-webterm-bridge.exe `
  mini_agent\webterm_bridge\server.py

.\dist\grape-agent.exe --help
```

产物：

- `dist\\grape-agent.exe`
- `dist\\grape-agent-feishu.exe`
- `dist\\grape-agent-webterm-bridge.exe`

## 6. 远程打包（推荐两种，Nuitka）

### 6.1 方案 A：GitHub Actions 矩阵构建（推荐）

优点：一次触发拿到 mac + windows 两套产物，适合发布。

`.github/workflows/build-binaries.yml` 示例：

```yaml
name: Build Grape-Agent Binaries (Nuitka)

on:
  workflow_dispatch:
  push:
    tags:
      - "v*"

jobs:
  build:
    strategy:
      matrix:
        os: [macos-latest, windows-latest]
    runs-on: ${{ matrix.os }}

    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - name: Sync deps
        run: uv sync
      - name: Build (Unix shell)
        if: runner.os != 'Windows'
        run: |
          uv run --with nuitka python -m nuitka --onefile --assume-yes-for-downloads --follow-imports --include-package=mini_agent --include-package-data=mini_agent --output-dir=dist --output-filename=grape-agent mini_agent/cli.py
          uv run --with nuitka python -m nuitka --onefile --assume-yes-for-downloads --follow-imports --include-package=mini_agent --include-package-data=mini_agent --output-dir=dist --output-filename=grape-agent-feishu mini_agent/feishu/server_ws.py
          uv run --with nuitka python -m nuitka --onefile --assume-yes-for-downloads --follow-imports --include-package=mini_agent --include-package-data=mini_agent --output-dir=dist --output-filename=grape-agent-webterm-bridge mini_agent/webterm_bridge/server.py
      - name: Build (Windows)
        if: runner.os == 'Windows'
        shell: pwsh
        run: |
          uv run --with nuitka python -m nuitka --onefile --assume-yes-for-downloads --follow-imports --include-package=mini_agent --include-package-data=mini_agent --output-dir=dist --output-filename=grape-agent.exe mini_agent/cli.py
          uv run --with nuitka python -m nuitka --onefile --assume-yes-for-downloads --follow-imports --include-package=mini_agent --include-package-data=mini_agent --output-dir=dist --output-filename=grape-agent-feishu.exe mini_agent/feishu/server_ws.py
          uv run --with nuitka python -m nuitka --onefile --assume-yes-for-downloads --follow-imports --include-package=mini_agent --include-package-data=mini_agent --output-dir=dist --output-filename=grape-agent-webterm-bridge.exe mini_agent/webterm_bridge/server.py
      - uses: actions/upload-artifact@v4
        with:
          name: grape-agent-${{ matrix.os }}
          path: dist/**
```

### 6.2 方案 B：远程主机手工打包

- mac 产物：在远程 mac 机器执行第 4 节命令
- windows 产物：在远程 windows 机器执行第 5 节命令

核心原则：**目标平台上构建目标平台产物**。

## 7. 本项目“实操清单”（建议直接照做）

### Step 1. 在本机先出 mac 包并归档

```bash
cd /Users/kxr/learning/Mini-Agent
uv sync
rm -rf build dist

uv run --with nuitka python -m nuitka --onefile --assume-yes-for-downloads --follow-imports --include-package=mini_agent --include-package-data=mini_agent --output-dir=dist --output-filename=grape-agent mini_agent/cli.py
uv run --with nuitka python -m nuitka --onefile --assume-yes-for-downloads --follow-imports --include-package=mini_agent --include-package-data=mini_agent --output-dir=dist --output-filename=grape-agent-feishu mini_agent/feishu/server_ws.py
uv run --with nuitka python -m nuitka --onefile --assume-yes-for-downloads --follow-imports --include-package=mini_agent --include-package-data=mini_agent --output-dir=dist --output-filename=grape-agent-webterm-bridge mini_agent/webterm_bridge/server.py

./dist/grape-agent --help
./dist/grape-agent-feishu --help
./dist/grape-agent-webterm-bridge --help

mkdir -p release/macos
cp dist/grape-agent dist/grape-agent-feishu dist/grape-agent-webterm-bridge release/macos/
tar -C release -czf release/grape-agent-macos.tar.gz macos
```

### Step 2. 在远程/CI 产出 windows 包

在 Windows Runner 或 Windows 主机执行第 5 节命令后：

```powershell
mkdir release\windows
copy dist\grape-agent.exe release\windows\
copy dist\grape-agent-feishu.exe release\windows\
copy dist\grape-agent-webterm-bridge.exe release\windows\
powershell Compress-Archive -Path release\windows\* -DestinationPath release\grape-agent-windows.zip -Force
```

### Step 3. 交付后启动验证

mac:

```bash
./grape-agent --help
./grape-agent
```

windows:

```powershell
.\grape-agent.exe --help
.\grape-agent.exe
```

## 8. 常见问题

1. 为什么不能在 mac 上直接产出 windows `.exe`？  
Nuitka 也不做通用跨平台交叉打包，必须在目标 OS 构建。

2. 打包后为什么建议外置配置？  
配置跟二进制解耦，升级时不覆盖 `settings.json`。

3. 只想用主程序，可以只打 `grape-agent` 吗？  
可以。飞书和 bridge 按需打包。

4. Linux onefile 怎么办？  
参考 `docs/DEPLOY_ONEFILE_TENGXUN1_RUNBOOK_CN.md`。

5. 如果 Nuitka 某版本遇到兼容问题怎么办？  
可先切回 PyInstaller 流程出应急包，保证交付连续性。
