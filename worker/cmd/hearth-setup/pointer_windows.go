package main

import "unsafe"

func uintptrPointer(value *uint16) uintptr { return uintptr(unsafe.Pointer(value)) }
