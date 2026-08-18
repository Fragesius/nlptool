# 汉英 NLP 分析工具

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey.svg)]()

> 基于 Python + Tkinter 的跨语言 NLP 桌面工具 — 分词 · 依存句法 · 情感分析 · 语言指纹 · 可读性 · 图表

**作者：** [Fragesius](https://github.com/Fragesius)

---

## ✨ 功能

### 🔤 基础分析
- 中文分词（jieba + pkuseg）、英文分词（spaCy）
- 词性标注、句子切分、字符/词数统计
- 词频分布、词性比例分析

### 🧬 句法 & 语义
- 命名实体识别（NER）、关键词提取（TF-IDF）
- 依存句法分析 & 可视化
- 情感分析（中文 SnowNLP + 英文 VADER）

### 🕵️ 语言指纹（Authorship Attribution）
- 8 维度加权余弦相似度：虚词频率(0.30)、标点模式(0.15)、词 bigram(0.15)、词长(0.10)、句长(0.10)、TTR(0.10)、字 4-gram(0.05)、Hapax(0.05)
- Wilcoxon 符号秩检验 + 置换检验(10k) + Cohen's d 效应量
- 多作者对比判定 + 报告生成

### 📊 可视化
- 词云、词频柱状图、词性饼图、依存句法树
- 情感趋势折线图、对比雷达图

### 📖 可读性分析
- Flesch-Kincaid 英文可读性
- 中文文本可读性评估
- 中英双语对齐分析

### 🌐 可选 API 模式
- 支持 OpenAI 兼容接口（GPT / GLM / DeepSeek 等）
- 综合语言学分析、句法深度分析、文体风格分析
- 配置保存在本地，不上传隐私

---

## 🚀 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 下载英文模型（推荐）
python -m spacy download en_core_web_sm

# 3. 运行
python main.py
```

> 未安装的库会自动降级，核心功能始终可用。

---

## 📁 项目结构

```
nlptool/
├── main.py                         # 入口
├── requirements.txt                # 依赖
├── core/
│   ├── analyzer.py                 # 分词、词性、NER、关键词、情感
│   ├── stylometry.py               # Burrows' Delta 文体计量（纯 Python）
│   ├── linguistic_fingerprint.py   # 语言指纹/作者识别引擎
│   ├── comparison.py               # 可读性、中英对齐
│   ├── api_backend.py              # 在线 API 后端
│   ├── file_io.py                  # 文件读写
│   ├── history.py                  # 分析历史
│   └── _paths.py                   # 路径管理
├── viz/
│   ├── plots.py                    # matplotlib 图表
│   └── dendrogram.py               # 层次聚类树状图（300 dpi PNG）
├── experiments/
│   ├── run_delta.py                # Burrows' Delta 命令行入口
│   └── sample_corpus/              # 4 篇合成冒烟语料（含生成脚本）
├── tests/
│   ├── test_analyzer.py            # 核心分析测试
│   ├── test_comparison.py          # 可读性/对齐测试
│   ├── test_concordance.py         # KWIC 测试
│   ├── test_stylometry.py          # 文体计量与聚类测试
│   └── test_spacy_fallback.py      # spaCy 缺失降级回归测试
└── ui/
    ├── main_window.py              # 主窗口 & 菜单
    ├── tabs.py                     # 功能标签页
    └── style.py                    # 界面样式
```

---

## ⚙️ 后端栈

| 功能 | 后端 |
|------|------|
| 中文分词 & 词性 | jieba / pkuseg |
| 英文 NLP | spaCy `en_core_web_sm` |
| 中文情感 | SnowNLP |
| 英文情感 | VADER（nltk） |
| 关键词 | TF-IDF |
| 可视化 | matplotlib + wordcloud |
| 语言指纹 | 纯 Python（无 scipy 依赖，自实现统计检验） |

---

## 📝 License

MIT © 2026 Fragesius

---

## 📦 Changelog

### v2.2.0 — 统计与图：多尺度切片、篇目级统计与自助法稳健性

📊 **篇目级统计（`experiments/story_stats.py`，新增）**
- `story_wilcoxon`：按篇目构造同译者减跨译者相似度差值，做篇目级 Wilcoxon 符号秩检验，报告 W、p 与秩双列相关 r 作为效应量
- `bootstrap_d_ci`：以篇目为单元自助重抽样，估计 Cohen's d 的 95% 置信区间；使用独立随机种子（默认 20260818），不干扰置换检验的随机流
- `equal_chunk_robustness`：把每个「篇目 × 译者」单元格降采样到最小切片数，重跑信号竞争检验与 Cohen's d，排除切片数不均衡的干扰
- 三个函数均为纯 Python、确定性实现

🔀 **多尺度切片与稳健性接线（`experiments/run_experiment.py`）**
- 新增 `--scale`：记入 v2.2.0 篇目级 CSV 产物的切片尺度标签（如 1k/2k/4k）
- 新增 `--boot-n`（篇目级自助法次数，默认 10000）与 `--boot-seed`（独立自助法随机种子）
- 报告新增稳健性检验段：篇目级自助法置信区间、篇目级 Wilcoxon 检验与均衡切片检验

🧪 **测试与图**
- 新增 `tests/test_story_stats.py`，覆盖三个统计函数的确定性与数值，兼容 `python run_tests.py`
- `viz/dendrogram.py` 图式改进

### v2.1.0 — 英文化：英文 CLI、英文报告与英文 README

🌐 **英文 CLI**
- `experiments/run_delta.py` 的命令行帮助、stdout 提示与报错信息全面英文化

🌍 **英文报告输出（`experiments/run_experiment.py`）**
- 新增 `--report-lang {zh,en}`（默认 zh）：`report.md` 模板文字可切换中英文，数字、表格结构与 CSV 产物两种语言完全一致

📘 **英文 README 与测试**
- 新增 `README_EN.md`（英文项目说明）
- 新增 `tests/test_report_lang.py`，覆盖中英文报告模板一致性
- 更新 `.gitignore`

### v2.0.0 — 性能重构、新研究指标、进度系统与 GUI 现代化

⚡ **实验管线性能重构（统计结果零变化）**
- 语言指纹管线每样本只分词一次：新增 `core/analyzer.py` 的 `tokenize_many()`（英文走 spaCy `nlp.pipe` 批处理，结果与逐条分词完全一致），预分词结果同时供 `build_global_vocab()` 与 `extract_features()` 复用；新增 `extract_sentence_stats_many()` 把全部文本的句子收集后一次性批量分词，消除「每句一次 spaCy 调用」的开销
- `weighted_cosine_similarity()` 增加向量范数缓存（`FeatureVector._norms`），两两比较场景下每个向量的范数只计算一次，公式与运算顺序不变
- 220 样本实测 115s → 80s；优化前后 `delta_matrix.csv` / `dendrogram.png` / `fingerprint_pairs.csv` / `report.md` 逐字节一致
- 新增 `tests/test_performance.py`：30 样本断言 `extract_features` 调用次数 == 样本数（O(n) 提取），批量/逐条路径结果一致性

📏 **两个新研究指标（`experiments/group_metrics.py`，只加不改）**
- 1-NN 留一法分类准确率：基于 Delta 距离矩阵逐切片找最近邻判组，输出总体准确率、随机基线（最大组占比）与分组准确率，明细 `nn_predictions.csv`（每切片一行）
- 信号竞争检验：同词根篇目（去 `__chunkNNN` 后缀）跨组配对为同一原作的两个译本，比较同篇跨译者距离与同译者跨篇距离，纯 Python 二项符号检验（H0: p=0.5），明细 `signal_competition.csv`，孤儿篇目跳过并列于报告；两项指标均含中文模板结论并写入 `report.md`
- 既有 Delta 比值、Wilcoxon、置换检验、Cohen's d 的计算逻辑与数字一律不变

📊 **确定性进度系统**
- `run()` / `slice_corpus()` / `delta_matrix()` / 1-NN / 信号竞争均接受可选 `progress_callback(current, total, stage_name)`；命令行不传回调时行为完全不变
- 各阶段工作量明确：切片 N 文件、指纹特征提取 N 样本、Delta 矩阵 N²/2 对、指纹配对 M 对、1-NN N 次、信号竞争 P 对
- GUI 实验页内嵌确定性进度条与阶段文字（如「指纹配对 12,340/27,930」），后台线程回调经队列切主线程刷新

🎨 **全 GUI 迁移 customtkinter**
- 主窗口、全部 8 个标签页与全部对话框迁移到 customtkinter 控件体系，无原生 tk/ttk 控件混用（仅保留 CTk 无等价物的窗口菜单 `tk.Menu` 与 matplotlib 嵌入画布）
- 学术工具感设计：深浅色跟随系统（保留手动切换按钮），全局统一墨绿强调色（`ui/theme_academic.json` + `ui/style.py` 双色常量），统一字体与 padding
- 每个标签页按「输入设置 / 运行控制 / 结果展示」三段式卡片分区；实验页结果摘要为整齐网格，显著性结论带语义色（显著=绿、不显著=灰）；长文本结果区均为滚动文本框；窗口设最小尺寸
- 迁移只动 `ui/` 层与 `main.py`，业务逻辑调用关系一行未改

🧹 **切片输出目录清理（`--clean`）**
- `slice_corpus.py` 新增 `--clean`：切片前清空输出目录（含根目录/主目录等危险路径护栏，清空前打印删除条目数）；不带 `--clean` 行为完全不变
- GUI 实验页新增「运行前清空输出目录」勾选框，默认勾选

### v1.4.1 — 批量实验管线图形界面

🖱 **「批量实验」标签页**
- 新增 `ExperimentTab`（`ui/tabs.py`）：鼠标点选语料目录（按 一级子文件夹=组别 组织）、输出目录（默认 `语料目录/experiment_output`）、切片词数（默认 2000，正整数校验），「切片后实验 / 直接实验」单选，一键跑完整条译者风格实验管线
- GUI 不复制实验逻辑：切片直接调 `experiments/slice_corpus.py` 的 `slice_corpus()`，实验直接调 `experiments/run_experiment.py` 的 `run()`；命令行入口、输出文件与既有测试行为完全不变
- 耗时任务复用 v1.2.0 建立的后台线程 + 进度对话框模式，界面不卡死；后台线程内临时将 matplotlib 切到 Agg 后端，避免非主线程建图崩溃
- 结果摘要直接取自 `run()` 返回的结果字典（新增 `conclusion`/`significant` 字段，report.md 结论段的中文模板文字随之暴露给调用方），展示组内/组间 Delta 及比值、Wilcoxon p、置换检验 p、Cohen's d 与显著性结论；「打开输出文件夹」按钮跨平台打开结果目录（`os.startfile` / `open` / `xdg-open`）
- 实验失败（目录结构不对、语料为空、切片结果为空等）弹错误对话框说明原因，不静默崩溃
- `tests/test_experiment.py` 新增用例：`run()` 作为库函数被外部调用时返回包含全部摘要字段的结果字典且四个输出工件齐全

### v1.4.0-dev — 真实语料批量实验管线（译者风格识别）

🧪 **批量分组实验管线**
- 新增 `experiments/slice_corpus.py`：按英文单词数把长文本切成定长切片（默认 2000 词，`--chunk-size` 可配），不足 0.5×chunk-size 的尾片丢弃、≥0.5 的保留；分词与 `core/stylometry.py` 保持一致（正则 `[A-Za-z]+`），但在原文本上下刀以保留标点与空白；输出命名 `{原文件名}__chunkNNN.txt` 并镜像原目录结构
- 新增 `experiments/run_experiment.py`：输入目录的每个一级子目录即一个组（组名自动识别，不硬编码），对全部切片跑 Burrows' Delta（复用 `core/stylometry.py`）输出 `delta_matrix.csv` 与 `dendrogram.png`（复用 `viz/dendrogram.py`），并计算组内/组间平均 Delta 的差值与比值
- 语言指纹两两相似度（复用 `core/linguistic_fingerprint.py`，不改其签名）：同译者对与跨译者对分组后跑 Wilcoxon 符号秩检验（按切片构造配对差值）+ 置换检验（默认 10000 次）+ Cohen's d，明细写入 `fingerprint_pairs.csv`
- 汇总输出 `report.md`：样本数、组内/组间 Delta 统计、检验 p 值与效应量、树状图引用，以及模板化自动生成的中文结论段
- 新增 `tests/test_experiment.py`：覆盖切片词数、尾片取舍规则、目录结构镜像、全流程跑通（先切片再实验，贴近真实用法）及"同组 Delta < 跨组 Delta"断言，兼容 `python run_tests.py`；无 matplotlib 环境下全流程用例自动跳过

🐞 **稳定性修复**
- `experiments/sample_corpus` 重新生成（`_generate.py` v2）：v1 让填充词频率跨文本严格一致（z-score 零方差剔除），整篇跑信号极强，但切片破坏该一致性后噪声被 z-score 放大、组间分离消失；v2 改为按 1000 词块独立生成，虚词从带组偏差的加权分布抽样（每组 8 个偏好虚词 4 倍加权），组偏差稳定作用于每块、噪声块间独立，整篇 / 1000 词 / 2000 词切片三种尺度下组内 Delta 均稳定小于跨组（比值 ≈1.2–1.26）且聚类正确
- `run_experiment.py` 报告新增 sanity check：cross/within Delta 比值 ≤1.1（含倒挂）时在 `report.md` 输出醒目警告，提示勿将阴性 Delta 误读为"无译者风格"
- `run_experiment.py` 统计细节修正：Cohen's d 输入改用样本标准差（n−1，与其合并方差公式约定一致）；显著性判定由「任一检验 p<0.05」改为「两项检验均 p<0.05」（取 max，与 `core/linguistic_fingerprint.py` 的保守风格一致），避免多重比较假阳性
- `run_experiment.py` 新增 `--lang`（en/zh，默认 en）指定指纹特征语言；输入根目录下散落的 .txt 会被警告并忽略（样本必须位于组子目录中）；`slice_corpus.py` 校验 `--chunk-size` 为正整数

### v1.3.0-dev — Burrows' Delta 文体计量（译者风格识别）

📏 **Burrows' Delta 文体计量**
- 新增 `core/stylometry.py`：英文分词、高频特征词相对频率表、z 分数标准化、两两 Delta 距离矩阵，全部为纯 Python 实现（无 scipy/pandas）
- 自实现平均联结（average-linkage）凝聚式层次聚类
- 新增 `viz/dendrogram.py`：matplotlib 手绘树状图，300 dpi 导出 PNG
- 新增命令行入口 `experiments/run_delta.py`（`--input/--top-n/--out`），输出 `delta_matrix.csv` 与 `dendrogram.png`
- 新增 `experiments/sample_corpus/` 4 篇合成英文语料（两篇抬高 "the"、两篇抬高 "of"）供冒烟测试
- 新增 `tests/test_stylometry.py` 单元测试，兼容 `python run_tests.py`

🐞 **稳定性修复**
- 修复 `core/analyzer.py::_get_spacy`：spaCy 库或模型缺失时 `model` 变量未赋值，警告日志自身抛 `UnboundLocalError`，导致英文分词 / 基础统计 / KWIC 的降级路径整体崩溃（4 个既有测试因此失败）；现在只警告并按约定回退（正则分词 / 返回空结果）
- 新增 `tests/test_spacy_fallback.py`：分别模拟「spaCy 包未安装」（import 抛 `ImportError`）与「已装但模型缺失」（`load` 抛 `OSError`）两种场景，覆盖 `tokenize_en`、`analyze_basic`、KWIC 的降级路径，不安装 en_core_web_sm 也能通过
- 冒烟语料重新生成：同组两篇不再完全相同——四篇共享同一填充词多重集，组内通过「目标虚词 ↔ 配套虚词」配比微调（the/a、of/in）制造频率偏移，组内 Delta > 0 但仍远小于跨组，聚类分组不变；`tests/test_stylometry.py` 同步新增"非 identical 同组仍聚为一枝"用例
- 树状图固定文案英文化：标题 "Burrows' Delta Hierarchical Clustering"、横轴 "Merge distance (Burrows' Delta)"，输出可直接用于英文学术投稿，且避免无中文字体环境乱码（叶子标签仍取文件名）

---

### v1.2.0 — 语言学研究工作台：异步分析、批量处理、导出与测试

🧰 **工程化与稳定性**
- 所有耗时分析改为后台线程 + 进度对话框，界面不再卡死
- 新增统一日志系统，写入 `_data/app.log`
- 新增 11 个单元测试，可直接 `python run_tests.py` 运行
- 修复主题切换后 header 背景丢失、路径依赖 `os.getcwd()` 等 bug

📤 **导出功能**
- 基础分析、句法/语义、可读性、中英对齐、语言指纹、批量结果、KWIC 均支持导出 TXT / CSV / JSON / DOCX

📁 **批量处理**
- 新增「批量处理」标签页，可一次分析多个文件并导出聚合报告

🔍 **KWIC 共现分析**
- 基础分析页新增关键词上下文（KWIC）检索，支持正则与窗口大小

📝 **依存句法文字化**
- 句法/语义页改为文字列表；可视化页保留图片树图

---

###  v1.1 — 语法依存可视化修复与其他若干bug修复

🌲 **依存句法树重构**
- 从左到右 Reingold-Tilford 树布局，取代旧版弧形图
- 依存关系按语义大类着色（主/谓/宾/修饰一目了然）
- 中英文模型 CJK 智能切换
