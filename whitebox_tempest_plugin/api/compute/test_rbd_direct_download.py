
# Copyright 2021 Red Hat Inc.
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

from oslo_log import log as logging
from tempest import config

from whitebox_tempest_plugin.api.compute import base
from whitebox_tempest_plugin.services import clients

CONF = config.CONF
LOG = logging.getLogger(__name__)


class TestRBDDirectDownload(base.BaseWhiteboxComputeTest):
    """Test validating RBD direct download configuration
       and logs
    """

    @classmethod
    def skip_checks(cls):
        super(TestRBDDirectDownload, cls).skip_checks()
        if not CONF.compute_feature_enabled.rbd_download:
            skip_msg = ("%s skipped as rbd-download is "
                        "not enabled" % cls.__name__)
            raise cls.skipException(skip_msg)

    def test_rbd_logs_and_conf(self):
        base_server = self.create_test_server(wait_until='ACTIVE')
        image = self.create_image_from_server(
            base_server['id'],
            name='base-server-img',
            wait_until='ACTIVE'
        )
        # Creating a server from above image ensures a fresh
        # attempt is made to download an image from the rbd
        # pool to the local compute
        server = self.create_test_server(wait_until='ACTIVE',
                                         image_id=image['id'])

        # Grab image id from newly created server
        detailed_server_data = \
            self.os_admin.servers_client.show_server(server['id'])['server']
        image_id = detailed_server_data['image']['id']

        host = self.get_host_for_server(server['id'])
        host_sm = clients.NovaServiceManager(host, 'nova-compute',
                                             self.os_admin.services_client)
        rbd_pool = host_sm.get_conf_opt('glance', 'rbd_pool')
        # Assert RBD direct download conf options
        self.assertEqual('images', rbd_pool)
        self.assertTrue(host_sm.get_conf_opt('glance', 'enable_rbd_download'))
        log_query_string = f"Attempting to export RBD image: " \
            f"[[]pool_name: {rbd_pool}[]] [[]image_uuid: " \
            f"{image_id}[]]"
        logs_client = clients.LogParserClient(host)
        # Assert if log with specified image is found
        self.assertTrue(len(logs_client.parse(log_query_string)))
        path = self.get_server_blockdevice_path(server['id'], 'vda')
        # Assert image disk is present in ephemeral
        # instances_path and not in rbd
        self.assertIsNotNone(path) and self.assertNotIn('rbd', path)
