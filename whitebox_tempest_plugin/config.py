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
        'hypervisors',
        help="Dictionary of hypervisor IP addresses. The keys are the "
             "hostnames as they appear in the OS-EXT-SRV-ATTR:host field of "
             "Nova's show server details API. The values are the ctlplane IP "
             "addresses. For example:"
             ""
             "  hypervisors = compute-0.localdomain:172.16.42.11,"
             "                controller-0.localdomain:172.16.42.10"
             ""
             "While this looks like a poor man's DNS, this is needed "
             "because the environment running the test does not necessarily "
             "have the ctlplane DNS accessible."),
    cfg.IntOpt(
        'max_compute_nodes',
        default=31337,
        help="Number of compute hosts in the deployment. Some tests depend "
             "on there being a single compute host."),
    cfg.StrOpt(
        'container_runtime',
        default="docker",
        choices=["docker", "podman"],
        help="Name of the executable running containers. Correct values are"
        " 'docker' (default) for osp 12 to 14, and 'podman' starting 15")
]

nova_compute_group = cfg.OptGroup(
    name='whitebox-nova-compute',
    title='Config options to manage the nova-compute service')

nova_compute_opts = [
    cfg.StrOpt(
        'config_path',
        help='Path to the configration file for the nova-compute service.'),
    cfg.StrOpt(
        'restart_command',
        help='Command to restart the nova-compute service, without any '
             'privilege management (ie, no sudo).'),
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
