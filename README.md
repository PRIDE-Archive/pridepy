# PRIDE_PY

[![PyPI version](https://badge.fury.io/py/google-api-python-client.svg)](https://badge.fury.io/py/google-api-python-client)

Python Client library for PRIDE Rest API 

# Installation
To install, simply use `pip`:

```bash
$ pip install --upgrade pride-py
```

# Examples 

Download all the raw files from a dataset(eg: PXD012353). 
Warning: Raw files are generally large in size, so it may take some time to download depending on the number of files and file sizes.

```python
$ python3 pridepy.py download -a PXD012353 -o /Users/yourname/Downloads/foldername/
```
# NOTE

Please make sure you are using Python3, not Python 2.7 version.
