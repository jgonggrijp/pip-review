#! /usr/bin/env sh

pip install -U setuptools pip wheel
pip install cram
pip install .
cram --shell=/bin/bash tests/*.t
