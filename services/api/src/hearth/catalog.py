from hearth.contracts import CapabilityDefinition

_ENTRIES = [
    ("chat.general", "Conversation", "chat", ["text"], ["text"]),
    ("reason.plan", "Planning", "reasoning", ["text"], ["text"]),
    ("code.explain", "Code explanation", "code", ["text", "artifact"], ["text"]),
    ("code.implement", "Coding", "code", ["text", "artifact"], ["text", "artifact"]),
    ("write.compose", "Writing", "writing", ["text"], ["text"]),
    ("text.summarize", "Summarization", "writing", ["text"], ["text"]),
    ("data.extract", "Data extraction", "embeddings", ["text", "artifact"], ["text", "artifact"]),
    ("vision.describe", "Vision", "vision", ["image", "text"], ["text"]),
    ("image.generate", "Image generation", "image", ["text", "image"], ["image"]),
    ("geometry.generate", "3D generation", "cube", ["text", "image"], ["geometry"]),
    ("audio.transcribe", "Transcription", "microphone", ["audio"], ["text"]),
    ("audio.speak", "Speech", "speech", ["text"], ["audio"]),
    ("memory.retrieve", "Memory retrieval", "knowledge", ["text"], ["text"]),
    ("memory.index", "Memory indexing", "knowledge", ["artifact"], ["artifact"]),
]

CAPABILITIES = tuple(CapabilityDefinition(
    capability_id=id, revision=1, display_name=label, description=f"{label} through an approved Hearth deployment.",
    icon=icon, input_modalities=inputs, output_modalities=outputs, quality_suite=id + ".v1",
    deadline_seconds=900 if outputs[0] in {"image", "geometry", "audio"} else 300,
    cloud_eligible=not id.startswith("memory.") and id != "geometry.generate",
) for id, label, icon, inputs, outputs in _ENTRIES)
