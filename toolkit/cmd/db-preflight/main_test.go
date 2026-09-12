package main

import (
	"bytes"
	"encoding/binary"
	"testing"

	"github.com/ethereum/go-ethereum/common"
)

func TestRawDatabaseKeys(t *testing.T) {
	const number = uint64(0x0102030405060708)
	hash := common.HexToHash("0x1234")

	canonical := canonicalHashKey(number)
	if len(canonical) != 10 || canonical[0] != 'h' || canonical[9] != 'n' {
		t.Fatalf("unexpected canonical key: %x", canonical)
	}
	if got := binary.BigEndian.Uint64(canonical[1:9]); got != number {
		t.Fatalf("canonical key number: got %x want %x", got, number)
	}

	header := storedHeaderKey(number, hash)
	body := storedBodyKey(number, hash)
	if len(header) != 41 || header[0] != 'h' {
		t.Fatalf("unexpected header key: %x", header)
	}
	if len(body) != 41 || body[0] != 'b' {
		t.Fatalf("unexpected body key: %x", body)
	}
	if !bytes.Equal(header[9:], hash[:]) || !bytes.Equal(body[9:], hash[:]) {
		t.Fatal("header/body key hash mismatch")
	}
}

func TestRewardAccumulatorKey(t *testing.T) {
	const number = uint64(93_623_067)
	key := rewardAccumulatorKey(number)
	if string(key[:len("blk-rwd-")]) != "blk-rwd-" {
		t.Fatalf("unexpected prefix: %x", key)
	}
	if got := binary.BigEndian.Uint64(key[len("blk-rwd-"):]); got != number {
		t.Fatalf("block number: got %d want %d", got, number)
	}
}
