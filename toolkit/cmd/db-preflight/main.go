package main

import (
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"strings"

	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/core/rawdb"
	"github.com/ethereum/go-ethereum/crypto"
	"github.com/ethereum/go-ethereum/ethdb/leveldb"
	"github.com/ethereum/go-ethereum/trie"
)

type manifest struct {
	SchemaVersion int             `json:"schema_version"`
	Shards        []shardManifest `json:"shards"`
}

type shardManifest struct {
	ShardID                   uint32       `json:"shard_id"`
	RequireValidatorList      bool         `json:"require_validator_list"`
	RewardAccumulatorAtBlocks []uint64     `json:"reward_accumulator_at_blocks"`
	Checkpoints               []checkpoint `json:"checkpoints"`
}

type checkpoint struct {
	Name        string `json:"name"`
	Block       uint64 `json:"block"`
	Hash        string `json:"hash"`
	StateRoot   string `json:"state_root,omitempty"`
	RequireBody bool   `json:"require_body,omitempty"`
}

type checkpointResult struct {
	Name          string `json:"name"`
	Block         uint64 `json:"block"`
	Hash          string `json:"hash"`
	HeaderFound   bool   `json:"header_found"`
	BodyFound     bool   `json:"body_found"`
	StateRoot     string `json:"state_root,omitempty"`
	StateTrieOpen bool   `json:"state_trie_open,omitempty"`
}

type result struct {
	SchemaVersion           int                `json:"schema_version"`
	Status                  string             `json:"status"`
	ShardID                 uint32             `json:"shard_id"`
	ValidatorListFound      bool               `json:"validator_list_found"`
	RewardAccumulatorsFound []uint64           `json:"reward_accumulators_found"`
	Checkpoints             []checkpointResult `json:"checkpoints"`
}

func fatalf(format string, args ...interface{}) {
	fmt.Fprintf(os.Stderr, "fatal: "+format+"\n", args...)
	os.Exit(1)
}

func parseHash(text string, label string) common.Hash {
	decoded, err := hex.DecodeString(strings.TrimPrefix(text, "0x"))
	if err != nil || len(decoded) != common.HashLength {
		fatalf("invalid %s %q", label, text)
	}
	return common.BytesToHash(decoded)
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

func storedBodyKey(number uint64, hash common.Hash) []byte {
	key := make([]byte, 1+8+common.HashLength)
	key[0] = 'b'
	binary.BigEndian.PutUint64(key[1:9], number)
	copy(key[9:], hash[:])
	return key
}

func rewardAccumulatorKey(number uint64) []byte {
	key := make([]byte, len("blk-rwd-")+8)
	copy(key, "blk-rwd-")
	binary.BigEndian.PutUint64(key[len("blk-rwd-"):], number)
	return key
}

func loadManifest(path string, shardID uint32) shardManifest {
	encoded, err := os.ReadFile(path)
	if err != nil {
		fatalf("read checkpoint manifest: %v", err)
	}
	var all manifest
	if err := json.Unmarshal(encoded, &all); err != nil {
		fatalf("decode checkpoint manifest: %v", err)
	}
	if all.SchemaVersion != 1 {
		fatalf("unsupported checkpoint manifest schema %d", all.SchemaVersion)
	}
	for _, shard := range all.Shards {
		if shard.ShardID == shardID {
			return shard
		}
	}
	fatalf("checkpoint manifest has no shard %d", shardID)
	return shardManifest{}
}

func writeResult(path string, value result) {
	encoded, err := json.MarshalIndent(value, "", "  ")
	if err != nil {
		fatalf("encode result: %v", err)
	}
	encoded = append(encoded, '\n')
	if path == "" {
		if _, err := os.Stdout.Write(encoded); err != nil {
			fatalf("write stdout: %v", err)
		}
		return
	}
	partial := path + ".partial"
	if _, err := os.Stat(path); err == nil {
		fatalf("output already exists: %s", path)
	} else if !os.IsNotExist(err) {
		fatalf("inspect output: %v", err)
	}
	file, err := os.OpenFile(partial, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o600)
	if err != nil {
		fatalf("create partial output: %v", err)
	}
	ok := false
	defer func() {
		_ = file.Close()
		if !ok {
			_ = os.Remove(partial)
		}
	}()
	if _, err := file.Write(encoded); err != nil {
		fatalf("write output: %v", err)
	}
	if err := file.Sync(); err != nil {
		fatalf("sync output: %v", err)
	}
	if err := file.Close(); err != nil {
		fatalf("close output: %v", err)
	}
	if err := os.Rename(partial, path); err != nil {
		fatalf("publish output: %v", err)
	}
	ok = true
}

func main() {
	var (
		dbPath       = flag.String("db", "", "path to a stopped or cold Harmony LevelDB")
		manifestPath = flag.String("checkpoints", "", "checkpoint manifest JSON")
		shardID      = flag.Uint64("shard", 0, "expected shard ID")
		outputPath   = flag.String("output", "", "deterministic JSON output; stdout when empty")
		cacheMB      = flag.Int("cache-mb", 64, "LevelDB/trie cache in MiB")
		handles      = flag.Int("handles", 64, "LevelDB open-file handles")
	)
	flag.Parse()
	if *dbPath == "" || *manifestPath == "" {
		flag.Usage()
		os.Exit(2)
	}
	if *shardID > uint64(^uint32(0)) {
		fatalf("shard ID is too large")
	}
	shard := loadManifest(*manifestPath, uint32(*shardID))

	disk, err := leveldb.New(*dbPath, *cacheMB, *handles, "", true)
	if err != nil {
		fatalf("open source database read-only (stop the node first): %v", err)
	}
	db := rawdb.NewDatabase(disk)
	defer db.Close()

	output := result{
		SchemaVersion: 1,
		Status:        "passed",
		ShardID:       shard.ShardID,
		Checkpoints:   make([]checkpointResult, 0, len(shard.Checkpoints)),
	}
	if shard.RequireValidatorList {
		if encoded, err := db.Get([]byte("validator-list")); err != nil || len(encoded) == 0 {
			fatalf("validator-list is missing")
		}
		output.ValidatorListFound = true
	}
	for _, number := range shard.RewardAccumulatorAtBlocks {
		if encoded, err := db.Get(rewardAccumulatorKey(number)); err != nil || len(encoded) == 0 {
			fatalf("reward accumulator is missing at block %d", number)
		}
		output.RewardAccumulatorsFound = append(output.RewardAccumulatorsFound, number)
	}

	trieDB := trie.NewDatabase(db)
	for _, expected := range shard.Checkpoints {
		wantHash := parseHash(expected.Hash, "block hash")
		gotHashBytes, err := db.Get(canonicalHashKey(expected.Block))
		if err != nil {
			fatalf("read canonical hash at block %d: %v", expected.Block, err)
		}
		gotHash := common.BytesToHash(gotHashBytes)
		if len(gotHashBytes) != common.HashLength || gotHash != wantHash {
			fatalf("canonical hash mismatch at block %d: got %s want %s", expected.Block, gotHash.Hex(), wantHash.Hex())
		}
		header, err := db.Get(storedHeaderKey(expected.Block, wantHash))
		if err != nil || len(header) == 0 {
			fatalf("canonical header is missing at block %d", expected.Block)
		}
		if crypto.Keccak256Hash(header) != wantHash {
			fatalf("stored header hash mismatch at block %d", expected.Block)
		}

		checked := checkpointResult{
			Name:        expected.Name,
			Block:       expected.Block,
			Hash:        wantHash.Hex(),
			HeaderFound: true,
		}
		if expected.RequireBody {
			body, err := db.Get(storedBodyKey(expected.Block, wantHash))
			if err != nil || len(body) == 0 {
				fatalf("canonical body is missing at block %d", expected.Block)
			}
			checked.BodyFound = true
		}
		if expected.StateRoot != "" {
			root := parseHash(expected.StateRoot, "state root")
			stateTrie, err := trie.NewStateTrie(trie.StateTrieID(root), trieDB)
			if err != nil {
				fatalf("open state trie %s at checkpoint %s: %v", root.Hex(), expected.Name, err)
			}
			if stateTrie.Hash() != root {
				fatalf("state trie root mismatch at checkpoint %s", expected.Name)
			}
			checked.StateRoot = root.Hex()
			checked.StateTrieOpen = true
		}
		output.Checkpoints = append(output.Checkpoints, checked)
	}
	writeResult(*outputPath, output)
}
