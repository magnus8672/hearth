// Development contract/interoperability probe. Secrets arrive on stdin only.
package main

import (
	"crypto/ed25519"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"os"

	"hearth.local/worker/internal/contracts"
	"hearth.local/worker/internal/enrollment"
	"hearth.local/worker/internal/supplychain"
)

type request struct {
	Action      string          `json:"action"`
	Contract    string          `json:"contract"`
	Payload     json.RawMessage `json:"payload"`
	Secret      string          `json:"secret"`
	Ciphertext  string          `json:"ciphertext"`
	PublicKey   string          `json:"public_key"`
	SignerID    string          `json:"signer_id"`
	ContentType string          `json:"content_type"`
	Revoked     bool            `json:"revoked"`
}

func main() {
	var input request
	decoder := json.NewDecoder(io.LimitReader(os.Stdin, (1<<20)+1))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&input); err != nil {
		fail(err)
	}
	var output any
	var err error
	switch input.Action {
	case "verify-signature":
		var key, payload []byte
		key, err = base64.RawURLEncoding.DecodeString(input.PublicKey)
		if err == nil {
			payload, err = supplychain.VerifyDocument(input.Ciphertext, map[string]ed25519.PublicKey{input.SignerID: key}, map[string]bool{input.SignerID: input.Revoked}, input.ContentType)
		}
		output = map[string]any{"valid": err == nil, "payload": base64.RawURLEncoding.EncodeToString(payload)}
		err = nil
	case "validate":
		err = contracts.Validate(input.Contract, input.Payload)
		output = map[string]bool{"valid": err == nil}
	case "encrypt", "decrypt":
		var key []byte
		key, err = base64.RawURLEncoding.DecodeString(input.Secret)
		if err != nil {
			fail(err)
		}
		if input.Action == "encrypt" {
			var ciphertext string
			ciphertext, err = enrollment.Encrypt(input.Payload, key)
			output = map[string]string{"ciphertext": ciphertext}
		} else {
			var payload []byte
			payload, err = enrollment.Decrypt(input.Ciphertext, key)
			output = json.RawMessage(payload)
		}
	default:
		err = fmt.Errorf("unknown probe action")
	}
	if err != nil {
		fail(err)
	}
	if err = json.NewEncoder(os.Stdout).Encode(output); err != nil {
		os.Exit(1)
	}
}

func fail(err error) {
	// Schema errors may contain fixture content. Probe output must never be used for production diagnostics.
	fmt.Fprintln(os.Stderr, err)
	os.Exit(1)
}
