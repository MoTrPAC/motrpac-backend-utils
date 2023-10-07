CWD := $(abspath $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST))))))
PROTO_DIR = motrpac_backend_utils/proto
PROTO_PATH = proto
VENV_PATH := $(shell poetry env info --path)

.PHONY: help
help:
	@# Magic line used to create self-documenting makefiles.
	@# See https://stackoverflow.com/a/35730928
	@awk '/^#/{c=substr($$0,3);next}c&&/^[[:alpha:]][[:alnum:]_-]+:/{print substr($$1,1,index($$1,":")),c}1{c=0}' Makefile | column -s: -t

.PHONY: init
# Initialize all dependencies
init: get-poetry venv-init check-requirements

.PHONY: check-requirements
# Check if all dependencies are installed
check-requirements:
	if ! command -v protoc &> /dev/null; then \
		echo "Protobuf compiler is not installed. Please install it first."; \
		ERROR = 1; \
	fi
	if [ -n "$(ERROR)" ]; then \
		exit 1; \
	fi

.PHONY: get-poetry
# Install Poetry if it doesn't exist
get-poetry:
	if ! command -v poetry &> /dev/null; then \
    	curl -sSL https://install.python-poetry.org | python3 - ; \
	fi

.PHONY: venv-init
# initialize Prototyping
venv-init:
	poetry install

.PHONY: protobuf-init
# generate protobuf files from the proto files
protobuf-init:
	protoc --proto_path=$(CWD)/$(PROTO_PATH) --python_out=$(CWD)/$(PROTO_DIR) --pyi_out=$(CWD)/$(PROTO_DIR) file_download.proto notification.proto

# Define a function for common steps in version bumping
define bump_version
	poetry version $(1) ; \
	VERSION=$$(poetry version | sed "s/motrpac-backend-utils[[:space:]]//g") ; \
	git add pyproject.toml ; \
	git commit -m "chore(release): bump version to $$VERSION" ; \
	git tag -a v$$VERSION -m "chore(release: bump version to $$VERSION)" ; \
	git cliff > CHANGELOG.md ; \
	git add CHANGELOG.md ; \
	git commit -m "chore(release): update CHANGELOG.md"
endef

# Use the function for patch and minor version bumping targets

version-patch:
	$(call bump_version,patch)

version-minor:
	$(call bump_version,minor)
