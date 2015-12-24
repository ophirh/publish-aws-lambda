#!/usr/bin/env bash

echo Create a AWS Lambda package

rm -rf ./lambda
mkdir ./lambda

pip install . -t lambda
pip install requests -t lambda

cd lambda
zip lambda.zip -r *

cd ..
mv ./lambda/lambda.zip .
