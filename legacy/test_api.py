import requests
import json
import traceback

BASE_URL = "http://127.0.0.1:8000"


def test_calculate_reaction():
    """测试元素反应乘区计算接口（原有兼容）"""
    print("\n=== 测试 /calculate_reaction（反应乘区） ===")
    # 增幅反应
    reaction_data = {
        "em": 100,
        "base_reaction_multiplier": 1.5
    }
    response = requests.post(f"{BASE_URL}/calculate_reaction", json=reaction_data)
    print("状态码:", response.status_code)
    print("响应内容:", response.json())

    # 剧变反应
    reaction_data = {
        "em": 100,
        "base_reaction_multiplier": 2.0,
        "reaction_type": "transformative"
    }
    response = requests.post(f"{BASE_URL}/calculate_reaction", json=reaction_data)
    print("剧变反应状态码:", response.status_code)
    print("剧变响应内容:", response.json())


def test_calculate_damage():
    """测试直伤计算接口（原有兼容）"""
    print("\n=== 测试 /calculate_damage（直伤） ===")
    damage_data = {
        "base_atk": 800,
        "bonus_atk": 1000,
        "skill_ratio": 1.0,
        "dmg_bonus": 0.4,
        "other_bonus": 0.0,
        "crit_rate": 0.5,
        "crit_dmg": 1.0,
        "reaction_multiplier": 1.5,
        "independent_multiplier": 1.0,
        "enemy_resistance": 0.1,
        "def_ignore": 0.0,
        "char_level": 90,
        "enemy_level": 90
    }
    response = requests.post(f"{BASE_URL}/calculate_damage", json=damage_data)
    print("状态码:", response.status_code)
    print("响应内容:", response.json())


def test_reaction_damage():
    """测试完整反应伤害计算接口"""
    print("\n=== 测试 /calculate_reaction_damage（完整反应伤害） ===")

    # 1. 增幅反应（蒸发）
    data = {
        "reaction_type": "amplify",
        "em": 200,
        "enemy_resistance": 0.1,
        "char_level": 90,
        "enemy_level": 90,
        "atk": 2000,
        "talent_ratio": 2.0,
        "reaction_coef": 1.5,
        "elemental_dmg_bonus": 0.4,
        "other_dmg_bonus": 0.0,
        "crit_rate": 0.5,
        "crit_dmg": 1.0,
        "is_crit": True
    }
    response = requests.post(f"{BASE_URL}/calculate_reaction_damage", json=data)
    print("增幅反应 状态码:", response.status_code)
    print("增幅反应 响应:", json.dumps(response.json(), ensure_ascii=False, indent=2))

    # 2. 剧变反应（超载）
    data = {
        "reaction_type": "transformative",
        "em": 300,
        "enemy_resistance": 0.1,
        "char_level": 90
    }
    response = requests.post(f"{BASE_URL}/calculate_reaction_damage", json=data)
    print("剧变反应 状态码:", response.status_code)
    print("剧变反应 响应:", json.dumps(response.json(), ensure_ascii=False, indent=2))

    # 3. 激化反应（超激化/蔓激化 flat_bonus）
    data = {
        "reaction_type": "aggravate",
        "em": 300,
        "char_level": 90
    }
    response = requests.post(f"{BASE_URL}/calculate_reaction_damage", json=data)
    print("激化反应 状态码:", response.status_code)
    print("激化反应 响应:", json.dumps(response.json(), ensure_ascii=False, indent=2))

    # 4. 结晶反应
    data = {
        "reaction_type": "crystallize"
    }
    response = requests.post(f"{BASE_URL}/calculate_reaction_damage", json=data)
    print("结晶反应 状态码:", response.status_code)
    print("结晶反应 响应:", json.dumps(response.json(), ensure_ascii=False, indent=2))


def test_lunar():
    """测试月反应计算接口"""
    print("\n=== 测试 /calculate_lunar（月反应） ===")

    # 1. 月感电 - 间接伤害（多角色加权求和）
    data = {
        "damage_type": "indirect",
        "reaction_type": "lunar_electro",
        "participants": [
            {
                "char_level": 90,
                "em": 100,
                "lunar_dmg_bonus": 0.1,
                "reaction_dmg_bonus": 0.0,
                "enemy_resistance": 0.1,
                "crit_rate": 0.5,
                "crit_dmg": 1.0,
                "is_crit": True
            },
            {
                "char_level": 90,
                "em": 200,
                "lunar_dmg_bonus": 0.15,
                "reaction_dmg_bonus": 0.1,
                "enemy_resistance": 0.1,
                "crit_rate": 0.3,
                "crit_dmg": 0.8,
                "is_crit": False
            },
            {
                "char_level": 85,
                "em": 50,
                "lunar_dmg_bonus": 0.0,
                "reaction_dmg_bonus": 0.0,
                "enemy_resistance": 0.1,
                "crit_rate": 0.0,
                "crit_dmg": 0.0,
                "is_crit": False
            },
            {
                "char_level": 80,
                "em": 0,
                "lunar_dmg_bonus": 0.0,
                "reaction_dmg_bonus": 0.0,
                "enemy_resistance": 0.1,
                "crit_rate": 0.0,
                "crit_dmg": 0.0,
                "is_crit": False
            }
        ]
    }
    response = requests.post(f"{BASE_URL}/calculate_lunar", json=data)
    print("月感电间接 状态码:", response.status_code)
    print("月感电间接 响应:", json.dumps(response.json(), ensure_ascii=False, indent=2))

    # 2. 月绽放 - 间接伤害（系数为0）
    data = {
        "damage_type": "indirect",
        "reaction_type": "lunar_bloom",
        "participants": [
            {"char_level": 90, "em": 100, "lunar_dmg_bonus": 0.1}
        ]
    }
    response = requests.post(f"{BASE_URL}/calculate_lunar", json=data)
    print("月绽放间接 状态码:", response.status_code)
    print("月绽放间接 响应:", json.dumps(response.json(), ensure_ascii=False, indent=2))

    # 3. 月感电 - 直接伤害
    data = {
        "damage_type": "direct",
        "reaction_type": "lunar_electro",
        "attribute_value": 1800,
        "skill_ratio": 1.5,
        "em": 200,
        "lunar_dmg_bonus": 0.2,
        "reaction_dmg_bonus": 0.1,
        "flat_bonus": 500,
        "enemy_resistance": 0.1,
        "crit_rate": 0.5,
        "crit_dmg": 1.2,
        "is_crit": True
    }
    response = requests.post(f"{BASE_URL}/calculate_lunar", json=data)
    print("月感电直接 状态码:", response.status_code)
    print("月感电直接 响应:", json.dumps(response.json(), ensure_ascii=False, indent=2))


def test_stellar():
    """测试星反应计算接口"""
    print("\n=== 测试 /calculate_stellar（星超导） ===")

    # 1. 无加成（附着次数不足）
    data = {
        "attachment_count": 3,
        "base_physical_res": 0.1,
        "base_elemental_dmg_bonus": 0.3,
        "reaction_coef": 1.0
    }
    response = requests.post(f"{BASE_URL}/calculate_stellar", json=data)
    print("星超导(未激活) 状态码:", response.status_code)
    print("星超导(未激活) 响应:", json.dumps(response.json(), ensure_ascii=False, indent=2))

    # 2. 中层加成（6次附着）
    data = {
        "attachment_count": 6,
        "base_physical_res": 0.1,
        "base_elemental_dmg_bonus": 0.3,
        "reaction_coef": 1.0
    }
    response = requests.post(f"{BASE_URL}/calculate_stellar", json=data)
    print("星超导(6次) 状态码:", response.status_code)
    print("星超导(6次) 响应:", json.dumps(response.json(), ensure_ascii=False, indent=2))

    # 3. 满层加成（12次附着）
    data = {
        "attachment_count": 12,
        "base_physical_res": 0.1,
        "base_elemental_dmg_bonus": 0.3,
        "reaction_coef": 1.0
    }
    response = requests.post(f"{BASE_URL}/calculate_stellar", json=data)
    print("星超导(12次) 状态码:", response.status_code)
    print("星超导(12次) 响应:", json.dumps(response.json(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        test_calculate_reaction()
        test_calculate_damage()
        test_reaction_damage()
        test_lunar()
        test_stellar()
        print("\n✅ 所有测试完成！")
    except Exception as e:
        print(f"\n❌ 测试出错: {e}")
        traceback.print_exc()