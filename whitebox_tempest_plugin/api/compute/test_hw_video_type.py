# Copyright 2020 Red Hat
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

from tempest.common import waiters
from tempest import config
import testtools

from whitebox_tempest_plugin.api.compute import base

CONF = config.CONF


class HwVideoModelTest(base.BaseWhiteboxComputeTest):
    """Tests the support of different hardware video model type
     virtio and none that can be set through image
    meta data property flag "hw_video_model".
    """

    def setUp(self):
        super(HwVideoModelTest, self).setUp()

        self.virtio_image_id = self.copy_default_image(hw_video_model='virtio')
        self.none_image_id = self.copy_default_image(hw_video_model='none')

    def _assert_hw_video_type(self, server, hw_video_type):
        root = self.get_server_xml(server['id'])
        hw_video = root.find('./devices/video/model')
        self.assertEqual(hw_video_type, hw_video.get('type'))

    def test_create_virtio_instance(self):
        server = self.create_test_server(image_id=self.virtio_image_id)
        self._assert_hw_video_type(server, 'virtio')

    def test_create_none_instance(self):
        server = self.create_test_server(image_id=self.none_image_id)
        self._assert_hw_video_type(server, 'none')

    def test_rebuild_virtio_to_none(self):
        server = self.create_test_server(image_id=self.virtio_image_id)
        self._assert_hw_video_type(server, 'virtio')
        self.servers_client.rebuild_server(server['id'], self.none_image_id)
        waiters.wait_for_server_status(self.servers_client, server['id'],
                                       'ACTIVE')
        self._assert_hw_video_type(server, 'none')

    def test_rebuild_none_to_virtio(self):
        server = self.create_test_server(image_id=self.virtio_image_id)
        self._assert_hw_video_type(server, 'virtio')
        self.servers_client.rebuild_server(server['id'], self.none_image_id)
        waiters.wait_for_server_status(self.servers_client, server['id'],
                                       'ACTIVE')
        self._assert_hw_video_type(server, 'none')

    @testtools.skipUnless(CONF.whitebox.default_video_model,
                          'Requires expected default video model')
    def test_default_hw_device(self):
        expected_video_model = CONF.whitebox.default_video_model
        server = self.create_test_server()
        self._assert_hw_video_type(server, expected_video_model)
