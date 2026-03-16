@echo off
chcp 65001 >nul
title Grape-Agent 配置初始化工具

set "SOURCE_CONFIG=%~dp0settings.json"
set "TARGET_DIR=%USERPROFILE%\.grape-agent\config"
set "TARGET_CONFIG=%TARGET_DIR%\settings.json"

echo ==========================================
echo    Grape-Agent 配置文件初始化工具
echo ==========================================
echo.

:: 检查源配置文件是否存在
if not exist "%SOURCE_CONFIG%" (
    echo [错误] 未找到配置文件 settings.json
    echo.
    echo 请将 settings.json 放在与本脚本相同的目录下：
    echo %~dp0
    echo.
    pause
    exit /b 1
)

echo [1/3] 找到配置文件：%SOURCE_CONFIG%

:: 创建目标目录（如果不存在）
if not exist "%TARGET_DIR%" (
    echo [2/3] 创建配置目录：%TARGET_DIR%
    mkdir "%TARGET_DIR%"
) else (
    echo [2/3] 配置目录已存在：%TARGET_DIR%
)

:: 检查目标文件是否已存在
if exist "%TARGET_CONFIG%" (
    echo.
    echo [警告] 用户目录已存在配置文件！
    echo 目标：%TARGET_CONFIG%
    echo.
    choice /C YN /M "是否覆盖现有配置文件"
    if errorlevel 2 (
        echo.
        echo 已取消，保留现有配置。
        pause
        exit /b 0
    )
    :: 备份原配置
    set "BACKUP_FILE=%TARGET_CONFIG%.backup.%date:~0,4%%date:~5,2%%date:~8,2%_%time:~0,2%%time:~3,2%%time:~6,2%"
    set "BACKUP_FILE=%BACKUP_FILE: =0%"
    copy "%TARGET_CONFIG%" "%BACKUP_FILE%" >nul
    echo 已备份原配置到：%BACKUP_FILE%
)

:: 复制配置文件
echo [3/3] 复制配置文件...
copy /Y "%SOURCE_CONFIG%" "%TARGET_CONFIG%" >nul

if errorlevel 1 (
    echo.
    echo [错误] 复制失败，请检查权限。
    pause
    exit /b 1
)

echo.
echo ==========================================
echo    配置初始化完成！
echo ==========================================
echo.
echo 配置文件已安装到：
echo %TARGET_CONFIG%
echo.
echo 现在可以直接运行 grape-agent.exe 了
echo.
pause
