# v0.2 下一主线的并行分包

状态（2026-10-30）：A—H 均已交付并接线；本表保留历史文件分工，不重复派发。公共签名见 [CONTRACTS.md](CONTRACTS.md)，当前门槛与实际验证见[发布记录](../../releases/0.2.0.md)。

## 范围

本表最初覆盖⑩，后续 F/G/H 已补齐⑧登录态、④只读自检、⑦诊断/模板和⑨a Skill，并由 S 接线；完整回归和构建验收以统一发布记录为准。净室提示词继续备用。

## 分包与所有权

下列源码路径均相对 `src/misong/`，测试路径相对仓库根。没有列出的共享文件只由总集成负责人修改。

| 包 | 负责内容与独占文件 | 依赖与验收 |
|---|---|---|
| S 总集成 | `text_contracts.py`、`carriers/base.py`、`carriers/__init__.py`、`tests/test_text_contracts.py`；`cli.py`、`desktop/api.py`；项目元数据、AGENTS、.gitignore、公共文档；API/CLI 集成测试 | 公共接口准备已完成；最后统一接线、回归和文档，不与其他包抢文件 |
| A 文字链 | `text_layers.py`、`text_pipeline.py`、`sharing.py`；`tests/test_text_pipeline.py` | 按 01 实现；旧多选保持并列，文字正逆向逐字一致 |
| B 钥匙与还原 | `text_key.py`、`text_restore.py`；`tests/test_text_key.py`、`tests/test_text_restore.py` | 按 02 和 03 任务 1 的还原部分；先以 fake pipeline/carrier 开发，A/C 完成后真实联调；CLI 变更交 S |
| C 帧语网页驱动 | `carriers/framewords_web.py`；`tests/test_framewords_web.py`；`scripts/verify_framewords_web.py` | 按 03；先用纯文字合成输入独立验证生成、下载、重新读取，B 完成后验证钥匙全链；不改 text_restore |
| D 发布编排 | `publish.py`、`workflows.py`、`cleanup.py`；`tests/test_text_publish.py` | 按 04 任务 1；fake 服务先测重试、状态、清理，A/B/C 完成后接真实实现 |
| E 桌面前端 | `desktop/web/app.js`、`index.html`、`app.css`；`tests/test_text_ui.py`；`scripts/ui_preview.py` | 按 04 任务 3；依据 S 的 API 契约用模拟数据开发，S 接桥后端到端验证；不改 desktop/api.py |

B/C/D 所需已有回归测试可以运行；如须修改非本包测试，由 S 统一处理或明确转交所有权。公共依赖、异常类型、签名变更先记入契约，不让各包自行创造不兼容版本。

本轮 S 新增 `text_delivery.py`、`tests/test_text_integration.py` 并接线 publish/CLI/API。D 后续须在已有 `deliver_shared`、`text_recipes` 和新发布参数上扩展，不重复创建交付引擎；E 直接对接已实现桌面桥。A/B/C 不再重新派发，除非集成发现需要修复的问题。

## 开工顺序

1. **S 接口准备（已完成）**：已创建 `CONTRACTS.md` 并落实最小公共类型，明确方案/层模型、运行时密钥槽、文字链结果、carrier 输入输出、错误/取消、钥匙导出与还原入口，以及桌面 API 请求/响应和任务状态。A/B/C 按契约实现自己的模块；新 API/CLI 的实际接线仍待 S 后续完成。
2. **第一批并行 A、B、C**：冻结接口后同时启动。B 使用替身隔离尚未完成的 A/C；C 的真实网站最小实验无需等完整钥匙或 GUI。各自通过本包测试，不把替身通过报告成集成通过。
3. **第二批并行 D、E**：S 接收第一批、解决接口差异并稳定 API 后启动。D 与 E 使用契约/替身互不等待，S 同时完成 CLI 与桌面桥接线。若接口准备充分，也可提前做 D/E 的独立测试和模拟界面，但不能提前宣称真实链路可用。
4. **S 统一验收**：合并所有成果后执行 05：完整离线 pytest、真实官网独立回读、视频＋钥匙全链、浅深色预览、文档与敏感信息检查。官网不可用时明确留下真实验收缺口；本批无发布授权，不创建 Release。

建议同时运行 3 个开发 agent，加 1 个集成负责人。不要把 01—05 原样同时交给五个 agent：它们共享 text_restore、CLI/API 和文档，会产生覆盖与接口冲突。

## 可直接复制的派发模板

将下面的 `{包号}` 替换为 A/B/C/D/E；S 由负责集成的对话承担。

> 请执行 `docs/plans/2026-10-29-text-pipeline/PARALLEL.md` 的 {包号} 包。先读 AGENTS.md、开发指南、支持情况、本计划 README、对应阶段计划及 S 交付的 CONTRACTS.md。只修改本包独占文件；你不是唯一工作者，不撤销或覆盖他人的改动。跨包变更提交接口请求给集成负责人，不直接改共享文件。若契约未交付，先完成范围内阅读和可独立实验，明确列出所需接口，不擅自定稿共享协议。遵守当前 RPA 主线，不启动净室研究。用合成数据完成本包测试，报告实际命令、通过/失败、替身与真实验证区别、改动文件及待集成事项。不得将未验收功能标成完成，也不自动发送外部消息或发布。

每包交付须带接口说明、测试结果和未完成项。S 负责将各包行为变更统一同步到 docs/status、CHANGELOG 和用户文档，保证最终交付符合仓库要求。

## 工作区交接

当前工作区已有未提交的 v0.2 成果。开始前由 S 记录基线；同目录协作严格遵守所有权。若另建 worktree，必须从包含这些成果及当前计划的共同基线创建，不能直接从 v0.1.0 或旧 HEAD 开工遗漏未提交内容。不要自动丢弃、暂存清空或回滚既有改动。
