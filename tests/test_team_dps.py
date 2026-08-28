"""
单元测试 - 队伍 DPS 评估与联合优化
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import data_loader, Character
from src.team_dps import Rotation, RotationStep, evaluate_team_dps, PRESET_ROTATIONS
from src.team_optimizer import (
    TeamDPSOptimizer, TeamDPSOptimizationInput, _build_member, _allocation_to_substats,
)


def _cid(name):
    cs = data_loader.get_characters()
    return next((str(c.get("id")) for c in cs if c.get("name_cn") == name), None)


def _mini_cfg(name, atk=1500, cr=5.0, cd=50.0, em=0):
    return {
        "character_id": _cid(name),
        "constellation_level": 0,
        "weapon_id": None, "refinement": 1,
        "artifact_set_2": None, "artifact_set_4": None,
        "is_double_two_piece": False,
        "talent_levels": {"normal": 10, "skill": 10, "burst": 10},
        "panel": {"atk": atk, "crit_rate_pct": cr, "crit_dmg_pct": cd, "em": em,
                  "lunar_bonus_pct": 0.0, "er_pct": 0.0},
        "passive_modifiers": {}, "passive_effects": {}, "states": [], "display_name": name,
    }


class TestTeamDPSEval(unittest.TestCase):
    def test_preset_rotation_runs(self):
        hu = Character(_cid("胡桃"), 0)
        xq = Character(_cid("行秋"), 0)
        zl = Character(_cid("钟离"), 0)
        kz = Character(_cid("枫原万叶"), 0)
        for c in (hu, xq, zl, kz):
            c.flat_atk += max(0.0, 1500 - c.base_atk)
        hu.elemental_dmg_bonus += 0.466
        members = [hu, xq, zl, kz]
        rot = PRESET_ROTATIONS["玛薇卡火神队（示例）"]
        res = evaluate_team_dps(members, rot, effect_managers=[None] * 4, talent_levels=[None] * 4)
        self.assertGreater(res["total_damage"], 0)
        self.assertGreater(res["dps"], 0)
        self.assertAlmostEqual(res["total_damage"] / res["total_time"], res["dps"], places=4)
        print(f"示例轮换 队伍DPS={res['dps']:.1f}")


class TestJointOptimizer(unittest.TestCase):
    def test_joint_optimize(self):
        cfgs = [
            _mini_cfg("胡桃", atk=1500, cr=5.0, cd=50.0, em=0),
            _mini_cfg("行秋", atk=1500, cr=5.0, cd=50.0, em=120),
            _mini_cfg("钟离", atk=1500, cr=5.0, cd=50.0, em=0),
            _mini_cfg("枫原万叶", atk=1500, cr=5.0, cd=50.0, em=800),
        ]
        main_stats = [
            {"sands": "atk_percent", "goblet": "elemental_dmg", "circlet": "crit_dmg"},
            {"sands": "er", "goblet": "elemental_dmg", "circlet": "crit_dmg"},
            {"sands": "hp_percent", "goblet": "hp_percent", "circlet": "crit_rate"},
            {"sands": "em", "goblet": "elemental_dmg", "circlet": "crit_dmg"},
        ]
        rot = PRESET_ROTATIONS["玛薇卡火神队（示例）"]
        inp = TeamDPSOptimizationInput(
            team_configs=cfgs, rotation=rot,
            total_substat_rolls_per_member=[20, 20, 20, 20],
            main_stats_per_member=main_stats,
            enemy_level=90, enemy_res=0.1,
        )
        opt = TeamDPSOptimizer(inp)
        res = opt.optimize(iterations=300, refine_iterations=100)
        self.assertGreater(res.max_dps, 0)
        # 4 名成员都应给出分配
        self.assertEqual(len(res.allocations), 4)
        for alloc in res.allocations:
            self.assertEqual(sum(alloc.values()), 20)
        print(f"联合优化 最大队伍DPS={res.max_dps:.1f}")
        print("分配:", res.allocations)


if __name__ == "__main__":
    unittest.main(verbosity=2)
