# S 公共契约 v1

日期：2026-10-29。状态：A/B/C 已完成，S 已接通公共交付服务、CLI、桌面桥及发布检查点；GUI 层编辑及还原表单待 E。下文“约定”保留原接口归属，已实现范围以[集成说明](../../dev/text-delivery.md)为准。公共签名保持 v1，当前不新增协议研究或独立编解码。

## 基线与所有权

准备前 HEAD：`726d91ecdc2fbeb284f5db10528dffa94cd26ad2`。工作区已有未提交的还原钥匙、数据目录、doctor、脱敏及计划文档等 v0.2 成果；此 HEAD 单独不足以重建当前共同基线。不得 reset/clean 或把其他包的修改回滚。派发时让 agent 使用包含当前未提交成果的同一工作区，或由维护者先整理共同快照后创建 worktree。

以 [PARALLEL.md](PARALLEL.md) 为所有权表。补充：`src/misong/text_contracts.py`、`tests/test_text_contracts.py` 归 S；A/B/C/D/E 只导入公共类型，不擅自改签名。契约变更交 S 协调，更新此文及调用方测试后再生效。01—05 的功能验收继续有效，但其中共享文件修改归 S。

## 已实现的公共 Python 类型

从 `misong.text_contracts` 导入：

- `ErrorCode`、`TextOperationError(code)`：仅传稳定错误码，不把网页、解码器或异常原文塞入错误消息。失败边界统一映射为这些码，S 在用户界面映射中文提示；不得保留含私密内容的异常链到日志。
- 错误码：`invalid_recipe / unsupported / capacity / missing_secret / wrong_password / integrity / media / network / page_changed / download / timeout / cancelled / io`。不能确定是密码问题时使用 integrity/media，不凭失败猜密码错误。
- `RuntimeSecrets(values: Mapping[str, str])`：每次操作独立创建，`require(slot)` 取值，缺失抛 missing_secret；结束调用 `clear()`。空字符串与缺失不同，由具体算法校验。不暴露普通序列化接口，不承诺内存物理擦除。
- `OperationContext(secrets=..., cancel=..., deadline=..., notify=...)`：同步上下文，cancel 兼容 `threading.Event`；deadline 为绝对 `time.monotonic()` 时间。循环、等待和返回结果前调用 `check()`，浏览器等待也必须有界，取消后释放资源。
- `context.report(Stage, completed=0, total=None)`：回调收到 `Progress`，只有阶段和计数，无文案、密码、链接、路径或任意消息。阶段为 preflight/text_encode/text_decode/carrier_encode/carrier_decode/verify/key_export。适配既有 notify 的工作归 S。
- `text_digest(text)`：精确 UTF-8 SHA-256；不 trim，不改换行或 Unicode 形式。容量的 characters 指 Python Unicode 码点数；另记录 utf8_bytes，官网计数须由 C 实测核对，不直接假定等于此计数。
- `LayerReceipt(layer_id, input_sha256, output_sha256, characters, utf8_bytes)`、`PipelineResult(text, receipts=())`：单次运行结果。receipt 按正向配方层序保存，characters/utf8_bytes 是该层正向输出；逆向成功返回原始正向 receipts，不重新生成随机化密文。

这些是内存对象，禁止 `asdict/vars/pickle` 后写入任务或设置。默认 repr 隐藏载荷仅用于防止意外显示，不等于可安全序列化。持久化必须经过下文公开配方白名单；用户明确导出的 `.tkey` 是敏感文件例外。

## A：配方与文字链（约定，由 A 实现）

`text_layers.py` 提供 `TextLayer`、`CarrierSpec`、`DeliveryRecipe`，以 frozen dataclass 或等价不可变对象实现；固定字段如下。提供 `DeliveryRecipe.from_dict(data)` 严格验证，以及 `recipe.to_dict()` 的白名单序列化；嵌套 params 要复制，不能泄漏可变引用。未知字段、版本和算法拒绝，不静默忽略。

```json
{
  "version": 1,
  "id": "recipe-1",
  "name": "视频文案",
  "layers": [
    {"id": "layer-1", "scheme": "mojibake", "version": 1,
     "params": {"mode": "old"}, "secret_slot": "recipe-1/layer-1"}
  ],
  "carrier": {"format_id": "framewords", "version": 1, "mode": "standard",
              "params": {}, "secret_slot": "recipe-1/video"}
}
```

魔曰 mode 沿用现有 wenyan/old，兽曰沿用已有 dialect/chars 参数，A 核对实际接口后按算法严格验证，不额外发明方言。`TextLayer` 字段为 id/scheme/version/params/secret_slot；CarrierSpec 为 format_id/version/mode/params/secret_slot；DeliveryRecipe 为 version/id/name/layers/carrier。Python recipe.layers 使用 tuple，JSON 用数组。无密码 slot 为 null。层 ID 在方案内唯一，slot 在任务内唯一，每个密码层可单独取值。裸链接的 layers 为 []；纯文本载体为 `{"format_id":"text","version":1,"mode":"plain","params":{},"secret_slot":null}`。

公开配方不含密码、原文、完整中间文案、本机文件路径、export_key 自动选中状态、网页选择器或运行后端名。params 只收算法逐项白名单参数，禁止将 key/password 通过 params 绕入。容量/层数/方案数、旧 schemes 并列迁移按 01；`trunc` 不属于可还原白名单。

`text_pipeline.py` 固定入口（同步，C 的异步 I/O 不进入此引擎）：

```python
encode_text(text: str, recipe: DeliveryRecipe, context: OperationContext) -> PipelineResult
decode_text(text: str, recipe: DeliveryRecipe, receipts: tuple[LayerReceipt, ...],
            context: OperationContext) -> PipelineResult
```

encode 只处理 layers，最终 text 交载体；载体不在此处调用。decode 对照每层 output 摘要，逆序解码后校验 input 摘要，任何失败抛异常且不返回部分结果。零层也保留原文精确语义。无 `.tkey` 的手动配方可传空 receipts，此时只能保证算法成功，不能宣称原文摘要已验证；B 负责区分 verified 状态。旧 `sharing.encode_copy/write_copy` 的签名及返回语义保持兼容。

## B：钥匙与还原（约定，由 B 实现）

`text_key.py` 提供：

```python
build_payload(recipe: DeliveryRecipe, result: PipelineResult,
              context: OperationContext) -> dict
write(path: Path, payload: dict) -> Path
read(path: Path) -> dict
```

build_payload 为敏感内存对象；write 只由明确导出分支调用，不从普通任务序列化触发。v1 magic 已冻结为 `b"MISONGTKEY\x00\x01"`，后接随机 32 字节包装钥匙、12 字节 nonce、AES-256-GCM 密文及 16 字节 tag，完整头部作为 AAD。遵守 4 MiB、32 层限制、拒绝覆盖和旧 `.mskey` 不变原则。包装钥匙随文件同行，持有者有还原能力，不提供持有者隔离或来源认证。

payload v1 的固定字段：type=`misong-text-key`、version=1、recipe（公开配方）、receipts（正向序）、original_sha256、payload_sha256、secrets（仅 recipe 引用的 slot→字符串）。零层时两摘要均为 result.text 摘要；有层时 original 来自首层 input，payload 来自末层 output，并校验其等于 result.text 摘要。拒绝额外 slot、缺失 slot、重复 ID、摘要链不连续和层序不符；不得保存原文、中间文字、会话或路径。载体格式版本不是官方网页版本，不声称 framewords 自有协议的版本号。媒体字节指纹若后续添加，须显式协调扩展，不能作为转码视频唯一准入条件。

`text_restore.py` 提供统一异步入口：

```python
async def restore_text(*, text: str | None, video: Path | None,
                       key_file: Path | None, recipe: DeliveryRecipe | None,
                       context: OperationContext, carrier: VideoCarrier | None = None) -> RestoreResult
```

text/video 恰选一个；key_file/recipe 恰选一个，拒绝歧义。手动配方从 context 获取密钥；钥匙模式先验证并建立操作私有 secrets，结束释放，不写回任务。RestoreResult 字段 text（repr 隐藏）、original_sha256、verified（有钥匙且全部摘要通过才 true）。文本输入允许官网已提取的载荷，必须匹配 payload 摘要；video 输入先通过 carrier 解外层再调用 A 的 decode。只把外层密码交 C，内层密钥留在 B；构造给 C 的 context 时用空 RuntimeSecrets，保留 cancel/deadline/notify。没有匹配后端时 unsupported，不猜算法或自动访问 URL。

## C：视频载体（接口已实现，后端由 C 实现）

从 `misong.carriers` 导入现有 dataclass/Protocol，不重复定义：

```python
class FramewordsWebCarrier:  # framewords_web.py，由 C 实现
    def capabilities(self) -> CarrierCapabilities: ...
    async def encode(self, request: EncodeRequest, context: OperationContext) -> EncodedVideo: ...
    async def decode(self, request: DecodeRequest, context: OperationContext) -> DecodedText: ...
    async def verify(self, request: DecodeRequest, expected_text: str,
                     context: OperationContext) -> DecodedText: ...
```

构造器可接受 C 的测试用浏览器工厂；生产依赖保持可选，不能导入 base 就加载 Playwright。format_id=`framewords`，backend_id=`framewords_web`。语义模式名 standard 映射官网标准画面模式。C 已留下 2.7.8 的合成素材真实验收记录，S 按需创建该后端；能力限制未知用 None，实际运行仍要页面预检。不将其他模式或版本标为已验证。

EncodeRequest 包含 source/destination/text/mode/password；DecodeRequest 包含 source/mode/password。路径与明文只存在本次运行。encode 拒绝覆盖目标、禁止修改源视频、保护下载临时文件；保存后调用独立 decode 核对才能返回 `EncodedVideo(path, payload_sha256, verified=True)`。失败抛错且不交付未验证文件。decode 返回 DecodedText(text)，必须独立读取文件，不能返回上一次 encode 的缓存输入。

verify 可委托已实现的 `verify_saved_video(self, request, expected_text, context)`。该辅助函数逐字比较并在返回前再检查取消；它不能代替 C 的真实网页、完整性和资源清理测试。正常网站操作、隔离上下文及脱敏要求按 03，异步任务取消也须 finally 清理。

## D：任务状态与续跑（约定）

每任务公开字段增加 `text_delivery: {version: 1, share_complete: bool, source_sha256: str, recipes: [...]}`；各项为 recipe_id/status/artifacts/error_code。source_sha256 绑定最终分享原文，改变来源则停止复用。status 枚举 pending/running/complete/blocked/cancelled；artifacts 只记本次生成文件的角色、路径和文件指纹，不含密码/钥匙内容/中间文案。公开配方保存在 text_recipes；运行时 secrets 永不存盘。路径进入 GUI/诊断出口按现有脱敏规则处理。

旧任务缺 text_delivery 时沿用旧语义，不追溯生成新方案。重启后的 running 视为可恢复中断，不视为 complete；缺密钥进入 blocked。独立方案逐份检查点，share_complete 后只重试文案，不能再次 upload/share。当前错误只记 error_code。最终文件及两种钥匙的清理保护按 04；敏感原文如现有显式分享文案交付需留存，沿用原有交付文件边界，不能复制进新的普通检查点。

## S/E：桌面 API 和 CLI（约定，待集成）

新 API 不复用或改变旧 `encode/decode/start_restore`：

| API | 参数与响应 | 归属 |
|---|---|---|
| `text_capabilities()` | 返回 `{ok:true, data:{recipe_version:1, carriers:[公开能力字段]}}`，只列已实现后端；未实现不假报 | S |
| `preview_text_delivery(cfg)` | cfg={text, recipes}；返回 `{ok:true, data:{recipes:[{recipe_id, needs_secrets, capacity_known, requires_network}]}}`，仅结构/能力校验，不编码、不读取密钥、不返回派生文案 | S，复用 A/C |
| `start_text_delivery(cfg)` | cfg={text, recipes, secrets, video_sources, output_dir, export_keys}；返回既有任务启动结果形状 | S，调用 A/B/C/D |
| `start_text_restore(cfg)` | cfg={text, video, key_file, recipe, secrets, output_dir}，遵守 B 的互斥规则；返回既有任务启动结果形状 | S，调用 B |

`video_sources` 为 recipe_id→本机源视频路径；`export_keys` 为 recipe_id 列表，默认 []，仅本次显式选择才导出。secrets 为 slot→字符串，属于运行时字段，传输后绝不进入设置、模板、任务 JSON 或日志；调试工具也不能记录 cfg。普通模板只保存 recipes 的公开白名单，恢复模板时 export_keys 清空。输出目录用于原文最终交付，拒绝覆盖既有目标；不把恢复原文回传到可持久化的 job 摘要。失败响应沿用 `{ok:false,error:安全中文提示}`，可加 error_code；不得把原始异常回传。

最小合成运行请求：

```json
{"text":"https://example.invalid/s/demo","recipes":[{"version":1,"id":"plain","name":"原文","layers":[],"carrier":{"format_id":"text","version":1,"mode":"plain","params":{},"secret_slot":null}}],"secrets":{},"video_sources":{},"output_dir":"<用户选择的输出目录>","export_keys":[]}
```

S 接现有 `Api._start` 生命周期、事件队列和取消入口，不建立第二套任务调度；E 用模拟桥数据开发。成功启动的 data 是现有 job 字典，例如 `{"ok":true,"data":{"id":"demo0001","kind":"text-delivery","title":"生成文案","plan":null,"started":0,"step":"准备中…"}}`；完成仍走 job 事件。新任务 worker 先将私密异常映射为安全错误码，避免原始异常被事件记录。任务成功摘要只返回文件路径、方案状态和 verified 标志，正文在用户明确交付文件中；不得为 UI 预览重新执行一次随机编码。CLI 已接入 text-deliver/text-restore，显式 `--input-kind text/video` 分流，手动配方入口为 `--recipe`。密码走交互，不新增命令行明文密码参数。

## S 准备阶段完成条件（历史）

公共类型、错误/取消及独立回读辅助函数的离线测试通过；文档链接存在；A/B/C 所需签名已明确。这里只验收公共边界，不宣称文字链、`.tkey`、真实网页或 GUI 已完成。A/B/C 可以并行交付，S 在结果齐备后再执行第二阶段接线与完整 05 验收。

## S 集成交付（当前）

已新增 `text_delivery.py`（S 所有）负责 encode→精确逆向自检→文字/视频交付→显式钥匙导出；`restore_to_file` 负责最终原文文件交付。`deliver_shared` 负责发布检查点、来源摘要绑定及逐方案恢复，不操作上传/分享。CLI/API 参数和实际示例以[接线说明](../../dev/text-delivery.md)为准。D 后续扩展须保留这些行为及 `tests/test_text_integration.py`，E 可直接接已实现的桥方法。桌面 GUI 未完成，不能将本次后端验收写成 05 的最终 UI 验收。
