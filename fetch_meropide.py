"""
梅洛彼得堡信息处理中心 (meropide.cn) 数据采集脚本
====================================================
采集目标：
  - 角色数据   chs/characters/<名>/          -> data/meropide/characters_meropide.json
  - 武器数据   chs/weapons/<名>/             -> data/meropide/weapons_meropide.json
  - 圣遗物数据 chs/artifacts/<名>/           -> data/meropide/artifacts_meropide.json
  - 公式与机制 chs/reference/*, theorycraft  -> data/meropide/formulas.json

用法：
  python fetch_meropide.py                # 全量采集（带本地HTML缓存，重复运行只增量）
  python fetch_meropide.py --refresh      # 忽略缓存强制重新抓取
  python fetch_meropide.py --parse-only   # 仅用已缓存的HTML重新解析，不发请求

注意事项：
  - 遵守 robots.txt（Allow: /），请求间隔 SLEEP_SEC=1.0 秒
  - 所有原始 HTML 缓存于 .cache/meropide/，便于离线重解析
"""
import json
import os
import re
import sys
import time
import datetime
from urllib.parse import unquote

import requests
from bs4 import BeautifulSoup

BASE = "https://meropide.com"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "meropide")
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache", "meropide")
SITEMAP_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache", "meropide_sitemap.txt")

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) GenshinCalc-research"}
SLEEP_SEC = 1.0
TIMEOUT = 25
FETCH_DATE = datetime.date.today().isoformat()

_missing_log = []


# --------------------------------------------------------------------------
# 工具函数
# --------------------------------------------------------------------------

def load_sitemap() -> list:
    """获取全站 URL 列表（优先用本地缓存）"""
    if os.path.exists(SITEMAP_CACHE):
        urls = open(SITEMAP_CACHE, encoding="utf-8").read().split("\n")
        if len(urls) > 100:
            return [u for u in urls if u]
    r = requests.get(f"{BASE}/sitemap-0.xml", headers=HEADERS, timeout=TIMEOUT)
    urls = re.findall(r"<loc>(.*?)</loc>", r.text)
    os.makedirs(os.path.dirname(SITEMAP_CACHE), exist_ok=True)
    open(SITEMAP_CACHE, "w", encoding="utf-8").write("\n".join(urls))
    return urls


def select_targets(urls: list) -> dict:
    """从 sitemap 中筛选四类目标页面（仅中文站详情页）"""
    chars = [u for u in urls
             if "/chs/characters/" in u
             and unquote(u).rstrip("/").count("/") == 5        # 排除子页 materials/stats/theorycraft
             and not unquote(u).rstrip("/").endswith("characters")]
    weapons = [u for u in urls
               if "/chs/weapons/" in u
               and unquote(u).rstrip("/").count("/") == 5
               and not unquote(u).rstrip("/").endswith("weapons")]
    artifacts = [u for u in urls
                 if "/chs/artifacts/" in u
                 and unquote(u).rstrip("/").count("/") == 5
                 and not unquote(u).rstrip("/").endswith("artifacts")]
    refs = [u for u in urls if "/chs/reference/" in u] + \
           [u for u in urls if u.rstrip("/") == f"{BASE}/chs/theorycraft"]
    return {"character": chars, "weapon": weapons, "artifact": artifacts, "reference": refs}


def cache_path(url: str) -> str:
    """URL 对应的本地缓存文件路径（MD5 键，避免中文路径冲突）"""
    import hashlib
    return os.path.join(CACHE_DIR, hashlib.md5(url.encode("utf-8")).hexdigest() + ".html")


def fetch_html(url: str, refresh: bool = False) -> str:
    """抓取页面，带本地磁盘缓存；失败重试2次。
    缓存键使用 URL 的 MD5（中文路径若转 '_' 会引发键冲突）。"""
    path = cache_path(url)
    if not refresh and os.path.exists(path) and os.path.getsize(path) > 500:
        return open(path, encoding="utf-8").read()
    last_err = None
    for attempt in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            if r.status_code == 200:
                os.makedirs(CACHE_DIR, exist_ok=True)
                open(path, "w", encoding="utf-8").write(r.text)
                time.sleep(SLEEP_SEC)
                return r.text
            last_err = f"HTTP {r.status_code}"
        except Exception as e:
            last_err = repr(e)
        time.sleep(SLEEP_SEC * 2)
    print(f"  [MISS] {unquote(url)} -> {last_err}")
    _missing_log.append({"url": url, "error": last_err})
    return ""


def clean(text: str) -> str:
    """压缩空白"""
    return re.sub(r"\s+", " ", text or "").strip()


def pct(v: str):
    """'38.4%' -> 0.384 ; 解析失败返回 None"""
    m = re.search(r"(\d+(?:\.\d+)?)\s*%", v or "")
    return round(float(m.group(1)) / 100, 6) if m else None


def num(v: str):
    """'12,858' -> 12858.0"""
    m = re.search(r"([\d,]+(?:\.\d+)?)", (v or "").replace(",", ""))
    return float(m.group(1).replace(",", "")) if m else None


def infobox(soup: BeautifulSoup) -> dict:
    """解析 aside.wiki-infobox 中的 label->value 表"""
    out = {}
    box = soup.select_one("aside.wiki-infobox")
    if not box:
        return out
    for tr in box.select("table.infobox-table tr"):
        tds = tr.find_all(["td", "th"])
        if len(tds) >= 2:
            out[clean(tds[0].get_text())] = clean(tds[1].get_text())
    return out


# --------------------------------------------------------------------------
# 角色页解析
# --------------------------------------------------------------------------

def parse_character(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1")
    name = clean(h1.get_text()) if h1 else unquote(url).rstrip("/").split("/")[-1]
    info = infobox(soup)
    box = soup.select_one("aside.wiki-infobox")
    stars = len(re.findall("★", box.get_text())) if box else None

    d = {
        "source": "meropide",
        "fetch_date": FETCH_DATE,
        "url": url,
        "name": name,
        "title": info.get("称号", "missing"),
        "element": info.get("元素", "missing"),
        "weapon_type": info.get("武器类型", "missing"),
        "rarity": stars if stars else "missing",
        "region": info.get("地区", "missing"),
        "affiliation": info.get("所属", "missing"),
        "constellation_name": info.get("命之座", "missing"),
        "birthday": info.get("生日", "missing"),
        "ascension_stat": "missing",
        "ascension_value_pct": None,
        "stats_by_level": {},
        "talents": [],
        "passive_talents": [],
        "constellations": [],
        "materials_lv90": [],
        "research_notes": "",
    }

    # 突破属性（infobox 形如 "暴击伤害 38.4%"）
    asc = info.get("突破属性", "")
    if asc:
        am = re.match(r"(.*?)([\d.]+%)\s*$", asc)
        d["ascension_stat"] = am.group(1).strip() if am else asc.strip()
        d["ascension_value_pct"] = pct(am.group(2)) if am else None

    # 面板成长表（等级/基础生命值/基础攻击力/基础防御力）
    for tw in soup.select("div.table-wrap"):
        table = tw.find("table")
        if not table:
            continue
        headers = [clean(th.get_text()) for th in table.find_all("th")]
        if "等级" in headers and any("基础" in h for h in headers):
            key_map = {"基础生命值": "hp", "基础攻击力": "atk", "基础防御力": "def"}
            for tr in table.find_all("tr"):
                tds = [clean(td.get_text()) for td in tr.find_all("td")]
                if len(tds) == len(headers) and tds:
                    row = {key_map.get(h, h): num(tds[i])
                           for i, h in enumerate(headers[1:], start=1)}
                    d["stats_by_level"][tds[0]] = row
            break

    # 定位“固有天赋”标题，用于区分主动天赋与被动天赋
    pas_h2 = next((h2 for h2 in soup.find_all("h2")
                   if "固有天赋" in h2.get_text()), None)

    # 天赋：div.skill-header(h3 名称 + span 类型) + table.skill-data-table
    # 主动天赋带 span.skill-key-label（普攻/元素战技等），被动天赋没有该标签
    for header in soup.select("div.skill-header"):
        if header.select_one("span.skill-key-label") is None:
            continue
        h3 = header.find("h3")
        label = header.select_one("span.skill-key-label")
        card = header.find_parent("div", class_="section-card") or header.parent
        sd = card.select_one("div.skill-desc") if card else None
        rows = []
        for tbl in (card.select("table.skill-data-table") if card else []):
            for tr in tbl.find_all("tr"):
                tds = tr.find_all("td")
                if len(tds) >= 2:
                    rows.append({"label": clean(tds[0].get_text()),
                                 "value_text": clean(tds[1].get_text())})
        d["talents"].append({
            "skill_name": clean(h3.get_text()) if h3 else "missing",
            "skill_type": clean(label.get_text()) if label else "missing",
            "desc": clean(sd.get_text(" ", strip=True)) if sd else "",
            "rows": rows,
        })

    # 固有天赋&突破天赋：h2 标题后连续的 skill-header/skill-desc 对
    if pas_h2 is not None:
        node = pas_h2
        while True:
            node = node.find_next()
            if node is None or node.name == "h2":
                break
            cls = node.get("class") or []
            if "skill-header" in cls:
                pname = node.find("h3")
                pdesc = node.find_next("div", class_="skill-desc")
                d["passive_talents"].append({
                    "name": clean(pname.get_text()) if pname else "missing",
                    "desc": clean(pdesc.get_text(" ", strip=True)) if pdesc else "missing",
                })

    # 命之座
    for card in soup.select("div.constellation-card"):
        lines = [l for l in card.get_text("\n", strip=True).split("\n") if l.strip()]
        head = lines[0] if lines else ""
        cm = re.search(r"第(\d+)层\s*·\s*(.+)", head)
        d["constellations"].append({
            "level": int(cm.group(1)) if cm else None,
            "name": cm.group(2).strip() if cm else head,
            "desc": clean(" ".join(lines[1:])) if len(lines) > 1 else "",
        })

    # Lv90 突破材料
    mat_root = soup.select_one("div.ascension-calc")
    if mat_root:
        d["materials_lv90"] = [
            {"item": clean(it), "count": int(ct.replace(",", ""))}
            for it, ct in re.findall(r"([\u4e00-\u9fa5A-Za-z0-9·']+?)\s*[×x]\s*([\d,]+)",
                                     mat_root.get_text())
        ]

    # 我们的研究（人工审校机制笔记）
    d["research_notes"] = "\n\n".join(
        sec.get_text("\n", strip=True) for sec in soup.select("div.research-section"))

    # 关键字段缺失检查
    for k in ("name", "element", "weapon_type"):
        if d[k] in (None, "", "missing"):
            _missing_log.append({"url": url, "field": k})
    if not d["stats_by_level"]:
        _missing_log.append({"url": url, "field": "stats_by_level"})
    return d


# --------------------------------------------------------------------------
# 武器 / 圣遗物 / 公式解析
# --------------------------------------------------------------------------

_ELEM_EN = {"火": "pyro", "水": "hydro", "冰": "cryo", "雷": "electro",
            "风": "anemo", "岩": "geo", "草": "dendro", "物理": "physical"}


def parse_weapon(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1")
    info = infobox(soup)
    box = soup.select_one("aside.wiki-infobox")
    box_txt = box.get_text() if box else ""

    # 特效文本 = 第一个非材料/非研究的 section-card
    # （部分武器特效不含百分号，如原木刀的"识种"效果，故只排除已知非特效区块）
    effect = ""
    for sc in soup.select("div.section-card"):
        t = clean(sc.get_text(" ", strip=True))
        if not t or t.startswith(("突破材料", "我们的研究")):
            continue
        if len(t) >= 10 and re.search(r"[\d%触发提升降低获得恢复]", t):
            effect = t
            break

    materials = []
    mat_root = soup.select_one("div.ascension-calc")
    if mat_root:
        materials = [
            {"item": clean(it), "count": int(ct.replace(",", ""))}
            for it, ct in re.findall(r"([\u4e00-\u9fa5A-Za-z0-9·']+?)\s*[×x]\s*([\d,]+)",
                                     mat_root.get_text())
        ]

    sub = info.get("副属性", "")
    sm = re.match(r"(.+?)\s*([\d.]+%?)$", sub)

    d = {
        "source": "meropide",
        "fetch_date": FETCH_DATE,
        "url": url,
        "name": clean(h1.get_text()) if h1 else "missing",
        "weapon_type": info.get("武器类型", "missing"),
        "base_atk": num(info.get("基础攻击", "")),
        "substat_name": sm.group(1).strip() if sm else (sub or "missing"),
        "substat_value_text": sm.group(2) if sm else "",
        "rarity": len(re.findall("★", box_txt)) or None,
        "source_desc": info.get("来源", "missing"),
        "passive_effect_text": effect,
        "materials": materials,
    }
    if d["name"] == "missing" or d["base_atk"] is None:
        _missing_log.append({"url": url, "field": "name/base_atk"})
    return d


def parse_artifact(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1")
    info = infobox(soup)

    eff2, eff4 = "", ""
    for sc in soup.select("div.section-card"):
        t = clean(sc.get_text(" ", strip=True))
        if t.startswith("2件套效果"):
            eff2 = t[len("2件套效果"):].strip()
        elif t.startswith("4件套效果"):
            eff4 = t[len("4件套效果"):].strip()

    # 结构化尝试：2件套形如 "获得15%雷元素伤害加成"
    structured = {"set_2": None, "set_4": None}
    m2 = re.search(r"获得(\d+(?:\.\d+)?)%(.+?)元素伤害加成", eff2)
    if m2:
        elem = m2.group(2)
        structured["set_2"] = {
            "stat": f"{_ELEM_EN.get(elem, elem)}_dmg_bonus",
            "value": float(m2.group(1)) / 100,
            "element": _ELEM_EN.get(elem, elem),
        }

    max_r = num(info.get("最高稀有度", ""))
    d = {
        "source": "meropide",
        "fetch_date": FETCH_DATE,
        "url": url,
        "set_name": clean(h1.get_text()) if h1 else "missing",
        "max_rarity": int(max_r) if max_r else None,
        "possible_rarity_text": info.get("可能稀有度", "missing"),
        "set_2_effect": eff2,
        "set_4_effect": eff4,
        "structured_effects": structured,
    }
    if d["set_name"] == "missing" or not eff2:
        _missing_log.append({"url": url, "field": "set_name/set_2_effect"})
    return d


def parse_reference(html: str, url: str) -> dict:
    """公式/机制文档：保存清洗正文 + 全部表格结构化行"""
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main") or soup
    h1 = soup.find("h1")
    title = clean(h1.get_text()) if h1 else unquote(url).rstrip("/").split("/")[-1]

    # 先提取 KaTeX 内嵌的 LaTeX 源码（<annotation encoding="application/x-tex">）
    latex = [clean(a.get_text()) for a in main.select("annotation")]

    tables = []
    for tbl in main.find_all("table"):
        rows = []
        for tr in tbl.find_all("tr"):
            cells = [clean(td.get_text()) for td in tr.find_all(["td", "th"])]
            if any(cells):
                rows.append(cells)
        if rows:
            tables.append(rows)

    # 清洗：去掉 KaTeX 重复渲染块与脚本样式，保留可读正文
    for kat in main.select(".katex, script, style"):
        kat.decompose()
    body = main.get_text("\n", strip=True)

    return {
        "source": "meropide",
        "fetch_date": FETCH_DATE,
        "url": url,
        "title": title,
        "tables": tables,
        "latex": latex,
        "content": body,
    }


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------

PARSERS = {
    "character": parse_character,
    "weapon": parse_weapon,
    "artifact": parse_artifact,
    "reference": parse_reference,
}
OUT_FILES = {
    "character": "characters_meropide.json",
    "weapon": "weapons_meropide.json",
    "artifact": "artifacts_meropide.json",
    "reference": "formulas.json",
}


def crawl(kind: str, urls: list, refresh: bool) -> list:
    parser = PARSERS[kind]
    results = []
    for i, u in enumerate(urls, 1):
        html = fetch_html(u, refresh=refresh)
        tail = unquote(u).rstrip("/").split("/")[-1]
        print(f"  [{kind} {i}/{len(urls)}] {tail}")
        if not html:
            continue
        try:
            results.append(parser(html, u))
        except Exception as e:
            print(f"    [PARSE ERR] {e!r}")
            _missing_log.append({"url": u, "error": f"parse: {e!r}"})
    return results


def main():
    refresh = "--refresh" in sys.argv
    parse_only = "--parse-only" in sys.argv
    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(CACHE_DIR, exist_ok=True)

    print("[1/3] 加载 sitemap ...")
    targets = select_targets(load_sitemap())
    for k, v in targets.items():
        print(f"  {k}: {len(v)} 页")

    print("[2/3] 抓取 + 解析 ..." + ("（仅解析本地缓存，不发请求）" if parse_only else ""))
    all_data = {}
    for kind, urls in targets.items():
        if parse_only:
            results = []
            for u in urls:
                p = cache_path(u)
                if os.path.exists(p):
                    try:
                        results.append(PARSERS[kind](open(p, encoding="utf-8").read(), u))
                    except Exception as e:
                        print(f"  [PARSE ERR] {unquote(u)}: {e!r}")
                else:
                    _missing_log.append({"url": u, "error": "no cached html"})
            all_data[kind] = results
        else:
            all_data[kind] = crawl(kind, urls, refresh)
        print(f"  -> {kind}: 解析成功 {len(all_data[kind])}/{len(urls)}")

    print("[3/3] 写出 JSON ...")
    summary = {}
    for kind, data in all_data.items():
        payload = {
            "source": "meropide",
            "fetch_date": FETCH_DATE,
            "site": BASE,
            "robots": "https://meropide.cn/robots.txt (User-agent: * / Allow: /)",
            "count": len(data),
            "items": data,
        }
        out = os.path.join(OUT_DIR, OUT_FILES[kind])
        with open(out, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        summary[OUT_FILES[kind]] = len(data)
        print(f"  已保存 {out} ({len(data)} 条)")

    miss_path = os.path.join(OUT_DIR, "_missing_log.json")
    with open(miss_path, "w", encoding="utf-8") as f:
        json.dump({"fetch_date": FETCH_DATE, "missing_count": len(_missing_log),
                   "missing": _missing_log}, f, ensure_ascii=False, indent=2)
    print(f"\n完成！缺失记录 {len(_missing_log)} 条 -> {miss_path}")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
