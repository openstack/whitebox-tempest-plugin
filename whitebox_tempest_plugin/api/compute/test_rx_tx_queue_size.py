# Copyright 2018 Red Hat
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

import testtools

from oslo_log import log as logging
from tempest import config

from whitebox_tempest_plugin.api.compute import base

CONF = config.CONF
LOG = logging.getLogger(__name__)


class RxTxQueueSizeTest(base.BaseWhiteboxComputeTest):

    create_default_network = True

    @testtools.skipUnless(CONF.whitebox.rx_queue_size,
                          '`rx_queue_size` must be set')
    def test_rx_queue_size(self):
        server = self.create_test_server()
        domain = self.get_server_xml(server['id'])
        interface_criteria = \
            "devices/interface[@type='%s']/driver[@name='vhost']"
        driver = domain.find(interface_criteria % 'ethernet')
        driver = (driver if driver is not None else domain.find(
            interface_criteria % 'bridge'))
        self.assertEqual(
            driver.attrib['rx_queue_size'], str(CONF.whitebox.rx_queue_size),
            "Can't find interface with the proper rx_queue_size")
