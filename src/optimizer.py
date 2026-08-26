"""
属性优化模块 - 在给定总词条数下搜索最优副词条分配，使期望伤害最大化

优化思路：
1. 可分配副词条属性：攻击力百分比(atk_percent)、暴击率(crit_rate)、
   暴击伤害(crit_dmg)、元素精通(em)
2. 每个有效词条(roll)提供固定数值（五星圣遗物副词条平均值）
3. 主词条提供额外固定数值（根据 main_stats 选择）
4. 使用随机搜索 + 局部细化寻找最优分配

用户面板约束（v2）：
  面板输入的 crit_rate_pct / crit_dmg_pct / em 作为**最终上限 (cap)**，
  构建完成的属性值不允许超过该上限，确保优化器忠实于用户输入。
"""
import logging
import random
from .character import Character
from .effects import EffectManager
from .calculator import calculate_damage

logger = logging.getLogger(__name__)

# 每个有效副词条(roll)提供的数值（五星圣遗物副词条平均值）
ROLL_VALUES = {
    "atk_percent": 0.0493,   # 4.93% 攻击力
    "crit_rate": 0.033,      # 3.3% 暴击率
    "crit_dmg": 0.066,       # 6.6% 暴击伤害
    "em": 19.45,             # 19.45 元素精通
}

# 主词条数值（90级五星圣遗物）
MAIN_STAT_VALUES = {
    "sands": {
        "atk_percent": 0.466,   # 46.6% 攻击力
        "hp_percent": 0.466,    # 46.6% 生命值
        "em": 186.0,            # 186 元素精通
        "er": 0.518,            # 51.8% 元素充能
    },
    "goblet": {
        "elemental_dmg": 0.466, # 46.6% 元素伤害
        "atk_percent": 0.466,   # 46.6% 攻击力
        "hp_percent": 0.466,    # 46.6% 生命值
    },
    "circlet": {
        "crit_dmg": 0.622,      # 62.2% 暴击伤害
        "crit_rate": 0.311,     # 31.1% 暴击率
        "atk_percent": 0.466,   # 46.6% 攻击力
    },
}

# 剧变反应不暴击
TRANSFORMATIVE = ("overload", "superconduct", "swirl", "shatter", "electrocharged")
# 月反应间接伤害（需要队伍）
LUNAR_INDIRECT = ("lunar_charged", "lunar_crystallize", "lunar_bloom")

SUBSTAT_KEYS = ["atk_percent", "crit_rate", "crit_dmg", "em"]


class OptimizationInput:
    """优化输入参数"""

    def __init__(
        self,
        character_id: str,
        constellation_level: int = 0,
        talent_level: int = 10,
        skill_type: str = "burst",
        enemy_level: int = 90,
        enemy_res: float = 0.1,
        reaction_type=None,
        weapon_id=None,
        artifact_set_2=None,
        artifact_set_4=None,
        total_substat_rolls: int = 30,
        min_crit_rate: float = 0.2,
        main_stats: dict = None,
        team_members: list = None,
        # ---- 扩展输入（UI 队伍面板 / 固有天赋）----
        panel_inputs: dict = None,
        passive_modifiers: dict = None,
        team_configs: list = None,
        # 完整天赋效果结构：{modifiers{}, conversions[], er_scalings[], er_pct}
        passive_effects: dict = None,
    ):
        self.character_id = str(character_id)
        self.constellation_level = constellation_level
        self.talent_level = talent_level
        self.skill_type = skill_type
        self.enemy_level = enemy_level
        self.enemy_res = enemy_res
        self.reaction_type = reaction_type
        self.weapon_id = weapon_id
        self.artifact_set_2 = artifact_set_2
        self.artifact_set_4 = artifact_set_4
        self.total_substat_rolls = total_substat_rolls
        self.min_crit_rate = min_crit_rate
        self.main_stats = main_stats or {}
        self.team_members = team_members or []
        # 用户直接输入的基础面板值（起点，效果在此之上叠加）：{atk, crit_rate_pct, crit_dmg_pct, em}
        self.panel_inputs = panel_inputs or {}
        # 已启用的固有天赋修饰器合集：{attr: value}
        self.passive_modifiers = passive_modifiers or {}
        # 完整天赋效果（含属性转换/充能缩放）；为空时退回仅 modifiers 模式
        self.passive_effects = passive_effects or {}
        # 队伍成员独立配置列表（4 项，None 表示空位）：
        # [{character_id, weapon_id, refinement, artifact_set_2, artifact_set_4,
        #   talent_levels{normal,skill,burst}, panel{atk,crit_rate_pct,crit_dmg_pct,em},
        #   lunar_bonus_pct, passive_modifiers}, ...]
        self.team_configs = team_configs


class OptimizationResult:
    """优化结果"""

    def __init__(self, optimal_stats, max_damage, damage_breakdown,
                 history, suggestion, allocation):
        self.optimal_stats = optimal_stats      # 最终面板属性（含基础+主词条+副词条）
        self.max_damage = max_damage            # 最大期望伤害
        self.damage_breakdown = damage_breakdown  # 乘区明细
        self.history = history                  # 收敛曲线
        self.suggestion = suggestion            # 培养建议
        self.allocation = allocation            # 各属性分配的词条数


class DamageOptimizer:
    """伤害优化器"""

    def __init__(self, input_params: OptimizationInput):
        self.input = input_params
        self.history = []

    def _apply_main_stats(self, char: Character):
        """应用主词条到角色面板"""
        ms = self.input.main_stats
        # 时之沙
        sands = ms.get("sands")
        if sands in MAIN_STAT_VALUES["sands"]:
            val = MAIN_STAT_VALUES["sands"][sands]
            if sands == "em":
                char.elemental_mastery += val
            else:
                setattr(char, sands, getattr(char, sands) + val)
        # 空之杯
        goblet = ms.get("goblet")
        if goblet in MAIN_STAT_VALUES["goblet"]:
            val = MAIN_STAT_VALUES["goblet"][goblet]
            if goblet == "elemental_dmg":
                char.elemental_dmg_bonus += val
            else:
                setattr(char, goblet, getattr(char, goblet) + val)
        # 理之冠
        circlet = ms.get("circlet")
        if circlet in MAIN_STAT_VALUES["circlet"]:
            val = MAIN_STAT_VALUES["circlet"][circlet]
            setattr(char, circlet, getattr(char, circlet) + val)

    def _build_character(self, substats: dict) -> Character:
        """根据副词条分配构建角色。

        面板叠加顺序（用户输入为起点，所有加成在其上叠加，不做截断）：
          1) 用户输入的基础面板值（起点：不含任何装备/天赋/命座加成）
          2) 主词条与副词条分配
          3) 常驻加成（圣遗物2件套、武器基础属性等）
          4) 触发型/条件型加成（武器特效、圣遗物4件套、天赋、命座等，
             经 passive_modifiers / passive_effects 注入）
        """
        char = Character(self.input.character_id, self.input.constellation_level)

        # ---- 1) 用户输入的基础面板值（起点）----
        pi = self.input.panel_inputs or {}
        if pi.get("atk"):
            # 调整固定攻击使 (base_atk + flat_atk) = 输入值，
            # 后续 ATK% 类加成可正确作用于该基础值
            char.flat_atk += max(0.0, float(pi["atk"]) - char.base_atk)
        # 注意：base_crit_rate / base_crit_dmg 已含突破加成；用户输入的是
        # 实际观察到的面板值（同样已含突破），因此以角色总基础值为锚点，
        # 增减部分允许为负，保证最终基础面板精确等于用户输入。
        if pi.get("crit_rate_pct") is not None:
            cr_in = min(float(pi["crit_rate_pct"]) / 100.0, 1.0)  # 合法性校验: ≤100%
            char.crit_rate = cr_in - char.base_crit_rate
        if pi.get("crit_dmg_pct") is not None:
            cd_in = float(pi["crit_dmg_pct"]) / 100.0
            char.crit_dmg = cd_in - char.base_crit_dmg
        if pi.get("em") is not None:
            char.elemental_mastery = float(pi["em"])

        # ---- 2) 主词条与副词条分配 ----
        self._apply_main_stats(char)
        for k, v in substats.items():
            if k == "em":
                char.elemental_mastery += v
            else:
                setattr(char, k, getattr(char, k) + v)

        # ---- 3)+4) 常驻/触发/条件型效果：全部在基础面板之上叠加 ----
        char.apply_passive(self.input.passive_modifiers)
        self._apply_full_effects(char, self.input.passive_effects,
                                 pi.get("er_pct"))
        return char

    @staticmethod
    def _apply_full_effects(char: Character, effects: dict, er_pct=None):
        """应用完整天赋效果：属性转换 / 充能缩放 / 充能效率上下文"""
        if not effects:
            if er_pct:
                char.er_total = 1.0 + float(er_pct) / 100.0
            return
        for conv in effects.get("conversions") or []:
            char.apply_conversion(conv)
        for sc in effects.get("er_scalings") or []:
            char.apply_er_scaling(sc)
        eff_er = effects.get("er_pct")
        if er_pct or eff_er:
            base = float(er_pct) if er_pct else 0.0
            extra = float(eff_er) if eff_er else 0.0
            char.er_total = 1.0 + base + extra
        # ---- 机制型天赋数值（v3）----
        for k, tiers in (effects.get("talent_multipliers") or {}).items():
            prev = char.talent_multipliers.get(k) or []
            char.talent_multipliers[k] = (
                [max(a, b) for a, b in zip(prev + [0.0] * len(tiers), tiers)]
                if prev else list(tiers)
            )
        for eh in effects.get("extra_hits") or []:
            if eh not in char.extra_hits:
                char.extra_hits.append(dict(eh))
        for da in effects.get("damage_amps") or []:
            if da not in char.damage_amps:
                char.damage_amps.append(dict(da))
        char.stack_context.update(effects.get("stack_context") or {})
        # 状态标签触发上下文（UI 开关 → 引擎门控）
        char.active_states.update(effects.get("active_states") or {})

    def _build_member_character(self, cfg: dict) -> Character:
        """按队伍成员独立配置构建队友角色（武器/圣遗物/面板/固有天赋）"""
        char = Character(cfg.get("character_id"), cfg.get("constellation_level", 0))
        panel = cfg.get("panel") or {}
        # 面板锚定：用户输入的是观察到的总面板值（已含突破/基础成长），
        # 与主力角色 _build_character 保持一致——以角色总基础值为锚点，
        # 增减部分允许为负，保证最终面板精确等于用户输入，避免双重计入突破属性。
        if panel.get("atk"):
            char.flat_atk += max(0.0, float(panel["atk"]) - char.base_atk)
        if panel.get("crit_rate_pct"):
            cr_in = min(float(panel["crit_rate_pct"]) / 100.0, 1.0)
            char.crit_rate = cr_in - char.base_crit_rate
        if panel.get("crit_dmg_pct"):
            char.crit_dmg = float(panel["crit_dmg_pct"]) / 100.0 - char.base_crit_dmg
        if panel.get("em"):
            char.elemental_mastery = float(panel["em"])
        if panel.get("lunar_bonus_pct"):
            char.lunar_dmg_bonus += float(panel["lunar_bonus_pct"]) / 100.0
        char.apply_passive(cfg.get("passive_modifiers"))
        self._apply_full_effects(char, cfg.get("passive_effects"),
                                 panel.get("er_pct"))
        return char

    def _build_effect_manager(self, char: Character, weapon_id=None,
                              refinement: int = 1, artifact_set_2=None,
                              artifact_set_4=None) -> EffectManager:
        """构建并应用效果管理器（默认使用主角配置）"""
        em = EffectManager(char)
        wid = weapon_id or self.input.weapon_id
        a2 = artifact_set_2 or self.input.artifact_set_2
        a4 = artifact_set_4 or self.input.artifact_set_4
        if wid:
            em.apply_weapon_effect(wid, refinement)
        if a2:
            em.apply_artifact_effect(set_2_id=a2)
        if a4:
            em.apply_artifact_effect(set_4_id=a4)
        em.apply_constellation_effects()
        em.trigger_event("always")
        return em

    def _evaluate(self, substats: dict, char: Character = None):
        """
        评估一组副词条分配，返回 (期望伤害, 计算结果, 暴击率, 暴击伤害)
        :param char: 可选，已构建好的角色实例（避免重复构建）
        """
        if char is None:
            char = self._build_character(substats)
        em = self._build_effect_manager(char)

        # 队伍构建：优先使用成员独立配置（UI 队伍面板），否则回退 team_members
        team = None
        if self.input.team_configs and any(self.input.team_configs):
            from .team import Team
            members = []
            for cfg in self.input.team_configs:
                if cfg and cfg.get("character_id"):
                    mc = self._build_member_character(cfg)
                    members.append(mc)
                else:
                    members.append(None)
            while len(members) < 4:
                members.append(None)
            team = Team(members[:4])
        else:
            active_members = [m for m in self.input.team_members if m]
            if len(active_members) >= 2:
                from .team import Team
                members = []
                for mid in self.input.team_members:
                    if mid:
                        mc = self._build_character({}) if mid == self.input.character_id \
                            else Character(mid, self.input.constellation_level)
                        mem = self._build_effect_manager(mc)
                        members.append(mem.character)
                    else:
                        members.append(None)
                while len(members) < 4:
                    members.append(None)
                team = Team(members[:4])

        result = calculate_damage(
            character=char,
            skill_type=self.input.skill_type,
            talent_level=self.input.talent_level,
            enemy_level=self.input.enemy_level,
            enemy_res=self.input.enemy_res,
            reaction_type=self.input.reaction_type,
            is_crit=False,
            effect_manager=em,
            team=team,
        )
        non_crit = result["damage"]
        panel = char.get_effective_panel()
        mods = em.get_final_modifiers()
        crit_rate = min(panel["crit_rate"] + mods["crit_rate"], 1.0)
        crit_dmg = panel["crit_dmg"] + mods["crit_dmg"]

        if self.input.reaction_type in TRANSFORMATIVE:
            expected = non_crit
            # 剧变反应不暴击，暴击区保持 1.0
        else:
            expected = non_crit * (1 + crit_rate * crit_dmg)
            # 暴击区系数应反映期望伤害的实际乘数 (1 + CR×CD)，
            # 而非 calculate_damage 内部 is_crit=False 的占位值 1.0
            result["breakdown"]["crit_factor"] = 1.0 + crit_rate * crit_dmg
            result["breakdown"]["is_crit"] = False
            logger.debug(
                "暴击区系数: %.4f (CR=%.4f, CD=%.4f)",
                result["breakdown"]["crit_factor"], crit_rate, crit_dmg,
            )

        return expected, result, crit_rate, crit_dmg

    def _allocation_to_substats(self, alloc: list) -> dict:
        """将词条分配列表转换为属性字典"""
        return {k: alloc[i] * ROLL_VALUES[k] for i, k in enumerate(SUBSTAT_KEYS)}

    def optimize(self, iterations: int = 15000,
                 progress_callback=None) -> OptimizationResult:
        """
        执行优化搜索
        :param iterations: 随机搜索迭代次数
        :param progress_callback: 可选 fn(done, total)，用于 UI 进度显示
        :return: OptimizationResult
        """
        N = self.input.total_substat_rolls
        best = None
        best_score = -1.0
        best_alloc = None

        # 用户已直接指定暴击率时，输入值作为基础面板起点，
        # 不应再因低于 min_crit_rate 而拒绝所有分配方案
        pi = self.input.panel_inputs or {}
        eff_min_cr = 0.0 if pi.get("crit_rate_pct") is not None \
            else self.input.min_crit_rate
        if eff_min_cr != self.input.min_crit_rate:
            logger.debug(
                "用户指定 crit_rate=%.1f%%，min_crit_rate 约束已放宽",
                float(pi["crit_rate_pct"]),
            )

        random.seed(42)
        refine_iterations = 3000
        total_steps = iterations + refine_iterations

        for i in range(iterations):
            # 随机分配 N 个词条到 4 个属性
            alloc = [0, 0, 0, 0]
            for _ in range(N):
                alloc[random.randrange(4)] += 1
            substats = self._allocation_to_substats(alloc)

            # 构建一次角色，约束检查与评估复用同一实例
            char_tmp = self._build_character(substats)
            if char_tmp.get_effective_panel()["crit_rate"] < eff_min_cr:
                continue

            score, result, cr, cd = self._evaluate(substats, char_tmp)
            if score > best_score:
                best_score = score
                best = (substats, result, cr, cd)
                best_alloc = alloc[:]

            if i % 1000 == 0:
                self.history.append({"iteration": i, "damage": score})
            if progress_callback and i % 500 == 0:
                progress_callback(i, total_steps)

        # 局部细化：在最优分配附近 ±2 词条搜索
        if best_alloc is not None:
            for j in range(refine_iterations):
                alloc = best_alloc[:]
                # 随机移动 1~2 个词条
                for _ in range(random.randint(1, 2)):
                    src = random.randrange(4)
                    if alloc[src] > 0:
                        dst = random.randrange(4)
                        alloc[src] -= 1
                        alloc[dst] += 1
                substats = self._allocation_to_substats(alloc)
                char_tmp = self._build_character(substats)
                if char_tmp.get_effective_panel()["crit_rate"] < eff_min_cr:
                    continue
                score, result, cr, cd = self._evaluate(substats, char_tmp)
                if score > best_score:
                    best_score = score
                    best = (substats, result, cr, cd)
                    best_alloc = alloc[:]
                if progress_callback and j % 500 == 0:
                    progress_callback(iterations + j, total_steps)

        if progress_callback:
            progress_callback(total_steps, total_steps)

        if best is None:
            raise ValueError("未找到满足约束的属性分配，请降低最小暴击率要求或减少总词条数")

        substats, result, cr, cd = best
        char = self._build_character(substats)
        panel = char.get_effective_panel()

        optimal_stats = {
            "atk_percent": panel["atk"] / (char.base_atk + char.flat_atk) - 1 if (char.base_atk + char.flat_atk) else 0,
            "crit_rate": cr,
            "crit_dmg": cd,
            "em": panel["elemental_mastery"],
            "elemental_dmg_bonus": panel["elemental_dmg_bonus"],
        }
        # 攻击力百分比（相对于基础）
        optimal_stats["atk_percent"] = max(0.0, optimal_stats["atk_percent"])

        allocation = {SUBSTAT_KEYS[i]: best_alloc[i] for i in range(4)}

        suggestion = self._generate_suggestion(optimal_stats, allocation, cr, cd)

        return OptimizationResult(
            optimal_stats=optimal_stats,
            max_damage=best_score,
            damage_breakdown=result["breakdown"],
            history=self.history,
            suggestion=suggestion,
            allocation=allocation,
        )

    def _generate_suggestion(self, optimal_stats, allocation, cr, cd) -> str:
        """生成培养建议文字"""
        tips = []
        if cr < 0.70:
            tips.append(
                f"建议优先将暴击率堆到 70% 以上（当前 {cr*100:.1f}%），"
                f"再全力堆暴击伤害。当前暴击率词条分配 {allocation.get('crit_rate', 0)} 个。"
            )
        else:
            tips.append(
                f"暴击率已达 {cr*100:.1f}%，可放心堆暴击伤害（当前 {cd*100:.1f}%）。"
            )

        em = optimal_stats.get("em", 0)
        if em < 120:
            tips.append(f"元素精通仅 {em:.0f}，对反应收益较低，可适当补充（建议 120~200）。")
        elif em > 300:
            tips.append(f"元素精通已达 {em:.0f}，边际收益递减，可将词条转移至双暴/攻击。")
        else:
            tips.append(f"元素精通 {em:.0f} 处于合理区间，收益较好。")

        atk_p = optimal_stats.get("atk_percent", 0) * 100
        tips.append(f"攻击力加成约 {atk_p:.1f}%，若低于 50% 可考虑补充攻击% 词条。")

        return "\n".join(f"• {t}" for t in tips)