"""
队伍 DPS 联合优化器

在「轮换」固定的前提下，联合搜索 4 名成员各自的副词条分配
（攻击% / 暴击率 / 暴击伤害 / 元素精通），使整队 DPS 最高。

之所以联合而非只优化主力：队友联动会改变彼此基础数值，
例如砂糖/万叶「精通共享」、双火共鸣加攻、班尼特 Q 增攻等，
单独优化主力会忽略这些交叉增益。

搜索策略：随机搜索 + 局部细化（与单体优化器一致）。
每个成员有独立的词条预算，分配向量为 4（成员）× 4（属性）的整型张量。
"""
import logging
import random
from .character import Character
from .effects import EffectManager
from .team import Team
from .team_dps import evaluate_team_dps
from .optimizer import (
    ROLL_VALUES, MAIN_STAT_VALUES, SUBSTAT_KEYS, DamageOptimizer,
)

logger = logging.getLogger(__name__)

SUBSTAT_KEYS = SUBSTAT_KEYS  # 显式保留引用，便于阅读


def _apply_main_stats(char: Character, ms: dict):
    """将主词条数值叠加到角色面板（与单体优化器逻辑一致）"""
    if not ms:
        return
    # 时之沙
    sands = ms.get("sands")
    if sands in MAIN_STAT_VALUES["sands"]:
        val = MAIN_STAT_VALUES["sands"][sands]
        if sands == "em":
            char.elemental_mastery += val
        elif sands == "er":
            char.er_total += val          # 充能沙 → 元素充能效率
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


def _build_member(cfg: dict, substats: dict, main_stats: dict):
    """
    按成员配置 + 副词条分配构建 (角色, 效果管理器, 天赋等级表)。
    面板叠加顺序（与单体优化器 _build_member_character 一致）：
      用户输入基础面板 → 主词条/副词条 → 固有天赋/命座/武器/圣遗物效果
    """
    char = Character(cfg["character_id"], cfg.get("constellation_level", 0))
    panel = cfg.get("panel") or {}
    # 面板锚定：用户输入的是观察到的总面板值（已含突破），增减允许为负
    if panel.get("atk"):
        char.flat_atk += max(0.0, float(panel["atk"]) - char.base_atk)
    if panel.get("crit_rate_pct"):
        cr_in = min(float(panel["crit_rate_pct"]) / 100.0, 1.0)
        char.crit_rate = cr_in - char.base_crit_rate
    if panel.get("crit_dmg_pct"):
        char.crit_dmg = float(panel["crit_dmg_pct"]) / 100.0 - char.base_crit_dmg
    if panel.get("em") is not None:
        char.elemental_mastery = float(panel["em"])
    if panel.get("lunar_bonus_pct"):
        char.lunar_dmg_bonus += float(panel["lunar_bonus_pct"]) / 100.0
    if panel.get("elemental_dmg_bonus_pct"):
        char.elemental_dmg_bonus += float(panel["elemental_dmg_bonus_pct"]) / 100.0

    _apply_main_stats(char, main_stats)
    for k, v in substats.items():
        if k == "em":
            char.elemental_mastery += v
        else:
            setattr(char, k, getattr(char, k) + v)

    char.apply_passive(cfg.get("passive_modifiers"))
    DamageOptimizer._apply_full_effects(char, cfg.get("passive_effects"), panel.get("er_pct"))

    em = EffectManager(char)
    wid = cfg.get("weapon_id")
    a2 = cfg.get("artifact_set_2")
    a4 = cfg.get("artifact_set_4")
    d22 = cfg.get("is_double_two_piece", False)
    if wid:
        em.apply_weapon_effect(wid, cfg.get("refinement", 1))
    if d22:
        if a2:
            em.apply_artifact_pieces(a2, {2})
        if a4:
            em.apply_artifact_pieces(a4, {2})
    else:
        if a4:
            em.apply_artifact_effect(set_4_id=a4)
        elif a2:
            em.apply_artifact_effect(set_2_id=a2)
    em.apply_constellation_effects()
    em.trigger_event("always")

    tl = cfg.get("talent_levels") or {"normal": 10, "skill": 10, "burst": 10}
    return char, em, tl


def _allocation_to_substats(alloc):
    """将 4 维分配列表转为属性字典"""
    return {k: alloc[i] * ROLL_VALUES[k] for i, k in enumerate(SUBSTAT_KEYS)}


class TeamDPSOptimizationInput:
    """队伍 DPS 联合优化输入"""

    def __init__(self, team_configs, rotation,
                 total_substat_rolls_per_member, main_stats_per_member,
                 enemy_level=90, enemy_res=0.1, min_crit_rate_per_member=None,
                 star_params=None):
        self.team_configs = team_configs              # 长度 4 的配置字典列表（可含 None）
        self.rotation = rotation                      # Rotation 实例
        self.total_substat_rolls_per_member = list(total_substat_rolls_per_member)
        self.main_stats_per_member = list(main_stats_per_member)
        self.enemy_level = enemy_level
        self.enemy_res = enemy_res
        self.min_crit_rate_per_member = (
            list(min_crit_rate_per_member)
            if min_crit_rate_per_member else [0.0] * 4
        )
        self.star_params = dict(star_params or {})


class TeamDPSOptimizationResult:
    """队伍 DPS 联合优化结果"""

    def __init__(self, allocations, max_dps, result, history):
        self.allocations = allocations    # 长度 4 的分配字典列表（按成员）
        self.max_dps = max_dps            # 最大队伍 DPS
        self.result = result              # evaluate_team_dps 的完整返回
        self.history = history            # 收敛曲线


class TeamDPSOptimizer:
    """队伍 DPS 联合优化器"""

    def __init__(self, input_params: TeamDPSOptimizationInput):
        self.input = input_params
        self.history = []

    def _evaluate(self, alloc):
        """alloc: 长度 4 的「每成员 4 维分配列表」"""
        members, ems, tls = [], [], []
        for i, cfg in enumerate(self.input.team_configs):
            if not cfg or not cfg.get("character_id"):
                members.append(None)
                ems.append(None)
                tls.append(None)
                continue
            char, em, tl = _build_member(cfg, _allocation_to_substats(alloc[i]),
                                         self.input.main_stats_per_member[i])
            members.append(char)
            ems.append(em)
            tls.append(tl)

            # 最小暴击率约束（成员面板锚点已设定，此处仅作可行性过滤）
            min_cr = self.input.min_crit_rate_per_member[i]
            if min_cr and min_cr > 0:
                panel = char.get_effective_panel()
                mods = ems[-1].get_final_modifiers()
                cr = min(panel["crit_rate"] + mods["crit_rate"], 1.0)
                if cr + 1e-9 < min_cr:
                    return -1.0, None

        res = evaluate_team_dps(
            members, self.input.rotation,
            enemy_level=self.input.enemy_level,
            enemy_res=self.input.enemy_res,
            effect_managers=ems,
            talent_levels=tls,
            star_params=self.input.star_params,
        )
        return res["dps"], res

    def optimize(self, iterations=4000, refine_iterations=1500, progress_callback=None):
        """
        执行联合优化搜索。
        :param iterations: 随机搜索迭代次数
        :param refine_iterations: 局部细化迭代次数
        :param progress_callback: 可选 fn(done, total)
        """
        budgets = self.input.total_substat_rolls_per_member
        best_alloc = None
        best_score = -1.0
        best_res = None

        random.seed(42)
        total_steps = iterations + refine_iterations

        for it in range(iterations):
            alloc = []
            for b in budgets:
                a = [0, 0, 0, 0]
                for _ in range(int(b)):
                    a[random.randrange(4)] += 1
                alloc.append(a)
            score, res = self._evaluate(alloc)
            if score > best_score:
                best_score = score
                best_alloc = [a[:] for a in alloc]
                best_res = res
            if it % 500 == 0:
                self.history.append({"iteration": it, "dps": score})
            if progress_callback and it % 500 == 0:
                progress_callback(it, total_steps)

        # 局部细化：在最优分配附近 ±1~2 词条搜索（成员内/跨成员迁移）
        if best_alloc is not None:
            for j in range(refine_iterations):
                alloc = [a[:] for a in best_alloc]
                for _ in range(random.randint(1, 2)):
                    mi = random.randrange(4)
                    if budgets[mi] <= 0:
                        continue
                    src = random.randrange(4)
                    if alloc[mi][src] > 0:
                        dst = random.randrange(4)
                        alloc[mi][src] -= 1
                        alloc[mi][dst] += 1
                score, res = self._evaluate(alloc)
                if score > best_score:
                    best_score = score
                    best_alloc = [a[:] for a in alloc]
                    best_res = res
                if progress_callback and j % 500 == 0:
                    progress_callback(iterations + j, total_steps)

        if progress_callback:
            progress_callback(total_steps, total_steps)

        if best_alloc is None:
            raise ValueError("未找到满足约束的队伍词条分配，请降低最小暴击率或总词条数要求")

        allocations = [
            {SUBSTAT_KEYS[i]: best_alloc[m][i] for i in range(4)}
            for m in range(4)
        ]
        return TeamDPSOptimizationResult(
            allocations=allocations,
            max_dps=best_score,
            result=best_res,
            history=self.history,
        )
