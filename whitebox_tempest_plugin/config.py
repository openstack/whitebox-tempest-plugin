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


group = cfg.OptGroup(
    name='whitebox',
    title='Whitebox Tempest plugin config options')

opts = [
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
]
