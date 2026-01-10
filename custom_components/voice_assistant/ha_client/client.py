"""Home Assistant API client for LLM tool execution."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class HomeAssistantClient:
    """Client for executing Home Assistant operations."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the client."""
        self.hass = hass

    async def execute_tool(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute a tool and return the result.

        Args:
            tool_name: The name of the tool to execute.
            arguments: The tool arguments.

        Returns:
            Dict with 'success' (bool) and 'result' or 'error'.
        """
        try:
            handler = getattr(self, f"_tool_{tool_name}", None)
            if handler is None:
                return {"success": False, "error": f"Unknown tool: {tool_name}"}

            result = await handler(**arguments)
            return {"success": True, "result": result}

        except Exception as err:
            _LOGGER.error("Tool execution error (%s): %s", tool_name, err)
            return {"success": False, "error": str(err)}

    async def _tool_get_entity_state(self, entity_id: str) -> dict[str, Any]:
        """Get the state of an entity."""
        state = self.hass.states.get(entity_id)
        if state is None:
            return {"error": f"Entity '{entity_id}' not found"}

        return {
            "entity_id": entity_id,
            "state": state.state,
            "attributes": dict(state.attributes),
            "last_changed": state.last_changed.isoformat(),
        }

    async def _tool_call_service(
        self,
        domain: str,
        service: str,
        entity_id: str,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Call a Home Assistant service."""
        service_data = {"entity_id": entity_id}
        if data:
            service_data.update(data)

        await self.hass.services.async_call(
            domain,
            service,
            service_data,
            blocking=True,
        )

        return {
            "called": f"{domain}.{service}",
            "entity_id": entity_id,
            "status": "success",
        }

    async def _tool_search_entities(
        self,
        query: str,
        domain: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Search for entities matching a query."""
        query_lower = query.lower()
        results = []

        for state in self.hass.states.async_all():
            # Skip if domain filter doesn't match
            if domain and not state.entity_id.startswith(f"{domain}."):
                continue

            # Check if query matches entity_id or friendly_name
            friendly_name = state.attributes.get("friendly_name", "").lower()
            entity_id_lower = state.entity_id.lower()

            if query_lower in entity_id_lower or query_lower in friendly_name:
                results.append({
                    "entity_id": state.entity_id,
                    "friendly_name": state.attributes.get("friendly_name"),
                    "state": state.state,
                    "domain": state.entity_id.split(".")[0],
                })

            if len(results) >= limit:
                break

        return results

    async def _tool_get_area_entities(
        self,
        area_name: str,
        domain: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get entities in a specific area."""
        from homeassistant.helpers import area_registry, entity_registry

        area_reg = area_registry.async_get(self.hass)
        entity_reg = entity_registry.async_get(self.hass)

        # Find area by name
        area = None
        area_name_lower = area_name.lower()
        for a in area_reg.async_list_areas():
            if a.name.lower() == area_name_lower:
                area = a
                break

        if area is None:
            return {"error": f"Area '{area_name}' not found"}

        # Get entities in area
        results = []
        for entity in entity_reg.entities.values():
            if entity.area_id != area.id:
                continue
            if domain and not entity.entity_id.startswith(f"{domain}."):
                continue

            state = self.hass.states.get(entity.entity_id)
            if state:
                results.append({
                    "entity_id": entity.entity_id,
                    "friendly_name": state.attributes.get("friendly_name"),
                    "state": state.state,
                    "domain": entity.entity_id.split(".")[0],
                })

        return results

    async def _tool_list_areas(self) -> list[dict[str, Any]]:
        """List all areas."""
        from homeassistant.helpers import area_registry

        area_reg = area_registry.async_get(self.hass)

        return [
            {"id": area.id, "name": area.name}
            for area in area_reg.async_list_areas()
        ]

    async def _tool_set_light_brightness(
        self, entity_id: str, brightness_pct: int
    ) -> dict[str, Any]:
        """Set light brightness."""
        brightness = int(brightness_pct * 255 / 100)
        await self.hass.services.async_call(
            "light",
            "turn_on",
            {"entity_id": entity_id, "brightness": brightness},
            blocking=True,
        )
        return {"entity_id": entity_id, "brightness_pct": brightness_pct}

    async def _tool_set_light_color(
        self, entity_id: str, color_name: str
    ) -> dict[str, Any]:
        """Set light color."""
        await self.hass.services.async_call(
            "light",
            "turn_on",
            {"entity_id": entity_id, "color_name": color_name},
            blocking=True,
        )
        return {"entity_id": entity_id, "color": color_name}

    async def _tool_set_temperature(
        self, entity_id: str, temperature: float
    ) -> dict[str, Any]:
        """Set thermostat temperature."""
        await self.hass.services.async_call(
            "climate",
            "set_temperature",
            {"entity_id": entity_id, "temperature": temperature},
            blocking=True,
        )
        return {"entity_id": entity_id, "temperature": temperature}

    async def _tool_set_hvac_mode(
        self, entity_id: str, hvac_mode: str
    ) -> dict[str, Any]:
        """Set HVAC mode."""
        await self.hass.services.async_call(
            "climate",
            "set_hvac_mode",
            {"entity_id": entity_id, "hvac_mode": hvac_mode},
            blocking=True,
        )
        return {"entity_id": entity_id, "hvac_mode": hvac_mode}
