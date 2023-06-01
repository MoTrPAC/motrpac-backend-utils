# Changelog

All notable changes to this project will be documented in this file.

## [0.1.14] - 2023-06-01

### Features

- Update typing stubs of protobuf messages

### Miscellaneous Tasks

- Bump requirements
- Change priority of Python versions
- Fix license
- Bump version to 0.1.14

### Styling

- Run ruff on package

## [0.1.13] - 2023-01-30

### Features

- Add Flask Cloud Trace filter to package

### Miscellaneous Tasks

- Add Flask to project optional dependencies
- Bump version to 0.1.13

### Styling

- Apply Black to project

## [0.1.12] - 2022-11-03

### Bug Fixes

- Don't write logs to StreamHandlers when in production mode

### Miscellaneous Tasks

- Bump version to 0.1.12

## [0.1.11] - 2022-08-31

### Miscellaneous Tasks

- Add changelog, .python-version for pyenv, and update README.md
- Bump dependencies, fix conflicts caused by opentelemetry's non-semantic versioning
- Bump version to 0.1.11

## [0.1.10] - 2022-08-11

### Miscellaneous Tasks

- Update type annotations
- Delete dist/ directory
- Bump deps
- Bump version to 0.1.10

### Refactor

- Move threadpool code into threadpool.py so that a threadpool doesn't get created when importing utils

## [0.1.9] - 2022-05-27

### Bug Fixes

- Fix for if os.cpu_count() returns a value less than 4
- Bug fixes, type annotations

### Documentation

- Update documentation to reflect v3.20.1 protoc/protobuf requirement

### Miscellaneous Tasks

- Add .mypy_cache/ to .gitignore
- Bump dependencies
- Bump version to 0.1.9

## [0.1.8] - 2022-05-26

### Bug Fixes

- Make fixes based on mypy/pylint/flake8 recommendations
- Regenerate protobuf files

### Documentation

- Update README.md

### Miscellaneous Tasks

- Fix Makefile, remove mypy protoc plugin
- Add additional development dependencies
- Bump version to 0.1.8

## [0.1.7] - 2022-05-26

### Documentation

- Update documentation

### Miscellaneous Tasks

- Use typing extensions if python version < 3.10
- Make some zipper dependencies optional/enabled via extras
- Bump version to 0.1.7

## [0.1.6] - 2022-05-26

### Bug Fixes

- Fix circular imports

### Miscellaneous Tasks

- Bump version to 0.1.6

## [0.1.5] - 2022-05-26

### Miscellaneous Tasks

- Update documentation to better describe the zipper module
- Add license/copyright info
- Bump version to 0.1.5

## [0.1.4] - 2022-05-26

### Bug Fixes

- Use relative imports

### Documentation

- Update documentation formatting

### Miscellaneous Tasks

- Bump project version

## [0.1.3] - 2022-05-21

### Features

- Add decode message

## [0.1.2] - 2022-05-21

### Bug Fixes

- Update ZipUploader __init__.py function signature

### Miscellaneous Tasks

- Add Makefile

## [0.1.1] - 2022-05-20

### Documentation

- Add README.md

### Miscellaneous Tasks

- Bump version

## [0.1.0] - 2022-05-20

### Bug Fixes

- Add fixes for non-existent imports
- Add ProtoBufs and corresponding auto-generated files

### Features

- Create Python packages
- Add README.md
- Finish up package

### Miscellaneous Tasks

- Add development dependencies

### Refactor

- Continue consolidating common code to a private package
- Move .gitignore
- Move packages to top-level

