"""Todo list platform for HA Advanced Timer & Calendar."""
from __future__ import annotations
import logging
from typing import Any

from homeassistant.components.todo import (
    TodoItem,
    TodoItemStatus,
    TodoListEntity,
    TodoListEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, ReminderType
from .coordinator import ATCDataCoordinator
from .storage import ATCStorage

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: ATCDataCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([ATCTodoListEntity(coordinator, entry.entry_id)])


class ATCTodoListEntity(CoordinatorEntity, TodoListEntity):
    """Todo list entity backed by ATC storage reminders of type 'todo'."""

    _attr_supported_features = (
        TodoListEntityFeature.CREATE_TODO_ITEM
        | TodoListEntityFeature.UPDATE_TODO_ITEM
        | TodoListEntityFeature.DELETE_TODO_ITEM
    )

    def __init__(self, coordinator: ATCDataCoordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._attr_unique_id = f"{entry_id}_todo_list"
        self._attr_name = "ATC Todos"

    @property
    def todo_items(self) -> list[TodoItem]:
        """Return todo items from reminders of type 'todo'."""
        data = self.coordinator.data or {}
        items = []
        for reminder in data.get("reminders", []):
            if reminder.get("type") != ReminderType.TODO:
                continue
            status = (
                TodoItemStatus.COMPLETE
                if reminder.get("completed", False)
                else TodoItemStatus.NEEDS_ACTION
            )
            items.append(
                TodoItem(
                    uid=reminder["id"],
                    summary=reminder.get("name", "Todo"),
                    status=status,
                    description=reminder.get("description", ""),
                    due=reminder.get("due_date"),
                )
            )
        return items

    async def async_create_todo_item(self, item: TodoItem) -> None:
        """Create a new todo reminder in storage."""
        data = await self.coordinator.storage.async_load()
        reminder: dict[str, Any] = {
            "id": ATCStorage.new_id(),
            "name": item.summary or "Todo",
            "type": ReminderType.TODO,
            "description": item.description or "",
            "due_date": str(item.due) if item.due else None,
            "completed": item.status == TodoItemStatus.COMPLETE,
            "notifications": {},
        }
        data.setdefault("reminders", []).append(reminder)
        await self.coordinator.storage.async_save(data)
        await self.coordinator.async_request_refresh()

    async def async_update_todo_item(self, item: TodoItem) -> None:
        """Update an existing todo reminder."""
        data = await self.coordinator.storage.async_load()
        for reminder in data.get("reminders", []):
            if reminder["id"] == item.uid:
                if item.summary is not None:
                    reminder["name"] = item.summary
                if item.description is not None:
                    reminder["description"] = item.description
                if item.due is not None:
                    reminder["due_date"] = str(item.due)
                if item.status is not None:
                    reminder["completed"] = item.status == TodoItemStatus.COMPLETE
                break
        await self.coordinator.storage.async_save(data)
        await self.coordinator.async_request_refresh()

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        """Remove todo reminders by UID."""
        data = await self.coordinator.storage.async_load()
        data["reminders"] = [
            r for r in data.get("reminders", []) if r["id"] not in uids
        ]
        await self.coordinator.storage.async_save(data)
        await self.coordinator.async_request_refresh()
