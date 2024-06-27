#  Copyright (c) ZenML GmbH 2023. All Rights Reserved.
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
"""Implementation of the Databricks orchestrator."""

import io
import itertools
import os
import re
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Type, cast

from databricks.sdk import WorkspaceClient as DatabricksClient
from databricks.sdk.service.jobs import Task as DatabricksTask

from zenml.client import Client
from zenml.entrypoints.step_entrypoint_configuration import (
    StepEntrypointConfiguration,
)
from zenml.environment import Environment
from zenml.integrations.databricks.flavors.databricks_orchestrator_flavor import (
    DatabricksOrchestratorConfig,
    DatabricksOrchestratorSettings,
)
from zenml.integrations.databricks.orchestrators.databricks_utils import (
    convert_step_to_task,
)
from zenml.io import fileio
from zenml.logger import get_logger
from zenml.models.v2.core.schedule import ScheduleResponse
from zenml.orchestrators.utils import get_orchestrator_run_name
from zenml.orchestrators.wheeled_orchestrator import WheeledOrchestrator
from zenml.stack import StackValidator
from zenml.utils import io_utils
from zenml.utils.pipeline_docker_image_builder import (
    PipelineDockerImageBuilder,
)

if TYPE_CHECKING:
    from zenml.models import PipelineDeploymentResponse
    from zenml.stack import Stack


logger = get_logger(__name__)

ENV_ZENML_DATABRICKS_ORCHESTRATOR_RUN_ID = (
    "ZENML_DATABRICKS_ORCHESTRATOR_RUN_ID"
)
ZENML_STEP_DEFAULT_ENTRYPOINT_COMMAND = "entrypoint.main"


class DatabricksOrchestrator(WheeledOrchestrator):
    """Base class for Orchestrator responsible for running pipelines remotely in a VM.

    This orchestrator does not support running on a schedule.
    """

    # The default instance type to use if none is specified in settings
    DEFAULT_INSTANCE_TYPE: Optional[str] = None

    @property
    def validator(self) -> Optional[StackValidator]:
        """Validates the stack.

        In the remote case, checks that the stack contains a container registry,
        image builder and only remote components.

        Returns:
            A `StackValidator` instance.
        """

        def _validate_remote_components(
            stack: "Stack",
        ) -> Tuple[bool, str]:
            for component in stack.components.values():
                continue  # TODO: Remove this line
                if not component.config.is_local:
                    continue

                return False, (
                    f"The Databricks orchestrator runs pipelines remotely, "
                    f"but the '{component.name}' {component.type.value} is "
                    "a local stack component and will not be available in "
                    "the Databricks step.\nPlease ensure that you always "
                    "use non-local stack components with the Databricks "
                    "orchestrator."
                )

            return True, ""

        return StackValidator(
            custom_validation_function=_validate_remote_components,
        )

    def _get_databricks_client(
        self,
        settings: DatabricksOrchestratorSettings,
    ) -> DatabricksClient:
        """Creates a Databricks client.

        Args:
            settings: The orchestrator settings.

        Returns:
            The Databricks client.
        """
        return DatabricksClient(
            host="https://adb-3518312650259607.7.azuredatabricks.net",
            client_id="7c2a45bf-fd61-46b7-a0a3-6ff6d7b81a7a",
            client_secret="dose6c0332e765954e8483c60503b2e0a02c",
        )

    @property
    def config(self) -> DatabricksOrchestratorConfig:
        """Returns the `DatabricksOrchestratorConfig` config.

        Returns:
            The configuration.
        """
        return cast(DatabricksOrchestratorConfig, self._config)

    @property
    def settings_class(self) -> Type[DatabricksOrchestratorSettings]:
        """Settings class for the Databricks orchestrator.

        Returns:
            The settings class.
        """
        return DatabricksOrchestratorSettings

    def get_orchestrator_run_id(self) -> str:
        """Returns the active orchestrator run id.

        Raises:
            RuntimeError: If no run id exists. This happens when this method
                gets called while the orchestrator is not running a pipeline.

        Returns:
            The orchestrator run id.
        """
        return os.getenv(ENV_ZENML_DATABRICKS_ORCHESTRATOR_RUN_ID)

    @property
    def root_directory(self) -> str:
        """Path to the root directory for all files concerning this orchestrator.

        Returns:
            Path to the root directory.
        """
        return os.path.join(
            io_utils.get_global_config_directory(),
            "databricks",
            str(self.id),
        )

    @property
    def pipeline_directory(self) -> str:
        """Returns path to a directory in which the kubeflow pipeline files are stored.

        Returns:
            Path to the pipeline directory.
        """
        return os.path.join(self.root_directory, "pipelines")

    def setup_credentials(self) -> None:
        """Set up credentials for the orchestrator."""
        connector = self.get_connector()
        assert connector is not None
        connector.configure_local_client()

    def prepare_or_run_pipeline(
        self,
        deployment: "PipelineDeploymentResponse",
        stack: "Stack",
        environment: Dict[str, str],
    ) -> Any:
        """Creates a databricks yaml file.

        This functions as an intermediary representation of the pipeline which
        is then deployed to the kubeflow pipelines instance.

        How it works:
        -------------
        Before this method is called the `prepare_pipeline_deployment()`
        method builds a docker image that contains the code for the
        pipeline, all steps the context around these files.

        Based on this docker image a callable is created which builds
        container_ops for each step (`_construct_databricks_pipeline`).
        To do this the entrypoint of the docker image is configured to
        run the correct step within the docker image. The dependencies
        between these container_ops are then also configured onto each
        container_op by pointing at the downstream steps.

        This callable is then compiled into a databricks yaml file that is used as
        the intermediary representation of the kubeflow pipeline.

        This file, together with some metadata, runtime configurations is
        then uploaded into the kubeflow pipelines cluster for execution.

        Args:
            deployment: The pipeline deployment to prepare or run.
            stack: The stack the pipeline will run on.
            environment: Environment variables to set in the orchestration
                environment.

        Raises:
            RuntimeError: If trying to run a pipeline in a notebook
                environment.
        """
        # First check whether the code running in a notebook
        if Environment.in_notebook():
            raise RuntimeError(
                "The Kubeflow orchestrator cannot run pipelines in a notebook "
                "environment. The reason is that it is non-trivial to create "
                "a Docker image of a notebook. Please consider refactoring "
                "your notebook cells into separate scripts in a Python module "
                "and run the code outside of a notebook when using this "
                "orchestrator."
            )

        # Create a callable for future compilation into a dsl.Pipeline.
        def _construct_databricks_pipeline() -> List[DatabricksTask]:
            """Create a databrcks task for each step.

            This should contain the name of the step or task and configures the
            entrypoint of the task to run the step.

            Additionally, this gives each task information about its
            direct downstream steps.
            """
            tasks: DatabricksTask = []
            for step_name, step in deployment.step_configurations.items():
                # image = self.get_image(
                #    deployment=deployment, step_name=step_name
                # )

                # The arguments are passed to configure the entrypoint of the
                # docker container when the step is called.
                arguments = (
                    StepEntrypointConfiguration.get_entrypoint_arguments(
                        step_name=step_name, deployment_id=deployment.id
                    )
                )

                # Construct the --env argument
                env_vars = []
                for key, value in environment.items():
                    env_vars.append(f"{key}={value}")
                env_vars.append("ZENML_DATABRICKS_SOURCE_PREFIX=zenmlproject")
                env_vars.append(
                    f"ZENML_DATABRICKS_ORCHESTRATOR_RUN_ID={deployment.id}"
                )
                env_arg = ",".join(env_vars)

                arguments.extend(["--env", env_arg])

                # Find the upstream container ops of the current step and
                # configure the current container op to run after them
                upstream_steps = [
                    f"{deployment.id}_{upstream_step_name}"
                    for upstream_step_name in step.spec.upstream_steps
                ]

                docker_settings = step.config.docker_settings
                docker_image_builder = PipelineDockerImageBuilder()
                requirements_files = (
                    docker_image_builder.gather_requirements_files(
                        docker_settings=docker_settings,
                        stack=Client().active_stack,
                        log=False,
                    )
                )
                requirements = list(
                    itertools.chain.from_iterable(
                        r[1].split("\n") for r in requirements_files
                    )
                )

                task = convert_step_to_task(
                    f"{deployment.id}_{step_name}",
                    ZENML_STEP_DEFAULT_ENTRYPOINT_COMMAND,
                    arguments,
                    requirements,
                    depends_on=upstream_steps,
                )
                breakpoint()
                tasks.append(task)
                # Create a container_op - the kubeflow equivalent of a step. It
                # contains the name of the step, the name of the docker image,
                # the command to use to run the step entrypoint
                # (e.g. `python -m zenml.entrypoints.step_entrypoint`)
                # and the arguments to be passed along with the command. Find
                # out more about how these arguments are parsed and used
                # in the base entrypoint `run()` method.
                # settings = cast(
                #    DatabricksOrchestratorSettings, self.get_settings(step)
                # )
            return tasks

        orchestrator_run_name = get_orchestrator_run_name(
            pipeline_name=deployment.pipeline_configuration.name
        )

        # Get a filepath to use to save the finished yaml to
        fileio.makedirs(self.pipeline_directory)
        pipeline_file_path = os.path.join(
            self.pipeline_directory, f"{orchestrator_run_name}.yaml"
        )

        # Copy the repository to a temporary directory and add a setup.py file
        repository_temp_dir = (
            self.copy_repository_to_temp_dir_and_add_setup_py()
        )

        # Create a wheel for the package in the temporary directory
        wheel_path = self.create_wheel(temp_dir=repository_temp_dir)

        breakpoint()

        pipeline_wheel_path = os.path.join(
            self.pipeline_directory, wheel_path.rsplit("/", 1)[-1]
        )

        fileio.copy(wheel_path, pipeline_wheel_path, overwrite=True)

        fileio.rmtree(repository_temp_dir)

        databricks_client = self._get_databricks_client(
            cast(DatabricksOrchestratorSettings, self.get_settings())
        )

        breakpoint()
        # Create an empty folder in a volume.
        databricks_directory = (
            f"/zenml/{deployment.pipeline.name}/{orchestrator_run_name}"
        )
        databricks_wheel_path = (
            f"{databricks_directory}/{wheel_path.rsplit('/', 1)[-1]}"
        )
        databricks_client.files.create_directory(databricks_directory)

        breakpoint()
        # Upload a file to a volume.
        with fileio.open(wheel_path, "rb") as file:
            file_bytes = file.read()
            binary_data = io.BytesIO(file_bytes)
            databricks_client.files.upload(
                databricks_wheel_path, binary_data, overwrite=True
            )

        breakpoint()

        logger.info(
            "Writing Kubeflow workflow definition to `%s`.", pipeline_file_path
        )

        # using the databricks client uploads the pipeline to kubeflow pipelines and
        # runs it there
        breakpoint()
        self._upload_and_run_pipeline(
            pipeline_name=orchestrator_run_name,
            tasks=_construct_databricks_pipeline(),
            run_name=orchestrator_run_name,
            settings=cast(DatabricksOrchestratorSettings, self.get_settings()),
        )

    def _upload_and_run_pipeline(
        self,
        pipeline_name: str,
        tasks: List[DatabricksTask],
        run_name: str,
        settings: DatabricksOrchestratorSettings,
        schedule: Optional["ScheduleResponse"] = None,
    ) -> None:
        """Uploads and run the pipeline on the Databricks jobs.

        Args:
            pipeline_name: Name of the pipeline.
            tasks: List of tasks to run.
            run_name: Orchestrator run name.
            settings: Pipeline level settings for this orchestrator.
            schedule: The schedule the pipeline will run on.
        """
        databricks_client = self._get_databricks_client(settings)
        databricks_client.jobs.create(
            name=pipeline_name,
            tasks=tasks,
        )

    def sanitize_cluster_name(self, name: str) -> str:
        """Sanitize the value to be used in a cluster name.

        Args:
            name: Arbitrary input cluster name.

        Returns:
            Sanitized cluster name.
        """
        name = re.sub(
            r"[^a-z0-9-]", "-", name.lower()
        )  # replaces any character that is not a lowercase letter, digit, or hyphen with a hyphen
        name = re.sub(r"^[-]+", "", name)  # trim leading hyphens
        name = re.sub(r"[-]+$", "", name)  # trim trailing hyphens
        return name