import optparse
from publish_aws_lambda import plan, print_plan, publish

# Check the command line...
parser = optparse.OptionParser(description="Publish auth Lambdas into AWS (code will upload to a S3 bucket)")

parser.add_option("--dry-run", dest="dry_run", action="store_true", help="Plan but don't execute")
parser.add_option("--dir", dest="dir", default=".", help="Root dir of project to upload")
parser.add_option("--module", dest="module", help="Python module to upload as AWS lambda functions")
parser.add_option("--requirements", dest="requirements", default="",
                  help="List of modules (comma separated) to include")
parser.add_option("--bucket", dest="bucket", help="S3 bucket to upload code into")

options, args = parser.parse_args()

assert options.module, "Python module has to be provided"
assert options.bucket, "S3 bucket has to be provided"

if options.dry_run:
    p = plan(options.module)
    print_plan(options.module, *p)

else:
    publish(root_dir=options.dir,
            module_name=options.module,
            requirements=options.requirements.split(",") if len(options.requirements.strip()) > 0 else [],
            bucket=options.bucket)

    print("Done!")