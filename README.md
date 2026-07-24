# 汉英 NLP 分析工具

作者：Fragesius

一个基于 Python + Tkinter 的 Windows 桌面 NLP 工具，支持汉语与英语的语言分析。
采用**混合模式**：本地 jieba / spaCy 完成基础分析，可选调用在线 API 执行高级分析。

## 功能

| 模块 | 功能 |
|------|------|
| 基础分析 | 分词、词性标注、句子切分、字符/词数统计、词频、词性分布 |
| 句法 / 语义 | 命名实体识别（NER）、关键词提取、依存句法、情感分析 |
| 对比分析 | Flesch-Kincaid 英文可读性、中文可读性、中英双语对齐 |
| 可视化 | 词云、词频柱状图、词性饼图、依存句法图、情感趋势图 |

## 安装

```bash
cd nlp_tool
pip install -r requirements.txt
python -m spacy download en_core_web_sm        # 英文模型（推荐）
python -m spacy download zh_core_web_sm        # 中文模型（可选，用于 NER/依存）
```

> 未安装的库会被自动检测并优雅降级，应用仍可运行，仅相关功能不可用。

## 运行

```bash
python main.py
```

## API 配置（可选）

菜单「设置 → API 配置」，填写任意 OpenAI 兼容接口：

- **Base URL**：例如 `https://api.openai.com/v1`
- **API Key**：你的密钥
- **模型**：例如 `gpt-4o-mini`

配置保存在 `~/.nlp_tool_api.json`。配置后可在「句法 / 语义」标签页调用 API
进行综合语言学分析、句法结构分析、文体风格分析等。

## 项目结构

```
nlp_tool/
├── main.py                # 入口
├── requirements.txt
├── core/
│   ├── analyzer.py        # 核心分析引擎（分词、词性、NER、关键词、情感）
│   ├── comparison.py      # 可读性、中英对齐
│   └── api_backend.py     # 可选在线 API
├── viz/
│   └── plots.py           # matplotlib 可视化
└── ui/
    ├── main_window.py     # 主窗口与菜单
    └── tabs.py            # 四个功能标签页
```

## 后端说明

- **中文分词**：jieba（含词性标注 `jieba.posseg`）
- **英文分析**：spaCy `en_core_web_sm`（词性、依存、NER、词形还原）
- **情感分析**：中文 SnowNLP，英文 VADER（nltk）；缺失时回退到内置词典
- **可视化**：matplotlib + wordcloud，已处理中文字体
