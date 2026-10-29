# 文案交付集成（v0.2 开发版）

本阶段将 A 文字链、B 文案钥匙和 C 帧语网页驱动接入共同服务 `misong.text_delivery`、CLI 和桌面桥。GUI 第四步层编辑器、结果展示及文案还原表单仍待 E 包完成，当前界面上的旧文案选项沿用旧行为。B 站取流、音频/混合、自主离线视频编解码未实现。

## 命令行

将下列公开配方保存为 `recipes.json`，不填写密码；原文文件使用 UTF-8，保留换行。

```json
[
  {"version":1,"id":"encoded","name":"Base64 文案","layers":[
    {"id":"text","scheme":"base64","version":1,"params":{},"secret_slot":null}
  ],"carrier":{"format_id":"text","version":1,"mode":"plain","params":{},"secret_slot":null}}
]
```

```powershell
misong text-deliver 原文.txt --recipes recipes.json --export-key encoded -o 文案输出
misong text-restore 文案输出/encoded/message.txt --input-kind text --key-file 文案输出/encoded/message.tkey -o 还原文案.txt
```

输出目录必须尚不存在；还原目标为尚不存在的文件，父目录须存在。省略 `--export-key` 时不生成钥匙。输出原文不会隐式 trim、换行或 Unicode 归一化。手动配方可使用 `--recipe recipes.json`，但必须恰好一份；手动还原没有原文摘要保证。`.tkey` 是直接还原凭据，不要提交 Git、放入普通任务/设置或自动上传。

视频方案将 carrier 换成 `{"format_id":"framewords","version":1,"mode":"standard","params":{},"secret_slot":"encoded/video"}`，生成命令再加 `--video 本地源视频.mp4`；视频密码及魔曰层密钥由终端交互输入。没有密码时 slot 设为 null。接收方使用 `text-restore 视频.mp4 --input-kind video --key-file 文案.tkey -o 还原文案.txt`。视频生成与读取会联网正常操作官网，需安装 RPA 依赖及浏览器；保存后独立读取校验才成功，纯文字路径不启动浏览器。

## 发布接线与恢复

```powershell
misong publish 资源目录 -o 发布任务 --text-recipes recipes.json --export-text-key encoded
misong publish --plan 发布任务/relay-plan.json
```

新配方与显式 `--schemes` 互斥；不指定新配方时旧参数默认行为不变。库调用 `PublishOptions(text_recipes=公开配方元组, schemes=(), ...)`。`--text-video` 仅本次指定视频源，续跑时重新提供；钥匙导出选项也只影响本次尚未完成的方案，不作为全局或任务偏好保存。

分享完成后逐方案保存 status/artifacts/error_code 和原文摘要；完整文案和密钥不进入新检查点。成功方案复用文件指纹，失败方案重新生成到新的尝试目录；中断产物不覆盖，旧钥匙不与新随机密文混用。文案失败不重传已分享资源；全部交付完成后才允许既有加工产物清理，最终文案/视频及钥匙不登记成可删中间文件。分享文案来源改变时摘要不符会停止，避免复用旧内容。重试仍需用户重新输入缺失密钥。

## 桌面桥（已接线，前端待接）

新方法为 `text_capabilities`、`preview_text_delivery`、`start_text_delivery`、`start_text_restore`，使用既有 `{ok:true,data:...}` 包装和 job 事件。`Api._start` 仍是唯一任务入口；不创建另一套调度器。预览只校验公开结构/能力，不预编码随机密文。运行时 cfg 不写任务或设置，事件只交付文件元数据，原文写入用户明确选择的文件。

`start_pipeline` 可接 recipes/text_secrets/text_video_sources/export_text_keys；recipes 与旧 schemes 互斥。`resume_task` 增加可选第四参数 text_cfg={secrets,video_sources,export_keys}，旧调用保持可用。文案公开配方随发布计划保存；运行密钥不保存。公共 API 详细字段见[契约](../plans/2026-10-29-text-pipeline/CONTRACTS.md)。E 应接入这些已实现方法，不再建立重复服务。D 后续扩展须保留已接入的检查点与重试测试。

## 验证边界

集成测试 `tests/test_text_integration.py` 使用真实 A/B 算法和合成输入，视频部分用替身验证密码隔离及编排；日常测试不访问官网或真实网盘。C 包的合成素材验收记录显示：2026-10-29 官网 2.7.8、Chromium 156.0.8078.4，最后一批 6 个案例的生成、独立读取和 `.tkey` 还原通过。该记录不能证明平台转码、所有网页版本或所有浏览器可用；本轮 S 没有重复真实网站实验，也没有新增真实网盘验收。
