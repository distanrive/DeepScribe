"""DeepScribe 控制层 —— GUI 无关的共享模块。

CLI 与 Godot GUI 的后端共用这里的实现：

- `config_store` —— config.json 读写 + Windows DPAPI 加密 API Key
- `gpu_lock`     —— 跨进程 MinerU 槽位锁（GPU 显存保护）
- `worker`       —— 单文件流水线子进程入口（stdout 上回传进度标记）

这一层**不导入任何 GUI 框架** —— 后端是要拿 `websockets` 跑的，
这里混进 GUI 依赖会让「只想跑后端」变成得先装一整套界面工具。
"""
