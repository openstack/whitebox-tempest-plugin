#!/bin/bash
# build dist tarball
python setup.py sdist
# check dist tarball
twine check dist/*
