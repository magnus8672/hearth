//go:build linux

package host

import "os"

func Accelerator() (string, bool, string) {
	device, err := os.OpenFile("/dev/kvm", os.O_RDWR, 0)
	if err != nil {
		return "kvm", false, "The current account cannot access /dev/kvm"
	}
	device.Close()
	return "kvm", true, "KVM device is accessible; appliance boot qualification is separate"
}
