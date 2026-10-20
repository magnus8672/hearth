package manager

import (
	"errors"
	"golang.org/x/sys/windows"
	"os"
	"path/filepath"
)

func lock(directory string) (func(), error) {
	if err := os.MkdirAll(directory, 0700); err != nil {
		return nil, err
	}
	path, err := windows.UTF16PtrFromString(filepath.Join(directory, "worker.lock"))
	if err != nil {
		return nil, err
	}
	handle, err := windows.CreateFile(path, windows.GENERIC_READ|windows.GENERIC_WRITE, 0, nil, windows.OPEN_ALWAYS, windows.FILE_ATTRIBUTE_NORMAL, 0)
	if err != nil {
		return nil, errors.New("another worker owns this state directory or access is denied")
	}
	return func() { windows.CloseHandle(handle) }, nil
}
