#!/usr/bin/env python3
#this script generates storage (ZFS, iSCSI) facts out of the hostvars of each VM
import json
import optparse


def main():
  p = optparse.OptionParser(
    description='Sets relevant ansible facts needed for a ZFS VM storage server.',
    usage='%prog [storage hostname] [hostvars as json]')
  options, arguments = p.parse_args()
  if len(arguments) == 2:
    storage_host = arguments[0]
    #print(storage_host)
    original_facts = json.loads(open(arguments[1]).read())
    #print(original_facts)
    facts = generateFacts(original_facts, storage_host)
    print(json.dumps(facts))
  else:
    p.print_help()


def generateOrganizationFilesystem(org_name):
  """generates the configuration for a ZFS filesystem with the specified name"""
  org_fs = {
    'name': org_name,
    'attributes': {
      'exec': 'off',
      'setuid': 'off',
      'canmount': 'off',
      'mountpoint': 'none'
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
      'userid': initiator['userid'],
      'password': initiator['password']
    }
  }
  if 'userid_mutual' in initiator:
    initiator_config['authentication']['userid_mutual'] = initiator['userid_mutual']
  if 'password_mutual' in initiator:
    initiator_config['authentication']['password_mutual'] = initiator['password_mutual']
  return initiator_config


def generateFacts(original_facts, storage_host):
  facts = original_facts[storage_host] if storage_host in original_facts else {}
  fs_prefix = facts['vm_zfs_parent_prefix'] if 'vm_zfs_parent_prefix' in facts else ''
  nfs_ips = facts['vm_nfs_access_ips'] if 'vm_nfs_access_ips' in facts else []
  iscsi_initiators = facts['vm_iscsi_initiators'] if 'vm_iscsi_initiators' in facts else []
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

  for host in original_facts.keys():
    if 'vm' not in original_facts[host]:
      continue
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

    root_type = config['root_type'] if 'root_type' in config else 'zvol'
    attributes = config['zfs_attributes'] if 'zfs_attributes' in config else {}

    if root_type == 'filesystem':
      attributes['quota'] = config['size']
      nfs_ips = set(nfs_ips)
      #if a nfs_ip is configured, add it. Otherwise add all configures IPs of this host
      if 'nfs_ip' in config:
        nfs_ips.add(config['nfs_ip'])
      elif 'interfaces' in original_facts[host]:
        for interface in original_facts[host]['interfaces']:
          if 'ip' in interface:
            nfs_ips.add(interface['ip'])
      #combine all gathered IPs for the sharenfs attribute
      sharenfs = ''
      for ip in nfs_ips:
        sharenfs += 'rw=@' + ip + ' '
      attributes['sharenfs'] = 'off' if not sharenfs else sharenfs.strip()

      #create and add root and data filesystems if necessary
      if fs_prefix + org + '/' + host + '-root' not in facts['zfs_filesystems']:
        root_fs = {'name': fs_prefix + org + '/' + host + '-root', 'attributes': attributes}
        facts['zfs_filesystems'].append(root_fs)

      if fs_prefix + org + '/' + host + '-data' not in facts['zfs_filesystems']:
        data_fs = {'name': fs_prefix + org + '/' + host + '-data', 'attributes': attributes}
        facts['zfs_filesystems'].append(data_fs)

    elif root_type == 'zvol':
      #create ZVOL if it doesn't already exist
      if not any(d['name'] == fs_prefix + org + '/' + host for d in facts['zvols']):
        attributes['volsize'] = config['size']
        zvol = {'name': fs_prefix + org + '/' + host, 'attributes': attributes}
        facts['zvols'].append(zvol)

      #create iSCSI target config, if it doesn't already exist
      if not any(d['name'] == fs_prefix + org + '-' + host for d in facts['iscsi_targets']):
        target = generateIscsiTarget(fs_prefix, org, host)
        #add initiators with authentication
        for initiator in iscsi_initiators:
          if 'name' not in initiator or 'userid' not in initiator or 'password' not in initiator:
            failed_names['initiator'].append(host)
            continue
          initiator_config = generateIscsiInitiator(initiator)
          target['initiators'].append(initiator_config)

        facts['iscsi_targets'].append(target)
    else:
      #illegal root_type
      failed_names['root_type'].append(host)
  result = {'failed_hosts': failed_names, 'new_hostvars': facts}
  return result


if __name__ == "__main__":
  main()