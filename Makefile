.PHONY: setup build test test-go test-python verify verify-private manifest private-manifest check-public integration-test

setup:
	cd toolkit && GOWORK=off go mod download

build:
	./scripts/build-toolkit.sh

test: test-go test-python verify

test-go:
	./scripts/test-go.sh

test-python:
	python3 -m unittest discover -s toolkit/tests -p 'test_*.py'
	python3 -m py_compile \
		toolkit/scripts/supply/*.py \
		toolkit/scripts/forensics/*.py \
		toolkit/scripts/addresses/*.py \
		toolkit/scripts/cutoff/*.py \
		toolkit/scripts/verify/*.py \
		scripts/*.py

verify:
	python3 scripts/verify-source-manifest.py

verify-private: verify
	python3 toolkit/scripts/verify/verify-reconciliation.py
	python3 scripts/verify-results.py
	python3 scripts/verify-provenance.py

manifest:
	python3 scripts/update-source-manifest.py

private-manifest:
	python3 scripts/update-result-index.py --results results/2026-09-16
	python3 scripts/update-results-manifest.py
	python3 scripts/update-source-manifest.py

check-public:
	python3 scripts/check-public-package.py
	python3 scripts/check-numerical-embargo.py

integration-test:
	./scripts/test-harmony-integration.sh
