CWD := $(abspath $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST))))))
PROTO_DIR = src/motrpac_backend_utils/proto
PROTO_PATH = proto
VENV_PATH := $(CWD)/.venv/bin

IS_DARWIN := $(shell uname -s | grep Darwin)

.PHONY: help
help:
	@# Magic line used to create self-documenting makefiles.
	@# See https://stackoverflow.com/a/35730928
	@awk '/^#/{c=substr($$0,3);next}c&&/^[[:alpha:]][[:alnum:]_-]+:/{print substr($$1,1,index($$1,":")),c}1{c=0}' Makefile | column -s: -t

.PHONY: init
# Initialize all dependencies
init: check-requirements venv-init

.PHONY: check-requirements
# Check if all dependencies are installed
check-requirements:
	if ! command -v protoc &> /dev/null; then \
		echo "Protobuf compiler is not installed. Please install it first."; \
		ERROR = 1; \
	fi; \
	if ! command -v uv &> /dev/null; then \
		echo "\`uv\` is not installed. Please install it before continuing."; \
		ERROR = 1; \
  fi; \
	if [ -n "$(ERROR)" ]; then \
		exit 1; \
	fi

.PHONY: venv-init
# initialize Prototyping
venv-init:
	uv sync --all-groups --all-extras

.PHONY: test
# Run tests for the package
test:
	uv run pytest

.PHONY: protobuf-init
# generate protobuf files from the proto files
protobuf-init:
	protoc --proto_path=$(CWD)/$(PROTO_PATH) --python_out=$(CWD)/$(PROTO_DIR) --pyi_out=$(CWD)/$(PROTO_DIR) file_download.proto notification.proto

define bump_version
	echo "✅  $(1) release: bumping version" ; \
	uv version --bump $(1) ; \
	uv sync --all-groups --all-extras ;
endef

define release_version
	NEW_VERSION=$$(uv version --short) ; \
	git add pyproject.toml uv.lock ; \
	git commit -m "chore(release): bump version to $$NEW_VERSION" ; \
	git tag -a v$$NEW_VERSION -m "chore(release: bump version to $$NEW_VERSION)" ; \
	git cliff > CHANGELOG.md ; \
	git add CHANGELOG.md ; \
	git commit -m "chore(release): update CHANGELOG.md" ;
endef

# Use the function for patch and minor version bumping targets
version-patch:
	$(call bump_version,patch)
	$(call release_version)

version-minor:
	$(call bump_version,minor)
	$(call release_version)

version-major:
	$(call bump_version,major)
	$(call release_version)
