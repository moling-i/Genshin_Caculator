"""
三合一修复验证测试：
1. 优化器输入透传：面板输入的暴击伤害 / 精通应作为上限约束，
   优化结果不超过用户输入；用户输入的精通在结果中保留。
2. 暴击区系数：优化器输出 breakdown 中 crit_factor 应反映期望伤害乘数
   (1 + CR×CD)，而非 calculate_damage 内部的占位值 1.0。
3. 武器效果展示：get_weapon_effect 应能返回 Meropide 权威文案，
   且按精炼等级附上对应参数。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import data_loader
from src.optimizer import DamageOptimizer, OptimizationInput


class TestOptimizerInputPassthrough(unittest.TestCase):
    """问题1：用户输入应作为上限约束。"""

    def _run(self, crit_dmg_pct, em, crit_rate_pct=5.0, atk=1500):
        params = OptimizationInput(
            character_id="10000016",  # 迪卢克（用于稳定数据）
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
            main_stats={"sands": "atk_percent",
                        "goblet": "elemental_dmg",
                        "circlet": "crit_dmg"},
            panel_inputs={
                "atk": float(atk),
                "crit_rate_pct": float(crit_rate_pct),
                "crit_dmg_pct": float(crit_dmg_pct),
                "em": float(em),
            },
        )
        result = DamageOptimizer(params).optimize(iterations=500,
                                                  progress_callback=None)
        return result

    def test_crit_dmg_does_not_exceed_input(self):
        """用户输入 240% 暴击伤害，结果不应超过 240%（约束为上限）。"""
        result = self._run(crit_dmg_pct=240.0, em=105.0)
        cd = result.optimal_stats["crit_dmg"]
        self.assertLessEqual(cd, 2.40 + 1e-6,
                             f"暴击伤害 {cd} 超过了用户输入 240%")

    def test_em_preserved(self):
        """用户输入 105 精通，结果应保留（约 105）。"""
        result = self._run(crit_dmg_pct=240.0, em=105.0)
        em = result.optimal_stats["em"]
        self.assertGreaterEqual(em, 100.0,
                                f"元素精通 {em} 未保留用户输入的 105")

    def test_crit_factor_not_one(self):
        """暴击区系数应反映期望乘数，而非 1.0。"""
        result = self._run(crit_dmg_pct=240.0, em=105.0, crit_rate_pct=50.0)
        bd = result.damage_breakdown
        self.assertIn("crit_factor", bd)
        # 期望暴击区系数 ≈ 1 + CR×CD
        expected = 1.0 + 0.50 * 2.40
        self.assertAlmostEqual(bd["crit_factor"], expected, places=3,
                               msg=f"crit_factor={bd['crit_factor']} 应为 {expected}")


class TestCritZoneCoefficient(unittest.TestCase):
    """问题2：暴击区系数显示正确。"""

    def test_breakdown_crit_factor_is_expectation(self):
        params = OptimizationInput(
            character_id="10000016",
            constellation_level=0,
            talent_level=10,
            skill_type="burst",
            enemy_level=90,
            enemy_res=0.1,
            reaction_type=None,
            total_substat_rolls=10,
            min_crit_rate=0.2,
            main_stats={"sands": "atk_percent",
                        "goblet": "elemental_dmg",
                        "circlet": "crit_dmg"},
            panel_inputs={"atk": 1500, "crit_rate_pct": 50.0,
                          "crit_dmg_pct": 235.0, "em": 0.0},
        )
        result = DamageOptimizer(params).optimize(iterations=200,
                                                  progress_callback=None)
        bd = result.damage_breakdown
        cr = result.optimal_stats["crit_rate"]
        cd = result.optimal_stats["crit_dmg"]
        expected_cf = 1.0 + cr * cd
        self.assertAlmostEqual(bd["crit_factor"], expected_cf, places=3)
        # 不应为占位值 1.0（除非 CR/CD 为 0，这里显然不是）
        self.assertGreater(bd["crit_factor"], 1.5)


class TestWeaponEffectDisplay(unittest.TestCase):
    """问题3：武器效果展示。"""

    def test_known_weapon_returns_meropide_text(self):
        # 和璞鸢（5星长柄武器）在 Meropide 中有权威文案（首句为别名"昭理的鸢之枪"）
        text = data_loader.get_weapon_effect("13505", refinement=1)
        self.assertTrue(text, "和璞鸢应返回非空武器效果文案")
        self.assertIn("昭理的鸢之枪", text)

    def test_refinement_note_generated(self):
        # 精炼参数应被格式化进输出（即便无 meropide 文案也至少返回参数行）
        text = data_loader.get_weapon_effect("13505", refinement=5)
        self.assertIsInstance(text, str)
        self.assertIn("精炼", text)

    def test_unknown_weapon_returns_string(self):
        # 不存在的武器应返回空字符串而非报错
        self.assertEqual(data_loader.get_weapon_effect("99999999"), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
