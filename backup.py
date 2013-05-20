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
KEEP = 7 
STAMP_NAME  = 'CreatedBy'
STAMP_VALUE = 'AutoBackup'

def getSelfInstanceId():
    metadata = utils.get_instance_metadata()
    return metadata['instance-id'] if metadata.has_key('instance-id') else None
    
def getInstancesByRegion():
    instancesByRegion = {}
    for region in ec2.regions():
        conn = ec2.connect_to_region(region.name, aws_access_key_id=AWS_ACCESS_KEY_ID, aws_secret_access_key=AWS_SECRET_ACCESS_KEY)
        reservations = conn.get_all_instances()
        for r in reservations:
            for instance in r.instances:
                if not instancesByRegion.has_key(region.name):
                    instancesByRegion[region.name] = []
                instancesByRegion[region.name].append(instance)
    return instancesByRegion

def createAMI(instance):
    return

def removeOldAMIs():
    return

def main():
    sys.exit()
    