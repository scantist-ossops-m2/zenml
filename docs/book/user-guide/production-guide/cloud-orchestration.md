---
description: Orchestrate using cloud resources.
---

# Orchestrating pipelines on the cloud

Until now, we've only run pipelines locally. The next step is to get free from our local machines and transition our pipelines to execute on the cloud. This will enable you to run your MLOps pipelines in a cloud environment, leveraging the scalability and robustness that cloud platforms offer.

In order to do this, we need to get familiar with two more stack components: 

- The [orchestrator](../../stacks-and-components/component-guide/orchestrators/) manages the workflow and execution of your pipelines.
- The [container registry](../../stacks-and-components/component-guide/container-registries/) is a storage and content delivery system that holds your Docker container images.

These, along with [remote storage](remote-storage.md), complete a basic cloud stack where our pipeline is entirely running on the cloud. 

## Starting with a basic cloud stack

The easiest cloud orchestrator to start with is the [Skypilot](https://skypilot.readthedocs.io/) orchestrator running on a public cloud. The advantage of Skypilot is that it simply provisions a VM to execute the pipeline on your cloud provider.

Coupled with Skypilot, we need a mechanism to package your code and ship it to the cloud for Skypilot to do its thing. ZenML uses [Docker](https://www.docker.com/) to achieve this. Every time you run a pipeline with a remote orchestrator, [ZenML builds an image](../advanced-guide/configuring-zenml/connect-your-git-repository.md) for the entire pipeline (and optionally each step of a pipeline depending on your [configuration](../advanced-guide/infrastructure-management/containerize-your-pipeline.md)). This image contains the code, requirements, and everything else needed to run the steps of the pipeline in any environment. ZenML then pushes this image to the container registry configured in your stack, and the orchestrator pulls the image when it's ready to execute a step.

To summarize, here is the broad sequence of events that happen when you run a pipeline with such a cloud stack:

<figure><img src="../../.gitbook/assets/cloud_orchestration_run.png" alt=""><figcaption><p>Sequence of events that happen when running a pipeline on a full cloud stack.</p></figcaption></figure>

1. The user runs a pipeline on the client machine. This executes the `run.py` script where ZenML reads the `@pipeline` function and understands what steps need to be executed.
2. The client asks the server for the stack info, which returns it with the configuration of the cloud stack.
3. Based on the stack info and pipeline specification, the client builds and pushes an image to the `container registry`. The image contains the environment needed to execute the pipeline and the code of the steps.
4. The client creates a run in the `orchestrator`. For example, in the case of the [Skypilot](https://skypilot.readthedocs.io/) orchestrator, it creates a virtual machine in the cloud with some commands to pull and run a Docker image from the specified container registry.  
5. The `orchestrator` pulls the appropriate image from the `container registry` as it's executing the pipeline (each step has an image).
6. As each pipeline runs, it stores artifacts physically in the `artifact store`. Of course, this artifact store needs to be some form of cloud storage.
7. As each pipeline runs, it reports status back to the ZenML server and optionally queries the server for metadata.

## Provisioning and registering a Skypilot orchestrator alongside a container registry

While there are detailed docs on [how to set up a Skypilot orchestrator](../../stacks-and-components/component-guide/orchestrators/skypilot-vm.md) and a [container registry](../../stacks-and-components/component-guide/container-registries/container-registries.md) on each public cloud, we have put the most relevant details here for convenience:

{% tabs %}
{% tab title="AWS" %}
In order to launch a pipeline on AWS with the SkyPilot orchestrator, the first 
thing that you need to do is to install the AWS and Skypilot integrations:

```shell
zenml integration install aws skypilot_aws -f
```

Before we start registering any components, there is another step that we have 
to execute. As we [explained in the previous section](./remote-storage.md#configuring-permissions-with-your-first-service-connector), 
components such as orchestrators and container registries often require you to 
set up the right permissions. In ZenML, this process is simplified with the 
use of [Service Connectors](../../stacks-and-components/auth-management). 
For this example, we will go ahead and use the [implicit authentication feature 
of our AWS service connector](../../stacks-and-components/auth-management/aws-service-connector.md#implicit-authentication) 
if you haven't already created a service connector in the last section:

```shell
zenml service-connector register aws_connector --type aws --auth-method implicit
```
Once the service connector is set up, we can register [a
Skypilot orchestrator](../../stacks-and-components/component-guide/orchestrators/skypilot-vm.md):

```shell
zenml orchestrator register skypilot_orchestrator -f vm_aws -c aws_connector
```

The next step is to register [an AWS container registry](../../stacks-and-components/component-guide/container-registries/aws.md). 
Similar to the orchestrator, we will use our connector as we are setting up the 
container registry:

```shell
zenml container-registry register cloud_container_registry -f aws --uri=<ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com -c aws_connector
```

With the components registered, everything is set up for the next steps. 

For more information, you can always check the [dedicated Skypilot orchestrator guide](../../stacks-and-components/component-guide/orchestrators/skypilot-vm.md).
{% endtab %}
{% tab title="GCP" %}
In order to launch a pipeline on GCP with the SkyPilot orchestrator, the first 
thing that you need to do is to install the GCP and Skypilot integrations:

```shell
zenml integration install gcp skypilot_gcp -f
```

Before we start registering any components, there is another step that we have 
to execute. As we [explained in the previous section](./remote-storage.md#configuring-permissions-with-your-first-service-connector), 
components such as orchestrators and container registries often require you to 
set up the right permissions. In ZenML, this process is simplified with the 
use of [Service Connectors](../../stacks-and-components/auth-management). 
For this example, we will go ahead and use the [implicit authentication feature 
of our GCP service connector](../../stacks-and-components/auth-management/gcp-service-connector.md#implicit-authentication) 
if you haven't already created a service connector in the last section:

```shell
zenml service-connector register gcp_connector --type gcp --auth-method implicit --auto-configure
```
Once the service connector is set up, we can register [a 
Skypilot orchestrator](../../stacks-and-components/component-guide/orchestrators/skypilot-vm.md):

```shell
zenml orchestrator register skypilot_orchestrator -f vm_gcp -c gcp_connector
```

The next step is to register [a GCP container registry](../../stacks-and-components/component-guide/container-registries/gcp.md). 
Similar to the orchestrator, we will use our connector as we are setting up the 
container registry:

```shell
zenml container-registry register cloud-container-registry -f gcp --uri=gcr.io/<PROJECT_ID> -c gcp_connector
```

With the components registered, everything is set up for the next steps. 

For more information, you can always check the [dedicated Skypilot orchestrator guide](../../stacks-and-components/component-guide/orchestrators/skypilot-vm.md).
{% endtab %}
{% tab title="Azure" %}
In order to launch a pipeline on Azure with the SkyPilot orchestrator, the first 
thing that you need to do is to install the Azure and SkyPilot integrations:

```shell
zenml integration install azure skypilot_azure -f
```

Before we start registering any components, there is another step that we have 
to execute. As we [explained in the previous section](./remote-storage.md#configuring-permissions-with-your-first-service-connector), 
components such as orchestrators and container registries often require you to 
set up the right permissions. In ZenML, this process is simplified with the 
use of [Service Connectors](../../stacks-and-components/auth-management). 
For this example, we will go ahead and use the [implicit authentication feature 
of our Azure service connector](../../stacks-and-components/auth-management/gcp-service-connector.md#implicit-authentication) 
if you haven't already created a service connector in the last section:

```shell
zenml service-connector register azure_connector --type azure --auth-method implicit --auto-configure
```
Once the service connector is set up, we can register [a 
Skypilot orchestrator](../../stacks-and-components/component-guide/orchestrators/skypilot-vm.md):

```shell
zenml orchestrator register skypilot_orchestrator -f vm_azure -c azure_connector
```

The next step is to register [an Azure container registry](../../stacks-and-components/component-guide/container-registries/azure.md). 
Similar to the orchestrator, we will use our connector as we are setting up the 
container registry.

```shell
zenml container-registry register cloud-container-registry -f azure --uri=<REGISTRY_NAME>.azurecr.io -c azure_connector
```

With the components registered, everything is set up for the next steps. 

For more information, you can always check the [dedicated Skypilot orchestrator guide](../../stacks-and-components/component-guide/orchestrators/skypilot-vm.md).
{% endtab %}
{% endtabs %}

{% hint style="info" %}
Having trouble with setting up infrastructure? Try reading the [stack deployment](../../stacks-and-components/stack-deployment/) section of the docs to gain more insight. If that still doesn't work, join the [ZenML community](https://zenml.io/slack) and ask!
{% endhint %}

## Running a pipeline on a cloud stack

Now that we have our orchestrator and container registry registered, we can [register a new stack](understand-stacks.md#registering-a-stack), just like we did in the previous chapter:

{% tabs %}
{% tab title="CLI" %}
```shell
zenml stack register minimal_cloud_stack -o skypilot_orchestrator -a cloud_artifact_store -c cloud_container_registry
```
{% endtab %}
{% tab title="Dashboard" %}
<figure><img src="../../.gitbook/assets/CreateStack.png" alt=""><figcaption><p>Register a new stack.</p></figcaption></figure>
{% endtab %}
{% endtabs %}

Now, using the [code from the previous chapter](understand-stacks.md#run-a-pipeline-on-the-new-local-stack), 
we can run a training pipeline. First, set the minimal cloud stack active:

```shell
zenml stack set minimal_cloud_stack
```

and then, run the training pipeline:

```shell
python run.py --training-pipeline
```
 
You will notice this time your pipeline behaves differently. After it has built the Docker image with all your code, it will push that image, and run a VM on the cloud. Here is where your pipeline will execute, and the logs will be streamed back to you. So with a few commands, we were able to ship our entire code to the cloud!

Curious to see what other stacks you can create? The [Component Guide](../../stacks-and-components/component-guide/) has an exhaustive list of various artifact stores, container registries, and orchestrators that are integrated with ZenML. Try playing around with more stack components to see how easy it is to switch between MLOps stacks with ZenML.

<!-- For scarf -->
<figure><img alt="ZenML Scarf" referrerpolicy="no-referrer-when-downgrade" src="https://static.scarf.sh/a.png?x-pxid=f0b4f458-0a54-4fcd-aa95-d5ee424815bc" /></figure>