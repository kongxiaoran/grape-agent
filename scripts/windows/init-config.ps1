#!/usr/bin/env pwsh
# Grape-Agent 配置文件初始化工具 (PowerShell 版本)
# 功能更强大，支持验证和交互

$ErrorActionPreference = "Stop"

# 路径定义
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$SourceConfig = Join-Path $ScriptDir "settings.json"
$TargetDir = Join-Path $env:USERPROFILE ".grape-agent\config"
$TargetConfig = Join-Path $TargetDir "settings.json"

# 颜色定义
$Green = "Green"
$Yellow = "Yellow"
$Red = "Red"
$Cyan = "Cyan"

function Write-Header {
    Write-Host "==========================================" -ForegroundColor $Cyan
    Write-Host "    Grape-Agent 配置文件初始化工具" -ForegroundColor $Cyan
    Write-Host "==========================================" -ForegroundColor $Cyan
    Write-Host ""
}

function Test-ValidJson {
    param([string]$Path)
    try {
        $null = Get-Content $Path -Raw | ConvertFrom-Json
        return $true
    } catch {
        return $false
    }
}

function Backup-ExistingConfig {
    param([string]$Path)
    $Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $BackupPath = "$Path.backup.$Timestamp"
    Copy-Item -Path $Path -Destination $BackupPath -Force
    return $BackupPath
}

# 主程序
Write-Header

# 1. 检查源文件
Write-Host "[1/4] 检查源配置文件..." -ForegroundColor $Cyan
if (-not (Test-Path $SourceConfig)) {
    Write-Host "[错误] 未找到配置文件：settings.json" -ForegroundColor $Red
    Write-Host ""
    Write-Host "请将 settings.json 放在以下目录：" -ForegroundColor $Yellow
    Write-Host "  $ScriptDir"
    Write-Host ""
    Read-Host "按 Enter 键退出"
    exit 1
}
Write-Host "      找到：$SourceConfig" -ForegroundColor $Green

# 2. 验证 JSON 格式
Write-Host ""
Write-Host "[2/4] 验证配置文件格式..." -ForegroundColor $Cyan
if (-not (Test-ValidJson -Path $SourceConfig)) {
    Write-Host "[错误] settings.json 格式不正确，请检查 JSON 语法" -ForegroundColor $Red
    Read-Host "按 Enter 键退出"
    exit 1
}
Write-Host "      JSON 格式验证通过" -ForegroundColor $Green

# 读取并显示关键配置（脱敏）
try {
    $Config = Get-Content $SourceConfig -Raw | ConvertFrom-Json
    Write-Host "      检测到配置：" -ForegroundColor $Green
    Write-Host "        - API Base: $($Config.api_base)"
    Write-Host "        - Model: $($Config.model)"
    Write-Host "        - Provider: $($Config.provider)"
    $ApiKeyMasked = if ($Config.api_key -and $Config.api_key -ne "YOUR_API_KEY_HERE") {
        "已设置 (" + $Config.api_key.Substring(0, [Math]::Min(8, $Config.api_key.Length)) + "***)"
    } else {
        "未设置或需要修改"
    }
    Write-Host "        - API Key: $ApiKeyMasked"
} catch {
    Write-Host "      警告：无法解析配置详情" -ForegroundColor $Yellow
}

# 3. 创建目标目录
Write-Host ""
Write-Host "[3/4] 准备目标目录..." -ForegroundColor $Cyan
if (-not (Test-Path $TargetDir)) {
    New-Item -ItemType Directory -Path $TargetDir -Force | Out-Null
    Write-Host "      创建目录：$TargetDir" -ForegroundColor $Green
} else {
    Write-Host "      目录已存在：$TargetDir" -ForegroundColor $Green
}

# 4. 处理文件复制
Write-Host ""
Write-Host "[4/4] 安装配置文件..." -ForegroundColor $Cyan

if (Test-Path $TargetConfig) {
    Write-Host "      检测到已有配置" -ForegroundColor $Yellow
    Write-Host ""

    $Choices = @(
        [System.Management.Automation.Host.ChoiceDescription]::new("&覆盖", "用新配置替换现有配置（会备份）")
        [System.Management.Automation.Host.ChoiceDescription]::new("&保留", "保留现有配置，退出")
        [System.Management.Automation.Host.ChoiceDescription]::new("&比较", "显示两个文件的差异")
    )

    $Decision = $Host.UI.PromptForChoice("", "选择操作", $Choices, 1)

    switch ($Decision) {
        0 {  # 覆盖
            $Backup = Backup-ExistingConfig -Path $TargetConfig
            Write-Host "      已备份原配置到：$(Split-Path $Backup -Leaf)" -ForegroundColor $Green
        }
        1 {  # 保留
            Write-Host ""
            Write-Host "已取消，保留现有配置。" -ForegroundColor $Yellow
            Read-Host "按 Enter 键退出"
            exit 0
        }
        2 {  # 比较
            Write-Host ""
            Write-Host "当前配置（前20行）：" -ForegroundColor $Cyan
            Get-Content $TargetConfig -TotalCount 20 | ForEach-Object { Write-Host "  $_" }
            Write-Host ""
            Write-Host "新配置（前20行）：" -ForegroundColor $Cyan
            Get-Content $SourceConfig -TotalCount 20 | ForEach-Object { Write-Host "  $_" }
            Write-Host ""

            $Continue = Read-Host "是否继续覆盖？(Y/N)"
            if ($Continue -ne "Y" -and $Continue -ne "y") {
                Write-Host "已取消。" -ForegroundColor $Yellow
                Read-Host "按 Enter 键退出"
                exit 0
            }
            $Backup = Backup-ExistingConfig -Path $TargetConfig
            Write-Host "      已备份原配置" -ForegroundColor $Green
        }
    }
}

# 执行复制
Copy-Item -Path $SourceConfig -Destination $TargetConfig -Force
Write-Host "      配置已安装到：$TargetConfig" -ForegroundColor $Green

# 完成提示
Write-Host ""
Write-Host "==========================================" -ForegroundColor $Green
Write-Host "    配置初始化完成！" -ForegroundColor $Green
Write-Host "==========================================" -ForegroundColor $Green
Write-Host ""
Write-Host "现在可以运行以下命令启动：" -ForegroundColor $Cyan
Write-Host "  .\grape-agent.exe"
Write-Host ""
Write-Host "配置文件位置：" -ForegroundColor $Cyan
Write-Host "  $TargetConfig"
Write-Host ""
Read-Host "按 Enter 键退出"
