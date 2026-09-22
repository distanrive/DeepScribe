@echo off
REM ============================================================
REM DeepScribe Godot GUI 启动脚本 —— 示例
REM
REM 复制为 run_godot_gui.bat（已 gitignore）后按本机情况改下面两行：
REM   GODOT    Godot 4.7 可执行文件（用**不带 console 的**那个，不弹黑框）
REM   PROJECT  本仓库里的 godot_gui 目录
REM
REM 后端不用手动开：Godot 端连不上会自动按 godot_gui/project.godot 的
REM [backend] 段把 Python 后端拉起来（python 那一行也要按本机改）。
REM ============================================================

set "GODOT=D:\Program Files\Godot_v4.7.2-stable_win64\Godot_v4.7.2-stable_win64.exe"
set "PROJECT=%~dp0godot_gui"

if not exist "%GODOT%" (
    echo [错误] 找不到 Godot：%GODOT%
    echo         请编辑本脚本的 GODOT 变量，指向本机的 Godot 4.7 可执行文件。
    pause
    exit /b 1
)
if not exist "%PROJECT%\project.godot" (
    echo [错误] 找不到工程：%PROJECT%\project.godot
    pause
    exit /b 1
)

start "" "%GODOT%" --path "%PROJECT%" %*
