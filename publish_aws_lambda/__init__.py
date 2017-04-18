__version__ = "0.4.2"

"""
Publish the a python package as AWS lambdas functions.
"""

import logging
import os
import pprint
import shutil
import types
import boto3
# noinspection PyPackageRequirements
from unix_dates import UnixDate

logger = logging.getLogger(__name__)


def aws_lambda(role_arn, timeout=60, memory=128, description="", vpc_config=None):
    """
    :type role_arn: str
    :type timeout: int
    :type memory: int
    :type description: str
    :type vpc_config: dict
    """

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
        func.__aws_vpc_config__ = vpc_config

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


def get_latest_modified_date_in_dir(root_dir):
    """
    Recursively scan a directory to get the latest changes (used to detect if we need to upload code)

    :return: The latest modified date of all files in the directory
    """
    latest_modified = None

    for root, _, filenames in os.walk(root_dir):
        for fn in filenames:
            p = os.path.join(root, fn)

            parts = p.split(os.sep)

            if len(parts) > 1:
                if parts[1].startswith("."):
                    logger.debug("Skipping {}".format(p))
                    continue

                if parts[1] in ("lib", "lambda", "bin", "dist", "include"):
                    logger.debug("Skipping {}".format(p))
                    continue

            # Only consider the 'interesting files'. We don't want to scan random files
            _, ext = os.path.splitext(p)
            if ext not in (".py", ".txt", ".sh"):
                continue

            lm = os.stat(p).st_mtime

            if lm > (latest_modified or 0):
                latest_modified = lm

    return latest_modified


def plan(root_dir, modules, force, region):
    """
    Create a plan of upgrade existing AWS lambda functions with latest for this module.

    :type root_dir: str
    :type modules: collections.Iterable[str]
    :type force: bool
    :type force: bool
    :type region: str
    """
    module_functions = {}
    aws_functions = {}

    lambda_client = boto3.client("lambda", region_name=region)

    for module_name in modules:
        module_functions.update(
            {(module_name, fn.__name__): fn for fn in get_all_lambda_functions_in_module(module_name)})

        aws_functions.update(
            {(module_name, fn["FunctionName"]):
                 fn for fn in lambda_client.list_functions()["Functions"] if fn["Handler"].startswith(module_name)})

    to_create = {k: fn for k, fn in module_functions.iteritems() if k not in aws_functions}
    to_delete = {k: fn for k, fn in aws_functions.iteritems() if k not in module_functions}

    last_modified = get_latest_modified_date_in_dir(root_dir)

    # Examine the ones to update to see if anything changed...
    to_update, unchanged = {}, set()
    for fn_key, aws_function in aws_functions.iteritems():
        module_function = module_functions.get(fn_key)
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
            logger.info("Detected code change in function {}".format(fn_key))

            changed = True
            changes.add("Code")

        if changed or force:
            to_update[fn_key] = (aws_function, module_function, changes)
        else:
            unchanged.add(fn_key)

    return to_create, to_update, to_delete, unchanged


def print_plan(modules, to_create, to_update, to_delete, unchanged):
    # Group updates by reason
    update_with_reason = {(k, d[2]) for k, d in to_update.iteritems()}

    logger.info(pprint.pformat("The plan is (for modules {}):".format(modules)))
    logger.info(pprint.pformat("   Create: {}".format(to_create.keys())))
    logger.info(pprint.pformat("   Delete: {}".format(to_delete.keys())))
    logger.info(pprint.pformat("   Update: {}".format(update_with_reason)))
    logger.info(pprint.pformat("   Unchanged: {}".format(unchanged)))


def package_and_upload_module(root_dir, requirements_path, module_name, bucket, region):
    """
    Installs the module + all requirements into a folder ('lambda'). Zip it ('lambda.zip') and
    upload it to the indicated bucket in S3.

    :type root_dir: str
    :type bucket: str
    :type requirements_path: str
    :type module_name: str
    :type region: str

    :return: The s3 object key, path to the local zip file
    :rtype: str
    """

    s3_client = boto3.client("s3", region_name=region)

    assert os.path.isdir(root_dir)
    assert os.path.isfile(requirements_path)

    dist_dir = os.path.join(root_dir, "dist")
    lambda_target = "lambdas"

    # Clean up first (from any previous installation)
    lambda_dir = os.path.join(dist_dir, lambda_target)
    if os.path.exists(lambda_dir):
        shutil.rmtree(lambda_dir)

    lambda_zip = os.path.join(dist_dir, "{}.zip".format(lambda_target))
    if os.path.exists(lambda_zip):
        os.remove(lambda_zip)

    os.makedirs(lambda_dir)

    # Install the required packages
    import pip
    pip.main(["install", ".", "-t", lambda_dir])

    # Install requirements
    pip.main(["install", "-r", requirements_path, "-t", lambda_dir])

    # Make sure this package is part of the requirements!
    pip.main(["install", "publish_aws_lambda", "-t", lambda_dir])
    pip.main(["install", "unix_dates", "-t", lambda_dir])

    # No need for boto3 to be packaged
    for fn in os.listdir(lambda_dir):
        p = os.path.join(lambda_dir, fn)

        if os.path.isdir(p) and fn.startswith("boto"):
            shutil.rmtree(p)

    # ZIP it up!
    lambda_zip = shutil.make_archive(lambda_target, "zip", lambda_dir)

    # And upload to S3 (use module as object key)
    s3_client.upload_file(Filename=lambda_zip,
                          Bucket=bucket,
                          Key=module_name,
                          ExtraArgs={'ACL': 'bucket-owner-full-control'})

    logger.info("Uploaded {} to S3 bucket {} as {}".format(lambda_zip, bucket, module_name))

    return module_name


def publish(root_dir, modules, bucket, region, force=False):
    """
    Perform the publish / sync of the lambda functions. This includes packaging the lambda functions in this
    module, uploading it to S3 and then setting up the lambda function configuration

    :type root_dir: str
    :type modules: collections.Iterable[str]
    :type bucket: str
    :type force: bool
    :type region: str
    """

    lambda_client = boto3.client("lambda", region_name=region)

    # Check root_dir and make sure it has a "requirements.txt" file in it
    requirements_path = os.path.join(root_dir, "requirements.txt")
    assert os.path.exists(requirements_path), "Expecting requirements.txt to be in root_dir"

    to_create, to_update, to_delete, unchanged = plan(root_dir, modules, force, region=region)

    for fn_name in to_delete.keys():
        logger.info("Deleting lambda function {}".format(fn_name))
        lambda_client.delete_function(FunctionName=fn_name)

    for fn_key, fn in to_create.iteritems():
        module_name, fn_name = fn_key

        logger.info("Creating lambda function {}".format(fn_name))

        s3_object_key = package_and_upload_module(root_dir=root_dir,
                                                  module_name=module_name,
                                                  bucket=bucket,
                                                  requirements_path=requirements_path,
                                                  region=region)

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
                                      VpcConfig=fn.__aws_vpc_config__,
                                      Publish=True)

    for fn_key, (aws_function, module_function, changes) in to_update.iteritems():
        module_name, fn_name = fn_key

        logger.info("Updating lambda function {}".format(fn_name))

        # Check if we need to change the attributes of the function
        if {"Role", "MemorySize", "Timeout"}.intersection(changes):
            lambda_client.update_function_configuration(FunctionName=fn_name,
                                                        Role=module_function.__aws_lambda_role__,
                                                        Handler="{}.{}".format(module_name, fn_name),
                                                        Description=module_function.__aws_lambda_description__,
                                                        Timeout=module_function.__aws_lambda_timeout__,
                                                        MemorySize=module_function.__aws_lambda_memory__)

        if "Code" in changes or force:
            s3_object_key = package_and_upload_module(root_dir=root_dir,
                                                      module_name=module_name,
                                                      requirements_path=requirements_path,
                                                      bucket=bucket,
                                                      region=region)

            lambda_client.update_function_code(FunctionName=fn_name,
                                               S3Bucket=bucket,
                                               S3Key=s3_object_key,
                                               Publish=True)
