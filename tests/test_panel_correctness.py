# -*- coding: utf-8 -*-
"""
面板数值正确性单元测试。

覆盖：
- ascension_bonus 突破属性数据修复后的正确性（暴击/暴伤不得被多阶段累加放大）
- 主力角色面板锚定（用户输入 = 最终基础面板）
- 队友面板锚定与主力一致（不双重计入突破属性）
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import data_loader
from src.character import Character
from src.optimizer import DamageOptimizer, OptimizationInput


def _char_id(name):
    return str(next(
        c["id"] for c in data_loader.get_characters()
        if c.get("name_cn") == name
    ))


class TestAscensionBonus(unittest.TestCase):
    """ascension_bonus 数据：突破属性应为最终阶段值，而非多阶段累加。"""

    def test_known_values(self):
        """官方满破值抽查：胡桃/甘雨暴伤38.4%、迪卢克/琴暴率19.2%等。"""
        expectations = [
            ("胡桃", "FIGHT_PROP_CRITICAL_HURT", 0.384),
            ("甘雨", "FIGHT_PROP_CRITICAL_HURT", 0.384),
            ("迪卢克", "FIGHT_PROP_CRITICAL", 0.192),
            ("琴", "FIGHT_PROP_HEAL_ADD", 0.221),
            ("纳西妲", "FIGHT_PROP_ELEMENT_MASTERY", 115.2),
        ]
        chars = {c["name_cn"]: c for c in data_loader.get_characters()}
        for name, prop, expected in expectations:
            asc = chars[name].get("ascension_bonus") or {}
            self.assertIn(prop, asc, f"{name} 缺少突破属性 {prop}")
            # 允许文案舍入差异（如 Meropide 将纳西妲精通 115.2 写作 115）
            self.assertAlmostEqual(
                float(asc[prop]), expected, delta=0.5,
                msg=f"{name}.{prop} 应≈{expected}，实际 {asc[prop]}",
            )

    def test_no_inflated_crit(self):
        """全表检查：暴击/暴伤突破值不得超过官方最大档。"""
        for c in data_loader.get_characters():
            asc = c.get("ascension_bonus") or {}
            cr = asc.get("FIGHT_PROP_CRITICAL")
            cd = asc.get("FIGHT_PROP_CRITICAL_HURT")
            if cr is not None:
                self.assertLessEqual(float(cr), 0.20,
                                     f"{c['name_cn']} 暴击率突破异常: {cr}")
            if cd is not None:
                self.assertLessEqual(float(cd), 0.40,
                                     f"{c['name_cn']} 暴击伤害突破异常: {cd}")

    def test_character_base_crit(self):
        """Character 基础暴击 = JSON 基础值 + 正确的突破加成。"""
        hu = Character(_char_id("胡桃"))
        self.assertAlmostEqual(hu.base_crit_dmg, 0.5 + 0.384, places=6)
        diluc = Character(_char_id("迪卢克"))
        self.assertAlmostEqual(diluc.base_crit_rate, 0.05 + 0.192, places=6)


class TestPanelAnchoring(unittest.TestCase):
    """面板输入语义：无论主力还是队友，输入值即最终基础面板。"""

    @staticmethod
    def _member_panel(char_id, panel):
        opt = DamageOptimizer(OptimizationInput(
            character_id=char_id, panel_inputs={},
            team_configs=[{"character_id": char_id, "panel": dict(panel)}],
        ))
        return opt._build_member_character(
            {"character_id": char_id, "panel": panel}
        )

    def test_member_crit_anchored(self):
        """胡桃输入暴伤50% → 有效面板暴伤应恰为50%（而非50%+88.4%）。"""
        cid = _char_id("胡桃")
        char = self._member_panel(cid, {
            "atk": 1500, "crit_rate_pct": 60.0, "crit_dmg_pct": 50.0,
            "em": 100,
        })
        panel = char.get_effective_panel()
        self.assertAlmostEqual(panel["crit_dmg"], 0.5, places=9)
        self.assertAlmostEqual(panel["crit_rate"], 0.6, places=9)
        self.assertAlmostEqual(panel["elemental_mastery"], 100.0, places=9)

    def test_main_char_and_member_consistent(self):
        """同一角色同样面板，主力与队友的有效暴击应一致。"""
        cid = _char_id("迪卢克")
        panel = {"atk": 2000, "crit_rate_pct": 70.0, "crit_dmg_pct": 140.0}
        opt = DamageOptimizer(OptimizationInput(
            character_id=cid, panel_inputs=dict(panel),
        ))
        main = opt._build_character({})
        member = self._member_panel(cid, panel)
        p_main = main.get_effective_panel()
        p_mem = member.get_effective_panel()
        self.assertAlmostEqual(p_main["crit_rate"], p_mem["crit_rate"], places=9)
        self.assertAlmostEqual(p_main["crit_dmg"], p_mem["crit_dmg"], places=9)


if __name__ == "__main__":
    unittest.main()
