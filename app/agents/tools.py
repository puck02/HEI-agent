"""
Agent Tools — Tool definitions for ReAct agents.

Each sub-agent has access to specific tools based on its domain.
Tools are implemented as LangChain @tool decorated functions.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

import structlog
from langchain_core.tools import tool

log = structlog.get_logger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# Health Tools — For Health Advisor Agent
# ══════════════════════════════════════════════════════════════════════════════


@tool
def query_health_data(
    user_id: str,
    data_type: str,
    days: int = 7,
) -> str:
    """查询用户健康数据。

    Args:
        user_id: 用户ID
        data_type: 数据类型，可选值: blood_pressure（血压）, blood_sugar（血糖）,
                   sleep（睡眠）, weight（体重）, heart_rate（心率）, mood（情绪）
        days: 查询最近几天的数据，默认7天

    Returns:
        用户健康数据摘要
    """
    # TODO: 实际实现需要从数据库查询
    log.info("tool_query_health_data", user_id=user_id, data_type=data_type, days=days)

    # Mock data for demonstration
    mock_data = {
        "blood_pressure": f"最近{days}天血压数据: 平均 128/82 mmHg，略高于正常范围",
        "blood_sugar": f"最近{days}天血糖数据: 空腹平均 5.8 mmol/L，在正常范围内",
        "sleep": f"最近{days}天睡眠数据: 平均睡眠 6.5 小时，深睡比例 18%，略低",
        "weight": f"最近{days}天体重数据: 平均 72.5 kg，较上周增加 0.3 kg",
        "heart_rate": f"最近{days}天心率数据: 静息心率平均 72 bpm，正常",
        "mood": f"最近{days}天情绪记录: 整体偏正向，有2天记录疲劳",
    }

    return mock_data.get(data_type, f"暂无 {data_type} 类型的数据")


@tool
def calculate_bmi(weight_kg: float, height_m: float) -> str:
    """计算 BMI（身体质量指数）。

    Args:
        weight_kg: 体重（公斤）
        height_m: 身高（米）

    Returns:
        BMI 值和健康评估
    """
    if height_m <= 0 or weight_kg <= 0:
        return "输入无效，体重和身高必须大于0"

    bmi = weight_kg / (height_m ** 2)

    if bmi < 18.5:
        category = "偏瘦"
        advice = "建议适当增加营养摄入"
    elif bmi < 24:
        category = "正常"
        advice = "请继续保持健康的生活方式"
    elif bmi < 28:
        category = "偏胖"
        advice = "建议控制饮食，增加运动"
    else:
        category = "肥胖"
        advice = "建议咨询医生制定减重计划"

    return f"BMI: {bmi:.1f}，体重状态: {category}。{advice}"


@tool
def get_weather(city: str) -> str:
    """获取城市天气信息，用于生成与天气相关的健康建议。

    Args:
        city: 城市名称

    Returns:
        天气信息摘要
    """
    # TODO: 实际实现需要调用天气 API
    log.info("tool_get_weather", city=city)

    # Mock weather data
    return f"{city}今日天气: 晴，气温 22-28°C，湿度 55%，空气质量良好。适合户外运动。"


@tool
def calculate_water_intake(weight_kg: float, exercise_minutes: int = 0) -> str:
    """计算每日建议饮水量。

    Args:
        weight_kg: 体重（公斤）
        exercise_minutes: 今日运动时长（分钟）

    Returns:
        建议饮水量
    """
    # 基础饮水量: 每公斤体重 30-35ml
    base_intake = weight_kg * 33
    # 运动额外饮水: 每30分钟运动增加 500ml
    exercise_intake = (exercise_minutes / 30) * 500
    total = base_intake + exercise_intake

    return f"建议今日饮水量: {total:.0f} ml（约 {total/250:.1f} 杯）。基础需求 {base_intake:.0f} ml，运动补充 {exercise_intake:.0f} ml。"


# ══════════════════════════════════════════════════════════════════════════════
# Medication Tools — For Medication Agent
# ══════════════════════════════════════════════════════════════════════════════


@tool
def search_medication_info(drug_name: str) -> str:
    """查询药品信息，包括用法、禁忌、副作用等。

    Args:
        drug_name: 药品名称（通用名或商品名）

    Returns:
        药品详细信息
    """
    # TODO: 实际实现需要从药品知识库查询
    log.info("tool_search_medication", drug_name=drug_name)

    # Mock medication data
    mock_meds = {
        "阿司匹林": """【阿司匹林】
- 通用名: 乙酰水杨酸
- 常见剂量: 100mg/片
- 用法: 每日1次，餐后服用
- 注意事项: 胃溃疡患者慎用，不宜空腹服用
- 常见副作用: 胃肠道不适
- 禁忌: 活动性消化道出血、对阿司匹林过敏""",
        "二甲双胍": """【二甲双胍】
- 通用名: 盐酸二甲双胍
- 常见剂量: 500mg/片
- 用法: 每日2-3次，随餐服用
- 注意事项: 需监测肾功能，避免酗酒
- 常见副作用: 胃肠道反应（初期）
- 禁忌: 严重肾功能不全、酮症酸中毒""",
    }

    return mock_meds.get(drug_name, f"未找到 {drug_name} 的详细信息，建议咨询药师或医生。")


@tool
def check_drug_interaction(drug1: str, drug2: str) -> str:
    """检查两种药物之间的相互作用。

    Args:
        drug1: 第一种药品名称
        drug2: 第二种药品名称

    Returns:
        相互作用信息
    """
    # TODO: 实际实现需要药物相互作用数据库
    log.info("tool_drug_interaction", drug1=drug1, drug2=drug2)

    return f"【药物相互作用查询】{drug1} 与 {drug2}：暂无明确的严重相互作用记录。建议服药间隔至少2小时，并咨询医生确认。"


@tool
def query_medication_records(user_id: str, days: int = 30) -> str:
    """查询用户用药记录。

    Args:
        user_id: 用户ID
        days: 查询最近几天的记录

    Returns:
        用药记录摘要
    """
    log.info("tool_query_medication_records", user_id=user_id, days=days)

    # Mock data
    return f"""最近{days}天用药记录:
- 阿司匹林 100mg: 每日1次，服药率 93%
- 二甲双胍 500mg: 每日2次，服药率 87%（有3天漏服）
- 氨氯地平 5mg: 每日1次，服药率 100%"""


# ══════════════════════════════════════════════════════════════════════════════
# Insight Tools — For Insight Analyst Agent
# ══════════════════════════════════════════════════════════════════════════════


@tool
def analyze_health_trend(
    user_id: str,
    metric: str,
    period_days: int = 30,
) -> str:
    """分析健康数据趋势。

    Args:
        user_id: 用户ID
        metric: 分析指标，可选: blood_pressure, blood_sugar, sleep, weight, mood
        period_days: 分析周期（天）

    Returns:
        趋势分析结果
    """
    log.info("tool_analyze_trend", user_id=user_id, metric=metric, period=period_days)

    # Mock analysis
    mock_trends = {
        "blood_pressure": f"【血压趋势分析 - 近{period_days}天】\n趋势: 轻微上升 (+3%)\n波动性: 中等\n建议: 注意减少盐分摄入，保持规律作息",
        "blood_sugar": f"【血糖趋势分析 - 近{period_days}天】\n趋势: 稳定\n波动性: 低\n建议: 继续保持当前的饮食和用药习惯",
        "sleep": f"【睡眠趋势分析 - 近{period_days}天】\n趋势: 改善中 (+8%)\n深睡比例: 提升\n建议: 继续保持规律作息时间",
        "weight": f"【体重趋势分析 - 近{period_days}天】\n趋势: 略有上升 (+0.5kg)\n波动性: 低\n建议: 可适当增加运动量",
        "mood": f"【情绪趋势分析 - 近{period_days}天】\n整体: 积极向上\n低落天数: 3天\n建议: 情绪良好，继续保持社交和运动",
    }

    return mock_trends.get(metric, f"暂无 {metric} 的趋势数据")


@tool
def generate_weekly_summary(user_id: str) -> str:
    """生成用户健康周报摘要。

    Args:
        user_id: 用户ID

    Returns:
        周报摘要数据
    """
    log.info("tool_weekly_summary", user_id=user_id)

    return """【本周健康周报摘要】
📊 数据概览:
- 血压: 平均 125/80 mmHg，控制良好
- 血糖: 空腹平均 5.6 mmol/L，达标
- 睡眠: 平均 7.1 小时，较上周改善
- 运动: 累计 150 分钟，达到推荐量
- 用药: 整体依从性 92%

✅ 亮点:
- 睡眠质量持续改善
- 运动量达标

⚠️ 关注点:
- 周三、周四血压偏高
- 有2次漏服降糖药

💡 本周建议:
- 设置用药提醒避免漏服
- 周末注意饮食控制"""


@tool
def compare_periods(
    user_id: str,
    metric: str,
    period1_start: str,
    period2_start: str,
    duration_days: int = 7,
) -> str:
    """对比两个时间段的健康数据。

    Args:
        user_id: 用户ID
        metric: 对比指标
        period1_start: 第一个周期开始日期 (YYYY-MM-DD)
        period2_start: 第二个周期开始日期 (YYYY-MM-DD)
        duration_days: 每个周期的天数

    Returns:
        对比分析结果
    """
    log.info("tool_compare_periods", user_id=user_id, metric=metric)

    return f"""【{metric} 周期对比】
第一周期 ({period1_start} 起{duration_days}天): 平均值 偏高
第二周期 ({period2_start} 起{duration_days}天): 平均值 正常

变化: 改善 12%
分析: 近期生活方式调整效果显著"""


# ══════════════════════════════════════════════════════════════════════════════
# Tool Collections
# ══════════════════════════════════════════════════════════════════════════════

HEALTH_TOOLS = [
    query_health_data,
    calculate_bmi,
    get_weather,
    calculate_water_intake,
]

MEDICATION_TOOLS = [
    search_medication_info,
    check_drug_interaction,
    query_medication_records,
    query_health_data,  # 也需要查看健康数据
]

INSIGHT_TOOLS = [
    query_health_data,
    analyze_health_trend,
    generate_weekly_summary,
    compare_periods,
]

# General agent has no tools (pure conversation)
GENERAL_TOOLS = []
