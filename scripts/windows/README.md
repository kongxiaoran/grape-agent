# Grape-Agent Windows 配置初始化脚本

## 文件说明

| 文件 | 用途 | 适用场景 |
|------|------|----------|
| `init-config.bat` | 批处理脚本 | 简单快速，双击运行 |
| `init-config.ps1` | PowerShell 脚本 | 功能完整，带验证和交互 |

## 使用方法

### 方式一：批处理脚本（推荐小白用户）

1. 将 `settings.json`（已填写好 API Key 等配置）放在与 `init-config.bat` 同目录
2. 双击运行 `init-config.bat`
3. 脚本会自动将配置复制到 `%USERPROFILE%\.grape-agent\config\`

### 方式二：PowerShell 脚本（推荐进阶用户）

1. 将 `settings.json` 放在与 `init-config.ps1` 同目录
2. 右键点击 `init-config.ps1`，选择"使用 PowerShell 运行"
   - 或在 PowerShell 中执行：`powershell -ExecutionPolicy Bypass -File init-config.ps1`
3. 脚本会：
   - 验证 JSON 格式
   - 显示关键配置（API Key 脱敏显示）
   - 备份已有配置
   - 提供覆盖/保留/比较选项

## 目录结构示例

```
D:\GrapeAgent\
├── grape-agent.exe          # 主程序
├── init-config.bat          # 配置初始化脚本
└── settings.json            # 待安装的配置文件（用户提前填好）
```

运行脚本后，配置文件会被复制到：
```
C:\Users\<用户名>\.grape-agent\config\settings.json
```

## 分发建议

给用户打包时，可以按以下结构：

```
grape-agent-windows.zip
├── grape-agent.exe
├── grape-agent-feishu.exe
├── init-config.bat          # 包含这个脚本
├── settings.json.example    # 配置模板，带说明
└── 使用说明.txt
```

`使用说明.txt` 示例：

```
1. 将 settings.json.example 复制为 settings.json
2. 编辑 settings.json，填入你的 API Key
3. 双击运行 init-config.bat 安装配置
4. 运行 grape-agent.exe 开始使用
```

## 注意事项

1. **配置文件优先级**：程序启动时会按以下顺序查找配置：
   - 当前目录（开发模式）
   - `%USERPROFILE%\.grape-agent\config\settings.json`（用户配置）
   - 打包内置的默认配置

2. **升级保留配置**：配置文件放在用户目录，升级 exe 时不会被覆盖

3. **多用户支持**：每个 Windows 用户有自己的独立配置
