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
        # 扩展：属性转换 / 充能缩放 / 血量上下文（由固有天赋注入，get_effective_panel 时生效）
        self.pending_conversions = []   # [{from, to, ratio}]
        self.er_scalings = []           # [{threshold, per_unit, stat}]
        self.er_total = 1.0             # 元素充能效率（默认 100%）
        self.hp_ratio_context = None    # 当前血量比例上下文（None 表示满血）
        self.amplify_bonus = 0.0        # 蒸发/融化增幅反应专属加成

        # 命座效果（从 constellations.json 加载）
        self.constellation_effects = self._load_constellations()

        # 固有天赋（Meropide 数据；由 app 层勾选后调用 apply_passive 生效）
        self.passive_skills = data_loader.load_passive_skills(self.id)

        # 角色固有状态标签（夜魂/魔导/星超导/星扩散/月兆；只读展示，暂无数值效果）
        self.states = data_loader.get_character_states(self.id)

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

    def apply_conversion(self, conversion: dict):
        """注册属性转换型天赋（如"基于生命值上限6%转化为攻击力"）"""
        if conversion and conversion not in self.pending_conversions:
            self.pending_conversions.append(dict(conversion))

    def remove_conversion(self, conversion: dict):
        c = dict(conversion)
        self.pending_conversions = [
            x for x in self.pending_conversions if x != c
        ]

    def apply_er_scaling(self, scaling: dict):
        """注册充能效率转伤害型天赋（如雷电将军：超出100%每1%充能+0.4%雷伤）"""
        if scaling and scaling not in self.er_scalings:
            self.er_scalings.append(dict(scaling))

    def remove_er_scaling(self, scaling: dict):
        s = dict(scaling)
        self.er_scalings = [x for x in self.er_scalings if x != s]

    def _conversion_source_value(self, src: str) -> float:
        """属性转换的来源数值（使用当前面板总值）"""
        if src == "hp":
            return (self.base_hp + self.flat_hp) * (1 + self.hp_percent)
        if src == "atk":
            return (self.base_atk + self.flat_atk) * (1 + self.atk_percent)
        if src == "def":
            return (self.base_def + self.flat_def) * (1 + self.def_percent)
        if src == "em":
            return self.elemental_mastery
        return 0.0


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

        # 属性转换型天赋（如"生命值上限的X%转化为攻击力"）→ 追加固定攻击
        conv_flat_atk = 0.0
        for conv in self.pending_conversions:
            if conv.get("to") == "atk_flat":
                src_val = self._conversion_source_value(conv.get("from"))
                conv_flat_atk += src_val * float(conv.get("ratio", 0.0))
        total_atk += conv_flat_atk

        # 充能效率转伤害型天赋（如雷电将军固有）
        # 超出阈值的部分按"百分点"计：总充能200%、阈值100% → 超出100点
        dmg_bonus_extra = 0.0
        for scaling in self.er_scalings:
            over_pts = max(0.0, self.er_total - float(scaling.get("threshold", 1.0))) * 100.0
            dmg_bonus_extra += over_pts * float(scaling.get("per_unit", 0.0))

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
            "dmg_bonus": self.dmg_bonus + dmg_bonus_extra,
            "def_ignore": self.def_ignore,
            "amplify_bonus": getattr(self, "amplify_bonus", 0.0),
            "conversion_flat_atk": conv_flat_atk,
            "er_bonus_applied": dmg_bonus_extra,
            "hp_ratio": self.hp_ratio_context if self.hp_ratio_context is not None else 1.0,
            "element": self.element,
        }