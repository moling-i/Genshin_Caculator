import streamlit as st
import pandas as pd
import httpx
import numpy as np

# 设置页面配置
st.set_page_config(
    page_title="原神伤害计算器",
    page_icon="⚔️",
    layout="wide"
)

# 自定义CSS样式
st.markdown("""
<style>
    .main-header {
        color: #1E88E5;
        text-align: center;
        padding: 1rem 0;
    }
    .sub-header {
        color: #0D47A1;
        border-bottom: 2px solid #1E88E5;
        padding-bottom: 0.5rem;
        margin: 1rem 0;
    }
    .metric-card {
        background-color: #f0f8ff;
        border-radius: 10px;
        padding: 1rem;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .info-box {
        background-color: #e3f2fd;
        border-left: 5px solid #1E88E5;
        padding: 1rem;
        margin: 1rem 0;
    }
    .success-box {
        background-color: #e8f5e9;
        border-left: 5px solid #4caf50;
        padding: 1rem;
        margin: 1rem 0;
    }
    .warning-box {
        background-color: #fff3e0;
        border-left: 5px solid #ff9800;
        padding: 1rem;
        margin: 1rem 0;
    }
    .error-box {
        background-color: #ffebee;
        border-left: 5px solid #f44336;
        padding: 1rem;
        margin: 1rem 0;
    }
    .tab-style {
        font-weight: bold;
        color: #1E88E5;
    }
</style>
""", unsafe_allow_html=True)

# API基础URL
api_base_url = "http://127.0.0.1:8000"

# 页面标题
st.markdown("<h1 class='main-header'>⚔️ 原神伤害计算器</h1>", unsafe_allow_html=True)
st.markdown("---")

# API配置
with st.expander("API配置"):
    col1, col2 = st.columns(2)
    with col1:
        api_base_url = st.text_input("API基础URL", value="http://127.0.0.1:8000")
        use_local_api = st.checkbox("使用本地API", value=True)
        
        if use_local_api:
            api_base_url = "http://127.0.0.1:8000"
    
    with col2:
        # API状态检查
        try:
            with httpx.Client() as client:
                response = client.get(f"{api_base_url}/health")
                if response.status_code == 200:
                    st.success("API服务正常运行")
                else:
                    st.error(f"API服务异常: {response.status_code}")
        except Exception as e:
            st.error(f"无法连接到API服务: {e}")

# API状态检查
with st.expander("API状态检查"):
    try:
        with httpx.Client() as client:
            response = client.get(f"{api_base_url}/health")
            if response.status_code == 200:
                st.success("API服务正常运行")
                st.json(response.json())
            else:
                st.error(f"API服务异常: {response.status_code}")
    except Exception as e:
        st.error(f"无法连接到API服务: {e}")
        
# 伤害计算公式说明
with st.expander("伤害计算公式说明"):
    st.latex(r"""
    \text{伤害} = \left[ (\text{攻击力} \times \text{技能倍率}) \times (1 + \text{增伤区}) \times \text{暴击区} + \text{独立乘区} \right] \times \text{抗性区} \times \text{防御区} \times \text{反应区}
    """)
    st.markdown("""
直伤：(基础伤害区) × (爆伤区) × (增伤区) × (抗性区) × (防御区)
- 基础伤害区：(倍率*(攻击/防御/生命)) + 基础伤害加成
- 爆伤区：(1 + 爆伤) = 暴击伤害
- 抗性区：if x<0.75: return 1-x  else: return 1 / (4 * x + 1)
- 防御区：(角色等级+100)/(角色等级+100 + 怪物等级+100)
    """)


# 使用说明

st.markdown("<h2 class='sub-header'>使用说明</h2>", unsafe_allow_html=True)
st.markdown("""
<div class='info-box'>
    <ol>
        <li><strong>角色面板</strong>：在此标签页中设置角色的基础属性、额外属性和敌人属性</li>
        <li><strong>伤害计算</strong>：切换到此标签页，点击"⚔️ 计算伤害"按钮获取详细伤害结果</li>
        <li><strong>元素反应</strong>：在此标签页中分析元素精通对反应伤害的收益</li>
        <li><strong>架构说明</strong>：此版本采用前后端分离架构，前端通过API调用后端计算服务</li>
    </ol>
</div>
""", unsafe_allow_html=True)


st.markdown("---")
# 使用标签页组织界面
tab1, tab2, tab3, tab4, tab5 = st.tabs(["角色面板", "伤害计算", "元素反应", "月反应", "星反应"])

# 初始化session_state变量
if 'em' not in st.session_state:
    st.session_state.em = 100
if 'base_reaction_multiplier' not in st.session_state:
    st.session_state.base_reaction_multiplier = 1.5
if 'reaction_type' not in st.session_state:
    st.session_state.reaction_type = "amplify"

# 月反应参数默认值
if 'lunar_damage_type' not in st.session_state:
    st.session_state.lunar_damage_type = "indirect"
if 'lunar_reaction_type' not in st.session_state:
    st.session_state.lunar_reaction_type = "lunar_electro"
if 'lunar_participants_count' not in st.session_state:
    st.session_state.lunar_participants_count = 2

# 星反应参数默认值
if 'stellar_attachment_count' not in st.session_state:
    st.session_state.stellar_attachment_count = 6
if 'stellar_base_physical_res' not in st.session_state:
    st.session_state.stellar_base_physical_res = 0.1
if 'stellar_base_elemental_bonus' not in st.session_state:
    st.session_state.stellar_base_elemental_bonus = 0.3
if 'stellar_reaction_coef' not in st.session_state:
    st.session_state.stellar_reaction_coef = 1.0

# 角色面板标签页
with tab1:
    st.markdown("<h2 class='sub-header'>角色面板设置</h2>", unsafe_allow_html=True)
    
    # 创建三列布局
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("#### 基础属性")
        base_atk = st.number_input("基础攻击力", value=800, min_value=0, max_value=5000, key="base_atk", help="角色的基础攻击力")
        bonus_atk = st.number_input("额外攻击力", value=1000, min_value=0, max_value=10000, key="bonus_atk", help="装备、天赋等提供的额外攻击力")
        skill_ratio = st.number_input("技能倍率(%)", value=100.0, min_value=0.0, max_value=1000.0, step=10.0, key="skill_ratio", help="技能的基础倍率") / 100
        
        st.markdown("#### 暴击属性")
        crit_rate = st.number_input("暴击率(%)", value=50.0, min_value=0.0, max_value=100.0, key="crit_rate", help="角色的暴击率") / 100
        crit_dmg = st.number_input("暴击伤害(%)", value=100.0, min_value=0.0, max_value=500.0, key="crit_dmg", help="角色的暴击伤害") / 100
    
    with col2:
        st.markdown("#### 增伤区域")
        dmg_bonus = st.number_input("元素/物理伤害加成(%)", value=40.0, min_value=0.0, max_value=500.0, key="dmg_bonus", help="元素伤害加成或物理伤害加成") / 100
        other_bonus = st.number_input("其他增伤(%)", value=0.0, min_value=0.0, max_value=500.0, key="other_bonus", help="其他来源的伤害加成") / 100
        
        st.markdown("#### 乘区设置")
        # 移除固定的反应乘区设置，因为现在会动态计算
        independent_multiplier = st.number_input("独立乘区", value=1.0, min_value=1.0, max_value=10.0, step=0.1, key="independent_multiplier", help="其他独立乘区（如武器特效等）")
        
    with col3:
        st.markdown("#### 等级设置")
        char_level = st.number_input("角色等级", value=90.0, min_value=1.0, max_value=100.0, step=1.0, key="char_level", help="角色的当前等级")
        enemy_level = st.number_input("怪物等级", value=90.0, min_value=1.0, max_value=100.0, step=1.0, key="enemy_level", help="敌人的当前等级")
        
        st.markdown("#### 敌人属性")
        enemy_resistance = st.number_input("敌人抗性(%)", value=10.0, min_value=0.0, max_value=100.0, key="enemy_resistance", help="敌人的元素或物理抗性") / 100
        def_ignore = st.number_input("防御无视(%)", value=0.0, min_value=0.0, max_value=100.0, key="def_ignore", help="防御无视比例") / 100
        
        # 显示当前角色面板的总攻击力
        total_atk = base_atk + bonus_atk
        st.markdown("#### 面板总览")
        st.metric("总攻击力", f"{total_atk:.0f}")
        st.metric("技能倍率", f"{skill_ratio*100:.1f}%")
        st.metric("暴击期望", f"{(1 + crit_rate * crit_dmg)*100:.1f}%")

# 伤害计算标签页
with tab2:
    st.markdown("<h2 class='sub-header'>伤害计算</h2>", unsafe_allow_html=True)
    
    # 计算按钮
    if st.button("⚔️ 计算伤害", type="primary", width="stretch"):
        with st.spinner("正在计算伤害..."):
            # 获取元素反应参数
            em = st.session_state.get('em', 100)
            base_reaction_multiplier = st.session_state.get('base_reaction_multiplier', 1.5)
            
            # 先计算反应乘区
            reaction_req = {
                "em": em,
                "base_reaction_multiplier": base_reaction_multiplier,
                "reaction_type": st.session_state.get('reaction_type', 'amplify')
            }
            
            try:
                with httpx.Client() as client:
                    reaction_response = client.post(f"{api_base_url}/calculate_reaction", json=reaction_req)
                    reaction_response.raise_for_status()
                    reaction_result = reaction_response.json()
                    calculated_reaction_multiplier = reaction_result["total_reaction_multiplier"]
            except Exception as e:
                st.error(f"计算反应乘区时出错: {e}")
                calculated_reaction_multiplier = 1.0  # 出错时使用默认值
            
            # 准备伤害计算请求数据
            damage_data = {
                "base_atk": base_atk,
                "bonus_atk": bonus_atk,
                "skill_ratio": skill_ratio,
                "dmg_bonus": dmg_bonus,
                "other_bonus": other_bonus,
                "crit_rate": crit_rate,
                "crit_dmg": crit_dmg,
                "reaction_multiplier": calculated_reaction_multiplier,
                "independent_multiplier": independent_multiplier,
                "enemy_resistance": enemy_resistance,
                "def_ignore": def_ignore,
                "char_level": char_level,
                "enemy_level": enemy_level
            }
            
            try:
                # 发送请求到后端API
                with httpx.Client() as client:
                    response = client.post(f"{api_base_url}/calculate_damage", json=damage_data)
                    response.raise_for_status()
                    result = response.json()
                
                # 显示计算结果
                st.markdown("### 📊 计算结果")
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown("#### 伤害乘区")
                    # 使用卡片样式显示主要属性
                    st.markdown("<div class='metric-card'>", unsafe_allow_html=True)
                    st.metric("总攻击力", f"{result['total_atk']:.0f}")
                    st.metric("技能倍率", f"{skill_ratio*100:.1f}%")
                    st.metric("总增伤", f"{(result['total_bonus']-1)*100:.1f}%")
                    st.metric("暴击乘区", f"{result['crit_multiplier']:.2f}")
                    st.metric("反应乘区", f"{calculated_reaction_multiplier:.2f}")
                    st.markdown("</div>", unsafe_allow_html=True)
                    
                    # 显示敌人属性
                    st.markdown("#### 敌人属性")
                    st.markdown("<div class='metric-card'>", unsafe_allow_html=True)
                    st.metric("抗性乘区", f"{result['res_multiplier']:.2f}")
                    st.metric("防御乘区", f"{result['def_multiplier']:.2f}")
                    st.markdown("</div>", unsafe_allow_html=True)
                
                with col2:
                    st.markdown("#### 伤害流程")
                    # 创建伤害结果的DataFrame
                    damage_results = {
                        "基础伤害": result["base_damage"],
                        "增伤后": result["damage_with_bonus"],
                        "暴击后": result["damage_with_crit"],
                        "最终伤害": result["final_damage"]
                    }
                    
                    damage_df = pd.DataFrame({
                        "伤害阶段": list(damage_results.keys()),
                        "伤害值": list(damage_results.values())
                    })
                    st.dataframe(damage_df.style.format({"伤害值": "{:.0f}"}), width="stretch", height=200)
                    
                    # 显示最终伤害
                    st.markdown("---")
                    st.markdown("#### 最终伤害")
                    st.metric("最终伤害值", f"{result['final_damage']:.0f}")
                    
                    # 伤害构成饼图
                    st.markdown("#### 伤害构成分析")
                    damage_components = {
                        "基础攻击力": base_atk * skill_ratio,
                        "额外攻击力": bonus_atk * skill_ratio,
                        "增伤加成": result["damage_with_bonus"] - result["base_damage"],
                        "暴击增益": result["damage_with_crit"] - result["damage_with_bonus"],
                        "反应增伤": result["final_damage"] / result["damage_with_crit"] if result["damage_with_crit"] > 0 else 0,
                        "其他乘区": result["final_damage"] / (result["damage_with_crit"] * calculated_reaction_multiplier) if result["damage_with_crit"] > 0 and calculated_reaction_multiplier > 0 else 0
                    }
                    
                    # 创建饼图数据
                    components_df = pd.DataFrame({
                        "构成": list(damage_components.keys()),
                        "数值": list(damage_components.values())
                    })
                    components_df = components_df[components_df["数值"] > 0]  # 过滤掉0值
                    
                    # 显示饼图
                    if not components_df.empty:
                        st.bar_chart(components_df.set_index("构成"))
                    else:
                        st.info("暂无构成数据")
                        
            except httpx.RequestError as e:
                st.error(f"请求API时出错: {e}")
            except httpx.HTTPStatusError as e:
                st.error(f"API返回错误: {e.response.status_code} - {e.response.text}")
            except Exception as e:
                st.error(f"发生未知错误: {e}")

# 元素反应标签页
with tab3:
    st.markdown("<h2 class='sub-header'>元素反应计算器</h2>", unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### 反应参数设置")
        em = st.number_input("元素精通", value=st.session_state.get('em', 100), min_value=0, max_value=2000, key="em_input", help="角色的元素精通属性")
        base_reaction_multiplier = st.number_input("基础反应倍率", value=st.session_state.get('base_reaction_multiplier', 1.5), min_value=0.0, max_value=10.0, step=0.1, key="base_reaction_multiplier_input", help="基础元素反应倍率（如蒸发1.5、融化2.0、超载2.0等）")
        reaction_type_label = st.selectbox(
            "反应类型",
            options=["amplify", "transformative"],
            format_func=lambda x: "增幅反应（蒸发/融化）" if x == "amplify" else "剧变反应（超载/感电/激化等）",
            key="reaction_type_input",
            help="增幅反应使用经典公式；剧变反应使用3.3版本统一公式"
        )
        
        # 更新session_state
        st.session_state.em = em
        st.session_state.base_reaction_multiplier = base_reaction_multiplier
        st.session_state.reaction_type = reaction_type_label
        
        if st.button("🧮 计算反应增伤", type="primary", width="stretch"):
            with st.spinner("正在计算反应增伤..."):
                # 准备请求数据
                reaction_data = {
                    "em": em,
                    "base_reaction_multiplier": base_reaction_multiplier,
                    "reaction_type": st.session_state.get("reaction_type", "amplify")
                }
                
                try:
                    # 发送请求到后端API
                    with httpx.Client() as client:
                        response = client.post(f"{api_base_url}/calculate_reaction", json=reaction_data)
                        response.raise_for_status()
                        result = response.json()
                    
                    # 显示结果
                    st.markdown("#### 计算结果")
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown("<div class='metric-card'>", unsafe_allow_html=True)
                        st.metric("反应增伤系数", f"{result['reaction_bonus']*100:.2f}%")
                        st.metric("总反应乘区", f"{result['total_reaction_multiplier']:.2f}")
                        st.markdown("</div>", unsafe_allow_html=True)
                    
                except httpx.RequestError as e:
                    st.error(f"请求API时出错: {e}")
                except httpx.HTTPStatusError as e:
                    st.error(f"API返回错误: {e.response.status_code} - {e.response.text}")
                except Exception as e:
                    st.error(f"发生未知错误: {e}")
        
        # 即使没有点击按钮，也显示元素精通收益图
        st.markdown("#### 元素精通收益")
        # 创建元素精通收益数据
        em_values = np.arange(0, 1500, 50)
        reaction_bonuses = []
        
        for em_val in em_values:
            reaction_req = {
                "em": em_val,
                "base_reaction_multiplier": base_reaction_multiplier,
                "reaction_type": st.session_state.get("reaction_type", "amplify")
            }
            try:
                with httpx.Client() as client:
                    resp = client.post(f"{api_base_url}/calculate_reaction", json=reaction_req)
                    resp.raise_for_status()
                    reaction_result = resp.json()
                    reaction_bonuses.append(reaction_result["reaction_bonus"])
            except:
                # 如果API调用失败，使用本地计算公式（根据反应类型选择）
                if st.session_state.get("reaction_type", "amplify") == "transformative":
                    reaction_bonus = 25 * em_val / (12 * em_val + 8400) if em_val > 0 else 0
                else:
                    reaction_bonus = 2.78 * em_val / (em_val + 1400) if em_val > 0 else 0
                reaction_bonuses.append(reaction_bonus)
        
        em_df = pd.DataFrame({
            "元素精通": em_values,
            "反应增伤": reaction_bonuses
        })
        
        st.line_chart(em_df.set_index("元素精通"))
                        
        with col2:
            st.markdown("#### 元素精通收益分析")
            st.info(
                "**增幅反应**（蒸发/融化）：2.78 × EM ÷ (EM + 1400)\n\n"
                "**剧变反应**（超载/感电/超导/碎冰/绽放/激化）：25 × EM ÷ (12 × EM + 8400)"
            )
            st.markdown("""
            **元素精通收益特点**：
            - 收益递减：随着元素精通提升，每点元素精通带来的收益逐渐降低
            - 初期收益高：在较低元素精通时，提升效果明显
            - 后期收益低：在高元素精通时，提升效果不明显
            """)
            
            # 显示当前元素精正的收益
            if em > 0:
                if st.session_state.get("reaction_type", "amplify") == "transformative":
                    reaction_bonus_current = 25 * em / (12 * em + 8400)
                else:
                    reaction_bonus_current = 2.78 * em / (em + 1400)
                st.markdown(f"**当前元素精通收益**：{reaction_bonus_current*100:.2f}%")
                
                # 显示与常见阈值的对比
                thresholds = [100, 200, 400, 800, 1200]
                st.markdown("**常见元素精通阈值收益对比**：")
                threshold_data = []
                for threshold in thresholds:
                    if st.session_state.get("reaction_type", "amplify") == "transformative":
                        bonus = 25 * threshold / (12 * threshold + 8400)
                    else:
                        bonus = 2.78 * threshold / (threshold + 1400)
                    threshold_data.append({"元素精通": threshold, "反应增伤": f"{bonus*100:.2f}%"})
                
                threshold_df = pd.DataFrame(threshold_data)
                st.dataframe(threshold_df, width="stretch")

# 月反应标签页
with tab4:
    st.markdown("<h2 class='sub-header'>月反应 (Lunar Reactions)</h2>", unsafe_allow_html=True)
    st.markdown("""
    <div class='info-box'>
        <strong>月反应特性</strong>：月反应伤害可以暴击。<br>
        <strong>间接伤害</strong>：由元素反应触发，多角色参与时按权重合并（最高×1，第二×1/2，第三、四×1/12）。<br>
        <strong>直接伤害</strong>：由特定技能造成，基于角色属性（攻击/生命/防御等）。
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns([1, 1])

    with col1:
        st.markdown("#### 参数设置")
        damage_type = st.selectbox(
            "伤害类型",
            options=["indirect", "direct"],
            format_func=lambda x: "间接伤害（元素反应触发）" if x == "indirect" else "直接伤害（角色技能）",
            key="lunar_damage_type_input",
        )
        reaction_type = st.selectbox(
            "月反应类型",
            options=["lunar_electro", "lunar_crystallize", "lunar_bloom"],
            format_func=lambda x: {
                "lunar_electro": "月感电（间接系数1.8 / 直接系数3.0）",
                "lunar_crystallize": "月结晶（间接系数0.96 / 直接系数1.6）",
                "lunar_bloom": "月绽放（间接无伤害 / 直接系数1.0）",
            }[x],
            key="lunar_reaction_type_input",
        )
        st.session_state.lunar_damage_type = damage_type
        st.session_state.lunar_reaction_type = reaction_type

        if damage_type == "indirect":
            participants_count = st.number_input(
                "参与角色数量", value=st.session_state.lunar_participants_count,
                min_value=1, max_value=8, step=1, key="lunar_participants_count_input"
            )
            st.session_state.lunar_participants_count = int(participants_count)

            st.markdown("#### 参与角色面板")
            participant_params = []
            for i in range(int(participants_count)):
                st.markdown(f"**角色 {i+1}**")
                p_col1, p_col2 = st.columns(2)
                with p_col1:
                    char_lv = st.number_input(f"等级", value=90.0, min_value=1.0, max_value=100.0,
                                              step=1.0, key=f"lunar_p_char_lv_{i}")
                    em = st.number_input(f"元素精通", value=100.0, min_value=0.0, max_value=2000.0,
                                         key=f"lunar_p_em_{i}")
                    lunar_bonus = st.number_input(f"月反应基础伤害加成(%)", value=10.0, min_value=0.0,
                                                  max_value=500.0, key=f"lunar_p_bonus_{i}") / 100
                with p_col2:
                    res = st.number_input(f"敌人抗性(%)", value=10.0, min_value=-100.0, max_value=100.0,
                                          key=f"lunar_p_res_{i}") / 100
                    crit_rate = st.number_input(f"暴击率(%)", value=50.0, min_value=0.0, max_value=100.0,
                                                key=f"lunar_p_cr_{i}") / 100
                    crit_dmg = st.number_input(f"暴击伤害(%)", value=100.0, min_value=0.0, max_value=500.0,
                                               key=f"lunar_p_cd_{i}") / 100
                participant_params.append({
                    "char_level": char_lv,
                    "em": em,
                    "lunar_dmg_bonus": lunar_bonus,
                    "reaction_dmg_bonus": 0.0,
                    "enemy_resistance": res,
                    "crit_rate": crit_rate,
                    "crit_dmg": crit_dmg,
                    "is_crit": True,
                })
        else:
            st.markdown("#### 直接伤害参数")
            attr_value = st.number_input("属性值（攻击/生命/防御等）", value=1800.0, min_value=0.0,
                                         key="lunar_d_attr")
            skill_ratio = st.number_input("技能倍率(%)", value=150.0, min_value=0.0, max_value=1000.0,
                                          key="lunar_d_ratio") / 100
            em = st.number_input("元素精通", value=200.0, min_value=0.0, max_value=2000.0,
                                 key="lunar_d_em")
            lunar_bonus = st.number_input("月反应基础伤害加成(%)", value=20.0, min_value=0.0,
                                          max_value=500.0, key="lunar_d_bonus") / 100
            flat_bonus = st.number_input("固定加成 (flat_bonus)", value=500.0, min_value=0.0,
                                         key="lunar_d_flat")
            res = st.number_input("敌人抗性(%)", value=10.0, min_value=-100.0, max_value=100.0,
                                  key="lunar_d_res") / 100
            crit_rate = st.number_input("暴击率(%)", value=50.0, min_value=0.0, max_value=100.0,
                                        key="lunar_d_cr") / 100
            crit_dmg = st.number_input("暴击伤害(%)", value=120.0, min_value=0.0, max_value=500.0,
                                       key="lunar_d_cd") / 100

        if st.button("🌙 计算月反应伤害", type="primary", width="stretch", key="lunar_calc_btn"):
            with st.spinner("正在计算月反应伤害..."):
                if damage_type == "indirect":
                    lunar_data = {
                        "damage_type": "indirect",
                        "reaction_type": reaction_type,
                        "participants": participant_params,
                    }
                else:
                    lunar_data = {
                        "damage_type": "direct",
                        "reaction_type": reaction_type,
                        "attribute_value": attr_value,
                        "skill_ratio": skill_ratio,
                        "em": em,
                        "lunar_dmg_bonus": lunar_bonus,
                        "reaction_dmg_bonus": 0.0,
                        "flat_bonus": flat_bonus,
                        "enemy_resistance": res,
                        "crit_rate": crit_rate,
                        "crit_dmg": crit_dmg,
                        "is_crit": True,
                    }

                try:
                    with httpx.Client() as client:
                        response = client.post(f"{api_base_url}/calculate_lunar", json=lunar_data)
                        response.raise_for_status()
                        result = response.json()

                    st.markdown("#### 计算结果")
                    st.markdown("<div class='metric-card'>", unsafe_allow_html=True)
                    st.metric("最终伤害", f"{result['final_damage']:.0f}")
                    st.metric("反应系数", f"{result['reaction_coef']:.2f}")
                    st.metric("精通增益", f"{result['em_bonus']*100:.2f}%")
                    st.markdown("</div>", unsafe_allow_html=True)

                    st.markdown(f"**公式**：{result['formula']}")

                    # 间接伤害显示参与者明细
                    if result.get('detail', {}).get('individual_damages'):
                        st.markdown("#### 参与者伤害明细")
                        detail = result['detail']
                        participant_df = pd.DataFrame([
                            {
                                "角色": f"角色{i+1}",
                                "等级": d["char_level"],
                                "元素精通": d["em"],
                                "月加成": f"{d['lunar_dmg_bonus']*100:.1f}%",
                                "个人伤害": d["damage"],
                                "权重": detail["weights"][i] if i < len(detail["weights"]) else 0,
                                "贡献": detail["contributions"][i] if i < len(detail["contributions"]) else 0,
                            }
                            for i, d in enumerate(detail["individual_damages"][:4])
                        ])
                        st.dataframe(
                            participant_df.style.format({
                                "个人伤害": "{:.0f}",
                                "贡献": "{:.0f}"
                            }),
                            width="stretch", height=200
                        )
                except httpx.RequestError as e:
                    st.error(f"请求API时出错: {e}")
                except httpx.HTTPStatusError as e:
                    st.error(f"API返回错误: {e.response.status_code} - {e.response.text}")
                except Exception as e:
                    st.error(f"发生未知错误: {e}")

    with col2:
        st.markdown("#### 月反应公式说明")
        st.info(
            "**间接伤害**\n\n"
            "个人伤害 = 反应系数 × 等级系数 × (1+lunar_dmg_bonus) × (1+EM增益+反应增伤) × 抗性区 × 暴击区\n\n"
            "加权求和：最高×1 + 第二×1/2 + 第三×1/12 + 第四×1/12\n\n"
            "**直接伤害**\n\n"
            "直接伤害 = (反应系数 × 属性 × 倍率 × (1+lunar_dmg_bonus) × (1+EM增益+反应增伤) + flat_bonus) × 抗性区 × 暴击区"
        )
        st.markdown("""
        **月反应系数表**：
        | 反应 | 间接系数 | 直接系数 |
        |------|---------|---------|
        | 月感电 | 1.8 | 3.0 |
        | 月结晶 | 0.96 | 1.6 |
        | 月绽放 | 0（无伤害） | 1.0 |
        """)
        st.markdown("""
        **精通公式（月反应）**：`16 × EM ÷ (EM + 2000)`（暂用剧变公式，可配置）
        """)

# 星反应标签页
with tab5:
    st.markdown("<h2 class='sub-header'>星反应 (Stellar Reactions)</h2>", unsafe_allow_html=True)
    st.markdown("""
    <div class='info-box'>
        <strong>星超导</strong>：冰+雷触发，生成「极星辉域」领域。<br>
        降低领域内敌人 40% 物理抗性；根据冰/雷附着次数（累计，上限12次）提供额外加成：
        ≥6次：约34%雷/冰元素伤害加成 + 1.7反应系数；≥12次：约40% + 2.0反应系数。
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns([1, 1])

    with col1:
        st.markdown("#### 参数设置")
        attachment_count = st.slider(
            "冰/雷附着次数（累计，上限12）",
            min_value=0, max_value=12, value=st.session_state.stellar_attachment_count,
            step=1, key="stellar_attachment_count_input",
            help="领域内冰/雷元素附着累计次数"
        )
        st.session_state.stellar_attachment_count = attachment_count

        base_physical_res = st.number_input(
            "敌人基础物理抗性(%)", value=st.session_state.stellar_base_physical_res * 100,
            min_value=-100.0, max_value=100.0, step=5.0, key="stellar_base_physical_res_input"
        ) / 100
        st.session_state.stellar_base_physical_res = base_physical_res

        base_elemental_bonus = st.number_input(
            "当前雷/冰元素伤害加成(%)", value=st.session_state.stellar_base_elemental_bonus * 100,
            min_value=0.0, max_value=500.0, step=5.0, key="stellar_base_elemental_bonus_input"
        ) / 100
        st.session_state.stellar_base_elemental_bonus = base_elemental_bonus

        reaction_coef = st.number_input(
            "当前反应系数", value=st.session_state.stellar_reaction_coef,
            min_value=0.0, max_value=10.0, step=0.1, key="stellar_reaction_coef_input",
            help="用于计算最终反应系数（影响后续雷/冰反应伤害）"
        )
        st.session_state.stellar_reaction_coef = reaction_coef

        if st.button("⭐ 计算星超导加成", type="primary", width="stretch", key="stellar_calc_btn"):
            with st.spinner("正在计算星超导加成..."):
                stellar_data = {
                    "attachment_count": attachment_count,
                    "base_physical_res": base_physical_res,
                    "base_elemental_dmg_bonus": base_elemental_bonus,
                    "reaction_coef": reaction_coef,
                }
                try:
                    with httpx.Client() as client:
                        response = client.post(f"{api_base_url}/calculate_stellar", json=stellar_data)
                        response.raise_for_status()
                        result = response.json()

                    st.markdown("#### 计算结果")
                    st.markdown("<div class='metric-card'>", unsafe_allow_html=True)
                    st.metric("加成阶段", {
                        "none": "未激活",
                        "medium": "中层（≥6次）",
                        "max": "满层（≥12次）",
                    }[result["tier"]])
                    st.metric("物理减抗", f"{result['physical_res_reduction']*100:.0f}%")
                    st.metric("最终物理抗性", f"{result['final_physical_res']*100:.1f}%")
                    st.metric("额外雷/冰增伤", f"{result['elemental_dmg_bonus']*100:.1f}%")
                    st.metric("最终反应系数", f"{result['final_reaction_coef']:.2f}")
                    st.markdown("</div>", unsafe_allow_html=True)

                    st.info(result["note"])
                except httpx.RequestError as e:
                    st.error(f"请求API时出错: {e}")
                except httpx.HTTPStatusError as e:
                    st.error(f"API返回错误: {e.response.status_code} - {e.response.text}")
                except Exception as e:
                    st.error(f"发生未知错误: {e}")

    with col2:
        st.markdown("#### 星超导机制说明")
        st.markdown("""
        **触发条件**：冰 + 雷元素反应
                        
        **领域效果**：
        - 降低领域内敌人 **40% 物理抗性**
        - 根据领域内冰/雷元素附着次数（累计，上限12次）提供额外加成

        **附着次数加成表**：
        | 附着次数 | 雷/冰元素伤害加成 | 反应系数 |
        |---------|-----------------|---------|
        | <6 | 无 | 1.0 |
        | 6 | ~34% | 1.7 |
        | 12 | ~40% | 2.0 |
        """)

        # 显示当前状态的加成预览
        buff_table = {6: (0.34, 1.7), 12: (0.40, 2.0)}
        preview_bonus, preview_coef = 0.0, 1.0
        for threshold in [6, 12]:
            if attachment_count >= threshold:
                preview_bonus, preview_coef = buff_table[threshold]

        st.markdown("#### 当前状态预览")
        st.markdown(
            f"附着次数：**{attachment_count}** / 12\n\n"
            f"额外雷/冰增伤：**{preview_bonus*100:.1f}%**\n\n"
            f"反应系数：**{preview_coef:.1f}**\n\n"
            f"当前物理抗性：**{(base_physical_res - 0.40)*100:.1f}%**（已减40%）"
        )

        # 附着次数收益图
        st.markdown("#### 附着次数 → 加成预览")
        attach_range = list(range(0, 13))
        bonus_values = []
        for count in attach_range:
            b, _ = 0.0, 1.0
            for threshold in [6, 12]:
                if count >= threshold:
                    b, _ = buff_table[threshold]
            bonus_values.append(b * 100)

        stellar_df = pd.DataFrame({
            "附着次数": attach_range,
            "额外增伤(%)": bonus_values,
        })
        st.line_chart(stellar_df.set_index("附着次数"))


