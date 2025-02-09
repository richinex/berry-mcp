# src/ai_agent/tools/weather.py
from typing import Dict, Optional, Any
from pydantic import BaseModel

class WeatherResponse(BaseModel):
    temperature: float
    condition: str
    humidity: Optional[float] = None
    wind_speed: Optional[float] = None

async def get_weather(
    location: str,
    units: str = "celsius",
    detailed: bool = False
) -> Dict[str, Any]:
    """Get weather information for a specific location.

    Args:
        location: City and country (e.g., 'London, UK')
        units: Temperature units ('celsius' or 'fahrenheit')
        detailed: Whether to return detailed information
    """
    # Implement actual weather API call here
    return WeatherResponse(
        temperature=20.5,
        condition="sunny",
        humidity=65.0 if detailed else None,
        wind_speed=10.0 if detailed else None
    ).dict(exclude_none=True)