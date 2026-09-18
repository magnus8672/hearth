// Hearth's native host entry point. A read-only doctor never creates or joins a farm.
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/signal"
	"runtime"
	"syscall"

	"hearth.local/worker/internal/host"
	"hearth.local/worker/internal/manager"
)

func main() {
	if len(os.Args) == 3 && os.Args[1] == "serve" {
		ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
		defer cancel()
		if err := manager.Run(ctx, os.Args[2]); err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
		return
	}
	if len(os.Args) != 2 {
		fmt.Fprintln(os.Stderr, "Usage: hearth-worker doctor | version | serve /absolute/config.json")
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
