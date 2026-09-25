# UI 版本记录

每个完成验证的 UI 版本使用 annotated Git tag。功能分支保留分批提交，合入 `dev` 时 squash；已发布 tag 不移动。

| Tag | 内容 | 验证 |
| --- | --- | --- |
| `ui-v0.1.0` | 近白金画布、可收缩导航、移动抽屉和键盘操作 | 生产环境 7 项浏览器检查 |
| `ui-v0.2.0` | 减少分割线、资产语义色、轻量筛选、运行分页、跨页比较选择、空查询恢复 | 构建及类型检查；生产环境 8 项浏览器检查 |
| `ui-v0.2.1` | Figma 一界面一 Page、清理远处残留、22 页设计稿和 A3 打印审阅稿；UI squash 至 dev | 逐页结构及视觉核对；沿用未变更代码的 v0.2.0 验证 |

## ui-v0.2.0

画布仍为 `#FFFEFB`。删除顶栏、指标、普通表单分组、列表行和资产摘要的重复边界；保留输入边界、键盘焦点、图表网格与独立编辑区域的必要边界。数据集、模型、配方、运行环境和代码空间分别使用克制的青、蓝、金、紫、灰绿色标识，文字标签始终存在。

运行列表每页 10 条，支持跨页选择两个 Run 比较，也可以随时清空选择。进行中筛选包含 CREATED、PREPARING 和 RUNNING；新增已取消筛选。无匹配结果时可以清空筛选并回到第一页。列表仍使用真实 API 数据。

Figma 捕获脚本仅在 Vite 开发模式、带 `figmacapture` 参数时加载；生产构建不加载第三方设计脚本。

## 设计参考

参考 [OpenAI 设计指南](https://openai.com/brand/) 的排版层级与留白，以及 [Canvas](https://openai.com/index/introducing-canvas/) 将操作放在工作内容附近的方式。保留 Ninna 的近白金画布和领域语义色。

## Figma 整理规则

[设计文件](https://www.figma.com/design/ab3EG1a9aEHNyNZRJCzmD4)。一个界面对应一个真实 Figma Page；一个 Page 只保留一个主画板，位于原点。组件页与界面页分开。版本记录放在本文，不在同一 Page 上横向堆叠历史界面。

22 个界面已完成同步及公共控件提取；中文字体映射为 Noto Sans SC，Latin 使用 Arimo，等宽内容使用 Cousine。设计稿是可编辑文字、向量和自动布局，重复导航与状态使用公共组件实例。Figma 与浏览器的字体渲染可能存在细微差异。

[打印审阅稿](design/ui-v0.2.1-review.pdf) 使用 A3 横向，长界面分为续页，避免整页缩放后文字过小。导出脚本为 `scripts/design/print_review.py`，输入是按索引排序的 Figma PNG；使用 Poetry 环境中的 Pillow 和 Noto CJK 字体生成。

浏览器证据：`outputs/ui-evidence/`。Figma Page/画板索引见 `figma-pages.json`。
