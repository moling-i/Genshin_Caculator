# -*- coding: utf-8 -*-
"""
数据验证脚本
检查 ./data/ 下5个JSON文件的结构完整性
"""

import json
import os
import sys

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
REQUIRED_FILES = [
    "characters.json",
    "skills.json",
    "weapons.json",
    "artifacts.json",
    "constellations.json",
]


def check_characters(data: list) -> list:
    """验证角色数据"""
    errors = []
    if not isinstance(data, list):
        return ["characters.json: 顶层应为数组"]
    if len(data) == 0:
        errors.append("characters.json: 角色数为0")
    for i, c in enumerate(data[:200]):
        if not isinstance(c, dict):
            errors.append(f"{i}: 元素不是对象")
            continue
        for key in ["id", "name", "stats_90", "skill_depot_id"]:
            if key not in c:
                errors.append(f"{i} ({c.get('name','?')}): 缺少字段 {key}")
        s90 = c.get("stats_90", {})
        for stat in ["hp", "atk", "def"]:
            if stat not in s90:
                errors.append(f"{i} ({c.get('name','?')}): stats_90 缺少 {stat}")
    return errors


def check_skills(data: dict) -> list:
    """验证技能数据"""
    errors = []
    if not isinstance(data, dict):
        return ["skills.json: 顶层应为对象"]
    if "skill_depots" not in data or "proud_skill_groups" not in data:
        return ["skills.json: 缺少 skill_depots 或 proud_skill_groups"]
    depots = data["skill_depots"]
    groups = data["proud_skill_groups"]
    if len(depots) == 0:
        errors.append("skills.json: 技能仓库数为0")
    if len(groups) == 0:
        errors.append("skills.json: 天赋倍率组数为0")
    # 检查每组是否有 levels
    for g in groups[:100]:
        if "levels" not in g or len(g.get("levels", [])) == 0:
            errors.append(f"天赋组 {g.get('group_id')}: 缺少 levels")
    return errors


def check_weapons(data: list) -> list:
    """验证武器数据"""
    errors = []
    if not isinstance(data, list):
        return ["weapons.json: 顶层应为数组"]
    if len(data) == 0:
        errors.append("weapons.json: 武器数为0")
    for i, w in enumerate(data[:200]):
        if not isinstance(w, dict):
            errors.append(f"{i}: 元素不是对象")
            continue
        for key in ["id", "name", "base_atk_90"]:
            if key not in w:
                errors.append(f"{i} ({w.get('name','?')}): 缺少字段 {key}")
    return errors


def check_artifacts(data: list) -> list:
    """验证圣遗物数据"""
    errors = []
    if not isinstance(data, list):
        return ["artifacts.json: 顶层应为数组"]
    if len(data) == 0:
        errors.append("artifacts.json: 套装数为0")
    for i, a in enumerate(data[:100]):
        if not isinstance(a, dict):
            errors.append(f"{i}: 元素不是对象")
            continue
        for key in ["set_id", "name", "effects"]:
            if key not in a:
                errors.append(f"{i} ({a.get('name','?')}): 缺少字段 {key}")
    return errors


def check_constellations(data: list) -> list:
    """验证命座数据"""
    errors = []
    if not isinstance(data, list):
        return ["constellations.json: 顶层应为数组"]
    if len(data) == 0:
        errors.append("constellations.json: 角色数为0")
    for i, c in enumerate(data[:100]):
        if not isinstance(c, dict):
            errors.append(f"{i}: 元素不是对象")
            continue
        for key in ["character_id", "character_name", "constellations"]:
            if key not in c:
                errors.append(f"{i} ({c.get('character_name','?')}): 缺少字段 {key}")
        if len(c.get("constellations", [])) != 6:
            errors.append(
                f"{i} ({c.get('character_name','?')}): 命座数应为6，实际 {len(c.get('constellations', []))}"
            )
    return errors


def main():
    if not os.path.isdir(DATA_DIR):
        print(f"错误: 目录不存在 {DATA_DIR}")
        sys.exit(1)

    all_errors = []
    print("=== 数据验证 ===")
    for fname in REQUIRED_FILES:
        fpath = os.path.join(DATA_DIR, fname)
        if not os.path.exists(fpath):
            all_errors.append(f"{fname}: 文件不存在")
            continue
        with open(fpath, "r", encoding="utf-8") as f:
            data = json.load(f)
        print(f"\n[{fname}] {os.path.getsize(fpath)/1024:.0f} KB, {len(data) if isinstance(data, list) else 'obj'} 条目")
        if fname == "characters.json":
            errs = check_characters(data)
        elif fname == "skills.json":
            errs = check_skills(data)
        elif fname == "weapons.json":
            errs = check_weapons(data)
        elif fname == "artifacts.json":
            errs = check_artifacts(data)
        elif fname == "constellations.json":
            errs = check_constellations(data)
        else:
            errs = []
        if errs:
            for e in errs[:10]:
                print(f"  [!] {e}")
            all_errors.extend(errs)
        else:
            print("  [OK]")

    if all_errors:
        print(f"\n=== 发现 {len(all_errors)} 个问题 ===")
        for e in all_errors[:20]:
            print(f"  - {e}")
        sys.exit(1)
    else:
        print("\n=== 所有文件验证通过！===")


if __name__ == "__main__":
    main()