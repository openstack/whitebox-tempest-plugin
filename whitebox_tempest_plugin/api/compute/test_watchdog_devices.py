# Copyright 2024 Red Hat
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

import ddt
from whitebox_tempest_plugin.api.compute import base


@ddt.ddt
class WatchdogDeviceTest(base.BaseWhiteboxComputeTest):

    def _get_watchdog_action_from_xml(self, server_id):
        root = self.get_server_xml(server_id)
        return root.find(".devices/watchdog")

    @ddt.data('reset', 'poweroff', 'pause', 'none', 'disabled')
    def test_action_with_flavor(self, action):
        flavor_id = self.create_flavor(
            extra_specs={"hw:watchdog_action": action})['id']
        server = self.create_test_server(
            flavor=flavor_id, wait_until='ACTIVE')

        watchdog_dev = self._get_watchdog_action_from_xml(server['id'])

        if action == 'disabled':
            # as watchdog is disabled there is no watchdog dev in xml
            self.assertIsNone(watchdog_dev)
        else:
            self.assertEqual(action, watchdog_dev.attrib['action'])

    @ddt.data(
        ('reset', 'pc'), ('poweroff', 'pc'), ('pause', 'pc'), ('none', 'pc'),
        ('disabled', 'pc'),
        ('reset', 'q35'), ('poweroff', 'q35'), ('pause', 'q35'),
        ('none', 'q35'), ('disabled', 'q35')
    )
    @ddt.unpack
    def test_action_with_image(self, action, m_type):
        image_id = self.copy_default_image(
            hw_watchdog_action=action,
            hw_machine_type=m_type
        )
        server = self.create_test_server(
            image_id=image_id, wait_until='ACTIVE')

        watchdog_dev = self._get_watchdog_action_from_xml(server['id'])

        if m_type == 'q35' and action == 'disabled':
            # for machine_type q35, disabled watchdog exist with 'reset'
            self.assertEqual('reset', watchdog_dev.attrib['action'])
        elif m_type == 'pc' and action == 'disabled':
            # as watchdog is disabled there is no watchdog dev in xml
            self.assertIsNone(watchdog_dev)
        else:
            self.assertEqual(action, watchdog_dev.attrib['action'])
