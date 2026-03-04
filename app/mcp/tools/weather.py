"""
Weather tool — fetch current weather data for a city.

Uses wttr.in free API (no key required) as the default.
Can be replaced with a real weather API by setting WEATHER_API_KEY.
"""

from __future__ import annotations

import httpx
import structlog

log = structlog.get_logger(__name__)


async def get_weather(city: str) -> str:
    """
    Get weather information for a city.
    Returns temperature, humidity, and weather description.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # wttr.in provides a simple weather API
            url = f"https://wttr.in/{city}?format=j1"
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()

            current = data.get("current_condition", [{}])[0]
            temp_c = current.get("temp_C", "N/A")
            humidity = current.get("humidity", "N/A")
            feels_like = current.get("FeelsLikeC", "N/A")
            desc_cn = current.get("lang_zh", [{}])
            weather_desc = desc_cn[0].get("value", current.get("weatherDesc", [{}])[0].get("value", "未知")) if desc_cn else "未知"
            wind_speed = current.get("windspeedKmph", "N/A")
            uv_index = current.get("uvIndex", "N/A")

            return (
                f"🌤 {city}天气:\n"
                f"  温度: {temp_c}°C (体感 {feels_like}°C)\n"
                f"  湿度: {humidity}%\n"
                f"  天气: {weather_desc}\n"
                f"  风速: {wind_speed} km/h\n"
                f"  紫外线指数: {uv_index}"
            )

    except httpx.TimeoutException:
        return f"获取 {city} 天气超时，请稍后再试。"
    except Exception as e:
        log.warning("weather_api_error", city=city, error=str(e))
        return f"无法获取 {city} 的天气信息: {e}"
