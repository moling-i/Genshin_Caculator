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
        self.physical_dmg_bonus = 0    # 物理伤害加成（如辛焱固有）
        self.enemy_def_shred = 0       # 敌人防御降低（如丽莎静电场力），上限40%
        self.def_ignore = 0  # 无视防御比例（如雷电将军C2）
        # 扩展：属性转换 / 充能缩放 / 血量上下文（由固有天赋注入，get_effective_panel 时生效）
        self.pending_conversions = []   # [{from, to, ratio}]
        self.er_scalings = []           # [{threshold, per_unit, cap, stat}]
        self.er_total = 1.0             # 元素充能效率（默认 100%）
        self.hp_ratio_context = None    # 当前血量比例上下文（None 表示满血）
        self.amplify_bonus = 0.0        # 蒸发/融化增幅反应专属加成
        # 扩展 v2：新天赋类型
        self.atk_over_scalings = []     # [{source, threshold, per_points, bonus_per, cap, stat}] 属性超阈值转增伤
        self.lunar_scalings = []        # [{source, per_points, bonus_per, cap, stat}] 月曜反应基础伤害缩放
        self.attr_scalings = []         # [{source, per_points, bonus_per, cap, stat}] 属性线性转增伤（艾梅莉埃精馏式）
        self.flat_dmg_scalings = []     # [{source, ratio}] 伤害值flat加算（蓝砚/赛索斯式：来源属性×X%）
        self.team_effects_received = {"em_flat": 0.0, "em_pct": 0.0, "em_from": {}, "em_to_dmg": 0.0, "atk_pct": 0.0}
        self.passive_level_bonus = {}   # {normal/skill/burst: n} 天赋等级加成（如达达利亚诸武精通）
        # 扩展 v3：机制型天赋数值（万流归寂/烟绯/杜林式，由固有天赋注入，calculate_damage 消费）
        self.talent_multipliers = {}    # {skill_type: [tier1, tier2, ...]} 技能倍率层数提升
        self.extra_hits = []            # [{source, ratio}] 额外一段伤害（来源属性×X%）
        self.damage_amps = []           # [{source, per_points, per_bonus, cap}] 全伤害增幅
        self.stack_context = {}         # {skill_type: stacks} 层数上下文（缺省取最高层）

        # 命座效果（从 constellations.json 加载）
        self.constellation_effects = self._load_constellations()

        # 固有天赋（Meropide 数据；由 app 层勾选后调用 apply_passive 生效）
        self.passive_skills = data_loader.load_passive_skills(self.id)

        # 角色固有状态标签（夜魂/魔导/星超导/星扩散/月兆；只读展示，暂无数值效果）
        self.states = data_loader.get_character_states(self.id)
        # 状态触发上下文：{状态名: bool}，默认全部视为已触发（不丢伤害）；
        # UI 开关可关闭某状态 → 依赖该状态的固有天赋被跳过
        self.active_states = {s: True for s in self.states}

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

    def apply_all_passives(self, enabled_indices=None) -> list:
        """
        解析并应用全部（或指定启用的）固有天赋。

        :param enabled_indices: 启用的天赋下标集合/列表；None 表示全部启用
        :return: 应用明细列表 [{index, name, category, effect}]，供 UI 展示与撤销
        """
        applied = []
        for idx, p in enumerate(self.passive_skills):
            if enabled_indices is not None and idx not in set(enabled_indices):
                continue
            desc = (p.get("description") or "").strip()
            if not desc:
                continue
            eff = data_loader.parse_effect(desc)
            if eff["category"] != "stat":
                applied.append({"index": idx, "name": p.get("name", ""),
                                "category": eff["category"], "effect": None})
                continue
            # 条件天赋门控：hp_threshold 类（如"生命值低于50%时火伤+33%"）
            # 按当前血量上下文判定；hp_ratio_context 为 None 时视为满血（不满足）
            ht = eff.get("hp_threshold")
            if ht is not None:
                cur_ratio = (
                    self.hp_ratio_context
                    if self.hp_ratio_context is not None else 1.0
                )
                if cur_ratio > float(ht):
                    applied.append({"index": idx, "name": p.get("name", ""),
                                    "category": "stat_skipped_by_condition",
                                    "effect": None})
                    continue
            # 状态标签门控：天赋描述依赖某状态（夜魂/魔导/月兆等）且该状态未触发时跳过
            req_states = data_loader.detect_required_states(desc, self.states)
            if req_states and not all(
                self.active_states.get(s, True) for s in req_states
            ):
                applied.append({"index": idx, "name": p.get("name", ""),
                                "category": "stat_skipped_by_state",
                                "effect": None})
                continue
            self.apply_passive(eff["modifiers"])
            if eff["conversion"]:
                self.apply_conversion(eff["conversion"])
            if eff["er_scaling"]:
                self.apply_er_scaling(eff["er_scaling"])
            if eff["atk_over_scaling"]:
                self.atk_over_scalings.append(dict(eff["atk_over_scaling"]))
            if eff["lunar_scaling"]:
                self.lunar_scalings.append(dict(eff["lunar_scaling"]))
            if eff.get("attr_scaling"):
                self.attr_scalings.append(dict(eff["attr_scaling"]))
            if eff.get("flat_dmg_scaling"):
                self.flat_dmg_scalings.append(dict(eff["flat_dmg_scaling"]))
            if eff.get("talent_multiplier"):
                for k, tiers in eff["talent_multiplier"].get("skill_types", {}).items():
                    # 多天赋/重复启用时逐档取最大，避免叠加放大
                    prev = self.talent_multipliers.get(k) or []
                    self.talent_multipliers[k] = (
                        [max(a, b) for a, b in zip(prev + [0.0] * len(tiers), tiers)]
                        if prev else list(tiers)
                    )
            if eff.get("extra_hit") and eff["extra_hit"] not in self.extra_hits:
                self.extra_hits.append(dict(eff["extra_hit"]))
            if eff.get("damage_amp") and eff["damage_amp"] not in self.damage_amps:
                self.damage_amps.append(dict(eff["damage_amp"]))
            if eff["talent_level_up"]:
                for k, v in eff["talent_level_up"].items():
                    self.passive_level_bonus[k] = max(self.passive_level_bonus.get(k, 0), v)
            applied.append({"index": idx, "name": p.get("name", ""),
                            "category": eff["category"], "effect": eff})
        return applied

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

        # 固有天赋提供的技能等级加成（如达达利亚诸武精通：普攻+1）
        level_bonus += int(self.passive_level_bonus.get(skill_type, 0))

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
        stat_extras = {"dmg_bonus": 0.0, "elemental_dmg_bonus": 0.0, "lunar_dmg_bonus": 0.0}
        src_value_cache = {}
        for scaling in self.er_scalings:
            over_pts = max(0.0, self.er_total - float(scaling.get("threshold", 1.0))) * 100.0
            val = over_pts * float(scaling.get("per_unit", 0.0))
            cap = scaling.get("cap")
            if cap is not None:
                val = min(val, float(cap))
            stat_extras[scaling.get("stat", "dmg_bonus")] += val

        # 属性超阈值转增伤（奥黛塔式）与月曜反应基础伤害缩放（月兆祝赐式）
        def _src_val(key):
            if key not in src_value_cache:
                if key == "er":
                    src_value_cache[key] = self.er_total * 100.0
                else:
                    src_value_cache[key] = self._conversion_source_value(key)
            return src_value_cache[key]

        for sc in self.atk_over_scalings:
            over = max(0.0, _src_val(sc["source"]) - float(sc["threshold"]))
            val = (over / float(sc["per_points"])) * float(sc["bonus_per"])
            cap = sc.get("cap")
            if cap is not None:
                val = min(val, float(cap))
            stat_extras[sc.get("stat", "elemental_dmg_bonus")] += val

        for sc in self.lunar_scalings:
            over = max(0.0, _src_val(sc["source"]))
            val = (over / float(sc["per_points"])) * float(sc["bonus_per"])
            cap = sc.get("cap")
            if cap is not None:
                val = min(val, float(cap))
            stat_extras[sc.get("stat", "lunar_dmg_bonus")] += val

        for sc in self.attr_scalings:
            val = (_src_val(sc["source"]) / float(sc["per_points"])) * float(sc["bonus_per"])
            cap = sc.get("cap")
            if cap is not None:
                val = min(val, float(cap))
            stat_extras[sc.get("stat", "elemental_dmg_bonus")] += val

        # 伤害值 flat 加算（蓝砚/赛索斯式：来源属性 × X%）
        flat_dmg_bonus = sum(
            _src_val(sc["source"]) * float(sc["ratio"])
            for sc in self.flat_dmg_scalings
        )

        # 队伍共享攻击%（琳妮特式）
        team_atk_pct = self.team_effects_received.get("atk_pct", 0.0)
        total_atk *= (1 + team_atk_pct)

        # 队伍共享精通（由 Team.apply_team_passives 注入）
        em_from_team = self.team_effects_received.get("em_flat", 0.0)
        em_pct = self.team_effects_received.get("em_pct", 0.0)
        for _src, pct in (self.team_effects_received.get("em_from") or {}).items():
            em_pct += pct
        total_em = (
            self.elemental_mastery + em_from_team
        ) * (1 + em_pct)

        # 暴击/暴伤 = 基础 + 面板输入
        crit_rate = min(self.base_crit_rate + self.crit_rate, 1.0)
        crit_dmg = self.base_crit_dmg + self.crit_dmg

        return {
            "atk": total_atk,
            "hp": total_hp,
            "def": total_def,
            "crit_rate": crit_rate,
            "crit_dmg": crit_dmg,
            "elemental_mastery": total_em,
            "elemental_mastery_base": self.elemental_mastery,
            "elemental_dmg_bonus": self.elemental_dmg_bonus + stat_extras["elemental_dmg_bonus"],
            "lunar_dmg_bonus": self.lunar_dmg_bonus + stat_extras["lunar_dmg_bonus"],
            "reaction_dmg_bonus": self.reaction_dmg_bonus,
            "dmg_bonus": (
                self.dmg_bonus + stat_extras["dmg_bonus"]
                + self.team_effects_received.get("em_to_dmg", 0.0)
            ),
            "physical_dmg_bonus": getattr(self, "physical_dmg_bonus", 0.0),
            "enemy_def_shred": min(getattr(self, "enemy_def_shred", 0.0), 0.4),
            "def_ignore": self.def_ignore,
            "flat_dmg_bonus": flat_dmg_bonus,
            "amplify_bonus": getattr(self, "amplify_bonus", 0.0),
            "conversion_flat_atk": conv_flat_atk,
            "er_bonus_applied": dmg_bonus_extra,
            "hp_ratio": self.hp_ratio_context if self.hp_ratio_context is not None else 1.0,
            "element": self.element,
        }