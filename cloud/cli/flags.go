package main

import (
	"fmt"
	"strings"
)

// stringsFlag collects a repeatable flag, e.g. --sg a --sg b.
type stringsFlag []string

func (s *stringsFlag) String() string { return strings.Join(*s, ",") }

func (s *stringsFlag) Set(value string) error {
	*s = append(*s, value)
	return nil
}

// keyValues collects repeatable key=value flags for tags.
type keyValues map[string]string

func (k keyValues) String() string {
	parts := make([]string, 0, len(k))
	for key, value := range k {
		parts = append(parts, key+"="+value)
	}
	return strings.Join(parts, ",")
}

func (k keyValues) Set(text string) error {
	key, value, found := strings.Cut(text, "=")
	if !found || key == "" {
		return fmt.Errorf("expected key=value, got %q", text)
	}
	k[key] = value
	return nil
}

// optionalBool records whether a flag was given at all, so "not given" stays
// distinguishable from false.
type optionalBool struct {
	set   bool
	value bool
}

func (o *optionalBool) String() string {
	if !o.set {
		return ""
	}
	return fmt.Sprint(o.value)
}

func (o *optionalBool) Set(text string) error {
	parsed, err := parseBool(text)
	if err != nil {
		return err
	}
	o.set, o.value = true, parsed
	return nil
}

func (o *optionalBool) pointer() *bool {
	if !o.set {
		return nil
	}
	return &o.value
}

// optionalInt records whether an integer flag was given at all.
type optionalInt struct {
	set   bool
	value int
}

func (o *optionalInt) String() string {
	if !o.set {
		return ""
	}
	return fmt.Sprint(o.value)
}

func (o *optionalInt) Set(text string) error {
	var value int
	if _, err := fmt.Sscan(text, &value); err != nil {
		return fmt.Errorf("expected a number, got %q", text)
	}
	o.set, o.value = true, value
	return nil
}

func (o *optionalInt) pointer() *int {
	if !o.set {
		return nil
	}
	return &o.value
}
