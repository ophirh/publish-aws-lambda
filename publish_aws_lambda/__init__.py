"""
Publish the a python package as AWS lambdas functions.
"""

from __future__ import print_function
import os
import pprint
import shutil
import types
import boto3
from unix_dates import UnixDate

lambda_client = boto3.client("lambda")
s3_client = boto3.client("s3")


def aws_lambda(role_arn, timeout=60, memory=128, description=""):
    def decorator(func):
        """
        Decorator to help identify which of the methods in a module are AWS Lambda functions.

        Note that this IS NOT a typical decorator. The only thing it does is add a private attribute to the function to
        mark it as an AWS lambda.
        """

        func.__aws_lambda__ = True
        func.__aws_lambda_role__ = role_arn
        func.__aws_lambda_timeout__ = timeout
        func.__aws_lambda_memory__ = memory
        func.__aws_lambda_description__ = description

        return func

    return decorator


def get_all_lambda_functions_in_module(module_name):
    """
    Given a module (fully qualified module name), will return all the functions that are identified (using the
    aws_lambda decorator) as lambda functions.

    :param module_name: Fully qualified module name
    :return: List of all lambda function identified in the module
    :rtype: list
    """

    module = __import__(module_name, fromlist="*")

    lambda_functions = []

    for a in dir(module):
        attribute = getattr(module, a)
        if not isinstance(attribute, types.FunctionType):
            continue

        if "__aws_lambda__" in dir(attribute):
            lambda_functions.append(attribute)

    return lambda_functions


def plan(module_name):
    """
    Create a plan of upgrade existing AWS lambda functions with latest for this module.
    """
    module_functions = {fn.__name__: fn for fn in get_all_lambda_functions_in_module(module_name)}
    aws_functions = {fn["FunctionName"]: fn for fn in lambda_client.list_functions()["Functions"] if
                     fn["Handler"].startswith(module_name)}

    to_create = {k: fn for k, fn in module_functions.iteritems() if k not in aws_functions}
    to_delete = {k: fn for k, fn in aws_functions.iteritems() if k not in module_functions}

    last_modified = os.path.getmtime(__import__(module_name).__file__)

    # Examine the ones to update to see if anything changed...
    to_update, unchanged = {}, set()
    for k, aws_function in aws_functions.iteritems():
        module_function = module_functions.get(k)
        if not module_function:
            # We are looking for the ones that are in BOTH lists (to update / unchanged)
            continue

        changed = False
        changes = set()

        if aws_function["Role"] != module_function.__aws_lambda_role__:
            changed = True
            changes.add("Role")

        if aws_function["MemorySize"] != module_function.__aws_lambda_memory__:
            changed = True
            changes.add("MemorySize")

        if aws_function["Timeout"] != module_function.__aws_lambda_timeout__:
            changed = True
            changes.add("Timeout")

        # Check last modified (need to be within reasonable delta)
        if UnixDate.to_unix_time_from_iso_format(aws_function["LastModified"]) < last_modified:
            changed = True
            changes.add("Code")

        if changed:
            to_update[k] = (aws_function, module_function, changes)
        else:
            unchanged.add(k)

    return to_create, to_update, to_delete, unchanged


def print_plan(module, to_create, to_update, to_delete, unchanged):
    # Group updates by reason
    update_with_reason = {(k, d[2]) for k, d in to_update.iteritems()}

    pprint.pprint("The plan is (for module {}):".format(module))
    pprint.pprint("   Create: {}".format(to_create.keys()))
    pprint.pprint("   Delete: {}".format(to_delete.keys()))
    pprint.pprint("   Update: {}".format(update_with_reason))
    pprint.pprint("   Unchanged: {}".format(unchanged))


def package_and_upload_module(root_dir, requirements, module_name, bucket):
    """

    :type root_dir: str
    :type requirements: list[str]
    :type bucket: str
    """

    assert os.path.isdir(root_dir)
    assert isinstance(requirements, list)

    # Clean up first (from any previous installation)
    lambda_dir = os.path.join(root_dir, "lambda")
    if os.path.exists(lambda_dir):
        shutil.rmtree(lambda_dir)

    lambda_zip = os.path.join(root_dir, "lambda.zip")
    if os.path.exists(lambda_zip):
        os.remove(lambda_zip)

    os.makedirs(lambda_dir)

    # Install the required packages
    import pip
    pip.main(["install", ".", "-t", "lambda"])

    for pkg in requirements:
        pip.main(["install", pkg, "-t", "lambda"])

    # ZIP it up!
    shutil.make_archive("lambda", "zip", lambda_dir)

    # And upload to S3 (use module as object key)
    s3_client.upload_file(Filename=lambda_zip,
                          Bucket=bucket,
                          Key=module_name,
                          ExtraArgs={'ACL': 'bucket-owner-full-control'})

    print("Uploaded {} to S3 bucket {} as {}".format(lambda_zip, bucket, module_name))

    return module_name


def publish(root_dir, module_name, requirements, bucket):
    """
    Actually perform the publish / sync of the lambda functions. This includes packaging the lambda functions in this
    module, uploading it to S3 and then setting up the lambda function configuration

    :type root_dir: str
    :type module_name: str
    :type requirements: list[str]
    :type bucket: str
    """

    to_create, to_update, to_delete, unchanged = plan(module_name)

    for fn_name in to_delete.keys():
        print("Deleting lambda function {}".format(fn_name))
        lambda_client.delete_function(FunctionName=fn_name)

    for fn_name, fn in to_create.iteritems():
        print("Creating lambda function {}".format(fn_name))

        s3_object_key = package_and_upload_module(root_dir=root_dir,
                                                  module_name=module_name,
                                                  requirements=requirements,
                                                  bucket=bucket)

        lambda_client.create_function(FunctionName=fn_name,
                                      Runtime="python2.7",
                                      Role=fn.__aws_lambda_role__,
                                      Handler="{}.{}".format(module_name, fn_name),
                                      Code={
                                          'S3Bucket': bucket,
                                          'S3Key': s3_object_key,
                                      },
                                      Description=fn.__aws_lambda_description__,
                                      Timeout=fn.__aws_lambda_timeout__,
                                      MemorySize=fn.__aws_lambda_memory__,
                                      Publish=True)

    for fn_name, (aws_function, module_function, changes) in to_update.iteritems():
        print("Updating lambda function {}".format(fn_name))

        # Check if we need to change the attributes of the function
        if {"Role", "MemorySize", "Timeout"}.intersection(changes):
            lambda_client.update_function_configuration(FunctionName=fn_name,
                                                        Role=module_function.__aws_lambda_role__,
                                                        Handler="{}.{}".format(module_name, fn_name),
                                                        Description=module_function.__aws_lambda_description__,
                                                        Timeout=module_function.__aws_lambda_timeout__,
                                                        MemorySize=module_function.__aws_lambda_memory__)

        if "Code" in changes:
            s3_object_key = package_and_upload_module(root_dir=root_dir,
                                                      module_name=module_name,
                                                      requirements=requirements,
                                                      bucket=bucket)

            lambda_client.update_function_code(FunctionName=fn_name,
                                               S3Bucket=bucket,
                                               S3Key=s3_object_key,
                                               Publish=True)
