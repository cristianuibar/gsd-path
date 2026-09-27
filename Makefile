# GSD Path — developer test entrypoints
# Full guide: TEST_ENVIRONMENT.md

.PHONY: help install check-prereqs test test-smoke test-integration test-sync verify verify-release test-e2e test-daemon

help:
	@echo "GSD Path test targets"
	@echo "  make install          npm ci (lockfile-respecting dependencies)"
	@echo "  make check-prereqs    verify Node/Python/git toolchain"
	@echo "  make test-smoke       Node installer/wizard/package tests (~15s)"
	@echo "  make test-integration Python unittest suite (offline disk contract)"
	@echo "  make test-sync        generated skill-resource sync check"
	@echo "  make verify           smoke + integration + sync (CI gate)"
	@echo "  make verify-release   verify + trust-evidence receipt check"
	@echo "  make test-daemon      daemon-only unittest subset"
	@echo "  make test-e2e         live dogfood (requires GSD_E2E_HOST + API key)"
	@echo
	@echo "Default contributor path: make install && make verify"

install:
	npm ci

check-prereqs:
	@npm run --silent check:prereqs

test-smoke:
	npm test

test-integration:
	npm run test:python

test-sync:
	npm run test:sync

verify:
	npm run verify

verify-release:
	npm run verify:release

test-daemon:
	npm run test:daemon

test-e2e:
	@test -n "$$GSD_E2E_HOST" || (echo "Set GSD_E2E_HOST=claude or codex (see TEST_ENVIRONMENT.md)" >&2; exit 1)
	node scripts/dev/py.mjs tests/dogfood.py --host "$$GSD_E2E_HOST" --evidence "$${GSD_E2E_EVIDENCE:-/tmp/gsd-path-e2e-evidence}"

test: verify
