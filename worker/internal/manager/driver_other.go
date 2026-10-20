//go:build !windows

package manager

func platformDriver() (Driver, func(), error) { return Systemd{}, func() {}, nil }
func verifyRunning(s Service) error           { return VerifyFiles(s) }
