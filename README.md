# vm-facts

This role parses the existing `hostvars` of VMs and generates vars used by [zfs-storage](https://github.com/stuvusIT/zfs-storage/), [zfs-snap-manager](https://github.com/stuvusIT/zfs-snap-manager/) and [iscsi-target](https://github.com/stuvusIT/iscsi-target/). 
Currently, the storage volumes (ZFS filesystem or ZFS virtual block device) are created and shared to the hypervisor (via NFS or iSCSI).

## Requirements

A Linux distribution.

## Role Variables (storage)

| Name                   | Default / Mandatory | Description                                                                                                                                   |
|:-----------------------|:-------------------:|:----------------------------------------------------------------------------------------------------------------------------------------------|
| `vm_facts_variant`     |      `storage`      | Either `storage` or hypervisor. Needed to set the correct facts according to the role.                                                        |
| `vm_zfs_parent_prefix` |        `''`         | A prefix string for ZFS filesystems and ZVOLs, e.g. `tank/vms/`.                                                                              |
| `vm_nfs_options`       |        `[]`         | A list of NFS options, e.g. a default IP that is added to all exports. The option format must conform to the ZFS `sharenfs` attribute format. |
| `vm_iscsi_initiators`  |        `[]`         | List of iSCSI initiators. See [Initiators](#initiators).                                                                                      |
| `vm_iscsi_portals`     |        `[]`         | List of iSCSI portals (dicts that contain the `ip` and optionally the `port`) that are allowed to connect to iSCSI targets.                   |

### Initiators

| Name              | Default / Mandatory | Description                                              |
|:------------------|:-------------------:|:---------------------------------------------------------|
| `name`            | :heavy_check_mark:  | WWN of the initiator that should have access to all VMs. |
| `userid`          | :heavy_check_mark:  | `userid` used to authenticate the initiator              |
| `password`        | :heavy_check_mark:  | `password` used to authenticate the initiator            |
| `userid_mutual`   |                     | `userid_mutual` used to authenticate the target          |
| `password_mutual` |                     | `password_mutual` used to authenticate the target        |


## Role Variables (VM hostvars)

As this role looks at all `hostvars`, the `vm` dict also affect this role, even if the respective hosts don't run it:

### vm
| Name          |                                Default / Mandatory                                | Description                                                                                                                                                                                                                      |
|:--------------|:---------------------------------------------------------------------------------:|:---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `memory`      |                                :heavy_check_mark:                                 | The amount of memory reserved for this VM [MiB].                                                                                                                                                                                 |
| `vcpus`       |                                :heavy_check_mark:                                 | The number of virtual CPU cores simulated for this VM.                                                                                                                                                                           |
| `org`         |                                :heavy_check_mark:                                 | The organization this VM belongs to. Depending on this value, the filesystem or ZVOL will be placed at a different hierarchy level.                                                                                              |
| `size`        |                                :heavy_check_mark:                                 | Size of the root image or filesystem, e.g. `15G`. Depending on the `root_type`, the size may be changed later easily or with a bit of work.                                                                                      |
| `root_type`   |                                      `zvol`                                       | `zvol` to create a virtual blockdevice (which is of static size) and export it via iSCSI. `filesystem` to create a root filesystem `{{name}}-root` and optionally other filesystems (see `filesystems`) and export them via NFS. |
| `filesystems` | `[{'name': root, 'zfs_attributes':{'quota': {{size}}, 'reservation': {{size}}}}]` | A list containing filesystem definitions, see [filesystems](#filesystems)..                                                                                                                                                      |

#### filesystems

`filesystems` is a list of dicts that describe filesystems for one VM. A `root` filesystem will always be created, with `quota` and `reservation` set to the VM `size` value. The `filesystems` var is only respected if `root_type` is `filesystem`.

| Name             |   Default / Mandatory    | Description                                                                                                                                                                                                                                                                              |
|:-----------------|:------------------------:|:-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `name`           |    :heavy_check_mark:    | `name`-suffix of the filesystem. The final name consists of the vm name and the filesystem name, delimited by a dash.                                                                                                                                                                    |
| `zfs_attributes` |           `{}`           | A dict containing any ZFS attributes that shall be set for this filesystem. It is recommended to define a `quota`, though this may also be done in the default ZFS attributes on the actual [zfs-storage](https://github.com/stuvusIT/zfs-storage/) server.                              |
| `nfs_options`    | `[rw=@{{interface.ip}}]` | A list of NFS options that are set for this NFS export. The default is an rw access for every IP defined in the hostvar `interfaces`. The options have to conform to the ZFS `sharenfs` attribute format. The options defined in `vm_nfs_options` will be set in addition to this value. |



## Example Playbook

### Storage
```yml
- hosts: zfsstorage
  roles:
    - role: vm-facts
      vm_facts_variant: storage
      vm_zfs_parent_prefix: tank/vms/
      vm_iscsi_initiators:
       - name: 'iqn.1994-05.com.redhat:client1'
         userid: myuser
         password: mypassword
         userid_mutual: sharedkey
         password_mutual: sharedsecret
      vm_nfs_options:
       - rw=@192.168.10.2
```

### Example VM

```yml
vm:
  memory: 2048
  vcpus: 4
  org: misc
  size: 15G
  root_type: filesystem
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

|            Name            | ZFS attributes                                                                                   |
|:--------------------------:|:-------------------------------------------------------------------------------------------------|
| `tank/vms/misc/web01-root` | `quota=15G`, `reservation=15G`, `sharenfs=rw=@192.168.10.2,rw=@192.168.10.52,rw=@192.168.100.52` |
| `tank/vms/misc/web01-data` | `quota=50G`, `sharenfs=rw=@192.168.10.2,rw=@192.168.10.52`                                       |


## License

This work is licensed under a [Creative Commons Attribution-ShareAlike 4.0 International License](http://creativecommons.org/licenses/by-sa/4.0/).


## Author Information

 * [Michel Weitbrecht (SlothOfAnarchy)](https://github.com/SlothOfAnarchy) _michel.weitbrecht@stuvus.uni-stuttgart.de_
