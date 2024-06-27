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
"""Models representing full stack requests."""

from typing import Any, Dict, List, Optional, Union
from uuid import UUID

from pydantic import BaseModel, Field

from zenml.constants import STR_FIELD_MAX_LENGTH
from zenml.enums import StackComponentType
from zenml.models.v2.base.base import BaseRequest


class ServiceConnectorInfo(BaseModel):
    """Information about the service connector when creating a full stack."""

    connector_type: str
    auth_type: str
    configuration: Dict[str, Any] = {}


class ComponentInfo(BaseModel):
    """Information about each stack components when creating a full stack."""

    flavor: str
    service_connector_index: Optional[int] = Field(
        default=None,
        title="The id of the service connector from the list "
        "`service_connectors`.",
        description="The id of the service connector from the list "
        "`service_connectors` from `FullStackRequest`.",
    )
    configuration: Dict[str, Any] = {}


class FullStackRequest(BaseRequest):
    """Request model for a full-stack."""

    user_id: Optional[UUID] = None
    workspace_id: Optional[UUID] = None

    name: str = Field(
        title="The name of the stack.", max_length=STR_FIELD_MAX_LENGTH
    )
    description: Optional[str] = Field(
        default="",
        title="The description of the stack",
        max_length=STR_FIELD_MAX_LENGTH,
    )
    service_connectors: List[Union[UUID, ServiceConnectorInfo]] = Field(
        default=[],
        title="The service connectors dictionary for the full stack "
        "registration.",
        description="The UUID of an already existing service connector or "
        "request information to create a service connector from "
        "scratch.",
    )
    components: Dict[StackComponentType, Union[UUID, ComponentInfo]] = Field(
        title="The mapping for the components of the full stack registration.",
        description="The mapping from component types to either UUIDs of "
        "existing components or request information for brand new "
        "components.",
    )