# -*- coding: utf-8 -*-
"""
Gensri.wiki（强度研究院）数据采集脚本
====================================
抓取内容：
1. 游戏机制页（伤害公式、反应系数、等级系数表） -> data/gensri/game_mechanics.json
2. 计算数据文章（manifest + 各卡片详情）           -> data/gensri/calculations.json
3. 深渊幽境（深境螺旋/幽境危战）                   -> data/gensri/abyss.json
4. 抓取元信息                                      -> data/gensri/metadata.json

用法：
    python fetch_gensri.py            # 抓取全部
    python fetch_gensri.py wiki       # 仅游戏机制
"""
import json
import re
import sys
import time
from datetime import date
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.gensri.wiki"
OUTPUT_DIR = Path(__file__).parent / "data" / "gensri"
RAW_DIR = OUTPUT_DIR / "raw"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9",
}


class GensriScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        RAW_DIR.mkdir(parents=True, exist_ok=True)

    # ---------- 基础工具 ----------
    def _get(self, path: str):
        url = path if path.startswith("http") else f"{BASE_URL}/{path.lstrip('/')}"
        for attempt in range(3):
            try:
                resp = self.session.get(url, timeout=30)
                resp.raise_for_status()
                resp.encoding = resp.apparent_encoding or "utf-8"
                return resp.text
            except requests.RequestException as exc:
                print(f"[warn] {url} 第{attempt + 1}次请求失败: {exc}")
                time.sleep(2 * (attempt + 1))
        print(f"[error] 放弃抓取 {url}")
        return None

    @staticmethod
    def _clean_text(text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()

    def _save(self, name: str, payload) -> Path:
        path = OUTPUT_DIR / name
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"[ok] 已写入 {path.relative_to(Path(__file__).parent)}")
        return path

    @staticmethod
    def _table_rows(table) -> list:
        rows = []
        for tr in table.find_all("tr"):
            cells = [GensriScraper._clean_text(td.get_text()) for td in tr.find_all("td")]
            if any(cells):
                rows.append(cells)
        return rows

    def _extract_sections(self, soup: BeautifulSoup) -> dict:
        """按标题(h2/h3/h4)切分正文，收集文本与表格"""
        sections, current = {}, "_preamble"
        body = soup.body or soup
        for node in body.descendants:
            name = getattr(node, "name", None)
            if name in ("h2", "h3", "h4"):
                title = self._clean_text(node.get_text())
                if title:
                    current = title
                    sections.setdefault(current, {"text": "", "tables": []})
            elif name == "table":
                rows = self._table_rows(node)
                if rows:
                    sections.setdefault(current, {"text": "", "tables": []})
                    sections[current]["tables"].append(rows)
            elif name in ("p", "li"):
                txt = self._clean_text(node.get_text(" ", strip=True))
                if txt and len(txt) < 400:
                    sections.setdefault(current, {"text": "", "tables": []})
                    if txt not in sections[current]["text"]:
                        sep = "；" if sections[current]["text"] else ""
                        sections[current]["text"] += sep + txt
        return sections

    def _parse_level_coefficients(self, tables) -> dict:
        """从附录表格解析 角色等级系数 表（每行两对 等级/系数）"""
        result = {}
        for tb in tables:
            flat_headers = "".join(tb.get("headers", []))
            if "角色等级系数" not in flat_headers:
                continue
            for row in tb["rows"]:
                nums = [c for c in row if c]
                for i in range(0, len(nums) - 1, 2):
                    try:
                        result[str(int(float(nums[i])))] = float(nums[i + 1])
                    except ValueError:
                        pass
        return result

    # ---------- 1. 游戏机制 ----------
    def fetch_game_mechanics(self):
        html = self._get("/wiki/")
        if html is None:
            return None
        (RAW_DIR / "wiki.html").write_text(html, encoding="utf-8")
        soup = BeautifulSoup(html, "html.parser")

        tables = []
        for idx, table in enumerate(soup.find_all("table")):
            headers = [self._clean_text(th.get_text()) for th in table.find_all("th")]
            rows = self._table_rows(table)
            if rows or headers:
                tables.append({"index": idx, "headers": headers, "rows": rows})

        full_text = self._clean_text(soup.get_text(" ", strip=True))
        weight_match = re.search(
            r"第1贡献伤害\s*×\s*([\d.]+)\s*\+\s*第2贡献伤害\s*×\s*([\d.]+)"
            r"\s*\+\s*第3贡献伤害\s*×\s*([\d.]+)\s*\+\s*第4贡献伤害\s*×\s*([\d.]+)",
            full_text,
        )
        lunar_weights = (
            [float(weight_match.group(i)) for i in range(1, 5)]
            if weight_match else None
        )

        payload = {
            "source": "gensri.wiki",
            "url": f"{BASE_URL}/wiki/",
            "fetch_date": date.today().isoformat(),
            "formulas": {
                "normal_damage": {
                    "description": "普通直伤（非月/星类技能）",
                    "formula": "基础乘区 × 增伤乘区 × 暴击乘区 × 抗性乘区 × 防御乘区",
                },
                "amplifying_reaction": {
                    "description": "增幅反应（蒸发/融化）",
                    "formula": "基础乘区 × 反应系数 × 增幅精通乘区 × 增伤乘区 × 暴击乘区 × 抗性乘区 × 防御乘区",
                    "coefficients": {
                        "melt_pyro_on_cryo_火打冰": 2.0,
                        "melt_cryo_on_pyro_冰打火": 1.5,
                        "vaporize_hydro_on_pyro_水打火": 2.0,
                        "vaporize_pyro_on_hydro_火打水": 1.5,
                    },
                },
                "quicken_reaction": {
                    "description": "激化反应",
                    "formula": "(基础乘区 + 角色等级系数×反应系数×激化精通乘区) × 增伤乘区 × 暴击乘区 × 抗性乘区 × 防御乘区",
                    "coefficients": {"aggravate_超激化": 1.15, "spread_蔓激化": 1.25},
                },
                "transformative_reaction": {
                    "description": "剧变伤害（V5.2.0 增强后系数）",
                    "formula": "(角色等级系数 × 反应系数 × 剧变精通乘区 + 数值提升) × 暴击乘区 × 抗性乘区",
                    "note": "剧变不经过防御乘区；一般不暴击，特殊效果按效果数值暴击",
                },
                "lunar_reaction": {
                    "description": "月曜反应（多角色贡献加权）",
                    "formula": "每名角色贡献 = (角色等级系数 × 反应系数 × 基础提升 × 月曜精通乘区 + 数值提升) × 暴击乘区 × 抗性乘区 × (1+擢升)",
                    "contribution_weights": lunar_weights,
                    "coefficients": {"lunar_charged_月感电": 3.0, "lunar_crystallize_月结晶": 1.6},
                    "note": "前玉衡杯提供的反应系数以及贡献权重有误，以此处为准",
                },
                "lunar_direct": {
                    "description": "月曜直伤（技能造成）",
                    "moon_multipliers": {"月感电": 3.0, "月结晶": 1.6, "月绽放": 1.0},
                },
            },
            "sections": self._extract_sections(soup),
            "tables": tables,
            "level_coefficients": self._parse_level_coefficients(tables),
        }
        return self._save("game_mechanics.json", payload)

    # ---------- 2. 计算数据文章 ----------
    def fetch_calculations(self):
        manifest_raw = self._get("/data/manifest.json")
        if manifest_raw is None:
            return None
        try:
            manifest = json.loads(manifest_raw)
        except json.JSONDecodeError:
            print("[error] manifest.json 解析失败")
            return None

        cards = []
        for card in manifest.get("cards", []):
            link = card.get("link", "")
            detail_html = self._get(f"/data/{link}") if link else None
            detail_text = ""
            if detail_html:
                soup = BeautifulSoup(detail_html, "html.parser")
                for tag in soup(["script", "style", "nav", "header", "footer"]):
                    tag.decompose()
                detail_text = self._clean_text(soup.get_text(" ", strip=True))[:5000]
            cards.append({
                "id": card.get("id"),
                "version": card.get("version"),
                "title": card.get("title"),
                "sub_version": card.get("subVersion"),
                "date": card.get("date"),
                "link": link,
                "url": f"{BASE_URL}/data/{link}" if link else None,
                "content_preview": detail_text,
            })

        payload = {
            "source": "gensri.wiki",
            "url": f"{BASE_URL}/data/",
            "fetch_date": date.today().isoformat(),
            "current_test_version": manifest.get("currentTestVersion"),
            "versions": manifest.get("versions", []),
            "articles": cards,
        }
        return self._save("calculations.json", payload)

    # ---------- 3. 深渊幽境 ----------
    def fetch_abyss(self):
        html = self._get("/985/")
        if html is None:
            return None
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer"]):
            tag.decompose()
        text = self._clean_text(soup.get_text(" ", strip=True))

        # 解析期次信息：形如 V7.0 星芒之役 ... 2026/8/19 - 2026/9/30
        seasons = []
        for m in re.finditer(
                r"(V[\d.]+)\s+([\u4e00-\u9fa5]{2,10})\s+(?:加载中\s*)?"
                r"(\d{4}/\d{1,2}/\d{1,2})\s*-\s*(\d{4}/\d{1,2}/\d{1,2})",
                text):
            seasons.append({
                "version": m.group(1),
                "name": self._clean_text(m.group(2)),
                "start": m.group(3),
                "end": m.group(4),
            })

        payload = {
            "source": "gensri.wiki",
            "url": f"{BASE_URL}/985/",
            "fetch_date": date.today().isoformat(),
            "page_text": text[:4000],
            "spiral_abyss_seasons": seasons,
            "note": "当期祝福等动态内容需浏览器渲染，此处为静态可解析部分",
        }
        return self._save("abyss.json", payload)

    # ---------- 主流程 ----------
    def fetch_all(self) -> dict:
        results = {}
        results["game_mechanics"] = bool(self.fetch_game_mechanics())
        time.sleep(1)
        results["calculations"] = bool(self.fetch_calculations())
        time.sleep(1)
        results["abyss"] = bool(self.fetch_abyss())
        self._save("metadata.json", {
            "source": "gensri.wiki",
            "base_url": BASE_URL,
            "fetch_date": date.today().isoformat(),
            "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "results": results,
            "targets": {
                "game_mechanics": "/wiki/",
                "calculations": "/data/ (manifest.json + 卡片详情)",
                "abyss": "/985/",
            },
        })
        return results


if __name__ == "__main__":
    scraper = GensriScraper()
    only = sys.argv[1] if len(sys.argv) > 1 else "all"
    if only == "wiki":
        ok = bool(scraper.fetch_game_mechanics())
    elif only == "data":
        ok = bool(scraper.fetch_calculations())
    elif only == "abyss":
        ok = bool(scraper.fetch_abyss())
    else:
        ok = all(scraper.fetch_all().values())
    sys.exit(0 if ok else 1)
