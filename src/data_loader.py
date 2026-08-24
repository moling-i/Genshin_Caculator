"""
数据加载工具 - 从 data/ 目录读取规范化 JSON 文件
"""
import json
import os

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

_cache = {}

def _load(filename: str):
    if filename not in _cache:
        path = os.path.join(_DATA_DIR, filename)
        with open(path, "r", encoding="utf-8") as f:
            _cache[filename] = json.load(f)
    return _cache[filename]

def get_characters() -> list:
    return _load("characters.json")

def get_skills() -> dict:
    return _load("skills.json")

def get_proud_skill_groups() -> dict:
    """返回 group_id -> 倍率组 的映射"""
    skills = get_skills()
    groups = {}
    for g in skills.get("proud_skill_groups", []):
        groups[g["group_id"]] = g
    return groups

def get_skill_depots() -> dict:
    """返回 depot_id -> 技能仓库 的映射"""
    skills = get_skills()
    depots = {}
    for d in skills.get("skill_depots", []):
        depots[d["depot_id"]] = d
    return depots

def get_skill_ratios(skill_depot_id, skill_type: str, level: int = 10) -> dict:
    """
    获取指定角色技能仓库中某类型技能在指定等级的倍率参数。
    返回: {"param_list": [...], "group_id": int, "skill_id": int}
    若找不到则返回 None。
    """
    depots = get_skill_depots()
    depot = depots.get(skill_depot_id)
    if not depot:
        return None
    # 找到对应类型的技能
    target = None
    for s in depot["skills"]:
        if s["skill_type"] == skill_type:
            target = s
            break
    if not target:
        return None
    gid = target.get("proud_skill_group_id", 0)
    if not gid:
        return None
    groups = get_proud_skill_groups()
    group = groups.get(gid)
    if not group:
        return None
    # 找到对应等级
    level_data = None
    for lv in group["levels"]:
        if lv["level"] == level:
            level_data = lv
            break
    if not level_data:
        # 取最高等级
        level_data = group["levels"][-1] if group["levels"] else None
    if not level_data:
        return None
    return {
        "param_list": level_data["param_list"],
        "group_id": gid,
        "skill_id": target["skill_id"],
        "skill_type": skill_type,
        "level": level_data["level"],
    }

def get_weapons() -> list:
    return _load("weapons.json")

def get_artifacts() -> list:
    return _load("artifacts.json")

def get_constellations() -> list:
    return _load("constellations.json")

def find_character_by_name(name: str) -> dict:
    """按中文名或 id 查找角色"""
    chars = get_characters()
    for c in chars:
        if c.get("name_cn") == name or c.get("name") == name or str(c.get("id")) == str(name):
            return c
    return None

def find_weapon_by_name(name: str) -> dict:
    wps = get_weapons()
    for w in wps:
        if w.get("name_cn") == name or w.get("name") == name or str(w.get("id")) == str(name):
            return w
    return None

def find_artifact_set(set_id) -> dict:
    arts = get_artifacts()
    for a in arts:
        if str(a.get("set_id")) == str(set_id):
            return a
    return None

def find_constellation_by_char_id(char_id) -> dict:
    cons = get_constellations()
    for c in cons:
        if str(c.get("character_id")) == str(char_id):
            return c
    return None

def clear_cache():
    _cache.clear()