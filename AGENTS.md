# AGENTS.md

本仓库用于整理并翻译「柏林爱乐音像制品（Berliner Philharmoniker Recordings, BPHR）」发行物随附的 `booklet` 文档；产物以 Markdown 为主。本文为 AI/维护者的统一工作说明，适用范围：仓库全局。

## TL;DR

- 目标产物：`booklets/<booklet-标题>/booklet_zh.md`
- 中间产物：`booklets/<booklet-标题>/booklet_en.md`（必须保留，用于审校与复现翻译边界）
- 唯一输入：`booklets/<booklet-标题>/booklet.pdf` 的可选中文本层；若无文本层则停止（默认不做 OCR）
- 两步流程：先生成/迭代清理 `booklet_en.md`，再按本文件规则翻译为 `booklet_zh.md`
- 忽略图片：不翻译图片中的文字；仅当图注属于 PDF 可选中文本且确属正文时才翻译
- 译名/术语：优先官方中文（见 `GLOSSARY.md`）；否则用更通行译名，并建议首次出现处保留原文以便核对
- 完成后：运行 `python3 scripts/update_booklets_links_only.py` 刷新 `BOOKLETS.md` 的快捷链接与完成状态

## 非目标（默认不做）

- 不尝试通过脚本自动下载 `booklet.pdf`
- 默认不做 OCR（只使用 PDF 的可选中文本层；不以图片/扫描文字为原文）

## 语言与引用

- 默认语言：中文（简体）。
- 外部工具/命令/参数/文件路径保持英文原文，不做翻译（示例：`git status`、`booklets/`）。

## 仓库结构与命名（必须）

- 所有项目统一放在 `booklets/` 下，每个 `booklet` 独占一个目录：`booklets/<booklet-标题>/`
- 目录内常见文件（按需存在）：
  - `SOURCE.md`：来源记录（脚本可生成；建议长期保留）
  - `booklet.pdf`：原件 PDF（维护者通过合法方式获取后放入）
  - `booklet_en.md`：英文原文提取与清理结果（用于锁定翻译边界）
  - `booklet_zh.md`：中文译文（目标产物）
- 当本地目录名与官网标题不一致、且希望 `BOOKLETS.md` 按官网标题展示时：在对应目录的 `SOURCE.md` 追加一行
  - `- 官方标题：<官网页面显示的标题>`

### 目录命名建议（建议）

- 以可检索为目标，优先包含“指挥/作曲家 + 作品名”。
- 使用中文书名号 `《》`；人名用中文常用译名并用 `·` 分隔（如 `汉斯·里希特`）。
- 避免在目录名中使用跨平台不兼容字符（如 ASCII 冒号 `:`）；不把“CD专辑/专辑”写进目录名。

## 翻译来源与术语优先级

- 译名/术语优先采用官方中文（BPHR 官网/数字音乐厅、厂牌官网等）；常用对照见 `GLOSSARY.md`。
- 若官方渠道未提供或写法不一致：采用更通行译名，并建议首次出现处保留原文（括注）以便核对。

## booklet 原件收集（booklet.pdf）

- `booklet.pdf` 通常无法从商品页获得稳定公开直链；多需要购买并登录后下载。
- 维护者流程：通过合法方式获取 PDF，并放置到 `booklets/<booklet-标题>/booklet.pdf`。
- 若暂时无法获得 PDF：可先用脚本生成目录与 `SOURCE.md` 占位，后续再补齐原件。

## 翻译工作流（推荐）

### 0) 前置检查（必须）

- `booklets/<booklet-标题>/booklet.pdf` 必须存在。
- `booklet.pdf` 必须有可选中文本层；若缺少文本层（例如整页为扫描图片导致无法提取），则停止并提示维护者补充可提取文本的版本。

### 1) 生成并“定边界”：`booklet_en.md`（必须先做）

运行提取脚本：

```bash
python3 scripts/extract_booklet_english.py --booklet-dir 'booklets/<booklet-标题>'
```

然后人工快速通读并迭代清理 `booklet_en.md`：

- 删除/合并明显德文-only 残留、碎行噪声、重复段落。
- 必要时做断行合并、断词还原、连字符断行修复，使正文可读可译。
- 保留并修正页码标记 `## [PDF p.xx]`（用于回查与复现边界）。
- 仅保留与正文相关的文本流（标题、作者、正文、脚注/来源、曲目/人员表等）；不尝试“描述版式”。
- 若使用 `--cut-before` 截断：务必配合 `--cut-before-min-page`，避免关键词在前文页码也出现导致误截断。

说明：英文/德文分离是启发式近似，`booklet_en.md` 不是“一次性产物”。发现德文残留、断行噪声、范围截断不准等问题时，必须先修正/迭代更新 `booklet_en.md`，再进入中文翻译。

### 2) 按规则翻译：`booklet_zh.md`

- 严格遵循本文件“曲目基本信息块（严格规则）”“忽略图片”等排版与取舍要求。
- 若 `booklet_en.md` 已明确标注了跳过范围（members/credits/人物小传/图版说明等），则第二步严格遵循，不回头扩展范围，除非用户另行要求。

### 3) 刷新清单：`BOOKLETS.md`

```bash
python3 scripts/update_booklets_links_only.py
```

## `booklet_zh.md` 排版规则

### 曲目基本信息块（严格规则）

对每一首（或每一部）作品：在该作品正文开始之前，必须按下列固定结构给出“曲目基本信息块”，位置固定在作品标题后。

1) 作品标题行（Markdown 标题）

- 使用 `#`（或在同一文件中保持同层级一致）；建议：`# 《中文作品名》（英文作品名）`

2) 作品识别行（单独一行）

- 从 PDF 读取并翻译：调性、作品号/目录号等；示例：`《第一交响曲》c 小调，作品 68`

3) 表格（必须使用 Markdown 表格）

- 单乐章/无分乐章作品：仅使用“项目/内容”表（表头固定为 `| 项目 | 内容 |`）

```markdown
| 项目 | 内容 |
| --- | --- |
| 速度与时长 | — |
| 创作时间 | — |
| 首演 | — |
```

- 多乐章作品：先给“乐章/速度标记/时长”表，再给“项目/内容”表。

  - **表头措辞规则**：
    - 常规作品（仅有速度术语）：表头写作 `| 乐章 | 速度标记 | 时长 |`
    - 标题性作品（包含乐章标题）：表头写作 `| 乐章 | 速度标记 / 乐章标题 | 时长 |`

```markdown
| 乐章 | 速度标记 | 时长 |
| --- | --- | --- |
| I | Allegro — ... | 12:34 |
| II | — | — |

| 项目 | 内容 |
| --- | --- |
| 首演 | — |
```

项目表常用项目键（按需出现，但同类信息用词必须一致）：`速度与时长`、`创作时间`、`首演`、`首演指挥`、`柏林爱乐乐团首演`、`柏林爱乐乐团首演指挥`

补充规则：

- `乐章` 使用罗马数字 `I/II/III/...`；若 PDF 使用其他编号体系则保持一致但需全文统一。
- `速度标记` 逐字保留 PDF 中的速度术语/变速序列（通常为意/德文），用 ` — `（前后各一空格的长破折号）连接。
  - **例外**：若“速度标记”实为**标题性文字**（如《阿尔卑斯交响曲》的各段落标题、《田园交响曲》的乐章标题），**必须翻译为中文**，或采用“原文（中文）”格式。
  - 检查表格中是否残留 `und`、`mit` 等德文连词，需翻译为中文（如 `&` 或 `与`）。
- `时长` 使用 `M:SS`（秒始终两位）或 `H:MM:SS`；若 PDF 未提供则写 `—`。
- `日期格式`：统一使用 `YYYY 年 M 月 D 日`（如 `2024 年 1 月 1 日`）。
- `配器列表`：统一使用 `数量 乐器名` 格式，顿号分隔（如 `2 长笛、2 双簧管`）；避免使用 `×` 号。

### 忽略图片（必须）

- 不翻译图片中的文字，不对图片做 OCR，不写图片描述/图注式补充说明。
- 若 PDF 的图注是可选中文本且属于正文内容，可照常翻译；否则一律忽略。

### 长文处理与一致性（建议）

- 长文本按“章节/小节/自然段”分块处理，避免一次性堆入导致一致性丢失；分块时保持少量上下文衔接（例如上一段末句与下一段首句）。
- 在翻译开始前先建立/复用本仓库的术语与人名对照（见 `GLOSSARY.md`），翻译过程中持续维护一个“临时术语表”，在全文结束后做一次统一回查：
  - 人名、团体名、地名、体裁名、专有名词是否前后一致
  - 同一作品/主题的指代是否统一（避免同一术语多译）

## 人工检查清单（必须）

开始翻译前：

- 确认 `booklet_en.md` 中不存在明显德文-only 残留段落（或已明确标注为“非翻译范围/已忽略”），避免后续出现“中文看似漏译”的误判。
- （可选）运行语言审计脚本辅助定位德文占比高的页：

```bash
python3 scripts/audit_booklet_en_language.py
```

通读/清理 `booklet_en.md` 时重点关注：

- 双语并排：确认已选择“英文版本”为翻译来源；若同一文章同时有德/英两版，优先只保留其中一版（通常英文）。
- 语言混入：抽取结果中若残留德文标签（如 `Symphonie`、`Fassung`、`Uraufführung` 等）或断行碎片，手动删除或合并。
- 双语同一行：元信息行常把德/英放在同一行（如 `Entstehungszeit · Year of composition:`），启发式过滤可能截断年份范围/括注；翻译前应用 `## [PDF p.xx]` 回查对应页核对。
- 字段换行：首演信息常把 `Conductor`/`Pianist` 拆成多行，提取时容易漏掉“首演钢琴/独奏”或误并入上一行；翻译前需回查 PDF。
- 截断点：确认人物小传/制作人员等段落的停止点正确（例如从某位指挥简介开始即停止）。
- 图版/图片说明：若抽取页码中包含图版说明，按“忽略图片”策略删去。
- 页码标记：保留 `## [PDF p.xx]` 有助于回查；确认页码范围与标题命中一致。

完成翻译后：

- 结构检查：确认“文章标题”没有被误放在某首作品标题之下（Markdown 标题层级要正确）。
- `BOOKLETS.md` 的“中文翻译已完成”按本地 `booklet_zh.md` 是否存在判定，并不等同于“已覆盖 PDF 全部正文”。
- 若遇到可长期复用的新坑点，更新本文件 `AGENTS.md`（例如：某类双语版式、某类截断点、某类页面噪声）。

## 自动化脚本（清单与目录维护）

### 常用脚本

- 生成/更新发行物清单（联网；不下载 PDF）：`python3 scripts/generate_booklet_checklist.py`
  - 产物：仓库根目录 `BOOKLETS.md`
- 仅按本地文件状态刷新 `BOOKLETS.md` 快捷链接（不联网）：`python3 scripts/update_booklets_links_only.py`
- 为未收集条目生成目录与 `SOURCE.md`（不联网、不下载 PDF）：`python3 scripts/collect_missing_booklets.py`
- 清理无用占位目录（不联网）：
  - dry-run：`python3 scripts/prune_unused_booklets.py`
  - apply：`python3 scripts/prune_unused_booklets.py --apply`
  - 保护：目录内放置空文件 `MANUAL_KEEP` 可避免被清理
- （可选）审计 `booklet_en.md` 的德文占比（不联网）：`python3 scripts/audit_booklet_en_language.py`

### 清单去重与“豪华版本”规则（简述）

`scripts/generate_booklet_checklist.py` 会把官网同一发行物的多个版本页进行去重，并在同组内优先选择“更豪华”的实体版本作为代表条目（价格/蓝光/精装/限量等）。

如发现 `BOOKLETS.md` 出现重复标题，可用下列命令快速自检（只输出重复标题，不改文件）：

```bash
python3 - <<'PY'
import re
from collections import Counter

lines=open('BOOKLETS.md','r',encoding='utf-8').read().splitlines()
rx=re.compile(r'^- (?!\[)(.+)$')
c=Counter(m.group(1).strip() for line in lines if (m:=rx.match(line)))
dups=[(t,n) for t,n in c.items() if n>1]
print('duplicate_titles:', len(dups))
for t,n in sorted(dups, key=lambda x:(-x[1], x[0])):
    print(n, t)
PY
```

### 脚本验证（改动 `scripts/` 后建议跑）

离线验证（不联网）：

- `python3 -m py_compile scripts/*.py`
- `python3 scripts/update_booklets_links_only.py`
- `python3 scripts/prune_unused_booklets.py`
- `python3 scripts/collect_missing_booklets.py --limit 1 --dry-run`

在线验证（联网，尽量跑；避免污染仓库文件建议加 `--output`）：

- `python3 scripts/generate_booklet_checklist.py --url '<购买链接1>' --url '<购买链接2>' --output /tmp/BOOKLETS.online-smoke.md`

## 排坑备忘（不常见但有帮助）

- `scripts/extract_booklet_english.py` 的语言过滤是启发式；双语并排/两栏排版时，“残留德文/碎行”属于常见现象，必须回到 `## [PDF p.xx]` 做快速人工清理与核对。
- 终端连接不稳时，避免长 heredoc/大段输出；优先把逻辑写进脚本文件，执行用短命令（便于重跑与复现）。

## 完成定义（Definition of Done）

对单个 `booklet` 目录而言，完成通常意味着：

- `booklet_en.md` 可代表“需要翻译的范围”（无明显德文-only 残留、断行噪声已清理、截断点合理）
- `booklet_zh.md` 覆盖 `booklet_en.md` 的全部正文范围，且关键译名/体裁/角色用词一致
- 运行 `python3 scripts/update_booklets_links_only.py` 刷新 `BOOKLETS.md` 的状态与快捷链接

如需长期复用的译名/术语/栏目对照表，请更新 `GLOSSARY.md`。
