from distutils.core import setup
import os

readme_fname = os.path.join(os.path.dirname(__file__), "README.rst")
readme_text = open(readme_fname).read()

setup(name="ftptool", version="0.6",
    url="http://blogg.se",
    description="Higher-level interface to ftplib",
    author="Blogg Esse AB",
    author_email="opensource@blogg.se",
    long_description=readme_text,
    py_modules=["ftptool"])
