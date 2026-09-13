// Hearth's native host entry point. A read-only doctor never creates or joins a farm.
package main

import (
	"encoding/json"
	"fmt"
	"os"
	"runtime"

	"hearth.local/worker/internal/host"
)

func main() {
	if len(os.Args) != 2 {
		fmt.Fprintln(os.Stderr, "Usage: hearth-worker doctor | version")
		os.Exit(2)
	}
	switch os.Args[1] {
	case "version":
		fmt.Println("hearth-worker 0.1.0 protocol=1")
	case "doctor":
		name, available, reason := host.Accelerator()
		report := map[string]any{"schema_version": 1, "os": runtime.GOOS, "architecture": runtime.GOARCH,
			"logical_cpus": runtime.NumCPU(), "accelerator": name, "accelerator_available": available,
			"reason": reason, "farm_state": "not_inspected", "qualification": "development_probe"}
		encoder := json.NewEncoder(os.Stdout)
		encoder.SetIndent("", "  ")
		if err := encoder.Encode(report); err != nil {
			os.Exit(1)
		}
	default:
		fmt.Fprintln(os.Stderr, "Unknown command. Farm creation and enrollment are not available in this foundation build.")
		os.Exit(2)
	}
}
