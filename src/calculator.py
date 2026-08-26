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
    extra_res_shred: float = 0.0,
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
        extra_res_shred: 额外敌人减抗（如队友提供的全队减抗，直接叠加到抗性区）

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

    # flat 伤害加算（蓝砚/赛索斯式天赋：来源属性×X% 直接加到伤害值）
    if panel.get("flat_dmg_bonus"):
        base_damage += panel["flat_dmg_bonus"]
        breakdown["base_damage"] = base_damage
        breakdown["flat_dmg_bonus"] = panel["flat_dmg_bonus"]

    # 技能倍率层数提升（万流归寂/火花魔法式：层数 → 整段倍率乘区，默认取最高层）
    talent_mult_factor = 1.0
    tm_tiers = getattr(character, "talent_multipliers", {}).get(skill_type)
    if tm_tiers:
        stacks = int(getattr(character, "stack_context", {}).get(skill_type, len(tm_tiers)))
        idx = min(max(stacks, 1), len(tm_tiers)) - 1
        talent_mult_factor = float(tm_tiers[idx])
        base_damage *= talent_mult_factor
    breakdown["talent_mult_factor"] = talent_mult_factor

    # 额外一段伤害（烟绯/八重神子式：来源属性×X% 追加命中，走完整后续乘区）
    extra_hit_total = 0.0
    for eh in getattr(character, "extra_hits", []):
        src_val = character._conversion_source_value(eh.get("source", "atk"))
        extra_hit_total += src_val * float(eh.get("ratio", 0.0))
    if extra_hit_total:
        base_damage += extra_hit_total
        breakdown["base_damage"] = base_damage
        breakdown["extra_hit_damage"] = extra_hit_total

    # 全伤害增幅（杜林式：每X点来源属性→最终伤害+N%，逐条取cap后求和）
    # scope=reaction 时仅作用于月曜/星曜反应伤害路径
    damage_amp_total = 0.0
    is_reaction_path = bool(reaction_type and (
        reaction_type.startswith("lunar") or reaction_type.startswith("stellar")
    ))
    for da in getattr(character, "damage_amps", []):
        if da.get("scope") == "reaction" and not is_reaction_path:
            continue
        src_val = character._conversion_source_value(da.get("source", "atk"))
        damage_amp_total += min(
            src_val / float(da["per_points"]) * float(da["per_bonus"]),
            float(da["cap"]),
        )
    amp_factor = 1.0 + damage_amp_total
    base_damage *= amp_factor
    breakdown["damage_amp"] = damage_amp_total
    breakdown["amp_factor"] = amp_factor

    # 3. 增伤区（物理伤害加成并入通配增伤区：对物理输出正确；元素附魔场景为保守近似）
    dmg_bonus_factor = (
        1 + panel["elemental_dmg_bonus"] + panel["dmg_bonus"]
        + panel.get("physical_dmg_bonus", 0.0)
    )
    breakdown["dmg_bonus_factor"] = dmg_bonus_factor

    # 4. 防御区（考虑无视防御与敌人防御降低，减防上限40%）
    def_factor = constants.defense_factor(character.char_level, enemy_level)
    if panel["def_ignore"] > 0:
        def_factor = def_factor * (1 - panel["def_ignore"])
    enemy_shred = panel.get("enemy_def_shred", 0.0)
    if enemy_shred > 0:
        def_factor = def_factor * (1 - enemy_shred)
    breakdown["def_factor"] = def_factor

    # 5. 抗性区（应用减抗：全元素减抗恒生效；元素专属减抗仅匹配角色元素时生效）
    main_elem = getattr(character, "element", None)
    res_shred_total = (
        character.get_applicable_res_shred(main_elem)
        + float(extra_res_shred or 0.0)
    )
    effective_enemy_res = float(enemy_res) - res_shred_total
    res_factor = constants.resistance_factor(effective_enemy_res)
    breakdown["res_factor"] = res_factor
    breakdown["res_shred_total"] = res_shred_total
    breakdown["effective_enemy_res"] = effective_enemy_res

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
        amplify_extra = panel.get("amplify_bonus", 0.0)
        reaction_factor = coeff * (1 + em_bonus + amplify_extra)
        reaction_detail = {
            "type": "amplify", "coeff": coeff, "em_bonus": em_bonus,
            "amplify_bonus": amplify_extra,
        }

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
            (coeff * panel["atk"] * talent_ratio * talent_mult_factor * amp_factor
             * (1 + lunar_bonus) * (1 + em_bonus + reaction_bonus))
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