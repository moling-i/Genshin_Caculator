# -*- coding: utf-8 -*-
"""
Meropide 全量数据整合脚本
========================
将 fetch_all_meropide.py 产出的全量抓取文件（*_meropide_full.json 等，
schema 为解析器原始结构）整合为 data_loader.py / app.py / 测试所依赖的
旧版 schema 文件（characters_meropide.json / weapons_meropide.json /
artifacts_meropide.json / formulas.json）。

合并策略（以新数据为准，旧数据补缺）：
  - 角色：基础信息/面板/命座/天赋倍率表 <- 新；天赋描述与类型、固有天赋、
    突破材料、研究笔记 <- 旧（新数据不含这些文本字段）。
  - 武器：面板/被动文案 <- 新；稀有度/突破材料 <- 旧。
  - 圣遗物：套装效果文本 <- 新；structured_effects <- 旧。
  - 公式：表格/章节 <- 新；content/latex <- 旧。

用法：python integrate_meropide_data.py [--dry-run]
"""
import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
MP = BASE / "data" / "meropide"

_TALENT_TYPE_BY_INDEX = ["普攻", "元素战技", "元素爆发"]


def _load(name: str):
    return json.loads((MP / name).read_text(encoding="utf-8"))


def _dump(name: str, payload) -> None:
    (MP / name).write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")


def _parse_num(text):
    """'12,650' / '352' -> float；失败返回 None。"""
    if text is None:
        return None
    m = re.search(r"-?\d[\d,]*(?:\.\d+)?", str(text).replace(",", ""))
    return float(m.group()) if m else None


def _dedupe_chars(full_records: list) -> dict:
    """主/材料/面板三个子页产出相同结构的记录，按角色名去重。"""
    by_name = {}
    for r in full_records:
        name = r.get("name_cn") or ""
        if not name:
            continue
        prev = by_name.get(name)
        if prev is None or len(json.dumps(r, ensure_ascii=False)) > \
                len(json.dumps(prev, ensure_ascii=False)):
            by_name[name] = r
    return by_name


def _stats_by_level(growth_rows) -> dict:
    """growth_rows[['等级','基础生命值',...], ['90','12,650',...]] ->
    {'90': {'hp':..,'atk':..,'def':..}, ...}"""
    if not growth_rows or len(growth_rows) < 2:
        return {}
    header = [str(c or "") for c in growth_rows[0]]
    try:
        i_lv = next(i for i, h in enumerate(header) if "等级" in h)
        i_hp = next(i for i, h in enumerate(header) if "生命" in h)
        i_atk = next(i for i, h in enumerate(header) if "攻击" in h)
        i_df = next(i for i, h in enumerate(header) if "防御" in h)
    except StopIteration:
        return {}
    out = {}
    for row in growth_rows[1:]:
        lv = str(row[i_lv]).strip()
        if not lv.isdigit():
            continue
        hp, atk, df = (_parse_num(row[i_hp]), _parse_num(row[i_atk]),
                       _parse_num(row[i_df]))
        if hp is None:
            continue
        out[lv] = {"hp": hp, "atk": atk or 0.0, "def": df or 0.0}
    return out


def merge_characters(dry: bool = False) -> int:
    old_items = {i["name"]: i
                 for i in _load("characters_meropide.json")["items"]}
    new_by_name = _dedupe_chars(
        _load("characters_meropide_full.json")["records"])

    merged, stats_updated, talents_updated = [], 0, 0
    for name in sorted(new_by_name):
        new, old = new_by_name[name], old_items.get(name, {})
        bi = new.get("basic_info") or {}
        item = dict(old)
        item.update({
            "name": name,
            "title": bi.get("称号") or old.get("title") or "",
            "element": bi.get("元素") or old.get("element") or "",
            "weapon_type": bi.get("武器类型") or old.get("weapon_type") or "",
            "region": bi.get("地区") or old.get("region") or "",
            "affiliation": bi.get("所属") or old.get("affiliation") or "",
            "birthday": bi.get("生日") or old.get("birthday") or "",
            "constellation_name":
                bi.get("命之座") or old.get("constellation_name") or "",
            "ascension_stat":
                bi.get("突破属性") or old.get("ascension_stat") or "",
            "url": new.get("url") or old.get("url") or "",
            "fetch_date":
                new.get("fetch_date") or old.get("fetch_date") or "",
            "source": "meropide",
        })
        m = re.search(r"([\d.]+)%", item["ascension_stat"])
        item["ascension_value_pct"] = float(m.group(1)) if m else \
            old.get("ascension_value_pct")

        # 面板：新 growth_rows 解析结果优先
        sbl = _stats_by_level(new.get("growth_rows"))
        if sbl:
            if sbl != old.get("stats_by_level"):
                stats_updated += 1
            item["stats_by_level"] = sbl
        elif old.get("stats_by_level"):
            item["stats_by_level"] = old["stats_by_level"]

        # 命之座：统一为旧版 {level, name, desc} 结构
        cons_new = []
        for c in new.get("constellations") or []:
            nm = c.get("name", "")
            lm = re.search(r"第(\d+)层", nm)
            cons_new.append({
                "level": int(lm.group(1)) if lm else len(cons_new) + 1,
                "name": re.sub(r"^命之座\s*第\d+层\s*·\s*", "", nm),
                "desc": c.get("desc", ""),
            })
        item["constellations"] = cons_new or old.get("constellations") or []

        # 天赋：倍率表(rows) <- 新；skill_type/desc <- 旧
        old_talents = {t.get("skill_name"): t
                       for t in old.get("talents") or []}
        talents, changed = [], False
        for idx, t in enumerate(new.get("talents") or []):
            tn = t.get("name", "")
            ot = old_talents.get(tn, {})
            rows = [{"label": pair[0], "value_text": pair[1]}
                    for pair in (t.get("multipliers") or [])
                    if isinstance(pair, (list, tuple)) and len(pair) >= 2]
            skill_type = ot.get("skill_type") or \
                (_TALENT_TYPE_BY_INDEX[idx] if idx < 3 else "")
            if rows and rows != ot.get("rows"):
                changed = True
            talents.append({
                "skill_name": tn,
                "skill_type": skill_type,
                "desc": ot.get("desc", ""),
                "rows": rows or ot.get("rows") or [],
            })
        if changed:
            talents_updated += 1
        item["talents"] = talents or old.get("talents") or []

        # 其余文本类字段保留旧值（新数据无对应结构化输出）
        for key in ("passive_talents", "materials_lv90", "research_notes",
                    "rarity", "states"):
            if key not in item and key in old:
                item[key] = old[key]
        merged.append(item)

    print(f"[characters] 合并 {len(merged)} 条 | "
          f"面板更新 {stats_updated} | 天赋更新 {talents_updated}")
    if not dry:
        _dump("characters_meropide.json", {
            "source": "meropide",
            "site": "https://meropide.com",
            "fetch_date": datetime.now(timezone.utc).date().isoformat(),
            "count": len(merged),
            "items": merged,
        })
    return len(merged)


def merge_weapons(dry: bool = False) -> int:
    old_items = {i["name"]: i
                 for i in _load("weapons_meropide.json")["items"]}
    records = _load("weapons_meropide_full.json")["records"]
    merged, updated = [], 0
    for rec in records:
        name = rec.get("name_cn") or ""
        if not name:
            continue
        bi = rec.get("basic_info") or {}
        old = old_items.get(name, {})
        substat = bi.get("副属性") or ""
        sm = re.match(r"\s*(\S+?)\s+([\d.]+%?)\s*$", substat)
        base_atk = _parse_num(bi.get("基础攻击"))
        passive = (rec.get("passive_effect_text") or "").strip()
        old_passive = (old.get("passive_effect_text") or "").strip()
        # 旧文本若为新文本的超集（如含别名首句等更完整信息），保留旧文本
        if passive and old_passive and passive in old_passive:
            passive = old_passive
        if passive and passive != old_passive:
            updated += 1
        merged.append({
            "name": name,
            "weapon_type": bi.get("武器类型")
                           or old.get("weapon_type") or "",
            "base_atk": base_atk if base_atk is not None
                        else old.get("base_atk"),
            "substat_name": sm.group(1) if sm
                            else (substat or old.get("substat_name") or ""),
            "substat_value_text": sm.group(2) if sm
                                  else old.get("substat_value_text") or "",
            "passive_name": rec.get("passive_name")
                            or old.get("passive_name") or "",
            "passive_effect_text": passive
                                   or old.get("passive_effect_text") or "",
            "rarity": old.get("rarity"),
            "materials": old.get("materials") or [],
            "source_desc": bi.get("来源") or old.get("source_desc") or "",
            "url": rec.get("url") or old.get("url") or "",
            "fetch_date": rec.get("fetch_date")
                          or old.get("fetch_date") or "",
            "source": "meropide",
        })
    merged.sort(key=lambda x: x["name"])
    print(f"[weapons] 合并 {len(merged)} 条 | 被动文案更新 {updated}")
    if not dry:
        _dump("weapons_meropide.json", {
            "source": "meropide",
            "site": "https://meropide.com",
            "fetch_date": datetime.now(timezone.utc).date().isoformat(),
            "count": len(merged),
            "items": merged,
        })
    return len(merged)


def merge_artifacts(dry: bool = False) -> int:
    old_items = {i["set_name"]: i
                 for i in _load("artifacts_meropide.json")["items"]}
    records = _load("artifacts_meropide_full.json")["records"]
    merged, updated = [], 0
    for rec in records:
        set_name = rec.get("set_name") or ""
        if not set_name:
            continue
        bi = rec.get("basic_info") or {}
        old = old_items.get(set_name, {})
        e2 = (rec.get("set_2_effect") or "").strip()
        e4 = (rec.get("set_4_effect") or "").strip()
        if (e2 or e4) and (e2 != old.get("set_2_effect")
                           or e4 != old.get("set_4_effect")):
            updated += 1
        merged.append({
            "set_name": set_name,
            "max_rarity": _parse_num(bi.get("最高稀有度"))
                          or old.get("max_rarity"),
            "possible_rarity_text": bi.get("可能稀有度")
                                    or old.get("possible_rarity_text") or "",
            "set_2_effect": e2 or old.get("set_2_effect") or "",
            "set_4_effect": e4 or old.get("set_4_effect") or "",
            "structured_effects": old.get("structured_effects") or [],
            "url": rec.get("url") or old.get("url") or "",
            "fetch_date": rec.get("fetch_date")
                          or old.get("fetch_date") or "",
            "source": "meropide",
        })
    merged.sort(key=lambda x: (-(x["max_rarity"] or 0), x["set_name"]))
    print(f"[artifacts] 合并 {len(merged)} 条 | 套装文案更新 {updated}")
    if not dry:
        _dump("artifacts_meropide.json", {
            "source": "meropide",
            "site": "https://meropide.com",
            "fetch_date": datetime.now(timezone.utc).date().isoformat(),
            "count": len(merged),
            "items": merged,
        })
    return len(merged)


def merge_formulas(dry: bool = False) -> int:
    old_items = {i.get("title"): i
                 for i in _load("formulas.json")["items"]}
    # 旧条目标题同样归一化；同名（含后缀重复）时优先保留无后缀版本
    norm_old = {}
    for t, item in old_items.items():
        base = re.sub(r"\s*\|\s*梅信心\s*$", "", t or "").strip()
        if base not in norm_old or "|" not in (t or ""):
            norm_old[base] = item
    old_items = norm_old
    records = _load("formulas_meropide_full.json")["records"]
    merged, matched = [], 0
    seen = set()
    for rec in records:
        title = rec.get("title") or ""
        if not title:
            continue
        # 新抓取标题带作者后缀（"xxx | 梅信心"），归一化为旧版标题
        title = re.sub(r"\s*\|\s*梅信心\s*$", "", title).strip()
        if title in seen:
            continue
        seen.add(title)
        old = old_items.get(title, {})
        if old:
            matched += 1
        merged.append({
            "title": title,
            "topic": rec.get("topic") or title,
            "url": rec.get("url") or old.get("url") or "",
            "tables": rec.get("tables") or old.get("tables") or [],
            "sections": rec.get("sections") or [],
            "sub_sections": rec.get("sub_sections") or [],
            "formulas_raw": rec.get("formulas_raw") or [],
            "content": old.get("content", ""),
            "latex": old.get("latex", []),
            "fetch_date": rec.get("fetch_date")
                          or old.get("fetch_date") or "",
            "source": "meropide",
        })
    # 旧文件中存在而本次未覆盖的条目原样保留
    for title, old in old_items.items():
        if title not in seen:
            merged.append(dict(old))
    merged.sort(key=lambda x: x.get("title", ""))
    print(f"[formulas] 合并 {len(merged)} 条 "
          f"(新数据匹配旧标题 {matched})")
    if not dry:
        _dump("formulas.json", {
            "source": "meropide",
            "site": "https://meropide.com",
            "fetch_date": datetime.now(timezone.utc).date().isoformat(),
            "count": len(merged),
            "items": merged,
        })
    return len(merged)


def main():
    ap = argparse.ArgumentParser(description="Meropide 数据整合")
    ap.add_argument("--dry-run", action="store_true",
                    help="只统计不写盘")
    args = ap.parse_args()
    n_chars = merge_characters(args.dry_run)
    n_weapons = merge_weapons(args.dry_run)
    n_arts = merge_artifacts(args.dry_run)
    n_forms = merge_formulas(args.dry_run)
    print(f"完成：characters={n_chars} weapons={n_weapons} "
          f"artifacts={n_arts} formulas={n_forms}"
          f"{' (dry-run)' if args.dry_run else ''}")


if __name__ == "__main__":
    main()

