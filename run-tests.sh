#!/bin/sh
set -e
python -m pytest tests
cram --shell=/bin/bash tests/*.t
