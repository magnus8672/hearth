package contracts

import (
	"encoding/json"
	"os"
	"testing"
)

func TestSharedFixtures(t *testing.T) {
	data, err := os.ReadFile("../../../tests/fixtures/contracts.json")
	if err != nil {
		t.Fatal(err)
	}
	var fixtures []struct {
		Name     string          `json:"name"`
		Contract string          `json:"contract"`
		Valid    bool            `json:"valid"`
		Payload  json.RawMessage `json:"payload"`
	}
	if err := json.Unmarshal(data, &fixtures); err != nil {
		t.Fatal(err)
	}
	for _, fixture := range fixtures {
		t.Run(fixture.Name, func(t *testing.T) {
			err := Validate(fixture.Contract, fixture.Payload)
			if (err == nil) != fixture.Valid {
				t.Fatalf("valid=%v wanted=%v: %v", err == nil, fixture.Valid, err)
			}
		})
	}
}
