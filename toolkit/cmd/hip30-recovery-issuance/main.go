package main

import (
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"flag"
	"fmt"
	"math/big"
	"os"
	"sort"
	"time"

	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/crypto"
	"github.com/ethereum/go-ethereum/ethdb/leveldb"
	"github.com/ethereum/go-ethereum/rlp"
)

const (
	rewardFrequency              = uint64(64)
	envelopeSignature            = "HmnyTgd"
	hip30Epoch            uint64 = 1673
	rejectShard0Crosslink uint64 = 2964
)

var hip30RecoveryAttoPerCrosslink = new(big.Int).Mul(
	big.NewInt(35),
	big.NewInt(100_000_000_000_000_000),
)

type taggedEnvelope struct {
	Signature string
	Tag       string
	Raw       rlp.RawValue
}

type crosslink struct {
	HashF        common.Hash
	BlockNumberF *big.Int
	ViewIDF      *big.Int
	SignatureF   [96]byte
	BitmapF      []byte
	ShardIDF     uint32
	EpochF       *big.Int
}

type decodedHeader struct {
	number     *big.Int
	epoch      *big.Int
	shardID    uint32
	crosslinks []crosslink
}

type shardCount struct {
	ShardID uint32 `json:"shard_id"`
	Count   uint64 `json:"count"`
}

type summary struct {
	DBPath                      string       `json:"db_path"`
	RequestedStartBlock         uint64       `json:"requested_start_block"`
	RequestedEndBlock           uint64       `json:"requested_end_block"`
	FirstRewardBlock            uint64       `json:"first_reward_block"`
	LastRewardBlock             uint64       `json:"last_reward_block"`
	FirstCoveredHeader          uint64       `json:"first_covered_header"`
	LastCoveredHeader           uint64       `json:"last_covered_header"`
	UnrewardedTailHeaders       uint64       `json:"unrewarded_tail_headers"`
	RewardGroups                uint64       `json:"reward_groups"`
	CoveredBeaconHeaders        uint64       `json:"covered_beacon_headers"`
	SyntheticBeaconCrosslinks   uint64       `json:"synthetic_beacon_crosslinks"`
	EncodedHeaderCrosslinks     uint64       `json:"encoded_header_crosslinks"`
	FilteredShardZeroCrosslinks uint64       `json:"filtered_shard_zero_crosslinks"`
	IncludedHeaderCrosslinks    uint64       `json:"included_header_crosslinks"`
	IncludedHeaderLinksByShard  []shardCount `json:"included_header_crosslinks_by_shard"`
	TotalRecoveryCrosslinks     uint64       `json:"total_recovery_crosslinks"`
	RecoveryIssuanceAtto        string       `json:"recovery_issuance_atto"`
	CanonicalHeaderDigestSHA256 string       `json:"canonical_header_digest_sha256"`
	FirstCoveredHeaderHash      common.Hash  `json:"first_covered_header_hash"`
	LastCoveredHeaderHash       common.Hash  `json:"last_covered_header_hash"`
	FirstRewardEpoch            string       `json:"first_reward_epoch"`
	LastRewardEpoch             string       `json:"last_reward_epoch"`
	ElapsedMilliseconds         int64        `json:"elapsed_milliseconds"`
}

func fatalf(format string, args ...interface{}) {
	fmt.Fprintf(os.Stderr, "fatal: "+format+"\n", args...)
	os.Exit(1)
}

func nextRewardBlock(number uint64) uint64 {
	remainder := number % rewardFrequency
	return number + (rewardFrequency - 1 - remainder)
}

func previousRewardBlock(number uint64) uint64 {
	remainder := number % rewardFrequency
	if remainder >= rewardFrequency-1 {
		return number - (remainder - (rewardFrequency - 1))
	}
	return number - (remainder + 1)
}

func canonicalHashKey(number uint64) []byte {
	key := make([]byte, 10)
	key[0] = 'h'
	binary.BigEndian.PutUint64(key[1:9], number)
	key[9] = 'n'
	return key
}

func storedHeaderKey(number uint64, hash common.Hash) []byte {
	key := make([]byte, 1+8+common.HashLength)
	key[0] = 'h'
	binary.BigEndian.PutUint64(key[1:9], number)
	copy(key[9:], hash[:])
	return key
}

func readCanonicalHeader(disk *leveldb.Database, number uint64) (common.Hash, decodedHeader) {
	hashBytes, err := disk.Get(canonicalHashKey(number))
	if err != nil {
		fatalf("read canonical hash at block %d: %v", number, err)
	}
	if len(hashBytes) != common.HashLength {
		fatalf("invalid canonical hash length at block %d: %d", number, len(hashBytes))
	}
	hash := common.BytesToHash(hashBytes)
	encoded, err := disk.Get(storedHeaderKey(number, hash))
	if err != nil {
		fatalf("read canonical header at block %d hash %s: %v", number, hash.Hex(), err)
	}
	if crypto.Keccak256Hash(encoded) != hash {
		fatalf("canonical header hash mismatch at block %d", number)
	}

	var envelope taggedEnvelope
	if err := rlp.DecodeBytes(encoded, &envelope); err != nil {
		fatalf("decode header envelope at block %d: %v", number, err)
	}
	if envelope.Signature != envelopeSignature {
		fatalf("invalid header envelope signature at block %d: %q", number, envelope.Signature)
	}
	var fields []rlp.RawValue
	if err := rlp.DecodeBytes(envelope.Raw, &fields); err != nil {
		fatalf("decode %s header fields at block %d: %v", envelope.Tag, number, err)
	}
	if len(fields) <= 16 {
		fatalf("short %s header at block %d: %d fields", envelope.Tag, number, len(fields))
	}

	result := decodedHeader{
		number: new(big.Int),
		epoch:  new(big.Int),
	}
	if err := rlp.DecodeBytes(fields[8], result.number); err != nil {
		fatalf("decode header number at block %d: %v", number, err)
	}
	if err := rlp.DecodeBytes(fields[15], result.epoch); err != nil {
		fatalf("decode header epoch at block %d: %v", number, err)
	}
	if err := rlp.DecodeBytes(fields[16], &result.shardID); err != nil {
		fatalf("decode header shard at block %d: %v", number, err)
	}

	var crosslinkIndex int
	switch envelope.Tag {
	case "v2":
		crosslinkIndex = 23
	case "v3":
		crosslinkIndex = 22
	default:
		fatalf("unsupported header tag at block %d: %q", number, envelope.Tag)
	}
	if len(fields) <= crosslinkIndex {
		fatalf("short %s header at block %d: %d fields", envelope.Tag, number, len(fields))
	}
	var encodedCrosslinks []byte
	if err := rlp.DecodeBytes(fields[crosslinkIndex], &encodedCrosslinks); err != nil {
		fatalf("decode header crosslink bytes at block %d: %v", number, err)
	}
	if len(encodedCrosslinks) > 0 {
		if err := rlp.DecodeBytes(encodedCrosslinks, &result.crosslinks); err != nil {
			fatalf("decode header crosslinks at block %d: %v", number, err)
		}
	}
	return hash, result
}

func main() {
	var (
		dbPath     = flag.String("db", "", "path to shard-0 archive LevelDB")
		startBlock = flag.Uint64("start", 0, "first block at or after HIP-30 activation")
		endBlock   = flag.Uint64("end", 0, "last cutoff block")
		cacheMB    = flag.Int("cache-mb", 4096, "LevelDB cache in MiB")
		handles    = flag.Int("handles", 4096, "LevelDB open-file handles")
	)
	flag.Parse()
	if *dbPath == "" || *startBlock == 0 || *endBlock < *startBlock {
		flag.Usage()
		os.Exit(2)
	}

	firstReward := nextRewardBlock(*startBlock)
	if firstReward < rewardFrequency-1 {
		fatalf("first reward block underflows coverage")
	}
	lastReward := previousRewardBlock(*endBlock)
	if lastReward < firstReward {
		fatalf("range contains no completed reward group")
	}
	firstCovered := firstReward - (rewardFrequency - 1)
	lastCovered := lastReward
	if firstCovered != *startBlock {
		fatalf(
			"start block %d is not the first header of a reward group; first covered header would be %d",
			*startBlock,
			firstCovered,
		)
	}

	disk, err := leveldb.New(*dbPath, *cacheMB, *handles, "", true)
	if err != nil {
		fatalf("open database read-only: %v", err)
	}
	defer disk.Close()

	started := time.Now()
	lastProgress := started
	digest := sha256.New()
	recoveryIssuance := new(big.Int)
	includedByShard := map[uint32]uint64{}
	var (
		rewardGroups                uint64
		coveredHeaders              uint64
		syntheticCrosslinks         uint64
		encodedCrosslinks           uint64
		filteredShardZeroCrosslinks uint64
		includedHeaderCrosslinks    uint64
		totalRecoveryCrosslinks     uint64
		firstHash                   common.Hash
		lastHash                    common.Hash
		firstRewardEpoch            = new(big.Int)
		lastRewardEpoch             = new(big.Int)
	)

	for rewardBlock := firstReward; rewardBlock <= lastReward; rewardBlock += rewardFrequency {
		_, rewardHeader := readCanonicalHeader(disk, rewardBlock)
		if rewardHeader.number.Uint64() != rewardBlock || rewardHeader.shardID != 0 {
			fatalf("unexpected reward header identity at block %d", rewardBlock)
		}
		if !rewardHeader.epoch.IsUint64() || rewardHeader.epoch.Uint64() < hip30Epoch {
			fatalf("reward block %d epoch %s is before HIP-30", rewardBlock, rewardHeader.epoch)
		}
		if rewardGroups == 0 {
			firstRewardEpoch.Set(rewardHeader.epoch)
		}
		lastRewardEpoch.Set(rewardHeader.epoch)
		rewardGroups++

		groupCrosslinks := uint64(0)
		groupStart := rewardBlock - (rewardFrequency - 1)
		for number := groupStart; number <= rewardBlock; number++ {
			hash, header := readCanonicalHeader(disk, number)
			if header.number.Uint64() != number || header.shardID != 0 {
				fatalf("unexpected canonical header identity at block %d", number)
			}
			if coveredHeaders == 0 {
				firstHash = hash
			}
			lastHash = hash
			var numberBytes [8]byte
			binary.BigEndian.PutUint64(numberBytes[:], number)
			_, _ = digest.Write(numberBytes[:])
			_, _ = digest.Write(hash[:])

			coveredHeaders++
			syntheticCrosslinks++
			groupCrosslinks++

			encodedCrosslinks += uint64(len(header.crosslinks))
			for i := range header.crosslinks {
				crosslink := &header.crosslinks[i]
				if header.epoch.IsUint64() &&
					header.epoch.Uint64() >= rejectShard0Crosslink &&
					crosslink.ShardIDF == 0 {
					filteredShardZeroCrosslinks++
					continue
				}
				includedHeaderCrosslinks++
				includedByShard[crosslink.ShardIDF]++
				groupCrosslinks++
			}
		}
		totalRecoveryCrosslinks += groupCrosslinks
		recoveryIssuance.Add(
			recoveryIssuance,
			new(big.Int).Mul(
				new(big.Int).SetUint64(groupCrosslinks),
				hip30RecoveryAttoPerCrosslink,
			),
		)

		if time.Since(lastProgress) >= 30*time.Second {
			fmt.Fprintf(
				os.Stderr,
				"progress reward_block=%d/%d groups=%d headers=%d recovery_crosslinks=%d elapsed=%s\n",
				rewardBlock,
				lastReward,
				rewardGroups,
				coveredHeaders,
				totalRecoveryCrosslinks,
				time.Since(started).Round(time.Second),
			)
			lastProgress = time.Now()
		}
		if rewardBlock > ^uint64(0)-rewardFrequency {
			break
		}
	}

	shards := make([]uint32, 0, len(includedByShard))
	for shardID := range includedByShard {
		shards = append(shards, shardID)
	}
	sort.Slice(shards, func(i, j int) bool { return shards[i] < shards[j] })
	byShard := make([]shardCount, 0, len(shards))
	for _, shardID := range shards {
		byShard = append(byShard, shardCount{ShardID: shardID, Count: includedByShard[shardID]})
	}

	result := summary{
		DBPath:                      *dbPath,
		RequestedStartBlock:         *startBlock,
		RequestedEndBlock:           *endBlock,
		FirstRewardBlock:            firstReward,
		LastRewardBlock:             lastReward,
		FirstCoveredHeader:          firstCovered,
		LastCoveredHeader:           lastCovered,
		UnrewardedTailHeaders:       *endBlock - lastCovered,
		RewardGroups:                rewardGroups,
		CoveredBeaconHeaders:        coveredHeaders,
		SyntheticBeaconCrosslinks:   syntheticCrosslinks,
		EncodedHeaderCrosslinks:     encodedCrosslinks,
		FilteredShardZeroCrosslinks: filteredShardZeroCrosslinks,
		IncludedHeaderCrosslinks:    includedHeaderCrosslinks,
		IncludedHeaderLinksByShard:  byShard,
		TotalRecoveryCrosslinks:     totalRecoveryCrosslinks,
		RecoveryIssuanceAtto:        recoveryIssuance.String(),
		CanonicalHeaderDigestSHA256: hex.EncodeToString(digest.Sum(nil)),
		FirstCoveredHeaderHash:      firstHash,
		LastCoveredHeaderHash:       lastHash,
		FirstRewardEpoch:            firstRewardEpoch.String(),
		LastRewardEpoch:             lastRewardEpoch.String(),
		ElapsedMilliseconds:         time.Since(started).Milliseconds(),
	}
	encoder := json.NewEncoder(os.Stdout)
	encoder.SetIndent("", "  ")
	if err := encoder.Encode(result); err != nil {
		fatalf("encode summary: %v", err)
	}
}
