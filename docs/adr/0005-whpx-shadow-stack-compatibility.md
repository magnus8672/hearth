# ADR 0005: Reference WHPX guest CPU compatibility

Status: development workaround; production virtualization qualification remains open.

During identity acceptance, the QEMU 11.1 WHPX guest panicked after about 29 minutes. PID 1 faulted in libc/systemd with page-fault error codes 0x44/0x46. The console evidence is preserved in `evidence/identity/2026-09-12/guest-panic.txt`. The verified panicked process was stopped, preserving its disk; PostgreSQL recovered on restart.

The selected guest CPU is an explicit x86-64-v2 baseline without qualified XSAVE state support. Nevertheless, `/proc/cpuinfo` advertised `user_shstk` and `ibt`. QEMU's [WHPX CPUID path](https://raw.githubusercontent.com/qemu/qemu/master/target/i386/whpx/whpx-all.c) substitutes the hypervisor's dynamic CET bits. This is consistent with the observed shadow-stack fault, but a full upstream root-cause investigation has not been completed.

A hash-verified QEMU 10.2 comparison failed with the UEFI firmware's MMIO operations. A BIOS boot succeeded but still exposed shadow-stack features outside the intended profile. The reference therefore retains the original pinned 11.1 package and UEFI configuration.

The isolated development guest now boots with `clearcpuid=519`, masking `X86_FEATURE_SHSTK` as defined by its Linux 6.8 headers. This makes userspace shadow-stack availability match the intended guest CPU baseline. The configuration is stored in `deploy/appliance/60-hearth-cpu.cfg` and `/etc/default/grub.d/60-hearth-cpu.cfg` in the guest. Windows security settings are unchanged. The guest remains hardware accelerated; no emulation fallback or broad mitigation switch is used.

The stack helper requires this profile before serving the test build. On a new guest, it installs the configuration and asks for a normal appliance stop/start before continuing. Removing the workaround requires a qualified virtualization/CPU combination, followed by real inference and sustained lifecycle tests. A short successful acceptance run is not long-term reliability evidence.

Do not ship this profile as a silently inherited production default. Production packaging must qualify a consistent CPU/XSAVE/CET contract and record the supported host/guest combinations. This compatibility finding keeps P0 and the relevant installer/recovery release gates open.
