#!/usr/bin/env python3
# This script generates storage (ZFS, iSCSI) facts out of the hostvars of each VM
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
  """Generates the configuration for a ZFS filesystem with the specified name. Snapshots are disabled and sane attributes for parent filesystems are set"""
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


def generateIscsiTarget(name, path, portals):
  """Generates the configuration for an iSCSI target"""
  target = {
    'name': name,
    'disks': {
      'name': name,
      'path': path,
      'type': 'iblock'
    },
    'initiators': [],
    'portals': portals
  }
  return target


def generateIscsiInitiator(initiator):
  """Generates the configuration for one iSCSI initiator, optionally with mutual authentication"""
  initiator_config = {
    'name': initiator['name'],
    'authentication': {
      # name, userid and password are mandatory
      'userid': initiator['userid'],
      'password': initiator['password']
    }
  }
  # Mutual authentication is optional
  if 'userid_mutual' in initiator:
    initiator_config['authentication']['userid_mutual'] = initiator['userid_mutual']
  if 'password_mutual' in initiator:
    initiator_config['authentication']['password_mutual'] = initiator['password_mutual']
  return initiator_config


def generateFacts(original_facts, storage_host):
  # facts are the hostvars of the current storage host
  facts = original_facts[storage_host] if storage_host in original_facts else {}
  # ZFS filesystem prefix to be added in front of every generated ZFS filesystem
  fs_prefix = facts['vm_zfs_parent_prefix'] if 'vm_zfs_parent_prefix' in facts else ''
  # List of NFS options that will be set on all exports
  nfs_options = facts['vm_nfs_options'] if 'vm_nfs_options' in facts else []
  # List of iSCSI initators, containing name, user and password (optionally mutual user and password)
  iscsi_initiators = facts['vm_iscsi_initiators'] if 'vm_iscsi_initiators' in facts else []
  # List of portals (IPs to give iSCSI access to)
  portals = facts['vm_iscsi_portals'] if 'vm_iscsi_portals' in facts else []
  # List of hostnames that have missing VM vars. This lists will be printed in tasks for easier debugging
  failed_names = {'size': [], 'org': [], 'root_type': [], 'initiator': []}

  # Create dicts and prefix if not already set
  if 'zfs_filesystems' not in facts:
    facts['zfs_filesystems'] = []
  if 'iscsi_targets' not in facts:
    facts['iscsi_targets'] = []
  if 'zvols' not in facts:
    facts['zvols'] = []
  if 'iscsi_disk_path_prefix' not in facts:
    facts['iscsi_disk_path_prefix'] = '/dev/zvol/'

  # Traverse every host defined in hostvars
  for host in original_facts.keys():
    if 'vm' not in original_facts[host]:
      continue
    # config is the vm dict of a specific VM host
    config = original_facts[host]['vm']

    # Don't create this vm if org or size are not set
    if 'org' in config:
      org = config['org']
      if 'size' not in config:
        failed_names['size'].append(host)
        continue
    else:
      failed_names['org'].append(host)
      continue

    # Create organization filesystem if it doesn't already exist
    if not any(d['name'] == fs_prefix + org for d in facts['zfs_filesystems']):
      org_fs = generateOrganizationFilesystem(fs_prefix + org)
      facts['zfs_filesystems'].append(org_fs)

    # Get root type. zvol is the default
    root_type = config['root_type'] if 'root_type' in config else 'zvol'

    # If the VM wants ZFS filesystems, configure them and export them via NFS
    if root_type == 'filesystem':
      # Default NFS options if no overrides are specified for a filesystem
      default_nfs_options = list(nfs_options)
      # Add every existing interface ip as rw export
      if 'interfaces' in original_facts[host]:
        for interface in original_facts[host]['interfaces']:
          if 'ip' in interface:
            default_nfs_options.append("rw=@" + interface['ip'])

      filesystems = config['filesystems'] if 'filesystems' in config else []
      # Add root filesystem if it has not been defined by hand
      if not any(d['name'] == 'root' for d in filesystems):
        filesystems.append({'name': 'root'})

      for fs in filesystems:
        if 'name' not in fs:
          continue
        attributes = fs['zfs_attributes'] if 'zfs_attributes' in fs else {}
        # Use override NFS options if they exist, otherwise use the default
        nfs_options_to_set = fs['nfs_options'] + nfs_options if 'nfs_options' in fs else default_nfs_options
        # Set sizes and no_root_squash if it is the root filesystem
        if fs['name'] == 'root':
          attributes['quota'] = config['size']
          attributes['reservation'] = config['size']
          nfs_options_to_set.append('no_root_squash')
        attributes['sharenfs'] = 'off' if not nfs_options_to_set else ','.join(
          sorted(set(nfs_options_to_set)))
        # Create and add root and data filesystems if necessary
        if fs_prefix + org + '/' + host + '-' + fs['name'] not in facts['zfs_filesystems']:
          zfs_fs = {
            'name': fs_prefix + org + '/' + host + '-' + fs['name'],
            'attributes': attributes
          }
          facts['zfs_filesystems'].append(zfs_fs)

    # If the VM wants a ZVOL (virtual block device), create it and export it via iSCSI
    elif root_type == 'zvol':
      # Create ZVOL if it doesn't already exist
      if not any(d['name'] == fs_prefix + org + '/' + host for d in facts['zvols']):
        # volsize must be set at creation and cannot be changed later on
        zvol = {'name': fs_prefix + org + '/' + host, 'attributes': {'volsize': config['size']}}
        facts['zvols'].append(zvol)

      # Create iSCSI target config, if it doesn't already exist
      if not any(d['name'] == fs_prefix + org + '-' + host for d in facts['iscsi_targets']):
        target = generateIscsiTarget(org + '-' + host, fs_prefix + org + '/' + host, portals)
        # Add all initiators (with authentication) defined by the storage vars
        for initiator in iscsi_initiators:
          # If an initiator has no authentication defined, don't use it and mark the host as failed
          if 'name' not in initiator or 'userid' not in initiator or 'password' not in initiator:
            failed_names['initiator'].append(host)
            continue
          initiator_config = generateIscsiInitiator(initiator)
          target['initiators'].append(initiator_config)

        facts['iscsi_targets'].append(target)
    else:
      # If an illegal root_type has been used, mark the host as failed accordingly
      failed_names['root_type'].append(host)
  facts['zfs_filesystems'] = sorted(facts['zfs_filesystems'], key=lambda k: k['name'])
  facts['zvols'] = sorted(facts['zvols'], key=lambda k: k['name'])
  # Return the result, consisting of the failed hosts and the extended hostvars for the current storage server
  result = {'failed_hosts': failed_names, 'new_hostvars': facts}
  return result


if __name__ == "__main__":
  main()
