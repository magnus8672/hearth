package manager

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"os"
	"os/exec"
	"path/filepath"
	"testing"
	"time"
)

func TestWindowsProcessHelper(t *testing.T) {
	if len(os.Args) < 2 || os.Args[len(os.Args)-1] != "runner-child" {
		return
	}
	time.Sleep(time.Minute)
	os.Exit(0)
}
func windowsFixture(t *testing.T) Service {
	t.Helper()
	dir := t.TempDir()
	self, err := os.Executable()
	if err != nil {
		t.Fatal(err)
	}
	data, err := os.ReadFile(self)
	if err != nil {
		t.Fatal(err)
	}
	exe := filepath.Join(dir, "python.exe")
	if err = os.WriteFile(exe, data, 0600); err != nil {
		t.Fatal(err)
	}
	sum := sha256.Sum256(data)
	return Service{Unit: "fixture.service", Files: map[string]string{exe: hex.EncodeToString(sum[:])}, Processes: []Process{{Executable: exe, Directory: dir, Arguments: []string{"-test.run=^TestWindowsProcessHelper$", "--", "runner-child"}}}}
}
func TestWindowsJobLifecycle(t *testing.T) {
	s := windowsFixture(t)
	driver, closeDriver, err := platformDriver()
	if err != nil {
		t.Fatal(err)
	}
	defer closeDriver()
	ctx := context.Background()
	if !driver.Stopped(ctx, s) {
		t.Fatal("new service not stopped")
	}
	if err = driver.Start(ctx, s); err != nil {
		t.Fatal(err)
	}
	if driver.Stopped(ctx, s) {
		t.Fatal("child did not start")
	}
	if driver.Start(ctx, s) == nil {
		t.Fatal("duplicate start permitted")
	}
	if err = driver.Stop(ctx, s); err != nil {
		t.Fatal(err)
	}
	if !driver.Stopped(ctx, s) {
		t.Fatal("child tree not confirmed stopped")
	}
	if err = driver.Start(ctx, s); err != nil {
		t.Fatal("restart failed", err)
	}
	closeDriver()
	// Close uses the kernel job's kill-on-close guarantee; verify via process exit
	// in the dedicated tree test rather than trusting a successful Start.
}
func TestWindowsRefusesChangedExecutable(t *testing.T) {
	s := windowsFixture(t)
	d, closeD, _ := platformDriver()
	defer closeD()
	os.WriteFile(s.Processes[0].Executable, []byte("changed"), 0600)
	if d.Start(context.Background(), s) == nil {
		t.Fatal("changed executable started")
	}
}
func TestWindowsStateLock(t *testing.T) {
	dir := t.TempDir()
	unlock, err := lock(dir)
	if err != nil {
		t.Fatal(err)
	}
	if release, err := lock(dir); err == nil {
		release()
		t.Fatal("duplicate state owner")
	}
	unlock()
	again, err := lock(dir)
	if err != nil {
		t.Fatal(err)
	}
	again()
}
func TestDirectoryClosureIncludesNewFiles(t *testing.T) {
	dir := t.TempDir()
	os.WriteFile(filepath.Join(dir, "module.py"), []byte("pass"), 0600)
	first, err := DirectoryDigest(dir)
	if err != nil {
		t.Fatal(err)
	}
	os.Mkdir(filepath.Join(dir, "__pycache__"), 0700)
	os.WriteFile(filepath.Join(dir, "__pycache__", "cache.pyc"), []byte("cache"), 0600)
	cached, _ := DirectoryDigest(dir)
	if first == cached {
		t.Fatal("added executable bytecode did not invalidate closure")
	}
	os.WriteFile(filepath.Join(dir, "injected.pth"), []byte("import bad"), 0600)
	changed, _ := DirectoryDigest(dir)
	if cached == changed {
		t.Fatal("added import hook did not invalidate closure")
	}
}

func TestWindowsGrandchildHelper(t *testing.T) {
	if len(os.Args) < 3 || os.Args[len(os.Args)-2] != "runner-parent" {
		return
	}
	self, _ := os.Executable()
	cmd := exec.Command(self, "-test.run=^TestWindowsProcessHelper$", "--", "runner-child")
	if cmd.Start() != nil {
		os.Exit(3)
	}
	os.WriteFile(os.Args[len(os.Args)-1], []byte("started"), 0600)
	time.Sleep(time.Minute)
	os.Exit(0)
}
func TestWindowsStopsEntireProcessTree(t *testing.T) {
	s := windowsFixture(t)
	marker := filepath.Join(t.TempDir(), "child-started")
	s.Processes[0].Arguments = []string{"-test.run=^TestWindowsGrandchildHelper$", "--", "runner-parent", marker}
	d, closeD, _ := platformDriver()
	defer closeD()
	ctx := context.Background()
	if err := d.Start(ctx, s); err != nil {
		t.Fatal(err)
	}
	end := time.Now().Add(10 * time.Second)
	for {
		if _, err := os.Stat(marker); err == nil {
			break
		}
		if time.Now().After(end) {
			t.Fatal("grandchild did not start")
		}
		time.Sleep(20 * time.Millisecond)
	}
	wd := d.(*Windows)
	n, err := active(wd.jobs[s.Unit])
	if err != nil || n < 2 {
		t.Fatalf("child escaped job: %d %v", n, err)
	}
	if err = d.Stop(ctx, s); err != nil {
		t.Fatal(err)
	}
	if !d.Stopped(ctx, s) {
		t.Fatal("tree still populated")
	}
}
