@echo off
REM DeepScribe GUI 启动脚本示例。
REM 用法：复制本文件为 run_gui.bat，按需修改后双击运行。
REM 说明：run_gui.bat 已加入 .gitignore（其中可能含个人用户名/路径），不会入库。
REM pythonw.exe 以无控制台窗口方式启动 GUI；%USERPROFILE% 自动解析为当前用户目录，
REM 无需硬编码用户名。
cd /d "%~dp0"
start "" "%USERPROFILE%\.conda\envs\deepscribe\pythonw.exe" -m gui.main
