#!/usr/bin/env python3
# This script generates storage (ZFS, iSCSI) facts out of the hostvars of each VM
import json
import optparse


def main():
  p = optparse.OptionParser(
    description='Sets the relevant ansible facts needed for a ZFS VM storage server (ZFS, NFS, iSCSI).',
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


def generateIscsiTarget(name, path):
  """Generates the configuration for an iSCSI target"""
  target = {'name': name, 'disks': {'name': name, 'path': path}}
  return target


def generateFacts(original_facts, storage_host):
  # facts are the hostvars of the current host
  facts = original_facts[storage_host] if storage_host in original_facts else {}
  vm_facts_variant = facts['vm_facts_variant'] if 'vm_facts_variant' in facts else 'storage'
  # ZFS filesystem prefix to be added in front of every generated ZFS filesystem
  fs_prefix = facts['vm_facts_storage_zfs_parent_prefix'] if 'vm_facts_storage_zfs_parent_prefix' in facts else 'tank/'
  # ZFS filesystem prefix on the backup host (where filesystems will be sent to using zfs-snap-manager)
  backup_prefix = facts[
    'vm_facts_backup_zfs_parent_prefix'] if 'vm_facts_backup_zfs_parent_prefix' in facts else 'tank/'
  # List of NFS options that will be set on all exports
  nfs_options = facts['vm_facts_nfs_options'] if 'vm_facts_nfs_options' in facts else []
  # List of hostnames that have missing VM vars. This lists will be printed in tasks for easier debugging
  failed_names = {'size': [], 'org': []}

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

    # Get storage type. filesystem is the default
    storage_type = config['storage_type'] if 'storage_type' in config else facts['vm_facts_default_storage_type']

    # If the VM wants a ZVOL (virtual block device), create it and export it via iSCSI
    if storage_type == 'blockdevice':
      # Create ZVOL if it doesn't already exist
      if not any(d['name'] == fs_prefix + org + '/' + host for d in facts['zvols']):
        # volsize must be set at creation and cannot be changed later on
        zvol = {'name': fs_prefix + org + '/' + host, 'attributes': {'volsize': config['size']}}
        if vm_facts_variant == 'storage':
          zvol['snapshots'] = {'repilcate_target': backup_prefix + org + '/' + host}
        facts['zvols'].append(zvol)

      # Create iSCSI target config, if it doesn't already exist
      if vm_facts_variant == 'storage' and not any(d['name'] == fs_prefix + org + '-' + host
                                                   for d in facts['iscsi_targets']):
        target = generateIscsiTarget(org + '-' + host, fs_prefix + org + '/' + host)
        facts['iscsi_targets'].append(target)

    # If the VM wants ZFS filesystems (the default), configure them and export them via NFS
    else:
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
          if vm_facts_variant == 'storage':
            attributes['quota'] = config['size']
          if 'reservation' not in attributes:
            attributes['reservation'] = facts[
              'vm_facts_default_root_reservation'] if 'vm_facts_default_root_reservation' in facts else config['size']
          nfs_options_to_set.append('no_root_squash')
        if vm_facts_variant == 'backup':
          nfs_options_to_set = []
        attributes['sharenfs'] = 'off' if not nfs_options_to_set else ','.join(sorted(set(nfs_options_to_set)))
        # Create and add root and data filesystems if necessary
        if fs_prefix + org + '/' + host + '-' + fs['name'] not in facts['zfs_filesystems']:
          zfs_fs = {'name': fs_prefix + org + '/' + host + '-' + fs['name'], 'attributes': attributes}
          if vm_facts_variant == 'storage':
            zfs_fs['snapshots'] = {'replicate_target': backup_prefix + org + '/' + host + '-' + fs['name']}
          facts['zfs_filesystems'].append(zfs_fs)

  facts['zfs_filesystems'] = sorted(facts['zfs_filesystems'], key=lambda k: k['name'])
  facts['zvols'] = sorted(facts['zvols'], key=lambda k: k['name'])
  # Return the result, consisting of the failed hosts and the extended hostvars for the current storage server
  result = {'failed_hosts': failed_names, 'new_hostvars': facts}
  return result


if __name__ == "__main__":
  main()
