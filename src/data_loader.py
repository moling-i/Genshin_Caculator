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


# ==================== 角色状态标签系统 ====================
# 状态类型：夜魂(纳塔) / 魔导 / 星超导(至冬) / 星扩散(至冬) / 月兆(挪德卡莱)
# 当前阶段仅作展示，不产生数值加成；后续通过 `if "夜魂" in char.states` 触发效果。

# 固有状态硬编码映射表（优先级高于 region 推断，用于精确指定与多状态角色）
STATE_MAPPING = {
    # === 纳塔 → 夜魂 ===
    "玛薇卡": ["夜魂"],
    "基尼奇": ["夜魂"],
    "希诺宁": ["夜魂"],
    "卡齐娜": ["夜魂"],
    "恰斯卡": ["夜魂"],
    "玛拉妮": ["夜魂"],
    "欧洛伦": ["夜魂"],
    "茜特菈莉": ["夜魂"],
    "伊安珊": ["夜魂"],
    "瓦雷莎": ["夜魂"],  # meropide 数据用字
    "瓦蕾莎": ["夜魂"],  # 兼容常见别名写法
    # === 至冬/特殊 ===
    "尼可": ["星超导"],
    "伊法": ["星扩散"],  # 注意：meropide region 标记为纳塔，此处按需求文档显式指定
    # === 魔导（可与其他状态并存）===
    "埃洛伊": ["魔导"],
    "丝柯克": ["夜魂", "魔导"],
}

# 按 meropide region 字段推断的兜底映射（states 字段与 STATE_MAPPING 均未命中时使用）
_REGION_STATE_FALLBACK = {
    "纳塔": ["夜魂"],
    "挪德卡莱": ["月兆"],
}

_states_cache = {}


def get_character_states(character_id) -> list:
    """
    获取角色固有状态标签列表。
    数据源优先级：
      1. data/meropide/characters_meropide.json 的 states 字段
      2. STATE_MAPPING 硬编码映射
      3. meropide region 字段推断（纳塔→夜魂、挪德卡莱→月兆）
      4. 均未命中返回 []（不显示任何标签）
    """
    key = str(character_id)
    if key in _states_cache:
        return list(_states_cache[key])

    char = find_character_by_name(key)
    name_cn = (char or {}).get("name_cn") or ""
    mp = _find_meropide_character(name_cn) if name_cn else None

    states = []
    if mp and mp.get("states"):
        states = list(mp["states"])
    elif name_cn in STATE_MAPPING:
        states = list(STATE_MAPPING[name_cn])
    else:
        region = (mp or {}).get("region", "") or ""
        for rkey, rstates in _REGION_STATE_FALLBACK.items():
            if rkey in region:
                states = list(rstates)
                break

    _states_cache[key] = states
    return list(states)



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

# 减抗/无视防御："Q技能无视60%防御"
_DEF_IGNORE_RE = _re.compile(r"无视\s*(\d+(?:\.\d+)?)\s*%\s*的?防御")

# 增幅反应（蒸发/融化）专属增伤："触发蒸发时造成的伤害提升15%"
_AMPLIFY_RE = _re.compile(r"(蒸发|融化)")

# 属性转换："基于生命值上限的6%，转化为攻击力" 等
_CONV_RE = _re.compile(
    r"(生命值上限|防御力|攻击力|元素精通)[^。%]{0,8}?(\d+(?:\.\d+)?)\s*%"
    r"[^。]{0,20}?(?:转化|转换|换算)为?(攻击力)"
)
_CONV_FROM_MAP = {"生命值上限": "hp", "防御力": "def", "攻击力": "atk", "元素精通": "em"}

# 充能转伤害（如雷电将军固有）：充能效率超出100%的部分每1%提供X%某系伤害
_ER_SCALE_RE = _re.compile(
    r"充能效率[^。]{0,24}超[出过]\s*100\s*%[^。]*?"
    r"每\s*1\s*%[^。]{0,24}?(\d+(?:\.\d+)?)\s*%\s*"
    r"(?:[火水冰雷风岩草]元素)?伤害(?:加成)?"
)

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
        "modifiers": {attr: value, ...},     # 直接数值加成（叠加到面板属性）
        "conditional": bool,                 # 是否条件触发型（UI 需提供条件控制）
        "hp_threshold": float | None,        # 血量阈值（如半血天赋为 0.5）
        "conversion": {...} | None,          # 属性转换 {from, to, ratio}
        "er_scaling": {...} | None,          # 充能转伤害 {threshold, per_unit, stat}
        "unparsed": bool,                    # 是否未能识别出任何可计算效果
    }
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
                for vm_c in _PCT_RE.finditer(text[: m.start()]):
                    if m.start() - vm_c.end() <= 16:
                        vm = vm_c
        else:
            vm = _FLAT_RE.search(tail)
            if not vm:
                for vm_c in _FLAT_RE.finditer(text[: m.start()]):
                    if m.start() - vm_c.end() <= 16:
                        vm = vm_c
        if not vm:
            continue
        val = float(vm.group(1))
        if vtype == "pct":
            val /= 100.0
        modifiers[attr] = modifiers.get(attr, 0.0) + val

    # ---- 扩展类型解析 ----
    conversion = None
    cm = _CONV_RE.search(text)
    if cm:
        conversion = {
            "from": _CONV_FROM_MAP[cm.group(1)],
            "to": "atk_flat",
            "ratio": float(cm.group(2)) / 100.0,
            "text": cm.group(0),
        }

    er_scaling = None
    em2 = _ER_SCALE_RE.search(text)
    if em2:
        er_scaling = {
            "threshold": 1.0,               # 充能效率超出 100% 的部分
            "per_unit": float(em2.group(1)) / 100.0,  # 每 1% 充能提供的增伤
            "stat": "elemental_dmg_bonus",
            "text": em2.group(0),
        }

    dm = _DEF_IGNORE_RE.search(text)
    if dm:
        modifiers["def_ignore"] = modifiers.get("def_ignore", 0.0) + float(dm.group(1)) / 100.0

    am = _AMPLIFY_RE.search(text)
    amplify_hit = bool(am)

    conditional = any(w in text for w in _CONDITION_WORDS)

    # 血量条件阈值（"生命值低于或等于50%" → 0.5）
    hp_threshold = None
    hm = _re.search(r"生命值[^。%]{0,6}(?:低于或等于|低于|低于等于)\s*(\d+(?:\.\d+)?)\s*%", text)
    if hm:
        hp_threshold = float(hm.group(1)) / 100.0

    computable = (
        modifiers or conversion is not None or er_scaling is not None or amplify_hit
    )
    return {
        "modifiers": modifiers,
        "conditional": conditional,
        "hp_threshold": hp_threshold,
        "conversion": conversion,
        "er_scaling": er_scaling,
        "amplify_reaction": amplify_hit and not (modifiers or conversion or er_scaling),
        "unparsed": not computable,
    }
