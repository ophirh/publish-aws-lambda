from setuptools import setup, find_packages
from os import path

here = path.abspath(path.dirname(__file__))

setup(
    name="publish-aws-lambda",
    version="0.4.1",
    description="Publish a Python module as a set of AWS lambda functions",
    url="https://github.com/ophirh/publish-aws-lambda",
    author="Ophir",
    author_email="opensource@itculate.io",
    license="MIT",
    keywords=["aws", "lambda", "publish"],
    packages=find_packages(),
)
