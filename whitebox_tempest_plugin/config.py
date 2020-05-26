# Copyright 2016
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from oslo_config import cfg
from oslo_config import types


general_group = cfg.OptGroup(
    name='whitebox',
    title='General Whitebox Tempest plugin config options')

general_opts = [
    cfg.StrOpt(
        'ctlplane_ssh_username',
        help='Username to use when accessing controllers and/or compute hosts '
             'over SSH.',
        default='heat-admin',
        deprecated_opts=[cfg.DeprecatedOpt('target_ssh_user',
                                           group='whitebox')]),
    cfg.StrOpt(
        'ctlplane_ssh_private_key_path',
        help='Path to the private key to use when accessing controllers '
             'and/or compute hosts over SSH.',
        default='/home/stack/.ssh/id_rsa',
        deprecated_opts=[cfg.DeprecatedOpt('target_private_key_path',
                                           group='whitebox')]),
    cfg.BoolOpt(
        'containers',
        default=False,
        help='Deployment is containerized.'),
    cfg.DictOpt(
        'ctlplane_addresses',
        help="Dictionary of control plane addresses. The keys are the "
             "compute hostnames as they appear in the OS-EXT-SRV-ATTR:host "
             "field of Nova's show server details API. The values are the "
             "control plane addresses. For example:"
             ""
             "  ctlplane_addresses = compute-0.localdomain:172.16.42.11,"
             "                        compute-1.localdomain:172.16.42.10"
             ""
             "While this looks like a poor man's DNS, this is needed "
             "because the environment running the test does not necessarily "
             "have the ctlplane DNS accessible.",
        deprecated_opts=[cfg.DeprecatedOpt('hypervisors',
                                           group='whitebox')]),
    cfg.IntOpt(
        'max_compute_nodes',
        default=31337,
        help="Number of compute hosts in the deployment. Some tests depend "
             "on there being a single compute host."),
    cfg.IntOpt(
        'available_cinder_storage',
        default=0,
        help="Cinder storage available to the deployment (in GB)."),
    cfg.StrOpt(
        'container_runtime',
        default="docker",
        choices=["docker", "podman"],
        help="Name of the executable running containers. Correct values are"
        " 'docker' (default) for osp 12 to 14, and 'podman' starting 15"),
    cfg.IntOpt(
        'file_backed_memory_size',
        default=0,
        help="file_backed_memory size in mb used to set the"
             " [libvirt]/file_backed_memory in nova.conf"),
    cfg.StrOpt(
        'selinux_label',
        default=None,
        help='provide the selinux labels used by the instance'),
    cfg.StrOpt(
        'selinux_imagelabel',
        default=None,
        help='provide the selinux image labels used by the instance'),
    cfg.IntOpt(
        'flavor_volume_size',
        default=1,
        help="volume size for flavor used in whitebox test"),
    cfg.StrOpt(
        'cpu_model',
        help='The CPU model set in the [libvirt]/cpu_models config option '
             'on the compute hosts. While Nova supports multiple cpu_models '
             '(and has deprecated the old singular [libvirt]/cpu_model '
             'option), whitebox assumes a single CPU model.'),
    cfg.ListOpt(
        'cpu_model_extra_flags',
        help='Extra flags set in the [libvirt]/cpu_model_extra_flags config '
             'option on the compute hosts.'),
]

nova_compute_group = cfg.OptGroup(
    name='whitebox-nova-compute',
    title='Config options to manage the nova-compute service')

nova_compute_opts = [
    cfg.StrOpt(
        'config_path',
        help='Path to the configration file for the nova-compute service.'),
    cfg.StrOpt(
        'start_command',
        help='Command to start the nova-compute service, without any '
             'privilege management (ie, no sudo).'),
    cfg.StrOpt(
        'stop_command',
        help='Command to stop the nova-compute service, without any '
             'privilege management (ie, no sudo).'),
]

libvirt_group = cfg.OptGroup(
    name='whitebox-libvirt',
    title='Config options to manage the libvirt service')

libvirt_opts = [
    cfg.StrOpt(
        'start_command',
        help='Command to start the libvirt service, without any '
             'privilege management (ie, no sudo).'),
    cfg.StrOpt(
        'stop_command',
        help='Command to stop the libvirt service, without any '
             'privilege management (ie, no sudo).',
        deprecated_opts=[cfg.DeprecatedOpt('stop_command',
                                           group='whitebox-nova-libvirt')]),
    cfg.StrOpt(
        'mask_command',
        help='In some situations (Ubuntu Focal, for example), libvirtd can '
             'be activated by other systemd units even if it is stopped. '
             'In such cases, it can be useful to mask a service (ie, disable '
             'it completely) to prevent it from being started outside of our '
             'control. This config options sets the command to mask libvirt. '
             'If set, it will be executed after every stop command.'),
    cfg.StrOpt(
        'unmask_command',
        help='Similar to the mask_command option, this config options sets '
             'the command to unmask libvirt. If set, it will be run before '
             'every start command.'),
]

database_group = cfg.OptGroup(
    name='whitebox-database',
    title='Config options to access the database.')

database_opts = [
    cfg.StrOpt(
        'host',
        help='Address of the database host. This is normally a controller.'),
    cfg.StrOpt(
        'internal_ip',
        help='If the databse service is listening on separate internal '
             'network, this option specifies its IP on that network. It will '
             'be used to set up an SSH tunnel through the database host.'),
    cfg.StrOpt(
        'user',
        help='Username to use when connecting to the database server. '
             'This should normally be the root user, as it needs to '
             'have permissions on all databases.'),
    cfg.StrOpt(
        'password',
        help='The password to use when connecting to the database server.'),
    cfg.StrOpt(
        'nova_cell1_db_name',
        default="nova_cell1",
        help="Name of the Nova db to use for connection"),
    cfg.IntOpt(
        'ssh_gateway_port',
        default=3306,
        help="SSH port forwarding gateway number")
]

hardware_group = cfg.OptGroup(
    name='whitebox-hardware',
    title='Config options that describe the underlying compute node hardware '
          'in the environment.')

hardware_opts = [
    cfg.StrOpt(
        'vgpu_vendor_id',
        default=None,
        help='The vendor id of the underlying vgpu hardware of the compute. '
             'An example with Nvidia would be 10de'),
    cfg.ListOpt(
        'smt_hosts',
        default=[],
        help='List of compute hosts that have SMT (Hyper-Threading in Intel '
             'parlance).'),
    cfg.Opt(
        'cpu_topology',
        type=types.Dict(types.List(types.Integer(), bounds=True)),
        help='Host CPU topology, as a dictionary of <NUMA node ID>:'
             '<List of CPUs in that node>. For example, if NUMA node 0 has '
             'CPUs 0 and 1, and NUMA node 1 has CPUs 2 and 3, the value to '
             'set would be `0: [0,1], 1: [2, 3]`.'),
    cfg.StrOpt(
        'sriov_physnet',
        default=None,
        help='The physnet to use when creating sr-iov ports'),
    cfg.IntOpt(
        'physnet_numa_affinity',
        default=None,
        help="A one to one affinity mapping of the parameter sriov_phsynet to "
        "its underlying NIC's NUMA Node. A physnet mapping of one to many "
        "NUMAs is not supported with this parameter")
]
