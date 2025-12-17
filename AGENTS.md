# AGENTS.md

本仓库用于整理与翻译古典音乐相关的 `booklet`（唱片内页/小册子）文档，产物以 Markdown 为主。

## 语言与沟通

- 默认语言：中文（简体）。讨论、评审、提交信息等优先使用中文。
- 外部工具/命令/参数/文件路径保持英文原文，不做翻译（示例：`git status`、`booklets/`）。

## 仓库结构与命名

- 所有 `booklet` 项目统一放在 `booklets/` 下，并且每个 `booklet` 独占一个目录：
  - `booklets/<booklet-标题>/booklet.pdf`：原件 PDF（由维护者后续添加）
  - `booklets/<booklet-标题>/booklet_zh.md`：中文 Markdown 译文（统一使用 `_zh` 后缀）

提示：当本地目录名与官网标题不一致、且你希望 `BOOKLETS.md` 中显示为官网标题时，可在对应目录的 `SOURCE.md` 中额外添加一行：
- `- 官方标题：<官网页面显示的标题>`
脚本会优先用该标题作为清单展示名，但仍保持目录名不变。
- 目录命名建议：
  - 以可检索为目标，优先包含“指挥/作曲家 + 作品名”。
  - 使用中文书名号 `《》`；人名用中文常用译名并用 `·` 分隔（如 `汉斯·里希特`）。
  - 避免在目录名中使用 ASCII 冒号 `:` 等跨平台不兼容字符；不把“CD专辑/专辑”写进目录名。
  - 仓库语境统一称 `booklet`（不要混用“CD小册子”“CD专辑文案”等作为仓库术语）。

## booklet 原件收集（booklet.pdf）

- 结论：`booklet.pdf` 通常无法通过 Berliner Philharmoniker Recordings 商品页直接获得稳定的公开直链下载。
  - 官网页面可能会标注 “Digital Booklet/数字手册/手册”，但实际 PDF 多数需要购买并登录后下载。
- 因此：本仓库放弃“通过脚本自动拉取 booklet 原件”的方案。
- 维护者流程：请通过合法方式获取 PDF（例如购买并登录后下载），并放置到目标目录：
  - `booklets/<booklet-标题>/booklet.pdf`

提示：如果你暂时无法获得 PDF，可先用脚本生成目录与 `SOURCE.md` 占位，后续再补齐原件。

## 自动化脚本

- 生成/更新发行物清单（含本地完成状态与快捷链接）
  - `python3 scripts/generate_booklet_checklist.py`
  - 产物：仓库根目录 `BOOKLETS.md`
  - 说明：该脚本会抓取官网页面用于识别“是否标注 booklet”，但不会下载 `booklet.pdf`。

### 清单去重与“豪华版本”规则（维护要点）

官网同一发行物可能存在多个页面/版本（例如：同一套装的 `CD (Hybrid-SACD)`、`CD & Blu-ray`、`Vinyl`、以及合集页/专题页）。为避免 `BOOKLETS.md` 出现“同一专辑多个条目”或“标题完全相同但重复列出”的情况，`scripts/generate_booklet_checklist.py` 的核心策略是：

- **去重分组键**：优先使用页面主区域的 `product-title`（即页面上作品/发行物的主标题）作为同专辑的分组依据。
  - 原因：`og:title` / HTML `<title>` 往往会因页面类型不同而变化（例如“专题页标题”vs“具体版本页标题”），用它们做分组更容易把同专辑拆成多组。
- **选择“最豪华版本”**：在同一分组内，优先选择 **价格更高的实体版本** 作为代表条目；再用“蓝光/精装/限量”等关键词作为次级加权；并避免把 download-only 页面当作代表条目。

如果你发现 `BOOKLETS.md` 又出现重复条目，可先用下列命令做快速自检（不改文件，只输出重复标题）：

- `python3 - <<'PY'
import re
from collections import Counter
lines=open('BOOKLETS.md','r',encoding='utf-8').read().splitlines()
rx=re.compile(r'^- (?!\[)(.+)$')
c=Counter(m.group(1).strip() for line in lines if (m:=rx.match(line)))
dups=[(t,n) for t,n in c.items() if n>1]
print('duplicate_titles:', len(dups))
for t,n in sorted(dups, key=lambda x:(-x[1], x[0])):
    print(n, t)
PY`

- 仅根据本地文件状态为 `BOOKLETS.md` 补齐/更新快捷链接（不联网）
  - `python3 scripts/update_booklets_links_only.py`
  - 说明：当你手动放入/更新 `booklet.pdf` 或 `booklet_zh.md` 后，可用它快速刷新链接显示，并按清单头部声明的规则自动重排条目（`中文翻译已完成 > booklet 已收集 > 其他`；同一优先级内按标题首字符排序）。

- 为未收集条目生成目录与来源记录（不联网、不下载 PDF）
  - `python3 scripts/collect_missing_booklets.py`
  - 作用：对 `BOOKLETS.md` 中 “booklet 已收集” 未勾选的条目，创建 `booklets/<标题>/` 并写入 `SOURCE.md`。

- 清理 `booklets/` 下不再需要的占位目录（不联网）
  - `python3 scripts/prune_unused_booklets.py`（dry-run）
  - `python3 scripts/prune_unused_booklets.py --apply`（实际删除）
  - 说明：当清单去重/变动后，用于删除未在 `BOOKLETS.md` 中出现且不包含 `booklet.pdf`/`booklet_zh.md` 的占位目录。
  - 保护手工条目：若某目录属于“官网未列出、需手工维护”的条目，但暂时还没有 `booklet.pdf`/`booklet_zh.md`，可在目录内放置空文件 `MANUAL_KEEP` 以避免被清理脚本删除。

### 脚本验证（维护/改动后必做）

目标：当你修改 `scripts/` 下任一脚本（尤其是清单生成/链接更新/目录归一化逻辑）后，用一组**可重复**的检查尽快发现回归。

约定：验证命令建议在仓库根目录执行（例如 `python3 scripts/update_booklets_links_only.py`）。

#### 1) 离线验证（不联网，必须跑）

- 语法与导入检查：
  - `python3 -m py_compile scripts/*.py`
- 不联网脚本冒烟：
  - `python3 scripts/update_booklets_links_only.py`
  - `python3 scripts/prune_unused_booklets.py`（默认 dry-run）
  - `python3 scripts/collect_missing_booklets.py --limit 1 --dry-run`
- 联网脚本仅做入口检查（不触网）：
  - `python3 scripts/generate_booklet_checklist.py --help`

说明：`collect_missing_booklets.py` 的 `--dry-run` 用于安全验证解析与归一化逻辑，不会创建目录/写文件。

#### 2) 在线验证（联网，尽量跑）

注意：`generate_booklet_checklist.py` 默认会写入 `BOOKLETS.md`。为了验证而不影响仓库文件，推荐使用 `--output` 写到临时文件。

- 小规模在线冒烟（建议每次改动都跑）：
  - `python3 scripts/generate_booklet_checklist.py --url '<购买链接1>' --url '<购买链接2>' --output /tmp/BOOKLETS.online-smoke.md`
- 全量在线扫描（网络稳定时再跑，或准备发布/提交前跑）：
  - `python3 scripts/generate_booklet_checklist.py --workers 6 --output /tmp/BOOKLETS.online-full.md`
  - 查看抓取/解析告警：`grep -n 'Warning\|error\|failed' /tmp/BOOKLETS.online-full.md | head`

在线告警的常见原因：
- sitemap 可能包含已下线页面，导致 `curl ... 404`；这类告警通常不代表脚本逻辑问题。
- 若告警数量显著增加或出现非 404 的失败（例如大量超时/解析失败），再回查对应 URL 的页面结构是否变更。


## 术语规范（音乐/出版）

- `booklet`：在仓库语境中一律使用 `booklet` 指代唱片内页/小册子（不要混用“CD小册子”“CD专辑文案”等作为仓库术语）。
- 作品体裁常用译法（优先以数字音乐厅中文为准；未出现则按业界主流译法）：
  - 交响/管弦乐
    - Symphony：交响曲
    - Chamber Symphony：室内交响曲
    - Sinfonietta：小交响曲
    - Symphonic Poem / Tone Poem：交响诗（音诗）
    - Symphonic sketches：交响素描
    - Symphonic Variations：交响变奏曲
    - Overture：序曲
    - Concert Overture：音乐会序曲
    - Suite / Orchestral Suite：组曲 / 管弦组曲
    - Symphonic Suite：交响组曲
    - Ballet / Ballet Suite：芭蕾舞剧 / 芭蕾组曲
    - Serenade：小夜曲
    - Divertimento：嬉游曲
    - Rhapsody：狂想曲
    - Fantasia / Fantasy：幻想曲
    - Idyll：牧歌
    - March：进行曲
    - Waltz：圆舞曲
    - Polonaise：波兰舞曲
    - Mazurka：玛祖卡
  - 协奏
    - Concerto：协奏曲
    - Concerto for Orchestra：乐队协奏曲
    - Concerto grosso：大协奏曲
    - Sinfonia concertante：交响协奏曲
    - Double Concerto：双重协奏曲
    - Triple Concerto：三重协奏曲
    - Violin / Piano / Cello Concerto：小提琴 / 钢琴 / 大提琴协奏曲（以此类推）
  - 歌剧/舞台
    - Opera：歌剧
    - Operetta：轻歌剧
    - Singspiel：歌唱剧
    - Incidental music：戏剧配乐（或：舞台配乐）
  - 声乐/合唱
    - Oratorio：神剧
    - Cantata：康塔塔
    - Mass：弥撒曲
    - Requiem：安魂曲
    - Passion：受难曲
    - Motet：经文歌
    - Stabat Mater：圣母悼歌
    - Te Deum：感恩颂
    - Magnificat：尊主颂
    - Song cycle：歌曲套曲（或：艺术歌曲套曲）
    - Lied：艺术歌曲
  - 室内乐/独奏
    - Sonata：奏鸣曲
    - Duo：二重奏
    - Trio：三重奏
    - Quartet：四重奏
    - Quintet：五重奏
    - Sextet：六重奏
    - Septet：七重奏
    - Octet：八重奏
    - Nonet：九重奏
    - String Quartet：弦乐四重奏
    - Piano Trio / Piano Quartet / Piano Quintet：钢琴三重奏 / 钢琴四重奏 / 钢琴五重奏
    - Prelude：前奏曲
    - Fugue：赋格
    - Toccata：托卡塔
    - Etude：练习曲
    - Nocturne：夜曲
    - Scherzo：谐谑曲
    - Ballade：叙事曲
    - Impromptu：即兴曲
    - Intermezzo：间奏曲
    - Capriccio：随想曲
    - Humoresque：幽默曲
    - Romance：浪漫曲
    - Elegy：挽歌
    - Variations：变奏曲
- 合奏/机构相关常用译法：
  - Court Orchestra / Hoforchester：宫廷乐团（必要时保留原文）
- 调性写法：`c 小调 / C 大调`；需要降/升号时优先用 `♭/♯`（或“降/升”），同一文档内保持一致。
- 作品编号：`作品 68`、`作品 81`；若出现 `Op.` 可在首次出现处补充 `Op.` 与中文“作品号”的对应关系。
- 速度/力度术语：原文保留（可用斜体，如 `*fortissimo*`）；正文尽量避免用加粗做强调，需强调时优先改写句子或调整结构。

## 人名与地名翻译规范（古典音乐通用做法）

总体原则：以柏林爱乐官方中文为第一优先级，并按以下来源顺序统一译名与术语：

1) 柏林爱乐数字音乐厅（Digital Concert Hall）中文站（人名/乐团/栏目/功能与演出相关术语优先）
   - https://www.digitalconcerthall.com/zh/concerts
   - https://www.digitalconcerthall.com/zh/categories

2) Berliner Philharmoniker Recordings 中文站（唱片厂牌/发行物相关用语优先）
   - https://www.berliner-philharmoniker-recordings.com/?___store=rec_zh

若官方页面已给出译名，则在本仓库中统一使用其写法（包含头衔如“爵士”的处理、`冯/凡/范` 等小品词用字、分隔号 `·` 的使用等）。若官方渠道未提供或出现多种写法，则采用更通行的译名，并在首次出现处保留原文以便核对，同时记录在下方“常见对照”中以便后续统一。

写法规则：

- 首次出现建议使用“中文译名（原文/通行拉丁转写）”，后文可仅用中文译名。
- 西文人名使用间隔号 `·`；贵族小品词按官方写法（常见如 `冯·/凡·/范·`）。
- 头衔处理：若数字音乐厅的中文“艺术家”页将头衔作为姓名的一部分（如 `西蒙·拉特爵士`），则统一保留；否则不强行添加。原文头衔可保留在括注中。
- 机构/团体：
  - Berliner Philharmoniker / Berlin Philharmonic：柏林爱乐乐团（首次可括注原文）

常见对照（以数字音乐厅中文为准，可按需增补/统一）：

- Kirill Petrenko：基里尔·别特连科
- Sir Simon Rattle：西蒙·拉特爵士
- Nikolaus Harnoncourt：尼克劳斯·哈农库特
- Daniel Harding：丹尼尔·哈丁
- Leonidas Kavakos：列奥尼达·卡瓦克斯
- Johannes Brahms：约翰内斯·勃拉姆斯
- Ludwig van Beethoven：路德维希·凡·贝多芬（或常用简称：贝多芬）
- Wolfgang Amadeus Mozart：沃尔夫冈·阿马德乌斯·莫扎特（或：莫扎特）
- Robert Schumann：罗伯特·舒曼
- Clara Schumann：克拉拉·舒曼
- Eduard Hanslick：爱德华·汉斯立克
- Hans von Bülow：汉斯·冯·彪罗
- Richard Strauss：理查·施特劳斯
- Herbert von Karajan：赫伯特·冯·卡拉扬
- Claudio Abbado：克劳迪奥·阿巴多
- Daniel Barenboim：丹尼尔·巴伦博伊姆

## 术语与栏目（以数字音乐厅中文为准）

音乐会系列/栏目（Digital Concert Hall `分类`）：

- Europakonzert：欧洲圣城音乐会
- Waldbühne：森林音乐会
- Silvesterkonzert：除夕音乐会
- Late Night：深夜音乐会
- Education：寓教于乐
- Opera：歌剧
- Chamber Music：室内乐
- Tour concerts：巡演音乐会

常见“艺术家/角色/分工”用词：

- Conductor：指挥
- Chief Conductor：首席指挥
- Composer：作曲（数字音乐厅用法）
- Soprano：女高音
- Mezzo-soprano：次女高音（数字音乐厅用法）
- Tenor：男高音
- Baritone：男中音
- Bass：男低音
- Narration / Speaker：朗诵
- Host / Presenter：主持（如“中提琴与主持”）
- Lighting design：灯光设计
- Chorus master / Choir conductor：合唱指挥
- Choral director：合唱艺术指导

常见乐器/声部（数字音乐厅用法示例）：

- Violin：小提琴
- Viola：中提琴
- Cello：大提琴
- Double bass：低音提琴
- Piano：钢琴
- Harp：竖琴
- Organ：管风琴
- Flute：长笛
- Oboe：双簧管
- Clarinet：单簧管
- Bassoon：大管
- Horn：圆号
- Trumpet：小号
- Trombone：长号
- Tuba：大号
- Timpani：定音鼓
- Percussion：打击乐
- (其余按通行译法；新增时优先查数字音乐厅“艺术家”页或曲目页标注)

常见团体/机构（数字音乐厅用法示例）：

- Rundfunkchor Berlin：柏林广播合唱团

## 文档排版建议（Markdown）

- “乐章/速度/时长”与“创作/首演/首演指挥/柏林爱乐首演”等信息，建议用表格集中呈现，位置保持在作品标题后的开头区域。
- 列表/引用/标题层级保持清晰；避免在同一段落中混用多种强调方式。

## AI 翻译策略（booklet）

目标：从 `booklets/<booklet-标题>/booklet.pdf` 生成 `booklets/<booklet-标题>/booklet_zh.md`，并在全篇保持术语、人名、体裁等译法一致。

### 两步工作流（推荐）

将翻译流程拆为两步，先“定边界/定原文”，再“按规则翻译”。

1) 先从 PDF 提取英文原文，生成 `booklet_en.md`
  - 目的：明确“需要翻译的具体内容”与停止点（哪些页/哪些段落不翻译）。
  - 推荐使用脚本（示例）：`python3 scripts/extract_booklet_english.py --booklet-dir 'booklets/<booklet-标题>'`
  - 重要：英文/德文分离只能做到“自动化 + 规则化的近似”，无法保证 100% 纯净；必须人工快速通读校对（见下方“人工检查清单”）。
  - **迭代要求**：`booklet_en.md` 不是“一次性产物”。当发现德文残留、断行噪声、范围截断不准等问题时，必须**先修正/迭代更新 `booklet_en.md`**（必要时调整脚本参数或手工清理），直到它能代表“真正要翻译的内容”，再进入中文翻译。

2) 再根据翻译规则，把 `booklet_en.md` 翻译为 `booklet_zh.md`
  - 按本文件“曲目基本信息（严格规则）”“忽略图片”等要求排版与取舍。
  - 若 `booklet_en.md` 已明确标注了“跳过范围”（members/credits/人物小传/图版说明等），则第二步严格遵循，不再回头扩展范围，除非用户另行要求。

### 维护者自检（每次翻译任务）

- 在开始翻译前：
  - 确认 `booklet_en.md` 中**不存在明显德文-only 残留段落**（或已明确标注为“非翻译范围/已忽略”），避免后续出现“中文看似漏译”的误判。
  - 若发现问题：优先回到第 1 步迭代更新 `booklet_en.md`（必要时重跑提取脚本），再翻译。
- 在完成翻译后：
  - 用最新遇到的坑点反向检查：是否需要更新本文件（`AGENTS.md`）中的规则/清单（例如：某类双语版式、某类截断点、某类页面噪声）。
  - 若需要，及时把经验写入 `AGENTS.md`，确保下次可复用。
  - 运行 `python3 scripts/update_booklets_links_only.py`，同步刷新 `BOOKLETS.md` 的完成勾选、快捷链接与排序。

#### 人工检查清单（必须）

- 双语并排的 booklet：确认已选择“英文版本”为翻译来源；若同一文章同时有德/英两版，优先只保留其中一版（通常英文）。
- 语言混入：抽取结果中若残留德文标签（如 `Symphonie`、`Fassung`、`Uraufführung` 等）或断行碎片，手动删除或合并。
- 双语同一行：元信息行常把德/英放在同一行（如 `Entstehungszeit · Year of composition:`），启发式过滤可能截断年份范围/括注；翻译前应用 `## [PDF p.xx]` 回查对应页核对。
- 字段换行：首演信息常把 `Conductor`/`Pianist` 拆成多行，提取时容易漏掉“首演钢琴/独奏”或误并入上一行；翻译前需回查 PDF。
- 截断点：确认人物小传/制作人员等段落的停止点正确（例如从某位指挥简介开始即停止）。
- 图版/图片说明：若抽取页码中包含图版说明，按“忽略图片”策略删去。
- 页码标记：保留 `## [PDF p.xx]` 有助于回查；确认页码范围与标题命中一致。

### 输入与原文范围

- 读取目标目录下的 `booklet.pdf` 作为唯一输入源。
- 以 PDF 的**可选中英文文本**为原文进行翻译与改写（不以图片/扫描文字为原文）。
- 若 PDF 缺少文本层（例如整页为扫描图片导致无法提取英文文本），则停止并提示维护者补充可提取文本的版本；默认不做 OCR（见“忽略图片”）。

### 文本提取与预处理

- 先提取文本层（保持段落/标题层级，必要时做断行合并、断词还原、连字符断行修复）。
- 仅保留与正文相关的文本流：标题、作者、正文、脚注/来源、曲目/人员表等；不尝试“描述版式”。

### 曲目基本信息（严格规则）

对于每一首（或每一部）作品的正文部分，在该作品正文开始之前必须按以下结构给出“曲目基本信息块”，位置固定在作品标题后，且格式统一：

1) 作品标题行（Markdown 标题）  
   - 使用 `#`（或在同一层级中一致的标题级别），格式建议：`# 《中文作品名》（英文作品名）`

2) 作品识别行（单独一行）  
   - 优先从 PDF 读取并翻译：调性、作品号/目录号等信息；示例：`《第一交响曲》c 小调，作品 68`

3) 表格（必须使用 Markdown 表格）
   - 若为**单乐章/无分乐章**作品：使用一张“项目/内容”表：
     - 表头固定为 `| 项目 | 内容 |`
     - 常用项目键（按需出现，但同类信息用词必须一致）：`速度与时长`、`创作时间`、`首演`、`首演指挥`、`柏林爱乐乐团首演`、`柏林爱乐乐团首演指挥`
   - 若为**多乐章**作品：先给一张“乐章/速度标记/时长”表，再给一张“项目/内容”表：
     - 乐章表表头固定为 `| 乐章 | 速度标记 | 时长 |`
     - `乐章` 使用罗马数字（`I`/`II`/`III`/…）；若 PDF 使用其他编号体系则保持一致但需全文统一
     - `速度标记` 逐字保留 PDF 中的速度术语/变速序列（通常为意/德文），用 ` — `（长破折号，前后各一空格）连接；不在此处额外添加解释性中文（除非 PDF 原文包含）
     - `时长` 使用 `M:SS`（秒始终两位）或 `H:MM:SS`；若 PDF 未提供则写 `—`

### 忽略图片

- 不翻译图片中的文字，不对图片做 OCR，不写“图片描述/图注式”补充说明。
- 若 PDF 的图注是可选中文本且属于正文内容，可照常翻译；否则一律忽略。

### 长文处理与一致性（效率与质量）

- 长文本按“章节/小节/自然段”分块处理，避免一次性堆入导致一致性丢失；分块时保持少量上下文衔接（例如上一段末句与下一段首句）。
- 在翻译开始前先建立/复用本仓库的术语与人名对照（见本文件相关章节），翻译过程中持续维护一个“临时术语表”，在全文结束后做一次统一回查：
  - 人名、团体名、地名、体裁名、专有名词是否前后一致
  - 同一作品/主题的指代是否统一（避免同一术语多译）

### 排坑备忘（仅保留不常见但有帮助的点）

- `scripts/extract_booklet_english.py` 的语言过滤是启发式；双语并排/两栏排版时，“残留德文/碎行”属于正常现象，必须回到 `## [PDF p.xx]` 做快速人工清理与核对。
- 使用 `--cut-before` 截断时，务必配合 `--cut-before-min-page`，避免关键词在前文页码也出现而误截断。
- 终端连接不稳时，避免长 heredoc/大段输出；优先把逻辑写进脚本文件，执行用短命令（便于重跑与复现）。
- 最终排版做一次结构检查：确认“文章标题”没有被误放在某首作品标题之下（Markdown 标题层级）；`BOOKLETS.md` 的“中文翻译已完成”按本地 `booklet_zh.md` 是否存在判定，并不等同于“已覆盖 PDF 全部正文”。
