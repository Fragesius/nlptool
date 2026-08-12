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

> *Built with Python, linguistics, and curiosity.* 🧠

---

## 📦 Changelog

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
