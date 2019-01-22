# Copyright 2018 Red Hat
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

import mock
import textwrap

from whitebox_tempest_plugin.services import clients
from whitebox_tempest_plugin.tests import base


class ConfigClientTestCase(base.WhiteboxPluginTestCase):

    def test_getopt(self):
        config_client = clients.NovaConfigClient('fake-host')
        fake_config = textwrap.dedent("""
            [default]
            fake-key = fake-value""").strip()
        with mock.patch.object(config_client, '_read_nova_conf',
                               return_value=fake_config):
            self.assertEqual(config_client.getopt('default', 'fake-key'),
                             'fake-value')
