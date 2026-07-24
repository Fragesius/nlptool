"""可选的在线 API 后端（高级分析）。

支持任意 OpenAI 兼容的 Chat Completions 接口。配置保存在 ``_data/api_config.json``。
未配置时返回提示，不影响本地分析。
"""

from __future__ import annotations

import json
import os
from typing import Optional

from core._paths import API_CONFIG_PATH, ensure_data_dirs

CONFIG_PATH = API_CONFIG_PATH


def load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_config(cfg: dict) -> None:
    ensure_data_dirs()
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def is_configured() -> bool:
    cfg = load_config()
    return bool(cfg.get("api_key") and cfg.get("base_url") and cfg.get("model"))


def advanced_analysis(text: str, task: str = "综合分析", lang: Optional[str] = None) -> str:
    """调用在线 API 执行高级分析，返回模型文本。

    task 例如："句法结构分析"、"翻译质量评估"、"文体风格分析"。
    """
    cfg = load_config()
    if not is_configured():
        return "（未配置 API。请在「设置 → API 配置」中填写 base_url / api_key / model。）"

    try:
        import requests  # type: ignore
    except ImportError:
        return "（缺少 requests 库，请 pip install requests）"

    lang_hint = lang or "自动检测"
    messages = [
        {
            "role": "system",
            "content": (
                "你是一名严谨的语言学分析助手，精通汉语与英语分析。"
                "请用简洁的中文给出结构化分析结果。"
            ),
        },
        {
            "role": "user",
            "content": f"任务：{task}\n语言：{lang_hint}\n文本：\n{text}\n\n请给出分析。",
        },
    ]

    try:
        resp = requests.post(
            f"{cfg['base_url'].rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {cfg['api_key']}",
                "Content-Type": "application/json",
            },
            json={
                "model": cfg["model"],
                "messages": messages,
                "temperature": 0.2,
            },
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"（API 调用失败：{e}）"
