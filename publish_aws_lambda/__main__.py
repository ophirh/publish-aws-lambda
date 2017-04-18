import logging
import optparse
import sys
from publish_aws_lambda import plan, print_plan, publish

DEFAULT_REGION = "us-east-1"

logging.basicConfig(level=logging.INFO, format="%(message)s", datefmt="%Y-%m-%d %H:%M:%S", stream=sys.stdout)

# Check the command line...
parser = optparse.OptionParser(description="Publish auth Lambdas into AWS (code will upload to a S3 bucket)")

parser.add_option("--dry-run", dest="dry_run", action="store_true", help="Plan but don't execute")
parser.add_option("--dir", dest="dir", default=".", help="Root dir of project to upload")
parser.add_option("--module", dest="modules", action="append", help="Python modules to upload as AWS lambda functions")
parser.add_option("--bucket", dest="bucket", help="S3 bucket to upload code into")
parser.add_option("--force-upload", dest="force", action="store_true", default=False, help="Force upload to S3")
parser.add_option("--region", dest="region", default=DEFAULT_REGION, help="AWS Region")

options, args = parser.parse_args()

assert options.modules, "At least one python module has to be provided"
assert options.bucket, "S3 bucket has to be provided"

if options.dry_run:
    p = plan(root_dir=options.dir,
             modules=options.modules,
             force=options.force,
             region=options.region)

    print_plan(options.modules, *p)

else:
    publish(root_dir=options.dir,
            modules=options.modules,
            bucket=options.bucket,
            force=options.force,
            region=options.region)

    print("Done!")
