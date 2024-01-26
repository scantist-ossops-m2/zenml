#  Copyright (c) ZenML GmbH 2024. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at:
#
#       https://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express
#  or implied. See the License for the specific language governing
#  permissions and limitations under the License.
"""Base implementation of the event source configuration."""
import json
from abc import ABC, abstractmethod
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    Dict,
    Type,
)

from pydantic import BaseModel

from zenml.models import EventSourceRequest, EventSourceResponse
from zenml.plugins.base_plugin_flavor import (
    BasePlugin,
    BasePluginConfig,
    BasePluginFlavor,
    BasePluginFlavorResponse,
)

if TYPE_CHECKING:
    pass


# -------------------- Event Models -----------------------------------


class BaseEvent(BaseModel):
    """Base class for all inbound events."""


# -------------------- Configuration Models ----------------------------------


class EventSourceConfig(BasePluginConfig):
    """The Event Source configuration."""


class EventFilterConfig(BaseModel, ABC):
    """The Event Filter configuration."""

    @abstractmethod
    def event_matches_filter(self, event: BaseEvent) -> bool:
        """All implementations need to implement this check.

        If the filter matches the inbound event instance, this should
        return True, else False.

        Args:
            event: The inbound event instance.

        Returns: Whether the filter matches the event.
        """


# -------------------- Plugin -----------------------------------


class BaseEventSourcePlugin(BasePlugin, ABC):
    """Implementation for an EventPlugin."""

    @property
    def config_class(self) -> Type[BasePluginConfig]:
        """Returns the `BasePluginConfig` config.

        Returns:
            The configuration.
        """
        return EventSourceConfig

    @abstractmethod
    def create_event_source(
        self, event_source: EventSourceRequest
    ) -> EventSourceResponse:
        """Wraps the zen_store creation method for plugin specific functionality.

        All implementation of the BaseEventSource can overwrite this method to add
        implementation specific functionality.

        Args:
            event_source: Request model for the event source.

        Returns:
            The created event source.
        """
        self._fail_if_event_source_configuration_invalid(
            event_source=event_source
        )
        return self.zen_store.create_event_source(event_source=event_source)

    def _fail_if_event_source_configuration_invalid(
        self, event_source: EventSourceRequest
    ):
        try:
            self.config_class(**event_source.configuration)
        except ValueError:
            raise ValueError("Invalid Configuration.")
        else:
            return


# -------------------- Flavors ----------------------------------


class EventFlavorResponse(BasePluginFlavorResponse):
    """Response model for Event Flavors."""

    source_config_schema: Dict[str, Any]
    filter_config_schema: Dict[str, Any]


class BaseEventSourcePluginFlavor(BasePluginFlavor, ABC):
    """Base Event Plugin Flavor to access an event plugin along with its configurations."""

    # EventPlugin specific
    EVENT_SOURCE_CONFIG_CLASS: ClassVar[Type[EventSourceConfig]]
    EVENT_FILTER_CONFIG_CLASS: ClassVar[Type[EventFilterConfig]]

    @classmethod
    def get_event_filter_config_schema(cls) -> Dict[str, Any]:
        """The config schema for a flavor.

        Returns:
            The config schema.
        """
        config_schema: Dict[str, Any] = json.loads(
            cls.EVENT_SOURCE_CONFIG_CLASS.schema_json()
        )

        return config_schema

    @classmethod
    def get_event_source_config_schema(cls) -> Dict[str, Any]:
        """The config schema for a flavor.

        Returns:
            The config schema.
        """
        config_schema: Dict[str, Any] = json.loads(
            cls.EVENT_FILTER_CONFIG_CLASS.schema_json()
        )

        return config_schema

    @classmethod
    def get_plugin_flavor_response_model(cls) -> EventFlavorResponse:
        """Convert the Flavor into a Response Model."""
        return EventFlavorResponse(
            flavor_name=cls.FLAVOR,
            plugin_type=cls.TYPE,
            source_config_schema=cls.get_event_source_config_schema(),
            filter_config_schema=cls.get_event_filter_config_schema(),
        )