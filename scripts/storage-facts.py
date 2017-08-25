#!/usr/bin/env python3
#this script generates storage (ZFS, iSCSI) facts out of the hostvars of each VM
import json
import optparse


def main():
  p = optparse.OptionParser(
    description=
    'Sets the relevant ansible facts needed for a ZFS VM storage server (ZFS, NFS, iSCSI).',
    usage='%prog [storage hostname] [path to file containing hostvars in json]')
  options, arguments = p.parse_args()
  if len(arguments) == 2:
    storage_host = arguments[0]
    original_facts = json.loads(open(arguments[1]).read())
    facts = generateFacts(original_facts, storage_host)
    print(json.dumps(facts))
  else:
    p.print_help()


def generateOrganizationFilesystem(org_name):
  """generates the configuration for a ZFS filesystem with the specified name. Snapshots are disabled and sane attributes for parent filesystems are set"""
  org_fs = {
    'name': org_name,
    'attributes': {
      'exec': 'off',
      'setuid': 'off',
      'canmount': 'off',
      'recordsize': '1M'
    },
    'snapshots': {
      'snapshot': False  #don't snapshot the organizational filesystem, nothing lies there directly
    }
  }
  return org_fs


def generateIscsiTarget(fs_prefix, org, name):
  """Generates the configuration for an iSCSI target"""
  target = {
    'name': fs_prefix + org + '-' + name,
    'disks': {
      'name': fs_prefix + org + '-' + name,
      'path': fs_prefix + org + '/' + name,
      'type': 'iblock'
    },
    'initiators': []
  }
  return target


def generateIscsiInitiator(initiator):
  """Generates the configuration for one iSCSI initiator, optionally with mutual authentication"""
  initiator_config = {
    'name': initiator['name'],
    'authentication': {
      #name, userid and password are mandatory
      'userid': initiator['userid'],
      'password': initiator['password']
    }
  }
  #mutual authentication is optional
  if 'userid_mutual' in initiator:
    initiator_config['authentication']['userid_mutual'] = initiator['userid_mutual']
  if 'password_mutual' in initiator:
    initiator_config['authentication']['password_mutual'] = initiator['password_mutual']
  return initiator_config


def generateFacts(original_facts, storage_host):
  #facts are the hostvars of the current storage host
  facts = original_facts[storage_host] if storage_host in original_facts else {}
  #ZFS filesystem prefix to be added in front of every generated ZFS filesystem
  fs_prefix = facts['vm_zfs_parent_prefix'] if 'vm_zfs_parent_prefix' in facts else ''
  #list of NFS IPs which will have access to all VM NFS shares
  nfs_ips = facts['vm_nfs_access_ips'] if 'vm_nfs_access_ips' in facts else []
  #list of iSCSI initators, containing name, user and password (optionally mutual user and password)
  iscsi_initiators = facts['vm_iscsi_initiators'] if 'vm_iscsi_initiators' in facts else []

  #list of hostnames that have missing VM vars. This lists will be printed in tasks for easier debugging
  failed_names = {'size': [], 'org': [], 'root_type': [], 'initiator': []}

  #create dicts and prefix if not already set
  if 'zfs_filesystems' not in facts:
    facts['zfs_filesystems'] = []
  if 'iscsi_targets' not in facts:
    facts['iscsi_targets'] = []
  if 'zvols' not in facts:
    facts['zvols'] = []
  if 'iscsi_disk_path_prefix' not in facts:
    facts['iscsi_disk_path_prefix'] = '/dev/zvol/'

  #traverse every host defined in hostvars
  for host in original_facts.keys():
    if 'vm' not in original_facts[host]:
      continue
    #config is the vm dict of a specific VM host
    config = original_facts[host]['vm']

    #don't create this vm if org or size are not set
    if 'org' in config:
      org = config['org']
      if 'size' not in config:
        failed_names['size'].append(host)
        continue
    else:
      failed_names['org'].append(host)
      continue

    #create organization filesystem if it doesn't already exist
    if not any(d['name'] == fs_prefix + org for d in facts['zfs_filesystems']):
      org_fs = generateOrganizationFilesystem(fs_prefix + org)
      facts['zfs_filesystems'].append(org_fs)

    #get root type. zvol is the default
    root_type = config['root_type'] if 'root_type' in config else 'zvol'
    #get optional override ZFS attributes for VM filesystems/zvols. Default is {}
    attributes = config['zfs_attributes'] if 'zfs_attributes' in config else {}

    #if the VM wants ZFS filesystems, configure them and export them via NFS
    if root_type == 'filesystem':
      #set size as quota (this ZFS attribute can be changed later on)
      attributes['quota'] = config['size']
      #start with the nfs_ips defined by the storage vars
      nfs_ips = set(nfs_ips)
      #If a VM specifies a specific nfs access IP, use it.
      if 'nfs_ip' in config:
        nfs_ips.add(config['nfs_ip'])
      elif 'interfaces' in original_facts[host]:
        #Otherwise use all IPs defined in the interfaces of this VM
        for interface in original_facts[host]['interfaces']:
          if 'ip' in interface:
            nfs_ips.add(interface['ip'])
      #combine all gathered IPs for the sharenfs ZFS attribute
      sharenfs = ''
      for ip in nfs_ips:
        sharenfs += 'rw=@' + ip + ' '
      #set nfs to 'off' if there are no IPs.
      attributes['sharenfs'] = 'off' if not sharenfs else sharenfs.strip()

      #create and add root and data filesystems if necessary
      if fs_prefix + org + '/' + host + '-root' not in facts['zfs_filesystems']:
        root_fs = {'name': fs_prefix + org + '/' + host + '-root', 'attributes': attributes}
        facts['zfs_filesystems'].append(root_fs)

      if fs_prefix + org + '/' + host + '-data' not in facts['zfs_filesystems']:
        data_fs = {'name': fs_prefix + org + '/' + host + '-data', 'attributes': attributes}
        facts['zfs_filesystems'].append(data_fs)

    # If the VM wants a ZVOL (virtual block device), create it and export it via iSCSI
    elif root_type == 'zvol':
      #create ZVOL if it doesn't already exist
      if not any(d['name'] == fs_prefix + org + '/' + host for d in facts['zvols']):
        #volsize must be set at creation and cannot be changed later on
        attributes['volsize'] = config['size']
        zvol = {'name': fs_prefix + org + '/' + host, 'attributes': attributes}
        facts['zvols'].append(zvol)

      #create iSCSI target config, if it doesn't already exist
      if not any(d['name'] == fs_prefix + org + '-' + host for d in facts['iscsi_targets']):
        target = generateIscsiTarget(fs_prefix, org, host)
        #add all initiators (with authentication) defined by the storage vars
        for initiator in iscsi_initiators:
          #If an initiator has no authentication defined, don't use it and mark the host as failed
          if 'name' not in initiator or 'userid' not in initiator or 'password' not in initiator:
            failed_names['initiator'].append(host)
            continue
          initiator_config = generateIscsiInitiator(initiator)
          target['initiators'].append(initiator_config)

        facts['iscsi_targets'].append(target)
    else:
      #If an illegal root_type has been used, mark the host as failed accordingly
      failed_names['root_type'].append(host)
  #return the result, consisting of the failed hosts and the extended hostvars for the current storage server
  result = {'failed_hosts': failed_names, 'new_hostvars': facts}
  return result


if __name__ == "__main__":
  main()
