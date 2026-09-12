package main

import "testing"

func TestDirectiveNames(t *testing.T) {
	want := []string{
		"CreateValidator",
		"EditValidator",
		"Delegate",
		"Undelegate",
		"CollectRewards",
	}
	for directive, name := range want {
		if got := directiveName(byte(directive)); got != name {
			t.Fatalf("directive %d: got %q want %q", directive, got, name)
		}
	}
}
