# vm-facts

This role parses the existing `hostvars` of VMs and generates vars used by [zfs-storage](https://github.com/stuvusIT/zfs-storage/), [zfs-snap-manager](https://github.com/stuvusIT/zfs-snap-manager/) and [iscsi-target](https://github.com/stuvusIT/iscsi-target/). 
Currently, the storage volumes (ZFS filesystem or ZFS virtual block device) are created and shared to the hypervisor (via NFS or iSCSI).

## Requirements

A Linux distribution.

## Role Variables (storage or hypervisor)

| Name                   | Default / Mandatory | Description                                                                            |
|:-----------------------|:--------------------|:---------------------------------------------------------------------------------------|
| `vm_facts_variant`     | `storage`           | Either `storage` or hypervisor. Needed to set the correct facts according to the role. |
| `vm_zfs_parent_prefix` | `''`                | A prefix string for ZFS filesystems and ZVOLs, e.g. `tank/vms/`.                       |
| `vm_nfs_access_ips`    | `[]`                | A list of IPs that shall get read/write access on all defined VMs.                     |
| `vm_iscsi_initiators`  | `[]`                | List of iSCSI initiators. See [Initiators](#initiators).                               |

### Initiators

| Name              | Default / Mandatory | Description                                              |
|:------------------|:--------------------|:---------------------------------------------------------|
| `name`            | :heavy_check_mark:  | WWN of the initiator that should have access to all VMs. |
| `userid`          | :heavy_check_mark:  | `userid` used to authenticate the initiator              |
| `password`        | :heavy_check_mark:  | `password` used to authenticate the initiator            |
| `userid_mutual`   |                     | `userid_mutual` used to authenticate the target          |
| `password_mutual` |                     | `password_mutual` used to authenticate the target        |


## Role Variables (VM hostvars)

As this role looks at all `hostvars`, the `vm` dict also affect this role, even if the respective hosts don't run it:

### vm
| Name             | Default / Mandatory | Description                                                                                                                                                                                                                                                      |
|:-----------------|:--------------------|:-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `memory`         | :heavy_check_mark:  | The amount of memory reserved for this VM [MiB].                                                                                                                                                                                                                 |
| `vcpus`          | :heavy_check_mark:  | The number of virtual CPU cores simulated for this VM.                                                                                                                                                                                                           |
| `org`            | :heavy_check_mark:  | The organization this VM belongs to. Depending on this value, the filesystem or ZVOL will be placed at a different hierarchy level.                                                                                                                              |
| `size`           | :heavy_check_mark:  | Size of the VM, e.g. `15G`. Depending on the `root_type`, the size may be changed later easily or with a bit of work.                                                                                                                                            |
| `root_type`      | `zvol`              | `filesystem` to create two filesystems (`{{name}}-root` and `{{name}}-data`) and export them via NFS. `zvol` to create a virtual blockdevice (which is of static size) and export it via iSCSI.                                                                  |
| `zfs_attributes` | `{}`                | A dict to set specific ZFS filesystem/ZVOL attributes.                                                                                                                                                                                                           |
| `nfs_ip`         |                     | One IP that is allowed to access the NFS shares, besides the ones defined in `vm_nfs_access_ips`. If this var is left empty, all IPs that are defined in the hostvar `interfaces` are granted NFS access. This var is only needed if `root_type` is `filesystem` |


## Example Playbook

Including an example of how to use your role (for instance, with variables passed in as parameters) is always nice for users too:

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
```

### Example VM

```yml
vm:
  memory: 2048
  vcpus: 4
  org: misc
  size: 15G
  root_type: filesystem
  nfs_ip: '192.168.10.52' #only this IP can access NFS on the storage server
interfaces:
  - mac: 'AA:BB:CC:FE:19:AA'
    ip:  '192.168.10.52'
  - mac: 'AA:BB:CC:FE:19:AB'
    ip:  '192.168.100.52'
```


## License

This work is licensed under a [Creative Commons Attribution-ShareAlike 4.0 International License](http://creativecommons.org/licenses/by-sa/4.0/).


## Author Information

 * [Michel Weitbrecht (SlothOfAnarchy)](https://github.com/SlothOfAnarchy) _michel.weitbrecht@stuvus.uni-stuttgart.de_
