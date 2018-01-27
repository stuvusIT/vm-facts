# vm-facts

This role parses the existing `hostvars` of VMs and generates vars used by [xen_vman](https://github.com/stuvusIT/xen_vman), [zfs-storage](https://github.com/stuvusIT/zfs-storage/), [zfs-snap-manager](https://github.com/stuvusIT/zfs-snap-manager/) and [iscsi-target](https://github.com/stuvusIT/iscsi-target/).
With correct vars set, this role is able to gather and set all facts needed to create ZFS filesystems/ZVOLs, share them via NFS or iSCSI, snapshot them and configure XEN instances for them.

## Requirements

A Linux distribution.

## Role Variables

| Name                                 | Default / Mandatory | Description                                                               |
|:-------------------------------------|:-------------------:|:--------------------------------------------------------------------------|
| `vm_facts_generate_storage_facts`    |       `False`       | Flag to activate fact generation for storage variables (ZFS, NFS, iSCSI). |
| `vm_facts_generate_backup_facts`     |       `False`       | Flag to activate fact generation for storage variables (ZFS).             |
| `vm_facts_generate_hypervisor_facts` |       `False`       | Flag to activate fact generation for hypervisor variables (Xen).          |

`vm_facts_generate_storage_facts` and `vm_facts_generate_backup_facts` are mutually exclusive with `vm_facts_generate_storage_facts` being prioritized.


## Role Variables (needed for storage or backup)

| Name                                 | Default / Mandatory                   | Description                                                                                                                                                                                                                                                                                                                                                      |
|:-------------------------------------|:-------------------------------------:|:-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `vm_facts_storage_zfs_parent_prefix` | `'tank/'`                             | [only needed on `storage` and `backup`] A prefix string for ZFS filesystems and ZVOLs, e.g. `tank/vms/`.                                                                                                                                                                                                                                                         |
| `vm_facts_backup_zfs_parent_prefix`  | `'tank/'`                             | [only needed on `storage`] A prefix string for ZFS filesystems and ZVOLs, e.g. `tank/vms/`. This is used for setting the target filesystems on snapshot configurations (i.e. where on the backup host shall the filesystem on this storage host be placed).                                                                                                      |
	| `vm_facts_nfs_options`               | `[]`                                  | [only needed on `storage`] A list of NFS options, e.g. a default IP that is added to all exports. The option format must conform to the ZFS `sharenfs` attribute format. The role adds by default the `hypervisor_host` or the default hypervisor_host IP as `rw=@{{ hypervisor_host.ansible_host }}` option.                                                                                                                                                                                         |
| `vm_facts_default_root_reservation`  |                                       | [only needed on `storage` and `backup`] If this var is set (e.g. to `10G` or any other allowed value for ZFS `reservation` attribute), root filesystems will use it as reservation by default. Otherwise, the size of the VM will be set as reservation when choosing `storage`. Independently, custom `reservation` may be set in the `vm.filesystems` variable |
| `vm_facts_default_storage_type`      | `filesystem`                          | [only needed on `storage` and `backup`] This storage type will be chosen if the `vm` block does not specify one itself.                                                                                                                                                                                                                                          |
| `iscsi_default_initiators`           | :heavy_check_mark: (if iSCSI is used) | [only needed on `storage`] This var is explained in [iscsi-target](https://github.com/stuvusIT/iscsi-target#role-variables).                                                                                                                                                                                                                                     |
| `iscsi_default_portals`              | :heavy_check_mark: (if iSCSI is used) | [only needed on `storage`] This var is explained in [iscsi-target](https://github.com/stuvusIT/iscsi-target#role-variables).                                                                                                                                                                                                                                     |
| `vm_facts_default_storage_host`      | :heavy_check_mark:                    | Inventory name where the vm should store its data.                                                                                                                                                                                                                                                                                     |

## Role Variables (hypervisor)
| Name                               | Default / Mandatory | Description                                                                                                                  |
|:-----------------------------------|:-------------------:|:-----------------------------------------------------------------------------------------------------------------------------|
| `vm_facts_default_cidr_suffix`     | `/24`               | This suffix will be appended to all IPs in `vm.interfaces` if the IP in question does not already define a CIDR subnet mask. |
| `vm_facts_default_hypervisor_host` | :heavy_check_mark:  | Inventory name where the vm should run on.                                                     |

## Role Variables (VM hostvars)

As this role looks at all `hostvars`, some variables, especially the `vm` block are relevant. 
This table only lists the options used in this role, see [xen-vman](https://github.com/stuvusIT/xen_vman#vm-variables) for other possible and mandatory vars inside the `vm` dict.

### vm

| Name              | Default / Mandatory                                                                                                                                                                | Description                                                                                                                                                                                                                                                                                                                                                |
|:------------------|:----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------:|:-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `org`             | :heavy_check_mark:                                                                                                                                                                 | The organization this VM belongs to. Depending on this value, the filesystem or ZVOL will be placed at a different hierarchy level.                                                                                                                                                                                                                        |
| `storage_type`    | `filesystem`                                                                                                                                                                       | Use `blockdevice` to create a ZVOL (ZFS virtual blockdevice of static size) and export it (as `{{ org }}-{{ name }}`) via iSCSI (only on `storage`). Use `filesystem` (the default) to create a root filesystem `{{ org }}/{{ name }}-root` and optionally other filesystems (see `filesystems`) and export them via NFS (only enabled on type `storage`). |
| `size`            | :heavy_check_mark:                                                                                                                                                                 | Size of the root blockdevice or filesystem, e.g. `15G`. The size can only be changed later on if `storage_type`=`filesystem`.                                                                                                                                                                                                                              |
| `filesystems`     | `[{'name': root, 'zfs_attributes':{'quota': {{size}}, 'reservation': {{size &#124 d(vm_facts_default_root_reservation)}}}, 'nfs_options': [no_root_squash,rw=@{{interface.ip}}]}]` | A list containing filesystem definitions, see [filesystems](#filesystems) - this var is only relevant if `storage_type=filesystem`.                                                                                                                                                                                                                        |
| `interfaces`      | :heavy_check_mark:                                                                                                                                                                 | Description of interfaces, see (`vm.interfaces`)[https://github.com/stuvusIT/xen_vman#vm-interfaces]. This var may also be on the root level of the VM host in question.                                                                                                                                                                                   |
| `description`     | :heavy_check_mark:                                                                                                                                                                 | Description of this VM's purpose. This var may also be on the root level of the VM host in question.                                                                                                                                                                                                                                                       |
| `storage_host`    | `{{ vm_facts_default_storage_host }}`                                                                                                                                              | Storage host to use for this VM.                                                                                                                                                                                                                                                                                                                           |
| `hypervisor_host` | `{{ vm_facts_default_hypervisor_host }}`                                                                                                                                           | Hypervisor host to use for this VM.                                                                                                                                                                                                                                                                                                                        |

#### filesystems

`vm.filesystems` is a list of dicts that describe filesystems for one VM. A `root` filesystem will always be created, with `quota` set to the VM `size` value, `reservation` set to the global default value or also the VM `size` (see above) and the NFS option `no_root_squash` added. On hosts with `vm_facts_variant`=`backup`, no NFS options will be set by default. The `filesystems` var is only respected if `storage_type` is `filesystem`.

| Name             |   Default / Mandatory    | Description                                                                                                                                                                                                                                                                                                                                    |
|:-----------------|:------------------------:|:-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `name`           |    :heavy_check_mark:    | `name`-suffix of the filesystem. The final name consists of the vm name and the filesystem name, delimited by a dash.                                                                                                                                                                                                                          |
| `zfs_attributes` |           `{}`           | A dict containing any ZFS attributes that shall be set for this filesystem. It is recommended to define a `quota`, though this may also be done in the default ZFS attributes on the actual [zfs-storage](https://github.com/stuvusIT/zfs-storage/) server.                                                                                    |
| `nfs_options`    | `[rw=@{{ansible_host}}]` | A list of NFS options that are set for this NFS export. The default is one read-write NFS export for the IP defined in (`ansible_host`) in the hostvars of the respective VM. The options have to conform to the ZFS `sharenfs` attribute format. The options defined in `vm_nfs_options` will be set in addition to this value in every case. |

## Example Playbook

### Storage

```yml
- hosts: zfsstorage
  roles:
    - role: vm-facts
      vm_facts_facts_variant: storage
      vm_facts_storage_zfs_parent_prefix: tank/vms/
      iscsi_default_initiators:
       - name: 'iqn.1994-05.com.redhat:client1'
         authentication:
           userid: myuser
           password: mypassword
           userid_mutual: sharedkey
           password_mutual: sharedsecret
      iscsi_default_portals:
       - ip: 192.168.10.6
      vm_facts_nfs_options:
       - rw=@192.168.10.2
      vm_facts_default_root_reservation: 10G
```

### Hypervisor

```yml
- hosts: xenhypervisor
  roles:
    - role: vm-facts
      vm_facts_facts_variant: hypervisor
```

### Example VM

```yml
vm:
  description: VM to host static websites
  memory: 2048
  vcpus: 4
  org: misc
  size: 15G
  storage_type: filesystem
  filesystems:
   - name: data
     zfs_attributes:
       quota: 50G
     nfs_options:
      - rw=@192.168.10.52
  interfaces:
   - mac: 'AA:BB:CC:FE:19:AA'
     ip:  '192.168.10.52'
   - mac: 'AA:BB:CC:FE:19:AB'
     ip:  '192.168.100.52'
ansible_host: 192.168.10.52
```

### Result

Assuming the vm is named `web01`, these two filesystems will be created:

|            Name            | ZFS attributes                                                                               |
|:--------------------------:|:---------------------------------------------------------------------------------------------|
| `tank/vms/misc/web01-root` | `quota=15G`, `reservation=10G`, `sharenfs=no_root_squash,rw=@192.168.10.2,rw=@192.168.10.52` |
| `tank/vms/misc/web01-data` | `quota=50G`, `sharenfs=rw=@192.168.10.2,rw=@192.168.10.52`                                   |

The hypervisor will have an additional entry in his `xen_vman_vms` list:

```yml
xen_vman_vms:
 - description: VM to host static websites
   memory: 2048
   vcpus: 4
   org: misc
   size: 15G
   storage_type: filesystem
   interfaces:
    - mac: 'AA:BB:CC:FE:19:AA'
      ip:  '192.168.10.52'
    - mac: 'AA:BB:CC:FE:19:AB'
      ip:  '192.168.100.52'
```

Note that `filesystems` has been removed as it is not needed by the hypervisor.

## License

This work is licensed under a [Creative Commons Attribution-ShareAlike 4.0 International License](http://creativecommons.org/licenses/by-sa/4.0/).

## Author Information

- [Michel Weitbrecht (SlothOfAnarchy)](https://github.com/SlothOfAnarchy) _michel.weitbrecht@stuvus.uni-stuttgart.de_
