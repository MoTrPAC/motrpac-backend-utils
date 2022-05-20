# Packages

## MoTrPAC Backend Utils

This package provides code used across multiple services in the MoTrPAC backend.

This package is created using the Poetry package manager.

It is hosted in a private Google Artifact Registry.

### Getting Started

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
