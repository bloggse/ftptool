from distutils.core import setup
import os

readme_fname = os.path.join(os.path.dirname(__file__), "README.rst")
readme_text = open(readme_fname).read()

setup(name="ftptool", version="0.6",
      url="https://github.com/bloggse/ftptool",
      description="Higher-level interface to ftplib",
      author="Blogg Esse AB",
      author_email="teknik@blogg.se",
      requires=["six"],
      long_description=readme_text,
      py_modules=["ftptool"])
