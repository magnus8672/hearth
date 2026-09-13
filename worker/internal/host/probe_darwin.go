//go:build darwin

package host

import (
	"os/exec"
	"strings"
)

func Accelerator() (string, bool, string) {
	output, err := exec.Command("/usr/sbin/sysctl", "-n", "kern.hv_support").Output()
	if err != nil || strings.TrimSpace(string(output)) != "1" {
		return "hvf", false, "Hypervisor.framework support was not confirmed"
	}
	return "hvf", true, "Host hypervisor support is present; appliance boot qualification is separate"
}
