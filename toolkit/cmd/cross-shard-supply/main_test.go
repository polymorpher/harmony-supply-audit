package main

import (
	"bytes"
	"encoding/binary"
	"errors"
	"math/big"
	"reflect"
	"strings"
	"testing"

	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/core/rawdb"
	"github.com/ethereum/go-ethereum/ethdb"
	"github.com/ethereum/go-ethereum/ethdb/leveldb"
	"github.com/ethereum/go-ethereum/rlp"
)

type failingReadDB struct {
	ethdb.Database
	getKey []byte
	getErr error
	hasKey []byte
	hasErr error
}

func (db failingReadDB) Get(key []byte) ([]byte, error) {
	if bytes.Equal(key, db.getKey) {
		return nil, db.getErr
	}
	return db.Database.Get(key)
}

func (db failingReadDB) Has(key []byte) (bool, error) {
	if db.hasErr != nil && bytes.Equal(key, db.hasKey) {
		return false, db.hasErr
	}
	return db.Database.Has(key)
}

func receiptFixture(t *testing.T) (ethdb.Database, ethdb.Database, common.Hash) {
	t.Helper()
	source := rawdb.NewMemoryDatabase()
	t.Cleanup(func() { source.Close() })
	disk, err := leveldb.New(t.TempDir(), 16, 16, "", false)
	if err != nil {
		t.Fatal(err)
	}
	destination := rawdb.NewDatabase(disk)
	t.Cleanup(func() { destination.Close() })
	sourceHash := common.HexToHash("0x1111")
	destinationHash := common.HexToHash("0x2222")
	txHash := common.HexToHash("0x3333")
	to := common.HexToAddress("0x4444")
	rawdb.WriteCanonicalHash(source, sourceHash, 10)
	rawdb.WriteCanonicalHash(destination, destinationHash, 20)
	key := make([]byte, len(receiptPrefix)+4+8+common.HashLength)
	copy(key, receiptPrefix)
	binary.BigEndian.PutUint32(key[len(receiptPrefix):], 1)
	binary.BigEndian.PutUint64(key[len(receiptPrefix)+4:], 10)
	copy(key[len(receiptPrefix)+12:], sourceHash[:])
	encoded, err := rlp.EncodeToBytes([]*cxReceipt{{
		TxHash: txHash, To: &to, ShardID: 0, ToShardID: 1, Amount: big.NewInt(100),
	}})
	if err != nil {
		t.Fatal(err)
	}
	if err := source.Put(key, encoded); err != nil {
		t.Fatal(err)
	}
	lookup, err := rlp.EncodeToBytes(txLookupEntry{BlockHash: destinationHash, BlockIndex: 20})
	if err != nil {
		t.Fatal(err)
	}
	if err := destination.Put(cxLookupKey(txHash), lookup); err != nil {
		t.Fatal(err)
	}
	return source, destination, txHash
}

func TestSumReceiptsDestinationLookup(t *testing.T) {
	readErr := errors.New("destination I/O failure")
	for _, name := range []string{
		"spent",
		"missing",
		"empty",
		"after cutoff",
		"missing cutoff",
		"noncanonical",
		"lookup read failure",
		"lookup existence failure",
		"destination canonical read failure",
		"destination canonical existence failure",
		"destination canonical missing",
		"destination canonical malformed",
		"destination canonical zero",
		"closed LevelDB",
		"malformed lookup",
	} {
		t.Run(name, func(t *testing.T) {
			source, destination, txHash := receiptFixture(t)
			cutoff := uint64(20)
			cutoffs := map[uint32]uint64{1: cutoff}
			wantPending, wantError, wantReadError := false, false, false
			switch name {
			case "missing":
				if err := destination.Delete(cxLookupKey(txHash)); err != nil {
					t.Fatal(err)
				}
				wantPending = true
			case "empty":
				if err := destination.Put(cxLookupKey(txHash), nil); err != nil {
					t.Fatal(err)
				}
				wantError = true
			case "after cutoff":
				cutoffs[1], wantPending = 19, true
			case "missing cutoff":
				delete(cutoffs, 1)
				wantError = true
			case "noncanonical":
				rawdb.WriteCanonicalHash(destination, common.HexToHash("0x9999"), 20)
				wantPending = true
			case "lookup read failure":
				destination = failingReadDB{
					Database: destination,
					getKey:   cxLookupKey(txHash),
					getErr:   readErr,
				}
				wantError, wantReadError = true, true
			case "lookup existence failure":
				destination = failingReadDB{
					Database: destination,
					getKey:   cxLookupKey(txHash),
					getErr:   readErr,
					hasKey:   cxLookupKey(txHash),
					hasErr:   errors.New("existence check failed"),
				}
				wantError, wantReadError = true, true
			case "destination canonical read failure":
				destination = failingReadDB{
					Database: destination,
					getKey:   canonicalHashKey(20),
					getErr:   readErr,
				}
				wantError, wantReadError = true, true
			case "destination canonical existence failure":
				destination = failingReadDB{
					Database: destination,
					getKey:   canonicalHashKey(20),
					getErr:   readErr,
					hasKey:   canonicalHashKey(20),
					hasErr:   errors.New("existence check failed"),
				}
				wantError, wantReadError = true, true
			case "destination canonical missing":
				if err := destination.Delete(canonicalHashKey(20)); err != nil {
					t.Fatal(err)
				}
				wantError = true
			case "destination canonical malformed":
				if err := destination.Put(canonicalHashKey(20), []byte{0x01}); err != nil {
					t.Fatal(err)
				}
				wantError = true
			case "destination canonical zero":
				if err := destination.Put(canonicalHashKey(20), make([]byte, common.HashLength)); err != nil {
					t.Fatal(err)
				}
				wantError = true
			case "closed LevelDB":
				if err := destination.Close(); err != nil {
					t.Fatal(err)
				}
				wantError = true
			case "malformed lookup":
				if err := destination.Put(cxLookupKey(txHash), []byte{0xff}); err != nil {
					t.Fatal(err)
				}
				wantError = true
			}
			got, err := sumReceipts(0, source, map[uint32]ethdb.Database{1: destination}, 10, cutoffs)
			if wantError {
				if err == nil {
					t.Fatalf("unreadable receipt returned totals: %+v", got)
				}
				if !reflect.DeepEqual(got, directionTotals{}) {
					t.Fatalf("partial totals returned on error: %+v", got)
				}
				if !strings.Contains(err.Error(), txHash.Hex()) {
					t.Fatalf("missing transaction context: %v", err)
				}
				if wantReadError && !errors.Is(err, readErr) {
					t.Fatalf("lost original read error: %v", err)
				}
				return
			}
			if err != nil {
				t.Fatal(err)
			}
			if wantPending {
				if got.PendingAmountAtto != "100" || got.SpentAmountAtto != "0" || got.PendingReceiptCount != 1 {
					t.Fatalf("unexpected pending totals: %+v", got)
				}
			} else if got.PendingAmountAtto != "0" || got.SpentAmountAtto != "100" || got.SpentReceiptCount != 1 {
				t.Fatalf("unexpected spent totals: %+v", got)
			}
		})
	}
}

func TestReadOptionalMemoryDatabaseMissingKey(t *testing.T) {
	db := rawdb.NewMemoryDatabase()
	defer db.Close()
	value, found, err := readOptional(db, []byte("missing"))
	if err != nil || found || value != nil {
		t.Fatalf("missing key: value=%x found=%t error=%v", value, found, err)
	}
}

func TestReadOptionalExistingEmptyValue(t *testing.T) {
	db := rawdb.NewMemoryDatabase()
	defer db.Close()
	key := []byte("empty")
	if err := db.Put(key, nil); err != nil {
		t.Fatal(err)
	}
	value, found, err := readOptional(db, key)
	if err != nil || !found || len(value) != 0 {
		t.Fatalf("empty key: value=%x found=%t error=%v", value, found, err)
	}
}

func TestSumReceiptsSourceCanonicalReadFailure(t *testing.T) {
	readErr := errors.New("source canonical I/O failure")
	for _, name := range []string{
		"read failure",
		"existence failure",
		"missing",
		"malformed",
		"zero",
	} {
		t.Run(name, func(t *testing.T) {
			source, destination, _ := receiptFixture(t)
			switch name {
			case "read failure":
				source = failingReadDB{
					Database: source,
					getKey:   canonicalHashKey(10),
					getErr:   readErr,
				}
			case "existence failure":
				source = failingReadDB{
					Database: source,
					getKey:   canonicalHashKey(10),
					getErr:   readErr,
					hasKey:   canonicalHashKey(10),
					hasErr:   errors.New("existence check failed"),
				}
			case "missing":
				if err := source.Delete(canonicalHashKey(10)); err != nil {
					t.Fatal(err)
				}
			case "malformed":
				if err := source.Put(canonicalHashKey(10), []byte{0x01}); err != nil {
					t.Fatal(err)
				}
			case "zero":
				if err := source.Put(canonicalHashKey(10), make([]byte, common.HashLength)); err != nil {
					t.Fatal(err)
				}
			}
			got, err := sumReceipts(
				0,
				source,
				map[uint32]ethdb.Database{1: destination},
				10,
				map[uint32]uint64{1: 20},
			)
			if err == nil {
				t.Fatalf("unreadable source returned totals: %+v", got)
			}
			if !reflect.DeepEqual(got, directionTotals{}) {
				t.Fatalf("partial totals returned on error: %+v", got)
			}
			if !strings.Contains(err.Error(), "source shard 0") ||
				!strings.Contains(err.Error(), "block 10") {
				t.Fatalf("missing source context: %v", err)
			}
			if (name == "read failure" || name == "existence failure") &&
				!errors.Is(err, readErr) {
				t.Fatalf("lost original read error: %v", err)
			}
		})
	}
}
