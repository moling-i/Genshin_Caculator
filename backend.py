from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI(title="原神伤害计算器API", version="2.0.0")


# ==================== 核心伤害计算类 ====================

class GenshinDamageCalculator:
    """
    原神伤害计算器核心类
    依据技术规格书实现：
      - 通用乘区（基础伤害/增伤/防御/抗性/暴击）
      - 常规元素反应（增幅/剧变/激化/结晶）
      - 月反应 Lunar（间接伤害 / 直接伤害）
      - 星反应 Stellar（星超导，预留可配置）
    """

    # 等级系数表（90级 = 1446.85，其余插值）
    LEVEL_COEF_TABLE = {
        1: 17.16, 10: 29.84, 20: 56.52, 30: 95.06, 40: 138.90,
        50: 206.85, 60: 341.50, 70: 543.98, 80: 852.12,
        85: 1052.18, 90: 1446.85,
    }

    # 月反应间接伤害系数
    LUNAR_INDIRECT_COEF = {
        "lunar_electro": 1.8,       # 月感电
        "lunar_crystallize": 0.96,  # 月结晶
        "lunar_bloom": 0.0,         # 月绽放（间接无伤害）
    }

    # 月反应直接伤害系数
    LUNAR_DIRECT_COEF = {
        "lunar_electro": 3.0,       # 月感电
        "lunar_crystallize": 1.6,   # 月结晶
        "lunar_bloom": 1.0,         # 月绽放
    }

    # 增幅反应系数（蒸发/融化）
    AMPLIFY_COEF = {
        "water_to_fire": 2.0,   # 水→火 2.0
        "fire_to_water": 1.5,   # 火→水 1.5
        "ice_to_fire": 2.0,     # 冰→火 2.0
        "fire_to_ice": 1.5,     # 火→冰 1.5
    }

    # 星超导物理减抗
    STELLAR_RES_REDUCTION = 0.40

    # 星超导附着次数加成表
    STELLAR_BUFF_TABLE = {
        6:  {"dmg_bonus": 0.34, "reaction_coef": 1.7},
        12: {"dmg_bonus": 0.40, "reaction_coef": 2.0},
    }

    def __init__(self, char_level: float = 90.0, enemy_level: float = 90.0):
        self.char_level = char_level
        self.enemy_level = enemy_level

    # ---------- 通用乘区 ----------

    @staticmethod
    def base_damage(atk: float, talent_ratio: float, flat_bonus: float = 0.0) -> float:
        """基础伤害区: base = ATK * talent_ratio + flat_bonus"""
        return atk * talent_ratio + flat_bonus

    @staticmethod
    def dmg_bonus_factor(elemental_dmg_bonus: float = 0.0, other_dmg_bonus: float = 0.0) -> float:
        """增伤区: 1 + 元素伤害加成 + 其他伤害加成"""
        return 1.0 + elemental_dmg_bonus + other_dmg_bonus

    def defense_factor(self) -> float:
        """防御区: (char_level+100) / (char_level+100 + enemy_level+100)"""
        return (self.char_level + 100) / (self.char_level + 100 + self.enemy_level + 100)

    @staticmethod
    def resistance_factor(res: float) -> float:
        """
        抗性区:
        - 0 <= RES <= 0.75: 1 - RES
        - RES < 0: 1 - RES/2
        - RES > 0.75: 1 / (4*RES + 1)
        """
        if res < 0:
            return 1.0 - res / 2
        elif res <= 0.75:
            return 1.0 - res
        else:
            return 1.0 / (4 * res + 1)

    @staticmethod
    def crit_factor(crit_rate: float = 0.0, crit_dmg: float = 0.0, is_crit: bool = False) -> float:
        """
        暴击区:
        - 明确暴击时: 1 + crit_dmg
        - 期望值: 1 + crit_rate * crit_dmg
        """
        if is_crit:
            return 1.0 + crit_dmg
        return 1.0 + crit_rate * crit_dmg

    # ---------- 精通增益 ----------

    @staticmethod
    def em_bonus_amplify(em: float) -> float:
        """增幅反应精通增益: 2.78 * EM / (EM + 1400)"""
        return 2.78 * em / (em + 1400) if em > 0 else 0.0

    @staticmethod
    def em_bonus_transformative(em: float) -> float:
        """剧变反应精通增益: 16 * EM / (EM + 2000)"""
        return 16 * em / (em + 2000) if em > 0 else 0.0

    @staticmethod
    def em_bonus_lunar(em: float) -> float:
        """月反应精通增益（暂用剧变公式，可配置）: 16 * EM / (EM + 2000)"""
        return 16 * em / (em + 2000) if em > 0 else 0.0

    # ---------- 等级系数 ----------

    def level_coefficient(self, level: float) -> float:
        """根据等级获取等级系数（线性插值）"""
        if level <= 1:
            return self.LEVEL_COEF_TABLE[1]
        if level >= 90:
            return self.LEVEL_COEF_TABLE[90]

        levels = sorted(self.LEVEL_COEF_TABLE.keys())
        for i in range(len(levels) - 1):
            low_lv, high_lv = levels[i], levels[i + 1]
            if low_lv <= level <= high_lv:
                low_coef = self.LEVEL_COEF_TABLE[low_lv]
                high_coef = self.LEVEL_COEF_TABLE[high_lv]
                t = (level - low_lv) / (high_lv - low_lv)
                return low_coef + t * (high_coef - low_coef)
        return self.LEVEL_COEF_TABLE[90]

    # ---------- 常规元素反应 ----------

    def amplify_reaction(
        self,
        atk: float,
        talent_ratio: float,
        em: float,
        reaction_coef: float,
        elemental_dmg_bonus: float = 0.0,
        other_dmg_bonus: float = 0.0,
        crit_rate: float = 0.0,
        crit_dmg: float = 0.0,
        is_crit: bool = False,
        enemy_resistance: float = 0.0,
        flat_bonus: float = 0.0,
    ) -> float:
        """
        增幅反应（蒸发/融化）
        最终伤害 = 基础伤害区 × 增伤区 × 防御区 × 抗性区 × 暴击区 × 反应系数 × 精通增益
        """
        base = self.base_damage(atk, talent_ratio, flat_bonus)
        return (
            base
            * self.dmg_bonus_factor(elemental_dmg_bonus, other_dmg_bonus)
            * self.defense_factor()
            * self.resistance_factor(enemy_resistance)
            * self.crit_factor(crit_rate, crit_dmg, is_crit)
            * reaction_coef
            * (1 + self.em_bonus_amplify(em))
        )

    def transformative_reaction(
        self,
        em: float,
        enemy_resistance: float = 0.0,
        char_level: float = 90.0,
        level_coef: Optional[float] = None,
    ) -> float:
        """
        剧变反应（超载/超导/扩散/碎冰/感电）
        伤害 = 等级系数 × (1 + 精通增益) × 抗性区
        不暴击，不受攻击/增伤影响
        """
        if level_coef is None:
            level_coef = self.level_coefficient(char_level)
        return (
            level_coef
            * (1 + self.em_bonus_transformative(em))
            * self.resistance_factor(enemy_resistance)
        )

    def aggravate_spread_flat(
        self,
        char_level: float = 90.0,
        em: float = 0.0,
        level_coef: Optional[float] = None,
    ) -> float:
        """
        激化反应（超激化/蔓激化）提供的 flat_bonus
        flat_bonus = 等级系数 × 1.15 × (1 + 5*EM/(EM+1200))
        该加成后续受增伤、暴击、防御、抗性影响
        """
        if level_coef is None:
            level_coef = self.level_coefficient(char_level)
        em_part = (1 + 5 * em / (em + 1200)) if em > 0 else 1.0
        return level_coef * 1.15 * em_part

    # ---------- 月反应 (Lunar) ----------

    def lunar_indirect_damage(
        self,
        participants: List[dict],
        reaction_type: str = "lunar_electro",
    ) -> dict:
        """
        月反应间接伤害（由元素反应触发）

        个人伤害_i = 反应系数 × 等级系数 × (1 + lunar_dmg_bonus_i)
                     × (1 + EM_bonus_i + reaction_dmg_bonus_i)
                     × 抗性区_i × 暴击区_i

        加权求和（取前四高）:
          最终 = 最高×1 + 第二高×1/2 + 第三高×1/12 + 第四高×1/12
        """
        coef = self.LUNAR_INDIRECT_COEF.get(reaction_type, 0.0)

        if coef == 0:
            return {
                "reaction_coef": coef,
                "individual_damages": [],
                "weights": [1.0, 0.5, 1.0 / 12, 1.0 / 12],
                "contributions": [],
                "final_damage": 0.0,
                "detail": f"{reaction_type} 间接伤害系数为0（月绽放间接无伤害，不计入）",
            }

        individual_damages = []
        for p in participants:
            char_level = p.get("char_level", 90.0)
            em = p.get("em", 0.0)
            lunar_bonus = p.get("lunar_dmg_bonus", 0.0)
            reaction_bonus = p.get("reaction_dmg_bonus", 0.0)
            res = p.get("enemy_resistance", 0.0)
            crit_rate = p.get("crit_rate", 0.0)
            crit_dmg = p.get("crit_dmg", 0.0)
            is_crit = p.get("is_crit", False)

            dmg = (
                coef
                * self.level_coefficient(char_level)
                * (1 + lunar_bonus)
                * (1 + self.em_bonus_lunar(em) + reaction_bonus)
                * self.resistance_factor(res)
                * self.crit_factor(crit_rate, crit_dmg, is_crit)
            )
            individual_damages.append({
                "char_level": char_level,
                "em": em,
                "lunar_dmg_bonus": lunar_bonus,
                "reaction_dmg_bonus": reaction_bonus,
                "enemy_resistance": res,
                "crit_rate": crit_rate,
                "crit_dmg": crit_dmg,
                "is_crit": is_crit,
                "damage": dmg,
            })

        # 从高到低排序
        individual_damages.sort(key=lambda x: x["damage"], reverse=True)
        damages = [d["damage"] for d in individual_damages]

        # 加权求和（只取前四高）
        weights = [1.0, 0.5, 1.0 / 12, 1.0 / 12]
        contributions = []
        for i, dmg in enumerate(damages[:4]):
            contributions.append(dmg * weights[i])

        final_damage = sum(contributions)

        return {
            "reaction_coef": coef,
            "individual_damages": individual_damages,
            "weights": weights[: len(contributions)],
            "contributions": contributions,
            "final_damage": final_damage,
            "detail": (
                f"{reaction_type} 间接伤害，反应系数={coef}，"
                f"前4高伤害加权求和（×1, ×1/2, ×1/12, ×1/12）"
            ),
        }

    def lunar_direct_damage(
        self,
        attribute_value: float,
        skill_ratio: float,
        em: float,
        reaction_type: str = "lunar_electro",
        lunar_dmg_bonus: float = 0.0,
        reaction_dmg_bonus: float = 0.0,
        flat_bonus: float = 0.0,
        enemy_resistance: float = 0.0,
        crit_rate: float = 0.0,
        crit_dmg: float = 0.0,
        is_crit: bool = False,
    ) -> float:
        """
        月反应直接伤害（由角色技能造成）

        直接伤害 = (反应系数 × 属性 × 倍率 × (1 + lunar_dmg_bonus)
                    × (1 + EM_bonus + reaction_dmg_bonus) + flat_bonus)
                    × 抗性区 × 暴击区
        """
        coef = self.LUNAR_DIRECT_COEF.get(reaction_type, 0.0)
        inner = (
            coef
            * attribute_value
            * skill_ratio
            * (1 + lunar_dmg_bonus)
            * (1 + self.em_bonus_lunar(em) + reaction_dmg_bonus)
            + flat_bonus
        )
        return inner * self.resistance_factor(enemy_resistance) * self.crit_factor(
            crit_rate, crit_dmg, is_crit
        )

    # ---------- 星反应 (Stellar) ----------

    def stellar_superconduct_buff(self, attachment_count: int) -> dict:
        """
        星超导（Stellar-Superconduct）
        - 触发：冰+雷，生成"极星辉域"领域
        - 效果：降低领域内敌人 40% 物理抗性
        - 附着次数加成（累计，上限12次）:
            >= 6次: ~34% 雷/冰元素伤害加成 + 1.7 反应系数
            >= 12次: ~40% 雷/冰元素伤害加成 + 2.0 反应系数
        """
        res_reduction = self.STELLAR_RES_REDUCTION

        if attachment_count >= 12:
            buff = self.STELLAR_BUFF_TABLE[12]
            tier = "max"
        elif attachment_count >= 6:
            buff = self.STELLAR_BUFF_TABLE[6]
            tier = "medium"
        else:
            buff = {"dmg_bonus": 0.0, "reaction_coef": 1.0}
            tier = "none"

        return {
            "attachment_count": attachment_count,
            "tier": tier,
            "res_reduction": res_reduction,
            "elemental_dmg_bonus": buff["dmg_bonus"],
            "reaction_coef": buff["reaction_coef"],
        }


# ==================== 数据模型 ====================

class DamageRequest(BaseModel):
    base_atk: float  # 基础攻击力
    bonus_atk: float  # 额外攻击力
    skill_ratio: float  # 技能倍率
    dmg_bonus: float  # 伤害加成
    other_bonus: float  # 其他增伤
    crit_rate: float  # 暴击率
    crit_dmg: float  # 暴击伤害
    reaction_multiplier: float  # 反应乘区
    independent_multiplier: float  # 独立乘区
    enemy_resistance: float  # 敌人抗性
    def_ignore: float  # 防御无视
    char_level: float = 90  # 角色等级（默认90）
    enemy_level: float = 90  # 怪物等级（默认90）

class DamageResponse(BaseModel):
    base_damage: float
    damage_with_bonus: float
    damage_with_crit: float
    final_damage: float
    total_atk: float
    total_bonus: float
    crit_multiplier: float
    res_multiplier: float
    def_multiplier: float

class ReactionRequest(BaseModel):
    em: float  # 元素精通
    base_reaction_multiplier: float  # 基础反应倍率（蒸发1.5/融化2.0/超载2.0等）
    reaction_type: str = "amplify"  # 反应类型: amplify / transformative

class ReactionResponse(BaseModel):
    reaction_bonus: float
    total_reaction_multiplier: float
    formula: str  # 实际使用的公式说明

class ReactionDamageRequest(BaseModel):
    """完整反应伤害计算请求"""
    reaction_type: str = "amplify"  # amplify / transformative / aggravate / spread

    # 通用参数
    em: float = 0
    enemy_resistance: float = 0.1
    char_level: float = 90
    enemy_level: float = 90

    # 增幅反应参数
    atk: float = 0
    talent_ratio: float = 0
    reaction_coef: float = 1.5  # 蒸发/融化系数
    elemental_dmg_bonus: float = 0
    other_dmg_bonus: float = 0
    crit_rate: float = 0
    crit_dmg: float = 0
    is_crit: bool = False
    flat_bonus: float = 0

    # 剧变/激化可选覆盖等级系数
    level_coef: Optional[float] = None

class ReactionDamageResponse(BaseModel):
    reaction_type: str
    damage: float
    em_bonus: float
    flat_bonus: float = 0
    formula: str
    detail: dict

class LunarParticipantModel(BaseModel):
    """月反应参与角色参数"""
    char_level: float = 90
    em: float = 0
    lunar_dmg_bonus: float = 0        # 月反应基础伤害加成
    reaction_dmg_bonus: float = 0     # 反应伤害加成
    enemy_resistance: float = 0.1
    crit_rate: float = 0
    crit_dmg: float = 0
    is_crit: bool = False

class LunarRequest(BaseModel):
    """月反应计算请求"""
    damage_type: str = "indirect"  # indirect / direct
    reaction_type: str = "lunar_electro"  # lunar_electro / lunar_crystallize / lunar_bloom

    # 间接伤害参数
    participants: List[LunarParticipantModel] = []

    # 直接伤害参数
    attribute_value: float = 0   # 属性值（攻击/生命/防御等）
    skill_ratio: float = 1.0     # 技能倍率
    em: float = 0
    lunar_dmg_bonus: float = 0
    reaction_dmg_bonus: float = 0
    flat_bonus: float = 0
    enemy_resistance: float = 0.1
    crit_rate: float = 0
    crit_dmg: float = 0
    is_crit: bool = False

class LunarResponse(BaseModel):
    damage_type: str
    reaction_type: str
    reaction_coef: float
    em_bonus: float
    final_damage: float
    formula: str
    detail: dict

class StellarRequest(BaseModel):
    """星反应计算请求"""
    attachment_count: int = 0              # 冰/雷附着次数（累计，上限12）
    base_physical_res: float = 0.1         # 敌人基础物理抗性
    base_elemental_dmg_bonus: float = 0.0  # 当前雷/冰元素伤害加成
    reaction_coef: float = 1.0             # 当前反应系数

class StellarResponse(BaseModel):
    attachment_count: int
    tier: str                       # none / medium / max
    physical_res_reduction: float   # 物理减抗
    final_physical_res: float       # 最终物理抗性
    elemental_dmg_bonus: float      # 额外雷/冰元素伤害加成
    reaction_coef: float            # 星反应系数
    final_reaction_coef: float      # 最终反应系数（含星超导加成）
    note: str


# ==================== API 端点 ====================

# 根目录访问
@app.get("/")
async def root():
    return {
        "message": "原神伤害计算器API服务已启动",
        "docs": "/docs",
        "version": "2.0.0",
        "endpoints": [
            "/calculate_damage",
            "/calculate_reaction",
            "/calculate_reaction_damage",
            "/calculate_lunar",
            "/calculate_stellar",
        ],
    }

# 健康检查接口
@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": "2.0.0"}

# ---------- 直伤计算（保留兼容） ----------
@app.post("/calculate_damage", response_model=DamageResponse)
async def calculate_damage(request: DamageRequest):
    # 计算攻击力
    total_atk = request.base_atk + request.bonus_atk

    # 计算增伤区域
    total_bonus = 1 + request.dmg_bonus + request.other_bonus

    # 计算暴击区域（期望）
    crit_multiplier = 1 + request.crit_rate * request.crit_dmg

    # 计算抗性区域（使用新公式，支持负抗性）
    res_multiplier = GenshinDamageCalculator.resistance_factor(request.enemy_resistance)

    # 计算防御区域
    level_def_multiplier = (request.char_level + 100) / (
        (request.char_level + 100) + (request.enemy_level + 100)
    )
    def_multiplier = level_def_multiplier * (1 - request.def_ignore)

    # 计算伤害
    base_damage = total_atk * request.skill_ratio
    damage_with_bonus = base_damage * total_bonus
    damage_with_crit = damage_with_bonus * crit_multiplier
    final_damage = (
        damage_with_crit
        * request.reaction_multiplier
        * request.independent_multiplier
        * res_multiplier
        * def_multiplier
    )

    return DamageResponse(
        base_damage=base_damage,
        damage_with_bonus=damage_with_bonus,
        damage_with_crit=damage_with_crit,
        final_damage=final_damage,
        total_atk=total_atk,
        total_bonus=total_bonus,
        crit_multiplier=crit_multiplier,
        res_multiplier=res_multiplier,
        def_multiplier=def_multiplier,
    )

# ---------- 反应乘区计算（保留兼容） ----------
@app.post("/calculate_reaction", response_model=ReactionResponse)
async def calculate_reaction(request: ReactionRequest):
    if request.reaction_type == "transformative":
        # 剧变反应（超载/感电/超导/碎冰/绽放/激化等）：3.3版本起统一公式
        reaction_bonus = 25 * request.em / (12 * request.em + 8400) if request.em > 0 else 0
        formula = "剧变反应: 精通报偿 = 25 × EM ÷ (12 × EM + 8400)"
    else:
        # 增幅反应（蒸发/融化）：经典公式
        reaction_bonus = 2.78 * request.em / (request.em + 1400) if request.em > 0 else 0
        formula = "增幅反应: 精通报偿 = 2.78 × EM ÷ (EM + 1400)"

    total_reaction_multiplier = request.base_reaction_multiplier * (1 + reaction_bonus)

    return ReactionResponse(
        reaction_bonus=reaction_bonus,
        total_reaction_multiplier=total_reaction_multiplier,
        formula=formula,
    )

# ---------- 完整反应伤害计算（新增） ----------
@app.post("/calculate_reaction_damage", response_model=ReactionDamageResponse)
async def calculate_reaction_damage(request: ReactionDamageRequest):
    calc = GenshinDamageCalculator(request.char_level, request.enemy_level)

    if request.reaction_type in ("amplify", "evaporate", "melt"):
        # 增幅反应（蒸发/融化）
        if request.reaction_type == "amplify":
            # 使用请求中的 reaction_coef
            coef = request.reaction_coef
        else:
            coef = GenshinDamageCalculator.AMPLIFY_COEF.get(request.reaction_type, 1.5)

        em_bonus = GenshinDamageCalculator.em_bonus_amplify(request.em)
        damage = calc.amplify_reaction(
            atk=request.atk,
            talent_ratio=request.talent_ratio,
            em=request.em,
            reaction_coef=coef,
            elemental_dmg_bonus=request.elemental_dmg_bonus,
            other_dmg_bonus=request.other_dmg_bonus,
            crit_rate=request.crit_rate,
            crit_dmg=request.crit_dmg,
            is_crit=request.is_crit,
            enemy_resistance=request.enemy_resistance,
            flat_bonus=request.flat_bonus,
        )
        formula = (
            f"增幅反应: 基础({request.atk}×{request.talent_ratio}) "
            f"× 增伤 × 防御 × 抗性 × 暴击 × 反应系数({coef}) × (1+精通增益)"
        )
        detail = {
            "reaction_coef": coef,
            "em_bonus": em_bonus,
            "defense_factor": calc.defense_factor(),
            "res_factor": GenshinDamageCalculator.resistance_factor(request.enemy_resistance),
            "crit_factor": GenshinDamageCalculator.crit_factor(
                request.crit_rate, request.crit_dmg, request.is_crit
            ),
        }
        return ReactionDamageResponse(
            reaction_type=request.reaction_type,
            damage=damage,
            em_bonus=em_bonus,
            formula=formula,
            detail=detail,
        )

    elif request.reaction_type == "transformative":
        # 剧变反应
        em_bonus = GenshinDamageCalculator.em_bonus_transformative(request.em)
        damage = calc.transformative_reaction(
            em=request.em,
            enemy_resistance=request.enemy_resistance,
            char_level=request.char_level,
            level_coef=request.level_coef,
        )
        formula = "剧变反应: 等级系数 × (1 + 精通增益) × 抗性区"
        detail = {
            "level_coef": request.level_coef or calc.level_coefficient(request.char_level),
            "em_bonus": em_bonus,
            "res_factor": GenshinDamageCalculator.resistance_factor(request.enemy_resistance),
        }
        return ReactionDamageResponse(
            reaction_type=request.reaction_type,
            damage=damage,
            em_bonus=em_bonus,
            formula=formula,
            detail=detail,
        )

    elif request.reaction_type in ("aggravate", "spread"):
        # 激化反应（超激化/蔓激化）- 返回 flat_bonus
        flat = calc.aggravate_spread_flat(
            char_level=request.char_level,
            em=request.em,
            level_coef=request.level_coef,
        )
        em_bonus = 0.0  # 激化使用独立的精通公式，已在 flat 中体现
        formula = (
            f"激化反应({request.reaction_type}): flat_bonus = "
            f"等级系数 × 1.15 × (1 + 5×EM/(EM+1200))"
        )
        detail = {
            "flat_bonus": flat,
            "level_coef": request.level_coef or calc.level_coefficient(request.char_level),
            "note": "该 flat_bonus 需进一步经过伤害各区乘算",
        }
        return ReactionDamageResponse(
            reaction_type=request.reaction_type,
            damage=flat,
            em_bonus=em_bonus,
            flat_bonus=flat,
            formula=formula,
            detail=detail,
        )

    elif request.reaction_type == "crystallize":
        # 结晶反应：无伤害，仅产生护盾
        return ReactionDamageResponse(
            reaction_type=request.reaction_type,
            damage=0.0,
            em_bonus=0.0,
            formula="结晶反应: 无直接伤害，仅产生护盾",
            detail={"note": "结晶护盾量需另行计算，不在本接口范围内"},
        )

    else:
        return ReactionDamageResponse(
            reaction_type=request.reaction_type,
            damage=0.0,
            em_bonus=0.0,
            formula="未知反应类型",
            detail={"error": f"不支持的 reaction_type: {request.reaction_type}"},
        )

# ---------- 月反应计算（新增） ----------
@app.post("/calculate_lunar", response_model=LunarResponse)
async def calculate_lunar(request: LunarRequest):
    calc = GenshinDamageCalculator()

    if request.damage_type == "indirect":
        participants = [p.model_dump() for p in request.participants]
        result = calc.lunar_indirect_damage(participants, request.reaction_type)

        em_bonus = calc.em_bonus_lunar(0)  # 间接伤害的 EM 由各参与者分别计算
        formula = (
            f"月反应间接伤害({request.reaction_type}): "
            f"Σ(反应系数×等级系数×(1+lunar_bonus)×(1+EM增益+反应增伤)×抗性×暴击) "
            f"→ 前4高加权: ×1, ×1/2, ×1/12, ×1/12"
        )
        return LunarResponse(
            damage_type=request.damage_type,
            reaction_type=request.reaction_type,
            reaction_coef=result["reaction_coef"],
            em_bonus=em_bonus,
            final_damage=result["final_damage"],
            formula=formula,
            detail=result,
        )

    else:  # direct
        damage = calc.lunar_direct_damage(
            attribute_value=request.attribute_value,
            skill_ratio=request.skill_ratio,
            em=request.em,
            reaction_type=request.reaction_type,
            lunar_dmg_bonus=request.lunar_dmg_bonus,
            reaction_dmg_bonus=request.reaction_dmg_bonus,
            flat_bonus=request.flat_bonus,
            enemy_resistance=request.enemy_resistance,
            crit_rate=request.crit_rate,
            crit_dmg=request.crit_dmg,
            is_crit=request.is_crit,
        )
        coef = calc.LUNAR_DIRECT_COEF.get(request.reaction_type, 0.0)
        em_bonus = calc.em_bonus_lunar(request.em)
        formula = (
            f"月反应直接伤害({request.reaction_type}): "
            f"(反应系数({coef})×属性×倍率×(1+lunar_bonus)×(1+EM增益+反应增伤)+flat) "
            f"× 抗性区 × 暴击区"
        )
        return LunarResponse(
            damage_type=request.damage_type,
            reaction_type=request.reaction_type,
            reaction_coef=coef,
            em_bonus=em_bonus,
            final_damage=damage,
            formula=formula,
            detail={
                "reaction_coef": coef,
                "em_bonus": em_bonus,
                "res_factor": GenshinDamageCalculator.resistance_factor(request.enemy_resistance),
                "crit_factor": GenshinDamageCalculator.crit_factor(
                    request.crit_rate, request.crit_dmg, request.is_crit
                ),
            },
        )

# ---------- 星反应计算（新增） ----------
@app.post("/calculate_stellar", response_model=StellarResponse)
async def calculate_stellar(request: StellarRequest):
    calc = GenshinDamageCalculator()
    result = calc.stellar_superconduct_buff(request.attachment_count)

    # 最终物理抗性（考虑减抗）
    final_physical_res = request.base_physical_res - result["res_reduction"]

    # 最终反应系数 = 当前反应系数 × 星超导加成反应系数
    final_reaction_coef = request.reaction_coef * result["reaction_coef"]

    tier_names = {
        "none": "未激活（附着次数不足6次）",
        "medium": "中层加成（6次附着）：约34%雷/冰元素伤害加成 + 1.7反应系数",
        "max": "满层加成（12次附着）：约40%雷/冰元素伤害加成 + 2.0反应系数",
    }
    note = (
        f"星超导领域已生成：降低敌人40%物理抗性。{tier_names[result['tier']]}。"
        f"最终雷/冰元素伤害加成 = 基础 {request.base_elemental_dmg_bonus*100:.1f}% "
        f"+ 星超导额外 {result['elemental_dmg_bonus']*100:.1f}%"
    )

    return StellarResponse(
        attachment_count=request.attachment_count,
        tier=result["tier"],
        physical_res_reduction=result["res_reduction"],
        final_physical_res=final_physical_res,
        elemental_dmg_bonus=result["elemental_dmg_bonus"],
        reaction_coef=result["reaction_coef"],
        final_reaction_coef=final_reaction_coef,
        note=note,
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)