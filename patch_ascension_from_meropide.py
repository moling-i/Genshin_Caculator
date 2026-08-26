# -*- coding: utf-8 -*-
"""
修复 data/characters.json 的 ascension_bonus 字段。

问题背景：
  fetch_data.py 曾对 AvatarPromote 各突破阶段的 addProps 做**累加**，
  而原始数据中各阶段是"累计至该阶段"的数值，导致暴击率/暴击伤害/
  元素精通等突破属性被放大数倍（如胡桃暴伤 1.152，正确值为 0.384）。

修复方式：
  以 Meropide 全量抓取数据 characters_meropide_full.json 中 basic_info
  的「突破属性」（如"暴击伤害 38.4%"）为权威来源，整体重建每个角色的
  ascension_bonus（仅保留真正的突破属性一项，丢弃无意义的 BASE_* 累计项）。

用法：
  python patch_ascension_from_meropide.py [--dry-run]
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
CHARS_PATH = os.path.join(ROOT, "data", "characters.json")
MEROPIDE_PATH = os.path.join(
    ROOT, "data", "meropide", "characters_meropide_full.json"
)

# Meropide「突破属性」文案 → FIGHT_PROP 类型
_ELEM_HURT_RE = re.compile(r"(火|水|雷|冰|风|岩|草)元素伤害加成\s*([\d.]+)\s*%?")
_ELEM_KEY = {"火": "FIRE", "水": "WATER", "雷": "ELEC",
             "冰": "ICE", "风": "WIND", "岩": "ROCK", "草": "GRASS"}
ASC_PROP_MAP = [
    (_ELEM_HURT_RE, None, 0.01),  # 元素伤害加成：按元素前缀动态映射
    (re.compile(r"物理伤害加成\s*([\d.]+)\s*%?"), "FIGHT_PROP_PHYSICAL_ADD_HURT", 0.01),
    (re.compile(r"治疗加成\s*([\d.]+)\s*%?"), "FIGHT_PROP_HEAL_ADD", 0.01),
    (re.compile(r"暴击伤害\s*([\d.]+)\s*%?"), "FIGHT_PROP_CRITICAL_HURT", 0.01),
    (re.compile(r"暴击率\s*([\d.]+)\s*%?"), "FIGHT_PROP_CRITICAL", 0.01),
    (re.compile(r"元素充能效率\s*([\d.]+)\s*%?"), "FIGHT_PROP_CHARGE_EFFICIENCY", 0.01),
    (re.compile(r"生命值上限\s*([\d.]+)\s*%?"), "FIGHT_PROP_MAX_HP", 0.01),
    (re.compile(r"生命值\s*([\d.]+)\s*%?"), "FIGHT_PROP_MAX_HP", 0.01),
    (re.compile(r"攻击力\s*([\d.]+)\s*%?"), "FIGHT_PROP_ATTACK", 0.01),
    (re.compile(r"防御力\s*([\d.]+)\s*%?"), "FIGHT_PROP_DEFENSE", 0.01),
    (re.compile(r"元素精通\s*([\d.]+)"), "FIGHT_PROP_ELEMENT_MASTERY", 1.0),
]


def parse_ascension(text: str) -> dict:
    """解析「暴击伤害 38.4%」类文案 → {prop_type: value}"""
    if not text:
        return {}
    for pattern, prop_type, scale in ASC_PROP_MAP:
        m = pattern.search(text)
        if m:
            if prop_type is None:  # 元素伤害加成，取元素前缀
                prop_type = f"FIGHT_PROP_{_ELEM_KEY[m.group(1)]}_ADD_HURT"
                value = m.group(2)
            else:
                value = m.group(1)
            return {prop_type: round(float(value) * scale, 6)}
    return {}


def main() -> None:
    dry_run = "--dry-run" in sys.argv

    with open(CHARS_PATH, encoding="utf-8") as f:
        chars = json.load(f)
    with open(MEROPIDE_PATH, encoding="utf-8") as f:
        records = json.load(f)["records"]

    # 中文名 → 突破属性文案（取首个非空）
    asc_text_map = {}
    for rec in records:
        name = rec.get("name_cn")
        text = (rec.get("basic_info") or {}).get("突破属性", "")
        if name and text and name not in asc_text_map:
            asc_text_map[name] = text

    changed = kept_same = unmatched = 0
    for c in chars:
        name = c.get("name_cn")
        old = c.get("ascension_bonus") or {}
        new = parse_ascension(asc_text_map.get(name, ""))
        if not new:
            unmatched += 1
            if old:
                print(f"[警告] {name}: Meropide 无突破属性，保留原值 {old}")
            continue
        same = set(old.keys()) == set(new.keys()) and all(
            abs(float(old.get(k, 0)) - v) <= 1e-9 for k, v in new.items()
        )
        if same:
            kept_same += 1
            continue
        changed += 1
        print(f"[修复] {name}: {old} -> {new}（Meropide: {asc_text_map[name]}）")
        c["ascension_bonus"] = new

    print(f"\n共 {len(chars)} 名角色：修复 {changed} 条，"
          f"一致 {kept_same} 条，未匹配 {unmatched} 条")

    if dry_run:
        print("[dry-run] 未写入文件")
        return
    if changed:
        with open(CHARS_PATH, "w", encoding="utf-8") as f:
            json.dump(chars, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print(f"-> 已保存 {CHARS_PATH}")
    else:
        print("无需写入")


if __name__ == "__main__":
    main()
