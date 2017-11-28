# vm-facts

This role parses the existing `hostvars` of VMs and generates vars used by [xen_vman](https://github.com/stuvusIT/xen_vman), [zfs-storage](https://github.com/stuvusIT/zfs-storage/), [zfs-snap-manager](https://github.com/stuvusIT/zfs-snap-manager/) and [iscsi-target](https://github.com/stuvusIT/iscsi-target/).
With correct vars set, this role is able to gather and set all facts needed to create ZFS filesystems/ZVOLs, share them via NFS or iSCSI, snapshot them and configure XEN instances for them.

## Requirements

A Linux distribution.

## Role Variables (storage)

| Name                                | Default / Mandatory | Description                                                                                                                                                                                                                                                                                                                 |
|:------------------------------------|:-------------------:|:----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `vm_facts_variant`                  |      `storage`      | Either `storage` or `hypervisor`. This var is needed to set the correct facts according to the role.                                                                                                                                                                                                                        |
| `vm_facts_zfs_parent_prefix`        |        `''`         | [only needed on `storage`] A prefix string for ZFS filesystems and ZVOLs, e.g. `tank/vms/`.                                                                                                                                                                                                                                 |
| `vm_facts_nfs_options`              |        `[]`         | [only needed on `storage`] A list of NFS options, e.g. a default IP that is added to all exports. The option format must conform to the ZFS `sharenfs` attribute format.                                                                                                                                                    |
| `vm_facts_iscsi_initiators`         |        `[]`         | [only needed on `storage`] List of iSCSI initiators allowed to connect to the generated iSCSI targets. See [Initiators](#initiators)..                                                                                                                                                                                      |
| `vm_facts_iscsi_portals`            |        `[]`         | [only needed on `storage`] List of iSCSI portals (dicts that contain the `ip` and optionally the `port`) that are allowed to connect to iSCSI targets.                                                                                                                                                                      |
| `vm_facts_default_root_reservation` |                     | [only needed on `storage`] If this var is set (e.g. to `10G` or any other allowed value for ZFS `reservation` attribute), root filesystems will use it as reservation by default. Otherwise, the size of the VM will be set as reservation. Independently, custom `reservation` may be set in the `vm.filesystems` variable |

### Initiators

| Name              | Default / Mandatory | Description                                              |
|:------------------|:-------------------:|:---------------------------------------------------------|
| `name`            | :heavy_check_mark:  | WWN of the initiator that should have access to all VMs. |
| `userid`          | :heavy_check_mark:  | `userid` used to authenticate the initiator              |
| `password`        | :heavy_check_mark:  | `password` used to authenticate the initiator            |
| `userid_mutual`   |                     | `userid_mutual` used to authenticate the target          |
| `password_mutual` |                     | `password_mutual` used to authenticate the target        |


## Role Variables (VM hostvars)

As this role looks at all `hostvars`, some variables, especially the `vm` block are relevant. 
This table only lists the options used in this role, see [xen-vman](https://github.com/stuvusIT/xen_vman#vm-variables) for other possible and mandatory vars inside the `vm` dict.

### vm

| Name           |                                                           Default / Mandatory                                                           | Description                                                                                                                                                                                                                                                                                 |
|:---------------|:---------------------------------------------------------------------------------------------------------------------------------------:|:--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
|                |                                                                                                                                         |                                                                                                                                                                                                                                                                                             |
| `org`          |                                                           :heavy_check_mark:                                                            | The organization this VM belongs to. Depending on this value, the filesystem or ZVOL will be placed at a different hierarchy level.                                                                                                                                                         |
| `storage_type` |                                                              `filesystem`                                                               | Use `blockdevice` to create a ZVOL (ZFS virtual blockdevice of static size) and export it (as `{{ org }}-{{ name }}`) via iSCSI. Use `filesystem` (the default) to create a root filesystem `{{ name }}-root` and optionally other filesystems (see `filesystems`) and export them via NFS. |
| `size`         |                                                           :heavy_check_mark:                                                            | Size of the root blockdevice or filesystem, e.g. `15G`. Depending on the `storage_type`, the size may be changed later easily or with a bit of work.                                                                                                                                        |
| `filesystems`  | `[{'name': root, 'zfs_attributes':{'quota': {{size}}, 'reservation': {{size}}}, 'nfs_options': [no_root_squash,rw=@{{interface.ip}}]}]` | A list containing filesystem definitions, see [filesystems](#filesystems) - this var is only relevant if `storage_type=filesystem`.                                                                                                                                                         |
| `interfaces`   |                                                           :heavy_check_mark:                                                            | Description of interfaces, see (`vm.interfaces`)[https://github.com/stuvusIT/xen_vman#vm-interfaces]. This var may also be on the root level of the VM host in question.                                                                                                                    |
| `description`  |                                                           :heavy_check_mark:                                                            | Description of this VM's purpose. This var may also be on the root level of the VM host in question.                                                                                                                                                                                        |

#### filesystems

`vm.filesystems` is a list of dicts that describe filesystems for one VM. A `root` filesystem will always be created, with `quota` set to the VM `size` value, `reservation` set to the global default value or also the VM `size` (see above) and the NFS option `no_root_squash` added. The `filesystems` var is only respected if `storage_type` is `filesystem`.

| Name             |   Default / Mandatory    | Description                                                                                                                                                                                                                                                                                                                                         |
|:-----------------|:------------------------:|:----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `name`           |    :heavy_check_mark:    | `name`-suffix of the filesystem. The final name consists of the vm name and the filesystem name, delimited by a dash.                                                                                                                                                                                                                               |
| `zfs_attributes` |           `{}`           | A dict containing any ZFS attributes that shall be set for this filesystem. It is recommended to define a `quota`, though this may also be done in the default ZFS attributes on the actual [zfs-storage](https://github.com/stuvusIT/zfs-storage/) server.                                                                                         |
| `nfs_options`    | `[rw=@{{interface.ip}}]` | A list of NFS options that are set for this NFS export. The default is an rw access for every IP defined in (`vm.interfaces`)[https://github.com/stuvusIT/xen_vman#vm-interfaces]. The options have to conform to the ZFS `sharenfs` attribute format. The options defined in `vm_nfs_options` will be set in addition to this value in every case. |

## Example Playbook

### Storage

```yml
- hosts: zfsstorage
  roles:
    - role: vm-facts
      vm_facts_facts_variant: storage
      vm_facts_zfs_parent_prefix: tank/vms/
      vm_facts_iscsi_initiators:
       - name: 'iqn.1994-05.com.redhat:client1'
         userid: myuser
         password: mypassword
         userid_mutual: sharedkey
         password_mutual: sharedsecret
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
```

### Result

Assuming the vm is named `web01`, these two filesystems will be created:

|            Name            | ZFS attributes                                                                                                  |
|:--------------------------:|:----------------------------------------------------------------------------------------------------------------|
| `tank/vms/misc/web01-root` | `quota=15G`, `reservation=10G`, `sharenfs=no_root_squash,rw=@192.168.10.2,rw=@192.168.10.52,rw=@192.168.100.52` |
| `tank/vms/misc/web01-data` | `quota=50G`, `sharenfs=rw=@192.168.10.2,rw=@192.168.10.52`                                                      |

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
