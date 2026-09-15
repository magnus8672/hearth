# P6: shared MCP toolbox

Dependency: P5. Outcome: the administrator assigns a toolbox role and agents execute authorized tools through it.

## Build

Package the toolbox and approved MCP servers as typed service recipes under [11](../../../plan/11-INSTALLATION-AND-CENTRAL-MANAGEMENT.md). Assignment from Hearth installs the isolated host and its dependencies; credentials and settings are supplied centrally with per-service scope. No local member shell or container configuration is part of onboarding. Unsupported isolation backends remain visibly unavailable.

1. Implement the deployable Linux toolbox service package, approved MCP server registry and per-server isolated processes/containers.
2. Support stdio and authenticated Streamable HTTP through a pinned official SDK. Validate protocol compatibility rather than assuming all servers implement the same current revision.
3. Build relevant-tool discovery, schema validation, user/workspace/task grants, credential isolation, egress policy, output size limits and artifact conversion.
4. Implement read/reversible-write/external-action classes, durable invocation IDs, standing grants and explicit approval UI where required. Resume the agent loop after tool results.
5. Add safe reference tools: scoped document read/search, repository inspection, and sandboxed test execution. Administrative APIs are not generally offered to models.

## Prove

E10, E17 and S06, S08, S10-S11. Two users invoke the same server with separate credentials/scopes. A malicious document asks for broader access and is ignored as an instruction. A changed tool schema is quarantined. Killing the toolbox mid-invocation produces a recoverable state; an uncertain external action is not blindly repeated.

Use a test connector that records side-effect operation IDs to prove retry behavior. Check that sandbox processes cannot access host home directories, raw NAS roots, controller secrets or container-management sockets.

## Exit gate

One real MCP server and one sandboxed execution tool operate through the designated node, with visible authorized activity and complete isolation evidence. Model text alone cannot approve an action.

Next: [P7](../../../plan/phases/P7-CONVERSATION-MEMORY.md).
