//go:build windows

package host

import (
	"syscall"
	"unsafe"
)

func Accelerator() (string, bool, string) {
	dll := syscall.NewLazyDLL("WinHvPlatform.dll")
	procedure := dll.NewProc("WHvGetCapability")
	if err := procedure.Find(); err != nil {
		return "whpx", false, "Windows Hypervisor Platform is unavailable"
	}
	var present, written uint32
	result, _, _ := procedure.Call(0, uintptr(unsafe.Pointer(&present)), 4, uintptr(unsafe.Pointer(&written)))
	if result != 0 || present != 1 {
		return "whpx", false, "Hardware virtualization or Windows Hypervisor Platform is disabled"
	}
	return "whpx", true, "WHPX capability probe succeeded; appliance boot qualification is separate"
}
