# 工程协作指南

本文件适用于整个仓库，面向维护代码、主题和文档的 Agent。实际排版文章时，另读 `SKILL.md`；不要把工程维护请求误当成文章排版请求。

## 项目定位与运行方式

- 这是微信公众号文章排版 Skill，不是 Web 应用、写作工具或公众号发布客户端。
- 核心链路：输入归一化为 Markdown → 选定色系与版式 → 组装离线 HTML 模板 → 校验正文 → 包装可复制预览。
- 渲染、构建、DOCX 提取及单元测试均使用 Python 3 标准库。现有代码使用 `str.removeprefix` / `removesuffix`，需 Python 3.9 或以上。
- 没有 Node 构建、包管理配置或第三方 Markdown 解析器；不要为了普通维护引入前端框架或运行时网络依赖。
- 以下命令均从仓库根目录执行。脚本之间使用同目录模块导入；优先直接执行脚本或使用下面的 unittest discovery 命令。

## 先读哪些文件

| 任务 | 入口 |
|---|---|
| 产品边界、参数、交付 | `README.md`、`README.en.md`、`docs/product-guide.md` |
| Agent 排版工作流 | `SKILL.md`、`references/theme-index.md`、所选主题库、`references/common-components.md` |
| 输入归一化 | `references/format-normalize.md`、`scripts/extract_docx.py` |
| 修改主题或公众号适配 | `scripts/build_stitch_themes.py`、`references/stitch-design-system.md` |
| 自定义主题 | `references/theme-generator.md` |
| 回归与贡献要求 | `scripts/test_*.py`、`references/eval-cases.md`、`CONTRIBUTING.md` |

## 代码地图

- `scripts/stitch_themes.py`：共享主题目录、模板读取、CSS 声明解析、属性转义、叶节点合并和章节装配。`catalog()` / `templates()` 有进程内缓存，重建后使用新进程验证。
- `scripts/render_stitch_article.py`：确定性 Markdown 扫描与 `Renderer`；负责行内标记、嵌套列表、代码、表格、图片、脚注、引用、扩展块和唯一页尾。渲染完成后调用 `validate()`，任何 ERROR 或 WARNING 都会拒绝输出。
- `scripts/build_stitch_themes.py`：解析来源 HTML、核验来源摘要、提取色板、编译公众号模板、优化静态 CSS/结构，并生成主题目录、模板、组件库与索引。内置主题样式修改的主要入口。
- `scripts/build_stitch_gallery.py`：用同一篇示例文章重建 15 色系 × 3 版式画廊和入口，并调用对照页构建。
- `scripts/build_stitch_comparison.py`：生成原稿与内联还原的同文、同色对照，支持 390 / 677px；不是正式文章输出入口。
- `scripts/validate_gzh_html.py`：正文兼容检查；`validate()` 返回 `(errors, warnings, leaf_count)`。CLI 只因 ERROR 返回非零，不能仅凭退出码宣称零警告。
- `scripts/component_lint.py`：扫描 `references/*.md` 中的 HTML 围栏，检查平台禁用项、代码大空白及正文虚线框；不等同于完整正文校验。
- `scripts/wrap_preview.py` + `assets/preview-template.html`：将干净正文嵌入预览页。复制逻辑同时写入 `text/html` 和 `text/plain`，工具栏与 JS 不属于被复制正文。
- `scripts/extract_docx.py`：用 ZIP/XML 提取标题、粗体、下划线、列表、表格与图片；图片写入输出 Markdown 旁的 `images/`。不上传图片。
- `scripts/capture_stitch_styles.py`：可选的来源样式抓取工具；依赖 `websocket-client`、macOS Chrome、固定本地端口及代理配置，可能访问原稿的外部资源。不是正常离线构建或测试的前置步骤，不要默认运行。
- `scripts/test_stitch_themes.py`：来源摘要、模板可重建性、45 组合内容保真、版式、名片和 CSS 优化回归。
- `scripts/test_validate_gzh_html.py`：渐变检测、定位信息及 CLI 退出码回归。

## 源文件、生成文件与来源证据

内置主题的依赖方向：

```text
assets/stitch/ 原稿 HTML + resolved-*.json/css + manifests + icons
  → scripts/build_stitch_themes.py
  → assets/stitch/themes.json
  → assets/stitch/templates/*.json
  → references/theme-{色系ID}.md + references/theme-index.md
  → scripts/build_stitch_gallery.py
  → docs/gallery/*.html
```

- 内置主题应修改编译器或经授权更新来源，再重建；不要只手改生成的 JSON、组件 HTML 或画廊来修复问题。
- 模板 JSON 中完全相同的 HTML 通过 `{"$ref":"组件名"}` 单层引用去重；引用仅指向同文件中的字符串，不允许链式引用。运行时 `templates()` 展开为原有字符串映射，组件名与最终 HTML 不变；读取模板应使用该入口，不直接假定 JSON 值全是字符串。
- `references/theme-index.md` 是 Agent 选主题的注册入口；离线渲染器实际从 `assets/stitch/themes.json` 和 `templates/*.json` 读取，两者必须一致。
- `manifest.json` 记录五份来源 HTML 的 SHA-256；`resolved-manifest.json` 记录来源及冻结计算样式的摘要。样式映射依赖原节点的 tag/class/style/文本索引，修改原文也可能影响匹配。
- 修改来源必须同步对应索引、摘要及来源说明；不要通过随意改摘要掩盖无法解释的来源差异，也不要把本地文字定制说成重新抓取远程设计。
- `assets/stitch/icons/` 是随附 Material Symbols SVG，保留 `NOTICE.md` 和许可。正式渲染不依赖在线图标字体。
- `docs/images/` 是预览截图；画廊构建脚本不生成这些 PNG。视觉变更若更新截图，需要另行实际渲染，不要声称脚本会自动同步。
- 根目录语法示例、其排版 HTML，以及 `assets/markdown-demo/` 是示例/演示资源，不是模板编译入口。不要因日常验证覆盖用户文章或重新生成无关文件。
- 临时正文、预览和自定义主题草稿写入临时目录。当前仓库没有 `.gitignore`，不要依赖贡献文档中“产物已忽略”的旧说明。

## 不应破坏的行为约定

### 主题与内容

- 主题与版式都省略时固定 `emerald + ruler`；只给主题时使用该色系登记的默认版式；只给版式时搭配 `emerald`。
- 版式为 `ruler`（墨规）、`overprint`（浮光）、`pure`（素墨），切换版式不得混用色系。纯净版不强塞可见章节编号。
- 未知或已删除主题应明确报错，不静默回退。当前构建器明确要求 15 个来源色系；新增内置色系不能只追加一个 Markdown 文件。
- 自定义主题的 Agent 注册流程与离线渲染器并不自动打通：只登记 Markdown 不会让 CLI 识别新主题；重建内置库也会重写索引。扩展时明确处理注册、模板及重建保留策略。
- Markdown 扫描器是有限实现，不是完整 CommonMark 引擎。新增语法须提供内容保真测试，不能仅因仓库有语法演示文档就宣称全部支持。
- 保留用户段落、代码、列表层级、表格单元格、链接、图片及脚注；不得混入设计稿示例内容。语义关键词由 Agent 在 Markdown 阶段用 `++关键词++` 标记，CLI 不负责语义提取。

### 正文与预览边界

- 正文必须是全局 `<section>` 容器包裹的片段，不带文档外壳。样式内联，文字用 `<span leaf="">` 包裹。
- 正文禁止 `<div>`、`<style>`、`<script>`、外部 CSS/字体、`class` / `id`、Grid、CSS 变量、媒体查询、动画、float 和 fixed/absolute/sticky 定位。
- 来源原稿、对照页和预览外壳可以包含网页样式、脚本、类名；不要对整个仓库 HTML 一刀切清理，也不要把预览页直接交给正文校验器。
- 普通字体只在全局容器定义；代码和刻意等宽的编号保留局部字体。`*_in_article`、`*_in_toc`、`*_in_list` 等变体依赖明确的父容器契约，不能任意互换或去重。
- 普通正文直接使用段落，不默认套背景/边框/阴影卡片；步骤标题无外层卡片，但保留编号徽章。
- 代码每行一个普通 `<p>`，用 NBSP 保留缩进和空行；不生成行号列或行内 flex，不用 `white-space:pre`。代码中的半角符号不得被中文标点转换破坏。
- 图片保持 `max-width:100%;height:auto;display:block;margin:0 auto`，不默认 `width:100%` 拉伸小图；alt 为空时不编造图注，不虚构 URL。
- 正文默认不新增 CSS 背景渐变；渐变 WARNING 须逐项处理或说明风险。内置来源编译器使用的装饰 SVG 不应套用自定义主题生成提示词的禁 SVG 规则而直接删掉。

### 安全与页尾

- 模板普通字段必须转义；仅显式 `*_html` 字段接受已转换的可信 HTML。保持单轮占位符替换，用户文字不能二次注入模板。
- 保持原始 HTML 转义、危险资源协议拒绝、未知来源 utility 报错和未闭合代码/扩展块报错，不为“兼容”而静默丢内容。
- 没有真实作者不生成名片；没有简介不生成空简介节点；没有真实二维码使用无二维码变体。默认不传作者、不显示名片，不配置 Jacob 或默认简介；只有显式 `--author` 才生成名片，原文署名默认作为正文保留。
- 署名与互动各仅末尾一处，尽量合并原文签名。显式互动文案保留，不全局替换正文中的“转发”。
- 互动区保留来源设计的圆角卡片、图标与点赞/收藏/分享动作行；使用静态富文本，不添加原生操作承诺或点击脚本，不强制三连。
- 部分组件库、通用约定、产品指南和旧回归清单仍写有作者占位符或 DOCX 表格占位的旧描述：实际默认行为以当前 `SKILL.md`、实现和自动测试交叉核实；DOCX 提取器已输出 Markdown 表格。遇到冲突先指出，不复制旧说法；修复生成文档时修改生成函数。

## 修改后的验证

基础检查（代码、组件库或工作流变更后运行）：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s scripts -p 'test_*.py'
python3 scripts/component_lint.py .
```

修改内置主题编译、来源或模板时，先重建再跑上述检查：

```bash
python3 scripts/build_stitch_themes.py
python3 scripts/build_stitch_gallery.py
```

最小端到端验证（临时产物不写入仓库）：

```bash
out_dir="$(mktemp -d)"
python3 scripts/render_stitch_article.py assets/sample-article.md \
  --theme emerald --layout ruler --output "$out_dir/article.html"
python3 scripts/validate_gzh_html.py "$out_dir/article.html"
python3 scripts/wrap_preview.py "$out_dir/article.html"
```

- 源头检查要求 0 ERROR；正文要求 0 ERROR、半角标点 0 WARNING，内置渲染器要求所有 WARNING 为零。
- 保持全部色系 × 版式的内容保真及模板可重建性测试，不只验证默认主题。
- 新增或修复行为时，在对应 `test_*.py` 中补回归；CSS/结构优化需保护继承、原生标签边界、简写覆盖顺序、代码文本和 SVG 几何。
- 视觉改动检查手机宽度、长标题、长链接、代码和图片；设计还原用 `docs/gallery/comparison.html` 同文同色同宽比较。静态检查通过不代表已在真实公众号编辑器或所有深色模式客户端验证。
- 完成后检查 `git diff --check` 与 `git status --short`，仅保留相关源码、必要生成文件和文档。不要提交临时文件、`__pycache__`、凭据、API Key，或未经用户要求的文章产物。
- 默认用中文说明改动与测试结果；未执行的检查如实列出。保持改动聚焦，不顺手修复无关代码或用户内容。
