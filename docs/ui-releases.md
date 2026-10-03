# UI 版本记录

每个完成验证的 UI 版本使用 annotated Git tag。功能分支保留分批提交，合入 `dev` 时 squash；已发布 tag 不移动。

| Tag | 内容 | 验证 |
| --- | --- | --- |
| `ui-v0.8.0` | MANAS × 苍渊·白垣双主题、表单与参数层级、统一控件、31 页 Figma 与双主题打印稿 | 45 项单元测试；6 项主题检查；既有 UI 回归与真实 Docker 训练通过 |
| `ui-v0.1.0` | 近白金画布、可收缩导航、移动抽屉和键盘操作 | 生产环境 7 项浏览器检查 |
| `ui-v0.2.0` | 减少分割线、资产语义色、轻量筛选、运行分页、跨页比较选择、空查询恢复 | 构建及类型检查；生产环境 8 项浏览器检查 |
| `ui-v0.2.1` | Figma 一界面一 Page、清理远处残留、22 页设计稿和 A3 打印审阅稿；UI squash 至 dev | 逐页结构及视觉核对；沿用未变更代码的 v0.2.0 验证 |
| `ui-v0.3.0` | 紧凑工程侧栏、统一图标、无竖条选中态、精简工作空间与结构化底部状态；同步 Figma 组件和各页 | 类型检查与构建；8 项浏览器检查；Figma 逐页单画板核对 |
| `ui-v0.7.0` | 镜像按站点、命名空间、镜像与版本逐层浏览；独立拉取任务；大小自动单位 | 45 项单元测试、5 项定向浏览器/格式检查、生产 MCP 查询通过 |
| `ui-v0.6.0` | 镜像资产独立注册、异步拉取、Runtime 固定引用、MCP 工具与四个新界面 | 34 项单元测试、20 项浏览器测试、真实 Docker 训练与镜像生命周期通过 |
| `ui-v0.5.0` | Project 组织训练、指标归入单次运行、移除生产验收入口；同步 Figma | 单元、真实 Docker/MCP、生产浏览器检查通过 |
| `ui-v0.4.0` | 任务区域独立滚动、紧凑标题与摘要、本地字体、中心存储连接状态修正；同步 22 个 Figma 界面 | 13 项 UI 检查与现有真实训练用例通过；生产环境关键检查通过 |

## ui-v0.8.0

沿用 `feature/image-catalog`，完整迁移 31 个既有界面，保留领域、API、资产注册和训练执行契约。MANAS 负责连续工作表面、页面范式和任务层级；苍渊·白垣负责锁定色值、字体、尺寸及动效。

- 默认白垣，主画布 `#F8F7F2`；苍渊主画布 `#080A0D`。桌面和移动顶栏可切换，`ninna.theme` 保存手动偏好。首屏脚本提前应用有效偏好，存储不可用或值无效时回退白垣。
- 直接复用技能的 `tokens.css` 和 `tokens.dtcg.json`，项目适配集中在 `design-system.css`。白垣主按钮采用墨骨 / 石素，苍渊采用初光 / 深渊；主体文字、状态图标和图表使用语义角色。
- 正文 14px，常规控件 40px、紧凑控件 32px，间距以 8px 为基准，圆角 6 / 8 / 12px。创建训练采用分组表单与独立提交摘要，参数表保持列对齐，长内容与短字段分别处理。
- 图表集中注入主题颜色，结合虚线和图例区分曲线。白垣的次曲线使用既有 `textSecondary` 与虚线，避免铜霜细线在浅背景上失去辨识度。
- 切换主题不重建页面；草稿、筛选、比较选择、区域滚动和标签继续保留。修正标签切换时旧区域清理回调覆盖滚动记录的问题；滚动事件负责保存有效位置。
- 提供键盘焦点、选中标记、禁用与错误状态，支持 reduced-motion。移动端保持抽屉与表格局部滚动。

验证：`poetry run pytest tests/unit -q` 45 passed；类型检查与生产构建通过。6 项主题测试通过，包含精确配色、偏好持久化、跨断点控制同步、键盘切换、草稿与选择保留、存储失败和无效值回退，以及两主题在 320 / 768 / 1440px 的关键路由 axe 检查。既有导航、分页、项目、滚动密度、Hub 状态、镜像目录与移动端回归通过。显式 `NINNA_INTEGRATION=1` 的浏览器检查完成真实 Docker 训练与 checkpoint 下载；未用 mock 训练作为端到端证据。

Figma 保留原有 31 个屏幕 Page 和主画板 ID，各 Page 仅一个原点画板。规范、交互组件、页面控件独立；共享控件为原生组件实例，界面保留可编辑文字与向量，没有整页截图填充。`Ninna / UI` 提供 Vallum、Abyssus 两模式并绑定锁定原始色值，交互页覆盖按钮、Input、Select 的默认、悬停、焦点、错误、禁用和只读状态。

浏览器 PNG、字体与布局记录在 `data-bin/tmp/ui-v0.8.0-20261001/browser/`，62 个视口均无文档横向溢出。Figma 双主题 PNG 与逐页结构核对在同目录 `figma/`。设计稿采用采集时真实平台快照；后续训练或注册产生的新记录不会回写旧快照。浏览器与 Figma 的文字光栅化、原生表单箭头和系统滚动条可能略有差异。

[白垣 A3 审阅稿 · 35 页](design/ui-v0.8.0-vallum-review.pdf) · [苍渊 A3 审阅稿 · 35 页](design/ui-v0.8.0-abyssus-review.pdf)。页面索引见 `figma-pages.json`，采集及同步方法见 [设计同步说明](design/sync.md)。

## ui-v0.7.0

分支 `feature/image-catalog`，基于 `feature/image-assets`。目录完全派生自已登记镜像元数据，不扫描远端仓库，不改写资产、Runtime 或历史 Run。

- 镜像资产按站点 → 命名空间 → 镜像 → 版本逐层显示，URL 保存路径和搜索；面包屑、刷新、前进后退及表单返回保留目录。
- 使用登记时的 source_reference 作为归属；仅 image ID 的登记归入本地镜像。多仓库别名放入未分类，避免错误猜测。
- 同一引用、相同内容的重复登记折叠并可展开查看资产；相同内容的不同 tag 仍分别展示。
- 拉取任务独立页面；本地注册可以明确选择标签；远端表单预览归属。
- 大小统一自动显示 B、KB、MB、GB、TB（十进制），覆盖版本、详情、注册选项及拉取进度，处理未知值与舍入边界。
- 新增只读 `/api/images/catalog` 和 MCP `browse_images`，同步 Agent 指南与 Skill。

验证：45 项 Python 单元测试通过；类型检查和生产构建通过；3 项目录/格式测试、2 项既有镜像页面测试通过，包含真实本地镜像注册及 Runtime 容器校验。生产 MCP 返回 migo-dl 的 pytorch 6 个版本、pytorch-train 1 个版本、preludio2 4 个版本。此次未修改训练执行链路，未重复运行 MNIST 训练验收。

Figma 共 31 个界面，各自独立 Page 和原点主画板；站点、命名空间、镜像、版本、搜索与拉取任务分开。PNG 与浏览器证据位于 `data-bin/tmp/20260925-154836/`；页面索引见 `figma-pages.json`。[35 页 A3 打印稿](design/ui-v0.7.0-review.pdf)。设计中的数据记录各界面的采集时刻，注册测试随后新增的资产不回写旧截图。

## ui-v0.6.0

分支 `feature/image-assets`，从 `dev` 创建，分批提交后端与 Agent 契约、前端与设计交付。

- 新增 Image Asset，注册读取 Docker inspect，保存 image ID、RepoDigests、来源与标签、平台和大小。实时可用性独立于不可变资产。
- Runtime 通过 image_ref 引用镜像，创建时真实容器验证训练依赖；训练按完整 image ID 执行，Run 保存镜像快照。历史资产与 Run 不改写。
- 本地注册与远端拉取分开，拉取任务持久保存 digest、进度与脱敏错误；重启恢复不猜测可变标签。私有仓库凭据由部署侧 Docker 配置提供。
- 镜像列表、详情、注册、拉取四个界面各有独立 Figma Page；展开与收起导航、Runtime 页面和创建训练页同步。

验证证据：

- `poetry run pytest tests/unit -q`：34 passed。
- `pnpm --dir src/web test`：20 passed，包含浏览器注册镜像、创建 Runtime、真实训练与下载 checkpoint，以及桌面/移动端 axe 检查。
- 真实 Docker MNIST 验收：4 passed；Adam `run-544855648415` 98.94%，SGD `run-218c5a9b6d66` 98.70%。验证 Dataset/Workspace 挂载、checkpoint 重载、hash 变化、loss 下降和 Recipe 解耦。
- 真实失败链路：4 passed；缺少依赖、非法 Recipe、平台取消和外部停止均进入正确终态并保留日志。
- 真实镜像身份测试：标签漂移仍保留原 image ID；删除后可用性为 MISSING，历史资产不变；scratch 镜像纳管成功而 Runtime 校验失败。
- 远端拉取：`registry.cn-hangzhou.aliyuncs.com/google_containers/pause:3.9` 成功按 digest 拉取；不存在版本明确 FAILED。Docker Hub 在此部署网络超时，失败任务保留。可用 `NINNA_TEST_PULL_IMAGE` 指定测试仓库。401 脱敏与重启恢复通过单元测试；尚未使用真实私有仓库凭据验收成功拉取。

浏览器 PNG、字体和布局记录：`data-bin/tmp/20260925-152400/browser/`，26 个界面无文档横向溢出；Figma PNG 位于同目录 `figma/`。页面索引见 `figma-pages.json`，规范页仅一个原点画板，无捕获残留。[30 页 A3 打印稿](design/ui-v0.6.0-review.pdf)。设计稿记录捕获时的数据，后续测试产生的新资产与运行不会伪装成同一时刻的数据。

## ui-v0.5.0

从 squash 后的 `dev` 创建 `feature/project-workspaces`，分批提交领域/API/MCP、前端和设计文档。

Project 持久化于 SQLite；创建 Run 必须传项目 ID，重训限制同一项目。旧执行记录不改写，通过独立成员索引归入 `legacy`。项目首页只有名称、说明、运行数与最近时间，准确率和 loss 集中在 Run 详情；运行比较与 Aim 观察限定当前项目。数据、模型、配方和执行资产继续平台级复用。

生产系统验收页面、API、CLI、MCP 工具和服务模块已删除。MNIST Golden Path 移到 `tests/support/training.py`，通过生产 API 提交真实训练、在独立 Docker 容器重载模型，由 opt-in pytest 执行。

验证：26 项单元测试通过，随后项目/注册/MCP 21 项针对性检查通过；真实 HTTP MCP 创建、stdio 观察和失败重训 2 项通过（64.07 秒）；迁出的完整 Golden Path 7 项通过（165.82 秒）。浏览器项目/滚动/字体/无障碍 4 项通过；原有回归 11 项通过，真实创建用例揭示项目列表加载晚于资产的时序问题，修复后该用例通过（28.6 秒），真实下载 checkpoint。最终镜像部署后 4 项关键检查通过（11.5 秒）。类型检查、Ruff、前端及 Docker 构建通过；既有 bundle 大小提示未作无关拆包处理。

Figma 同步 22 个界面，项目替换验收页，每个界面一 Page、单个原点主画板，规范页无捕获残留。实际 PNG、DOM 字体和布局测量在 `data-bin/tmp/20260925-084958/`，Figma PNG 在 `figma/` 子目录；[25 页 A3 打印稿](design/ui-v0.5.0-review.pdf)。设计记录捕获时的真实运行数据，后续测试会增加项目和运行数。

## ui-v0.4.0

功能分支 `feature/workspace-density` 分批提交连接状态、工作区布局和跨页修订，合入 `dev` 时 squash。画布保留 `#FFFEFB`，导航保留 218px / 72px。

桌面固定标题、筛选或详情标签，记录与详情主体内部滚动；运行列表保存筛选、分页与位置，详情按 Run ID 和标签隔离。轮询不重置位置，日志跟随仅作用于日志区域。小于 1000px 宽或 650px 高时恢复文档滚动，避免固定控制区挤占内容。1440×900 首屏完整显示至少 7 条记录，分页保持可达。

统一标题 24px、辅助文字 12px、指标 24px，收紧资产摘要、创建表单与验收页；模型名称、状态和普通指标使用正文体系，标识、版本和日志使用等宽字体。Inter、Noto Sans SC、IBM Plex Mono 由 Fontsource 包锁定并本地提供，许可证随静态资源发布。训练定义解释移至创建页帮助入口；去掉列表尾部说明和全局品牌页脚。

中心存储将首次加载、检查中、已连接、未启用和实际失败分开。后台检查保留上次结果并显示检查中，请求失败后及时撤销已连接状态；仓库读取失败提供局部重试，不显示空仓库文案。浏览器故障注入只用于 UI 传输状态，不用于证明 Docker 训练。

验证：类型检查与 Docker 构建通过；13 项 UI 检查通过（45.8 秒），覆盖内部滚动、跨 Run/标签恢复、字体加载、320/720/768/1280/1440/1920px、短视口、axe 和连接状态。跨页摘要调整后 6 项检查通过，包括现有真实训练与 checkpoint 下载（约 1 分钟）；生产环境 5 项滚动、字体和连接状态检查通过（5.8 秒）。随后补充未启用 Hub 的设置保存失败回归，4 项连接状态检查通过（4.7 秒）。既有大 bundle 警告仍存在。

Figma：一界面一 Page，规范和组件分开，每页单个原点画板。使用 Inter / Noto Sans SC / IBM Plex Mono 与显式字重，复用导航、状态和按钮实例。设计稿记录捕获时的真实数据快照；之后的验收训练会增加平台记录数量。

实际界面 PNG 和布局测量：`data-bin/tmp/20260925-083500/`；Figma 导出：同目录 `figma/`；[A3 打印稿](design/ui-v0.4.0-review.pdf)。移动端设计稿保留自然文档长度，桌面主要展示工作视口。平台与 Figma 的系统滚动条和文字光栅化可能存在细微差异。

可重新采集界面（需要 Chromium，路由及详情状态见清单）：

```bash
node scripts/design/capture.mjs docs/figma-pages.json data-bin/tmp/$(date -u +%Y%m%d-%H%M%S) http://127.0.0.1:8000
poetry run python scripts/design/print_review.py --images data-bin/tmp/日期-时间/figma --output docs/design/ui-v0.4.0-review.pdf
```

采集脚本通过 Chromium CDP 截图。可选 `captureId` 只用于带捕获脚本的 Vite 开发服务；它等待实际 POST 提交成功，避免将 CORS 预检误判为 Figma 导入完成。生产应用不加载 Figma 捕获脚本。打印脚本读取另行导出的 Figma PNG。

## ui-v0.3.0

分支 `feature/precise-sidebar`。保留 218px 展开宽度与 72px 收起宽度；Logo 28px，桌面菜单 14px / 500、38px 行高、18px / 1.5 图标，分组间距 22px，左侧内容基准 24px。移动抽屉和收起导航保留 44px 触达区域。选中背景为 `#F3F3F1`，没有棕色竖线；导航辅助文字为 `#64696D`，画布继续使用 `#FFFEFB`。

去掉工作空间的 N 方块、英文副标题和无功能箭头。底部改为 Docker / 连接状态、执行 / CPU 两行，项目链接使用真实用途标签。保留导航结构、路由、键盘操作、收起偏好和移动抽屉焦点恢复。

8 项浏览器检查通过（38.6 秒），覆盖 320/768/1280/1440px、axe、路由、分页与比较、侧栏键盘操作及跨断点恢复。部署后额外运行生产环境 2 项侧栏检查，通过（3.6 秒）。构建通过，仍有既有的大 bundle 提示。

Figma 同步了两个侧栏组件、九个图标、四个导航状态和九个页面导航控件；各桌面界面使用侧栏实例并设置相应选中项。移动端关闭导航页面保持原布局。每页仍只有一个原点主画板。内容区保留已有真实数据快照，本次同步范围是侧栏。

截图：`data-bin/tmp/20260925-080005/`（23 张实际界面 PNG；`figma/` 内为 22 张同步后的 Figma PNG）。新版 [A3 审阅稿](design/ui-v0.3.0-review.pdf) 从 Figma 导出生成；旧版 PDF 保留作为历史存档。

## ui-v0.2.0

画布仍为 `#FFFEFB`。删除顶栏、指标、普通表单分组、列表行和资产摘要的重复边界；保留输入边界、键盘焦点、图表网格与独立编辑区域的必要边界。数据集、模型、配方、运行环境和代码空间分别使用克制的青、蓝、金、紫、灰绿色标识，文字标签始终存在。

运行列表每页 10 条，支持跨页选择两个 Run 比较，也可以随时清空选择。进行中筛选包含 CREATED、PREPARING 和 RUNNING；新增已取消筛选。无匹配结果时可以清空筛选并回到第一页。列表仍使用真实 API 数据。

Figma 捕获脚本仅在 Vite 开发模式、带 `figmacapture` 参数时加载；生产构建不加载第三方设计脚本。

## 设计参考

参考 [OpenAI 设计指南](https://openai.com/brand/) 的排版层级与留白，以及 [Canvas](https://openai.com/index/introducing-canvas/) 将操作放在工作内容附近的方式。当前版本使用 MANAS 的低噪声工作空间结构与苍渊·白垣的锁定双主题。历史版本的近白金配色仅作为历史记录保留。

## Figma 整理规则

[设计文件](https://www.figma.com/design/ab3EG1a9aEHNyNZRJCzmD4)。一个界面对应一个真实 Figma Page；一个 Page 只保留一个主画板，位于原点。组件页与界面页分开。版本记录放在本文，不在同一 Page 上横向堆叠历史界面。

当前 31 个界面已完成双主题同步及公共控件提取；自 ui-v0.4.0 起，中文使用 Noto Sans SC，Latin 使用 Inter，等宽内容使用 IBM Plex Mono。设计稿是可编辑文字、向量和自动布局，重复导航与状态使用公共组件实例。Figma 与浏览器的字体渲染可能存在细微差异。

[打印审阅稿](design/ui-v0.2.1-review.pdf) 使用 A3 横向，长界面分为续页，避免整页缩放后文字过小。导出脚本为 `scripts/design/print_review.py`，输入是按索引排序的 Figma PNG；使用 Poetry 环境中的 Pillow 和 Noto CJK 字体生成。

浏览器证据：`outputs/ui-evidence/`。Figma Page/画板索引见 `figma-pages.json`。
