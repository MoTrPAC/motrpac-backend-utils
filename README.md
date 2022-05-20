# Packages

## MoTrPAC Backend Utils

This package provides code used across multiple services in the MoTrPAC backend.

This package is created using the Poetry package manager.

### Getting Started

#### Structure

```bash
├── motrpac_backend_utils
│   ├── proto
│   │   ├── *_pb2.py
│   │   └── *_pb2.pyi
│   ├── zipper
│   │   ├── utils.py # utility functions used by the zipper
│   │   └── zipper.py # the zipper class
│   ├── messages.py # contains functions for messaging in the backend
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

##### `/proto`

The `proto` directory contains the protobuf files used by the backend.

##### `/motrpac_backend_utils/proto/`

This folder contains auto-generated Python code for the protobuf files located in `/proto`

In addition, it contains the Python type definitions for the auto-generated Python files, located in the `*.pyi` files

##### `/motrpac_backend_utils/setup.py`

This contains functions for initializing Google Cloud Logging and Google Cloud Tracing.

It reads an environment variable called `PRODUCTION_DEPLOYMENT` to determine whether to send logs and traces to the
Google Cloud Logging and Google Cloud Tracing services. This can be a boolean value, or a string that can be 0 or 1.

### Google Artifact Registry

It is hosted in a private Google Artifact Registry.

#### Getting Started

First install all dependencies

```bash
cd packages/motrpac-backend-utils
poetry install
```

In order to authenticate with Google Artifact Registry, you should install `keyring`
and `keyrings.google-artifactregistry-auth`:

```bash
pip install keyring keyrings.google-artifactregistry-auth
# Confirm that the backend was successfully installed
keyring --list-backends
# Confirm that the list includes:
# ChainerBackend(priority:10)
# GooglePythonAuth(priority: 9)
```

Then you can generate the settings that you need to add to certain local files in order to authenticate with the
registry:

```bash
gcloud artifacts print-settings python --project=<project> \
    --repository=<repository> \
    --location=<region>
```

Your `pip.conf` should be located in the virtualenv created by Poetry

You can run `poetry env info` to view the path of the virtual environment

```bash
Virtualenv
Python:         3.9.10
Implementation: CPython
# this is the generated virtual environment
Path:           /Users/user/Library/Caches/pypoetry/virtualenvs/motrpac-backend-utils-zxT_a_A5-py3.9
Valid:          True

System
Platform: darwin
OS:       posix
Python:   /Users/user/.pyenv/versions/3.9.10
```

### Building the package

```bash
poetry build
twine upload --repository-url https://<region>-python.pkg.dev/<project>/<repo>/ dist/*
```
