"""
Agent Tools — Tool definitions for ReAct agents.

Each sub-agent has access to specific tools based on its domain.
Tools are implemented as LangChain @tool decorated async functions
that query the real PostgreSQL database.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

import structlog
from langchain_core.tools import tool
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from app.database import async_session_factory
from app.models.health_data import HealthEntry, QuestionResponse, DailySummary
from app.models.medication import Medication, MedicationCourse, MedicationEvent

log = structlog.get_logger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# Health Tools — For Health Advisor Agent
# ══════════════════════════════════════════════════════════════════════════════


@tool
async def query_health_data(
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
    log.info("tool_query_health_data", user_id=user_id, data_type=data_type, days=days)

    try:
        uid = UUID(user_id)
    except ValueError:
        return f"无效的用户ID: {user_id}"

    since = date.today() - timedelta(days=days)

    async with async_session_factory() as session:
        stmt = (
            select(HealthEntry)
            .options(selectinload(HealthEntry.question_responses))
            .where(
                and_(
                    HealthEntry.user_id == uid,
                    HealthEntry.entry_date >= since,
                )
            )
            .order_by(HealthEntry.entry_date.desc())
        )
        rows = (await session.execute(stmt)).scalars().all()

    if not rows:
        return f"最近{days}天暂无健康打卡数据"

    # Collect answers matching data_type from question_responses
    records: list[str] = []
    for entry in rows:
        for qr in entry.question_responses:
            if data_type in (qr.question_id or ""):
                label = qr.answer_label or qr.answer_value or ""
                records.append(f"{entry.entry_date}: {label}")

    if not records:
        # data_type not found in question_responses; return general summary
        dates = [e.entry_date.isoformat() for e in rows]
        return f"最近{days}天有 {len(rows)} 天健康打卡记录（{', '.join(dates[:5])}），但未找到 {data_type} 类型的数据"

    header = f"最近{days}天 {data_type} 数据（共 {len(records)} 条）:\n"
    return header + "\n".join(records[:15])


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
async def search_medication_info(drug_name: str) -> str:
    """查询药品信息，包括用法、禁忌、副作用等。

    Args:
        drug_name: 药品名称（通用名或商品名）

    Returns:
        药品详细信息
    """
    log.info("tool_search_medication", drug_name=drug_name)

    # Try RAG knowledge base first
    try:
        from app.rag.engine import get_rag_engine
        rag = get_rag_engine()
        results = await rag.retrieve(drug_name, collections=["medication"], top_k=3)
        if results:
            chunks = [r.get("content", "") for r in results if r.get("content")]
            if chunks:
                return f"【{drug_name} 相关信息】\n" + "\n---\n".join(chunks[:3])
    except Exception as e:
        log.warning("rag_medication_search_failed", error=str(e))

    return f"知识库中未找到 {drug_name} 的详细信息，建议咨询药师或医生。"


@tool
async def check_drug_interaction(drug1: str, drug2: str) -> str:
    """检查两种药物之间的相互作用。

    Args:
        drug1: 第一种药品名称
        drug2: 第二种药品名称

    Returns:
        相互作用信息
    """
    log.info("tool_drug_interaction", drug1=drug1, drug2=drug2)

    # Search RAG for interaction info
    try:
        from app.rag.engine import get_rag_engine
        rag = get_rag_engine()
        query = f"{drug1} {drug2} 药物相互作用"
        results = await rag.retrieve(query, collections=["medication"], top_k=3)
        if results:
            chunks = [r.get("content", "") for r in results if r.get("content")]
            if chunks:
                return f"【{drug1} 与 {drug2} 相互作用查询】\n" + "\n---\n".join(chunks[:3])
    except Exception as e:
        log.warning("rag_interaction_search_failed", error=str(e))

    return f"【药物相互作用查询】{drug1} 与 {drug2}：知识库中暂无明确记录。建议服药间隔至少2小时，并咨询医生确认。"


@tool
async def query_medication_records(user_id: str, days: int = 30) -> str:
    """查询用户用药记录。

    Args:
        user_id: 用户ID
        days: 查询最近几天的记录

    Returns:
        用药记录摘要
    """
    log.info("tool_query_medication_records", user_id=user_id, days=days)

    try:
        uid = UUID(user_id)
    except ValueError:
        return f"无效的用户ID: {user_id}"

    async with async_session_factory() as session:
        # Active medication courses
        stmt = (
            select(MedicationCourse)
            .join(Medication, MedicationCourse.med_id == Medication.id)
            .options(selectinload(MedicationCourse.medication))
            .where(
                and_(
                    Medication.user_id == uid,
                    MedicationCourse.status == "active",
                )
            )
        )
        courses = (await session.execute(stmt)).scalars().all()

        # Recent medication events
        since_dt = datetime.now(timezone.utc) - timedelta(days=days)
        evt_stmt = (
            select(MedicationEvent)
            .where(
                and_(
                    MedicationEvent.user_id == uid,
                    MedicationEvent.created_at >= since_dt,
                )
            )
            .order_by(MedicationEvent.created_at.desc())
            .limit(20)
        )
        events = (await session.execute(evt_stmt)).scalars().all()

    if not courses and not events:
        return f"最近{days}天暂无用药记录"

    parts: list[str] = []
    if courses:
        parts.append("【当前在用药物】")
        for c in courses:
            med = c.medication
            line = f"- {med.name}"
            if c.dose_text:
                line += f" {c.dose_text}"
            if c.frequency_text:
                line += f"，{c.frequency_text}"
            parts.append(line)

    if events:
        parts.append(f"\n【最近{days}天用药事件（共 {len(events)} 条）】")
        for ev in events[:10]:
            ts = ev.created_at.strftime("%m-%d %H:%M") if ev.created_at else ""
            parts.append(f"- {ts}: {ev.raw_text[:60]}")

    return "\n".join(parts)


# ══════════════════════════════════════════════════════════════════════════════
# Insight Tools — For Insight Analyst Agent
# ══════════════════════════════════════════════════════════════════════════════


@tool
async def analyze_health_trend(
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

    try:
        uid = UUID(user_id)
    except ValueError:
        return f"无效的用户ID: {user_id}"

    since = date.today() - timedelta(days=period_days)

    async with async_session_factory() as session:
        stmt = (
            select(HealthEntry)
            .options(selectinload(HealthEntry.question_responses))
            .where(
                and_(
                    HealthEntry.user_id == uid,
                    HealthEntry.entry_date >= since,
                )
            )
            .order_by(HealthEntry.entry_date.asc())
        )
        rows = (await session.execute(stmt)).scalars().all()

    if not rows:
        return f"最近{period_days}天暂无健康数据，无法分析趋势"

    records: list[tuple[date, str]] = []
    for entry in rows:
        for qr in entry.question_responses:
            if metric in (qr.question_id or ""):
                label = qr.answer_label or qr.answer_value or ""
                records.append((entry.entry_date, label))

    if not records:
        return f"最近{period_days}天有 {len(rows)} 天打卡，但未找到 {metric} 类型数据"

    lines = [f"【{metric} 趋势分析 - 近{period_days}天，共 {len(records)} 条】"]
    for d, v in records[-10:]:
        lines.append(f"  {d}: {v}")
    return "\n".join(lines)


@tool
async def generate_weekly_summary(user_id: str) -> str:
    """生成用户健康周报摘要。

    Args:
        user_id: 用户ID

    Returns:
        周报摘要数据
    """
    log.info("tool_weekly_summary", user_id=user_id)

    try:
        uid = UUID(user_id)
    except ValueError:
        return f"无效的用户ID: {user_id}"

    since = date.today() - timedelta(days=7)

    async with async_session_factory() as session:
        # Health entries for last 7 days
        h_stmt = (
            select(HealthEntry)
            .options(selectinload(HealthEntry.question_responses))
            .where(
                and_(
                    HealthEntry.user_id == uid,
                    HealthEntry.entry_date >= since,
                )
            )
            .order_by(HealthEntry.entry_date.asc())
        )
        entries = (await session.execute(h_stmt)).scalars().all()

        # Active medications
        m_stmt = (
            select(MedicationCourse)
            .join(Medication, MedicationCourse.med_id == Medication.id)
            .options(selectinload(MedicationCourse.medication))
            .where(
                and_(
                    Medication.user_id == uid,
                    MedicationCourse.status == "active",
                )
            )
        )
        courses = (await session.execute(m_stmt)).scalars().all()

    parts = [f"【本周健康周报摘要（最近7天）】"]
    parts.append(f"📊 健康打卡: {len(entries)}/7 天")

    # Aggregate question responses by type
    type_values: dict[str, list[str]] = {}
    for e in entries:
        for qr in e.question_responses:
            qid = qr.question_id or "other"
            label = qr.answer_label or qr.answer_value or ""
            if label:
                type_values.setdefault(qid, []).append(label)

    if type_values:
        parts.append("\n📋 数据概览:")
        for qid, vals in type_values.items():
            parts.append(f"  - {qid}: {len(vals)} 条记录")

    if courses:
        parts.append("\n💊 在用药物:")
        for c in courses:
            med = c.medication
            parts.append(f"  - {med.name} {c.dose_text or ''} {c.frequency_text or ''}")

    if not entries:
        parts.append("\n⚠️ 本周无健康打卡记录，建议保持每日记录习惯")

    return "\n".join(parts)


@tool
async def compare_periods(
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

    try:
        uid = UUID(user_id)
        p1 = date.fromisoformat(period1_start)
        p2 = date.fromisoformat(period2_start)
    except (ValueError, TypeError) as e:
        return f"参数解析错误: {e}"

    async def _query_period(session, start: date, days: int) -> list[str]:
        end = start + timedelta(days=days)
        stmt = (
            select(HealthEntry)
            .options(selectinload(HealthEntry.question_responses))
            .where(
                and_(
                    HealthEntry.user_id == uid,
                    HealthEntry.entry_date >= start,
                    HealthEntry.entry_date < end,
                )
            )
        )
        rows = (await session.execute(stmt)).scalars().all()
        vals = []
        for e in rows:
            for qr in e.question_responses:
                if metric in (qr.question_id or ""):
                    vals.append(qr.answer_label or qr.answer_value or "")
        return vals

    async with async_session_factory() as session:
        v1 = await _query_period(session, p1, duration_days)
        v2 = await _query_period(session, p2, duration_days)

    parts = [f"【{metric} 周期对比】"]
    parts.append(f"周期一 ({period1_start} 起{duration_days}天): {len(v1)} 条记录")
    if v1:
        parts.append(f"  数据: {', '.join(v1[:5])}")
    parts.append(f"周期二 ({period2_start} 起{duration_days}天): {len(v2)} 条记录")
    if v2:
        parts.append(f"  数据: {', '.join(v2[:5])}")

    return "\n".join(parts)


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
