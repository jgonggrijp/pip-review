#! /usr/bin/env sh
set -e
pip install -U setuptools pip wheel
pip install cram pytest pytest-mock
pip install .
python -m pytest tests
cram --shell=/bin/bash tests/*.t
