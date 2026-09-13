// Package supplychain verifies signed bytes before they can become executable plans.
package supplychain

import (
	"crypto/ed25519"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"strings"

	jose "github.com/go-jose/go-jose/v4"
)

type ed25519Verifier struct{ key ed25519.PublicKey }

// go-jose owns JWS parsing and the signing input. Go's crypto package performs
// the standard Ed25519 operation under the RFC 9864 fully specified identifier.
func (v ed25519Verifier) VerifyPayload(payload, signature []byte, algorithm jose.SignatureAlgorithm) error {
	if algorithm != "Ed25519" || !ed25519.Verify(v.key, payload, signature) {
		return fmt.Errorf("signature verification failed")
	}
	return nil
}

func VerifyDocument(compact string, trusted map[string]ed25519.PublicKey, revoked map[string]bool, contentType string) ([]byte, error) {
	if contentType != "application/hearth.recipe+json" && contentType != "application/hearth.package+json" && contentType != "application/hearth.node-plan+json" {
		return nil, fmt.Errorf("unsupported signed content type")
	}
	if len(compact) > 175000 || strings.Count(compact, ".") != 2 {
		return nil, fmt.Errorf("invalid signed document")
	}
	segment := strings.SplitN(compact, ".", 2)[0]
	if len(segment) > 1024 {
		return nil, fmt.Errorf("oversized signature header")
	}
	headerBytes, err := base64.RawURLEncoding.DecodeString(segment)
	if err != nil {
		return nil, err
	}
	var header map[string]string
	if err = json.Unmarshal(headerBytes, &header); err != nil {
		return nil, err
	}
	if len(header) != 3 || header["alg"] != "Ed25519" || header["typ"] != contentType {
		return nil, fmt.Errorf("unexpected signature header")
	}
	key, found := trusted[header["kid"]]
	if !found || revoked[header["kid"]] || len(key) != ed25519.PublicKeySize {
		return nil, fmt.Errorf("untrusted signer")
	}
	document, err := jose.ParseSigned(compact, []jose.SignatureAlgorithm{"Ed25519"})
	if err != nil {
		return nil, err
	}
	return document.Verify(ed25519Verifier{key: key})
}
