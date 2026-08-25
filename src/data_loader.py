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


def find_meropide_artifact(name_cn: str) -> dict:
    """按中文名在 meropide 圣遗物数据中查找（权威套装文案：set_2_effect/set_4_effect）"""
    try:
        items = _load(os.path.join("meropide", "artifacts_meropide.json"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    if isinstance(items, dict):
        items = items.get("items", [])
    for m in items:
        if m.get("set_name") == name_cn:
            return m
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


# 状态触发短语提示：天赋描述中出现这些关键词即视为依赖对应状态标签
# （即使角色 states 列表未显式包含，如可莉「魔导·秘仪」）
_STATE_TRIGGER_HINTS = {
    "夜魂": ["夜魂加持", "夜魂迸发"],
    "魔导": ["魔导·秘仪", "魔导角色"],
    "星超导": ["星超导"],
    "星扩散": ["星扩散"],
    "月兆": ["月曜反应", "月之领域"],
}


def detect_required_states(text: str, states: list) -> list:
    """
    检测天赋描述依赖哪些状态标签。
    命中规则：
      1. 触发短语提示（魔导·秘仪/夜魂加持/星超导/月曜反应等）→ 依赖对应状态
        （即使角色 states 列表未显式包含，如可莉「魔导·秘仪」、温迪「颂时风若」）；
      2. 角色 states 列表中的状态名直接出现在描述中。
    返回依赖的状态名列表（用于 UI 触发开关与引擎门控）。
    """
    req = []
    for s, hints in _STATE_TRIGGER_HINTS.items():
        if s in text or any(h in text for h in hints):
            req.append(s)
    for s in states or []:
        if s in text and s not in req:
            req.append(s)
    return req



# ---- 固有天赋描述 -> 结构化修饰器解析 ----

import re as _re

# 属性关键词映射（顺序敏感：具体关键词优先于泛化关键词）
# 注：(?:提升|提高) 统一写成 将?(?:提升|提高) 以兼容"元素精通将提升25点"语序
_EFFECT_RULES = [
    # 各元素伤害加成 -> 统一计入元素伤害加成区
    (_re.compile(r"([火水冰雷风岩草])元素伤害加成"), "elemental_dmg_bonus", "pct"),
    (_re.compile(r"月曜反应伤害(?:提升|提高)"), "lunar_dmg_bonus", "pct"),
    (_re.compile(r"月反应伤害(?:提升|提高)"), "lunar_dmg_bonus", "pct"),
    # 物理伤害（须先于通用"造成的伤害"）
    (_re.compile(r"物理伤害(?:提高|提升)"), "physical_dmg_bonus", "pct"),
    (_re.compile(r"元素爆发造成的伤害(?:提升|提高)"), "dmg_bonus", "pct"),
    (_re.compile(r"元素战技造成的伤害(?:提升|提高)"), "dmg_bonus", "pct"),
    (_re.compile(r"普通攻击造成的伤害(?:提升|提高)"), "dmg_bonus", "pct"),
    (_re.compile(r"重击造成的伤害(?:提升|提高)"), "dmg_bonus", "pct"),
    (_re.compile(r"造成的(?:所有)?伤害(?:提升|提高)"), "dmg_bonus", "pct"),
    # 剧变/激化系反应专属增伤（超导/感电/扩散/超载/绽放…，兼容"反应伤害提升"与"反应的伤害提升"两种语序）
    (_re.compile(r"(?:超导|感电|扩散|超载|绽放|碎裂)(?:星)?[^。]{0,12}反应的伤害将?(?:提升|提高)"), "reaction_dmg_bonus", "pct"),
    (_re.compile(r"(?:星超导|星扩散|超导|感电|扩散|超载|绽放)反应伤害将?(?:提升|提高)"), "reaction_dmg_bonus", "pct"),
    (_re.compile(r"攻击力将?(?:提升|提高)"), "atk_percent", "pct"),
    (_re.compile(r"生命值上限将?(?:提升|提高)"), "hp_percent", "pct"),
    (_re.compile(r"防御力将?(?:提升|提高)"), "def_percent", "pct"),
    (_re.compile(r"暴击伤害将?(?:提升|提高)"), "crit_dmg", "pct"),
    (_re.compile(r"暴击率将?(?:提升|提高)"), "crit_rate", "pct"),
    (_re.compile(r"元素充能效率将?(?:提升|提高)"), "er", "pct"),  # 计算引擎暂未使用，标记解析
    (_re.compile(r"元素精通将?(?:提升|提高)"), "elemental_mastery", "flat"),
]

# 前置语序规则："提高10%攻击力"/"提升20%元素充能效率"（数值在前、属性在后）
_PRE_ORDER_RULES = [
    (_re.compile(r"将?(?:提高|提升)\s*(\d+(?:\.\d+)?)\s*%\s*的?攻击力"), "atk_percent", "pct"),
    (_re.compile(r"将?(?:提高|提升)\s*(\d+(?:\.\d+)?)\s*%\s*的?生命值上限"), "hp_percent", "pct"),
    (_re.compile(r"将?(?:提高|提升)\s*(\d+(?:\.\d+)?)\s*%\s*的?防御力"), "def_percent", "pct"),
    (_re.compile(r"将?(?:提高|提升)\s*(\d+)\s*点\s*的?元素精通"), "elemental_mastery", "flat"),
    (_re.compile(r"将?(?:提高|提升)\s*(\d+(?:\.\d+)?)\s*%\s*的?元素充能效率"), "er", "pct"),
    (_re.compile(r"将?(?:提高|提升)\s*(\d+(?:\.\d+)?)\s*%\s*的?暴击率"), "crit_rate", "pct"),
    (_re.compile(r"将?(?:提高|提升)\s*(\d+(?:\.\d+)?)\s*%\s*的?暴击伤害"), "crit_dmg", "pct"),
]

# "伤害值提升，提升值相当于XX的X%"（蓝砚/赛诺/赛索斯/梦见月瑞希/叶洛亚式 flat 加算）
_FLAT_DMG_SCALE_RE = _re.compile(
    r"伤害值(?:将)?(?:提升|提高)[^。]*?相当于\S{0,8}(元素精通|攻击力|防御力|生命值上限)的\s*([\d.%/和]+)"
)

# 属性线性转自身增伤（艾梅莉埃精馏式，无阈值起点）：
# "基于X的攻击力，提升…造成的伤害：每1000点攻击力都将提升15%伤害，至多…36%"
_ATTR_SCALE_RE = _re.compile(
    r"基于\S{0,8}的(攻击力|元素精通|生命值上限|防御力)[^。]*?[：:][^。]*?"
    r"每\s*(\d+)\s*点\s*\1?[^。]*?(?:提升|提高)\s*(\d+(?:\.\d+)?)\s*%伤害[^。]*?至多[^。]*?(\d+(?:\.\d+)?)\s*%"
)

# 全队攻击共享（琳妮特式："队伍中所有角色的攻击力分别提升8%/12%/16%/20%"）
_TEAM_ATK_SHARE_RE = _re.compile(
    r"队伍中所有角色的攻击力分别将?(?:提升|提高)\s*([\d%/.]+)"
)

# 全队精通共享-按全队最高精通比例（纳西妲净善摄受明论式，含上限；允许跨句）
_TEAM_EM_MAX_RE = _re.compile(
    r"元素精通最高的角色的元素精通数值的\s*(\d+(?:\.\d+)?)\s*%"
    r"[\s\S]{0,80}?至多[\s\S]{0,10}?(?:提升|提高)\s*(\d+)\s*点元素精通"
)

# 全队精通共享-按自身属性比例（莉奈娅万类博物图鉴式，跨句）：
# "提升值基于莉奈娅防御力的5%"
_TEAM_EM_FROM_ATTR2_RE = _re.compile(
    r"提升值基于\S{0,10}(攻击力|生命值上限|防御力)的\s*(\d+(?:\.\d+)?)\s*%"
)

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
# 充能转伤害变体B（雷电将军殊胜之御体式）：
# "基于元素充能效率超过100%的部分，每1%…雷元素伤害加成 提升0.4%"
_ER_SCALE_B_RE = _re.compile(
    r"充能效率超[出过]\s*100\s*%[^。]*?"
    r"每\s*1\s*%[^。]*?"
    r"([火水冰雷风岩草])元素伤害加成\s*(?:将)?(?:提升|提高)\s*(\d+(?:\.\d+)?)\s*%"
)

# 充能转伤害变体（阿罗夏式，无"超出100%"起点，从第1点充能即生效，含上限）：
# "每1%元素充能效率都会使上述伤害提升0.35%，至多提升至70%"
_ER_SCALE_V2_RE = _re.compile(
    r"每\s*1\s*%\s*元素充能效率[^。]*?(?:伤害)?(?:提升|提高)\s*(\d+(?:\.\d+)?)\s*%"
    r"[^。]*?至多[^。]*?(\d+(?:\.\d+)?)\s*%"
)

# 属性超阈值转反应增伤（奥黛塔式）：
# "基于…攻击力超过1000点的部分，每100点攻击力都将使…星烁反应伤害额外…1.5%…至多…30%"
_ATK_OVER_RE = _re.compile(
    r"(攻击力|生命值上限|防御力|元素精通)超过\s*(\d+)\s*点[^。]*?"
    r"每\s*(\d+)\s*点[^。]*?(\d+(?:\.\d+)?)\s*%[^。]*?至多[^。]*?(\d+(?:\.\d+)?)\s*%"
)
_OVER_SRC_MAP = {"攻击力": "atk", "生命值上限": "hp", "防御力": "def", "元素精通": "em"}

# 敌人防御降低（我方增益型减防，如丽莎静电场力："降低15%防御力"）
_ENEMY_DEF_SHRED_RE = _re.compile(r"降低\s*(\d+(?:\.\d+)?)\s*%\s*的?防御力")

# 敌人元素抗性降低（如重云追冰剑诀："冰元素抗性 降低10%"）
_ENEMY_RES_SHRED_RE = _re.compile(
    r"([火水冰雷风岩草])元素抗性[^。%]{0,8}?(?:降低|减少)\s*(\d+(?:\.\d+)?)\s*%"
)

# 技能等级提高（达达利亚/丝柯克/洛恩式："普通攻击 等级提高1级"）
_TALENT_LV_RE = _re.compile(
    r"(普通攻击|元素战技|元素爆发)[^。]{0,12}等级(?:提高|提升)\s*(\d+)\s*级"
)
_TALENT_LV_MAP = {"普通攻击": "normal", "元素战技": "skill", "元素爆发": "burst"}

# 全队精通共享-固定值（砂糖触媒置换术："队伍中…元素精通提升50"）
_TEAM_EM_FLAT_RE = _re.compile(
    r"队伍中[^。]{0,30}?元素精通(?:提升|提高)\s*(\d+)(?!\s*%)"
)

# 全队精通共享-比例（砂糖小小的慧风："基于砂糖元素精通的20%，为队伍…提供元素精通加成"）
_TEAM_EM_PCT_RE = _re.compile(
    r"基于[^。]{0,14}元素精通的\s*(\d+(?:\.\d+)?)\s*%\s*[，,][^。]*?元素精通"
)
# 全队精通共享-按其他属性百分比（伊涅芙全相重构协议："基于伊涅芙攻击力的6%，提升…元素精通"）
_TEAM_EM_FROM_ATTR_RE = _re.compile(
    r"基于\S{0,6}(攻击力|生命值上限|防御力)的\s*(\d+(?:\.\d+)?)\s*%[^。]*?元素精通"
)

# 精通转对应元素伤共享（枫原万叶："每点元素精通…提供0.04%对应元素伤害加成"）
_EM_TO_DMG_RE = _re.compile(
    r"每点元素精通[^。]*?(\d+(?:\.\d+)?)\s*%(?:对应)?元素伤害加成"
)

# 月曜反应基础伤害缩放（月兆祝赐系列：伊涅芙/菈乌玛/菲林斯/奈芙尔/兹白/哥伦比娅）
# "基于X的攻击力，提升月感电反应的基础伤害：每100点攻击力都将提升0.7%基础伤害，至多…14%"
_LUNAR_SCALE_RE = _re.compile(
    r"基于[^。]{0,14}?(攻击力|元素精通|生命值上限|防御力)[^。]{0,20}月[^。]{0,10}反应的基础伤害[：:]"
    r"[^。]*?每\s*(\d*)\s*点?\s*\1?[^。]*?(?:提升|提高)\s*(\d+(?:\.\d+)?)\s*%"
    r"[^。]*?至多[^。]*?(\d+(?:\.\d+)?)\s*%"
)
# 月曜缩放变体2（奥黛塔星耀祝礼式）："…上述反应的基础伤害：每100点攻击力都将提升0.7%…至多…14%"
_LUNAR_SCALE_V2_RE = _re.compile(
    r"反应的基础伤害[：:][^。]*?每\s*(\d+)\s*点(攻击力|元素精通|生命值上限|防御力)"
    r"[^。]*?(?:提升|提高)\s*(\d+(?:\.\d+)?)\s*%[^。]*?至多[^。]*?(\d+(?:\.\d+)?)\s*%"
)

# flat 伤害加算-按自身属性百分比（克洛琳德破夜的明焰式）：
# "基于克洛琳德攻击力的20%，提升…造成的雷元素伤害"
_FLAT_DMG_FROM_ATTR_RE = _re.compile(
    r"基于\S{0,10}(攻击力|元素精通|生命值上限|防御力)的\s*(\d+(?:\.\d+)?)\s*%\s*[，,]"
    r"[^。]*?(?:提升|提高).{0,32}?(?:的)?(?:雷|火|水|冰|草|风|岩)?\s?元素伤害"
)

# flat 伤害加算-追加式（云堇莫从恒蹊式）："进一步追加云堇防御力的2.5%/5%/7.5%/11.5%"
_FLAT_DMG_APPEND_RE = _re.compile(
    r"(?:进一步)?追加\S{0,8}(攻击力|元素精通|生命值上限|防御力)的\s*([\d.%/和\s]+?)(?:[。，,]|$)"
)

# 属性线性转增伤-无cap变体（坎蒂丝漫沙陨穹式）：
# "坎蒂丝每1000点生命值上限会使这次伤害提高0.5%"
_ATTR_SCALE_NOCAP_RE = _re.compile(
    r"每\s*(\d+)\s*点(攻击力|元素精通|生命值上限|防御力)会使这次伤害将?(?:提高|提升)\s*(\d+(?:\.\d+)?)\s*%"
)
_LUNAR_SRC_MAP = {"攻击力": "atk", "元素精通": "em", "生命值上限": "hp", "防御力": "def"}

# 满层覆盖（魈式递增："至多获得25%伤害加成"→ 按满层数值计）
_DMG_CAP_RE = _re.compile(r"至多获得\s*(\d+(?:\.\d+)?)\s*%伤害加成")

# ---- 机制型天赋数值解析（丝柯克万流归寂/可莉火花魔法等）----
# 技能倍率层数提升："普通攻击造成原本110%/120%/170%的伤害"（带技能关键词）
_TALENT_MULT_RE = _re.compile(
    r"(下落攻击|普通攻击|元素爆发|元素战技|重击)[^。]{0,60}?造成原本\s*"
    r"((?:\d+(?:\.\d+)?%[/／])+)?\s*(\d+(?:\.\d+)?)%\s*的伤害"
)
# 技能倍率层数提升-无关键词变体（雅珂达式："造成原本130%的伤害"，视为元素爆发段）
_TALENT_MULT_NOKEY_RE = _re.compile(
    r"造成原本\s*((?:\d+(?:\.\d+)?%[/／])+)?\s*(\d+(?:\.\d+)?)%\s*的伤害"
)
_TM_SKILL_MAP = {"普通攻击": "normal", "重击": "charged",
                 "下落攻击": "charged", "元素爆发": "burst", "元素战技": "skill"}

# 额外一段伤害（烟绯/八重神子/伊涅芙/欧洛伦式）：来源属性×X% 的独立追加命中
_EXTRA_HIT_VARIANTS = [
    # "造成相当于伊涅芙攻击力65%的 雷元素范围伤害"（「的」可省略）
    _re.compile(
        r"造成相当于[^。，；]{0,14}(攻击力|生命值上限|防御力|元素精通)的?\s*"
        r"(\d+(?:\.\d+)?)\s*%"
    ),
    # "会额外造成一次80%攻击力的 火元素范围伤害"/"额外造成180%攻击力的伤害"
    _re.compile(
        r"额外造成(?:一次)?\s*(\d+(?:\.\d+)?)\s*%(?:的)?"
        r"(攻击力|生命值上限|防御力|元素精通)"
    ),
    # "分别造成35%攻击力的 风元素伤害"（流浪者）
    _re.compile(
        r"分别造成\s*(\d+(?:\.\d+)?)\s*%(?:的)?"
        r"(攻击力|生命值上限|防御力|元素精通)"
    ),
    # "将附加200%攻击力的对应元素伤害"（枫原万叶）
    _re.compile(
        r"附加(?:原本)?\s*(\d+(?:\.\d+)?)\s*%(?:的)?"
        r"(攻击力|生命值上限|防御力|元素精通)"
    ),
    # "基于攻击力的80%提高造成的伤害"（林尼）/
    # "基于生命值上限的15%/30%/45%提高…伤害"（玛拉妮，多档取最大）
    _re.compile(
        r"基于[^。，；]{0,10}(攻击力|生命值上限|防御力)的\s*"
        r"((?:\d+(?:\.\d+)?%[/／])*\d+(?:\.\d+)?)\s*%提高"
    ),
    # 数值在属性前（八重神子式）："造成相当于八重神子40%攻击力的 雷元素伤害"
    _re.compile(
        r"(?:造成|伤害)相当于[^。，；\d]{0,10}(\d+(?:\.\d+)?)\s*%\s*(?:的)?"
        r"(攻击力|生命值上限|防御力|元素精通)"
    ),
    # 属性直接跟数值（布伦妮式）："造成布伦妮攻击力150%的对应类型的元素伤害"
    _re.compile(
        r"(?:造成|附加)[^。，；%，]{0,10}(攻击力|生命值上限|防御力|元素精通)"
        r"\s*(\d+(?:\.\d+)?)\s*%"
    ),
    # 条件独立命中（欧洛伦式）："基于欧洛伦攻击力的160%，对周围…敌人造成…伤害"
    _re.compile(
        r"基于[^。，；]{0,10}(攻击力|生命值上限|防御力)的\s*(\d+(?:\.\d+)?)\s*%"
        r"\s*[，,][^。]*?对[^。]*?造成"
    ),
]

# 全伤害增幅（杜林混沌如黑夜构成式）：
# "每100点攻击力都将额外造成相当于原本3%的伤害，至多…75%"
# 奥黛塔变体省略"相当于"，且可限定反应伤害（scope=reaction）
_DAMAGE_AMP_RE = _re.compile(
    r"每\s*(\d+(?:\.\d+)?)\s*点(攻击力|生命值上限|防御力|元素精通)"
    r"[^。]*?额外造成(?:相当于)?原本\s*(\d+(?:\.\d+)?)\s*%的伤害[^。]*?"
    r"至多[^。]*?(\d+(?:\.\d+)?)\s*%"
)

# 敌人双元素抗性降低（夏沃蕾尖兵协同战法式）：
# "火元素 与 雷元素 抗性降低40%"
_ENEMY_RES_SHRED_MULTI_RE = _re.compile(
    r"(火|水|雷|冰|风|岩|草)元素\s*(?:与|和)\s*(火|水|雷|冰|风|岩|草)元素\s*抗性(?:降低|下降)\s*(\d+(?:\.\d+)?)\s*%"
)
# 敌人全抗性降低（希格雯急性剂量式）："所有元素抗性和物理抗性下降10%"
_ENEMY_RES_SHRED_ALL_RE = _re.compile(
    r"所有元素抗性和物理抗性(?:下降|降低)\s*(\d+(?:\.\d+)?)\s*%"
)
# 自身暴击率降低（珊瑚宫心海庙算无遗式）："暴击率降低100%"
_CRIT_DOWN_RE = _re.compile(r"暴击率(?:降低|下降)\s*(\d+(?:\.\d+)?)\s*%")


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

    # 前置语序规则（"提高10%攻击力"：数值在前、属性名在后）
    for pattern, attr, vtype in _PRE_ORDER_RULES:
        pm = pattern.search(text)
        if not pm:
            continue
        val = float(pm.group(1))
        if vtype == "pct":
            val /= 100.0
        # 与常规规则同键叠加
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
            "cap": None,                    # 无上限
            "stat": "elemental_dmg_bonus",
            "text": em2.group(0),
        }
    else:
        emb = _ER_SCALE_B_RE.search(text)
        if emb:
            er_scaling = {
                "threshold": 1.0,
                "per_unit": float(emb.group(2)) / 100.0,
                "cap": None,
                "stat": "elemental_dmg_bonus",
                "element": emb.group(1),
            }
    if er_scaling is None:
        # 变体（阿罗夏式）：从第 1 点充能即生效，含上限
        em3 = _ER_SCALE_V2_RE.search(text)
        if em3:
            er_scaling = {
                "threshold": 0.0,
                "per_unit": float(em3.group(1)) / 100.0,
                "cap": float(em3.group(2)) / 100.0,
                "stat": "dmg_bonus",
                "text": em3.group(0),
            }
    if er_scaling is not None:
        # 充能转伤害已结构化，移除通用规则对同一数值的误捕（避免双重计算）
        modifiers.pop("elemental_dmg_bonus", None)

    # 属性超阈值转反应增伤（奥黛塔式）
    atk_over_scaling = None
    aom = _ATK_OVER_RE.search(text)
    if aom:
        src_key = _OVER_SRC_MAP[aom.group(1)]
        stat = "lunar_dmg_bonus" if ("月" in aom.group(0) or "星" in aom.group(0)) else "elemental_dmg_bonus"
        atk_over_scaling = {
            "source": src_key,
            "threshold": float(aom.group(2)),       # 超过该值的部分才开始计算
            "per_points": float(aom.group(3)),      # 每多少点一个步长
            "bonus_per": float(aom.group(4)) / 100.0,
            "cap": float(aom.group(5)) / 100.0,
            "stat": stat,
        }

    dm = _DEF_IGNORE_RE.search(text)
    if dm:
        modifiers["def_ignore"] = modifiers.get("def_ignore", 0.0) + float(dm.group(1)) / 100.0

    am = _AMPLIFY_RE.search(text)
    amplify_hit = bool(am)

    # ---- 扩展类型解析 v2 ----
    # 敌人防御降低
    eds = _ENEMY_DEF_SHRED_RE.search(text)
    if eds:
        modifiers["enemy_def_shred"] = modifiers.get("enemy_def_shred", 0.0) + float(eds.group(1)) / 100.0

    # 敌人元素抗性降低 {element: value}
    res_shred = None
    rm = _ENEMY_RES_SHRED_RE.search(text)
    if rm:
        res_shred = {"element": rm.group(1), "value": float(rm.group(2)) / 100.0}

    # 技能等级提高 {"normal"/"skill"/"burst": n}
    talent_level_up = None
    for lm in _TALENT_LV_RE.finditer(text):
        key = _TALENT_LV_MAP[lm.group(1)]
        talent_level_up = talent_level_up or {}
        talent_level_up[key] = max(talent_level_up.get(key, 0), int(lm.group(2)))

    # 全队精通共享 / 精通转元素伤共享
    team_effects = []
    tem = _TEAM_EM_FLAT_RE.search(text)
    if tem:
        team_effects.append({"type": "em_share", "flat": float(tem.group(1))})
    tem2 = _TEAM_EM_PCT_RE.search(text)
    if tem2:
        team_effects.append({"type": "em_share", "pct": float(tem2.group(1)) / 100.0, "from": "em"})
    tem3 = _TEAM_EM_FROM_ATTR_RE.search(text)
    if tem3 and not tem2:
        team_effects.append({
            "type": "em_share", "pct": float(tem3.group(2)) / 100.0,
            "from": _OVER_SRC_MAP[tem3.group(1)],
        })
    # 纳西妲式：按全队最高精通的 X%，至多 N 点
    tem4 = _TEAM_EM_MAX_RE.search(text)
    if tem4:
        team_effects.append({
            "type": "em_share", "pct": float(tem4.group(1)) / 100.0,
            "from": "em_max", "cap": float(tem4.group(2)),
        })
        # 该效果的数值已被团队共享结构化，移除通用规则误捕的自身固定精通
        modifiers.pop("elemental_mastery", None)
    # 莉奈娅式：提升值基于自身某属性的 X%（跨句）
    tem5 = _TEAM_EM_FROM_ATTR2_RE.search(text)
    if tem5 and not (tem2 or tem3 or tem4):
        team_effects.append({
            "type": "em_share", "pct": float(tem5.group(2)) / 100.0,
            "from": _OVER_SRC_MAP[tem5.group(1)],
        })
    # 琳妮特式：全队攻击力共享（取最高档，条件型）
    tas = _TEAM_ATK_SHARE_RE.search(text)
    if tas:
        best = max(float(x) for x in _re.findall(r"(\d+(?:\.\d+)?)", tas.group(1)))
        team_effects.append({"type": "atk_share", "pct": best / 100.0})
    emd = _EM_TO_DMG_RE.search(text)
    if emd:
        team_effects.append({"type": "em_to_elemental_dmg", "ratio": float(emd.group(1)) / 100.0})

    # flat 伤害加算（伤害值提升=来源属性×X%；多档位取最大档）
    flat_dmg_scaling = None
    fds = _FLAT_DMG_SCALE_RE.search(text)
    if not fds:
        # 叶洛亚变体："伤害，提升值相当于叶洛亚元素精通的7%/14%/24%"
        fds = _re.search(
            r"伤害[^。]{0,4}[，,]\s*提升值相当于\S{0,8}(元素精通|攻击力|防御力|生命值上限)的\s*[\d.%/和]+",
            text,
        )
    if fds:
        nums = [float(x) for x in _re.findall(r"(\d+(?:\.\d+)?)", fds.group(0))]
        if nums:
            flat_dmg_scaling = {
                "source": _LUNAR_SRC_MAP[fds.group(1)],
                "ratio": max(nums) / 100.0,
                "text": fds.group(0),
            }
    if flat_dmg_scaling is None:
        # 赛诺变体："提高自身以下攻击造成的伤害值：·普通攻击：元素精通的150%；…"
        if _re.search(r"伤害值[：:]", text) and _re.search(r"元素精通的\s*\d", text):
            all_ratios = _re.findall(r"元素精通的\s*(\d+(?:\.\d+)?)\s*%", text)
            if all_ratios:
                flat_dmg_scaling = {
                    "source": "em",
                    "ratio": max(float(x) for x in all_ratios) / 100.0,
                    "text": "伤害值提升（取最高档）",
                }
    if flat_dmg_scaling is None:
        # 克洛琳德式："基于X的攻击力的20%，提升…雷元素伤害"
        fda = _FLAT_DMG_FROM_ATTR_RE.search(text)
        if fda:
            flat_dmg_scaling = {
                "source": _LUNAR_SRC_MAP[fda.group(1)],
                "ratio": float(fda.group(2)) / 100.0,
                "text": fda.group(0),
            }
    if flat_dmg_scaling is None:
        # 云堇追加式："进一步追加云堇防御力的2.5%/5%/7.5%/11.5%"
        fdap = _FLAT_DMG_APPEND_RE.search(text)
        if fdap:
            nums = [float(x) for x in _re.findall(r"(\d+(?:\.\d+)?)", fdap.group(2))]
            if nums:
                flat_dmg_scaling = {
                    "source": _LUNAR_SRC_MAP[fdap.group(1)],
                    "ratio": max(nums) / 100.0,
                    "text": fdap.group(0),
                }

    # 属性线性转自身增伤（艾梅莉埃精馏式，threshold=0）
    attr_scaling = None
    asm = _ATTR_SCALE_RE.search(text)
    if not asm:
        # 坎蒂丝变体（无 cap）："坎蒂丝每1000点生命值上限会使这次伤害提高0.5%"
        asm2 = _ATTR_SCALE_NOCAP_RE.search(text)
        if asm2:
            attr_scaling = {
                "source": _LUNAR_SRC_MAP[asm2.group(2)],
                "per_points": float(asm2.group(1)),
                "bonus_per": float(asm2.group(3)) / 100.0,
                "cap": None,
                "stat": "elemental_dmg_bonus",
            }
    if asm and attr_scaling is None:
        attr_scaling = {
            "source": _LUNAR_SRC_MAP[asm.group(1)],
            "per_points": float(asm.group(2)),
            "bonus_per": float(asm.group(3)) / 100.0,
            "cap": float(asm.group(4)) / 100.0,
            "stat": "elemental_dmg_bonus",
        }

    # ---- 机制型天赋数值解析 v3 ----
    # 自身暴击率降低（心海庙算无遗式）
    cdm = _CRIT_DOWN_RE.search(text)
    if cdm:
        modifiers["crit_rate"] = modifiers.get("crit_rate", 0.0) - float(cdm.group(1)) / 100.0

    # 敌人双元素/全抗性降低（夏沃蕾/希格雯式；单元素版已在上方处理）
    if res_shred is None:
        rsm = _ENEMY_RES_SHRED_MULTI_RE.search(text)
        if rsm:
            res_shred = {
                "element": rsm.group(1), "element2": rsm.group(2),
                "value": float(rsm.group(3)) / 100.0,
            }
        else:
            rsa = _ENEMY_RES_SHRED_ALL_RE.search(text)
            if rsa:
                res_shred = {"element": "all", "value": float(rsa.group(1)) / 100.0}

    # 技能倍率层数提升（万流归寂/火花魔法/法尔伽/那维莱特式）：
    # {"skill_types": {normal: [1.10,1.20,1.70], burst: [...]}}
    talent_multiplier = None
    tm_tiers = {}
    for tmm in _TALENT_MULT_RE.finditer(text):
        nums = [
            float(x) / 100.0
            for x in _re.findall(r"(\d+(?:\.\d+)?)\s*%", tmm.group(2) or "") + [tmm.group(3)]
        ]
        # 条件强化档（法尔伽式："则会使上述效果提升至220%"）追加为更高档
        boost = _re.search(r"提升至\s*(\d+(?:\.\d+)?)\s*%", text[tmm.end(): tmm.end() + 120])
        if boost:
            nums.append(float(boost.group(1)) / 100.0)
        # 命中文段内的全部技能关键词均获得该档位（法尔伽式："普通攻击、重击…元素战技…造成原本140%"）
        keys = [_TM_SKILL_MAP[k] for k in _TM_SKILL_MAP if k in tmm.group(0)]
        for key in keys:
            prev = tm_tiers.get(key) or []
            tm_tiers[key] = [max(a, b) for a, b in zip(prev + [0.0] * len(nums), nums)] \
                if prev else nums
    if not tm_tiers and not (_DAMAGE_AMP_RE.search(text) or "额外造成原本" in text):
        tnk = _TALENT_MULT_NOKEY_RE.search(text)
        if tnk:
            nums = [
                float(x) / 100.0
                for x in _re.findall(r"(\d+(?:\.\d+)?)\s*%", tnk.group(1) or "") + [tnk.group(2)]
            ]
            tm_tiers["burst"] = nums
    if tm_tiers:
        talent_multiplier = {"skill_types": tm_tiers}

    # 额外一段伤害（烟绯/八重神子/伊涅芙式）：取全部命中中的最大倍率
    extra_hit = None

    def _extract_ratio_attr(groups):
        """从变体命中组中提取 (倍率, 属性)；数值组可能是多档字符串（取最大）。"""
        num_g = next(
            g for g in groups
            if g and (_re.fullmatch(r"\d+(?:\.\d+)?", g) or "%" in g)
        )
        attr_g = next(g for g in groups if g and g != num_g)
        nums = [float(x) for x in _re.findall(r"(\d+(?:\.\d+)?)", num_g)]
        return max(nums) / 100.0, attr_g

    best_ratio, best_src = 0.0, None
    for variant in _EXTRA_HIT_VARIANTS:
        for evm in variant.finditer(text):
            ratio, attr_g = _extract_ratio_attr(list(evm.groups()))
            if ratio > best_ratio:
                best_ratio, best_src = ratio, _LUNAR_SRC_MAP[attr_g]
    if best_src is not None:
        extra_hit = {"source": best_src, "ratio": best_ratio}

    # 全伤害增幅（杜林/奥黛塔式）：每X点来源属性 → 伤害+N%，至多cap；
    # 若限定反应伤害（"星烁反应伤害"等），标记 scope=reaction
    damage_amp = None
    dam = _DAMAGE_AMP_RE.search(text)
    if dam:
        damage_amp = {
            "source": _LUNAR_SRC_MAP[dam.group(2)],
            "per_points": float(dam.group(1)),
            "per_bonus": float(dam.group(3)) / 100.0,
            "cap": float(dam.group(4)) / 100.0,
            "scope": "reaction" if "反应" in dam.group(0) else None,
        }

    # 月曜反应基础伤害缩放
    lunar_scaling = None
    lsm = _LUNAR_SCALE_RE.search(text)
    if not lsm:
        lsm = _LUNAR_SCALE_V2_RE.search(text)
        if lsm:
            lunar_scaling = {
                "source": _LUNAR_SRC_MAP[lsm.group(2)],
                "per_points": float(lsm.group(1)),
                "bonus_per": float(lsm.group(3)) / 100.0,
                "cap": float(lsm.group(4)) / 100.0,
                "stat": "lunar_dmg_bonus",
            }
    if lsm and lunar_scaling is None:
        lunar_scaling = {
            "source": _LUNAR_SRC_MAP[lsm.group(1)],
            "per_points": float(lsm.group(2)) if lsm.group(2) else 1.0,
            "bonus_per": float(lsm.group(3)) / 100.0,
            "cap": float(lsm.group(4)) / 100.0,
            "stat": "lunar_dmg_bonus",
        }

    # 满层覆盖（魈式递增："至多获得25%伤害加成"→ 按满层数值计入，UI 条件开关控制启停）
    cm2 = _DMG_CAP_RE.search(text)
    if cm2 and "dmg_bonus" in modifiers:
        modifiers["dmg_bonus"] = float(cm2.group(1)) / 100.0

    conditional = any(w in text for w in _CONDITION_WORDS)

    # 血量条件阈值（"生命值低于或等于50%" → 0.5）
    hp_threshold = None
    hm = _re.search(r"生命值[^。%]{0,6}(?:低于或等于|低于|低于等于)\s*(\d+(?:\.\d+)?)\s*%", text)
    if hm:
        hp_threshold = float(hm.group(1)) / 100.0

    computable = (
        modifiers or conversion is not None or er_scaling is not None or amplify_hit
        or res_shred or talent_level_up or team_effects or lunar_scaling
        or atk_over_scaling is not None or flat_dmg_scaling is not None
        or attr_scaling is not None
        or talent_multiplier is not None or extra_hit is not None
        or damage_amp is not None
    )

    # 三级分类：stat=数值型已结构化；mechanism=纯机制（冷却/能量/召唤物行为等，不参与面板计算）；
    # unparsed=未能识别（理论上不应出现）
    category = "stat" if computable else ("mechanism" if _is_mechanism(text) else "unparsed")

    return {
        "modifiers": modifiers,
        "conditional": conditional,
        "hp_threshold": hp_threshold,
        "conversion": conversion,
        "er_scaling": er_scaling,
        "amplify_reaction": amplify_hit and not (modifiers or conversion or er_scaling),
        "res_shred": res_shred,
        "talent_level_up": talent_level_up,
        "team_effects": team_effects,
        "lunar_scaling": lunar_scaling,
        "atk_over_scaling": atk_over_scaling,
        "flat_dmg_scaling": flat_dmg_scaling,
        "attr_scaling": attr_scaling,
        "talent_multiplier": talent_multiplier,
        "extra_hit": extra_hit,
        "damage_amp": damage_amp,
        "category": category,
        "unparsed": not computable,
    }


# 纯机制类天赋关键词（不参与伤害面板计算的战斗/生活机制）
_MECHANISM_WORDS = [
    "冷却", "持续时间", "持续期间延长", "元素能量", "微粒", "晶球", "体力", "小地图",
    "合成", "锻造", "烹饪", "料理", "食材", "治疗", "回复量", "恢复生命值", "护盾",
    "引雷", "断流效果", "虚影", "重置", "附魔", "协同", "发射", "掉落", "附加",
    "移动速度", "攻击速度", "蓄力时间", "概率", "产出", "派遣", "特产", "矿脉",
    "魔导", "夜魂值", "燃素", "积攒", "层数", "距离提高", "不会消耗", "击飞",
    "抗打断", "迅行", "寻宝罗盘", "虚境裂隙", "雷暴云", "华彩", "祝颂", "加固包装",
    "摩拉", "木材", "晶蝶", "生物", "上升气流", "生命之契", "琢光镜", "抗性提升",
    "草露", "上升一级", "耐力", "留影", "投掷", "变格", "愿力", "杀生樱",
    "恢复等同于", "恢复300点", "攻击力降低", "辣椒", "白玉萝卜", "圣裁之雷",
    "范围伤害 ", "额外造成一次", "额外引发一次", "落雷", "召唤出", "降下",
    "最高伤害加成", "立即爆发", "二段蓄力的形式", "完成蓄力", "采集物",
    "物理抗性", "柔灯之匣", "虚己之赐", "升变", "启途誓使状态，持续",
    "持续对身边的敌人造成", "赋予「新叶」",
]


def _is_mechanism(text: str) -> bool:
    return any(w in text for w in _MECHANISM_WORDS)
