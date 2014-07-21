from setuptools import setup

import marquise.marquise
extension = marquise.marquise.ffi.verifier.get_extension()

with open('VERSION', 'r') as f:
	VERSION = f.readline().strip()


# These notes suggest that there's not yet any "correct" way to do packageable
# CFFI interfaces. For now I'm splitting the CFFI stuff from the python
# interface stuff, and it seems to do the job okay, though dealing with
# packages and modules is a flailfest at best for me.
# https://bitbucket.org/cffi/cffi/issue/109/enable-sane-packaging-for-cffi

setup(
    name="marquise",
    version=VERSION,
    description="Python bindings for libmarquise",
    author="Sharif Olorin",
    author_email="sio@tesser.org",
    url="https://github.com/anchor/pymarquise",
    zip_safe=False,
    packages=[
        "marquise",
    ],
    ext_modules = [extension],
)
