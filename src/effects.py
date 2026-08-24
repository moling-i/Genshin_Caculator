"""
效果管理器 - 管理武器特效、圣遗物套装、命座效果的触发和应用
"""
from . import data_loader
from . import constants

class EffectManager:
    def __init__(self, character, team=None):
        self.character = character
        self.team = team
        self.active_effects = []  # 当前激活的效果列表

    def apply_weapon_effect(self, weapon_id: str, refinement_level: int):
        """加载并应用武器特效（从 weapons.json）"""
        weapon = data_loader.find_weapon_by_name(weapon_id)
        if not weapon:
            return
        refinements = weapon.get("refinements", [])
        if not refinements:
            return
        # refinement_level: 1-5，对应 index 0-4
        idx = max(0, min(refinement_level - 1, len(refinements) - 1))
        ref = refinements[idx]
        effect = {
            "source": "weapon",
            "weapon_id": weapon_id,
            "name": ref.get("name_cn", ""),
            "open_config": ref.get("open_config", ""),
            "param_list": ref.get("param_list", []),
            "trigger": "always",  # 武器特效通常为常驻或条件触发
        }
        self.active_effects.append(effect)

    def apply_artifact_effect(self, set_2_id: str = None, set_4_id: str = None):
        """加载并应用圣遗物套装效果（从 artifacts.json）"""
        for set_id in [set_2_id, set_4_id]:
            if not set_id:
                continue
            art_set = data_loader.find_artifact_set(set_id)
            if not art_set:
                continue
            for eff in art_set.get("effects", []):
                effect = {
                    "source": "artifact",
                    "set_id": set_id,
                    "pieces": eff.get("pieces", 0),
                    "name": eff.get("name_cn", ""),
                    "open_config": eff.get("open_config", ""),
                    "param_list": eff.get("param_list", []),
                    "trigger": "always" if eff.get("pieces") == 2 else "4pc",
                }
                self.active_effects.append(effect)

    def apply_constellation_effects(self):
        """加载并应用命座效果（从 constellations.json）"""
        for eff in self.character.constellation_effects:
            effect = {
                "source": "constellation",
                "level": eff.get("level", 0),
                "name": eff.get("name", ""),
                "open_config": eff.get("open_config", ""),
                "param_list": eff.get("param_list", []),
                "trigger": "always",
            }
            self.active_effects.append(effect)

    def trigger_event(self, event_type: str, **kwargs):
        """
        触发事件（如"重击命中"、"触发扩散"、"生命值低于50%"）
        检查所有效果中是否有匹配的 trigger，若有则激活对应的 modifiers
        """
        # 简化实现：根据 open_config 关键词判断条件
        for eff in self.active_effects:
            oc = eff.get("open_config", "")
            # 示例：护摩之杖 "Weapon_Polearm_HPScaleAtkUp" 需要生命值低于50%
            if "HPScaleAtkUp" in oc:
                hp_ratio = kwargs.get("hp_ratio", 1.0)
                if hp_ratio < 0.5:
                    eff["activated"] = True
            else:
                eff["activated"] = True

    def get_final_modifiers(self) -> dict:
        """
        返回所有当前激活的效果叠加后的最终修饰器
        例如：{"atk_percent": 0.18, "dmg_bonus": 0.35, "lunar_dmg_bonus": 0.20}
        """
        modifiers = {
            "atk_percent": 0.0,
            "atk_flat": 0.0,
            "hp_percent": 0.0,
            "def_percent": 0.0,
            "crit_rate": 0.0,
            "crit_dmg": 0.0,
            "elemental_mastery": 0.0,
            "elemental_dmg_bonus": 0.0,
            "lunar_dmg_bonus": 0.0,
            "reaction_dmg_bonus": 0.0,
            "dmg_bonus": 0.0,
            "def_ignore": 0.0,
        }
        for eff in self.active_effects:
            if not eff.get("activated", True):
                continue
            oc = eff.get("open_config", "")
            params = eff.get("param_list", [])
            # 根据 open_config 关键词应用不同修饰器
            if "DamageUpToEnemy" in oc or "AtkUp" in oc:
                if params:
                    modifiers["dmg_bonus"] += params[0]
            elif "ExtraAtkCritUp" in oc:
                if params:
                    modifiers["atk_percent"] += params[0]
                    if len(params) > 1:
                        modifiers["crit_rate"] += params[1]
            elif "HPScaleAtkUp" in oc:
                # 护摩之杖：基于生命值提供攻击力%
                if params:
                    modifiers["atk_percent"] += params[0]
            elif "SkillDamageUp" in oc:
                # 圣遗物：技能伤害提升
                if params:
                    modifiers["dmg_bonus"] += params[0]
            elif "GiantKiller" in oc:
                # 圣遗物：对大体型敌人伤害提升
                if params:
                    modifiers["dmg_bonus"] += params[0]
            elif "LowHPGainExtraCritRate" in oc:
                # 圣遗物：低生命值获得额外暴击率
                if params:
                    modifiers["crit_rate"] += params[0]
            elif "AtkAndExtraAtkUp" in oc:
                # 圣遗物：攻击力提升
                if params:
                    modifiers["atk_percent"] += params[0]
            elif "ElemDmgEnhanceElemResist" in oc:
                # 圣遗物：元素伤害加成
                if params:
                    modifiers["elemental_dmg_bonus"] += params[0]
            elif "ReactionGainExtraElemMasteryForTeam" in oc:
                # 圣遗物：反应获得元素精通
                if params:
                    modifiers["elemental_mastery"] += params[0]
            # 命座效果（如雷电将军C2：无视防御）
            elif "Constellation_2" in oc and "Shougun" in oc:
                # 雷电将军C2：开大时无视60%防御
                if params:
                    modifiers["def_ignore"] = max(modifiers["def_ignore"], params[0])
                else:
                    modifiers["def_ignore"] = max(modifiers["def_ignore"], 0.60)
            elif "Constellation" in oc and params and "DefIgnore" in oc:
                modifiers["def_ignore"] = max(modifiers["def_ignore"], params[0])
        return modifiers