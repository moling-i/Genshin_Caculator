"""
优化器面板语义测试：用户输入为基础面板（起点），所有效果在其上叠加。

验证场景（用户需求）：
1. 输入暴击率60% + 圣遗物4件套暴击率+12%  → 最终面板暴击率 = 72%
2. 输入暴击伤害200% + 武器特效暴击伤害+20% → 最终面板暴击伤害 = 220%
3. 输入精通100 + 天赋精通转化加成          → 最终面板精通 = 100 + 转化值
4. 输入攻击力1000 + 圣遗物2件套攻击+18%    → 最终面板攻击力 = 1180

另含：crit_factor 期望系数校验、武器效果展示回退链。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import data_loader
from src.optimizer import DamageOptimizer, OptimizationInput


def _make_input(panel_inputs, passive_modifiers=None):
    return OptimizationInput(
        character_id="10000016",  # 迪卢克
        constellation_level=0,
        talent_level=10,
        skill_type="burst",
        enemy_level=90,
        enemy_res=0.1,
        reaction_type=None,
        weapon_id=None,
        artifact_set_2=None,
        artifact_set_4=None,
        total_substat_rolls=30,
        min_crit_rate=0.2,
        main_stats={"sands": None, "goblet": None, "circlet": None},
        panel_inputs=panel_inputs,
        passive_modifiers=passive_modifiers,
    )


class TestPanelAsStartingPoint(unittest.TestCase):
    """用户输入为起点，效果叠加而非截断。"""

    def _panel_of(self, panel_inputs, passive_modifiers=None):
        opt = DamageOptimizer(_make_input(panel_inputs, passive_modifiers))
        char = opt._build_character({})
        return char.get_effective_panel()

    def test_crit_rate_input_plus_set_bonus(self):
        """场景1：输入暴击率60% + 4件套暴击率+12% → 72%"""
        panel = self._panel_of(
            {"crit_rate_pct": 60.0},
            passive_modifiers={"crit_rate": 0.12},
        )
        self.assertAlmostEqual(panel["crit_rate"], 0.72, places=6)

    def test_crit_dmg_input_plus_weapon_bonus(self):
        """场景2：输入暴击伤害200% + 武器特效暴击伤害+20% → 220%"""
        panel = self._panel_of(
            {"crit_dmg_pct": 200.0},
            passive_modifiers={"crit_dmg": 0.20},
        )
        self.assertAlmostEqual(panel["crit_dmg"], 2.20, places=6)

    def test_em_input_plus_conversion_bonus(self):
        """场景3：输入精通100 + 天赋精通加成50 → 150"""
        panel = self._panel_of(
            {"em": 100.0},
            passive_modifiers={"elemental_mastery": 50.0},
        )
        self.assertAlmostEqual(panel["elemental_mastery"], 150.0, places=6)

    def test_atk_input_plus_set_percent(self):
        """场景4：输入攻击力1000 + 2件套攻击+18% → 1180"""
        panel = self._panel_of(
            {"atk": 1000.0},
            passive_modifiers={"atk_percent": 0.18},
        )
        self.assertAlmostEqual(panel["atk"], 1180.0, places=6)

    def test_substats_stack_on_panel(self):
        """副词条分配在用户基础面板之上继续叠加（优化器自由度保留）。"""
        opt = DamageOptimizer(_make_input({"crit_rate_pct": 20.0}))
        char = opt._build_character({"crit_rate": 0.10})
        panel = char.get_effective_panel()
        self.assertAlmostEqual(panel["crit_rate"], 0.30, places=6)

    def test_crit_rate_input_validated_to_100(self):
        """合法性校验：输入超过100%按100%处理（仅校验，不截断效果）。"""
        panel = self._panel_of(
            {"crit_rate_pct": 150.0},
            passive_modifiers={"crit_rate": 0.12},
        )
        # get_effective_panel 内部 min(..., 1.0)，效果仍参与计算
        self.assertLessEqual(panel["crit_rate"], 1.0)


class TestOptimizerEndToEnd(unittest.TestCase):
    """完整优化流程冒烟：面板起点 + crit_factor 真实化。"""

    def _run(self, crit_rate_pct, crit_dmg_pct, em):
        params = _make_input({
            "atk": 1500.0,
            "crit_rate_pct": float(crit_rate_pct),
            "crit_dmg_pct": float(crit_dmg_pct),
            "em": float(em),
        })
        return DamageOptimizer(params).optimize(iterations=500,
                                                progress_callback=None)

    def test_optimize_runs_and_crit_factor_is_expectation(self):
        result = self._run(crit_rate_pct=50.0, crit_dmg_pct=235.0, em=105.0)
        bd = result.damage_breakdown
        cr = result.optimal_stats["crit_rate"]
        cd = result.optimal_stats["crit_dmg"]
        expected_cf = 1.0 + cr * cd
        self.assertAlmostEqual(bd["crit_factor"], expected_cf, places=3)
        self.assertGreater(bd["crit_factor"], 1.5)
        # 用户面板作为起点：结果应 ≥ 起点（副词条只增不减）
        self.assertGreaterEqual(cd, 2.35 - 1e-6)
        self.assertGreaterEqual(em_val := result.optimal_stats["em"], 105.0 - 1e-6)


class TestWeaponEffectDisplay(unittest.TestCase):
    """武器被动效果展示（Meropide 权威文案 → 本地参数 → desc 回退链）。"""

    def test_known_weapon_returns_meropide_text(self):
        # 和璞鸢（5星长柄武器）在 Meropide 中有权威文案（首句为别名"昭理的鸢之枪"）
        text = data_loader.get_weapon_effect("13505", refinement=1)
        self.assertTrue(text, "和璞鸢应返回非空武器效果文案")
        self.assertIn("昭理的鸢之枪", text)

    def test_refinement_note_generated(self):
        text = data_loader.get_weapon_effect("13505", refinement=5)
        self.assertIsInstance(text, str)
        self.assertIn("精炼", text)

    def test_unknown_weapon_returns_string(self):
        self.assertEqual(data_loader.get_weapon_effect("99999999"), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)

