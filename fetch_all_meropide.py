# -*- coding: utf-8 -*-
"""
fetch_all_meropide.py — 全量抓取“梅洛彼得堡信息处理中心”(meropide) 公开数据。

数据流：
    sitemap-index.xml -> sitemap-0.xml -> 按 CHS 路径分类 ->
    逐页抓取(requests) -> BeautifulSoup 解析 -> 结构化 JSON -> data/meropide/

输出文件（data/meropide/）：
    characters_meropide_full.json   # 所有角色完整数据
    weapons_meropide_full.json      # 所有武器完整数据
    artifacts_meropide_full.json    # 所有圣遗物完整数据
    domains_meropide.json           # 幽境危战(stygian) 数据
    formulas_meropide_full.json     # 速查/reference（含伤害公式）
    theorycraft_meropide.json       # 角色研究(theorycraft 子页)
    metadata.json                   # 爬取元信息

增量更新：_fetch_cache.json 记录 url -> {fetch_date, last_modified, fingerprint}，
再次运行时内容哈希一致则跳过；支持 --limit / --groups / --max-runtime 断点续传。
"""
import argparse
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests
from bs4 import BeautifulSoup

BASE = "https://meropide.com"
SITEMAP_INDEX = f"{BASE}/sitemap-index.xml"
OUT_DIR = Path(__file__).parent / "data" / "meropide"
CACHE_FILE = OUT_DIR / "_fetch_cache.json"
HEADERS = {"User-Agent": "GenshinCalculator-data-sync/1.0 (+local project)"}

GROUP_RULES = [
    ("characters", "/chs/characters/", "characters_meropide_full.json"),
    ("weapons", "/chs/weapons/", "weapons_meropide_full.json"),
    ("artifacts", "/chs/artifacts/", "artifacts_meropide_full.json"),
    ("stygian", "/chs/stygian/", "domains_meropide.json"),
    ("reference", "/chs/reference/", "formulas_meropide_full.json"),
]


def load_sitemap_urls() -> list:
    """sitemap-index -> 子 sitemap，返回全部 CHS URL。"""
    sess = requests.Session()
    sess.headers.update(HEADERS)
    index = sess.get(SITEMAP_INDEX, timeout=30)
    index.raise_for_status()
    urls = []
    for sub in re.findall(r"<loc>(.*?)</loc>", index.text):
        r = sess.get(sub, timeout=60)
        r.raise_for_status()
        urls.extend(re.findall(r"<loc>(.*?)</loc>", r.text))
    return [u for u in urls if "/chs/" in u]


def classify(urls: list) -> dict:
    """按分组归类；返回 组名 -> {url: {slug, sub}}。"""
    groups = {name: {} for name, _, _ in GROUP_RULES}
    for u in sorted(urls):
        path = urlparse(u).path
        for name, prefix, _ in GROUP_RULES:
            if not path.startswith(prefix):
                continue
            rest = path[len(prefix):].strip("/")
            if not rest:
                continue  # 列表页本身
            slug = unquote(rest.split("/")[0])
            sub = rest.split("/")[1] if "/" in rest.strip("/") else ""
            groups[name][u] = {"slug": slug, "sub": sub}
            break
    return groups


# ---- 解析工具 ----

def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def table_to_rows(table) -> list:
    rows = []
    for tr in table.find_all("tr"):
        cells = [_clean(c.get_text(" ", strip=True)) for c in tr.find_all(["th", "td"])]
        if cells:
            rows.append(cells)
    return rows


def kv_table(table) -> dict:
    out = {}
    for row in table_to_rows(table):
        if len(row) >= 2 and row[0]:
            out[row[0]] = row[1]
    return out


def sections_by_level(soup) -> dict:
    """{'h1'..'h4': [(标题, 该节文本)...]}，节文本含到下一同级标题前的内容。"""
    main = soup.find("main") or soup.body or soup
    result = {"h1": [], "h2": [], "h3": [], "h4": []}
    for el in main.find_all(["h1", "h2", "h3", "h4"]):
        parts = []
        for sib in el.next_siblings:
            name = getattr(sib, "name", None)
            if name in ("h1", "h2", "h3", "h4"):
                break
            if name == "table":
                for row in table_to_rows(sib):
                    parts.append(" | ".join(row))
                continue
            txt = sib.get_text(" ", strip=True) if hasattr(sib, "get_text") else str(sib)
            parts.append(txt)
        result[el.name].append((_clean(el.get_text(strip=True)), _clean(" ".join(parts))))
    return result


def page_common(soup, url: str) -> dict:
    secs = sections_by_level(soup)
    return {
        "source": "meropide",
        "fetch_date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "url": url,
        "title": _clean(soup.title.get_text()) if soup.title else "",
        "h1": secs["h1"][0][0] if secs["h1"] else "",
    }


# ---- 各类型页面解析 ----

def parse_character(url: str, html: str, sub: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    rec = page_common(soup, url)
    secs = sections_by_level(soup)
    tables = soup.find_all("table")

    if sub == "theorycraft":
        rec["type"] = "character_theorycraft"
        rec["character"] = unquote(url.rstrip("/").split("/")[-2])
        rec["sections_h2"] = secs["h2"]
        rec["sections_h3"] = secs["h3"]
        rec["tables"] = [table_to_rows(t) for t in tables]
        return rec

    rec["type"] = "character"
    rec["name_cn"] = rec["h1"]
    # 基础信息表（称号/元素/武器类型/突破属性...）
    for t in tables:
        kv = kv_table(t)
        if ("元素" in kv or "称号" in kv) and not rec.get("basic_info"):
            rec["basic_info"] = kv
    # 天赋倍率表：前几个含倍率数值的两列表
    talent_tables = []
    for t in tables[:3]:
        rows = table_to_rows(t)
        if rows and any("%" in c or "冷却" in c for r in rows for c in r):
            talent_tables.append(rows)
    # 位于第一个 h2 之前的 h3 为天赋名（普攻/E/Q）
    talents = []
    first_h2_pair = secs["h2"][0] if secs["h2"] else None
    for pair in secs["h3"]:
        if first_h2_pair and pair == first_h2_pair:
            break
        entry = {"name": pair[0]}
        if len(talents) < len(talent_tables):
            entry["multipliers"] = talent_tables[len(talents)]
        talents.append(entry)
        if len(talents) >= 3:
            break
    rec["talents"] = talents
    rec["passives_text"] = next((d for t, d in secs["h2"] if "固有天赋" in t), "")
    rec["constellations_title"] = next((t for t, d in secs["h2"] if "命之座" in t), "")
    rec["constellations"] = [{"name": n, "desc": d} for n, d in secs["h4"]]
    rec["growth_rows"] = next((table_to_rows(t) for t in tables
                               if table_to_rows(t) and table_to_rows(t)[0]
                               and table_to_rows(t)[0][0] == "等级"), [])
    rec["mechanics"] = next((d for t, d in secs["h2"] if t == "机制"), "")
    rec["tips"] = next((d for t, d in secs["h2"] if t == "技巧"), "")
    return rec


def parse_weapon(url: str, html: str, sub: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    rec = page_common(soup, url)
    rec["type"] = "weapon"
    rec["name_cn"] = rec["h1"]
    tables = soup.find_all("table")
    if tables:
        rec["basic_info"] = kv_table(tables[0])
    secs = sections_by_level(soup)
    # 第一个 h2 为被动效果别名（如「昭理的鸢之枪」），其后文本为精炼效果描述
    if secs["h2"]:
        rec["passive_name"], rec["passive_effect_text"] = secs["h2"][0]
    rec["ascension_materials"] = next((d for t, d in secs["h2"] if "突破材料" in t), "")
    return rec


def parse_artifact(url: str, html: str, sub: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    rec = page_common(soup, url)
    rec["type"] = "artifact"
    rec["set_name"] = rec["h1"]
    tables = soup.find_all("table")
    if tables:
        rec["basic_info"] = kv_table(tables[0])
    secs = sections_by_level(soup)
    for t, d in secs["h2"]:
        if "2件套" in t:
            rec["set_2_effect"] = f"{t}：{d}"
        elif "4件套" in t:
            rec["set_4_effect"] = f"{t}：{d}"
    return rec


def parse_stygian(url: str, html: str, sub: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    rec = page_common(soup, url)
    rec["type"] = "stygian"
    rec["name_cn"] = rec["h1"]
    secs = sections_by_level(soup)
    rec["sections"] = {t: d for t, d in secs["h2"]}
    rec["tables"] = [table_to_rows(t) for t in soup.find_all("table")]
    return rec


def parse_reference(url: str, html: str, sub: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    rec = page_common(soup, url)
    rec["type"] = "reference"
    rec["topic"] = rec["h1"]
    secs = sections_by_level(soup)
    rec["sections"] = {t: d for t, d in secs["h2"]}
    rec["sub_sections"] = {t: d for t, d in secs["h3"]}
    rec["tables"] = [table_to_rows(t) for t in soup.find_all("table")]
    # KaTeX 渲染输出的 MathML 中带 <annotation encoding="application/x-tex">，
    # 可直接还原 LaTeX 公式源码；退化方案为抓取 $...$ 文本。
    annotations = re.findall(
        r'<annotation[^>]*encoding="application/x-tex"[^>]*>(.*?)</annotation>',
        html, re.S)
    if not annotations:
        annotations = re.findall(r"\$\$?(.+?)\$\$?", html)
    rec["formulas_raw"] = [_clean(f) for f in annotations][:400]
    return rec


PARSERS = {
    "characters": parse_character,
    "weapons": parse_weapon,
    "artifacts": parse_artifact,
    "stygian": parse_stygian,
    "reference": parse_reference,
}


# ---- 缓存与抓取主流程 ----

def load_cache() -> dict:
    if CACHE_FILE.exists():
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    return {}


def save_cache(cache: dict):
    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=1),
                          encoding="utf-8")


def content_fingerprint(html: str) -> str:
    return hashlib.sha256(html.encode("utf-8")).hexdigest()[:16]


def fetch_page(sess, url: str, cache: dict, force: bool = False):
    """返回 (payload|None, status)。status: fetched / skipped / error。

    支持条件请求（If-None-Match / If-Modified-Since）：未变更页面返回 304，
    跳过时无需下载正文。
    """
    cond = {}
    prev = cache.get(url)
    if not force and prev:
        if prev.get("etag"):
            cond["If-None-Match"] = prev["etag"]
        elif prev.get("last_modified"):
            cond["If-Modified-Since"] = prev["last_modified"]
    try:
        resp = sess.get(url, timeout=45, headers=cond)
        if resp.status_code == 304:
            return None, "skipped"
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001 —— 单页网络错误不中断整体任务
        return None, f"error: {exc}"
    html = resp.text
    fp = content_fingerprint(html)
    if not force and prev and prev.get("fingerprint") == fp \
            and not prev.get("etag"):
        return None, "skipped"
    return {"html": html,
            "last_modified": resp.headers.get("Last-Modified", ""),
            "etag": resp.headers.get("ETag", ""),
            "fingerprint": fp}, "fetched"


def main():
    ap = argparse.ArgumentParser(description="Meropide 全站数据爬取")
    ap.add_argument("--limit", type=int, default=0, help="每组最多抓取页数（0=不限）")
    ap.add_argument("--delay", type=float, default=1.0, help="请求间隔秒数")
    ap.add_argument("--max-runtime", type=int, default=0,
                    help="单次运行时间预算秒（0=不限），超时中断可续传")
    ap.add_argument("--groups", nargs="*", choices=list(PARSERS), default=None,
                    help="仅抓取指定分组")
    ap.add_argument("--force", action="store_true", help="忽略缓存强制重抓")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("[1/4] 获取 sitemap ...")
    groups = classify(load_sitemap_urls())
    wanted = args.groups or list(PARSERS)
    start_ts = time.time()
    cache = load_cache()
    results = {name: [] for name in PARSERS}
    stats = {name: {"fetched": 0, "skipped": 0, "error": 0} for name in PARSERS}
    total_pages = sum(len(groups[g]) for g in wanted)
    print(f"[2/4] 待处理页面 {total_pages} 个（组: {', '.join(wanted)}）")

    sess = requests.Session()
    sess.headers.update(HEADERS)
    out_files = {name: outfile for name, _, outfile in GROUP_RULES}

    print("[3/4] 开始抓取 ...")
    for gname in wanted:
        items = list(groups[gname].items())
        # 未缓存页面优先抓取，已缓存页面（增量校验）放后面
        items.sort(key=lambda kv: kv[0] in cache)
        if args.limit:
            items = items[:args.limit]
        parser = PARSERS[gname]
        for url, meta in items:
            if args.max_runtime and time.time() - start_ts > args.max_runtime:
                print(f"[time-budget] 达 {args.max_runtime}s 预算，中断（可续传）。")
                break
            payload, status = fetch_page(sess, url, cache, force=args.force)
            if status.startswith("error"):
                stats[gname]["error"] += 1
                print(f"  [ERR ] {unquote(url)} :: {status}")
                time.sleep(args.delay)
                continue
            if status == "skipped":
                stats[gname]["skipped"] += 1
                time.sleep(0.05)
                continue
            try:
                rec = parser(url, payload["html"], meta["sub"])
                rec["last_modified_header"] = payload["last_modified"]
                rec["version"] = payload["last_modified"] or payload["fingerprint"]
                results[gname].append(rec)
                cache[url] = {"fetch_date": rec["fetch_date"],
                              "last_modified": payload["last_modified"],
                              "etag": payload["etag"],
                              "fingerprint": payload["fingerprint"]}
                stats[gname]["fetched"] += 1
                if stats[gname]["fetched"] % 25 == 0:
                    print(f"  [{gname}] 已抓取 {stats[gname]['fetched']} ...")
                    save_cache(cache)  # 定期落盘，支持断点续传
            except Exception as exc:  # noqa: BLE001
                stats[gname]["error"] += 1
                print(f"  [PARSE-ERR] {unquote(url)} :: {exc}")
            time.sleep(args.delay)
        save_cache(cache)

    # 写出 JSON：新记录 + 未变更的旧记录合并（增量）
    print("[4/4] 写出 JSON ...")
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for gname in wanted:
        by_url = {r["url"]: r for r in results[gname]}
        old_path = OUT_DIR / out_files[gname]
        if old_path.exists():
            try:
                old_data = json.loads(old_path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                old_data = []
            old_records = old_data if isinstance(old_data, list) \
                else old_data.get("records", [])
            for old in old_records:
                by_url.setdefault(old.get("url"), old)
        records = sorted(by_url.values(), key=lambda r: r.get("url", ""))
        # 角色研究(theorycraft)子页从角色数据中分离，单独落盘
        extra_name = "theorycraft_meropide.json"
        if gname == "characters":
            main_recs = [r for r in records
                         if r.get("type") != "character_theorycraft"]
            tc_path = OUT_DIR / extra_name
            tc_by_url = {}
            if tc_path.exists():
                try:
                    tc_old = json.loads(tc_path.read_text(encoding="utf-8"))
                    for old in (tc_old if isinstance(tc_old, list)
                                else tc_old.get("records", [])):
                        tc_by_url.setdefault(old.get("url"), old)
                except Exception:  # noqa: BLE001
                    pass
            for r in records:
                if r.get("type") == "character_theorycraft":
                    tc_by_url[r["url"]] = r
            tc_records = sorted(tc_by_url.values(), key=lambda r: r.get("url", ""))
            tc_path.write_text(json.dumps({
                "source_site": BASE,
                "generated_at": now_iso,
                "count": len(tc_records),
                "records": tc_records,
            }, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"  {extra_name}: 共 {len(tc_records)} 条")
        else:
            main_recs = records
        payload_out = {
            "source_site": BASE,
            "generated_at": now_iso,
            "count": len(main_recs),
            "records": main_recs,
        }
        (OUT_DIR / out_files[gname]).write_text(
            json.dumps(payload_out, ensure_ascii=False, indent=1), encoding="utf-8")
        s = stats[gname]
        print(f"  {out_files[gname]}: 共 {len(records)} 条 "
              f"(本轮新增 {s['fetched']}, 未变跳过 {s['skipped']}, 错误 {s['error']})")

    meta = {
        "site": BASE,
        "crawl_finished_at": now_iso,
        "totals": {g: sum(s.values()) for g, s in stats.items()},
        "details": stats,
    }
    (OUT_DIR / "metadata.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False))
    print("完成。")
    return 0


if __name__ == "__main__":
    sys.exit(main())

