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
- 依存句法分析 & 可视化 （此处排版有问题，下个版本解决）
- 情感分析（中文 SnowNLP + 英文 VADER）

### 🕵️ 语言指纹（Authorship Attribution）
- 8 维度加权余弦相似度：虚词频率(0.30)、标点模式(0.15)、词 bigram(0.15)、词长(0.10)、句长(0.10)、TTR(0.10)、字 4-gram(0.05)、Hapax(0.05)
- Wilcoxon 符号秩检验 + 置换检验(10k) + Cohen's d 效应量
- 多作者对比判定 + 报告生成

### 📊 可视化
- 词云、词频柱状图、词性饼图、依存句法树 （此处排版有问题，下个版本解决）
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
│   ├── linguistic_fingerprint.py   # 语言指纹/作者识别引擎
│   ├── comparison.py               # 可读性、中英对齐
│   ├── api_backend.py              # 在线 API 后端
│   ├── file_io.py                  # 文件读写
│   ├── history.py                  # 分析历史
│   └── _paths.py                   # 路径管理
├── viz/
│   └── plots.py                    # matplotlib 图表
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
