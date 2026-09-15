package main

import (
	"crypto/tls"
	"crypto/x509"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestConnectorBoundary(t *testing.T) {
	calls := 0
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls++
		if r.Header.Get("Authorization") != "Bearer local-key" || r.Header.Get("Cookie") != "" || (r.URL.Path != "/v1/models" && r.URL.Path != "/api/v1/models") {
			t.Error("unexpected forwarded request")
		}
		w.Header().Set("Set-Cookie", "leak=1")
		w.Header().Set("Content-Type", "application/json")
		io.WriteString(w, `{"data":[]}`)
	}))
	defer upstream.Close()
	c := config{Listen: "127.0.0.1:1240", PublicHost: "192.168.1.12", Upstream: upstream.URL}
	h, err := handler(c, "controller-key", "local-key")
	if err != nil {
		t.Fatal(err)
	}
	for _, test := range []struct {
		method, path, host, token, origin, remote string
		status                                    int
	}{
		{"GET", "/v1/models", "192.168.1.12:1240", "controller-key", "", "192.168.1.10:5555", 200},
		{"GET", "/api/v1/models", "192.168.1.12:1240", "controller-key", "", "192.168.1.10:5555", 200},
		{"POST", "/api/v1/models", "192.168.1.12:1240", "controller-key", "", "192.168.1.10:5555", 404},
		{"POST", "/api/v1/models/load", "192.168.1.12:1240", "controller-key", "", "192.168.1.10:5555", 404},
		{"POST", "/api/v1/models/unload", "192.168.1.12:1240", "controller-key", "", "192.168.1.10:5555", 404},
		{"POST", "/api/v1/models/download", "192.168.1.12:1240", "controller-key", "", "192.168.1.10:5555", 404},
		{"GET", "/v1/models", "192.168.1.12:1240", "wrong", "", "192.168.1.10:5555", 401},
		{"GET", "/v1/models", "evil.example:1240", "controller-key", "", "192.168.1.10:5555", 403},
		{"GET", "/v1/models", "192.168.1.12:1240", "controller-key", "https://example.com", "192.168.1.10:5555", 403},
		{"GET", "/v1/models", "192.168.1.12:1240", "controller-key", "", "8.8.8.8:5555", 403},
		{"GET", "/admin", "192.168.1.12:1240", "controller-key", "", "192.168.1.10:5555", 404},
		{"GET", "/v1/models?url=http://example.com", "192.168.1.12:1240", "controller-key", "", "192.168.1.10:5555", 404},
		{"POST", "/v1/models", "192.168.1.12:1240", "controller-key", "", "192.168.1.10:5555", 404},
	} {
		r := httptest.NewRequest(test.method, "https://"+test.host+test.path, nil)
		r.RemoteAddr = test.remote
		r.Header.Set("Authorization", "Bearer "+test.token)
		r.Header.Set("Origin", test.origin)
		r.Header.Set("Cookie", "must-not-forward=1")
		w := httptest.NewRecorder()
		h.ServeHTTP(w, r)
		if w.Code != test.status {
			t.Fatalf("%s %s: got %d want %d", test.method, test.path, w.Code, test.status)
		}
		if w.Header().Get("Set-Cookie") != "" {
			t.Fatal("upstream cookie leaked")
		}
	}
	if calls != 2 {
		t.Fatalf("unexpected upstream operations: %d", calls)
	}
	r := httptest.NewRequest("POST", "https://192.168.1.12:1240/v1/chat/completions", strings.NewReader(strings.Repeat("x", (8<<20)+1)))
	r.RemoteAddr = "192.168.1.10:5555"
	r.Header.Set("Authorization", "Bearer controller-key")
	r.ContentLength = -1
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if w.Code != 413 || calls != 2 {
		t.Fatal("oversized chunked request reached upstream")
	}
}

func TestConnectorTLSIdentity(t *testing.T) {
	dir := filepath.Join(t.TempDir(), "private")
	c := config{Listen: "127.0.0.1:1240", PublicHost: "127.0.0.1", Upstream: "http://127.0.0.1:1234"}
	if err := initialize(dir, c); err != nil {
		t.Fatal(err)
	}
	before, _ := os.ReadFile(filepath.Join(dir, "controller.key"))
	if err := initialize(dir, c); err == nil {
		t.Fatal("identity overwritten")
	}
	after, _ := os.ReadFile(filepath.Join(dir, "controller.key"))
	if string(before) != string(after) {
		t.Fatal("key changed")
	}
	cert, err := tls.LoadX509KeyPair(filepath.Join(dir, "server.pem"), filepath.Join(dir, "server-key.pem"))
	if err != nil || len(cert.Certificate) != 1 {
		t.Fatal("invalid TLS identity")
	}
	if _, err := os.Stat(filepath.Join(dir, "ca-key.pem")); !os.IsNotExist(err) {
		t.Fatal("CA signing key should not persist")
	}
	for _, upstream := range []string{"http://192.168.1.10:1234", "https://127.0.0.1:1234", "http://localhost:1234", "http://127.0.0.1:8444", "http://127.0.0.1:1234/admin"} {
		c.Upstream = upstream
		if _, err := validate(c); err == nil {
			t.Fatalf("accepted unsafe upstream %s", upstream)
		}
	}
}

func TestRealTLSRequestsRequireThisCAAndHostname(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/event-stream")
		io.WriteString(w, "data: {\"choices\":[]}\n\n")
	}))
	defer upstream.Close()
	dir := filepath.Join(t.TempDir(), "private")
	c := config{Listen: "127.0.0.1:1240", PublicHost: "127.0.0.1", Upstream: upstream.URL}
	if err := initialize(dir, c); err != nil {
		t.Fatal(err)
	}
	token, err := secret(filepath.Join(dir, "controller.key"))
	if err != nil {
		t.Fatal(err)
	}
	h, err := handler(c, token, "")
	if err != nil {
		t.Fatal(err)
	}
	pair, err := tls.LoadX509KeyPair(filepath.Join(dir, "server.pem"), filepath.Join(dir, "server-key.pem"))
	if err != nil {
		t.Fatal(err)
	}
	server := httptest.NewUnstartedServer(h)
	server.TLS = &tls.Config{Certificates: []tls.Certificate{pair}, MinVersion: tls.VersionTLS12}
	server.StartTLS()
	defer server.Close()
	root, _ := os.ReadFile(filepath.Join(dir, "provider-ca.pem"))
	trust := x509.NewCertPool()
	if !trust.AppendCertsFromPEM(root) {
		t.Fatal("CA import failed")
	}
	for _, check := range []struct {
		trust    *x509.CertPool
		name     string
		succeeds bool
	}{
		{trust, "127.0.0.1", true}, {x509.NewCertPool(), "127.0.0.1", false}, {trust, "wrong.home", false},
	} {
		transport := &http.Transport{TLSClientConfig: &tls.Config{RootCAs: check.trust, ServerName: check.name, MinVersion: tls.VersionTLS12}}
		client := &http.Client{Transport: transport}
		request, _ := http.NewRequest("POST", server.URL+"/v1/chat/completions", strings.NewReader(`{"model":"fixture"}`))
		request.Host = "127.0.0.1:1240"
		request.Header.Set("Authorization", "Bearer "+token)
		response, err := client.Do(request)
		if check.succeeds {
			if err != nil {
				t.Fatal(err)
			}
			body, _ := io.ReadAll(response.Body)
			response.Body.Close()
			if response.StatusCode != 200 || !strings.Contains(string(body), "data:") {
				t.Fatal("TLS proxy did not stream")
			}
		} else if err == nil {
			response.Body.Close()
			t.Fatal("incorrect CA or hostname accepted")
		}
		transport.CloseIdleConnections()
	}
}
