# bphr-booklets-zh

本仓库用于整理并翻译「柏林爱乐音像制品（Berliner Philharmoniker Recordings）」官网发布的各类音像制品随附 booklet（唱片内页/小册子）。产物以中文 Markdown 为主，便于检索、版本管理与协作。

- Booklet 项目统一放在 `booklets/` 下，每个 booklet 独占一个目录：
  - `booklets/<booklet-标题>/booklet.pdf`：原件 PDF（由维护者后续添加）
  - `booklets/<booklet-标题>/booklet_zh.md`：中文译文（统一使用 `_zh` 后缀）
- 目录命名规则参见 [AGENTS.md](AGENTS.md)

## 清单

- 含 booklet 的官方发行物清单（仅实体版；每条发行物下有两项任务，分别表示“booklet PDF 收集情况 / 中文翻译完成情况”；按制品标题首字母/首字符排序）：[BOOKLETS.md](BOOKLETS.md)

## 生成/更新清单
在仓库根目录运行：

- `python3 scripts/generate_booklet_checklist.py`
