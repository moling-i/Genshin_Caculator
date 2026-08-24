"""
伤害计算核心引擎 - 整合所有公式，计算最终伤害
"""
from . import constants
from .character import Character
from .team import Team
from .effects import EffectManager

def calculate_damage(
    character: Character,
    skill_type: str,
    talent_level: int,
    enemy_level: int,
    enemy_res: float,
    reaction_type: str = None,
    is_crit: bool = False,
    team: Team = None,
    effect_manager: EffectManager = None,
    stellar_stacks: int = 0,
) -> dict:
    """
    计算最终伤害

    参数:
        character: 角色实例
        skill_type: "normal", "skill", "burst"
        talent_level: 天赋等级
        enemy_level: 敌人等级
        enemy_res: 敌人抗性（0.1 表示 10%）
        reaction_type: 反应类型
            - 增幅: "vaporize", "melt"
            - 剧变: "overload", "superconduct", "swirl", "shatter", "electrocharged"
            - 激化: "aggravate", "spread"
            - 月反应间接: "lunar_charged", "lunar_crystallize", "lunar_bloom"
            - 月反应直接: "lunar_charged_direct", "lunar_crystallize_direct", "lunar_bloom_direct"
            - 星超导: "stellar_superconduct"
        is_crit: 是否暴击
        team: 队伍实例（月反应间接伤害需要）
        effect_manager: 效果管理器（提供最终修饰器）
        stellar_stacks: 星超导附着次数（0/6/12）

    返回:
        {
            "damage": 伤害数值,
            "breakdown": 各乘区明细
        }
    """
    # 1. 获取最终有效面板（应用所有效果）
    panel = character.get_effective_panel()

    # 应用效果管理器的修饰器
    if effect_manager is not None:
        mods = effect_manager.get_final_modifiers()
        panel["atk"] *= (1 + mods["atk_percent"])
        panel["atk"] += mods["atk_flat"]
        panel["crit_rate"] += mods["crit_rate"]
        panel["crit_dmg"] += mods["crit_dmg"]
        panel["elemental_mastery"] += mods["elemental_mastery"]
        panel["elemental_dmg_bonus"] += mods["elemental_dmg_bonus"]
        panel["lunar_dmg_bonus"] += mods["lunar_dmg_bonus"]
        panel["reaction_dmg_bonus"] += mods["reaction_dmg_bonus"]
        panel["dmg_bonus"] += mods["dmg_bonus"]
        panel["def_ignore"] = max(panel["def_ignore"], mods["def_ignore"])

    # 2. 基础伤害区
    talent_ratio = character.get_talent_ratio(skill_type, talent_level)
    base_damage = panel["atk"] * talent_ratio

    breakdown = {
        "base_atk": panel["atk"],
        "talent_ratio": talent_ratio,
        "base_damage": base_damage,
    }

    # 3. 增伤区
    dmg_bonus_factor = 1 + panel["elemental_dmg_bonus"] + panel["dmg_bonus"]
    breakdown["dmg_bonus_factor"] = dmg_bonus_factor

    # 4. 防御区（考虑无视防御）
    def_factor = constants.defense_factor(character.char_level, enemy_level)
    if panel["def_ignore"] > 0:
        def_factor = def_factor * (1 - panel["def_ignore"])
    breakdown["def_factor"] = def_factor

    # 5. 抗性区
    res_factor = constants.resistance_factor(enemy_res)
    breakdown["res_factor"] = res_factor

    # 6. 暴击区
    if is_crit:
        crit_factor = 1 + panel["crit_dmg"]
    else:
        crit_factor = 1.0
    breakdown["crit_factor"] = crit_factor
    breakdown["is_crit"] = is_crit

    # 7. 反应区
    reaction_factor = 1.0
    reaction_detail = {}

    if reaction_type is None:
        pass

    elif reaction_type in ("vaporize", "melt"):
        # 增幅反应
        # 反应系数需根据触发元素与被触发元素确定（此处简化：使用默认系数）
        # 实际应从技能元素与敌人元素判断
        coeff = 2.0 if reaction_type == "vaporize" else 2.0
        em_bonus = constants.em_bonus_amplifying(panel["elemental_mastery"])
        reaction_factor = coeff * (1 + em_bonus)
        reaction_detail = {"type": "amplify", "coeff": coeff, "em_bonus": em_bonus}

    elif reaction_type in ("overload", "superconduct", "swirl", "shatter", "electrocharged"):
        # 剧变反应（不暴击，不受攻击/增伤影响）
        em_bonus = constants.em_bonus_transformative(panel["elemental_mastery"])
        transformative_dmg = constants.LEVEL_COEFFICIENT * (1 + em_bonus) * res_factor
        breakdown["transformative_damage"] = transformative_dmg
        return {
            "damage": transformative_dmg,
            "breakdown": {**breakdown, "reaction": reaction_detail, "note": "剧变反应不受攻击/增伤/暴击影响"},
        }

    elif reaction_type in ("aggravate", "spread"):
        # 激化反应（为基础伤害区提供 flat_bonus）
        em_bonus = 5 * panel["elemental_mastery"] / (panel["elemental_mastery"] + 1200)
        flat_bonus = constants.LEVEL_COEFFICIENT * 1.15 * (1 + em_bonus)
        base_damage += flat_bonus
        breakdown["base_damage"] += flat_bonus
        breakdown["aggravate_flat"] = flat_bonus
        reaction_detail = {"type": "aggravate", "flat_bonus": flat_bonus}

    elif reaction_type in ("lunar_charged", "lunar_crystallize", "lunar_bloom"):
        # 月反应间接伤害（需要队伍数据）
        if team is None:
            raise ValueError("月反应间接伤害需要 Team 实例")
        lunar_dmg = team.calculate_lunar_indirect_damage(reaction_type, enemy_res)
        return {
            "damage": lunar_dmg,
            "breakdown": {**breakdown, "reaction": {"type": "lunar_indirect"}, "lunar_indirect_damage": lunar_dmg},
        }

    elif reaction_type in ("lunar_charged_direct", "lunar_crystallize_direct", "lunar_bloom_direct"):
        # 月反应直接伤害（由角色技能造成）
        base_type = reaction_type.replace("_direct", "")
        coeff = constants.LUNAR_REACTION_COEFF[base_type]["direct"]
        em_bonus = constants.em_bonus_lunar(panel["elemental_mastery"])
        lunar_bonus = panel["lunar_dmg_bonus"]
        reaction_bonus = panel["reaction_dmg_bonus"]
        direct_dmg = (
            (coeff * panel["atk"] * talent_ratio * (1 + lunar_bonus) * (1 + em_bonus + reaction_bonus))
            * res_factor * crit_factor
        )
        breakdown["lunar_direct_damage"] = direct_dmg
        return {
            "damage": direct_dmg,
            "breakdown": {**breakdown, "reaction": {"type": "lunar_direct", "coeff": coeff}},
        }

    elif reaction_type == "stellar_superconduct":
        # 星超导（预留接口）
        if stellar_stacks >= 12:
            stack_data = constants.STELLAR_SUPERCONDUCT["stacks_12"]
        elif stellar_stacks >= 6:
            stack_data = constants.STELLAR_SUPERCONDUCT["stacks_6"]
        else:
            stack_data = {"dmg_bonus": 0.0, "reaction_coef": 1.0}
        dmg_bonus_factor += stack_data["dmg_bonus"]
        reaction_factor = stack_data["reaction_coef"]
        reaction_detail = {"type": "stellar_superconduct", "stacks": stellar_stacks, **stack_data}

    breakdown["reaction_factor"] = reaction_factor
    breakdown["reaction"] = reaction_detail

    # 8. 最终伤害
    final_damage = base_damage * dmg_bonus_factor * def_factor * res_factor * crit_factor * reaction_factor
    breakdown["final_damage"] = final_damage

    return {"damage": final_damage, "breakdown": breakdown}