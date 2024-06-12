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

import os

from tempest import config

from whitebox_tempest_plugin.api.compute import base
from whitebox_tempest_plugin.services import clients

CONF = config.CONF


class TestStableCpuId(base.BaseWhiteboxComputeTest):
    """Test nova-compute generates a proper compute_id at startup.
    """
    min_microversion = '2.53'

    @classmethod
    def skip_checks(cls):
        super(TestStableCpuId, cls).skip_checks()
        if not CONF.compute_feature_enabled.stable_compute_uuid_supported:
            raise cls.skipException(
                'Deployment requires support for stable compute UUID feature. '
                'Set [compute-feature-enabled]stable_compute_uuid_supported '
                'to True to enable these tests.')

    def test_compute_id_file_match_db_state(self):
        compute_id_path = os.path.join(
            CONF.whitebox_nova_compute.state_path, "compute_id")
        hypervisors = self.os_admin.hypervisor_client.list_hypervisors(
        )["hypervisors"]
        for hypervisor in hypervisors:
            name = hypervisor['hypervisor_hostname']
            ssh_client = clients.SSHClient(name)
            uuid_on_disk = ssh_client.execute(f'cat {compute_id_path}',
                                              sudo=True)
            uuid_on_disk = uuid_on_disk.rstrip()
            self.assertEqual(
                hypervisor['id'],
                uuid_on_disk,
                f"Compute UUID does not match on {name}: "
                f"on disk: {uuid_on_disk}, in DB: {hypervisor['id']}",
            )
