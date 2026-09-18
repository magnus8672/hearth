package manager

import (
	"context"
	"crypto/sha256"
	"fmt"
	"os"
	"path/filepath"
	"testing"
	"time"
)

type fakeDriver struct {
	live          map[string]bool
	healthy       bool
	stopFails     bool
	starts, stops int
}

func (d *fakeDriver) Start(_ context.Context, s Service) error {
	d.live[s.Unit] = true
	d.starts++
	return nil
}
func (d *fakeDriver) Stop(_ context.Context, s Service) error {
	d.stops++
	if !d.stopFails {
		d.live[s.Unit] = false
	}
	return nil
}
func (d *fakeDriver) Stopped(_ context.Context, s Service) bool { return !d.live[s.Unit] }
func (d *fakeDriver) Healthy(context.Context, Service) bool     { return d.healthy }

func fixture(t *testing.T) (*Controller, *fakeDriver) {
	t.Helper()
	path := filepath.Join(t.TempDir(), "entrypoint")
	data := []byte("approved executable")
	if err := os.WriteFile(path, data, 0600); err != nil {
		t.Fatal(err)
	}
	sum := fmt.Sprintf("%x", sha256.Sum256(data))
	files := map[string]string{path: sum}
	d := &fakeDriver{live: map[string]bool{"fooocus.service": true}, healthy: true}
	c := New(Recipe{Services: map[string]Service{"fooocus": {Unit: "fooocus.service", Files: files}, "trellis": {Unit: "trellis.service", Files: files}}}, "digest", d)
	return c, d
}
func TestSharedServiceSwitchAndLease(t *testing.T) {
	c, d := fixture(t)
	desired := "trellis"
	if err := c.Accept(Command{Revision: 1, DesiredService: &desired, LeaseSeconds: 15}); err != nil {
		t.Fatal(err)
	}
	c.Reconcile(context.Background())
	r := c.Snapshot()
	if r.State != "ready" || *r.ReadyService != "trellis" || d.starts != 1 || d.stops != 1 {
		t.Fatalf("switch did not drain and start: %+v", r)
	}
	c.Reconcile(context.Background())
	if d.starts != 1 {
		t.Fatal("restarted resident service")
	}
	c.expires = time.Now().Add(-time.Second)
	c.command.DesiredService = nil
	c.command.Revision++
	c.Reconcile(context.Background())
	if d.stops != 1 {
		t.Fatal("acted after lease expiry")
	}
}
func TestStopAcknowledgementBlocksReplacement(t *testing.T) {
	c, d := fixture(t)
	d.stopFails = true
	desired := "trellis"
	_ = c.Accept(Command{Revision: 1, DesiredService: &desired, LeaseSeconds: 15})
	c.Reconcile(context.Background())
	if c.Snapshot().Reason != "stop_failed" || d.starts != 0 {
		t.Fatal("started over unconfirmed GPU release")
	}
	d.stopFails = false
	c.Reconcile(context.Background())
	if d.starts != 0 {
		t.Fatal("retried failed command without fresh approval")
	}
	_ = c.Accept(Command{Revision: 2, DesiredService: &desired, LeaseSeconds: 15})
	c.Reconcile(context.Background())
	if d.starts != 1 {
		t.Fatal("approved retry failed")
	}
}
func TestManifestTamperingAndReadiness(t *testing.T) {
	c, d := fixture(t)
	desired := "fooocus"
	d.healthy = false
	_ = c.Accept(Command{Revision: 1, DesiredService: &desired, LeaseSeconds: 15})
	c.Reconcile(context.Background())
	if c.Snapshot().State == "ready" {
		t.Fatal("process mistaken for readiness")
	}
	for path := range c.recipe.Services["fooocus"].Files {
		_ = os.WriteFile(path, []byte("tampered"), 0600)
	}
	c.Reconcile(context.Background())
	if c.Snapshot().Reason != "recipe_mismatch" {
		t.Fatal("changed executable accepted")
	}
}
func TestRejectCommandsAndSingleInstance(t *testing.T) {
	c, _ := fixture(t)
	desired := "fooocus"
	_ = c.Accept(Command{Revision: 3, DesiredService: &desired, LeaseSeconds: 15})
	unknown := "shell"
	for _, command := range []Command{{Revision: 2, DesiredService: &desired, LeaseSeconds: 15}, {Revision: 4, DesiredService: &unknown, LeaseSeconds: 15}, {Revision: 3, LeaseSeconds: 15}, {Revision: 4, LeaseSeconds: 60}} {
		if c.Accept(command) == nil {
			t.Fatal("invalid command accepted")
		}
	}
	directory := t.TempDir()
	unlock, err := lock(directory)
	if err != nil {
		t.Fatal(err)
	}
	defer unlock()
	if release, err := lock(directory); err == nil {
		release()
		t.Fatal("duplicate worker accepted")
	}
}
