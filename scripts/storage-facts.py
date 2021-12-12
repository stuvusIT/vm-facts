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


def unique(list):
  """Returns a list with all unqiue elements of the given list. Preserves order."""
  return sorted(set(list), key=lambda x: list.index(x))

def generateIscsiTarget(name, path):
  """Generates the configuration for an iSCSI target"""
  target = {'name': name, 'disks': {'name': name, 'path': path}}
  return target


def generateFacts(original_facts, storage_host):
  # facts are the hostvars of the current host
  facts = original_facts[storage_host] if storage_host in original_facts else {}
  if 'vm_facts_generate_storage_facts' in facts and facts['vm_facts_generate_storage_facts']:
    vm_facts_variant = 'storage'
  elif 'vm_facts_generate_backup_facts' in facts and facts['vm_facts_generate_backup_facts']:
    vm_facts_variant = 'backup'
  else:
    vm_facts_variant = 'illegal'
  # ZFS filesystem prefix to be added in front of every generated ZFS filesystem
  pool_prefix = facts[
    'vm_facts_storage_zfs_parent_prefix'] if 'vm_facts_storage_zfs_parent_prefix' in facts else 'tank/'
  fs_prefix = pool_prefix
  # ZFS filesystem prefix on the backup host (where filesystems will be sent to using zfs-snap-manager)
  backup_prefix = facts[
    'vm_facts_backup_zfs_parent_prefix'] if 'vm_facts_backup_zfs_parent_prefix' in facts else 'tank/'
  backup_replication_prefix = facts[
    'vm_facts_backup_replication_zfs_parent_prefix'] if 'vm_facts_backup_replication_zfs_parent_prefix' in facts else 'tank/'
  # List of NFS options that will be set on all exports
  nfs_options = facts['vm_facts_nfs_options'] if 'vm_facts_nfs_options' in facts else ["no_root_squash"]
  # default hostnames, to use when a VM doesn't define a hypervisor/storage/backup host
  default_storage = facts['vm_facts_default_storage_host']
  default_hypervisor = facts['vm_facts_default_hypervisor_host']
  default_backup = facts['vm_facts_default_backup_host']
  default_backup_replication = facts['vm_facts_default_backup_replication_host']

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
  if 'vm_facts_move_storages' not in facts:
    facts['vm_facts_move_storages'] = []
  if 'vm_facts_check_snapshots' not in facts:
    facts['vm_facts_check_snapshots'] = {}

  default_local_snapshots = ['hourly']
  AVAILABLE_LOCAL_SNAPSHOTS = ['frequent', 'hourly', 'daily', 'weekly', 'monthly']

  for frequency in AVAILABLE_LOCAL_SNAPSHOTS:
    if frequency not in facts['vm_facts_check_snapshots'].keys():
      facts['vm_facts_check_snapshots'][frequency] = []

  # Traverse every host defined in hostvars
  for host in original_facts.keys():
    # Skip illegal vm-fact execution and hardware hosts
    if vm_facts_variant == 'illegal':
      break
    if 'vm' not in original_facts[host]:
      continue
    # Limit hosts to those defined in vm_facts_limit_hosts
    if 'vm_facts_limit_hosts' in facts and host not in facts['vm_facts_limit_hosts']:
      continue
    # Determine the storage, hypervisor and backup host to be used for this VM
    storage_for_vm = original_facts[host]['vm']['storage_host'] if 'storage_host' in original_facts[host][
      'vm'] else default_storage
    hypervisor_for_vm = original_facts[host]['vm']['hypervisor_host'] if 'hypervisor_host' in original_facts[host][
      'vm'] else default_hypervisor
    backup_for_vm = original_facts[host]['vm']['backup_host'] if 'backup_host' in original_facts[host][
      'vm'] else default_backup
    backup_replication_for_vm = original_facts[host]['vm']['backup_replication_host'] if 'backup_replication_host' in \
                                                                                         original_facts[host][
                                                                                           'vm'] else default_backup_replication

    # config is the vm dict of a specific VM host
    config = original_facts[host]['vm']

    # Skip VMs that should not be saved/backed up on the current host
    if vm_facts_variant == 'storage':
      if (storage_host != storage_for_vm or ('create_storage' in config and not config['create_storage'])) and (
          ('pull_storage_from' not in config) or (
          'pull_storage_from' in config and storage_host != config['pull_storage_from'])):
        continue
    elif vm_facts_variant == 'backup':
      fs_prefix = pool_prefix + storage_for_vm + '/vms/'
      if (storage_host != backup_for_vm and storage_host != backup_replication_for_vm) or (
          'create_backup' in config and not config['create_backup']):
        continue

    # Don't create this vm if org or size are not set
    if 'org' in config:
      org = config['org']
      if 'size' not in config:
        failed_names['size'].append(host)
        continue
    else:
      failed_names['org'].append(host)
      continue

    # Get storage type. filesystem is the default
    if 'storage_type' in config:
      storage_type = config['storage_type']
    elif 'vm_facts_default_storage_type' in facts:
      storage_type = facts['vm_facts_default_storage_type']
    else:
      storage_type = 'filesystem'

    # If the VM wants a ZVOL (virtual block device), create it and export it via iSCSI
    if storage_type == 'blockdevice':
      # Create ZVOL if it doesn't already exist
      dataset_name = fs_prefix + org + '/' + host
      if not any(d['name'] == dataset_name for d in facts['zvols']):
        # volsize must be set at creation and cannot be changed later on
        zvol = {'name': dataset_name, 'attributes': {'volsize': config['size']}}
        if vm_facts_variant == 'storage':
          zvol['snapshots'] = {'replicate_target': backup_prefix + storage_for_vm + '/vms/' + org + '/' + host}
        else:  # Backup variant
          zvol['attributes']['readonly'] = 'on'
          # If this is the first backup host, configure replication to the replication backup host
          if storage_host == backup_for_vm:
            zvol['snapshots'] = {
              'replicate_target': backup_replication_prefix + storage_for_vm + '/vms/' + org + '/' + host}

        # Create configuration for zfs-auto-snapshot script
        if vm_facts_variant == 'storage' and ('local_snapshots' not in config and len(default_local_snapshots) > 0
                                              or len(config['local_snapshots']) > 0):
          label_list = config['local_snapshots'] if 'local_snapshots' in config else default_local_snapshots
          for label in AVAILABLE_LOCAL_SNAPSHOTS:
            zvol['attributes']['com_sun_auto_snapshot_{}'.format(label)] = label in label_list

        facts['zvols'].append(zvol)

      # Create iSCSI target config, if it doesn't already exist
      if vm_facts_variant == 'storage' and not any(d['name'] == dataset_name for d in facts['iscsi_targets']):
        target = generateIscsiTarget(org + '-' + host, dataset_name)
        facts['iscsi_targets'].append(target)

      # Collect data needed to move VM datasets
      if 'pull_storage_from' in config and config['pull_storage_from'] == storage_host:
        facts['vm_facts_move_storages'].append(
          {'source_storage': storage_host, 'source_dataset': fs_name,
           'target_storage': storage_for_vm,
           'target_dataset_suffix': org + '/' + host,
           'source_backup_dataset': backup_prefix + storage_host + '/vms/' + org + '/' + host,
           'target_backup_dataset': backup_prefix + storage_for_vm + '/vms/' + org + '/' + host,
           'backup_host': backup_for_vm})

      # Every dataset gets snapshotted daily on storage and transferred to backup by zfs-snap-manager.
      # -> no variant checking necessary
      if dataset_name not in facts['vm_facts_check_snapshots']['daily']:
        facts['vm_facts_check_snapshots']['daily'].append(dataset_name)

    # If the VM wants ZFS filesystems (the default), configure them and export them via NFS
    else:
      # Default NFS options if no overrides are specified for a filesystem
      default_nfs_options = list(nfs_options)
      # Add VM IP as rw export
      if vm_facts_variant == 'storage' and 'ansible_host' in original_facts[host]:
        default_nfs_options.insert(0, "rw=@" + original_facts[host]['ansible_host'])
      nfs_options_rw_hypervisor = "rw=@{}".format(original_facts[hypervisor_for_vm]['ansible_host'])
      # Add the IP of the used hypervisor as NFS rw export
      if vm_facts_variant == 'storage' and nfs_options_rw_hypervisor not in default_nfs_options:
        default_nfs_options.insert(0, nfs_options_rw_hypervisor)

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
        # Set sizes and no_root_squash if it is the root filesystem.
        if fs['name'] == 'root':
          if vm_facts_variant == 'storage':
            attributes['quota'] = config['size']
            # This squash option is forced because root access is necessary in all cases
            nfs_options_to_set.append('no_root_squash')
          if 'reservation' not in attributes:
            attributes['reservation'] = facts[
              'vm_facts_default_root_reservation'] if 'vm_facts_default_root_reservation' in facts else config['size']
        # Don't share via NFS on backup hosts
        attributes['sharenfs'] = 'off' if not nfs_options_to_set else ','.join(unique(nfs_options_to_set))
        # Set to readonly and remove quota if on backup
        if vm_facts_variant == 'backup':
          attributes['readonly'] = 'on'
          attributes['quota'] = 'none'

        dataset_name = fs_prefix + org + '/' + host + '-' + fs['name']

        # Create configuration for zfs-auto-snapshot script
        if vm_facts_variant == 'storage' and ('local_snapshots' not in config and len(default_local_snapshots) > 0
                                              or len(config['local_snapshots']) > 0):
          label_list = default_local_snapshots
          if 'local_snapshots' in fs:
            label_list = fs['local_snapshots']
          elif 'local_snapshots' in config:
            label_list = config['local_snapshots']
          for label in AVAILABLE_LOCAL_SNAPSHOTS:
            attributes['com_sun_auto_snapshot_{}'.format(label)] = label in label_list
            if label in label_list:
              facts['vm_facts_check_snapshots'][label].append(dataset_name)

        # Every filesystem gets snapshotted daily on storage and transferred to backup by zfs-snap-manager.
        # -> no variant checking necessary
        if dataset_name not in facts['vm_facts_check_snapshots']['daily']:
          facts['vm_facts_check_snapshots']['daily'].append(dataset_name)

        # Create and add root and data filesystems if necessary
        if dataset_name not in facts['zfs_filesystems']:
          zfs_fs = {'name': dataset_name, 'attributes': attributes}
          if vm_facts_variant == 'storage':
            zfs_fs['snapshots'] = {
              'replicate_target': backup_prefix + storage_for_vm + '/vms/' + org + '/' + host + '-' + fs['name']
            }
          elif vm_facts_variant == 'backup' and storage_host == backup_for_vm:
            # If this is the first backup host, configure replication to the replication backup host
            zfs_fs['snapshots'] = {
              'replicate_target': backup_replication_prefix + storage_for_vm + '/vms/' + org + '/' + host + '-' + fs[
                'name']
            }
          facts['zfs_filesystems'].append(zfs_fs)

        # Collect data needed to move VM datasets
        if 'pull_storage_from' in config and config['pull_storage_from'] == storage_host:
          facts['vm_facts_move_storages'].append(
            {'source_storage': storage_host,
             'source_dataset': fs_prefix + org + '/' + host + '-' + fs['name'],
             'target_storage': storage_for_vm,
             'target_dataset_suffix': org + '/' + host + '-' + fs['name'],
             'source_backup_dataset': backup_prefix + storage_host + '/vms/' + org + '/' + host + '-' + fs[
               'name'],
             'target_backup_dataset': backup_prefix + storage_for_vm + '/vms/' + org + '/' + host + '-' + fs[
               'name'],
             'backup_host': backup_for_vm})

  facts['zfs_filesystems'] = sorted(facts['zfs_filesystems'], key=lambda k: k['name'])
  facts['zvols'] = sorted(facts['zvols'], key=lambda k: k['name'])
  # Return the result, consisting of the failed hosts and the extended hostvars for the current storage server
  result = {'failed_hosts': failed_names, 'new_hostvars': facts}
  return result


if __name__ == "__main__":
  main()
