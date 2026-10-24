# 密送品牌图标

项目采用整块黄油的插画作为图标，中文名为 **密送**，英文名与命令为 **Misong / misong**。

- `butter-source.png` 是本项目设计过程中生成、由维护者选定的透明底原图。
- 发布台左上角与 README 使用 `src/misong/desktop/web/branding/logo.png`。
- Windows 标题栏、任务栏与旧版 Tk 窗口使用同目录的 `logo.ico`，包含
  16、20、24、32、40、48、64、96、128、256 像素图层。
- 网页图标也复用同一份 ICO。图标随 Python 包分发，不依赖仓库工作目录。

安装开发依赖后，在仓库根目录重新导出：

```powershell
.venv\Scripts\python scripts\build_branding.py
```

导出只调整透明画布留白、等比例缩放及转换格式，不重绘原图。原图保持不变。
新增或替换图标后运行浅色、深色界面预览，并检查 Windows 原生窗口图标。

Windows 桌面端使用 pywebview 6.2.1 及以上版本的 `icon` 参数；启动前设置稳定的
`Misong.Desktop` AppUserModelID，将密送归入独立的任务栏分组。
源代码运行时，`start-gui.cmd` 仍由 Python 启动；脚本文件本身的资源管理器图标由系统决定。
