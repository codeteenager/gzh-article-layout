# 通用增量约定 —— 主题专属组件优先

当前 15 套内置主题的代码块、图片/GIF、步骤标题、引用、列表、任务、表格、链接、脚注和名片**都在所选主题库中**。这些组件不能被不匹配的历史组件替代。

## 对应关系

| 输入 | 首选组件 |
|---|---|
| 围栏代码 | code + code_row，保留 macOS 顶栏；每行一个普通 p，无行号列；NBSP 保持缩进，不用 white-space:pre |
| 行内代码 | 主题纸底等宽 span，正文引号归一化不影响代码 |
| 图片 / GIF | image，保留原始 src；图注仅来自 alt，GIF 图注注明动图 |
| 标题 / 引用 / 金句 | chapter / step / quote / pullquote |
| 列表 / 任务 / 表格 | list + 对应 item / task_item / table + table_cell |
| 外链 / 脚注 / details | 完整 URL 展示卡 / footnote / 静态展开补充阅读 |

一篇文章只用选定色系的组件；三种章节版式可以按用户选择切换，但不改变色板。
所有正文从用户 Markdown 来，不能带入源设计稿的示例代码或二维码；不配置默认作者或简介，名片仅由显式作者参数启用。

## 待补素材（唯一通用补充）

设计原稿的图像展示区为样例。原文明确写了「【插入…】」时，保留待补提示并用以下居中卡片；不要编造图片 URL。
`{{纸底色}}`、`{{边框色}}`、`{{正文色}}`、`{{说明}}` 必须在生成时替换为主题变量和原文说明。

```html
<section style="margin:0 0 24px;padding:28px 20px;border:1px dashed {{边框色}};border-radius:12px;background:{{纸底色}};text-align:center;">
  <p style="margin:0 0 8px;font-size:22px;"><span leaf="">▧</span></p>
  <p style="margin:0;font-size:14px;color:{{正文色}};line-height:1.9;"><span leaf="">{{说明}}</span></p>
</section>
```

未给真实二维码时使用无二维码名片变体，不留下白色空井；给出 `--qr-url` 时恢复完整二维码右栏。默认不传作者参数、不显示名片；原文署名作为正文保留。不得输出占位符。
