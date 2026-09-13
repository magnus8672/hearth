package main

import (
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestSetupProofOriginAndOneUse(t *testing.T) {
	calls := 0
	s := &setupServer{origin: "http://127.0.0.1:8470", secret: strings.Repeat("a", 43), expires: time.Now().Add(time.Minute), run: func(body []byte) ([]byte, error) { calls++; return []byte(`{"owner_created":true}`), nil }}
	request := func(host, origin, proof, body string) int {
		r := httptest.NewRequest("POST", "http://"+host+"/api", strings.NewReader(body))
		r.Host = host
		r.Header.Set("Origin", origin)
		r.Header.Set("Authorization", "Bearer "+proof)
		w := httptest.NewRecorder()
		s.ServeHTTP(w, r)
		return w.Code
	}
	for _, code := range []int{
		request("evil.example:8470", s.origin, s.secret, `{"action":"owner"}`),
		request("127.0.0.1:8470", "http://evil.example", s.secret, `{"action":"owner"}`),
		request("127.0.0.1:8470", s.origin, "wrong", `{"action":"owner"}`),
	} {
		if code != 403 {
			t.Fatal("Host, Origin or local proof bypass")
		}
	}
	if calls != 0 {
		t.Fatal("unauthorized helper execution")
	}
	if request("127.0.0.1:8470", s.origin, s.secret, `{"action":"shell","payload":{}}`) != 400 {
		t.Fatal("arbitrary helper operation accepted")
	}
	if request("127.0.0.1:8470", s.origin, s.secret, `{"action":"owner","payload":{}}`) != 200 {
		t.Fatal("authorized bootstrap failed")
	}
	if request("127.0.0.1:8470", s.origin, s.secret, `{"action":"owner","payload":{}}`) != 410 || calls != 1 {
		t.Fatal("bootstrap replay accepted")
	}
}
