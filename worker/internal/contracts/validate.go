package contracts

import (
	"bytes"
	"embed"
	"encoding/json"
	"fmt"
	"sync"

	"github.com/santhosh-tekuri/jsonschema/v6"
)

//go:embed schema/hearth.json
var schemaFiles embed.FS

var compileMu sync.Mutex
var compiled = map[string]*jsonschema.Schema{}

func Validate(name string, data []byte) error {
	if len(data) > 1<<20 {
		return fmt.Errorf("contract body exceeds limit")
	}
	compileMu.Lock()
	schema, found := compiled[name]
	if !found {
		raw, err := schemaFiles.ReadFile("schema/hearth.json")
		if err != nil {
			compileMu.Unlock()
			return err
		}
		document, err := jsonschema.UnmarshalJSON(bytes.NewReader(raw))
		if err != nil {
			compileMu.Unlock()
			return err
		}
		compiler := jsonschema.NewCompiler()
		compiler.DefaultDraft(jsonschema.Draft2020)
		if err := compiler.AddResource("https://hearth.invalid/contracts/v1", document); err != nil {
			compileMu.Unlock()
			return err
		}
		schema, err = compiler.Compile("https://hearth.invalid/contracts/v1#/$defs/" + name)
		if err != nil {
			compileMu.Unlock()
			return err
		}
		compiled[name] = schema
	}
	compileMu.Unlock()
	value, err := jsonschema.UnmarshalJSON(bytes.NewReader(data))
	if err != nil {
		return err
	}
	return schema.Validate(value)
}

func Decode(name string, data []byte, destination any) error {
	if err := Validate(name, data); err != nil {
		return err
	}
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.DisallowUnknownFields()
	return decoder.Decode(destination)
}
