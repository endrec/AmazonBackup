#!/usr/bin/env python
# encoding: utf-8

# Standard Modules
import os
import sys
import time

# Third-Party Modules
from boto import ec2, utils

# AWS Credentials
from credentials import AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, ACCOUNT_ID

# Settings
FILTER_TAG = 'Backup'
NO_REBOOT_TAG = 'NoReboot'
DEFAULT_KEEP = 7
STAMP_TAG = 'AutoBackupTimestamp'
SOURCE_TAG = 'SourceInstanceId'

def get_self_instance_id():
    metadata = utils.get_instance_metadata()
    return metadata['instance-id'] if metadata.has_key('instance-id') else None

def get_instances_by_region(filters=None):
    instances_by_region = {}
    for region in ec2.regions():
        conn = ec2.connect_to_region(region.name, aws_access_key_id=AWS_ACCESS_KEY_ID, aws_secret_access_key=AWS_SECRET_ACCESS_KEY)
        reservations = conn.get_all_instances(filters=filters)
        for r in reservations:
            for instance in r.instances:
                if not instances_by_region.has_key(region.name):
                    instances_by_region[region.name] = []
                instances_by_region[region.name].append(instance)
    return instances_by_region

def create_ami(instance):
    create_time = time.gmtime()
    name = (instance.tags['Name'].replace(' ', '_') if instance.tags.has_key('Name') else instance.id) + '_Backup_' + time.strftime('%Y%m%dT%H%M%SZ0000', create_time)
    desc = (instance.tags['Name'] if instance.tags.has_key('Name') else instance.id) + ' Backup on ' + time.asctime(create_time)
    
    no_reboot = instance.tags.has_key(NO_REBOOT_TAG) or (instance.id == get_self_instance_id())
    
    ami_id = instance.create_image(name, description=desc, no_reboot=no_reboot)
    image = instance.connection.get_all_images(image_ids= [ami_id])[0]
    image.add_tag(STAMP_TAG, time.mktime(create_time))
    image.add_tag(SOURCE_TAG, instance.id)
    
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

    images = [image for image in conn.get_all_images(filters={'tag:'+SOURCE_TAG: instance.id})]
    images.sort(image_date_compare)
    for image in images[:-keep]:
        conn.deregister_image(image.id, delete_snapshot=True)

def main():
    sys.exit()

if __name__ == '__main__':
    main()

