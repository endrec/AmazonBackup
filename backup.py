#!/usr/local/bin/python2.7
# encoding: utf-8
'''
backup -- Backup script for AWS

backup is a script which creates backup images (AMIs) from AWS EC2 and VPC instances.
To backup an instance it needs to have a tag 'Backup' (see FILTER_TAG),
its value defines the number of images to keep.

@author:     Endre Czirbesz
        
@copyright:  2013 Ultrasis. All rights reserved.
        
@license:    Permission is hereby granted, free of charge, to any person obtaining a
            copy of this software and associated documentation files (the
            "Software"), to deal in the Software without restriction, including
            without limitation the rights to use, copy, modify, merge, publish, dis-
            tribute, sublicense, and/or sell copies of the Software, and to permit
            persons to whom the Software is furnished to do so, subject to the fol-
            lowing conditions:

            The above copyright notice and this permission notice shall be included
            in all copies or substantial portions of the Software.

            THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
            OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABIL-
            ITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT
            SHALL THE AUTHOR BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
            WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
            OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
            IN THE SOFTWARE.

@contact:    eczirbesz@ultrasis.com
@deffield    updated: Updated
'''

# Standard Modules
import os
import string
import sys
import time
import ConfigParser

# Third-Party Modules
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from boto import ec2, utils

__all__ = []
__version__ = 0.1
__date__ = '2013-05-22'
__updated__ = '2013-05-23'

# Settings
FILTER_TAG = 'Backup'
NO_REBOOT_TAG = 'NoReboot'
DEFAULT_KEEP = 7
STAMP_TAG = 'AutoBackupTimestamp'
SOURCE_TAG = 'SourceInstanceId'
DEBUG = 0
TESTRUN = 0
PROFILE = 0

# Globals
verbose = 0
silent = False
self_id = None
aws_access_key = None
aws_secret_key = None

class CLIError(Exception):
    '''Generic exception to raise and log different fatal errors.'''
    def __init__(self, msg):
        super(CLIError).__init__(type(self))
        self.message = "ERROR: %s" % msg
    def __str__(self):
        return self.message
    def __unicode__(self):
        return self.message

def get_self_instance_id():
    if not silent and verbose > 0:
        print "Enquiring self instance id"
    metadata = {}  # utils.get_instance_metadata()
    instance_id = metadata['instance-id'] if metadata.has_key('instance-id') else None
    if not silent and verbose > 0:
        print "Instance Id: %s" % (instance_id)

    return instance_id

def get_instances_in_regions(regions, filters=None):
    if not silent and verbose > 0:
        print "Retrieving instances"
    if not silent and verbose > 1:
        print "Regions: %s\nFilters: %s" % (regions, filters)

    instances_in_regions = []
    for region in ec2.regions():
        if region.name in regions:
            if not silent and verbose > 1:
                print "Connecting %s region" % (region.name)
            conn = ec2.connect_to_region(region.name, aws_access_key_id=aws_access_key, aws_secret_access_key=aws_secret_key)
            reservations = conn.get_all_instances(filters=filters)
            i = 0
            for r in reservations:
                for instance in r.instances:
                    instances_in_regions.append(instance)
                    i += 1
            if not silent and verbose > 0:
                print "Found %d instances in %s region" % (i, region.name)

    if not silent:
        print "Got %s instances" % (len(instances_in_regions))

    return instances_in_regions

def create_ami(instance):
    if not silent and verbose > 0:
        print "Creating AMI"
    create_time = time.gmtime()
    name = (instance.tags['Name'].replace(' ', '_') if instance.tags.has_key('Name') else instance.id) + '_Backup_' + time.strftime('%Y%m%dT%H%M%SZ0000', create_time)
    desc = (instance.tags['Name'] if instance.tags.has_key('Name') else instance.id) + ' Backup on ' + time.asctime(create_time)

    no_reboot = instance.tags.has_key(NO_REBOOT_TAG) or (instance.id == self_id)

    if not silent and verbose > 1:
        print '''Image parameters:
  Name:        %s
  Description: %s
  Source:      %s
  ''' % (name, desc, instance.id)

    ami_id = instance.create_image(name, description=desc, no_reboot=no_reboot)
    if not silent:
        print "Created AMI: %s" % (ami_id)

    # Wait for the image to appear
    time.sleep(0.2)

    if not silent and verbose > 0:
        print "Tagging image"
    image = instance.connection.get_all_images(image_ids=[ami_id])[0]
    image.add_tag(STAMP_TAG, time.mktime(create_time))
    image.add_tag(SOURCE_TAG, instance.id)

    if not silent and verbose > 1:
        print "Created AMI tags: %s" % (image.tags)

    return ami_id

def image_date_compare(ami1, ami2):
    if ami1.tags[STAMP_TAG] < ami2.tags[STAMP_TAG]:
        return -1
    elif ami1.tags[STAMP_TAG] == ami2.tags[STAMP_TAG]:
        return 0
    return 1

def remove_old_amis(instance):
    conn = instance.connection
    keep = int(instance.tags[FILTER_TAG]) if (instance.tags.has_key(FILTER_TAG) and instance.tags[FILTER_TAG].isdigit()) else DEFAULT_KEEP
    if not silent and verbose > 0:
        print "Removing old images for %s, keeping %d" % (instance.id, keep)
        print "Retrieving images"

    images = [image for image in conn.get_all_images(filters={'tag:' + SOURCE_TAG: instance.id})]
    images.sort(image_date_compare)

    if not silent and verbose > 0:
        print "Got %d images" % (len(images))

    for image in images[:-keep]:
        conn.deregister_image(image.id, delete_snapshot=True)
        if not silent:
            print "Image %s deregistered" % (image.id)

def main(argv=None):  # IGNORE:C0111
    '''Processing command line options and config file.'''

    if argv is None:
        argv = sys.argv
    else:
        sys.argv.extend(argv)

    program_name = os.path.basename(sys.argv[0])
    program_version = "v%s" % __version__
    program_build_date = str(__updated__)
    program_version_message = '%%(prog)s %s (%s)' % (program_version, program_build_date)
    program_shortdesc = __import__('__main__').__doc__.split("\n")[1]
    program_license = '''%s

  The script creates backup images (AMIs) from AWS EC2 and VPC instances.
  To backup an instance it needs to have a tag 'Backup' (see FILTER_TAG),
  its value defines the number of images to keep.

  Created by Endre Czirbesz on %s.
  Copyright 2013 Ultrasis. All rights reserved.
  
  Licensed under the MIT License (MIT)
  http://opensource.org/licenses/MIT
  
  Distributed on an "AS IS" basis without warranties
  or conditions of any kind, either express or implied.

USAGE
''' % (program_shortdesc, str(__date__))

    try:
        # Setup argument parser
        parser = ArgumentParser(description=program_license, formatter_class=RawDescriptionHelpFormatter)
        parser.add_argument("--cron", dest="silent", action="store_true", help="suppress all output for cron run [default: %(default)s]")
        parser.add_argument("-C", "--credential-file", dest="credential_file_name", metavar="FILE",
                             help="config file with AWS credentials [default: ccredentials.ini], overrides environment settings")
        parser.add_argument("-O", "--aws-access-key", dest="aws_access_key", metavar="KEY",
                            help="AWS Access Key ID. Defaults to the value of the AWS_ACCESS_KEY environment variable (if set).")
        parser.add_argument("-W", "--aws-secret-key", dest="aws_secret_key", metavar="KEY",
                            help="AWS Secret Access Key. Defaults to the value of the AWS_SECRET_KEY environment variable (if set).")
        parser.add_argument("-v", "--verbose", dest="verbose", action="count", help="set verbosity level [default: %(default)s]")
        parser.add_argument('-V', '--version', action='version', version=program_version_message)
        region_name_list = [region.name for region in ec2.regions()]
        parser.add_argument(dest="regions", help="region(s) to backup [default: %s]" % (region_name_list), metavar="region", nargs='*', default=region_name_list)

        # Process arguments
        args = parser.parse_args()

        global verbose, silent, aws_access_key, aws_secret_key
        regions = args.regions
        verbose = args.verbose
        silent = args.silent

        if not silent and verbose > 0:
            print "Verbose mode on, level %d" % (verbose)

        if (args.aws_access_key == None or args.aws_secret_key == None):
            aws_access_key = os.getenv("AWS_ACCESS_KEY")
            aws_secret_key = os.getenv("AWS_SECRET_KEY")
            if not silent and verbose > 2:
                print "Access key from env: %s\nSecret key from env: %s" % (aws_access_key, aws_secret_key)
            
            config_file_path = os.path.abspath(args.credential_file_name if args.credential_file_name else "credentials.ini")
            if not silent and verbose > 0:
                print "Reading config file: %s" % (config_file_path)
            try:
                config = ConfigParser.ConfigParser()
                config.read(config_file_path)
                if not silent and verbose > 0:
                    print "Got sections: %s" % (config.sections())
                    
                if (not config.sections()) and (not args.credential_file_name) and aws_access_key and aws_secret_key:
                    if not silent and verbose > 0:
                        print "Missing or empty default config file, falling back to env"
                else:
                    aws_access_key = config.get('AWS', 'AWSAccessKeyId')
                    aws_secret_key = config.get('AWS', 'AWSSecretKey')
                    if not silent and verbose > 2:
                        print "Access key from file: %s\nSecret key from file: %s" % (aws_access_key, aws_secret_key)
            except (ConfigParser.NoOptionError, ConfigParser.NoSectionError):
                raise CLIError("AWS credentials must be specified.")
        else:
            if args.credential_file_name:
                raise CLIError("You can not specify both credentials and a config file.")
            aws_access_key = args.aws_access_key
            aws_secret_key = args.aws_secret_key
            if not silent and verbose > 2:
                print "Access key from args: %s\nSecret key from args: %s" % (aws_access_key, aws_secret_key)

        if not silent and verbose > 2:
            print "Access key: %s\nSecret key: %s" % (aws_access_key, aws_secret_key)

        if (aws_access_key == None or aws_secret_key == None):
            raise CLIError("AWS credentials must be specified.")
        
        global self_id
        self_id = get_self_instance_id()
        for instance in get_instances_in_regions(regions, {'tag:' + FILTER_TAG: '*'}):
            create_ami(instance)
            remove_old_amis(instance)

        if not silent:
            print "Done."

        return 0
    except KeyboardInterrupt:
        ### handle keyboard interrupt ###
        return 0
    except Exception as e:
        if DEBUG or TESTRUN:
            raise(e)
        indent = len(program_name) * " "
        sys.stderr.write(program_name + ": " + e.message + "\n")
        sys.stderr.write(indent + "  for help use --help")
        return 2

if __name__ == "__main__":
    if DEBUG:
        sys.argv.append("-vvvv")
    if TESTRUN:
        import doctest
        doctest.testmod()
    if PROFILE:
        import cProfile
        import pstats
        profile_filename = 'backup_profile.txt'
        cProfile.run('main()', profile_filename)
        statsfile = open("profile_stats.txt", "wb")
        p = pstats.Stats(profile_filename, stream=statsfile)
        stats = p.strip_dirs().sort_stats('cumulative')
        stats.print_stats()
        statsfile.close()
        sys.exit(0)
    sys.exit(main())
