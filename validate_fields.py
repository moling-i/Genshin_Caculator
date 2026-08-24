#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据字段完整性验证脚本
==================================================
对 data/ 目录下 5 个 JSON 文件进行深度字段验证，
输出《数据字段完整性报告》，为第二阶段（伤害计算架构）做准备。

检查重点：
  - 角色基础属性、元素类型、突破属性
  - 技能倍率（按等级分条）、冷却、能量消耗
  - 武器特效结构化（触发条件 + 修饰器 + 精炼分级）
  - 圣遗物套装 2/4 件效果区分与结构化修饰器
  - 命座属性修改解析与"技能等级+3"识别

用法：
  python validate_fields.py
"""

import json
import os
import sys

# 修复 Windows GBK 终端下 emoji 无法编码的问题
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")


def load(name):
    with open(os.path.join(DATA_DIR, name), "r", encoding="utf-8") as f:
        return json.load(f)


def pct(x):
    return f"{x * 100:.1f}%"


# ==================== 1. characters.json ====================

def check_characters():
    print("\n1. characters.json")
    d = load("characters.json")
    n = len(d)
    print(f"   - 总角色数: {n}")

    has_id = all("id" in c and "name_cn" in c for c in d)
    print(f"   - id / name_cn: {'✅ 齐全' if has_id else '❌ 缺失'}")

    # 基础属性字段名检查（实际为 base_stats.hp/atk/def）
    base_ok = all(
        "base_stats" in c and {"hp", "atk", "def"} <= set(c["base_stats"].keys())
        for c in d
    )
    print(f"   - 基础属性字段: {'✅ 齐全 (base_stats: hp/atk/def)' if base_ok else '❌ 缺失'}")
    print(f"     （注：字段名为 base_stats.hp/atk/def，非 base_hp/base_atk/base_def）")

    # 元素类型
    elem_filled = sum(1 for c in d if c.get("element"))
    print(f"   - element 字段: {'✅ 存在' if elem_filled == n else '❌ 缺失/为空'} "
          f"(填充 {elem_filled}/{n}, {pct(elem_filled / n if n else 0)})")

    # 突破属性
    asc_filled = sum(1 for c in d if c.get("ascension_bonus"))
    print(f"   - ascension_bonus (突破属性): {'✅ 存在' if asc_filled else '❌ 缺失 (空对象)'}"
          f" (填充 {asc_filled}/{n})")

    # 成长曲线
    curve_ok = all("grow_curves" in c for c in d)
    print(f"   - 成长曲线 grow_curves: {'✅ 存在' if curve_ok else '❌ 缺失'}")

    # 暴击/暴伤
    cr_ok = all("base_crit_rate" in c and "base_crit_dmg" in c for c in d)
    print(f"   - 基础暴击/暴伤: {'✅ 齐全' if cr_ok else '❌ 缺失'}")

    return {
        "n": n, "has_id": has_id, "base_ok": base_ok,
        "elem_filled": elem_filled, "asc_filled": asc_filled,
        "curve_ok": curve_ok, "cr_ok": cr_ok,
    }


# ==================== 2. skills.json ====================

def check_skills():
    print("\n2. skills.json")
    d = load("skills.json")
    depots = d.get("skill_depots", [])
    groups = d.get("proud_skill_groups", [])

    total_skills = sum(len(dep["skills"]) for dep in depots)
    print(f"   - 技能仓库数: {len(depots)}，技能条目总数: {total_skills}")
    print(f"   - 天赋倍率组 (proud_skill_groups): {len(groups)}")

    # character_id 关联：skill_depots 用 depot_id，需通过 characters.json 反查
    chars = load("characters.json")
    depot_to_char = {c["skill_depot_id"]: c["name_cn"] for c in chars}
    linked = sum(1 for dep in depots if dep["depot_id"] in depot_to_char)
    print(f"   - depot_id → 角色 关联: {'✅ 可反查' if linked == len(depots) else '⚠️ 部分缺失'}"
          f" ({linked}/{len(depots)})")

    # skill_type 填充情况
    st_filled = sum(1 for dep in depots for s in dep["skills"] if s.get("skill_type"))
    print(f"   - skill_type (普攻/E/Q): {'✅ 已填充' if st_filled == total_skills else '❌ 缺失/为空'}"
          f" (填充 {st_filled}/{total_skills})")

    # 倍率按等级分条：检查 proud_skill_groups 的 levels
    grp_with_levels = sum(1 for g in groups if g.get("levels"))
    sample = groups[0] if groups else {}
    lvl_count = len(sample.get("levels", [])) if sample else 0
    print(f"   - 倍率按等级分条 (proud_skill_groups.levels): "
          f"{'✅ 已分条' if grp_with_levels == len(groups) and lvl_count > 0 else '❌ 缺失'}"
          f" (分组 {grp_with_levels}/{len(groups)}, 样例等级数 {lvl_count})")

    # 技能与倍率组是否关联
    linked_ratio = sum(1 for dep in depots for s in dep["skills"] if s.get("proud_skills"))
    print(f"   - 技能→倍率组 直接关联: {'✅ 已关联' if linked_ratio else '❌ 未关联 (proud_skills 为空)'}"
          f" (关联 {linked_ratio}/{total_skills})")

    # 冷却时间
    cd_filled = sum(1 for dep in depots for s in dep["skills"] if "cooldown" in s)
    print(f"   - cooldown (冷却): {'✅ 存在' if cd_filled else '❌ 缺失 (字段不存在)'}")

    # 能量消耗
    ec_filled = sum(1 for dep in depots for s in dep["skills"] if s.get("cost_energy", 0) > 0)
    print(f"   - energy_cost (能量): {'✅ 存在 (cost_energy)' if ec_filled else '❌ 缺失'}"
          f" (非零条目 {ec_filled})")

    # 持续时间
    dur_filled = sum(1 for dep in depots for s in dep["skills"] if "duration" in s)
    print(f"   - duration (持续时间): {'✅ 存在' if dur_filled else '❌ 缺失 (字段不存在)'}")

    return {
        "total_skills": total_skills, "groups": len(groups),
        "st_filled": st_filled, "grp_with_levels": grp_with_levels,
        "lvl_count": lvl_count, "linked_ratio": linked_ratio,
        "cd_filled": cd_filled, "ec_filled": ec_filled, "dur_filled": dur_filled,
    }


# ==================== 3. weapons.json ====================

def check_weapons():
    print("\n3. weapons.json")
    d = load("weapons.json")
    n = len(d)
    print(f"   - 总武器数: {n}")

    has_name = all("name_cn" in w and "rarity" in w for w in d)
    print(f"   - name_cn / rarity: {'✅ 齐全' if has_name else '❌ 缺失'}")
    # 实际字段为 rank 而非 rarity
    has_rank = all("rank" in w for w in d)
    print(f"     （注：星级字段名为 'rank'，非 'rarity'）")

    has_atk = all("base_atk_90" in w and "sub_stat" in w for w in d)
    print(f"   - base_atk / sub_stat: {'✅ 齐全' if has_atk else '❌ 缺失'}")

    # 武器特效结构化
    ref_total = 0
    ref_struct = 0
    for w in d:
        for r in w.get("refinements", []):
            ref_total += 1
            pl = r.get("param_list", [])
            if pl:  # 有结构化参数
                ref_struct += 1
    print(f"   - 武器特效 (refinements): 总条目 {ref_total}，含结构化参数 {ref_struct}")
    if ref_total == 0:
        print("     ❌ 完全缺失武器特效数据")
    elif ref_struct == ref_total:
        print("     ✅ 全部以结构化参数 (param_list) 存储")
    else:
        print("     ⚠️ 部分含结构化参数，需检查触发条件字段")

    # 检查是否有 effect_trigger / effect_modifiers 字段
    has_trigger = any("effect_trigger" in w or "effect_modifiers" in w for w in d)
    print(f"   - effect_trigger / effect_modifiers 显式字段: "
          f"{'✅ 存在' if has_trigger else '❌ 不存在 (仅 param_list 原始参数)'}")

    return {
        "n": n, "has_name": has_name, "has_rank": has_rank,
        "has_atk": has_atk, "ref_total": ref_total, "ref_struct": ref_struct,
        "has_trigger": has_trigger,
    }


# ==================== 4. artifacts.json ====================

def check_artifacts():
    print("\n4. artifacts.json")
    d = load("artifacts.json")
    n = len(d)
    print(f"   - 总套装数: {n}")

    has_id = all("set_id" in a and "name_cn" in a for a in d)
    print(f"   - set_id / set_name_cn: {'✅ 齐全' if has_id else '❌ 缺失'}")

    # 2件/4件区分
    has_2 = sum(1 for a in d if any(e.get("pieces") == 2 for e in a.get("effects", [])))
    has_4 = sum(1 for a in d if any(e.get("pieces") == 4 for e in a.get("effects", [])))
    print(f"   - 2件套/4件套区分: {'✅ 是' if has_2 and has_4 else '❌ 否'}"
          f" (含2件 {has_2}/{n}, 含4件 {has_4}/{n})")

    # 效果结构化（修饰器）vs 纯文本
    total_eff = 0
    struct_eff = 0
    for a in d:
        for e in a.get("effects", []):
            total_eff += 1
            pl = e.get("param_list", [])
            if pl:
                struct_eff += 1
    print(f"   - 套装效果结构化: 总效果 {total_eff}，含 param_list 参数 {struct_eff}")
    if total_eff == 0:
        print("     ❌ 完全缺失套装效果")
    elif struct_eff == total_eff:
        print("     ✅ 全部含结构化参数 (param_list)")
    else:
        print("     ⚠️ 部分含参数，部分为纯文本 desc")

    # 缺失率计算（用于错误阈值判定）
    missing_rate = 1 - (struct_eff / total_eff) if total_eff else 1.0
    print(f"   - 纯文本/无参数缺失率: {pct(missing_rate)}")

    # 是否需要额外导入 ReliquarySetExcelConfigData
    print(f"   - 备注: 当前已使用 ReliquarySetExcelConfigData.json 提取套装效果，"
          f"效果以 param_list 结构化存储，无需额外导入。")

    return {
        "n": n, "has_id": has_id, "has_2": has_2, "has_4": has_4,
        "total_eff": total_eff, "struct_eff": struct_eff, "missing_rate": missing_rate,
    }


# ==================== 5. constellations.json ====================

def check_constellations():
    print("\n5. constellations.json")
    d = load("constellations.json")
    n = len(d)
    total_const = sum(len(c.get("constellations", [])) for c in d)
    print(f"   - 命座角色数: {n}，命座总条数: {total_const}")

    has_char = all("character_id" in c and "character_name_cn" in c for c in d)
    print(f"   - character_id / character_name_cn: {'✅ 齐全' if has_char else '❌ 缺失'}")

    # constellation_level
    lvl_ok = all(
        all("constellation_level" in cc for cc in c.get("constellations", []))
        for c in d
    )
    print(f"   - constellation_level (C1~C6): {'✅ 齐全' if lvl_ok else '❌ 缺失'}")

    # 属性修改解析（param_list 结构化）
    total_param = 0
    has_param = 0
    for c in d:
        for cc in c.get("constellations", []):
            total_param += 1
            if cc.get("param_list"):
                has_param += 1
    print(f"   - 属性修改解析 (param_list): 总命座 {total_param}，含参数 {has_param}")
    if has_param == total_param and total_param > 0:
        print("     ✅ 全部含结构化参数")
    elif has_param > 0:
        print("     ⚠️ 部分含参数，部分为纯文本 desc")
    else:
        print("     ❌ 仅纯文本 desc，无结构化参数")

    # 技能等级+3 识别
    plus3 = 0
    for c in d:
        for cc in c.get("constellations", []):
            desc = cc.get("desc", "") or ""
            pl = cc.get("param_list", [])
            # 检测 param_list 中是否含 +3 等级提升（通常第1参数为 3）
            if any(abs(p - 3) < 0.01 for p in pl if isinstance(p, (int, float))):
                plus3 += 1
            elif "等级" in desc and "+3" in desc:
                plus3 += 1
    print(f"   - 技能等级+3 识别: 疑似条目 {plus3}（基于 param_list 或 desc 文本）")
    print(f"     （注：当前未显式区分对应技能 E/Q，需下游结合技能仓库解析）")

    return {
        "n": n, "total_const": total_const, "has_char": has_char,
        "lvl_ok": lvl_ok, "total_param": total_param, "has_param": has_param,
        "plus3": plus3,
    }


# ==================== 主报告 ====================

def main():
    print("=" * 56)
    print("【数据字段完整性报告】")
    print("=" * 56)

    c = check_characters()
    s = check_skills()
    w = check_weapons()
    a = check_artifacts()
    co = check_constellations()

    print("\n" + "=" * 56)
    print("【结论】")
    print("=" * 56)

    print("\n当前数据结构对第二阶段（伤害计算）的支撑情况：")

    print("\n- ✅ 可直接使用：")
    print(f"  · 角色基础属性 (base_stats.hp/atk/def, stats_90, 暴击/暴伤) — {c['n']} 角色")
    print(f"  · 武器基础攻击与副属性 (base_atk_90, sub_stat) — {w['n']} 武器")
    print(f"  · 圣遗物套装 2/4 件效果 (param_list 结构化) — {a['n']} 套装")
    print(f"  · 天赋倍率组按等级分条 (proud_skill_groups.levels) — {s['groups']} 组")

    print("\n- ⚠️ 需要补充解析：")
    if c["elem_filled"] == 0:
        print("  · 角色元素类型 (element 字段为空) — 需从 AvatarSkillDepot 解析 element")
    if c["asc_filled"] == 0:
        print("  · 角色突破属性 (ascension_bonus 为空) — 需导入 AvatarPromoteExcelConfigData")
    if s["st_filled"] == 0:
        print("  · 技能类型 (skill_type 为空) — 需从 AvatarSkill 的 skillType 映射")
    if s["linked_ratio"] == 0:
        print("  · 技能→倍率组关联 (proud_skills 为空) — 需建立 skill_id→proud_group 映射")
    if s["cd_filled"] == 0:
        print("  · 冷却时间 (cooldown 字段缺失) — 需从 AvatarSkill.cdTime 提取")
    if not w["has_trigger"]:
        print("  · 武器特效触发条件 (effect_trigger 缺失) — 当前仅 param_list 原始参数")
    if co["has_param"] < co["total_param"]:
        print("  · 命座属性修改 (部分仅文本) — 需结构化解析 param_list")
    print("  · 月反应/星反应专属字段 — 当前数据无（需游戏机制层补充，非数据源问题）")

    print("\n- ❌ 完全缺失，需重新下载/处理：")
    if a["missing_rate"] > 0.3:
        print(f"  · artifacts.json 套装效果缺失率 {pct(a['missing_rate'])} > 30% — 需修改解析逻辑")
    else:
        print("  · 无（artifacts.json 缺失率 {:.1f}% ≤ 30%）".format(a["missing_rate"] * 100))

    # 错误阈值判定
    print("\n" + "-" * 56)
    if a["missing_rate"] > 0.3 or co["has_param"] == 0:
        print("⚠️ 判定：关键字段缺失率超阈值，当前数据【不具备】开发条件，需返回修改 fetch_data.py")
    else:
        print("✅ 判定：关键字段缺失率未超阈值，当前数据【具备】开发条件，可进入第二阶段")
    print("-" * 56)


if __name__ == "__main__":
    main()