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


class SSHClientTestCase(base.WhiteboxPluginTestCase):

    def setUp(self):
        super(SSHClientTestCase, self).setUp()
        self.client = clients.SSHClient('fake-host')

    @mock.patch('tempest.lib.common.ssh.Client.exec_command')
    def test_execute(self, mock_exec):
        # Test "vanilla" execute()
        self.client.execute('fake command')
        mock_exec.assert_called_with('fake command')
        mock_exec.reset_mock()

        # Test sudo without containers
        self.client.execute('fake command', sudo=True)
        mock_exec.assert_called_with('sudo fake command')
        mock_exec.reset_mock()

        # Test that container_name is ignored unless containers is set in CONF
        self.client.execute('fake command', container_name='fake-container')
        mock_exec.assert_called_with('fake command')
        mock_exec.reset_mock()

        # Test that containers in CONF is ignored unless container_name is
        # passed
        self.flags(containers=True, group='whitebox')
        self.client.execute('fake command')
        mock_exec.assert_called_with('fake command')
        mock_exec.reset_mock()

        # Test that container_name is used when containers is set in CONF
        self.client.execute('fake command', container_name='fake-container')
        mock_exec.assert_called_with('sudo docker exec -u root '
                                     'fake-container fake command')
        mock_exec.reset_mock()

        # Test that container_runtime is read from CONF if set
        self.flags(container_runtime='podman', group='whitebox')
        self.client.execute('fake command', container_name='fake-container')
        mock_exec.assert_called_with('sudo podman exec -u root '
                                     'fake-container fake command')
        mock_exec.reset_mock()


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
