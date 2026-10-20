package manager

import (
	"context"
	"errors"
	"strings"
	"sync"
	"syscall"
	"time"
	"unsafe"

	"golang.org/x/sys/windows"
)

// Every child is assigned while suspended. Closing the job kills the full tree,
// including on supervisor failure. No PID guessing or process-name killing.
type Windows struct {
	mu    sync.Mutex
	jobs  map[string]windows.Handle
	roots map[string][]windows.Handle
}

func verifyRunning(s Service) error {
	if len(s.Processes) == 0 {
		return VerifyFiles(s)
	}
	return nil
}
func platformDriver() (Driver, func(), error) {
	d := &Windows{jobs: map[string]windows.Handle{}, roots: map[string][]windows.Handle{}}
	return d, func() {
		d.mu.Lock()
		defer d.mu.Unlock()
		for _, j := range d.jobs {
			windows.CloseHandle(j)
		}
		for unit := range d.roots {
			d.closeRoots(unit)
		}
		d.jobs = map[string]windows.Handle{}
	}, nil
}
func (d *Windows) Start(ctx context.Context, s Service) error {
	d.mu.Lock()
	defer d.mu.Unlock()
	if err := ctx.Err(); err != nil {
		return err
	}
	if err := validateProcesses(s); err != nil {
		return err
	}
	if err := VerifyFiles(s); err != nil {
		return err
	}
	if _, ok := d.jobs[s.Unit]; ok {
		return errors.New("job already exists")
	}
	j, err := windows.CreateJobObject(nil, nil)
	if err != nil {
		return err
	}
	limits := windows.JOBOBJECT_EXTENDED_LIMIT_INFORMATION{}
	limits.BasicLimitInformation.LimitFlags = windows.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
	_, err = windows.SetInformationJobObject(j, windows.JobObjectExtendedLimitInformation, uintptr(unsafe.Pointer(&limits)), uint32(unsafe.Sizeof(limits)))
	if err != nil {
		windows.CloseHandle(j)
		return err
	}
	// Keep the handle on failures until Stop confirms all children have exited.
	d.jobs[s.Unit] = j
	for _, p := range s.Processes {
		if err = ctx.Err(); err != nil {
			windows.TerminateJobObject(j, 1)
			return err
		}
		app, _ := windows.UTF16PtrFromString(p.Executable)
		dir, _ := windows.UTF16PtrFromString(p.Directory)
		args := []string{syscall.EscapeArg(p.Executable)}
		for _, a := range p.Arguments {
			args = append(args, syscall.EscapeArg(a))
		}
		command, _ := windows.UTF16PtrFromString(strings.Join(args, " "))
		si := windows.StartupInfo{Cb: uint32(unsafe.Sizeof(windows.StartupInfo{}))}
		pi := windows.ProcessInformation{}
		err = windows.CreateProcess(app, command, nil, nil, false, windows.CREATE_SUSPENDED|windows.CREATE_NO_WINDOW, nil, dir, &si, &pi)
		if err != nil {
			windows.TerminateJobObject(j, 1)
			return err
		}
		err = windows.AssignProcessToJobObject(j, pi.Process)
		if err == nil {
			_, err = windows.ResumeThread(pi.Thread)
		}
		if err != nil {
			windows.TerminateProcess(pi.Process, 1)
			windows.TerminateJobObject(j, 1)
		}
		windows.CloseHandle(pi.Thread)
		if err != nil {
			windows.CloseHandle(pi.Process)
			return err
		}
		d.roots[s.Unit] = append(d.roots[s.Unit], pi.Process)
	}
	return nil
}
func (d *Windows) closeRoots(unit string) {
	for _, process := range d.roots[unit] {
		windows.CloseHandle(process)
	}
	delete(d.roots, unit)
}
func active(j windows.Handle) (uint32, error) {
	var info struct {
		TotalUserTime, TotalKernelTime, ThisPeriodTotalUserTime, ThisPeriodTotalKernelTime int64
		TotalPageFaultCount, TotalProcesses, ActiveProcesses, TotalTerminatedProcesses     uint32
	}
	err := windows.QueryInformationJobObject(j, windows.JobObjectBasicAccountingInformation, uintptr(unsafe.Pointer(&info)), uint32(unsafe.Sizeof(info)), nil)
	return info.ActiveProcesses, err
}
func (d *Windows) Stop(ctx context.Context, s Service) error {
	d.mu.Lock()
	defer d.mu.Unlock()
	j, ok := d.jobs[s.Unit]
	if !ok {
		return nil
	}
	if err := windows.TerminateJobObject(j, 0); err != nil {
		return err
	}
	deadline := time.NewTimer(15 * time.Second)
	defer deadline.Stop()
	for {
		n, err := active(j)
		if err != nil {
			return err
		}
		if n == 0 {
			d.closeRoots(s.Unit)
			windows.CloseHandle(j)
			delete(d.jobs, s.Unit)
			return nil
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-deadline.C:
			return errors.New("process tree did not stop")
		case <-time.After(50 * time.Millisecond):
		}
	}
}
func (d *Windows) Stopped(_ context.Context, s Service) bool {
	d.mu.Lock()
	defer d.mu.Unlock()
	j, ok := d.jobs[s.Unit]
	if !ok {
		return true
	}
	n, err := active(j)
	if err == nil && n == 0 {
		d.closeRoots(s.Unit)
		windows.CloseHandle(j)
		delete(d.jobs, s.Unit)
		return true
	}
	return false
}
func (d *Windows) Healthy(ctx context.Context, s Service) bool {
	if d.Stopped(ctx, s) {
		return false
	}
	d.mu.Lock()
	alive := len(d.roots[s.Unit]) == len(s.Processes)
	for _, process := range d.roots[s.Unit] {
		status, err := windows.WaitForSingleObject(process, 0)
		if err != nil || status != uint32(windows.WAIT_TIMEOUT) {
			alive = false
		}
	}
	d.mu.Unlock()
	if !alive {
		return false
	}
	return serviceHealth(ctx, s)
}
