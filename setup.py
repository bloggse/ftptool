from distutils.core import setup
import os

f = open("README.rst")
try:
    try:
        readme_text = f.read()
    except:
        readme_text = ""
finally:
    f.close()

setup(name="ftptool", version="0.4",
    url="http://blogg.se",
    description="Higher-level interface to ftplib",
    author="Blogg Esse AB",
    author_email="opensource@blogg.se",
    long_description=readme_text,
    py_modules=["ftptool"])
