# publish-aws-lambda

Publish a Python package as a set of AWS lambda functions.

### Does the following (given the location of a Python project) ###
1. Execute setup.py to package the project

2. Build a ZIP file with the requirements of this project (as required by AWS lambda)

3. Upload this ZIP file to S3 to the desired bucket
    * Name of the object will be the name of the Python module to be scanned

4. For each of the specified module's lambda functions (decorated with the aws_lambda decorator):
    * Create / Update / Delete the Lambda function in AWS



### How to create a lambda function: ###
    from publish_aws_lambda import aws_lambda
    
    @aws_lambda(role_arn="arn:aws:iam::....:role/SomeRole", timeout=5)
        def my_lambda(event, context):
            print("Hello World!!!")

### How to publish: ###
    python -m publish_aws_lambda --module=my_module --bucket=s3bucketname --requirements=requests,publish_aws_lambda
