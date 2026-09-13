// Local developer setup surface. This is not the signed production installer.
package main

import (
	"bytes"
	"crypto/rand"
	"crypto/subtle"
	"embed"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"sync"
	"time"
)

//go:embed setup.html setup.js setup.css hearth-lockup-light.svg
var assets embed.FS

type setupServer struct {
	origin   string
	secret   string
	expires  time.Time
	mutex    sync.Mutex
	finished bool
	run      func([]byte) ([]byte, error)
}

func (s *setupServer) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Cache-Control", "no-store")
	w.Header().Set("Referrer-Policy", "no-referrer")
	w.Header().Set("X-Content-Type-Options", "nosniff")
	w.Header().Set("Content-Security-Policy", "default-src 'none'; style-src 'self'; script-src 'self'; connect-src 'self' https://localhost:8443 https://localhost:8444 https://localhost:8445; img-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
	if "http://"+r.Host != s.origin || time.Now().After(s.expires) {
		http.Error(w, "Setup is unavailable.", 403)
		return
	}
	if r.URL.Path == "/api" {
		if r.Method != "POST" || r.Header.Get("Origin") != s.origin || subtle.ConstantTimeCompare([]byte(r.Header.Get("Authorization")), []byte("Bearer "+s.secret)) != 1 {
			http.Error(w, "This setup request is not authorized.", 403)
			return
		}
		s.mutex.Lock()
		defer s.mutex.Unlock()
		if s.finished {
			http.Error(w, "Owner setup is already complete.", 410)
			return
		}
		body, err := io.ReadAll(http.MaxBytesReader(w, r.Body, 16384))
		if err != nil {
			http.Error(w, "Setup request is too large.", 413)
			return
		}
		var input struct {
			Action  string          `json:"action"`
			Payload json.RawMessage `json:"payload"`
		}
		decoder := json.NewDecoder(bytes.NewReader(body))
		decoder.DisallowUnknownFields()
		if decoder.Decode(&input) != nil || (input.Action != "status" && input.Action != "trust" && input.Action != "owner" && input.Action != "certificate") {
			http.Error(w, "Unsupported setup action.", 400)
			return
		}
		output, err := s.run(body)
		w.Header().Set("Content-Type", "application/json")
		if err != nil {
			w.WriteHeader(400)
		} else if input.Action == "owner" {
			s.finished = true
		}
		_, _ = w.Write(output)
		return
	}
	if r.Method != "GET" {
		http.Error(w, "Method not allowed.", 405)
		return
	}
	file := ""
	switch r.URL.Path {
	case "/":
		file = "setup.html"
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
	case "/setup.js":
		file = "setup.js"
		w.Header().Set("Content-Type", "text/javascript; charset=utf-8")
	case "/hearth-lockup-light.svg":
		file = "hearth-lockup-light.svg"
		w.Header().Set("Content-Type", "image/svg+xml")
	case "/setup.css":
		file = "setup.css"
		w.Header().Set("Content-Type", "text/css; charset=utf-8")
	default:
		http.NotFound(w, r)
		return
	}
	content, _ := assets.ReadFile(file)
	_, _ = w.Write(content)
}

func main() {
	executable, err := os.Executable()
	if err != nil {
		panic(err)
	}
	root := filepath.Clean(filepath.Join(filepath.Dir(executable), "../.."))
	python := filepath.Join(root, ".venv", "Scripts", "python.exe")
	if _, err := os.Stat(python); err != nil {
		fmt.Println("Start setup with Start-Hearth.ps1 from the development checkout.")
		os.Exit(1)
	}
	listener, err := net.Listen("tcp4", "127.0.0.1:0")
	if err != nil {
		panic(err)
	}
	secret := make([]byte, 32)
	if _, err := rand.Read(secret); err != nil {
		panic(err)
	}
	server := &setupServer{origin: "http://" + listener.Addr().String(), secret: base64.RawURLEncoding.EncodeToString(secret), expires: time.Now().Add(30 * time.Minute)}
	server.run = func(body []byte) ([]byte, error) {
		command := exec.Command(python, filepath.Join(root, "scripts", "setup_helper.py"))
		command.Dir = root
		command.Stdin = bytes.NewReader(body)
		output, err := command.Output()
		if !json.Valid(output) {
			return []byte(`{"error":"The local setup service is not ready. Restart Start-Hearth.ps1."}`), fmt.Errorf("helper unavailable")
		}
		return output, err
	}
	fmt.Println("Hearth local setup is open in your browser. Keep this window open until setup completes.")
	fmt.Println("This setup session expires in 30 minutes. Close this window to end it.")
	go func() { time.Sleep(300 * time.Millisecond); openBrowser(server.origin + "/#" + server.secret) }()
	httpServer := &http.Server{Handler: server, ReadHeaderTimeout: 5 * time.Second, ReadTimeout: 20 * time.Second, WriteTimeout: 90 * time.Second, IdleTimeout: 30 * time.Second, MaxHeaderBytes: 8192}
	if err := httpServer.Serve(listener); err != nil {
		fmt.Println("The setup window has closed.")
	}
}
