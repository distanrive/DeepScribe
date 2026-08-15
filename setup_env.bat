@echo off
REM DeepScribe 一键配置 conda 环境（mineru + PyTorch CUDA + GUI 依赖）
REM 用法：双击运行（需已安装 conda 且可在当前 shell 中调用 conda 命令）
setlocal

set ENV_NAME=deepscribe
set PYTHON_VER=3.10

echo ============================================================
echo   DeepScribe 环境配置：%ENV_NAME% (Python %PYTHON_VER%)
echo ============================================================
echo [1/3] 创建 conda 环境
call conda create -n %ENV_NAME% python=%PYTHON_VER% -y || goto :err
call conda activate %ENV_NAME% || goto :err

echo [2/3] 安装 MinerU + 流水线依赖 + PyQt5（GUI）
call pip install "mineru[all]" openai python-dotenv PyMuPDF PyQt5 || goto :err

echo [3/3] CUDA 版 PyTorch（GPU 用户，hybrid-engine 需要）
echo    RTX 4060 + Driver 560.94 对应 CUDA 12.6，安装 cu126 版：
echo      pip uninstall torch torchvision torchaudio -y
echo      pip install torch==2.8.0 torchvision==0.23.0 --index-url https://download.pytorch.org/whl/cu126
echo    验证：python -c "import torch; print(torch.cuda.is_available())" 应输出 True
echo ------------------------------------------------------------
echo 环境 %ENV_NAME% 就绪。
pause
exit /b 0

:err
echo 出错，请检查上方日志。
pause
exit /b 1
