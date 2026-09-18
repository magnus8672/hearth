//go:build !linux

package manager

import "errors"

func lock(string) (func(), error) {
	return nil, errors.New("managed services currently require Linux with systemd")
}
