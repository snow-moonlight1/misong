# 数据目录解析与迁移

`src/misong/paths.py` 是 v0.2“数据目录可配置”的前置基础模块：只负责解析路径与显式迁移，
解析本身不创建目录、不读取会话内容。主线已对接 CLI、桌面端、旧版 Tk 与浏览器运行时的默认路径。

## resolve_paths()

```python
from misong.paths import resolve_paths

paths = resolve_paths()          # Paths(home=..., state=..., runs=...)
paths.home / "rpa" / "state" == paths.state
paths.runs                       # <home>/runs
```

优先级与取值：

| 场景 | home |
| --- | --- |
| 设置了 `MISONG_HOME`（非空） | 该值（展开 `~`，转为绝对路径） |
| 源码 checkout（含 `pip install -e`）未设置 | 仓库根，即沿用 `rpa/state/`、`runs/` 原目录 |
| 普通安装未设置 | Windows `%LOCALAPPDATA%/misong`（缺省回落 `%USERPROFILE%\AppData\Local\misong`）；macOS `~/Library/Application Support/misong`；Linux `$XDG_DATA_HOME/misong`，缺省 `~/.local/share/misong` |

- 空白的环境变量值视为未设置；`resolve_paths()` 接受可选 `env` 映射便于测试。
- 只计算路径，不创建任何目录，也不迁移或读取既有数据。

## runtime 的关系

- `rpa/runtime.py` 的 `ROOT` 仍是源码根兼容符号，含义不变。
- `DEFAULT_STATE` 改为 `resolve_paths().state` 的解析结果：源码 checkout 中仍等于
  `ROOT / "rpa" / "state"`，设置了 `MISONG_HOME` 时随其变化。
- `BrowserRuntime(state_dir=...)` 未传参时在**构造时刻**解析默认状态目录，
  导入之后的环境变量变化不会锁死；已创建的实例不受后续变化影响。显式传参优先。

## migrate_data(source, destination)

独立、显式的迁移函数：仅复制调用者指定的旧数据目录，不自动推断源或目标。
典型用法是把旧 `rpa/state` 与旧 `runs` 分别复制到新 home 下对应位置。

- 只复制，原目录完整保留；测试确认逐文件字节一致、空目录也保留。
- 校验先于任何写入：源缺失、源/目标是符号链接或 Windows 目录联接（junction）、
  目标位于源目录内部、目标已有同名目录或**不同内容**的文件，均整体拒绝
  （`MigrationError`），目标保持原样。
- 目标已存在**相同内容**的文件时跳过，可安全重跑（幂等）。
- 不接触真实会话；是否迁移、何时迁移由调用方决定。

## 使用与集成

关闭密送及其专用浏览器后，在旧源码目录执行（以下仅为操作示例，不会自动执行）：

```powershell
$env:MISONG_HOME = "D:\MisongData"
misong data-migrate .\rpa\state "$env:MISONG_HOME\rpa\state"
misong data-migrate .\runs "$env:MISONG_HOME\runs"
misong gui
```

环境变量须在启动应用前设置。迁移是复制，旧目录保留；已保存的自定义产物目录和历史任务路径也保留，
不会因为设置 home 而改写用户先前选择。每次 CLI 调用只迁移明确指定的一个目录。
校验还覆盖目标父目录中的符号链接/联接，以及“源子目录与目标文件同名”的冲突，先检查后写入。
若无法完整遍历源目录，预检即报错停止，避免把不完整复制误报为迁移成功。

桌面 `Api` 与 `BrowserRuntime` 在构造时解析默认值，显式 `runs_dir` / `state_dir` 参数优先。

## 测试

`tests/test_paths.py` 全部使用 `tmp_path` 与合成内容，不读取、不提交真实
`rpa/state/`；覆盖已登录状态文件、设置和任务目录的无损迁移与各类冲突。
