# -*- coding: utf-8 -*-
"""
explore_meropide.py — 梅洛彼得堡信息处理中心（meropide）网站结构探索辅助脚本。

功能：
1. 获取 sitemap（robots.txt 指引 -> sitemap-index.xml -> sitemap-0.xml）
2. 按 URL 路径模式分类统计，打印各分组数量与示例
3. 可选：抓取指定页面的标题/元数据/关键元素，帮助确定 CSS 选择器

用法：
    python explore_meropide.py                 # 仅分析 sitemap
    python explore_meropide.py <url> [...]     # 额外分析指定页面结构
"""
import re
import sys
from collections import Counter
from urllib.parse import unquote, urlparse

import requests

SITEMAP_INDEX = "https://meropide.com/sitemap-index.xml"
HEADERS = {"User-Agent": "GenshinCalculator-research/1.0 (+local data sync)"}


def get_sitemap_urls() -> list:
    """从 sitemap-index 追溯到所有子 sitemap，返回全部 URL 列表。"""
    sess = requests.Session()
    sess.headers.update(HEADERS)
    locs = []
    index = sess.get(SITEMAP_INDEX, timeout=30)
    index.raise_for_status()
    # sitemap-index -> 子 sitemap
    subs = re.findall(r"<loc>(.*?)</loc>", index.text)
    for sub_url in subs:
        r = sess.get(sub_url, timeout=60)
        r.raise_for_status()
        urls = re.findall(r"<loc>(.*?)</loc>", r.text)
        print(f"[sitemap] {sub_url}: {len(urls)} urls")
        locs.extend(urls)
    return locs


def classify(urls: list):
    """按路径模式分类统计。"""
    groups = Counter()
    samples = {}
    for u in urls:
        path = unquote(urlparse(u).path)
        parts = [p for p in path.split("/") if p]
        # 归纳模式：取前两级目录作为组名，详情页归入其列表组
        if len(parts) >= 2:
            key = "/".join(parts[:2])
        elif parts:
            key = parts[0]
        else:
            key = "(root)"
        # 子页面（如 /characters/迪卢克/stats/）单独统计深度
        if len(parts) >= 3:
            groups[f"{key}/*"] += 1
        else:
            groups[key] += 1
        samples.setdefault(key if len(parts) < 3 else f"{key}/*", u)
    return groups, samples


def explore_page(url: str):
    """打印页面标题、meta 与主要结构元素，辅助确定选择器。"""
    from bs4 import BeautifulSoup

    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    print("=" * 70)
    print(f"URL   : {url}")
    title_text = soup.title.string.strip() if soup.title and soup.title.string else "(none)"
    print(f"title : {title_text}")
    h1 = soup.find("h1")
    print(f"h1    : {h1.get_text(strip=True) if h1 else '(none)'}")
    for tag in ("table",) :
        print(f"{tag:<6}: {len(soup.find_all(tag))}")
    print(f"div   : {len(soup.find_all('div'))}, section: {len(soup.find_all('section'))}")
    # 打印主要 class 分布（前 15 个）
    cls = Counter(c for el in soup.find_all(True) for c in (el.get("class") or []))
    for name, n in cls.most_common(15):
        print(f"  .{name} x{n}")


def main():
    urls = get_sitemap_urls()
    print(f"\n[total] {len(urls)} urls\n")
    groups, samples = classify(urls)
    print(f"{'group':<28}{'count':>7}   sample")
    print("-" * 100)
    for g, n in sorted(groups.items(), key=lambda kv: -kv[1]):
        print(f"{g:<28}{n:>7}   {unquote(samples[g])[:68]}")

    for u in sys.argv[1:]:
        explore_page(u)


if __name__ == "__main__":
    main()
