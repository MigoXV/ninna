# UI 与 Figma 同步

当前工作任务 v2 使用 [界面索引](../figma-work-v2.json)，保留 11 个界面及两套主题画板。Figma 只保留 10 个 Page：白垣与苍渊各 4 页（项目与任务、模型与数据、训练环境、设置），设计规范和公共组件各 1 页。相关界面在 Page 内用命名 Section 分组排列。完整顺序与实时 ID 见 [页面目录](figma-page-order.json)。

界面索引的顶层 `page`、`frame`、`section` 指向白垣版，`themeVariants.vallum` 与 `themeVariants.abyssus` 分别记录两主题的业务 Page、画板和 Section；同一业务内的多个界面共用 Page。两主题 Page 使用相同的 01–04 编号与界面布局，每页固定自己的主题模式，浏览或导出时无需来回切换同一画板。导出与打印仍按界面清单顺序逐画板处理。

当前两套 Figma PNG 位于 `outputs/figma-theme-organization/vallum` 与 `abyssus`，结构证据为同目录的 `merged-structure.json`；最新打印稿为本目录的 `work-v2-vallum-review.pdf`、`work-v2-abyssus-review.pdf`。界面索引保存当前画板与 Section，页面目录保存顺序与画布样式，[组件映射](figma-components.json) 统一保存公共控件和工作流组件。仓库只维护当前材料，不保留旧 PDF 或已删除节点的清单。

```bash
node scripts/design/capture.mjs docs/figma-work-v2.json outputs/work-v2-validation/ui http://127.0.0.1:8021
node scripts/design/prepare-figma.mjs outputs/work-v2-validation/ui docs/figma-work-v2.json
```


当前体系为 MANAS × 苍渊·白垣，默认 Vallum，提供 Abyssus 手动切换。颜色数值以 `src/web/src/tokens.dtcg.json` 和 `tokens.css` 为源，组件使用 `design-system.css` 的语义适配；不要从截图取色。

当前界面只读取 `figma-work-v2.json`。Page 按业务合并，Section 使用统一留白、对齐和间隔；画板保留采集视口及原尺寸，避免重叠。设计规范独立，交互状态、页面控件和工作流组件归入同一个公共组件 Page。

Section 仅用于组织画板，`fills` 与 `strokes` 均为空，避免默认白底和描边形成界面外框。Page 画布背景使用对应主题的 `bgPrimary`：白垣 `#F8F7F2`、苍渊 `#080A0D`；共享页面使用白垣。Figma Page 背景不支持变量绑定，写入时从语义变量解析当前值，并在主题 Token 更新后重新同步。当前值记录于 `figma-page-order.json` 的 `canvasBackground`。

## 采集真实界面

启动 API 与前端后执行：

```bash
node scripts/design/capture.mjs docs/figma-work-v2.json data-bin/tmp/本次设计/browser http://127.0.0.1:5175
node scripts/design/prepare-figma.mjs data-bin/tmp/本次设计/browser docs/figma-work-v2.json
```

采集脚本使用 Chromium CDP，等待字体与 API 内容，分别记录两主题 PNG、字体和文档溢出；Vallum 另输出原生场景。`--scenes-only` 可更新场景而保留已有 PNG。关闭的 details 正文、不可见内容和裁切区域外内容不进入场景；密码字段脱敏。SVG 仅用于图标和图表，不用整页截图替代可编辑界面。

## 更新 Figma

通过 Figma 插件的 `use_figma` 写入现有设计文件。首次调用前读取 `figma-use`；组合界面同时遵循 `figma-generate-design`，组件遵循 `figma-generate-library`。每次调用最多切换一次 Page；跨 Page 操作按页面拆开并行执行。

1. 核对 `Ninna / UI` 的 Vallum / Abyssus 两模式。语义变量别名到锁定原始色，尺寸绑定 40 / 32px、圆角 6 / 8 / 12px。
2. `component-batches.json` 提供分批组件定义；用 `native-runtime.txt` 的 `build` 创建原生组件，将 key → component ID 登记在 `docs/design/figma-components.json` 的 components 中，工作流组件描述登记在 workflowComponents 中。已有 key 复用原组件。
3. `page-plans.json` 将大界面分为骨架与区域任务，避免单次代码超出连接器长度上限。注入 `config.components` 和本批 `data`，在目标业务 Page 构建暂存画板，依次填充 slots。完整成功后才替换原画板的子节点，保留 ID、所在 Section、位置与清单尺寸，并移除暂存节点；不要为同一业务下的详情或表单再创建 Page。
4. 使用 Inter、Noto Sans SC、IBM Plex Mono；中文 Figma 的 600 字重映射到可用的 Medium，避免请求不存在的字体样式。单行标签自适应宽度，长文本保留固定布局。
5. 按目录核对业务 Page 的画板数量、Section、间隔、尺寸、字体、变量绑定与 IMAGE 填充。根据 `themeVariants` 定位对应 Page 和 Section，固定 Page 与画板的主题模式，确保子节点没有相反主题覆盖。按实际消费者解析变量并刷新 paint 的 fallback，再导出 PNG，防止连接器导出采用旧模式 fallback。主题开关的选中标记同样随主题变量解析。
6. 分别从两套固定主题画板导出 `figma/vallum/01.png` 至 `11.png` 和 `figma/abyssus/01.png` 至 `11.png`，顺序来自当前界面清单。检查长表单、文字、主题开关与组件展示页，并按 `figma-page-order.json` 排列 10 个 Page；默认打开白垣项目与任务页。不要重新创建历史 Page。

快照反映采集时的真实平台数据。浏览器与 Figma 的文字光栅化、原生控件箭头及系统滚动条可能存在细微差异。

## 打印审阅稿

```bash
poetry run python scripts/design/print_review.py --manifest docs/figma-work-v2.json --images outputs/figma-theme-organization/vallum --theme vallum --output docs/design/work-v2-vallum-review.pdf
poetry run python scripts/design/print_review.py --manifest docs/figma-work-v2.json --images outputs/figma-theme-organization/abyssus --theme abyssus --output docs/design/work-v2-abyssus-review.pdf
```

脚本默认读取当前界面索引，并从所选主题的当前 PNG 目录生成 A3 横向 PDF，长界面沿空白区域续页，深色主题使用对应的断行判断。发布 UI tag 前更新页面清单、两套 PNG、两份打印稿和 `docs/ui-design.md`。打印稿覆盖当前文件，不另存旧版；annotated tag 按仓库发布约定创建。
