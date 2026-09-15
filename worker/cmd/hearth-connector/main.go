// hearth-connector exposes one fixed loopback inference service over authenticated TLS.
// It does not install models, run commands, enroll a worker or grant model authority.
package main

import (
	"context"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/sha256"
	"crypto/subtle"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/hex"
	"encoding/json"
	"encoding/pem"
	"errors"
	"flag"
	"fmt"
	"io"
	"log"
	"math/big"
	"net"
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"time"
)

type config struct {
	Listen          string `json:"listen"`
	PublicHost      string `json:"public_host"`
	Upstream        string `json:"upstream"`
	UpstreamKeyFile string `json:"upstream_key_file,omitempty"`
}

func privateIP(ip net.IP) bool {
	return ip != nil && (ip.IsLoopback() || ip.IsPrivate()) && !ip.IsUnspecified()
}

func validate(c config) (*url.URL, error) {
	u, err := url.Parse(c.Upstream)
	if err != nil || u.Scheme != "http" || u.User != nil || u.RawQuery != "" || u.Fragment != "" || (u.Path != "" && u.Path != "/" && u.Path != "/v1") || !net.ParseIP(u.Hostname()).IsLoopback() || u.Port() == "" {
		return nil, errors.New("upstream must be a fixed http://127.0.0.1:PORT or http://[::1]:PORT address")
	}
	for _, p := range []string{"8080", "8085", "8443", "8444", "8445"} {
		if u.Port() == p {
			return nil, errors.New("upstream cannot be a hearth application or identity port")
		}
	}
	host, port, err := net.SplitHostPort(c.Listen)
	if err != nil || port == "0" || port == "" || (host != "0.0.0.0" && host != "::" && !privateIP(net.ParseIP(host))) {
		return nil, errors.New("listen must be a private or wildcard IP and an explicit port")
	}
	if strings.ContainsAny(c.PublicHost, "/\\@?#% \r\n\t") || c.PublicHost == "" {
		return nil, errors.New("public-host must be a private IP or local DNS name")
	}
	if ip := net.ParseIP(c.PublicHost); ip != nil && !privateIP(ip) {
		return nil, errors.New("public-host must be private or loopback")
	}
	if u.Port() == port {
		return nil, errors.New("connector and upstream must use different ports")
	}
	u.Path = ""
	return u, nil
}

func secret(path string) (string, error) {
	b, err := os.ReadFile(path)
	if err != nil {
		return "", errors.New("cannot read a configured key file")
	}
	v := strings.TrimSpace(string(b))
	if len(v) < 1 || len(v) > 2048 {
		return "", errors.New("invalid key file length")
	}
	for _, c := range v {
		if c < 33 || c > 126 {
			return "", errors.New("key file must contain one printable token")
		}
	}
	return v, nil
}

var imageJob = regexp.MustCompile(`^/v1/image-jobs/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}(/image|/cancel)?$`)

func allowed(method, path string) bool {
	switch path {
	case "/v1/models", "/v1/image-provider", "/api/v1/models":
		return method == "GET"
	case "/v1/chat/completions", "/v1/embeddings", "/v1/audio/speech", "/v1/audio/transcriptions", "/v1/image-jobs":
		return method == "POST"
	}
	return imageJob.MatchString(path) && ((strings.HasSuffix(path, "/cancel") && method == "POST") || (!strings.HasSuffix(path, "/cancel") && method == "GET"))
}

func handler(c config, token, upstreamKey string) (http.Handler, error) {
	upstream, err := validate(c)
	if err != nil {
		return nil, err
	}
	_, port, _ := net.SplitHostPort(c.Listen)
	expectedHost := net.JoinHostPort(c.PublicHost, port)
	expectedToken := sha256.Sum256([]byte("Bearer " + token))
	proxy := &httputil.ReverseProxy{
		Rewrite: func(p *httputil.ProxyRequest) {
			p.SetURL(upstream)
			p.Out.Host = upstream.Host
			// Forward only protocol headers. Controller credentials and cookies never
			// reach the local service. A separate optional upstream key is file-backed.
			p.Out.Header = make(http.Header)
			p.Out.Header.Set("Content-Type", p.In.Header.Get("Content-Type"))
			p.Out.Header.Set("Accept", p.In.Header.Get("Accept"))
			p.Out.Header.Set("Accept-Encoding", "identity")
			if upstreamKey != "" {
				p.Out.Header.Set("Authorization", "Bearer "+upstreamKey)
			}
		},
		Transport:     &http.Transport{Proxy: nil, DialContext: (&net.Dialer{Timeout: 5 * time.Second}).DialContext, ResponseHeaderTimeout: 30 * time.Second, DisableCompression: true, MaxIdleConnsPerHost: 4},
		FlushInterval: -1,
		ModifyResponse: func(r *http.Response) error {
			if r.StatusCode >= 300 && r.StatusCode < 400 {
				return errors.New("redirect rejected")
			}
			contentType := r.Header.Get("Content-Type")
			r.Header = make(http.Header)
			r.Header.Set("Content-Type", contentType)
			r.Header.Set("Cache-Control", "no-store")
			r.Header.Set("X-Content-Type-Options", "nosniff")
			return nil
		},
		ErrorHandler: func(w http.ResponseWriter, _ *http.Request, _ error) {
			http.Error(w, "local provider unavailable or protocol rejected", http.StatusBadGateway)
		},
	}
	slots := make(chan struct{}, 16)
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Cache-Control", "no-store")
		remote, _, _ := net.SplitHostPort(r.RemoteAddr)
		if r.TLS == nil || !privateIP(net.ParseIP(remote)) || r.Host != expectedHost || r.Header.Get("Origin") != "" {
			http.Error(w, "connection not permitted", http.StatusForbidden)
			return
		}
		offered := sha256.Sum256([]byte(r.Header.Get("Authorization")))
		if subtle.ConstantTimeCompare(expectedToken[:], offered[:]) != 1 {
			http.Error(w, "authentication required", http.StatusUnauthorized)
			return
		}
		if r.URL.RawQuery != "" || r.URL.EscapedPath() != r.URL.Path || !allowed(r.Method, r.URL.Path) {
			http.Error(w, "unsupported provider operation", http.StatusNotFound)
			return
		}
		select {
		case slots <- struct{}{}:
			defer func() { <-slots }()
		default:
			http.Error(w, "connector busy", http.StatusServiceUnavailable)
			return
		}
		if r.ContentLength > 8<<20 {
			http.Error(w, "request too large", http.StatusRequestEntityTooLarge)
			return
		}
		// Buffer bounded requests before forwarding: an oversized chunked request
		// must not start a partially authorized upstream operation.
		data, err := io.ReadAll(http.MaxBytesReader(w, r.Body, 8<<20))
		if err != nil {
			http.Error(w, "request too large or interrupted", http.StatusRequestEntityTooLarge)
			return
		}
		r.Body = io.NopCloser(strings.NewReader(string(data)))
		r.ContentLength = int64(len(data))
		ctx, cancel := context.WithTimeout(r.Context(), 20*time.Minute)
		defer cancel()
		proxy.ServeHTTP(w, r.WithContext(ctx))
	}), nil
}

func writeNew(path string, data []byte) error {
	f, err := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
	if err != nil {
		return err
	}
	defer f.Close()
	_, err = f.Write(data)
	return err
}

func initialize(dir string, c config) error {
	if _, err := validate(c); err != nil {
		return err
	}
	if err := os.MkdirAll(dir, 0700); err != nil {
		return err
	}
	// Never overwrite an existing identity, even following an incomplete setup.
	entries, err := os.ReadDir(dir)
	if err != nil {
		return err
	}
	if len(entries) != 0 {
		return errors.New("connector directory must be empty; existing identity is preserved")
	}
	caKey, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		return err
	}
	serial := func() *big.Int { n, _ := rand.Int(rand.Reader, new(big.Int).Lsh(big.NewInt(1), 128)); return n }
	now := time.Now()
	ca := &x509.Certificate{SerialNumber: serial(), Subject: pkix.Name{CommonName: "hearth local provider CA"}, NotBefore: now.Add(-5 * time.Minute), NotAfter: now.AddDate(1, 0, 0), IsCA: true, BasicConstraintsValid: true, KeyUsage: x509.KeyUsageCertSign | x509.KeyUsageCRLSign}
	caDER, err := x509.CreateCertificate(rand.Reader, ca, ca, &caKey.PublicKey, caKey)
	if err != nil {
		return err
	}
	serverKey, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		return err
	}
	server := &x509.Certificate{SerialNumber: serial(), Subject: pkix.Name{CommonName: "hearth provider connector"}, NotBefore: now.Add(-5 * time.Minute), NotAfter: ca.NotAfter, ExtKeyUsage: []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth}, KeyUsage: x509.KeyUsageDigitalSignature}
	if ip := net.ParseIP(c.PublicHost); ip != nil {
		server.IPAddresses = []net.IP{ip}
	} else {
		server.DNSNames = []string{c.PublicHost}
	}
	der, err := x509.CreateCertificate(rand.Reader, server, ca, &serverKey.PublicKey, caKey)
	if err != nil {
		return err
	}
	keyDER, err := x509.MarshalPKCS8PrivateKey(serverKey)
	if err != nil {
		return err
	}
	token := make([]byte, 32)
	if _, err := rand.Read(token); err != nil {
		return err
	}
	configBytes, _ := json.MarshalIndent(c, "", "  ")
	files := map[string][]byte{
		"connector.json":  configBytes,
		"provider-ca.pem": pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: caDER}),
		"server.pem":      pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: der}),
		"server-key.pem":  pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: keyDER}),
		"controller.key":  []byte(hex.EncodeToString(token)),
	}
	for name, data := range files {
		if err := writeNew(filepath.Join(dir, name), data); err != nil {
			return err
		}
	}
	fingerprint := sha256.Sum256(caDER)
	_, port, _ := net.SplitHostPort(c.Listen)
	fmt.Printf("Connector initialized. Address: https://%s/v1\nCA SHA-256: %x\nImport provider-ca.pem in hearth Providers and use controller.key as its API key.\nKeep server-key.pem and controller.key private. The CA signing key was not retained.\n", net.JoinHostPort(c.PublicHost, port), fingerprint)
	return nil
}

func main() {
	dir := flag.String("dir", "", "private connector state directory (required)")
	init := flag.Bool("init", false, "initialize a new identity; refuses an existing directory")
	publicHost := flag.String("public-host", "", "private LAN IP or local DNS name in the server certificate")
	listen := flag.String("listen", "127.0.0.1:1240", "listen IP:port; choose the LAN interface explicitly")
	upstream := flag.String("upstream", "http://127.0.0.1:1234", "fixed local model service")
	upstreamKey := flag.String("upstream-key-file", "", "optional absolute path to the local service key")
	flag.Parse()
	log.SetFlags(0)
	if *dir == "" {
		log.Fatal("--dir is required; use a private directory in your user profile")
	}
	if *init {
		if err := initialize(*dir, config{*listen, *publicHost, *upstream, *upstreamKey}); err != nil {
			log.Fatal(err)
		}
		return
	}
	raw, err := os.ReadFile(filepath.Join(*dir, "connector.json"))
	if err != nil {
		log.Fatal("Cannot read connector.json; initialize this connector first.")
	}
	var c config
	decoder := json.NewDecoder(strings.NewReader(string(raw)))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&c); err != nil {
		log.Fatal("Invalid connector configuration.")
	}
	token, err := secret(filepath.Join(*dir, "controller.key"))
	if err != nil {
		log.Fatal(err)
	}
	if len(token) != 64 {
		log.Fatal("Invalid controller key.")
	}
	upstreamToken := ""
	if c.UpstreamKeyFile != "" {
		upstreamToken, err = secret(c.UpstreamKeyFile)
		if err != nil {
			log.Fatal(err)
		}
	}
	h, err := handler(c, token, upstreamToken)
	if err != nil {
		log.Fatal(err)
	}
	server := &http.Server{Addr: c.Listen, Handler: h, TLSConfig: &tls.Config{MinVersion: tls.VersionTLS12}, ReadHeaderTimeout: 5 * time.Second, ReadTimeout: 30 * time.Second, IdleTimeout: 30 * time.Second, MaxHeaderBytes: 16384, ErrorLog: log.New(io.Discard, "", 0)}
	log.Printf("hearth connector listening on %s; one fixed loopback provider; authenticated TLS only", c.Listen)
	if err := server.ListenAndServeTLS(filepath.Join(*dir, "server.pem"), filepath.Join(*dir, "server-key.pem")); err != nil {
		log.Fatal("Connector stopped: listener or certificate unavailable.")
	}
}
