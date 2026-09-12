package main

import (
	"bufio"
	"bytes"
	"crypto/sha256"
	"encoding/binary"
	"encoding/csv"
	"encoding/hex"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"math/big"
	"os"
	"sort"
	"time"

	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/crypto"
	"github.com/ethereum/go-ethereum/ethdb/leveldb"
	"github.com/ethereum/go-ethereum/rlp"
)

const envelopeSignature = "HmnyTgd"

var (
	stakingPrecompile  = common.BytesToAddress([]byte{252})
	delegateSelector   = [4]byte{0x51, 0x0b, 0x11, 0xbb}
	undelegateSelector = [4]byte{0xbd, 0xa8, 0xc0, 0xe9}
	rewardsSelector    = [4]byte{0x6d, 0x6b, 0x2f, 0x77}
)

type taggedEnvelope struct {
	Signature string
	Tag       string
	Raw       rlp.RawValue
}

type rawTransaction struct {
	AccountNonce uint64
	Price        *big.Int
	GasLimit     uint64
	ShardID      uint32
	ToShardID    uint32
	Recipient    *common.Address `rlp:"nil"`
	Amount       *big.Int
	Payload      []byte
	V            *big.Int
	R            *big.Int
	S            *big.Int
}

type methodCount struct {
	Method string `json:"method"`
	Count  uint64 `json:"count"`
}

type unknownTarget struct {
	Address        common.Address `json:"address"`
	FirstBlock     uint64         `json:"first_block"`
	LastBlock      uint64         `json:"last_block"`
	Transactions   uint64         `json:"transactions"`
	DelegateAtto   string         `json:"delegate_atto"`
	UndelegateAtto string         `json:"undelegate_atto"`
}

type mutableUnknownTarget struct {
	firstBlock     uint64
	lastBlock      uint64
	transactions   uint64
	delegateAtto   *big.Int
	undelegateAtto *big.Int
}

type summary struct {
	DBPath                    string          `json:"db_path"`
	StartBlockExclusive       uint64          `json:"start_block_exclusive"`
	EndBlockInclusive         uint64          `json:"end_block_inclusive"`
	BlocksScanned             uint64          `json:"blocks_scanned"`
	RegularTransactions       uint64          `json:"regular_transactions"`
	TopLevelPrecompileCalls   uint64          `json:"top_level_staking_precompile_calls"`
	ValidStakingCalls         uint64          `json:"valid_staking_calls"`
	InvalidCalldataCalls      uint64          `json:"invalid_calldata_calls"`
	MethodCounts              []methodCount   `json:"method_counts"`
	CurrentValidatorListCount uint64          `json:"current_validator_list_count"`
	UnknownTargetTransactions uint64          `json:"unknown_target_transactions"`
	UnknownTargets            []unknownTarget `json:"unknown_targets"`
	CanonicalBlockDigest      string          `json:"canonical_block_digest_sha256"`
	OutputPath                string          `json:"output_path"`
	OutputSHA256              string          `json:"output_sha256"`
	ElapsedMilliseconds       int64           `json:"elapsed_milliseconds"`
}

func fatalf(format string, args ...interface{}) {
	fmt.Fprintf(os.Stderr, "fatal: "+format+"\n", args...)
	os.Exit(1)
}

func canonicalHashKey(number uint64) []byte {
	key := make([]byte, 10)
	key[0] = 'h'
	binary.BigEndian.PutUint64(key[1:9], number)
	key[9] = 'n'
	return key
}

func bodyKey(number uint64, hash common.Hash) []byte {
	key := make([]byte, 1+8+common.HashLength)
	key[0] = 'b'
	binary.BigEndian.PutUint64(key[1:9], number)
	copy(key[9:], hash[:])
	return key
}

func decodeBodyTransactions(encoded []byte, number uint64) []rlp.RawValue {
	var envelope taggedEnvelope
	if err := rlp.DecodeBytes(encoded, &envelope); err != nil {
		fatalf("decode body envelope at block %d: %v", number, err)
	}
	if envelope.Signature != envelopeSignature {
		fatalf("invalid body envelope signature at block %d: %q", number, envelope.Signature)
	}
	var fields []rlp.RawValue
	if err := rlp.DecodeBytes(envelope.Raw, &fields); err != nil {
		fatalf("decode %s body fields at block %d: %v", envelope.Tag, number, err)
	}
	if envelope.Tag != "v2" {
		fatalf("unsupported body tag at block %d: %q", number, envelope.Tag)
	}
	if len(fields) != 4 {
		fatalf("unexpected v2 body field count at block %d: %d", number, len(fields))
	}
	var transactions []rlp.RawValue
	if err := rlp.DecodeBytes(fields[0], &transactions); err != nil {
		fatalf("decode regular transaction list at block %d: %v", number, err)
	}
	return transactions
}

func decodeStakingCall(input []byte) (method string, delegator, target common.Address, amount *big.Int, valid bool) {
	amount = new(big.Int)
	if len(input) < 4 {
		return "invalid", delegator, target, amount, false
	}
	var selector [4]byte
	copy(selector[:], input[:4])
	switch selector {
	case delegateSelector:
		method = "Delegate"
	case undelegateSelector:
		method = "Undelegate"
	case rewardsSelector:
		method = "CollectRewards"
	default:
		return "unknown-selector-" + hex.EncodeToString(selector[:]), delegator, target, amount, false
	}
	if method == "CollectRewards" {
		if len(input) != 36 || !bytes.Equal(input[4:16], make([]byte, 12)) {
			return method, delegator, target, amount, false
		}
		delegator = common.BytesToAddress(input[16:36])
		return method, delegator, target, amount, true
	}
	if len(input) != 100 ||
		!bytes.Equal(input[4:16], make([]byte, 12)) ||
		!bytes.Equal(input[36:48], make([]byte, 12)) {
		return method, delegator, target, amount, false
	}
	delegator = common.BytesToAddress(input[16:36])
	target = common.BytesToAddress(input[48:68])
	amount.SetBytes(input[68:100])
	return method, delegator, target, amount, true
}

func main() {
	var (
		dbPath  = flag.String("db", "", "path to shard-0 archive LevelDB")
		start   = flag.Uint64("start", 0, "starting block, excluded")
		end     = flag.Uint64("end", 0, "ending block, included")
		output  = flag.String("output", "", "staking-precompile call CSV output path")
		cacheMB = flag.Int("cache-mb", 4096, "LevelDB cache in MiB")
		handles = flag.Int("handles", 4096, "LevelDB open-file handles")
	)
	flag.Parse()
	if *dbPath == "" || *output == "" || *end <= *start {
		flag.Usage()
		os.Exit(2)
	}

	disk, err := leveldb.New(*dbPath, *cacheMB, *handles, "", true)
	if err != nil {
		fatalf("open database read-only: %v", err)
	}
	defer disk.Close()

	validatorBytes, err := disk.Get([]byte("validator-list"))
	if err != nil {
		fatalf("read current validator list: %v", err)
	}
	var validators []common.Address
	if err := rlp.DecodeBytes(validatorBytes, &validators); err != nil {
		fatalf("decode current validator list: %v", err)
	}
	knownValidators := make(map[common.Address]struct{}, len(validators))
	for _, address := range validators {
		knownValidators[address] = struct{}{}
	}

	partial := *output + ".partial"
	outputFile, err := os.OpenFile(partial, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o600)
	if err != nil {
		fatalf("create output: %v", err)
	}
	outputComplete := false
	defer func() {
		_ = outputFile.Close()
		if !outputComplete {
			_ = os.Remove(partial)
		}
	}()
	outputHash := sha256.New()
	buffered := bufio.NewWriterSize(io.MultiWriter(outputFile, outputHash), 1024*1024)
	writer := csv.NewWriter(buffered)
	if err := writer.Write([]string{
		"block_number",
		"block_hash",
		"transaction_index",
		"transaction_hash",
		"method",
		"delegator_address",
		"target_validator_address",
		"amount_atto",
		"target_in_current_validator_list",
		"calldata_valid",
	}); err != nil {
		fatalf("write output header: %v", err)
	}

	started := time.Now()
	lastProgress := started
	blockDigest := sha256.New()
	methods := map[string]uint64{}
	unknownTargets := map[common.Address]*mutableUnknownTarget{}
	var blocksScanned, regularTransactions, topLevelCalls, validCalls, invalidCalls, unknownTransactions uint64

	for number := *start + 1; number <= *end; number++ {
		hashBytes, err := disk.Get(canonicalHashKey(number))
		if err != nil {
			fatalf("read canonical hash at block %d: %v", number, err)
		}
		if len(hashBytes) != common.HashLength {
			fatalf("invalid canonical hash length at block %d: %d", number, len(hashBytes))
		}
		hash := common.BytesToHash(hashBytes)
		body, err := disk.Get(bodyKey(number, hash))
		if err != nil {
			fatalf("read body at block %d hash %s: %v", number, hash.Hex(), err)
		}
		var numberBytes [8]byte
		binary.BigEndian.PutUint64(numberBytes[:], number)
		_, _ = blockDigest.Write(numberBytes[:])
		_, _ = blockDigest.Write(hash[:])
		blocksScanned++

		rawTransactions := decodeBodyTransactions(body, number)
		regularTransactions += uint64(len(rawTransactions))
		for index, raw := range rawTransactions {
			var transaction rawTransaction
			if err := rlp.DecodeBytes(raw, &transaction); err != nil {
				fatalf("decode regular transaction at block %d index %d: %v", number, index, err)
			}
			to := transaction.Recipient
			if to == nil || *to != stakingPrecompile {
				continue
			}
			topLevelCalls++
			method, delegator, target, amount, valid := decodeStakingCall(transaction.Payload)
			methods[method]++
			if valid {
				validCalls++
			} else {
				invalidCalls++
			}
			_, targetKnown := knownValidators[target]
			if valid && target != (common.Address{}) && !targetKnown {
				unknownTransactions++
				entry := unknownTargets[target]
				if entry == nil {
					entry = &mutableUnknownTarget{
						firstBlock:     number,
						delegateAtto:   new(big.Int),
						undelegateAtto: new(big.Int),
					}
					unknownTargets[target] = entry
				}
				entry.lastBlock = number
				entry.transactions++
				if method == "Delegate" {
					entry.delegateAtto.Add(entry.delegateAtto, amount)
				}
				if method == "Undelegate" {
					entry.undelegateAtto.Add(entry.undelegateAtto, amount)
				}
			}
			if err := writer.Write([]string{
				fmt.Sprintf("%d", number),
				hash.Hex(),
				fmt.Sprintf("%d", index),
				crypto.Keccak256Hash(raw).Hex(),
				method,
				delegator.Hex(),
				target.Hex(),
				amount.String(),
				fmt.Sprintf("%t", target == (common.Address{}) || targetKnown),
				fmt.Sprintf("%t", valid),
			}); err != nil {
				fatalf("write output row: %v", err)
			}
		}

		if time.Since(lastProgress) >= 30*time.Second {
			fmt.Fprintf(
				os.Stderr,
				"progress block=%d/%d blocks=%d regular_transactions=%d top_level_precompile_calls=%d unknown_target_transactions=%d elapsed=%s\n",
				number,
				*end,
				blocksScanned,
				regularTransactions,
				topLevelCalls,
				unknownTransactions,
				time.Since(started).Round(time.Second),
			)
			lastProgress = time.Now()
		}
		if number == ^uint64(0) {
			break
		}
	}

	writer.Flush()
	if err := writer.Error(); err != nil {
		fatalf("flush output CSV: %v", err)
	}
	if err := buffered.Flush(); err != nil {
		fatalf("flush output buffer: %v", err)
	}
	if err := outputFile.Sync(); err != nil {
		fatalf("sync output: %v", err)
	}
	if err := outputFile.Close(); err != nil {
		fatalf("close output: %v", err)
	}
	if err := os.Rename(partial, *output); err != nil {
		fatalf("publish output: %v", err)
	}
	outputComplete = true

	methodNames := make([]string, 0, len(methods))
	for method := range methods {
		methodNames = append(methodNames, method)
	}
	sort.Strings(methodNames)
	counts := make([]methodCount, 0, len(methodNames))
	for _, method := range methodNames {
		counts = append(counts, methodCount{Method: method, Count: methods[method]})
	}

	unknownAddresses := make([]common.Address, 0, len(unknownTargets))
	for address := range unknownTargets {
		unknownAddresses = append(unknownAddresses, address)
	}
	sort.Slice(unknownAddresses, func(i, j int) bool {
		return string(unknownAddresses[i][:]) < string(unknownAddresses[j][:])
	})
	unknown := make([]unknownTarget, 0, len(unknownAddresses))
	for _, address := range unknownAddresses {
		entry := unknownTargets[address]
		unknown = append(unknown, unknownTarget{
			Address:        address,
			FirstBlock:     entry.firstBlock,
			LastBlock:      entry.lastBlock,
			Transactions:   entry.transactions,
			DelegateAtto:   entry.delegateAtto.String(),
			UndelegateAtto: entry.undelegateAtto.String(),
		})
	}

	result := summary{
		DBPath:                    *dbPath,
		StartBlockExclusive:       *start,
		EndBlockInclusive:         *end,
		BlocksScanned:             blocksScanned,
		RegularTransactions:       regularTransactions,
		TopLevelPrecompileCalls:   topLevelCalls,
		ValidStakingCalls:         validCalls,
		InvalidCalldataCalls:      invalidCalls,
		MethodCounts:              counts,
		CurrentValidatorListCount: uint64(len(validators)),
		UnknownTargetTransactions: unknownTransactions,
		UnknownTargets:            unknown,
		CanonicalBlockDigest:      hex.EncodeToString(blockDigest.Sum(nil)),
		OutputPath:                *output,
		OutputSHA256:              hex.EncodeToString(outputHash.Sum(nil)),
		ElapsedMilliseconds:       time.Since(started).Milliseconds(),
	}
	encoder := json.NewEncoder(os.Stdout)
	encoder.SetIndent("", "  ")
	if err := encoder.Encode(result); err != nil {
		fatalf("encode summary: %v", err)
	}
}
