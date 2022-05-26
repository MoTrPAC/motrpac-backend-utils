# MoTrPAC Backend Utils

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

This package provides code used across multiple services in the MoTrPAC backend.

This package is created using the Poetry package manager.

## Getting Started

### Requirements

A Makefile is provided for your convenience.

To get started, run the following command:

```bash
make init
```

This will check you have Poetry installed and will install the dependencies. It will error if you don't have
the `protoc` compiler installed. This is a non-fatal error, if you are not going to be re-generating protobuf files, you
can ignore this.

#### Protobuf

Install the latest version of the `protoc` compiler:

##### macOS

```bash
brew install protobuf
```

*Note: as of 5/26/22 `protoc` has not been updated to the latest version on Homebrew, so you will need to manually
install it using the instructions below*

##### Manual Install

```bash
PROTOC_VERSION=21.0
PROTOC_ZIP=protoc-$PROTOC_VERSION-{REPLACE BRACKETS WITH YOUR PLATFORM (i.e. win64, osx, or linux}-$(uname -m).zip
curl -OL https://github.com/protocolbuffers/protobuf/releases/download/v$PROTOC_VERSION/$PROTOC_ZIP
sudo unzip -o $PROTOC_ZIP -d /usr/local bin/protoc
sudo unzip -o $PROTOC_ZIP -d /usr/local 'include/*'
rm -f $PROTOC_ZIP
```

### Structure

```bash
├── motrpac_backend_utils
│   ├── proto
│   │   ├── *_pb2.py
│   │   └── *_pb2.pyi
│   ├── zipper
│   │   ├── cache.py # functions for caching requests/other info used by the zipper
│   │   ├── utils.py # utility functions used by the zipper
│   │   └── zipper.py # the zipper class
│   ├── messages.py # contains functions for messaging in the backend
│   ├── requester.py # contains Requester class
│   ├── setup.py # contains functions for setting up the backend (tracing and logging)
│   └── utils.py # utility functions used by the backend
├── proto
│   ├── file_download.proto
│   └── notification.proto
├── pyproject.toml
├── poetry.lock
├── README.md
└── .gitignore
```

#### `/proto`

The `proto` directory contains the protobuf files used by the backend.

#### `/motrpac_backend_utils/proto/`

This folder contains auto-generated Python code for the protobuf files located in `/proto`

In addition, it contains the Python type definitions for the auto-generated Python files, located in the `*.pyi` files

#### `/motrpac_backend_utils/setup.py`

This contains functions for initializing Google Cloud Logging and Google Cloud Tracing.

It reads an environment variable called `PRODUCTION_DEPLOYMENT` to determine whether to send logs and traces to the
Google Cloud Logging and Google Cloud Tracing services. This can be a boolean value, or a string that can be 0 or 1.

## Zipper

### Overview

The zipper module contains the `ZipUploader` class which allows for asynchronous creation of a zip file from a list of
files hosted in a single Google Cloud Storage bucket. It then uploads the completed zip file to another Google Cloud
Storage Bucket.

The requested files are hashed in order to create a unique zip file name, and also to identify duplicate requests. Any
duplicate requests are ignored, but their requesters are added to a list of requesters, who then get notified when the
zip file is created.

It is able to process multiple requests for zip files concurrently using the `multiprocessing` module.

It caches common input files in the same location to reduce transfer costs. If multiple zip processes request the same
file, the process which has already started downloading the file will continue, and the other processes will wait for
completion.

This class is designed to be used with or without Pub/Sub message that would have sent the zip request. If the message
is provided, then the message's ack deadline will be extended to the maximum of the ack deadline of the message and the
process will continue.

After completion of a zip file's creation a notification can be sent to a URL, using the notification protobuf defined
in the `proto` directory.

### Usage

If using any of the messaging functions in `motrpac_backend_utils.messages` or the `Requester` class
in `motrpac_backend_utils.requester`, ensure you `pip` install with the `messaging` feature enabled.

```bash
pip install -e git+https://github.com/MoTrPAC/motrpac-backend-utils.git#egg=motrpac_backend_utils[messaging]
```

*If using `zsh`, make sure to quote the url, like so:*

```bash
pip install -e  "git+https://github.com/MoTrPAC/motrpac-backend-utils.git#egg=motrpac_backend_utils[messaging]"
```

If using any of the zipper functions in `motrpac_backend_utils.zipper`, the `messaging` feature is automatically
enabled, but the `zipper` feature must be enabled.

```bash
pip install -e git+https://github.com/MoTrPAC/motrpac-backend-utils.git#egg=motrpac_backend_utils[zipper]
```
