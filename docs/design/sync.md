# UI 与 Figma 同步

当前工作任务 v2 使用 [独立页面索引](../figma-work-v2.json)，包含 9 个新页面。原 `figma-pages.json` 保留旧版页面清单作为历史记录。两主题 Figma PNG 位于 `outputs/work-v2-validation/figma-png` 与 `figma-abyssus`，打印稿为本目录的 `work-v2-vallum-review.pdf`、`work-v2-abyssus-review.pdf`。

```bash
node scripts/design/capture.mjs docs/figma-work-v2.json outputs/work-v2-validation/ui http://127.0.0.1:8021
node scripts/design/prepare-figma.mjs outputs/work-v2-validation/ui docs/figma-work-v2.json
```


当前体系为 MANAS × 苍渊·白垣，默认 Vallum，提供 Abyssus 手动切换。颜色数值以 `src/web/src/tokens.dtcg.json` 和 `tokens.css` 为源，组件使用 `design-system.css` 的语义适配；不要从截图取色。

`docs/figma-pages.json` 保存界面路由、详情标签、视口、Page 和主画板 ID。每个界面独立 Page，Page 内只保留一个位于原点的主画板。规范、交互组件和页面控件分别维护，更新时保留既有主画板 ID。

## 采集真实界面

启动 API 与前端后执行：

```bash
node scripts/design/capture.mjs docs/figma-pages.json data-bin/tmp/本次设计/browser http://127.0.0.1:5175
node scripts/design/prepare-figma.mjs data-bin/tmp/本次设计/browser
```

采集脚本使用 Chromium CDP，等待字体与 API 内容，分别记录两主题 PNG、字体和文档溢出；Vallum 另输出原生场景。`--scenes-only` 可更新场景而保留已有 PNG。关闭的 details 正文、不可见内容和裁切区域外内容不进入场景；密码字段脱敏。SVG 仅用于图标和图表，不用整页截图替代可编辑界面。

## 更新 Figma

通过 Figma 插件的 `use_figma` 顺序写入现有设计文件。首次调用前读取 `figma-use`；组合界面同时遵循 `figma-generate-design`，组件遵循 `figma-generate-library`。

1. 核对 `Ninna / UI` 的 Vallum / Abyssus 两模式。语义变量别名到锁定原始色，尺寸绑定 40 / 32px、圆角 6 / 8 / 12px。
2. `component-batches.json` 提供分批组件定义；用 `native-runtime.txt` 的 `build` 创建原生组件，将 key → component ID 登记在 `figma-components.json`。已有 key 复用原组件。
3. `page-plans.json` 将大页面分为骨架与区域任务，避免单次代码超出连接器长度上限。注入 `config.components` 和本批 `data`，在目标 Page 构建暂存画板，依次填充 slots。完整成功后才替换原主画板的子节点，保留 ID、原点与清单尺寸，并移除暂存节点。
4. 使用 Inter、Noto Sans SC、IBM Plex Mono；中文 Figma 的 600 字重映射到可用的 Medium，避免请求不存在的字体样式。单行标签自适应宽度，长文本保留固定布局。
5. 逐页核对单画板、原点、尺寸、字体、变量绑定与 IMAGE 填充。切换主画板模式后按消费者解析变量，刷新 paint 的 fallback，再导出 PNG，防止连接器导出采用旧模式 fallback。
6. 分别导出 `figma/vallum/01.png` 至 `31.png` 和 `figma/abyssus/01.png` 至 `31.png`，顺序来自清单。检查桌面、移动端、长表单、图表、错误状态与组件展示页，最后恢复默认 Vallum。

快照反映采集时的真实平台数据。浏览器与 Figma 的文字光栅化、原生控件箭头及系统滚动条可能存在细微差异。

## 打印审阅稿

```bash
poetry run python scripts/design/print_review.py --images data-bin/tmp/本次设计/figma/vallum --theme vallum
poetry run python scripts/design/print_review.py --images data-bin/tmp/本次设计/figma/abyssus --theme abyssus
```

脚本从 Figma 导出的 PNG 生成 A3 横向 PDF，长界面沿空白区域续页，深色主题使用对应的断行判断。发布 UI tag 前更新页面清单、两套 PNG、两份打印稿与 `docs/ui-releases.md`，保留旧版文档和 annotated tag。
