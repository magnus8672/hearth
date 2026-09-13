# Hearth implementation guidance

Read `DEVELOPMENT.md` and `docs/implementation/BUILD_STATUS.md` before changing the application. The numbered design documents, phase plans and original brand package are the product baseline. Their snapshot is in `docs/plan/`; preserve the original inputs and keep implementation decisions in `docs/adr/` and `docs/implementation/`.

Use the fixed architecture: Python control plane, PostgreSQL, native Go workers, and separate React admin/user bundles sharing the supplied brand assets. The Python appliance helper is a development tool, not a substitute for the product installer or member management protocol.

Keep desired state, observed state and verified readiness separate. A running process, loaded model name, heartbeat, UI specimen or passing fixture does not prove product readiness. Default to local-only content and zero cloud budget. Do not make paid provider calls without a concrete authorized budget.

Security boundaries are product behavior. Never turn headers, model output, tool output, hostnames or retrieved content into authority. Models do not receive admin credentials or execution grants. Verify signed packages and recipes before activation; general shell execution is not a worker command.

Keep secrets and runtime artifacts in ignored `.hearth/`, never in source, URLs, command arguments or committed evidence. Use the pinned SSH maintenance channel only for the isolated developer appliance. Keep database migration and application roles separate; tests must not bypass RLS to make application access pass.

After contract changes, run `uv run --group knowledge python scripts/dev.py generate`. Relevant checks are `uv run --group knowledge python scripts/dev.py check`, `uv run --group appliance python scripts/development_stack.py qualify-linux`, and `HEARTH_LIVE_UI=1 pnpm test:e2e`. The Linux Switchyard build must retain its pinned source and CPU baseline because the public AVX2 wheel does not run in the qualified WHPX guest.

Update the implementation ledger with observed results and explicit missing work. Keep all 61 release gates at their real status. Required local 3D and the P8 portions of A12 must not disappear from scope.
