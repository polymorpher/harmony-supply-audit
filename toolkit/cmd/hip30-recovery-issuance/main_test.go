package main

import (
	"math/big"
	"testing"
)

func TestRewardBlockBoundaries(t *testing.T) {
	tests := []struct {
		number   uint64
		next     uint64
		previous uint64
	}{
		{0, 63, ^uint64(0)},
		{1, 63, ^uint64(0)},
		{62, 63, ^uint64(0)},
		{63, 63, 63},
		{64, 127, 63},
		{127, 127, 127},
	}
	for _, test := range tests {
		if got := nextRewardBlock(test.number); got != test.next {
			t.Fatalf("nextRewardBlock(%d): got %d want %d", test.number, got, test.next)
		}
		if got := previousRewardBlock(test.number); got != test.previous {
			t.Fatalf("previousRewardBlock(%d): got %d want %d", test.number, got, test.previous)
		}
	}
}

func TestRecoveryRate(t *testing.T) {
	want := new(big.Int).Mul(big.NewInt(35), big.NewInt(100_000_000_000_000_000))
	if hip30RecoveryAttoPerCrosslink.Cmp(want) != 0 {
		t.Fatalf("recovery rate: got %s want %s", hip30RecoveryAttoPerCrosslink, want)
	}
}
