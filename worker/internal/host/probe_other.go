//go:build !windows && !linux && !darwin

package host

func Accelerator() (string, bool, string) { return "none", false, "Unsupported host platform" }
