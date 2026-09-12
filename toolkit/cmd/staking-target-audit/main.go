package main

import (
	"bufio"
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

type taggedEnvelope struct {
	Signature string
	Tag       string
	Raw       rlp.RawValue
}

type rawStakingTransaction struct {
	Directive byte
	StakeMsg  rlp.RawValue
	Nonce     uint64
	GasPrice  *big.Int
	GasLimit  uint64
	V         *big.Int
	R         *big.Int
	S         *big.Int
}

type directiveCount struct {
	Directive string `json:"directive"`
	Count     uint64 `json:"count"`
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
	DBPath                    string           `json:"db_path"`
	StartBlockExclusive       uint64           `json:"start_block_exclusive"`
	EndBlockInclusive         uint64           `json:"end_block_inclusive"`
	BlocksScanned             uint64           `json:"blocks_scanned"`
	BlocksWithStakingTx       uint64           `json:"blocks_with_staking_transactions"`
	StakingTransactions       uint64           `json:"staking_transactions"`
	DirectiveCounts           []directiveCount `json:"directive_counts"`
	CurrentValidatorListCount uint64           `json:"current_validator_list_count"`
	CreatedValidatorsInRange  uint64           `json:"created_validators_in_range"`
	UnknownTargetTransactions uint64           `json:"unknown_target_transactions"`
	UnknownTargets            []unknownTarget  `json:"unknown_targets"`
	CanonicalBlockDigest      string           `json:"canonical_block_digest_sha256"`
	OutputPath                string           `json:"output_path"`
	OutputSHA256              string           `json:"output_sha256"`
	ElapsedMilliseconds       int64            `json:"elapsed_milliseconds"`
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

func decodeBodyStakingTransactions(encoded []byte, number uint64) []rlp.RawValue {
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
	if err := rlp.DecodeBytes(fields[1], &transactions); err != nil {
		fatalf("decode staking transaction list at block %d: %v", number, err)
	}
	return transactions
}

func decodeMessageFields(raw rlp.RawValue, number uint64, index int) []rlp.RawValue {
	var fields []rlp.RawValue
	if err := rlp.DecodeBytes(raw, &fields); err != nil {
		fatalf("decode staking message at block %d index %d: %v", number, index, err)
	}
	return fields
}

func decodeAddress(raw rlp.RawValue, number uint64, index int, field string) common.Address {
	var address common.Address
	if err := rlp.DecodeBytes(raw, &address); err != nil {
		fatalf("decode %s at block %d index %d: %v", field, number, index, err)
	}
	return address
}

func decodeAmount(raw rlp.RawValue, number uint64, index int) *big.Int {
	amount := new(big.Int)
	if err := rlp.DecodeBytes(raw, amount); err != nil {
		fatalf("decode amount at block %d index %d: %v", number, index, err)
	}
	if amount.Sign() < 0 {
		fatalf("negative amount at block %d index %d", number, index)
	}
	return amount
}

func directiveName(directive byte) string {
	switch directive {
	case 0:
		return "CreateValidator"
	case 1:
		return "EditValidator"
	case 2:
		return "Delegate"
	case 3:
		return "Undelegate"
	case 4:
		return "CollectRewards"
	default:
		fatalf("unknown staking directive %d", directive)
		return ""
	}
}

func main() {
	var (
		dbPath  = flag.String("db", "", "path to shard-0 archive LevelDB")
		start   = flag.Uint64("start", 0, "starting block, excluded")
		end     = flag.Uint64("end", 0, "ending block, included")
		output  = flag.String("output", "", "staking target CSV output path")
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
		"staking_transaction_index",
		"staking_transaction_hash",
		"directive",
		"actor_address",
		"target_validator_address",
		"amount_atto",
		"target_in_current_or_created_validator_set",
	}); err != nil {
		fatalf("write output header: %v", err)
	}

	started := time.Now()
	lastProgress := started
	blockDigest := sha256.New()
	directives := map[string]uint64{}
	createdInRange := map[common.Address]struct{}{}
	unknownTargets := map[common.Address]*mutableUnknownTarget{}
	var blocksScanned, blocksWithStaking, stakingTransactions, unknownTransactions uint64

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

		rawTransactions := decodeBodyStakingTransactions(body, number)
		if len(rawTransactions) > 0 {
			blocksWithStaking++
		}
		for index, raw := range rawTransactions {
			var transaction rawStakingTransaction
			if err := rlp.DecodeBytes(raw, &transaction); err != nil {
				fatalf("decode staking transaction at block %d index %d: %v", number, index, err)
			}
			name := directiveName(transaction.Directive)
			directives[name]++
			stakingTransactions++

			message := decodeMessageFields(transaction.StakeMsg, number, index)
			var actor, target common.Address
			amount := new(big.Int)
			switch transaction.Directive {
			case 0:
				if len(message) != 8 {
					fatalf("unexpected CreateValidator field count at block %d index %d: %d", number, index, len(message))
				}
				target = decodeAddress(message[0], number, index, "validator address")
				actor = target
				amount = decodeAmount(message[7], number, index)
				knownValidators[target] = struct{}{}
				createdInRange[target] = struct{}{}
			case 1:
				if len(message) != 9 {
					fatalf("unexpected EditValidator field count at block %d index %d: %d", number, index, len(message))
				}
				target = decodeAddress(message[0], number, index, "validator address")
				actor = target
			case 2, 3:
				if len(message) != 3 {
					fatalf("unexpected delegate field count at block %d index %d: %d", number, index, len(message))
				}
				actor = decodeAddress(message[0], number, index, "delegator address")
				target = decodeAddress(message[1], number, index, "validator address")
				amount = decodeAmount(message[2], number, index)
			case 4:
				if len(message) != 1 {
					fatalf("unexpected CollectRewards field count at block %d index %d: %d", number, index, len(message))
				}
				actor = decodeAddress(message[0], number, index, "delegator address")
			}

			_, targetKnown := knownValidators[target]
			if target != (common.Address{}) && !targetKnown {
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
				if transaction.Directive == 2 {
					entry.delegateAtto.Add(entry.delegateAtto, amount)
				}
				if transaction.Directive == 3 {
					entry.undelegateAtto.Add(entry.undelegateAtto, amount)
				}
			}

			if err := writer.Write([]string{
				fmt.Sprintf("%d", number),
				hash.Hex(),
				fmt.Sprintf("%d", index),
				crypto.Keccak256Hash(raw).Hex(),
				name,
				actor.Hex(),
				target.Hex(),
				amount.String(),
				fmt.Sprintf("%t", target == (common.Address{}) || targetKnown),
			}); err != nil {
				fatalf("write output row: %v", err)
			}
		}

		if time.Since(lastProgress) >= 30*time.Second {
			fmt.Fprintf(
				os.Stderr,
				"progress block=%d/%d blocks=%d staking_transactions=%d unknown_target_transactions=%d elapsed=%s\n",
				number,
				*end,
				blocksScanned,
				stakingTransactions,
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

	directiveNames := make([]string, 0, len(directives))
	for name := range directives {
		directiveNames = append(directiveNames, name)
	}
	sort.Strings(directiveNames)
	counts := make([]directiveCount, 0, len(directiveNames))
	for _, name := range directiveNames {
		counts = append(counts, directiveCount{Directive: name, Count: directives[name]})
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
		BlocksWithStakingTx:       blocksWithStaking,
		StakingTransactions:       stakingTransactions,
		DirectiveCounts:           counts,
		CurrentValidatorListCount: uint64(len(validators)),
		CreatedValidatorsInRange:  uint64(len(createdInRange)),
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
