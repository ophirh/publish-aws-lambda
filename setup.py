from setuptools import setup, find_packages
from os import path
from publish_aws_lambda import __version__

here = path.abspath(path.dirname(__file__))

setup(
    name="publish-aws-lambda",
    version=__version__,
    description="Publish a Python module as a set of AWS lambda functions",
    url="https://github.com/ophirh/publish-aws-lambda",
    author="Ophir",
    author_email="opensource@itculate.io",
    license="MIT",
    keywords=["aws", "lambda", "publish"],
    packages=find_packages(),
    install_requires=[
        "boto3>=1.4.4",
        "unix-dates>=0.4.1",
    ],
)
