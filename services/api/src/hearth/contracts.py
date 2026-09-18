"""Versioned, closed wire contracts shared by the control plane and native clients."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    field_validator,
    model_validator,
)

Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Label = Annotated[str, Field(min_length=1, max_length=120)]
Identifier = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{0,79}$")]
Nonnegative = Annotated[StrictInt, Field(ge=0, le=2**53 - 1)]
Positive = Annotated[StrictInt, Field(ge=1, le=2**53 - 1)]


class WireModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False, validate_default=True)
    schema_version: Literal[1] = 1

    @field_validator("schema_version", mode="before")
    @classmethod
    def version_is_not_boolean(cls, value):
        if isinstance(value, bool):
            raise ValueError("protocol version must be an integer, not a boolean")
        return value


class Locality(StrEnum):
    LOCAL_ONLY = "local_only"
    CLOUD_ALLOWED = "cloud_allowed"


class ErrorDetail(WireModel):
    code: Identifier
    message: Annotated[str, Field(max_length=500)]
    retryable: StrictBool = False
    trace_id: UUID


class ErrorResponse(WireModel):
    error: ErrorDetail


class EventEnvelope(WireModel):
    event_id: UUID
    event_type: Identifier
    occurred_at: AwareDatetime
    aggregate_id: UUID
    aggregate_version: Positive
    trace_id: UUID
    data: dict[str, object] = Field(default_factory=dict)


class JobScope(WireModel):
    farm_id: UUID
    principal_id: UUID
    workspace_id: UUID
    task_id: UUID
    parent_task_id: UUID | None = None
    authorization_version: Positive
    resource_grant_ids: list[UUID] = Field(default_factory=list, max_length=100)
    locality: Locality = Locality.LOCAL_ONLY
    remaining_budget_id: UUID
    audience: Identifier
    attempt_id: UUID
    fencing_token: Positive
    expires_at: AwareDatetime


class CapabilityDefinition(WireModel):
    capability_id: Identifier
    revision: Positive
    display_name: Label
    description: Annotated[str, Field(max_length=500)]
    icon: Identifier
    input_modalities: list[Literal["text", "image", "audio", "artifact"]] = Field(min_length=1)
    output_modalities: list[Literal["text", "image", "audio", "geometry", "artifact"]] = Field(min_length=1)
    required_features: list[Identifier] = Field(default_factory=list)
    permitted_tool_categories: list[Identifier] = Field(default_factory=list)
    quality_suite: Identifier
    deadline_seconds: Annotated[StrictInt, Field(ge=1, le=7200)] = 300
    cloud_eligible: StrictBool = False
    enabled: StrictBool = True


class CapabilityAvailability(WireModel):
    schema_version: Literal[2] = 2
    capability_id: Identifier
    assignment_state: Literal["unassigned", "assigned", "disabled"]
    local_state: Literal["unavailable", "warming", "ready", "busy", "offline", "failed"]
    local_deployment_ids: list[UUID] = Field(default_factory=list)
    external_target_ids: list[UUID] = Field(default_factory=list)
    cloud_configured: StrictBool = False
    cloud_allowed_for_caller: StrictBool = False
    effective_state: Literal["unavailable", "warming", "ready", "busy", "cloud_available"]
    reason: Identifier | None = None
    available_actions: list[Identifier] = Field(default_factory=list)


class ResourceEnvelope(WireModel):
    ram_bytes: Nonnegative
    vram_bytes: Nonnegative
    disk_bytes: Nonnegative
    cpu_millicores: Nonnegative
    generation_slots: Annotated[StrictInt, Field(ge=0, le=64)] = 0


class PackageReference(WireModel):
    package_id: Identifier
    digest: Digest
    size_bytes: Positive
    signer_id: Identifier


class RecipeDependency(WireModel):
    dependency_id: Identifier
    package: PackageReference
    depends_on: list[Identifier] = Field(default_factory=list, max_length=30)


class ServiceRecipe(WireModel):
    recipe_id: Identifier
    revision: Positive
    digest: Digest
    platforms: list[Literal["windows_amd64", "linux_amd64", "darwin_amd64", "darwin_arm64", "linux_arm64"]] = Field(min_length=1)
    capabilities: list[Identifier] = Field(default_factory=list)
    dependencies: list[RecipeDependency] = Field(min_length=1, max_length=30)
    entrypoint_id: Literal["llama_cpp", "diffusers", "whisper_cpp", "kokoro_onnx", "geometry", "toolbox", "knowledge", "storage_gateway"]
    minimum_node_protocol: Literal[1] = 1
    isolation: Literal["native_unprivileged", "linux_container"]
    settings_schema: dict[str, object]
    readiness_probe: Identifier
    rollback: Literal["compatible", "restore_required"]

    @model_validator(mode="after")
    def dependency_graph(self):
        graph = {dep.dependency_id: dep.depends_on for dep in self.dependencies}
        if len(graph) != len(self.dependencies):
            raise ValueError("duplicate recipe dependency")
        seen, active = set(), set()

        def visit(name):
            if name not in graph:
                raise ValueError("missing recipe dependency")
            if name in active:
                raise ValueError("cyclic recipe dependency")
            if name in seen:
                return
            active.add(name)
            for other in graph[name]:
                visit(other)
            active.remove(name)
            seen.add(name)

        for name in graph:
            visit(name)
        if self.settings_schema.get("type") != "object" or self.settings_schema.get("additionalProperties") is not False:
            raise ValueError("recipe settings require a closed object schema")
        return self


class ServicePlan(WireModel):
    service_instance_id: UUID
    recipe_id: Identifier
    recipe_digest: Digest
    package_digests: list[Digest] = Field(min_length=1, max_length=30)
    model_digests: list[Digest] = Field(default_factory=list, max_length=100)
    capability_ids: list[Identifier] = Field(default_factory=list, max_length=30)
    settings: dict[str, object] = Field(default_factory=dict)
    secret_reference_ids: list[UUID] = Field(default_factory=list, max_length=20)
    reservations: ResourceEnvelope
    pinned: StrictBool = True


class NodePlan(WireModel):
    farm_id: UUID
    node_id: UUID
    controller_generation: Positive
    node_epoch: Positive
    expected_revision: Nonnegative
    desired_revision: Positive
    services: list[ServicePlan] = Field(default_factory=list, max_length=30)
    drain_policy: Literal["finish_active", "cancel_active"] = "finish_active"
    expires_at: AwareDatetime

    @model_validator(mode="after")
    def revision_and_instances(self):
        if self.desired_revision != self.expected_revision + 1:
            raise ValueError("desired revision must follow expected revision")
        ids = [service.service_instance_id for service in self.services]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate service instance")
        return self


class ServiceObservation(WireModel):
    service_instance_id: UUID
    desired_revision: Positive
    observed_revision: Nonnegative
    state: Literal["unassigned", "planning", "downloading", "installing", "configuring", "starting", "warming", "ready", "degraded", "draining", "stopped", "failed"]
    reason: Identifier | None = None
    completed_bytes: Nonnegative = 0
    total_bytes: Nonnegative | None = None
    observed_at: AwareDatetime


class EnrollmentPending(WireModel):
    attempt_id: UUID
    node_id: UUID
    nonce: Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{43}$")]
    public_key_fingerprint: Digest
    display_name: Label
    protocol_version: Literal[1] = 1


class EnrollmentEnvelope(WireModel):
    farm_id: UUID
    node_id: UUID
    attempt_id: UUID
    nonce: Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{43}$")]
    public_key_fingerprint: Digest
    farm_ca_pem: Annotated[str, Field(min_length=100, max_length=16384)]
    control_origin: Annotated[str, Field(pattern=r"^https://[^/?#@]+$", max_length=300)]
    enrollment_token: Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{43}$")]
    expires_at: AwareDatetime


class Heartbeat(WireModel):
    node_id: UUID
    farm_id: UUID
    node_epoch: Positive
    controller_generation: Positive
    sequence: Positive
    observed_plan_revision: Nonnegative
    active_attempt_ids: list[UUID] = Field(default_factory=list, max_length=64)
    services: list[ServiceObservation] = Field(default_factory=list, max_length=30)


class WorkerCommand(WireModel):
    command_id: UUID
    node_id: UUID
    node_epoch: Positive
    operation: Literal["reconcile_plan", "stage", "load", "drain", "unload", "cancel_attempt"]
    reference_id: UUID
    reference_digest: Digest
    expires_at: AwareDatetime


class ProviderBootstrap(WireModel):
    schema_version: Literal[2] = 2
    id: UUID
    path: Literal["local_head", "joined_member", "openai", "existing_service"]
    readiness: Literal["unconfigured", "configured", "inference_verified", "admin_agent_ready", "failed"]
    node_id: UUID | None = None
    deployment_id: UUID | None = None
    provider_configuration_id: UUID | None = None
    probe_evidence_id: UUID | None = None
    reason: Identifier | None = None
    revision: Positive


class ProviderProbeRequest(WireModel):
    expected_revision: Positive
    maximum_cost_minor: Nonnegative = 0
    paid_probe_grant_id: UUID | None = None


class ExternalProviderConnection(WireModel):
    id: UUID
    farm_id: UUID
    name: Label
    base_url: Annotated[str, Field(min_length=1, max_length=2048)]
    protocol: Literal["openai_compatible"] = "openai_compatible"
    management: Literal["external"] = "external"
    locality_assurance: Literal["operator_declared_local"] = "operator_declared_local"
    credential_configured: StrictBool = False


class InferenceTarget(WireModel):
    id: UUID
    connection_id: UUID
    resource_pool_id: UUID
    model_id: Annotated[str, Field(min_length=1, max_length=200)]
    state: Literal["configured", "ready", "failed", "disabled"]
    features: list[Identifier] = Field(default_factory=list, max_length=30)
    probed_at: AwareDatetime | None = None
    verified_until: AwareDatetime | None = None
    revision: Positive


class CapabilityBinding(WireModel):
    capability_id: Identifier
    target_id: UUID
    priority: Annotated[StrictInt, Field(ge=0, le=100)] = 0


class ProviderResourcePool(WireModel):
    id: UUID
    name: Label
    generation_slots: Literal[1] = 1
    busy: StrictBool
    execution_state: Literal["idle", "running", "unknown"]


class SecureInputReceipt(WireModel):
    receipt_id: UUID
    run_id: UUID
    resource_id: UUID
    form: Literal["provider_credential", "nas_connector", "pairing", "model_license"]
    status: Literal["awaiting_input", "validated", "failed", "expired"]
    expires_at: AwareDatetime


class AdminIntent(WireModel):
    action: Literal["assign_capability", "configure_service", "drain_node", "resume_node", "retry_service"]
    target_node_ids: list[UUID] = Field(min_length=1, max_length=30)
    capability_id: Identifier | None = None
    approved_recipe_id: Identifier | None = None
    settings: dict[str, object] = Field(default_factory=dict)


class RevisionPrecondition(WireModel):
    resource_id: UUID
    expected_revision: Nonnegative


class AdminChangeSet(WireModel):
    id: UUID
    farm_id: UUID
    principal_id: UUID
    run_id: UUID
    intent: AdminIntent
    change_hash: Digest
    node_plans: list[NodePlan] = Field(default_factory=list, max_length=30)
    preconditions: list[RevisionPrecondition] = Field(min_length=1, max_length=100)
    download_bytes: Nonnegative
    disruption: Annotated[str, Field(max_length=500)]
    expires_at: AwareDatetime


class AdminApplyRequest(WireModel):
    change_hash: Digest
    expected_revision: Positive


class AdminExecutionGrant(WireModel):
    """Server-held record, never a model tool argument or public response."""
    id: UUID
    farm_id: UUID
    principal_id: UUID
    run_id: UUID
    change_hash: Digest | None = None
    target_node_ids: list[UUID] = Field(min_length=1, max_length=30)
    actions: list[Identifier] = Field(min_length=1, max_length=30)
    maximum_download_bytes: Nonnegative
    authorization_version: Positive
    expires_at: AwareDatetime
    revoked_at: AwareDatetime | None = None


class AdminOperation(WireModel):
    id: UUID
    change_id: UUID
    state: Literal["accepted", "running", "waiting_node", "completed", "partially_completed", "failed", "cancelled"]
    revision: Positive
    completed_service_ids: list[UUID] = Field(default_factory=list)
    reason: Identifier | None = None
    deadline: AwareDatetime


class ArtifactMetadata(WireModel):
    id: UUID
    farm_id: UUID
    owner_id: UUID
    workspace_id: UUID
    source_task_id: UUID
    digest: Digest
    content_type: Annotated[str, Field(max_length=100)]
    size_bytes: Positive
    locality: Locality = Locality.LOCAL_ONLY
    source_artifact_ids: list[UUID] = Field(default_factory=list, max_length=100)


class GeometryRequest(WireModel):
    prompt: Annotated[str, Field(min_length=1, max_length=4000)] | None = None
    input_image_id: UUID | None = None
    output_format: Literal["glb"] = "glb"
    units: Literal["meters"] = "meters"
    up_axis: Literal["Y"] = "Y"
    maximum_triangles: Annotated[StrictInt, Field(ge=100, le=1_000_000)] = 100_000
    maximum_texture_size: Literal[512, 1024, 2048, 4096] = 2048

    @model_validator(mode="after")
    def has_input(self):
        if not self.prompt and not self.input_image_id:
            raise ValueError("geometry requires a supported text or image input")
        return self


class ImageOptions(WireModel):
    resolution: Literal['native', '2k', '4k'] = 'native'
    styles: list[Annotated[str, Field(min_length=1, max_length=100)]] | None = Field(default=None, max_length=8)
    guidance_scale: Annotated[float, Field(ge=1, le=30, allow_inf_nan=False)] | None = None
    sharpness: Annotated[float, Field(ge=0, le=30, allow_inf_nan=False)] | None = None


class ImageOptionsProfile(WireModel):
    resolutions: list[Literal['native', '2k', '4k']] = Field(default_factory=lambda: ['native'], min_length=1, max_length=3)
    styles: list[Annotated[str, Field(min_length=1, max_length=100)]] = Field(default_factory=list, max_length=512)
    default_styles: list[Annotated[str, Field(min_length=1, max_length=100)]] = Field(default_factory=list, max_length=8)
    guidance_scale: Annotated[float, Field(ge=1, le=30, allow_inf_nan=False)] | None = None
    sharpness: Annotated[float, Field(ge=0, le=30, allow_inf_nan=False)] | None = None


class ImageGeneration(WireModel):
    id: UUID
    model: Annotated[str, Field(min_length=1, max_length=200)]
    prompt: Annotated[str, Field(min_length=1, max_length=1000)]
    negative_prompt: Annotated[str, Field(max_length=1000)] = ''
    shape: Literal['square', 'landscape', 'portrait', 'widescreen', 'tall'] = 'square'
    steps: Literal[20, 30, 40, 60] = 20
    seed: Annotated[StrictInt, Field(ge=0, le=4294967295)]
    options: ImageOptions = Field(default_factory=ImageOptions)

    @field_validator('prompt')
    @classmethod
    def nonempty_prompt(cls, value):
        if not value.strip():
            raise ValueError('Describe the image you want to make.')
        return value


class ImageReceipt(WireModel):
    id: UUID
    model: Annotated[str, Field(min_length=1, max_length=200)]
    state: Literal['queued', 'running', 'completed', 'cancelled', 'failed', 'interrupted']
    progress: Annotated[StrictInt, Field(ge=0, le=60)]
    steps: Literal[20, 30, 40, 60]
    seed: Annotated[StrictInt, Field(ge=0, le=4294967295)]
    shape: Literal['square', 'landscape', 'portrait', 'widescreen', 'tall']
    width: Annotated[StrictInt, Field(ge=1, le=4096)]
    height: Annotated[StrictInt, Field(ge=1, le=4096)]
    reason: Annotated[str, Field(max_length=500)] | None = None
    sha256: Digest | None = None
    execution_released: StrictBool
    manifest_sha256: Digest
    cancel_requested: StrictBool


class ConversationImage(WireModel):
    request: ImageGeneration
    status: Literal['queued', 'running', 'completed', 'cancelled', 'failed', 'interrupted', 'deleted']
    progress: Annotated[StrictInt, Field(ge=0, le=60)]
    reason: Annotated[str, Field(max_length=500)] | None = None
    sha256: Digest | None = None
    planning_model: Annotated[str, Field(max_length=200)] | None = None
    source_image_id: UUID | None = None
    variation: StrictBool = False
    batch_index: Annotated[StrictInt, Field(ge=1, le=4)] = 1
    batch_count: Annotated[StrictInt, Field(ge=1, le=4)] = 1


class ImagePrompt(WireModel):
    prompt: Annotated[str, Field(min_length=1, max_length=1000)]
    negative_prompt: Annotated[str, Field(max_length=1000)] = ''
    shape: Literal['square', 'landscape', 'portrait'] = 'square'

    @model_validator(mode='after')
    def short_description(self):
        if not self.prompt.strip() or any(len(value.split()) > 60 for value in (self.prompt, self.negative_prompt)):
            raise ValueError('Image descriptions must fit the short local model profile.')
        return self


class ImagePromptPlan(WireModel):
    action: Literal['generate', 'clarify']
    prompt: Annotated[str, Field(min_length=1, max_length=1000)] | None = None
    negative_prompt: Annotated[str, Field(max_length=1000)] = ''
    shape: Literal['square', 'landscape', 'portrait'] = 'square'
    question: Annotated[str, Field(min_length=1, max_length=500)] | None = None
    images: list[ImagePrompt] | None = Field(default=None, min_length=1, max_length=4)

    @model_validator(mode='after')
    def coherent_proposal(self):
        if self.action == 'generate' and (bool(self.prompt and self.prompt.strip()) == bool(self.images) or self.question):
            raise ValueError('Generation needs either one prompt or an image list, and no question.')
        if self.images and (self.prompt is not None or self.negative_prompt or self.shape != 'square'):
            raise ValueError('Batch settings belong to each image.')
        if self.action == 'clarify' and (self.images is not None or self.prompt is not None or not self.question or not self.question.strip() or self.negative_prompt):
            raise ValueError('Clarification needs a question and no generation prompt.')
        if any(len(value.split()) > 60 for value in (self.prompt or '', self.negative_prompt)):
            raise ValueError('Image descriptions must fit the short local model profile.')
        return self

    def descriptions(self):
        return self.images or [ImagePrompt(prompt=self.prompt, negative_prompt=self.negative_prompt, shape=self.shape)]


class ImageProviderInfo(WireModel):
    protocol: Literal['hearth.image.v1']
    model: Annotated[str, Field(min_length=1, max_length=200)]
    model_revision: Annotated[str, Field(min_length=1, max_length=100)]
    manifest_sha256: Digest
    shapes: list[Literal['square', 'landscape', 'portrait', 'widescreen', 'tall']] = Field(min_length=1, max_length=5)
    steps: list[Literal[20, 30, 40, 60]] = Field(min_length=1, max_length=4)
    options: ImageOptionsProfile | None = None
    job_cancellation: StrictBool
    offline: StrictBool


class TranscriptionRequest(WireModel):
    id: UUID
    model: Annotated[str, Field(min_length=1, max_length=200)]
    audio_sha256: Digest


class TranscriptionReceipt(WireModel):
    id: UUID
    model: Annotated[str, Field(min_length=1, max_length=200)]
    audio_sha256: Digest
    state: Literal['queued', 'running', 'completed', 'cancelled', 'failed', 'interrupted']
    reason: Annotated[str, Field(max_length=500)] | None = None
    text: Annotated[str, Field(max_length=6000)] = ''
    language: Literal['en'] = 'en'
    execution_released: StrictBool
    manifest_sha256: Digest
    cancel_requested: StrictBool


class TranscriptionProviderInfo(WireModel):
    protocol: Literal['hearth.transcription.v1']
    model: Annotated[str, Field(min_length=1, max_length=200)]
    model_revision: Annotated[str, Field(min_length=1, max_length=100)]
    manifest_sha256: Digest
    languages: list[Literal['en']] = Field(min_length=1, max_length=1)
    maximum_seconds: Literal[120] = 120
    sample_rate: Literal[16000] = 16000
    job_cancellation: StrictBool
    offline: StrictBool


class SpeechGeneration(WireModel):
    id: UUID
    model: Annotated[str, Field(min_length=1, max_length=200)]
    voice: Annotated[str, Field(min_length=1, max_length=80)]
    input: Annotated[str, Field(min_length=1, max_length=6000)]


class SpeechReceipt(WireModel):
    id: UUID
    model: Annotated[str, Field(min_length=1, max_length=200)]
    voice: Annotated[str, Field(min_length=1, max_length=80)]
    input_sha256: Digest
    state: Literal['queued', 'running', 'completed', 'cancelled', 'failed', 'interrupted']
    reason: Annotated[str, Field(max_length=500)] | None = None
    sha256: Digest | None = None
    frames: Annotated[StrictInt, Field(ge=0, le=14400000)] = 0
    sample_rate: Literal[24000] = 24000
    execution_released: StrictBool
    manifest_sha256: Digest
    cancel_requested: StrictBool


class SpeechProviderInfo(WireModel):
    protocol: Literal['hearth.speech.v1']
    model: Annotated[str, Field(min_length=1, max_length=200)]
    model_revision: Annotated[str, Field(min_length=1, max_length=100)]
    manifest_sha256: Digest
    voices: list[Annotated[str, Field(min_length=1, max_length=80)]] = Field(min_length=1, max_length=100)
    default_voice: Annotated[str, Field(min_length=1, max_length=80)]
    maximum_characters: Literal[6000] = 6000
    sample_rate: Literal[24000] = 24000
    job_cancellation: StrictBool
    offline: StrictBool


class CloudAuthorization(WireModel):
    provider_enabled: StrictBool
    capability_allowed: StrictBool
    user_opt_in: StrictBool
    workspace_allowed: StrictBool
    price_known: StrictBool
    farm_remaining_minor: Nonnegative
    user_remaining_minor: Nonnegative
    requested_reservation_minor: Positive
    input_localities: list[Locality] = Field(min_length=1, max_length=1000)


CONTRACTS = {
    name: value for name, value in list(globals().items())
    if isinstance(value, type) and issubclass(value, WireModel) and value is not WireModel
}


def utc_now() -> datetime:
    from datetime import UTC
    return datetime.now(UTC)
