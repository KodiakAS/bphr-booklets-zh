# bphr-booklets-zh

本仓库收集并翻译「柏林爱乐音像制品（Berliner Philharmoniker Recordings, BPHR）」发行物随附的 booklet（唱片内页/小册子）文本，输出为可检索的中文 Markdown。

## 如何阅读

- 总目录/完成进度：`BOOKLETS.md`
- 单个 booklet：`booklets/<booklet-标题>/booklet_zh.md`
- 英文对照（如存在）：`booklets/<booklet-标题>/booklet_en.md`

## 清单

- 含 booklet 的官方发行物清单（仅实体版；每条发行物下有两项任务，分别表示“booklet PDF 收集情况 / 中文翻译完成情况”；按制品标题首字母/首字符排序）：[BOOKLETS.md](BOOKLETS.md)

## 仓库结构（简要）

- `booklets/<booklet-标题>/booklet_zh.md`：中文译文（目标产物）
- `booklets/<booklet-标题>/booklet_en.md`：从 PDF 提取并清理后的英文原文（中间产物，建议保留以便审校与复现）
- `booklets/<booklet-标题>/booklet.pdf`：原件 PDF（可能缺失；通常需要购买并登录后下载，本仓库不自动下载，默认不做 OCR）

## 维护与贡献

- 命名、脚本、翻译规则（给维护者/AI）：[AGENTS.md](AGENTS.md)
- 译名/术语对照：`GLOSSARY.md`
