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


# ==================== 图标 / 天赋 / 固有天赋 ====================

_ENKA_UI = "https://enka.network/ui/{icon}.png"


def get_icons() -> dict:
    """读取 data/icons.json（avatar/weapon/relic 的 id -> 图标名映射）"""
    try:
        return _load("icons.json")
    except (FileNotFoundError, json.JSONDecodeError):
        return {"avatar": {}, "weapon": {}, "relic": {}}


def get_icon_url(kind: str, obj_id, default_suffix: str = "") -> str:
    """
    获取 enka CDN 图片直链；未知 id 返回空字符串（UI 显示占位符）。
    kind: "avatar" | "weapon" | "relic"
    圣遗物图标名若不含件数后缀，用 default_suffix 补全（如 "_5"）。
    """
    icon = get_icons().get(kind, {}).get(str(obj_id), "")
    if not icon:
        return ""
    if kind == "relic" and icon.endswith("_"):
        icon = icon.rstrip("_") + default_suffix
    return _ENKA_UI.format(icon=icon)


def _find_meropide_character(name_cn: str) -> dict:
    """按中文名在 meropide 角色数据中查找"""
    try:
        items = _load(os.path.join("meropide", "characters_meropide.json"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    if isinstance(items, dict):
        items = items.get("items", [])
    for m in items:
        if m.get("name") == name_cn:
            return m
    return None


def get_talent_display(character_id) -> list:
    """
    获取角色的天赋展示信息（来自 meropide 权威文案）。
    返回: [{skill_name, skill_type, desc, rows: [{label, value_text}]}]
    数据源缺失时返回 []。
    """
    char = find_character_by_name(character_id)
    if not char:
        return []
    mp = _find_meropide_character(char.get("name_cn") or "")
    if not mp:
        return []
    return mp.get("talents") or []


def load_passive_skills(character_id) -> list:
    """
    读取角色的所有固有天赋（Meropide 数据）。
    返回: [{"name": ..., "description": ...}]，数据缺失时返回 []。
    """
    char = find_character_by_name(character_id)
    if not char:
        return []
    mp = _find_meropide_character(char.get("name_cn") or "")
    if not mp:
        return []
    result = []
    for pt in mp.get("passive_talents") or []:
        result.append({
            "name": pt.get("name", ""),
            "description": pt.get("desc", pt.get("description", "")),
        })
    return result


# ---- 固有天赋描述 -> 结构化修饰器解析 ----

import re as _re

# 属性关键词映射（顺序敏感：具体关键词优先于泛化关键词）
_EFFECT_RULES = [
    # 各元素伤害加成 -> 统一计入元素伤害加成区
    (_re.compile(r"([火水冰雷风岩草])元素伤害加成"), "elemental_dmg_bonus", "pct"),
    (_re.compile(r"月曜反应伤害(?:提升|提高)"), "lunar_dmg_bonus", "pct"),
    (_re.compile(r"月反应伤害(?:提升|提高)"), "lunar_dmg_bonus", "pct"),
    (_re.compile(r"元素爆发造成的伤害(?:提升|提高)"), "dmg_bonus", "pct"),
    (_re.compile(r"元素战技造成的伤害(?:提升|提高)"), "dmg_bonus", "pct"),
    (_re.compile(r"普通攻击造成的伤害(?:提升|提高)"), "dmg_bonus", "pct"),
    (_re.compile(r"重击造成的伤害(?:提升|提高)"), "dmg_bonus", "pct"),
    (_re.compile(r"造成的伤害(?:提升|提高)"), "dmg_bonus", "pct"),
    (_re.compile(r"攻击力(?:提升|提高)"), "atk_percent", "pct"),
    (_re.compile(r"生命值上限(?:提升|提高)"), "hp_percent", "pct"),
    (_re.compile(r"防御力(?:提升|提高)"), "def_percent", "pct"),
    (_re.compile(r"暴击伤害(?:提升|提高)"), "crit_dmg", "pct"),
    (_re.compile(r"暴击率(?:提升|提高)"), "crit_rate", "pct"),
    (_re.compile(r"元素充能效率(?:提升|提高)"), "er", "pct"),  # 计算引擎暂未使用，标记解析
    (_re.compile(r"元素精通(?:提升|提高)"), "elemental_mastery", "flat"),
]

_PCT_RE = _re.compile(r"(\d+(?:\.\d+)?)\s*%")
_FLAT_RE = _re.compile(r"(\d+(?:\.\d+)?)\s*点")

# 条件触发短语：命中任一则视为条件型天赋（UI 提供条件满足开关）
_CONDITION_WORDS = [
    "低于", "以下", "处于", "结束时", "结束后", "命中敌人时", "施放",
    "触发", "持续期间", "场上", "附近的角色", "受到", "拾取", "击败",
]


def parse_effect(description: str) -> dict:
    """
    将固有天赋描述文本解析为结构化修饰器。

    返回: {
        "modifiers": {attr: value, ...},   # 可直接叠加到角色面板的加成
        "conditional": bool,               # 是否为条件触发型（UI 需提供条件开关）
        "unparsed": bool,                  # 是否未能识别出任何数值加成
    }
    说明：仅覆盖直接数值加成型固有天赋；复杂机制类天赋标记为 unparsed，
    UI 中仍可勾选展示，但不参与面板计算。
    """
    text = description or ""
    modifiers = {}

    for pattern, attr, vtype in _EFFECT_RULES:
        m = pattern.search(text)
        if not m:
            continue
        # 数值可能在关键词之后（"提升12%"）或之前（"获得33%火元素伤害加成"）
        tail = text[m.end():]
        vm = None
        if vtype == "pct":
            vm = _PCT_RE.search(tail)
            if not vm:
                # 回退：取关键词之前、距离最近的百分数（限制在 16 字符窗口内）
                vm = None
                for vm_c in _PCT_RE.finditer(text[: m.start()]):
                    if m.start() - vm_c.end() <= 16:
                        vm = vm_c
        else:
            vm = _FLAT_RE.search(tail)
            if not vm:
                vm = None
                for vm_c in _FLAT_RE.finditer(text[: m.start()]):
                    if m.start() - vm_c.end() <= 16:
                        vm = vm_c
        if not vm:
            continue
        val = float(vm.group(1))
        if vtype == "pct":
            val /= 100.0
        modifiers[attr] = modifiers.get(attr, 0.0) + val

    conditional = any(w in text for w in _CONDITION_WORDS)
    return {
        "modifiers": modifiers,
        "conditional": conditional,
        "unparsed": not modifiers,
    }
