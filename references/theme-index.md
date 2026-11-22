# 内置主题索引与选择决策表

当前主题的唯一注册表。原本 6 套旧主题已删除，不再作为生成候选。
设计来源与适配：[设计来源与兼容说明](stitch-design-system.md)。15 色系 × 3 章节版式；默认「墨规·翡翠林木」。
色系 ID 与主题画廊一致；版式不混色。

| 主题 | 主色 | 适用场景 | 组件库文件 | 正文下划线 CSS |
|---|---|---|---|---|
| 墨规· 翡翠林木 | `#059669` | 技术深度长文、工程架构手记（默认墨规） | `references/theme-emerald.md` | `border-bottom:2px solid #10B981;font-weight:600;` |
| 浮光· 青竹晨露 | `#0D9488` | 商业特写、年度特刊、人物专访（默认浮光） | `references/theme-bamboo-teal.md` | `border-bottom:2px solid #2DD4BF;font-weight:600;` |
| 佩兰· 寒松冷柏 | `#2E5B4B` | 古籍整理、文史哲考据、学人札记（默认素墨） | `references/theme-pine-green.md` | `border-bottom:2px solid #5E8B79;font-weight:600;` |
| 沧浪· 群青深矿 | `#1D4ED8` | 前沿 AI 报告、系统架构、硬核数码（默认墨规） | `references/theme-mineral-blue.md` | `border-bottom:2px solid #3B82F6;font-weight:600;` |
| 霁蓝· 雨过天晴 | `#0284C7` | 设计美学、用户体验、艺术展评（默认浮光） | `references/theme-cerulean.md` | `border-bottom:2px solid #38BDF8;font-weight:600;` |
| 黛渊· 极夜海墨 | `#312E81` | 宏观经济、深度研究报告、投研观察（默认素墨） | `references/theme-abyssal-indigo.md` | `border-bottom:2px solid #6366F1;font-weight:600;` |
| 朱印· 藏书官印 | `#B91C1C` | 官方重磅公告、典藏特刊、大事记（默认墨规） | `references/theme-vermilion-seal.md` | `border-bottom:2px solid #EF4444;font-weight:600;` |
| 晚霞· 霜林落日 | `#C2410C` | 品牌起源故事、手作匠人记、文化随笔（默认浮光） | `references/theme-terracotta.md` | `border-bottom:2px solid #F97316;font-weight:600;` |
| 绛华· 沉檀深绛 | `#881337` | 高奢品鉴、古典音乐策展、名著长评（默认素墨） | `references/theme-burgundy.md` | `border-bottom:2px solid #E11D48;font-weight:600;` |
| 琥珀· 金石凝光 | `#D97706` | 个人创业手记、心智认知模型、周刊（默认墨规） | `references/theme-amber-honey.md` | `border-bottom:2px solid #FBBF24;font-weight:600;` |
| 古檀· 沉香木案 | `#854D0E` | 深度学术书评、思想史研究、哲学札记（默认浮光） | `references/theme-sandalwood.md` | `border-bottom:2px solid #CA8A04;font-weight:600;` |
| 苍苔· 阶前青痕 | `#4D7C0F` | 建筑景观漫游、生态农耕生活、草木志（默认素墨） | `references/theme-moss-clay.md` | `border-bottom:2px solid #65A30D;font-weight:600;` |
| 黛紫· 紫气东来 | `#7E22CE` | 先锋精神哲学、现代诗歌、艺术跨界（默认墨规） | `references/theme-imperial-violet.md` | `border-bottom:2px solid #C084FC;font-weight:600;` |
| 素墨· 宣纸淡烟 | `#27272A` | 黑白纪实摄影、冷峻严肃文学、极简诗集（默认浮光） | `references/theme-monochrome-zen.md` | `border-bottom:2px solid #71717A;font-weight:600;` |
| 暮雪· 寒江残雪 | `#475569` | 北欧极简美学、空间建筑评论、留白随笔（默认素墨） | `references/theme-frost-slate.md` | `border-bottom:2px solid #94A3B8;font-weight:600;` |

## 选择规则

- 普通模式与全自动模式均采用固定默认参数：主题和版式均省略时，直接使用【墨规】· 翡翠林木（theme=emerald，layout=ruler），不询问确认，不按题材自动换主题。
- 仅指定主题时使用该主题及其登记的默认版式；仅指定版式时使用 emerald 色系及指定版式；两者均指定时使用指定组合。
- 用户明确要求推荐或比较时才按适用场景给建议；指定浮光/透叠用 overprint，指定墨规/标尺用 ruler，指定素墨/纯净用 pure。
- 不把色系与版式混为同一个参数；例如 mineral-blue + overprint 仍然全篇为沧浪色系。
- 用户指定已删除的旧主题时提示选择当前内置主题，不默默回退或复活旧库。
- 自定义主题仍按 theme-generator.md 登记，当前主题专属组件优先于通用库。
