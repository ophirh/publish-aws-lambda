# publish-aws-lambda

Publish a Python package as a set of AWS lambda functions.

### Does the following (given the location of a Python project) ###
1. Execute setup.py to package the project

2. Build a ZIP file with the requirements of this project (as required by AWS lambda)

3. Upload this ZIP file to S3 to the desired bucket
    * Name of the object will be the name of the Python module to be scanned

4. For each of the specified module's lambda functions (decorated with the aws_lambda decorator):
    * Create / Update / Delete the Lambda function in AWS


