"""
原神伤害计算器 - 常量配置文件
存放所有可调的常数与公式参数。
"""

# ==================== 等级系数 ====================
# 剧变/月反应间接伤害等级系数（90级）
# 已对照 gensri.wiki《游戏机制》附录等级系数表校验（90 级 = 1446.853）
LEVEL_COEFFICIENT = 1446.853

# ==================== 精通增益公式 ====================
def em_bonus_transformative(em: float) -> float:
    """剧变反应精通增益"""
    return 16 * em / (em + 2000)

def em_bonus_amplifying(em: float) -> float:
    """增幅反应精通增益"""
    return 2.78 * em / (em + 1400)

def em_bonus_lunar(em: float) -> float:
    """月反应精通增益（暂用剧变公式，可配置）"""
    return 16 * em / (em + 2000)

# ==================== 反应系数 ====================
# 增幅反应系数（触发元素 → 被击元素）
# 已对照 meropide.cn《伤害公式》校验：蒸发 水打火2/火打水1.5；融化 火打冰2/冰打火1.5
AMPLIFY_COEFF = {
    ("Hydro", "Pyro"): 2.0,    # 水→火 蒸发（水打火）
    ("Pyro", "Hydro"): 1.5,    # 火→水 蒸发（火打水）
    ("Cryo", "Pyro"): 1.5,     # 冰→火 融化（冰打火）
    ("Pyro", "Cryo"): 2.0,     # 火→冰 融化（火打冰）
}

# 月反应系数
# 已对照 gensri.wiki《游戏机制》校验：月感电（雷暴云）3.0、月结晶（月笼谐奏）1.6
# 注：gensri 明确标注"前玉衡杯提供的反应系数以及贡献权重有误，以此处为准"
LUNAR_REACTION_COEFF = {
    "lunar_charged": {"indirect": 3.0, "direct": 3.0},       # 月感电
    "lunar_crystallize": {"indirect": 1.6, "direct": 1.6},   # 月结晶
    "lunar_bloom": {"indirect": 0.0, "direct": 1.0},         # 月绽放（直伤月乘区 1.0）
}

# 月反应间接伤害加权系数（按个人贡献从高到低排序后）
# gensri 权威值：第1×0.6 + 第2×0.3 + 第3×0.05 + 第4×0.05
LUNAR_INDIRECT_WEIGHTS = [0.6, 0.3, 0.05, 0.05]

# ==================== 激化反应系数 ====================
# gensri 权威值：超激化 1.15，蔓激化 1.25
AGGRAVATE_COEFF = 1.15   # 超激化（雷元素触发）
SPREAD_COEFF = 1.25      # 蔓激化（草元素触发）

# ==================== 剧变反应系数 ====================
# gensri 权威值（V5.2.0 增强后）：碎冰 3.0、超/烈绽放 3.0、超载 2.75、
# 绽放 2.0、感电 2.0、超导 1.5、扩散 0.6、燃烧 0.25
TRANSFORMATIVE_COEFF = {
    "overload": 2.75,        # 超载
    "superconduct": 1.5,     # 超导
    "swirl": 0.6,            # 扩散
    "shatter": 3.0,          # 碎冰
    "electrocharged": 2.0,   # 感电
    "bloom": 2.0,            # 绽放
    "hyperbloom": 3.0,       # 超绽放
    "burgeon": 3.0,          # 烈绽放
    "burning": 0.25,         # 燃烧
}

# ==================== 星超导参数 ====================
STELLAR_SUPERCONDUCT = {
    "res_decrease": 0.40,  # 降低 40% 物理抗性
    "stacks_6": {"dmg_bonus": 0.34, "reaction_coef": 1.7},
    "stacks_12": {"dmg_bonus": 0.40, "reaction_coef": 2.0},
}


def stellar_superconduct_params(records: int) -> dict:
    """
    星超导连续档位公式（gensri.wiki 权威值）：
    - 记录次数 = 0：反应系数 1.00，雷/冰伤加成 20%
    - 记录次数 = 1：反应系数 1.45，雷/冰伤加成 29%
    - 记录次数 > 1：每次 +0.05 反应系数 / +1% 加成
    - 上限（12 次记录）：反应系数 2.0，加成 40%
    """
    n = max(int(records), 0)
    if n == 0:
        coef, bonus = 1.00, 0.20
    else:
        coef = min(1.45 + (n - 1) * 0.05, 2.0)
        bonus = min(0.29 + (n - 1) * 0.01, 0.40)
    return {"reaction_coef": coef, "dmg_bonus": bonus}

# ==================== 抗性区计算 ====================
def resistance_factor(res: float) -> float:
    """
    抗性区计算
    - 0 <= RES <= 0.75: 1 - RES
    - RES < 0: 1 - RES/2
    - RES > 0.75: 1/(4*RES + 1)
    """
    if res < 0:
        return 1 - res / 2
    elif res <= 0.75:
        return 1 - res
    else:
        return 1 / (4 * res + 1)

# ==================== 防御区计算 ====================
def defense_factor(char_level: int, enemy_level: int) -> float:
    """防御区 = (char_level + 100) / (char_level + 100 + enemy_level + 100)"""
    return (char_level + 100) / (char_level + 100 + enemy_level + 100)

# ==================== 元素类型映射 ====================
ELEMENT_MAP = {
    "Fire": "火", "Water": "水", "Grass": "草", "Electric": "雷",
    "Ice": "冰", "Wind": "风", "Rock": "岩", "None": "物理",
    "火": "火", "水": "水", "草": "草", "雷": "雷",
    "冰": "冰", "风": "风", "岩": "岩", "物理": "物理",
}

# 技能类型映射（内部统一使用）
SKILL_TYPE_MAP = {
    "normal": "normal_attack",
    "skill": "elemental_skill",
    "burst": "elemental_burst",
    "normal_attack": "normal_attack",
    "elemental_skill": "elemental_skill",
    "elemental_burst": "elemental_burst",
    "passive": "passive",
}