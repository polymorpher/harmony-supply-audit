package main

import (
	"math/big"
	"testing"

	"github.com/ethereum/go-ethereum/common"
)

func TestDecodeDelegateCall(t *testing.T) {
	delegator := common.HexToAddress("0x1111111111111111111111111111111111111111")
	validator := common.HexToAddress("0x2222222222222222222222222222222222222222")
	amount := big.NewInt(123456789)
	input := make([]byte, 100)
	copy(input[:4], delegateSelector[:])
	copy(input[16:36], delegator[:])
	copy(input[48:68], validator[:])
	amount.FillBytes(input[68:100])

	method, gotDelegator, gotValidator, gotAmount, valid := decodeStakingCall(input)
	if !valid || method != "Delegate" {
		t.Fatalf("method: got %q valid=%t", method, valid)
	}
	if gotDelegator != delegator || gotValidator != validator {
		t.Fatalf("addresses: got %s -> %s", gotDelegator, gotValidator)
	}
	if gotAmount.Cmp(amount) != 0 {
		t.Fatalf("amount: got %s want %s", gotAmount, amount)
	}
}

func TestDecodeCollectRewardsAndInvalidInput(t *testing.T) {
	delegator := common.HexToAddress("0x3333333333333333333333333333333333333333")
	input := make([]byte, 36)
	copy(input[:4], rewardsSelector[:])
	copy(input[16:], delegator[:])

	method, gotDelegator, target, amount, valid := decodeStakingCall(input)
	if !valid || method != "CollectRewards" || gotDelegator != delegator {
		t.Fatalf("collect rewards decode failed")
	}
	if target != (common.Address{}) || amount.Sign() != 0 {
		t.Fatalf("unexpected target or amount")
	}

	input = append(input, 0)
	if _, _, _, _, valid := decodeStakingCall(input); valid {
		t.Fatal("accepted invalid collect-rewards length")
	}
}
