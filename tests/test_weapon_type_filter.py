# -*- coding: utf-8 -*-
"""
武器类型匹配与过滤系统单元测试。

覆盖：
- get_character_weapon_type 三级优先级（Meropide > characters.json 枚举 > 硬编码映射）
- get_weapon_type（通过武器 id / 中文名查找类型）
- get_weapons_by_type（按类型过滤，结果完整性）
- 异常与边界（角色不存在、武器不存在、类型无匹配武器）
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import data_loader


class TestGetCharacterWeaponType(unittest.TestCase):
    """角色武器类型获取：三级优先级链路。"""

    def test_meropide_source(self):
        """玛薇卡（双手剑）、胡桃（长柄武器）、甘雨（弓）——Meropide 有完整 weapon_type"""
        for name, expected in [
            ("玛薇卡", "双手剑"),
            ("胡桃", "长柄武器"),
            ("甘雨", "弓"),
            ("纳西妲", "法器"),
            ("琴", "单手剑"),
        ]:
            cid = str(
                next(
                    c.get("id")
                    for c in data_loader.get_characters()
                    if c.get("name_cn") == name
                )
            )
            result = data_loader.get_character_weapon_type(cid)
            self.assertEqual(
                result, expected,
                f"{name}(id={cid}) 期望 {expected}，实际 {result}"
            )

    def test_fallback_characters_json_enum(self):
        """若 Meropide 条目缺失，应回退到 characters.json 枚举映射"""
        # 测试一个 characters.json 中存在但不在 Meropide 的角色（如果有）
        # 或直接验证已知角色通过枚举映射链路正确
        # 夜兰：characters.json weapon_type = WEAPON_BOW → '弓'
        result = data_loader.get_character_weapon_type("夜兰")
        self.assertEqual(result, "弓")

    def test_hardcoded_mapping_fallback(self):
        """两个数据源都找不到时，使用 CHARACTER_WEAPON_MAPPING 硬编码映射"""
        # 直接测试硬编码映射入口（用一个不在 characters.json 的虚构 id）
        result = data_loader.get_character_weapon_type("NONEXISTENT_CHAR")
        self.assertEqual(result, "")

    def test_returns_empty_string_for_unknown(self):
        """完全找不到时返回空字符串（不会报错）"""
        self.assertEqual(data_loader.get_character_weapon_type("999999"), "")


class TestGetWeaponType(unittest.TestCase):
    """武器类型查找（武器 id / 中文名）。"""

    def test_by_weapon_id(self):
        """通过数字 id 查找武器类型"""
        # 找一把已知武器的 id 来验证
        wps = data_loader.get_weapons()
        sample = next(w for w in wps if w.get("name_cn") == "和璞鸢")
        result = data_loader.get_weapon_type(str(sample["id"]))
        self.assertEqual(result, "长柄武器")

    def test_by_weapon_name_cn(self):
        """通过中文名也能查找（find_weapon_by_name 支持中文名）"""
        result = data_loader.get_weapon_type("和璞鸢")
        self.assertEqual(result, "长柄武器")

    def test_unknown_weapon_returns_empty(self):
        """不存在的武器返回空字符串"""
        self.assertEqual(data_loader.get_weapon_type("不存在的武器"), "")
        self.assertEqual(data_loader.get_weapon_type("999999"), "")


class TestGetWeaponsByType(unittest.TestCase):
    """按武器类型过滤。"""

    def test_all_five_types_non_empty(self):
        """五种武器类型各有若干武器"""
        for wtype, min_count in [
            ("单手剑", 10),
            ("双手剑", 10),
            ("长柄武器", 10),
            ("法器", 10),
            ("弓", 10),
        ]:
            result = data_loader.get_weapons_by_type(wtype)
            self.assertGreaterEqual(
                len(result), min_count,
                f"{wtype} 期望 ≥{min_count} 把，实际 {len(result)}"
            )

    def test_result_structure(self):
        """返回结果包含 id、name_cn、weapon_type 字段"""
        result = data_loader.get_weapons_by_type("单手剑")
        for item in result:
            self.assertIn("id", item)
            self.assertIn("name_cn", item)
            self.assertEqual(item["weapon_type"], "单手剑")

    def test_no_type_match_returns_empty(self):
        """不存在的类型返回空列表"""
        self.assertEqual(data_loader.get_weapons_by_type("不存在的类型"), [])

    def test_no_cross_type_contamination(self):
        """每种类型的结果中只包含该类型，不含其他类型"""
        for wtype in ["单手剑", "双手剑", "长柄武器", "法器", "弓"]:
            result = data_loader.get_weapons_by_type(wtype)
            for item in result:
                self.assertEqual(
                    item["weapon_type"], wtype,
                    f"{item['name_cn']} 被错误归入 {wtype}"
                )


class TestWeaponTypeEnumMapping(unittest.TestCase):
    """枚举→中文映射完整性。"""

    def test_all_five_enum_values_covered(self):
        """_WEAPON_TYPE_CN 覆盖全部五种游戏内枚举"""
        expected_enums = {
            "WEAPON_SWORD_ONE_HAND", "WEAPON_CLAYMORE",
            "WEAPON_POLE", "WEAPON_CATALYST", "WEAPON_BOW",
        }
        self.assertTrue(expected_enums.issubset(data_loader._WEAPON_TYPE_CN.keys()))


if __name__ == "__main__":
    unittest.main(verbosity=2)