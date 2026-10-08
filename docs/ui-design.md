# Ninna 当前界面设计与状态约定

界面采用 MANAS 与苍渊·白垣。默认白垣背景 `#F8F7F2`，可切换苍渊 `#080A0D`；准确色值与语义角色来自 `src/web/src/tokens.dtcg.json`、`tokens.css`，组件适配集中在 `design-system.css`。字体使用 Inter、Noto Sans SC、IBM Plex Mono。正文 14px，常规控件 40px、紧凑控件 32px，间距以 8px 为基准，圆角使用 6 / 8 / 12px。

## 页面与任务

主导航包括项目、模型与数据、训练环境、托管平台和 Codex 接入；外观设置控制主题偏好。项目组织 WorkItem 和 Run，指标属于具体 Run。工作详情显示真实目标、准备状态、方案、运行、日志及成果；训练操作通过平台执行。列表、表单和详情复用公共控件，长路径与 hash 使用等宽字体并允许完整查看。

首次加载、空数据、请求失败、后台刷新失败和提交中分别呈现。后台刷新失败保留已有内容，不推断训练已停止；提交失败保留输入。运行状态来自 API，终态 Run 提供指标、日志、产物和新尝试入口，不改写执行记录。准备状态与训练状态分别展示，不绘制占位指标。

桌面内容区域独立滚动，窄屏采用移动导航与局部表格滚动。主题切换保留草稿、筛选、选择和滚动位置。控件提供键盘焦点、明确标签、禁用与错误状态；颜色之外使用文字和图标表达状态，支持 reduced-motion。

## 当前 Figma 文件

[Figma 设计文件](https://www.figma.com/design/ab3EG1a9aEHNyNZRJCzmD4) 维护 10 个 Page：白垣与苍渊各 4 个业务 Page（项目与任务、模型与数据、训练环境、设置），另有设计规范和公共组件各 1 页。每套主题包含 11 个界面画板，相关画板以命名 Section 排列。

- [界面索引](figma-work-v2.json)：路由、视口尺寸和双主题画板、Section ID。
- [页面目录](design/figma-page-order.json)：Page 顺序、业务分组、位置及画布背景。
- [组件映射](design/figma-components.json)：统一的公共控件与工作流组件 key、ID 和状态描述。
- [同步流程](design/sync.md)：浏览器采集、原生可编辑图层同步和打印稿生成。

Section 只作组织，填充与描边为空；Page 画布匹配所属主题的 bgPrimary。文字、向量、布局和组件实例可编辑，不用整页截图替代界面。业务界面分主题组织，两主题共享组件及语义变量。

最新审阅稿为 [白垣](design/work-v2-vallum-review.pdf) 与 [苍渊](design/work-v2-abyssus-review.pdf)。对应的当前逐画板 PNG 位于 `outputs/figma-theme-organization/vallum` 和 `abyssus`。索引、组件和打印稿随界面更新，不保留旧版副本或已删除节点目录。

## 验证

界面变更验证真实页面导航、表单、主题偏好、键盘操作、移动抽屉、滚动恢复和横向溢出，并运行相关 Playwright 与 axe 检查。设计同步核对画板数量、Page/Section 归属、主题变量和字体，按当前索引导出两主题 PNG 及打印稿。采集时的业务数据是快照，后续训练不自动回写设计文件。
