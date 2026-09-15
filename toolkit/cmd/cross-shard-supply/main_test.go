package main

import (
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

type failingLookupDB struct {
	ethdb.Database
	getErr error
	hasErr error
}

func (db failingLookupDB) Get(key []byte) ([]byte, error) {
	if len(key) == len(cxLookupPrefix)+common.HashLength && string(key[:len(cxLookupPrefix)]) == string(cxLookupPrefix) {
		return nil, db.getErr
	}
	return db.Database.Get(key)
}

func (db failingLookupDB) Has(key []byte) (bool, error) {
	if db.hasErr != nil {
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
	for _, name := range []string{"spent", "missing", "empty", "after cutoff", "noncanonical", "read failure", "existence failure", "closed LevelDB", "malformed lookup"} {
		t.Run(name, func(t *testing.T) {
			source, destination, txHash := receiptFixture(t)
			cutoff := uint64(20)
			wantPending, wantError := false, false
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
				wantPending = true
			case "after cutoff":
				cutoff, wantPending = 19, true
			case "noncanonical":
				rawdb.WriteCanonicalHash(destination, common.HexToHash("0x9999"), 20)
				wantPending = true
			case "read failure":
				destination = failingLookupDB{Database: destination, getErr: readErr}
				wantError = true
			case "existence failure":
				destination = failingLookupDB{Database: destination, getErr: readErr, hasErr: errors.New("existence check failed")}
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
			got, err := sumReceipts(0, source, map[uint32]ethdb.Database{1: destination}, 10, map[uint32]uint64{1: cutoff})
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
				if (name == "read failure" || name == "existence failure") && !errors.Is(err, readErr) {
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
	value, err := readOptional(db, []byte("missing"))
	if err != nil || value != nil {
		t.Fatalf("missing key: value=%x error=%v", value, err)
	}
}
