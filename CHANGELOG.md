# Changelog

All notable changes to this project will be documented in this file.

## [0.9.4] - 2025-11-02

### Bug Fixes

- Remove key from DownloadRequestFileModel

### Features

- Update DownloadRequestModel to improve documentation and enhance hash generation method

### Miscellaneous Tasks

- *(deps)* Bump the google group with 2 updates
- *(deps)* Bump the monitoring group with 7 updates
- *(deps)* Bump the storage group with 3 updates
- *(deps)* Bump the tools group with 4 updates
- Remove outdated REPOSITORY.md file
- Add Dependabot configuration for dependency and CI updates
- Add CI workflow for testing on develop, fix/*, and feat/* branches
- Add test target to Makefile
- Add main branch to CI target
- Do not use self hosted runners for public repo
- Remove isort from deps
- Remove black and isort from dependabot config

### Refactor

- Update ID token fetching in utils.py to use google.oauth2 for improved authentication
- Rename smart_open to avoid shadowing built-in

### Testing

- Update tests for get_authorized_sessions

## [0.9.1] - 2025-10-20

### Bug Fixes

- Add minimum requirement for opentelemetry-exporter-gcp-trace

## [0.9.0] - 2025-10-19

### Bug Fixes

- Update type handling, format code

### Features

- Integrate ThreadingInstrumentor into tracing setup
- Enhance logging setup with TraceIdInjectionFilter

### Miscellaneous Tasks

- Update dependencies and Python version constraints in pyproject.toml and uv.lock
- Update .gitignore
- Update release workflow to sync dependencies and include uv.lock

### Refactor

- Update test files for consistency and modernize syntax

## [0.8.0] - 2025-03-16

### Features

- Add new tracing setup for better flexibility

## [0.7.1] - 2024-06-19

### Miscellaneous Tasks

- Update Makefile version bump script now that poetry is no longer being used

### Refactor

- Move to `src`-layout, change test directory to `tests/`

### Build

- Replace poetry with uv and hatch

## [0.7.0] - 2024-04-16

### Features

- [**breaking**] Remove flask request id log filter
- Add OpenTelemetry record attribute injector

### Miscellaneous Tasks

- *(deps)* Bump dependencies

### Styling

- Update ruff config, run ruff lint

## [0.6.7] - 2024-02-23

### Miscellaneous Tasks

- Update protobuf files

## [0.6.6] - 2024-02-21

### Bug Fixes

- Update Flask logger for Flask >3

## [0.6.5] - 2024-02-19

### Bug Fixes

- Fix logging format (fr this time)

### Miscellaneous Tasks

- Update package deps

## [0.6.4] - 2024-02-19

### Bug Fixes

- Fix logging format

## [0.6.3] - 2024-02-14

### Features

- Add CloudTraceIDFilter to log records

### Miscellaneous Tasks

- Update copyright comments on all files

## [0.6.2] - 2024-02-12

### Miscellaneous Tasks

- Bump package versions

## [0.6.1] - 2023-10-10

### Miscellaneous Tasks

- Code cleanup

## [0.6.0] - 2023-10-09

### Features

- Update protobufs to make the ID field optional

## [0.5.0] - 2023-10-07

### Features

- Add user id field to protobufs

### Miscellaneous Tasks

- Make bump version targets DRY

### Build

- Add version patch automation to Makefile

## [0.4.1] - 2023-07-29

### Bug Fixes

- Remove potential bug in zipper utility

## [0.4.0] - 2023-07-28

### Features

- Add custom BlobNotFoundError class and modify blob handling
- [**breaking**] Extracted common Requester class from Message protobufs
- [**breaking**] Revert "extracted common Requester class from Message protobufs"

### Refactor

- Remove deprecated 'zipper' file, move content to '__init__' module
- Threadpool decorator and its tests

## [0.2.1] - 2023-06-05

### Features

- Allow overriding env var via argument to setup_logging_and_tracing function

## [0.2.0] - 2023-06-04

### Bug Fixes

- Remove unnecessary argument from ZipUploadError

### Testing

- Add more tests

## [0.1.19] - 2023-06-03

### Bug Fixes

- Fix erroneous code detected by tests

### Testing

- Add tests for messages and threadpool

## [0.1.18] - 2023-06-03

### Bug Fixes

- Add default argument to threadpool class
- Remove stack_info argument from exception logs

### Documentation

- Document the filter method of the FlaskCloudTraceIDFilter class

### Features

- Add opentelemetry tracing to Pub/Sub publish calls

### Refactor

- See if this type annotation works for the Value field

## [0.1.17] - 2023-06-02

### Bug Fixes

- Invalid type annotation

### Miscellaneous Tasks

- Add cliff.toml for changelog generation

## [0.1.16] - 2023-06-02

### Bug Fixes

- Type-checking bug fix

## [0.1.15] - 2023-06-02

### Miscellaneous Tasks

- *(deps)* Bump protobuf library requirement
- Update protoc generated python files

## [0.1.14] - 2023-06-02

### Features

- Update typing stubs of protobuf messages

### Miscellaneous Tasks

- *(deps)* Bump requirements
- Change priority of Python versions
- Fix license

### Styling

- Run ruff on package

## [0.1.13] - 2023-06-02

### Features

- Add Flask Cloud Trace filter to package

### Miscellaneous Tasks

- *(deps)* Add Flask to project optional dependencies

### Styling

- Apply Black to project

## [0.1.12] - 2023-06-02

### Bug Fixes

- Don't write logs to StreamHandlers when in production mode

## [0.1.11] - 2023-06-02

### Bug Fixes

- Bump dependencies, fix conflicts caused by opentelemetry's non-semantic versioning

### Miscellaneous Tasks

- Add changelog, .python-version for pyenv, and update README.md

## [0.1.10] - 2023-06-02

### Miscellaneous Tasks

- *(deps)* Bump deps
- Delete dist/ directory

### Refactor

- Update type annotations
- Move threadpool code into threadpool.py so that a threadpool doesn't get created when importing utils

## [0.1.9] - 2023-06-02

### Bug Fixes

- Fix for if os.cpu_count() returns a value less than 4
- Bug fixes, type annotations

### Documentation

- Update documentation to reflect v3.20.1 protoc/protobuf requirement

### Miscellaneous Tasks

- *(deps)* Bump dependencies
- Add .mypy_cache/ to .gitignore

## [0.1.8] - 2023-06-02

### Bug Fixes

- Make fixes based on mypy/pylint/flake8 recommendations
- Regenerate protobuf files

### Documentation

- Update README.md

### Miscellaneous Tasks

- *(deps)* Add additional development dependencies
- Fix Makefile, remove mypy protoc plugin

## [0.1.7] - 2023-06-02

### Bug Fixes

- Use typing extensions if python version < 3.10

### Documentation

- Update documentation

### Miscellaneous Tasks

- Make some zipper dependencies optional/enabled via extras

## [0.1.6] - 2023-06-02

### Bug Fixes

- Fix circular imports

## [0.1.5] - 2023-06-02

### Miscellaneous Tasks

- Update documentation to better describe the zipper module
- Add license/copyright info

## [0.1.4] - 2023-06-02

### Bug Fixes

- Use relative imports

### Documentation

- Update documentation formatting

## [0.1.3] - 2023-06-02

### Features

- Add decode message

## [0.1.2] - 2023-06-02

### Bug Fixes

- Update ZipUploader __init__.py function signature

### Miscellaneous Tasks

- Add Makefile

## [0.1.1] - 2023-06-02

### Documentation

- Add README.md

## [0.1.0] - 2023-06-02

### Bug Fixes

- Add fixes for non-existent imports
- Add ProtoBufs and corresponding auto-generated files

### Features

- Create Python packages
- Add README.md

### Miscellaneous Tasks

- *(deps)* Add development dependencies

### Refactor

- Continue consolidating common code to a private package
- Move .gitignore
- Move packages to top-level


