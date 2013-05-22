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

# Third-Party Modules
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from boto import ec2, utils

# AWS Credentials
from credentials import AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY

__all__ = []
__version__ = 0.1
__date__ = '2013-05-22'
__updated__ = '2013-05-22'

# Settings
FILTER_TAG = 'Backup'
NO_REBOOT_TAG = 'NoReboot'
DEFAULT_KEEP = 7
STAMP_TAG = 'AutoBackupTimestamp'
SOURCE_TAG = 'SourceInstanceId'
DEBUG = 1
TESTRUN = 1
PROFILE = 0

verbose = 0
silent = False

class CLIError(Exception):
    '''Generic exception to raise and log different fatal errors.'''
    def __init__(self, msg):
        super(CLIError).__init__(type(self))
        self.msg = "E: %s" % msg
    def __str__(self):
        return self.msg
    def __unicode__(self):
        return self.msg

def get_self_instance_id():
    if not silent and verbose > 0:
        print "Enquiring self instance id"
    metadata = utils.get_instance_metadata()
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
            conn = ec2.connect_to_region(region.name, aws_access_key_id=AWS_ACCESS_KEY_ID, aws_secret_access_key=AWS_SECRET_ACCESS_KEY)
            reservations = conn.get_all_instances(filters=filters)
            for r in reservations:
                for instance in r.instances:
                    instances_in_regions.append(instance)
    
    if not silent:
        print "Got %s instances" % (len(instances_in_regions))
    
    return instances_in_regions

def create_ami(instance):
    if not silent and verbose > 0:
        print "Creating AMI"
    create_time = time.gmtime()
    name = (instance.tags['Name'].replace(' ', '_') if instance.tags.has_key('Name') else instance.id) + '_Backup_' + time.strftime('%Y%m%dT%H%M%SZ0000', create_time)
    desc = (instance.tags['Name'] if instance.tags.has_key('Name') else instance.id) + ' Backup on ' + time.asctime(create_time)

    no_reboot = instance.tags.has_key(NO_REBOOT_TAG) or (instance.id == get_self_instance_id())

    if not silent and verbose > 1:
        print '''Image parameters:
  Name:        %s
  Description: %s
  Source:      %s
  ''' % (name, desc, instance.id)

    ami_id = instance.create_image(name, description=desc, no_reboot=no_reboot)
    image = instance.connection.get_all_images(image_ids= [ami_id])[0]
    image.add_tag(STAMP_TAG, time.mktime(create_time))
    image.add_tag(SOURCE_TAG, instance.id)

    if not silent:
        print "Created AMI: %s" % (ami_id)

    remove_old_amis(instance)
    return ami_id

def image_date_compare(ami1, ami2):
    if ami1.tags[STAMP_TAG] < ami2.tags[STAMP_TAG]:
        return -1
    elif ami1.tags[STAMP_TAG] == ami2.tags[STAMP_TAG]:
        return 0
    return 1

def remove_old_amis(instance):
    conn = instance.connection
    keep = instance.tags[FILTER_TAG] if (instance.tags.has_key(FILTER_TAG) and instance.tags[FILTER_TAG].isdigit()) else DEFAULT_KEEP
    if not silent and verbose > 0:
        print "Removing old images for %s, keeping %d" % (instance.id, keep)

    images = [image for image in conn.get_all_images(filters={'tag:'+SOURCE_TAG: instance.id})]
    images.sort(image_date_compare)
    for image in images[:-keep]:
        conn.deregister_image(image.id, delete_snapshot=True)
        if not silent:
            print "Image %s deregistered" % (image.id)

def main(argv=None): # IGNORE:C0111
    '''Command line options.'''
    
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
        parser.add_argument("--cron", dest="silent", action="store_true", help="Suppress all output for cron run [default: %(default)s]")
        parser.add_argument("-v", "--verbose", dest="verbose", action="count", help="set verbosity level [default: %(default)s]")
        parser.add_argument('-V', '--version', action='version', version=program_version_message)
        region_name_list = [region.name for region in ec2.regions()]
        parser.add_argument(dest="regions", help="region(s) to backup [default: %s]" % (region_name_list), metavar="region", nargs='*', default=region_name_list)
        
        # Process arguments
        args = parser.parse_args()

        global verbose, silent        
        regions = args.regions
        verbose = args.verbose
        silent = args.silent
        
        if not silent and verbose > 0:
            print "Verbose mode on, level %d" % (verbose)
        
        instances = get_instances_in_regions(regions, {'tag:' + FILTER_TAG: '*'})
        
        return 0
    except KeyboardInterrupt:
        ### handle keyboard interrupt ###
        return 0
    except Exception, e:
        if DEBUG or TESTRUN:
            raise(e)
        indent = len(program_name) * " "
        sys.stderr.write(program_name + ": " + repr(e) + "\n")
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