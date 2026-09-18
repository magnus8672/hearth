// Package manager adopts approved services; it never accepts executable commands
// from the network. One instance owns one explicitly configured resource group.
package manager

import (
	"bytes"
	"context"
	"crypto/ed25519"
	"crypto/rand"
	"crypto/sha256"
	"crypto/tls"
	"crypto/x509"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strings"
	"sync"
	"time"

	"hearth.local/worker/internal/supplychain"
)

type Config struct {
	HeadURL        string `json:"head_url"`
	WorkerID       string `json:"worker_id"`
	TokenFile      string `json:"token_file"`
	CAFile         string `json:"ca_file"`
	RecipeFile     string `json:"recipe_file"`
	TrustFile      string `json:"trust_file"`
	StateDirectory string `json:"state_directory"`
}
type Service struct {
	Unit          string            `json:"unit"`
	Files         map[string]string `json:"files"`
	HealthURL     string            `json:"health_url"`
	HealthKeyFile string            `json:"health_key_file"`
	HealthField   string            `json:"health_field"`
	HealthValue   string            `json:"health_value"`
}
type Recipe struct {
	SchemaVersion int                `json:"schema_version"`
	WorkerID      string             `json:"worker_id"`
	Services      map[string]Service `json:"services"`
}
type Command struct {
	Revision       int64   `json:"revision"`
	DesiredService *string `json:"desired_service"`
	LeaseSeconds   int     `json:"lease_seconds"`
}
type Report struct {
	BootID           string  `json:"boot_id"`
	Sequence         int64   `json:"sequence"`
	RecipeDigest     string  `json:"recipe_digest"`
	ObservedRevision int64   `json:"observed_revision"`
	ReadyService     *string `json:"ready_service"`
	State            string  `json:"state"`
	Reason           string  `json:"reason"`
}
type Driver interface {
	Start(context.Context, Service) error
	Stop(context.Context, Service) error
	Stopped(context.Context, Service) bool
	Healthy(context.Context, Service) bool
}
type Controller struct {
	mu      sync.Mutex
	recipe  Recipe
	report  Report
	command Command
	expires time.Time
	driver  Driver
}

var identifier = regexp.MustCompile(`^[a-z][a-z0-9_-]{0,39}$`)
var uuid = regexp.MustCompile(`^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$`)
var digestPattern = regexp.MustCompile(`^[0-9a-f]{64}$`)
var unitPattern = regexp.MustCompile(`^[A-Za-z0-9_-]{1,80}\.service$`)

func decode(data []byte, value any) error {
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(value); err != nil {
		return err
	}
	if decoder.Decode(new(any)) != io.EOF {
		return errors.New("trailing JSON")
	}
	return nil
}

func read(path string, maximum int64) ([]byte, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	st, err := f.Stat()
	if err != nil || !st.Mode().IsRegular() || st.Size() > maximum {
		return nil, errors.New("invalid file")
	}
	data, err := io.ReadAll(io.LimitReader(f, maximum+1))
	if int64(len(data)) > maximum {
		return nil, errors.New("oversized file")
	}
	return data, err
}

func Load(path string) (Config, Recipe, string, error) {
	var config Config
	var recipe Recipe
	fail := func() (Config, Recipe, string, error) {
		return config, recipe, "", errors.New("invalid worker configuration or signed service recipe")
	}
	data, err := read(path, 16384)
	if err != nil || decode(data, &config) != nil {
		return fail()
	}
	endpoint, err := url.Parse(config.HeadURL)
	if err != nil || endpoint.Scheme != "https" || endpoint.Hostname() == "" || endpoint.User != nil || endpoint.Path != "" || endpoint.RawQuery != "" || endpoint.Fragment != "" || !uuid.MatchString(config.WorkerID) {
		return fail()
	}
	for _, p := range []string{config.TokenFile, config.CAFile, config.RecipeFile, config.TrustFile, config.StateDirectory} {
		if !filepath.IsAbs(p) || filepath.Clean(p) != p {
			return fail()
		}
	}
	trustedBytes, err := read(config.TrustFile, 16384)
	if err != nil {
		return fail()
	}
	var encoded map[string]string
	if decode(trustedBytes, &encoded) != nil {
		return fail()
	}
	trusted := map[string]ed25519.PublicKey{}
	for id, value := range encoded {
		b, err := base64.RawURLEncoding.DecodeString(value)
		if err != nil || len(b) != ed25519.PublicKeySize {
			return fail()
		}
		trusted[id] = b
	}
	signed, err := read(config.RecipeFile, 175000)
	if err != nil {
		return fail()
	}
	payload, err := supplychain.VerifyDocument(strings.TrimSpace(string(signed)), trusted, nil, "application/hearth.recipe+json")
	if err != nil || decode(payload, &recipe) != nil || recipe.WorkerID != config.WorkerID || recipe.SchemaVersion != 1 || len(recipe.Services) == 0 || len(recipe.Services) > 16 {
		return fail()
	}
	units := map[string]bool{}
	for id, service := range recipe.Services {
		u, err := url.Parse(service.HealthURL)
		if !identifier.MatchString(id) || !unitPattern.MatchString(service.Unit) || units[service.Unit] || err != nil || u.Scheme != "http" || u.Hostname() != "127.0.0.1" || u.Port() == "" || u.User != nil || u.RawQuery != "" || u.Fragment != "" || service.HealthField == "" || service.HealthValue == "" {
			return fail()
		}
		units[service.Unit] = true
		if len(service.Files) < 2 || len(service.Files) > 128 || !filepath.IsAbs(service.HealthKeyFile) {
			return fail()
		}
		if _, ok := service.Files["/etc/systemd/system/"+service.Unit]; !ok {
			return fail()
		}
		for path, sum := range service.Files {
			if !filepath.IsAbs(path) || filepath.Clean(path) != path || !digestPattern.MatchString(sum) {
				return fail()
			}
		}
	}
	hash := sha256.Sum256(payload)
	return config, recipe, hex.EncodeToString(hash[:]), nil
}

func New(recipe Recipe, digest string, driver Driver) *Controller {
	b := make([]byte, 16)
	if _, err := rand.Read(b); err != nil {
		panic("system randomness unavailable")
	}
	boot := fmt.Sprintf("%x-%x-%x-%x-%x", b[:4], b[4:6], b[6:8], b[8:10], b[10:])
	return &Controller{recipe: recipe, driver: driver, report: Report{BootID: boot, RecipeDigest: digest, State: "stopped"}}
}

func (c *Controller) Accept(command Command) error {
	c.mu.Lock()
	defer c.mu.Unlock()
	if command.Revision < c.command.Revision || command.Revision < 1 || command.LeaseSeconds < 1 || command.LeaseSeconds > 15 {
		return errors.New("invalid control lease")
	}
	if command.DesiredService != nil {
		if _, ok := c.recipe.Services[*command.DesiredService]; !ok {
			return errors.New("unapproved service")
		}
	}
	if command.Revision == c.command.Revision && !equalService(command.DesiredService, c.command.DesiredService) {
		return errors.New("changed command without revision")
	}
	c.command = command
	c.expires = time.Now().Add(time.Duration(command.LeaseSeconds) * time.Second)
	return nil
}
func equalService(a, b *string) bool { return a == nil && b == nil || a != nil && b != nil && *a == *b }
func (c *Controller) Snapshot() Report {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.report.Sequence++
	return c.report
}
func (c *Controller) set(command Command, state, reason string, ready *string) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.report.ObservedRevision = command.Revision
	c.report.State = state
	c.report.Reason = reason
	c.report.ReadyService = ready
}
func (c *Controller) current(command Command) bool {
	c.mu.Lock()
	defer c.mu.Unlock()
	return time.Now().Before(c.expires) && c.command.Revision == command.Revision
}

// Reconcile runs in one goroutine. Polling continues while systemd drains a
// service. A lost head lease permits observation, never a new lifecycle action.
func (c *Controller) Reconcile(ctx context.Context) {
	c.mu.Lock()
	command, report := c.command, c.report
	c.mu.Unlock()
	if !c.current(command) {
		return
	}
	if report.State == "failed" && report.ObservedRevision == command.Revision {
		return
	}
	for id, service := range c.recipe.Services {
		if command.DesiredService != nil && id == *command.DesiredService {
			continue
		}
		if !c.driver.Stopped(ctx, service) {
			c.set(command, "starting", "service_starting", nil)
			if !c.current(command) {
				return
			}
			if c.driver.Stop(ctx, service) != nil || !c.driver.Stopped(ctx, service) {
				c.set(command, "failed", "stop_failed", nil)
				return
			}
		}
	}
	if command.DesiredService == nil {
		c.set(command, "stopped", "", nil)
		return
	}
	service := c.recipe.Services[*command.DesiredService]
	if err := VerifyFiles(service); err != nil {
		c.set(command, "failed", "recipe_mismatch", nil)
		return
	}
	if c.driver.Stopped(ctx, service) {
		c.set(command, "starting", "service_starting", nil)
		if !c.current(command) {
			return
		}
		if c.driver.Start(ctx, service) != nil {
			c.set(command, "failed", "start_failed", nil)
			return
		}
	}
	if !c.driver.Healthy(ctx, service) {
		c.set(command, "starting", "service_not_ready", nil)
		return
	}
	c.set(command, "ready", "", command.DesiredService)
}

func VerifyFiles(service Service) error {
	for path, expected := range service.Files {
		data, err := read(path, 16<<20)
		if err != nil {
			return errors.New("approved service file unavailable")
		}
		sum := sha256.Sum256(data)
		if hex.EncodeToString(sum[:]) != expected {
			return errors.New("approved service file changed")
		}
	}
	return nil
}

type Systemd struct{}

func run(ctx context.Context, args ...string) ([]byte, error) {
	limited, cancel := context.WithTimeout(ctx, 45*time.Second)
	defer cancel()
	return exec.CommandContext(limited, "/usr/bin/systemctl", args...).Output()
}
func (Systemd) Start(ctx context.Context, s Service) error {
	if !approvedUnit(ctx, s) {
		return errors.New("systemd unit differs from approval")
	}
	_, err := run(ctx, "start", s.Unit)
	return err
}

func approvedUnit(ctx context.Context, s Service) bool {
	output, err := run(ctx, "show", "--property=FragmentPath", "--property=DropInPaths", "--property=NeedDaemonReload", s.Unit)
	if err != nil {
		return false
	}
	values := map[string]string{}
	for _, line := range strings.Split(string(output), "\n") {
		p := strings.SplitN(line, "=", 2)
		if len(p) == 2 {
			values[p[0]] = p[1]
		}
	}
	if values["FragmentPath"] != "/etc/systemd/system/"+s.Unit || values["NeedDaemonReload"] != "no" {
		return false
	}
	for _, path := range strings.Fields(values["DropInPaths"]) {
		if _, ok := s.Files[path]; !ok {
			return false
		}
	}
	return VerifyFiles(s) == nil
}
func (Systemd) Stop(ctx context.Context, s Service) error {
	if !approvedUnit(ctx, s) {
		return errors.New("systemd unit differs from approval")
	}
	_, err := run(ctx, "stop", s.Unit)
	return err
}
func (Systemd) Stopped(ctx context.Context, s Service) bool {
	output, err := run(ctx, "show", "--property=ActiveState", "--property=MainPID", "--property=ControlPID", "--property=ControlGroup", s.Unit)
	if err != nil {
		return false
	}
	values := map[string]string{}
	for _, line := range strings.Split(string(output), "\n") {
		p := strings.SplitN(line, "=", 2)
		if len(p) == 2 {
			values[p[0]] = p[1]
		}
	}
	if values["ActiveState"] != "inactive" && values["ActiveState"] != "failed" || values["MainPID"] != "0" || values["ControlPID"] != "0" {
		return false
	}
	group := values["ControlGroup"]
	if group == "" {
		return true
	}
	if !strings.HasPrefix(group, "/system.slice/") || strings.Contains(group, "..") {
		return false
	}
	events, err := read("/sys/fs/cgroup"+group+"/cgroup.events", 1024)
	return os.IsNotExist(err) || err == nil && strings.Contains(string(events), "populated 0\n")
}
func (Systemd) Healthy(ctx context.Context, s Service) bool {
	if !approvedUnit(ctx, s) {
		return false
	}
	key, err := read(s.HealthKeyFile, 4096)
	if err != nil {
		return false
	}
	req, err := http.NewRequestWithContext(ctx, "GET", s.HealthURL, nil)
	if err != nil {
		return false
	}
	req.Header.Set("Authorization", "Bearer "+strings.TrimSpace(string(key)))
	client := &http.Client{Timeout: 3 * time.Second, Transport: &http.Transport{Proxy: nil}, CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }}
	response, err := client.Do(req)
	if err != nil {
		return false
	}
	defer response.Body.Close()
	data, err := io.ReadAll(io.LimitReader(response.Body, 65537))
	if err != nil || len(data) > 65536 || response.StatusCode != 200 {
		return false
	}
	var fields map[string]any
	return json.Unmarshal(data, &fields) == nil && fields[s.HealthField] == s.HealthValue
}

func Run(ctx context.Context, path string) error {
	config, recipe, digest, err := Load(path)
	if err != nil {
		return err
	}
	unlock, err := lock(config.StateDirectory)
	if err != nil {
		return err
	}
	defer unlock()
	cert, err := read(config.CAFile, 32768)
	if err != nil {
		return errors.New("head CA unavailable")
	}
	roots := x509.NewCertPool()
	if !roots.AppendCertsFromPEM(cert) {
		return errors.New("head CA invalid")
	}
	token, err := read(config.TokenFile, 1024)
	if err != nil {
		return errors.New("worker credential unavailable")
	}
	secret := strings.TrimSpace(string(token))
	if !digestPattern.MatchString(secret) {
		return errors.New("worker credential invalid")
	}
	client := &http.Client{Timeout: 8 * time.Second, Transport: &http.Transport{Proxy: nil, TLSClientConfig: &tls.Config{MinVersion: tls.VersionTLS12, RootCAs: roots}}, CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }}
	controller := New(recipe, digest, Systemd{})
	workerDone := make(chan struct{})
	go func() {
		defer close(workerDone)
		ticker := time.NewTicker(time.Second)
		defer ticker.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				controller.Reconcile(ctx)
			}
		}
	}()
	defer func() { <-workerDone }()
	ticker := time.NewTicker(3 * time.Second)
	defer ticker.Stop()
	for {
		report := controller.Snapshot()
		body, _ := json.Marshal(report)
		req, err := http.NewRequestWithContext(ctx, "POST", config.HeadURL+"/api/v1/worker-control/"+config.WorkerID+"/poll", bytes.NewReader(body))
		if err != nil {
			return errors.New("invalid head request")
		}
		req.Header.Set("Authorization", "Bearer "+secret)
		req.Header.Set("Content-Type", "application/json")
		response, err := client.Do(req)
		if err == nil {
			data, readErr := io.ReadAll(io.LimitReader(response.Body, 8193))
			response.Body.Close()
			if readErr == nil && len(data) <= 8192 && response.StatusCode == 200 {
				var command Command
				if decode(data, &command) == nil {
					_ = controller.Accept(command)
				}
			}
		}
		// An atomic public status journal aids diagnosis; it contains no credentials.
		temp := filepath.Join(config.StateDirectory, "status.tmp")
		final := filepath.Join(config.StateDirectory, "status.json")
		if os.WriteFile(temp, body, 0600) == nil {
			_ = os.Rename(temp, final)
		}
		select {
		case <-ctx.Done():
			return nil
		case <-ticker.C:
		}
	}
}
