"""
角色类 - 加载角色数据、管理面板属性、应用命座效果
"""
from . import data_loader
from . import constants

class Character:
    def __init__(self, character_id: str, constellation_level: int = 0):
        self.id = str(character_id)
        char_data = data_loader.find_character_by_name(self.id)
        if char_data is None:
            raise ValueError(f"未找到角色: {character_id}")

        self.name = char_data.get("name_cn") or char_data.get("name")
        self.constellation_level = constellation_level

        # 基础属性（从 JSON 加载）
        self.base_atk = char_data.get("stats_90", {}).get("atk", 0)
        self.base_hp = char_data.get("stats_90", {}).get("hp", 0)
        self.base_def = char_data.get("stats_90", {}).get("def", 0)
        self.element = char_data.get("element", "")
        self.ascension_bonus = char_data.get("ascension_bonus", {})
        self.skill_depot_id = char_data.get("skill_depot_id", 0)
        self.char_level = 90

        # 基础暴击/暴伤（含突破加成）
        self.base_crit_rate = char_data.get("base_crit_rate", 0.05)
        self.base_crit_dmg = char_data.get("base_crit_dmg", 0.5)
        # 突破提供的暴击/暴伤
        for ptype, val in self.ascension_bonus.items():
            if ptype == "FIGHT_PROP_CRITICAL":
                self.base_crit_rate += val
            elif ptype == "FIGHT_PROP_CRITICAL_HURT":
                self.base_crit_dmg += val

        # 面板属性（由用户输入，初始为0）
        self.flat_atk = 0
        self.flat_hp = 0
        self.flat_def = 0
        self.atk_percent = 0
        self.hp_percent = 0
        self.def_percent = 0
        self.crit_rate = 0
        self.crit_dmg = 0
        self.elemental_mastery = 0
        self.elemental_dmg_bonus = 0
        self.lunar_dmg_bonus = 0
        self.reaction_dmg_bonus = 0
        self.dmg_bonus = 0
        self.def_ignore = 0  # 无视防御比例（如雷电将军C2）

        # 命座效果（从 constellations.json 加载）
        self.constellation_effects = self._load_constellations()

        # 固有天赋（Meropide 数据；由 app 层勾选后调用 apply_passive 生效）
        self.passive_skills = data_loader.load_passive_skills(self.id)

    def apply_passive(self, modifiers: dict):
        """
        将解析后的固有天赋修饰器叠加到面板属性。
        :param modifiers: {attr: value}，attr 为 Character 面板属性名
                          （如 atk_percent / crit_rate / elemental_dmg_bonus）
                          未识别的属性名将被忽略（如 er 计算引擎暂未使用）
        """
        for attr, val in (modifiers or {}).items():
            if hasattr(self, attr) and not callable(getattr(self, attr)):
                setattr(self, attr, getattr(self, attr) + val)

    def revert_passive(self, modifiers: dict):
        """撤销已应用的固有天赋修饰器（用于 UI 取消勾选）"""
        for attr, val in (modifiers or {}).items():
            if hasattr(self, attr) and not callable(getattr(self, attr)):
                setattr(self, attr, getattr(self, attr) - val)


    def _load_constellations(self) -> list:
        """加载命座效果（仅取 <= constellation_level 的命座）"""
        cons_data = data_loader.find_constellation_by_char_id(self.id)
        if not cons_data:
            return []
        effects = []
        for c in cons_data.get("constellations", []):
            level = c.get("constellation_level", 0)
            if level <= self.constellation_level:
                effects.append({
                    "level": level,
                    "name": c.get("name_cn", ""),
                    "param_list": c.get("param_list", []),
                    "open_config": c.get("open_config", ""),
                })
        return effects

    def get_talent_ratio(self, skill_type: str, talent_level: int) -> float:
        """
        获取指定技能在指定等级下的倍率（取 param_list[0]）
        若命座有技能等级+3（如 C3/C5 等），则实际等级 = talent_level + 3
        """
        internal_type = constants.SKILL_TYPE_MAP.get(skill_type, skill_type)

        # 命座提供的技能等级加成（如 C3: +3级普攻/战技/爆发）
        level_bonus = 0
        for eff in self.constellation_effects:
            oc = eff.get("open_config", "")
            if "Constellation_3" in oc or "Constellation_5" in oc:
                params = eff.get("param_list", [])
                if params and params[0] in (3, 3.0):
                    level_bonus = max(level_bonus, int(params[0]))

        actual_level = min(talent_level + level_bonus, 15)  # 上限15级

        # 通过 skill_depot_id + skill_type + level 获取倍率
        result = data_loader.get_skill_ratios(
            self.skill_depot_id, internal_type, actual_level
        )
        if not result:
            return 0.0
        params = result.get("param_list", [])
        return params[0] if params else 0.0

    def get_skill_params(self, skill_type: str, talent_level: int) -> list:
        """
        获取指定技能在指定等级下的完整倍率参数列表（param_list）
        用于需要多个参数的技能（如胡桃E的火伤加成、行秋E的倍率等）
        """
        internal_type = constants.SKILL_TYPE_MAP.get(skill_type, skill_type)
        result = data_loader.get_skill_ratios(
            self.skill_depot_id, internal_type, talent_level
        )
        if not result:
            return []
        return result.get("param_list", [])

    def get_skill_cd(self, skill_type: str) -> float:
        """获取技能冷却时间（秒）"""
        internal_type = constants.SKILL_TYPE_MAP.get(skill_type, skill_type)
        skills_data = data_loader.get_skills()
        depot = next(
            (d for d in skills_data["skill_depots"] if d.get("depot_id") == self.skill_depot_id),
            None,
        )
        if not depot:
            return 0.0
        for sk in depot.get("skills", []):
            if sk.get("skill_type") == internal_type:
                # 数据中未包含 cdTime，返回 0（需从原始 AvatarSkill 补充）
                return 0.0
        return 0.0

    def get_effective_panel(self) -> dict:
        """返回最终有效面板（应用所有常驻效果后）"""
        # 攻击力 = (基础ATK + 固定ATK) × (1 + ATK%)
        total_atk = (self.base_atk + self.flat_atk) * (1 + self.atk_percent)
        total_hp = (self.base_hp + self.flat_hp) * (1 + self.hp_percent)
        total_def = (self.base_def + self.flat_def) * (1 + self.def_percent)

        # 暴击/暴伤 = 基础 + 面板输入
        crit_rate = min(self.base_crit_rate + self.crit_rate, 1.0)
        crit_dmg = self.base_crit_dmg + self.crit_dmg

        return {
            "atk": total_atk,
            "hp": total_hp,
            "def": total_def,
            "crit_rate": crit_rate,
            "crit_dmg": crit_dmg,
            "elemental_mastery": self.elemental_mastery,
            "elemental_dmg_bonus": self.elemental_dmg_bonus,
            "lunar_dmg_bonus": self.lunar_dmg_bonus,
            "reaction_dmg_bonus": self.reaction_dmg_bonus,
            "dmg_bonus": self.dmg_bonus,
            "def_ignore": self.def_ignore,
            "element": self.element,
        }