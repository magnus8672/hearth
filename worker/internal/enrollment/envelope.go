package enrollment

import (
	"encoding/base64"
	"encoding/json"
	"errors"
	"strings"
	"time"

	jose "github.com/go-jose/go-jose/v4"
	"hearth.local/worker/internal/contracts"
)

func Encrypt(payload []byte, secret []byte) (string, error) {
	if len(secret) != 32 {
		return "", errors.New("pairing secret must be 256 bits")
	}
	if err := contracts.Validate("EnrollmentEnvelope", payload); err != nil {
		return "", err
	}
	encrypter, err := jose.NewEncrypter(jose.A256GCM, jose.Recipient{Algorithm: jose.DIRECT, Key: secret}, nil)
	if err != nil {
		return "", err
	}
	encrypted, err := encrypter.Encrypt(payload)
	if err != nil {
		return "", err
	}
	return encrypted.CompactSerialize()
}

func Decrypt(ciphertext string, secret []byte) ([]byte, error) {
	if len(secret) != 32 || len(ciphertext) > 32768 {
		return nil, errors.New("invalid envelope")
	}
	parts := strings.Split(ciphertext, ".")
	if len(parts) != 5 {
		return nil, errors.New("invalid compact JWE")
	}
	headerBytes, err := base64.RawURLEncoding.DecodeString(parts[0])
	if err != nil {
		return nil, err
	}
	var header map[string]any
	if err = json.Unmarshal(headerBytes, &header); err != nil {
		return nil, err
	}
	if len(header) != 2 || header["alg"] != "dir" || header["enc"] != "A256GCM" {
		return nil, errors.New("unsupported security header")
	}
	object, err := jose.ParseEncrypted(ciphertext, []jose.KeyAlgorithm{jose.DIRECT}, []jose.ContentEncryption{jose.A256GCM})
	if err != nil {
		return nil, err
	}
	payload, err := object.Decrypt(secret)
	if err != nil {
		return nil, errors.New("enrollment authentication failed")
	}
	if err = contracts.Validate("EnrollmentEnvelope", payload); err != nil {
		return nil, err
	}
	return payload, nil
}

func ValidateBindings(envelope contracts.EnrollmentEnvelope, pending contracts.EnrollmentPending, origin string, now time.Time) error {
	expiry, err := time.Parse(time.RFC3339Nano, envelope.ExpiresAt)
	if err != nil {
		return err
	}
	if envelope.NodeId != pending.NodeId || envelope.AttemptId != pending.AttemptId ||
		envelope.Nonce != pending.Nonce || envelope.PublicKeyFingerprint != pending.PublicKeyFingerprint ||
		envelope.ControlOrigin != origin || !expiry.After(now) || expiry.Sub(now) > 10*time.Minute {
		return errors.New("enrollment binding mismatch")
	}
	return nil
}
