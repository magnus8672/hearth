package manager

import (
	"errors"
	"path/filepath"
	"strings"
)

func validateProcesses(s Service) error {
	if len(s.Processes) < 1 || len(s.Processes) > 2 {
		return errors.New("approve one engine and an optional connector")
	}
	for _, p := range s.Processes {
		if !filepath.IsAbs(p.Executable) || !filepath.IsAbs(p.Directory) || filepath.Clean(p.Executable) != p.Executable || filepath.Clean(p.Directory) != p.Directory {
			return errors.New("absolute clean process paths required")
		}
		switch strings.ToLower(filepath.Base(p.Executable)) {
		case "python.exe", "llama-server.exe", "hearth-connector.exe":
		default:
			return errors.New("unsupported engine executable")
		}
		if _, ok := s.Files[p.Executable]; !ok {
			return errors.New("engine executable must be bound to the recipe")
		}
		if len(p.Arguments) > 48 {
			return errors.New("too many engine arguments")
		}
		for _, a := range p.Arguments {
			if len(a) > 4096 || strings.ContainsRune(a, 0) {
				return errors.New("invalid engine argument")
			}
		}
	}
	return nil
}
