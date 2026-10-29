---
phase: 5
plan: 1
wave: 5
depends_on: [04-integration]
files_modified: [docs/user-guide.md, docs/receiver-guide.md, docs/dev/development.md, docs/status.md, docs/roadmap.md, CHANGELOG.md, README.md]
autonomous: true
must_haves:
  truths: [实际支持与规划分开报告, 原有打包和 mskey 回归通过, 无敏感或第三方研究文件进入交付]
  artifacts: [docs/user-guide.md, docs/receiver-guide.md, docs/status.md]
---

# 05 验收与文档

## 任务 1：说明实际行为

- **文件**：`docs/user-guide.md`、`docs/receiver-guide.md`、`docs/dev/development.md`、`docs/status.md`。
- **动作**：说明多个方案与方案内层序的区别；记录裸链接/魔曰→视频示例、容量预检、`.tkey` 持有者权限、独立交付与逆序还原。明确视频步骤由密送操作官网完成、需要网络；纯文字处理可离线，官网不接收整个密送钥匙，B 站当前仍为手动官网入口。文案层密码、网盘提取码和资源压缩密码分别说明。
- **动作**：状态只写实际通过的浏览器、网页版本、模式及测试；不把网页在设备内处理说成应用离线能力。未验证的 B 站转码、音频/混合、自定义区域和自主兼容不得标成支持。删除不存在的假设，不使用真实分享链接、截图或研究源码举例。
- **验证**：核对 CLI/API/GUI 和文档逐项一致，检查相对链接存在；按新文档使用合成文案完成一次 `.tkey` 还原。
- **完成**：接收方能知道所需文件、工具和还原顺序，开发者能明确判断已验证边界。

## 任务 2：回归、发布记录与范围复查

- **文件**：`docs/roadmap.md`、`CHANGELOG.md`、`README.md`。
- **动作**：把当前 RPA 交付与未排期的净室研究分开记录，保留两份备用提示词。确认不改变魔曰 vendor 或现有 `.mskey` 格式，不把帧语自有代码/组件复制进发行包；复查普通任务/设置/日志无文案密钥，`.tkey` 没有被 Git 跟踪。测试本地合成内容，不访问真实网盘。
- **验证**：`.venv\Scripts\python -m pytest -q`；浅色/深色预览已通过且无新增 UI 变化时不重复生成；执行 `git diff --check` 和 `git ls-files '*.tkey' '*.mskey' 'tmp/*' 'rpa/state/*' 'runs/*'`，最后一项不得出现敏感交付文件。检查工作区原有改动没有被清除。
- **完成**：报告实际测试数量、跳过原因、真实官网生成/独立回读及 `.tkey` 全链路结果；只将自有源码、文档与合成测试纳入变更。官网不可用时完成离线部分并标记真实验收未完成，不把模拟页面测试等同于网站实际可用，也不把 RPA 描述为自主实现。
